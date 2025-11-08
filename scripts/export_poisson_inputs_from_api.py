# ============================================================
# scripts/export_poisson_inputs_from_api.py
# Cria data/train/poisson_inputs.csv a partir da API-Football
# ============================================================
from __future__ import annotations
import os, json, time, argparse
from pathlib import Path
from typing import Dict, Any, List

import requests
import pandas as pd

# -----------------------------
# Config de API
# -----------------------------
def normalize_base(u: str | None) -> str:
    u = (u or "").strip()
    if not u.startswith(("http://", "https://")):
        return "https://v3.football.api-sports.io/"
    return u.rstrip("/") + "/"

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE = normalize_base(os.getenv("API_FOOTBALL_BASE"))
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# -----------------------------
# HTTP com retry simples
# -----------------------------
def req(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not API_KEY:
        raise SystemExit("Falta API_FOOTBALL_KEY no ambiente.")
    url = f"{BASE}{path.lstrip('/')}"
    for i in range(5):
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(1.2 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}  # nunca chega aqui

# -----------------------------
# Ligas curadas (config/leagues_*.json)
# -----------------------------
def list_leagues_curated() -> pd.DataFrame:
    cfg_dir = Path("config")
    arr: List[Dict[str, Any]] = []
    for p in cfg_dir.glob("leagues_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            items = data.get("leagues") or data.get("items") or data
            for x in items:
                lid = x.get("id") or x.get("league_id")
                name = x.get("name") or x.get("league")
                if lid:
                    arr.append({"league_id": int(lid), "name": str(name or "")})
        except Exception:
            continue
    return pd.DataFrame(arr).drop_duplicates(subset=["league_id"])

# -----------------------------
# Fixtures por época com paginação
# -----------------------------
def fetch_fixtures_league_season(league_id: int, season: int) -> List[Dict[str, Any]]:
    page = 1
    out: List[Dict[str, Any]] = []
    while True:
        data = req("fixtures", {"league": league_id, "season": season, "page": page})
        resp = data.get("response") or []
        out.extend(resp)
        pag = data.get("paging") or {}
        cur, tot = int(pag.get("current", 1)), int(pag.get("total", 1))
        if cur >= tot:
            break
        page += 1
        time.sleep(0.45)
    return out

# -----------------------------
# Rolling helpers
# -----------------------------
def compute_team_marginals(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    # Sort por data para garantir histórico
    df = df.sort_values("date").copy()

    # λ_home: média móvel dos golos em casa por equipa (home_id), usando apenas jogos anteriores (shift)
    gh = df.groupby(["league_id", "home_id"], group_keys=False)["goals_home"]
    lam_h_roll = gh.apply(lambda s: s.shift().rolling(window=window, min_periods=max(5, window // 2)).mean())
    lam_h_exp  = gh.apply(lambda s: s.shift().expanding().mean())
    df["lambda_home"] = lam_h_roll.fillna(lam_h_exp)

    # λ_away: média móvel dos golos fora por equipa (away_id), usando apenas jogos anteriores (shift)
    ga = df.groupby(["league_id", "away_id"], group_keys=False)["goals_away"]
    lam_a_roll = ga.apply(lambda s: s.shift().rolling(window=window, min_periods=max(5, window // 2)).mean())
    lam_a_exp  = ga.apply(lambda s: s.shift().expanding().mean())
    df["lambda_away"] = lam_a_roll.fillna(lam_a_exp)

    # Fallbacks por liga quando ainda não há histórico
    league_home_mean = df.groupby("league_id")["goals_home"].transform("mean")
    league_away_mean = df.groupby("league_id")["goals_away"].transform("mean")
    df["lambda_home"] = df["lambda_home"].fillna(league_home_mean).clip(lower=0.05)
    df["lambda_away"] = df["lambda_away"].fillna(league_away_mean).clip(lower=0.05)
    return df

# -----------------------------
# Parse seasons do CLI/ENV
# -----------------------------
def parse_seasons(cli_values: List[str] | None) -> List[int]:
    # CLI pode ter múltiplos --season e/ou "2024,2025"
    vals: List[str] = []
    for v in (cli_values or []):
        vals.extend(str(v).split(","))
    if not vals:
        env = (os.getenv("API_FOOTBALL_SEASONS")
               or os.getenv("API_FOOTBALL_SEASON")
               or os.getenv("SEASONS")
               or os.getenv("SEASON")
               or "2024")
        vals = [x.strip() for x in env.split(",") if x.strip()]
    seasons: List[int] = []
    for v in vals:
        try:
            seasons.append(int(v))
        except ValueError:
            pass
    return sorted(set(seasons))

# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser("export: poisson_inputs_from_api.py")
    ap.add_argument("--season", action="append",
                    help="Época(s) ex: --season 2024 --season 2025 ou '2024,2025'. "
                         "Se omitir, usa ENV: API_FOOTBALL_SEASONS/SEASON (default 2024).")
    ap.add_argument("--out", default="data/train/poisson_inputs.csv",
                    help="Caminho do CSV de saída.")
    args = ap.parse_args()

    seasons = parse_seasons(args.season)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    leagues = list_leagues_curated()
    if leagues.empty:
        raise SystemExit("Sem ligas curadas em config/leagues_*.json")

    rows: List[Dict[str, Any]] = []
    for _, row in leagues.iterrows():
        lid = int(row["league_id"])
        for season in seasons:
            fixtures = fetch_fixtures_league_season(lid, season)
            time.sleep(0.2)
            for f in fixtures:
                sc = f.get("score", {}) or {}
                ft = (sc.get("fulltime") or {})
                gh, ga = ft.get("home"), ft.get("away")
                if gh is None or ga is None:
                    continue
                teams = f.get("teams", {}) or {}
                home = (teams.get("home") or {})
                away = (teams.get("away") or {})
                rows.append({
                    "league_id": lid,
                    "season": season,
                    "date": (f.get("fixture") or {}).get("date"),
                    "goals_home": int(gh),
                    "goals_away": int(ga),
                    "home_id": home.get("id"),
                    "away_id": away.get("id"),
                })

    if not rows:
        raise SystemExit("Sem dados de fixtures com resultado.")

    df = pd.DataFrame(rows)
    # Normaliza data para ordenação
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df = df.dropna(subset=["date", "goals_home", "goals_away", "home_id", "away_id"])

    # λ marginais por equipa (histórico)
    df = compute_team_marginals(df, window=20)

    # CSV final: colunas esperadas pelo treino de λ3
    df_out = df[["league_id", "goals_home", "goals_away", "lambda_home", "lambda_away"]].copy()
    df_out.to_csv(outp, index=False)
    print(f"[ok] gravado: {outp} (linhas={len(df_out)})")

if __name__ == "__main__":
    main()
