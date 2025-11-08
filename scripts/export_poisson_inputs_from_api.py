# scripts/export_poisson_inputs_from_api.py
# Cria data/train/poisson_inputs.csv a partir da API-Football
import os, json, time
from pathlib import Path
import argparse
import requests
import pandas as pd

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io")
HEADERS = {"x-apisports-key": API_KEY}

def req(path, params):
    url = f"{BASE.rstrip('/')}/{path.lstrip('/')}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def list_leagues_curated() -> pd.DataFrame:
    cfg_dir = Path("config")
    arr = []
    for p in cfg_dir.glob("leagues_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            items = data.get("leagues") or data.get("items") or data
            for x in items:
                arr.append({"league_id": int(x.get("id")), "name": x.get("name")})
        except Exception:
            continue
    return pd.DataFrame(arr).drop_duplicates(subset=["league_id"])

def moving_lambda(goals: pd.Series, window=20):
    s = goals.rolling(window=window, min_periods=max(5, window//2)).mean()
    return s.fillna(goals.expanding().mean())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", action="append", type=int, required=True)
    ap.add_argument("--out", type=str, default="data/train/poisson_inputs.csv")
    args = ap.parse_args()

    assert API_KEY, "Falta API_FOOTBALL_KEY"
    leagues = list_leagues_curated()
    if leagues.empty:
        raise SystemExit("Sem ligas em config/leagues_*.json")

    rows = []
    for _, row in leagues.iterrows():
        lid = int(row["league_id"])
        for season in args.season:
            # fixtures com resultados
            data = req("fixtures", {"league": lid, "season": season})
            time.sleep(0.6)
            for f in (data.get("response") or []):
                sc = f.get("score", {})
                ft = (sc.get("fulltime") or {})
                gh, ga = ft.get("home"), ft.get("away")
                if gh is None or ga is None: 
                    continue
                rows.append({
                    "league_id": lid,
                    "season": season,
                    "date": f.get("fixture", {}).get("date"),
                    "goals_home": int(gh),
                    "goals_away": int(ga),
                    "home_id": f.get("teams", {}).get("home", {}).get("id"),
                    "away_id": f.get("teams", {}).get("away", {}).get("id"),
                })

    df = pd.DataFrame(rows).sort_values("date")
    # λ marginais simples por rolling média (poderás trocar pelo que já tens no projeto)
    df["lambda_home"] = moving_lambda(df["goals_home"])
    df["lambda_away"] = moving_lambda(df["goals_away"])

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    df[["league_id","goals_home","goals_away","lambda_home","lambda_away"]].to_csv(outp, index=False)
    print(f"gravado: {outp}")

if __name__ == "__main__":
    main()
