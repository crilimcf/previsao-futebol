# scripts/export_poisson_inputs_from_api.py
# Cria data/train/poisson_inputs.csv a partir da API-Football (paginação + fallback)

import os, json, time, math, argparse
from pathlib import Path
from typing import List, Dict, Any
import requests
import pandas as pd

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE = (os.getenv("API_FOOTBALL_BASE") or "https://v3.football.api-sports.io/").rstrip("/")
HEADERS = {"x-apisports-key": API_KEY}

OUT = Path("data/train/poisson_inputs.csv")

# Fallback interno se não houver ficheiros em config/
BUILTIN_LEAGUES = [
    {"id": 39,  "name": "Premier League"},
    {"id": 140, "name": "La Liga"},
    {"id": 135, "name": "Serie A"},
    {"id": 78,  "name": "Bundesliga"},
    {"id": 61,  "name": "Ligue 1"},
    {"id": 94,  "name": "Primeira Liga"},
    {"id": 88,  "name": "Eredivisie"},
    {"id": 2,   "name": "UEFA Champions League"},
    {"id": 3,   "name": "UEFA Europa League"},
    {"id": 848, "name": "Saudi Pro League"},
]

def req(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE}/{path.lstrip('/')}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json() or {}

def list_leagues_curated() -> pd.DataFrame:
    cfg_dir = Path("config")
    arr: List[Dict[str, Any]] = []
    if cfg_dir.exists():
        for p in cfg_dir.glob("leagues_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items = data.get("leagues") or data.get("items") or data
                for x in items or []:
                    if "id" in x:
                        arr.append({"league_id": int(x["id"]), "name": x.get("name", "")})
            except Exception:
                continue
    if not arr:
        # fallback interno
        for x in BUILTIN_LEAGUES:
            arr.append({"league_id": int(x["id"]), "name": x.get("name", "")})
    return pd.DataFrame(arr).drop_duplicates(subset=["league_id"])

def parse_seasons(raw: List[str]) -> List[int]:
    """Aceita --season repetido, vírgulas, ponto-e-vírgula e/ou espaços."""
    out: List[int] = []
    for item in raw:
        tokens = (
            str(item)
            .replace(";", " ")
            .replace(",", " ")
            .split()
        )
        for token in tokens:
            try:
                out.append(int(token))
            except Exception:
                pass
    return sorted(set(out))

def moving_lambda(s: pd.Series, window=20) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    roll = s.rolling(window=window, min_periods=max(5, window // 2)).mean()
    return roll.fillna(s.expanding().mean()).fillna(s.mean())

def fetch_fixtures_finished(league_id: int, season: int) -> List[Dict[str, Any]]:
    """Puxa TODOS os jogos finalizados para liga/época (com paginação)."""
    page = 1
    rows: List[Dict[str, Any]] = []
    while True:
        payload = {"league": league_id, "season": season, "status": "FT", "page": page}
        data = req("fixtures", payload)
        resp = data.get("response") or []
        rows.extend(resp)
        paging = data.get("paging") or {}
        cur, tot = int(paging.get("current", 1)), int(paging.get("total", 1))
        if cur >= tot:
            break
        page += 1
        time.sleep(0.4)
    return rows

def fetch_fixtures_fallback_range(league_id: int, season: int) -> List[Dict[str, Any]]:
    """Fallback: último ~360 dias em blocos para não estourar paginação."""
    from datetime import datetime, timedelta
    out: List[Dict[str, Any]] = []
    end = datetime.utcnow().date()
    start = end - timedelta(days=360)

    # blocos de ~60 dias
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=60), end)
        page = 1
        while True:
            payload = {"league": league_id, "from": cur.isoformat(), "to": nxt.isoformat(), "status": "FT", "page": page}
            data = req("fixtures", payload)
            resp = data.get("response") or []
            out.extend(resp)
            paging = data.get("paging") or {}
            curp, totp = int(paging.get("current", 1)), int(paging.get("total", 1))
            if curp >= totp:
                break
            page += 1
            time.sleep(0.4)
        cur = nxt
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--season",
        action="append",
        required=True,
        help="Épocas: repetir flag ou usar vírgulas/espaços/ponto-e-vírgula. Ex: --season 2023 --season 2024  OU  --season 2023,2024",
    )
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    # Garante diretório de saída
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        print("[export] Falta API_FOOTBALL_KEY no ambiente — a escrever CSV vazio.")
        pd.DataFrame(columns=["league_id","goals_home","goals_away","lambda_home","lambda_away"]).to_csv(args.out, index=False)
        return

    seasons = parse_seasons(args.season)
    leagues = list_leagues_curated()
    if leagues.empty:
        print("[export] Sem ligas (mesmo após fallback) — CSV vazio.")
        pd.DataFrame(columns=["league_id","goals_home","goals_away","lambda_home","lambda_away"]).to_csv(args.out, index=False)
        return

    print(f"[export] base={BASE} | seasons={seasons} | ligas={len(leagues)}")

    rows: List[Dict[str, Any]] = []
    for _, lg in leagues.iterrows():
        lid = int(lg["league_id"])
        for season in seasons:
            try:
                data = fetch_fixtures_finished(lid, season)
                if not data:
                    data = fetch_fixtures_fallback_range(lid, season)
                for f in data:
                    sc = (f.get("score") or {}).get("fulltime") or {}
                    gh, ga = sc.get("home"), sc.get("away")
                    if gh is None or ga is None:
                        continue
                    rows.append({
                        "league_id": lid,
                        "season": season,
                        "date": (f.get("fixture") or {}).get("date"),
                        "goals_home": int(gh),
                        "goals_away": int(ga),
                    })
            except requests.HTTPError as e:
                # não quebra o job
                print(f"[export] HTTPError liga={lid} season={season}: {e}")
            except Exception as e:
                print(f"[export] erro liga={lid} season={season}: {e}")
            time.sleep(0.3)

    df = pd.DataFrame(rows).sort_values("date")
    if df.empty:
        print("[export] Sem jogos com FT após tentativas — CSV vazio.")
        pd.DataFrame(columns=["league_id","goals_home","goals_away","lambda_home","lambda_away"]).to_csv(args.out, index=False)
        return

    # λ marginais simples (rolling)
    df["lambda_home"] = moving_lambda(df["goals_home"])
    df["lambda_away"] = moving_lambda(df["goals_away"])

    df[["league_id","goals_home","goals_away","lambda_home","lambda_away"]].to_csv(args.out, index=False)
    print(f"[export] gravado: {args.out} ({len(df)} linhas)")

if __name__ == "__main__":
    main()
