# src/fetch_matches.py
import os
import json
import math
import random
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from src import config

logger = logging.getLogger("football_api")

# =========================
# ENV & CONSTANTES
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = (os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# Preferência de bookies ao ler odds reais
PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

# Limites
REQUEST_TIMEOUT = 8
MAX_GOALS = 6            # Poisson 0..6
DAYS_AHEAD  = 5          # hoje + 4 dias


# =========================
# Redis helper (via config)
# =========================
redis = config.redis_client

def _rget(key: str) -> Optional[str]:
    try:
        return redis.get(key) if redis else None
    except Exception:
        return None

def _rset(key: str, value: str, ex: Optional[int] = 3600):
    try:
        if redis:
            redis.set(key, value, ex=ex)
    except Exception:
        pass


# =========================
# HTTP + CACHE
# =========================
def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    p = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return f"cache:{url}:{p}"

def _get_api(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    GET à API-Football com cache Redis.
    Devolve o campo "response" quando existir; senão o JSON bruto.
    """
    if not API_KEY:
        logger.error("❌ API_FOOTBALL_KEY não definida.")
        return []

    url = BASE_URL + endpoint.lstrip("/")
    key = _cache_key(url, params)

    cached = _rget(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        r = requests.get(url, headers=HEADERS, params=params or {}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            data = body.get("response", body)
            _rset(key, json.dumps(data), ex=1800)  # 30min
            return data
        logger.warning(f"⚠️ API {endpoint} -> HTTP {r.status_code}: {r.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"❌ API {endpoint} erro: {e}")
        return []


# =========================
# CARREGAR LIGAS
# =========================
def _load_target_league_ids() -> List[int]:
    """
    Se existir config/leagues.json usa-o (lista branca).
    Caso contrário, devolve lista vazia -> SEM FILTRO (apanha TODAS as ligas).
    """
    path = "config/leagues.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                leagues = json.load(f)
            ids = [int(l["id"]) for l in leagues if "id" in l]
            if ids:
                return ids
        except Exception as e:
            logger.warning(f"⚠️ leagues.json inválido: {e}")
    # Sem config -> sem filtro
    return []


# =========================
# FIXTURES + ODDS + STATS
# =========================
def _fixtures_by_date(yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    return _get_api("fixtures", {"date": yyyy_mm_dd, "season": SEASON}) or []

def _team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    """teams/statistics (cache 6h)."""
    url = BASE_URL + "teams/statistics"
    params = {"team": team_id, "league": league_id, "season": SEASON}
    ck = _cache_key(url, params)
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    data = _get_api("teams/statistics", params) or {}
    if isinstance(data, list) and data:
        data = data[0]
    _rset(ck, json.dumps(data), ex=6 * 3600)
    return data or {}


def _odds_by_fixture(fixture_id: int) -> Dict[str, Any]:
    """
    Lê odds reais (se existirem) e agrega:
      - 1x2 -> {home, draw, away}
      - double_chance -> {"1X","12","X2"}
      - over_under -> {"2.5": {over,under}, "1.5": {over,under}, ...}
      - btts -> {yes,no}
    """
    raw = _get_api("odds", {"fixture": fixture_id}) or []
    if not raw:
        return {}

    best_bm = None
    try:
        for row in raw:
            bms = row.get("bookmakers") or []
            pref = [b for b in bms if (b.get("name") or "") in PREFERRED_BOOKMAKERS]
            candidates = pref or bms
            if candidates:
                best_bm = candidates[0]
                break
    except Exception:
        pass

    if not best_bm:
        return {}

    out = {"1x2": {}, "double_chance": {}, "over_under": {}, "btts": {}}

    def _push_ou(value: str, odd: str):
        # value: "Over 2.5" | "Under 2.5"
        try:
            parts = value.split()
            if len(parts) >= 2 and parts[0] in {"Over", "Under"}:
                line = parts[1]  # "2.5"
                d = out["over_under"].setdefault(line, {})
                d[parts[0].lower()] = float(odd)
        except Exception:
            pass

    for bet in best_bm.get("bets") or []:
        name = (bet.get("name") or "").lower()
        values = bet.get("values") or []

        if "match winner" in name or name in {"winner", "1x2"}:
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                if val in {"home", "1"}:
                    out["1x2"]["home"] = odd
                elif val in {"draw", "x"}:
                    out["1x2"]["draw"] = odd
                elif val in {"away", "2"}:
                    out["1x2"]["away"] = odd

        elif "double chance" in name:
            for v in values:
                key = (v.get("value") or "").replace(" ", "")  # "1X","X2","12"
                try:
                    out["double_chance"][key] = float(v.get("odd"))
                except Exception:
                    continue

        elif "over/under" in name:
            for v in values:
                _push_ou(v.get("value") or "", v.get("odd") or "")

        elif "both teams to score" in name or "btts" in name:
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                if val in {"yes"}:
                    out["btts"]["yes"] = odd
                elif val in {"no"}:
                    out["btts"]["no"] = odd

    return out


def _top_scorers(league_id: int) -> List[Dict[str, Any]]:
    """players/topscorers (cache 12h)."""
    ck = f"cache:topscorers:{league_id}:{SEASON}"
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    data = _get_api("players/topscorers", {"league": league_id, "season": SEASON}) or []
    res: List[Dict[str, Any]] = []
    try:
        for s in data[:5]:
            player = (s.get("player") or {}).get("name")
            stat0 = (s.get("statistics") or [{}])[0]
            team = (stat0.get("team") or {}).get("name")
            goals = ((stat0.get("goals") or {}).get("total")) or 0
            res.append(
                {
                    "player": player,
                    "team": team,
                    "goals": int(goals or 0),
                    # prob heurística só para ranking visual
                    "probability": round(0.40 + (goals or 0) * 0.05 + random.uniform(0.03, 0.08), 2),
                }
            )
    except Exception:
        pass

    _rset(ck, json.dumps(res), ex=12 * 3600)
    return res


# =========================
# POISSON + probabilidades
# =========================
def _poisson_pmf(lmbda: float, k: int) -> float:
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)
    except OverflowError:
        return 0.0

def _poisson_matrix(lh: float, la: float, max_goals: int = MAX_GOALS) -> List[List[float]]:
    mat = []
    for i in range(max_goals + 1):
        row = []
        ph = _poisson_pmf(lh, i)
        for j in range(max_goals + 1):
            pa = _poisson_pmf(la, j)
            row.append(ph * pa)
        mat.append(row)
    s = sum(sum(r) for r in mat)
    if s > 0:
        mat = [[x / s for x in r] for r in mat]
    return mat

def _params_from_stats(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    """Estimativa simples e robusta de λ a partir de médias for/against casa/fora."""
    def _flt(v, dv=1.1):
        try:
            if v is None:
                return dv
            return float(str(v).replace(",", "."))
        except Exception:
            return dv

    gh_home = _flt(((stats_home.get("goals") or {}).get("for")     or {}).get("average", {}).get("home"), 1.2)
    ga_home = _flt(((stats_home.get("goals") or {}).get("against") or {}).get("average", {}).get("home"), 1.0)
    gh_away = _flt(((stats_away.get("goals") or {}).get("for")     or {}).get("average", {}).get("away"), 1.1)
    ga_away = _flt(((stats_away.get("goals") or {}).get("against") or {}).get("average", {}).get("away"), 1.0)

    lam_h = max(0.2, min(3.5, 0.6 * gh_home + 0.4 * ga_away))
    lam_a = max(0.2, min(3.5, 0.6 * gh_away + 0.4 * ga_home))
    return lam_h, lam_a

def _probs_from_matrix(mat: List[List[float]]) -> Dict[str, Any]:
    n = len(mat)
    p_home = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(mat[i][i] for i in range(n))
    p_away = 1.0 - p_home - p_draw

    def _psum(cond) -> float:
        return sum(mat[i][j] for i in range(n) for j in range(n) if cond(i, j))

    p_over15 = _psum(lambda i, j: (i + j) >= 2)
    p_over25 = _psum(lambda i, j: (i + j) >= 3)
    p_btts   = _psum(lambda i, j: (i >= 1 and j >= 1))

    p_1x = p_home + p_draw
    p_12 = p_home + p_away
    p_x2 = p_draw + p_away

    flat = [((i, j), mat[i][j]) for i in range(n) for j in range(n)]
    flat.sort(key=lambda x: x[1], reverse=True)
    top3 = [{"score": f"{a}-{b}", "prob": round(float(p), 4)} for (a, b), p in flat[:3]]

    return {
        "winner": {"home": float(p_home), "draw": float(p_draw), "away": float(p_away)},
        "over_1_5": float(p_over15),
        "over_2_5": float(p_over25),
        "btts": float(p_btts),
        "double_chance": {"1X": float(p_1x), "12": float(p_12), "X2": float(p_x2)},
        "correct_score_top3": top3,
    }


# =========================
# Helpers odds
# =========================
def _clamp_prob(p: float, eps: float = 1e-6) -> float:
    return max(eps, min(1.0 - eps, p))

def _implied_odds(p: float) -> float:
    p = _clamp_prob(p)
    return round(1.0 / p, 2)

def _merge_odds_from_probs_and_bookmaker(
    probs: Dict[str, Any], real: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Formato final esperado pelo frontend.
    Preferimos odds reais quando presentes; fallback = odds lineadas via Poisson.
    """
    # 1X2
    odds_winner = {
        "home": _implied_odds(probs["winner"]["home"]),
        "draw": _implied_odds(probs["winner"]["draw"]),
        "away": _implied_odds(probs["winner"]["away"]),
    }
    if real.get("1x2"):
        odds_winner.update({k: float(v) for k, v in real["1x2"].items() if k in {"home", "draw", "away"}})

    # O/U 2.5
    p_over25 = float(probs["over_2_5"])
    odds_over25 = {"over": _implied_odds(p_over25), "under": _implied_odds(1.0 - p_over25)}
    if real.get("over_under") and real["over_under"].get("2.5"):
        ou = real["over_under"]["2.5"]
        odds_over25.update({k: float(v) for k, v in ou.items() if k in {"over", "under"}})

    # O/U 1.5
    p_over15 = float(probs["over_1_5"])
    odds_over15 = {"over": _implied_odds(p_over15), "under": _implied_odds(1.0 - p_over15)}
    if real.get("over_under") and real["over_under"].get("1.5"):
        ou = real["over_under"]["1.5"]
        odds_over15.update({k: float(v) for k, v in ou.items() if k in {"over", "under"}})

    # BTTS
    p_btts = float(probs["btts"])
    odds_btts = {"yes": _implied_odds(p_btts), "no": _implied_odds(1.0 - p_btts)}
    if real.get("btts"):
        odds_btts.update({k: float(v) for k, v in real["btts"].items() if k in {"yes", "no"}})

    return {
        "winner": odds_winner,
        "over_2_5": odds_over25,
        "over_1_5": odds_over15,
        "btts": odds_btts,
    }


# =========================
# BUILD REGISTO FINAL
# =========================
def _winner_class_from_probs(pw: Dict[str, float]) -> Tuple[int, float]:
    # 0=home, 1=draw, 2=away
    options = [(0, pw["home"]), (1, pw["draw"]), (2, pw["away"])]
    cls, conf = max(options, key=lambda t: t[1])
    return cls, float(conf)

def _dc_class_from_probs(pdc: Dict[str, float]) -> Tuple[int, float]:
    # 0=1X, 1=12, 2=X2
    options = [(0, pdc["1X"]), (1, pdc["12"]), (2, pdc["X2"])]
    cls, conf = max(options, key=lambda t: t[1])
    return cls, float(conf)

def _predicted_score_from_top(top3: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    if not top3:
        return {"home": None, "away": None}
    s = top3[0]["score"]
    try:
        h, a = s.split("-")
        return {"home": int(h), "away": int(a)}
    except Exception:
        return {"home": None, "away": None}


def _build_match_record(
    fix: Dict[str, Any],
    odds_real: Dict[str, Any],
    probs: Dict[str, Any],
    scorers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    fixture = fix.get("fixture", {})
    league = fix.get("league", {})
    teams = fix.get("teams", {})

    fid = fixture.get("id")
    lg_id = league.get("id")

    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}

    # classes + conf
    w_class, w_conf = _winner_class_from_probs(probs["winner"])
    dc_class, dc_conf = _dc_class_from_probs(probs["double_chance"])

    # correct-score
    top3 = probs["correct_score_top3"]
    pred_score = _predicted_score_from_top(top3)

    # odds finais (real com fallback em modeladas)
    odds_map = _merge_odds_from_probs_and_bookmaker(probs, odds_real)

    iso_dt = fixture.get("date") or ""
    date_ymd = iso_dt[:10] if iso_dt else None

    return {
        "match_id": fid,
        "league_id": lg_id,
        "league_name": league.get("name"),  # útil para /meta/leagues
        "league": league.get("name"),
        "country": league.get("country"),
        "date": iso_dt,
        "date_ymd": date_ymd,
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "home_logo": home.get("logo"),
        "away_logo": away.get("logo"),

        "odds": odds_map,

        # legado
        "predicted_score": pred_score,
        "confidence": round(float(w_conf), 4),

        "predictions": {
            "winner": {"class": w_class, "confidence": round(float(w_conf), 4)},
            "double_chance": {"class": dc_class, "confidence": round(float(dc_conf), 4)},
            "over_2_5": {"class": int(probs["over_2_5"] >= 0.5), "confidence": round(float(probs["over_2_5"]), 4)},
            "over_1_5": {"class": int(probs["over_1_5"] >= 0.5), "confidence": round(float(probs["over_1_5"]), 4)},
            "btts": {"class": int(probs["btts"] >= 0.5), "confidence": round(float(probs["btts"]), 4)},
        },

        "correct_score_top3": top3,
        "top_scorers": scorers,
    }


# =========================
# PIPELINE PRINCIPAL
# =========================
def fetch_today_matches() -> Dict[str, Any]:
    """
    Busca fixtures (hoje + próximos DAYS_AHEAD-1 dias), odds, stats, calcula Poisson,
    e grava em data/predict/predictions.json (UTF-8).
    """
    if not API_KEY:
        msg = "❌ API_FOOTBALL_KEY não definida."
        logger.error(msg)
        return {"status": "error", "detail": "API key missing", "total": 0}

    # Fixtures alvo (sem filtrar por liga, exceto se leagues.json existir)
    target_leagues = set(_load_target_league_ids())
    fixtures_all: List[Dict[str, Any]] = []

    for d in range(DAYS_AHEAD):
        yyyy_mm_dd = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        day_fixtures = _fixtures_by_date(yyyy_mm_dd) or []
        for f in day_fixtures:
            lg = f.get("league") or {}
            if not lg.get("id"):
                continue
            # Só filtra se houver whitelist
            if target_leagues and int(lg["id"]) not in target_leagues:
                continue
            fixtures_all.append(f)

    # Pré-carrega top scorers por liga
    league_ids = sorted(list({(f.get("league") or {}).get("id") for f in fixtures_all if (f.get("league") or {}).get("id")}))
    scorers_by_league = {int(lid): _top_scorers(int(lid)) for lid in league_ids if lid}

    out: List[Dict[str, Any]] = []

    for f in fixtures_all:
        fixture = f.get("fixture") or {}
        league  = f.get("league") or {}
        teams   = f.get("teams") or {}
        fid = fixture.get("id")
        lg_id = league.get("id")
        if not fid or not lg_id:
            continue

        home_id = (teams.get("home") or {}).get("id")
        away_id = (teams.get("away") or {}).get("id")
        if not home_id or not away_id:
            continue

        # Odds reais (com fallback para model)
        odds_real = _odds_by_fixture(int(fid)) or {}

        # Stats -> lambdas Poisson
        st_h = _team_stats(int(home_id), int(lg_id))
        st_a = _team_stats(int(away_id), int(lg_id))
        lam_h, lam_a = _params_from_stats(st_h, st_a)
        mat = _poisson_matrix(lam_h, lam_a, MAX_GOALS)
        probs = _probs_from_matrix(mat)

        # Scorers por liga
        top_scorers = scorers_by_league.get(int(lg_id), [])

        out.append(_build_match_record(f, odds_real, probs, top_scorers))

    # Escreve ficheiro (UTF-8 normal)
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    try:
        config.update_last_update()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao atualizar Redis: {e}")

    logger.info(f"✅ {len(out)} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": len(out)}


if __name__ == "__main__":
    print(fetch_today_matches())
