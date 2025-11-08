# Cria data/train/poisson_inputs.csv a partir da API-Football (robusto)
import os, json, time, argparse
from pathlib import Path
from typing import List, Dict, Any
import requests
import pandas as pd

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE = (os.getenv("API_FOOTBALL_BASE") or "https://v3.football.api-sports.io/").rstrip("/")
HEADERS = {"x-apisports-key": API_KEY}

DEFAULT_LEAGUES: List[Dict[str, Any]] = [
    {"id": 39,  "name": "Premier League",              "country": "England"},
    {"id": 140, "name": "La Liga",                     "country": "Spain"},
    {"id": 135, "name": "Serie A",                     "country": "Italy"},
    {"id": 78,  "name": "Bundesliga",                  "country": "Germany"},
    {"id": 61,  "name": "Ligue 1",                     "country": "France"},
    {"id": 88,  "name": "Eredivisie",                  "country": "Netherlands"},
    {"id": 94,  "name": "Primeira Liga",               "country": "Portugal"},
    {"id": 2,   "name": "UEFA Champions League",       "country": "Europe"},
    {"id": 3,   "name": "UEFA Europa League",          "country": "Europe"},
    {"id": 848, "name": "UEFA Europa Conference League","country": "Europe"},
]

def _req(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE}/{path.lstrip('/')}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def _moving_lambda(s: pd.Series, window: int = 20) -> pd.Series:
    return s.rolling(window=window, min_periods=max(5, window // 2)).mean().fillna(s.expanding().mean())

def _load_curated_leagues() -> List[Dict[str, Any]]:
    cfg_dir = Path("config")
    arr: List[Dict[str, Any]] = []
    if cfg_dir.exists():
        for p in cfg_dir.glob("leagues_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items = data.get("leagues") or data.get("items") or data
                for x in (items or []):
                    lid = x.get("id") or x.get("league_id")
                    if lid is None:
                        continue
                    arr.append({
                        "id": int(lid),
                        "name": (x.get("name") or x.get("league") or "").strip() or str(lid),
                        "country": x.get("country"),
                    })
            except Exception:
                continue
    if arr:
        return arr
    # fallback interno
    return DEFAULT_LEAGUES

def _parse_seasons(seasons_arg: List[str]) -> List[int]:
    flat: List[int] = []
    for item in seasons_arg:
        for tok in str(item).split(","):
            tok = tok.strip()
            if tok:
                flat.append(int(tok))
    return sorted(set(flat))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", "-s", action="append", required=True,
                    help="Pode repetir ou usar vírgulas: -s 2024 -s 2025 ou -s 2024,2025")
    ap.add_argument("--out", default="data/train/poisson_inputs.csv")
    args = ap.parse_args()

    if not API_KEY:
        raise SystemExit("Falta API_FOOTBALL_KEY (secret).")

    seasons = _parse_seasons(args.season)
    leagues = _load_curated_leagues()
    if not leagues:
        raise SystemExit("Sem ligas (mesmo após fallback interno).")

    print(f"[export] seasons={seasons} | ligas={len(leagues)} | base={BASE}")

    rows = []
    for lg in leagues:
        lid = int(lg["id"])
        for season in seasons:
            try:
                data = _req("fixtures", {"league": lid, "season": season})
            except Exception as e:
                print(f"[warn] liga {lid} season {season}: {e}")
                continue
            # respeitar rate limit da API-Football
            time.sleep(0.55)
            for f in (data.get("response") or []):
                sc = f.get("score", {}) or {}
                ft = sc.get("fulltime") or {}
                gh, ga = ft.get("home"), ft.get("away")
                if gh is None or ga is None:
                    continue
                rows.append({
                    "league_id": lid,
                    "season": season,
                    "date": (f.get("fixture", {}) or {}).get("date"),
                    "goals_home": int(gh),
                    "goals_away": int(ga),
                    "home_id": (f.get("teams", {}) or {}).get("home", {}).get("id"),
                    "away_id": (f.get("teams", {}) or {}).get("away", {}).get("id"),
                })

    if not rows:
        raise SystemExit("Sem jogos com resultado devolvidos pela API para as ligas/épocas pedidas.")

    df = pd.DataFrame(rows).sort_values("date")
    df["lambda_home"] = _moving_lambda(df["goals_home"])
    df["lambda_away"] = _moving_lambda(df["goals_away"])

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    df[["league_id", "goals_home", "goals_away", "lambda_home", "lambda_away"]].to_csv(outp, index=False)
    print(f"[ok] gravado: {outp} (linhas={len(df)})")

if __name__ == "__main__":
    main()
