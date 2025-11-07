# scripts/export_poisson_inputs_from_api.py
# -*- coding: utf-8 -*-
import os
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Iterable

import requests
import pandas as pd

API_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
BASE_URL = (os.getenv("API_FOOTBALL_BASE") or "https://v3.football.api-sports.io/").rstrip("/") + "/"
SEASONS_ENV = os.getenv("API_FOOTBALL_SEASONS") or os.getenv("API_FOOTBALL_SEASON") or "2024,2025"
MAX_FIXTURES_PER_LEAGUE = int(os.getenv("MAX_FIXTURES_PER_LEAGUE", "400"))  # limite segurança
OUT_FILE = Path("data/train/poisson_inputs.csv")

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

FALLBACK_LEAGUES = [
    # Top-5 + outras ligas do teu backend + UEFA (ids mais comuns na API-Football)
    39, 40, 61, 62, 78, 79, 88, 94, 95, 135, 136, 140, 141, 179,
    197, 203, 207, 218, 307, 71, 119,
    2, 3, 848  # UCL, UEL, UECL (ids típicos)
]

def _ensure_headers():
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_KEY não definido nos secrets/variáveis de ambiente.")

def _seasons() -> List[int]:
    out: List[int] = []
    for p in SEASONS_ENV.split(","):
        p = p.strip()
        if not p:
            continue
        try:
            out.append(int(p))
        except ValueError:
            pass
    return sorted(set(out))

def _load_league_ids_from_config() -> List[int]:
    cfg = Path("config")
    ids: List[int] = []
    if not cfg.exists():
        return ids
    for f in cfg.glob("leagues_*.json"):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        arr: Iterable[Any]
        if isinstance(obj, list):
            arr = obj
        elif isinstance(obj, dict):
            # tenta "leagues", "items", "data"
            for k in ("leagues", "items", "data"):
                if isinstance(obj.get(k), list):
                    arr = obj[k]
                    break
            else:
                arr = []
        else:
            arr = []

        for x in arr:
            if isinstance(x, dict):
                lid = x.get("id") or x.get("league_id") or x.get("code")
                try:
                    if lid is not None:
                        ids.append(int(str(lid)))
                except Exception:
                    pass
    return sorted(set(ids))

def _league_ids() -> List[int]:
    # 1) config/*
    ids = _load_league_ids_from_config()
    if ids:
        return ids
    # 2) env: API_FOOTBALL_LEAGUES="39,61,78"
    env_ids = os.getenv("API_FOOTBALL_LEAGUES", "").strip()
    if env_ids:
        out = []
        for t in env_ids.split(","):
            t = t.strip()
            if not t:
                continue
            try:
                out.append(int(t))
            except ValueError:
                pass
        if out:
            return sorted(set(out))
    # 3) fallback
    return FALLBACK_LEAGUES

def _api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = BASE_URL + path.lstrip("/")
    # retries com backoff para 429/5xx
    for attempt in range(6):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=25)
            if r.status_code == 429:
                wait = 2 * (attempt + 1)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt >= 5:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}

def _fetch_fixtures_finished(league_id: int, season: int, limit: int) -> List[Dict[str, Any]]:
    """
    Busca jogos terminados (status=FT) para uma liga/época, paginando.
    Corta quando atinge 'limit' para não estourar pedidos.
    """
    res: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = _api_get("fixtures", {
            "league": league_id,
            "season": season,
            "status": "FT",
            "page": page
        })
        batch = data.get("response") or []
        res.extend(batch)
        paging = data.get("paging") or {}
        cur = int(paging.get("current") or page)
        total = int(paging.get("total") or cur)
        if limit and len(res) >= limit:
            res = res[:limit]
            break
        if cur >= total or not batch:
            break
        page += 1
        # pequena espera para ser simpático com a API
        time.sleep(0.2)
    return res

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _compute_poisson_marginals(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calcula λ_home/λ_away jogo-a-jogo (sem leak) com forças ataque/defesa por equipa + médias de liga.
    """
    # ordenar cronologicamente
    def _row_key(f):
        # usar timestamp se existir; senão a data ISO
        ts = ((f.get("fixture") or {}).get("timestamp"))
        if ts:
            return int(ts)
        ds = ((f.get("fixture") or {}).get("date")) or ""
        try:
            return int(pd.Timestamp(ds).timestamp())
        except Exception:
            return 0

    fixtures = sorted(fixtures, key=_row_key)

    # estado por equipa
    teams: Dict[int, Dict[str, float]] = {}
    # estado de liga
    lg_matches = 0
    lg_home_goals = 0.0
    lg_away_goals = 0.0

    out_rows: List[Dict[str, Any]] = []

    # priors (ligeiros, para estabilizar início de época)
    PRIOR_MATCHES_LEAGUE = 20
    PRIOR_HOME_GOALS = 1.55
    PRIOR_AWAY_GOALS = 1.35
    PRIOR_MATCHES_TEAM = 5
    HOME_ADV = 1.05  # home advantage multiplicativo

    for f in fixtures:
        fix = f.get("fixture") or {}
        league = f.get("league") or {}
        teams_block = f.get("teams") or {}
        goals = f.get("goals") or {}

        home = (teams_block.get("home") or {})
        away = (teams_block.get("away") or {})
        gh = goals.get("home")
        ga = goals.get("away")

        # sanity
        if gh is None or ga is None:
            continue
        try:
            hid = int(home.get("id"))
            aid = int(away.get("id"))
        except Exception:
            continue

        # médias da liga com prior
        lg_home_avg = (lg_home_goals + PRIOR_MATCHES_LEAGUE * PRIOR_HOME_GOALS) / (lg_matches + PRIOR_MATCHES_LEAGUE or 1)
        lg_away_avg = (lg_away_goals + PRIOR_MATCHES_LEAGUE * PRIOR_AWAY_GOALS) / (lg_matches + PRIOR_MATCHES_LEAGUE or 1)

        # estado por equipa
        if hid not in teams:
            teams[hid] = dict(hp=0, hs=0.0, hc=0.0, ap=0, as_=0.0, ac=0.0)  # home played/scored/conceded; away played/scored/conceded
        if aid not in teams:
            teams[aid] = dict(hp=0, hs=0.0, hc=0.0, ap=0, as_=0.0, ac=0.0)

        th = teams[hid]
        ta = teams[aid]

        # forças com priors (tipo Dixon-Coles light)
        # ataque/defesa em casa
        h_att = ((th["hs"] + PRIOR_MATCHES_TEAM * lg_home_avg) / (th["hp"] + PRIOR_MATCHES_TEAM or 1)) / (lg_home_avg or 1e-6)
        h_def = ((th["hc"] + PRIOR_MATCHES_TEAM * lg_away_avg) / (th["hp"] + PRIOR_MATCHES_TEAM or 1)) / (lg_away_avg or 1e-6)

        # ataque/defesa fora
        a_att = ((ta["as_"] + PRIOR_MATCHES_TEAM * lg_away_avg) / (ta["ap"] + PRIOR_MATCHES_TEAM or 1)) / (lg_away_avg or 1e-6)
        a_def = ((ta["ac"] + PRIOR_MATCHES_TEAM * lg_home_avg) / (ta["ap"] + PRIOR_MATCHES_TEAM or 1)) / (lg_home_avg or 1e-6)

        lam_home = _clamp(lg_home_avg * h_att * a_def * HOME_ADV, 0.05, 6.0)
        lam_away = _clamp(lg_away_avg * a_att * h_def,            0.05, 6.0)

        out_rows.append({
            "league_id": int(league.get("id") or 0),
            "season": int(league.get("season") or 0),
            "fixture_id": int(fix.get("id") or 0),
            "date": (fix.get("date") or "")[:19],
            "home_id": hid, "away_id": aid,
            "goals_home": int(gh), "goals_away": int(ga),
            "lambda_home": round(float(lam_home), 4),
            "lambda_away": round(float(lam_away), 4),
        })

        # atualizar estados (só depois de calcular λ — evita leak)
        lg_matches += 1
        lg_home_goals += float(gh)
        lg_away_goals += float(ga)

        th["hp"] += 1
        th["hs"] += float(gh)
        th["hc"] += float(ga)

        ta["ap"] += 1
        ta["as_"] += float(ga)
        ta["ac"] += float(gh)

    return out_rows

def main():
    _ensure_headers()
    seasons = _seasons()
    leagues = _league_ids()
    if not seasons or not leagues:
        raise RuntimeError("Sem seasons ou leagues para exportar.")

    all_rows: List[Dict[str, Any]] = []
    for s in seasons:
        for lg in leagues:
            print(f"[export] liga={lg} season={s} …")
            try:
                fx = _fetch_fixtures_finished(lg, s, limit=MAX_FIXTURES_PER_LEAGUE)
                if not fx:
                    print(f"  • sem jogos terminados")
                    continue
                rows = _compute_poisson_marginals(fx)
                all_rows.extend(rows)
                print(f"  • {len(rows)} linhas")
            except Exception as e:
                print(f"  ! falhou liga={lg} season={s}: {e}")
            # pausa curta para não abusar
            time.sleep(0.25)

    if not all_rows:
        print("[export] nada a gravar — sem linhas.")
        return

    df = pd.DataFrame(all_rows, columns=[
        "league_id","season","fixture_id","date","home_id","away_id",
        "goals_home","goals_away","lambda_home","lambda_away"
    ])
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_FILE, index=False, encoding="utf-8")
    print(f"[export] gravado: {OUT_FILE} ({len(df)} linhas)")

if __name__ == "__main__":
    main()
