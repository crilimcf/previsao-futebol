# -*- coding: utf-8 -*-
"""
Exporta data/train/poisson_inputs.csv a partir da API-Football, com retries.
Cada linha: league_id,goals_home,goals_away,lambda_home,lambda_away

- Ligas: tenta ler de config/leagues_*.json; se não houver, usa fallback.
- λ_home/λ_away: médias por liga/época (robusto e suficiente para estimar λ3).
"""

import os, json, time, csv, glob
from pathlib import Path
from typing import Dict, List, Tuple
import requests

API_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
API_KEY  = os.getenv("API_FOOTBALL_KEY", "")
HEADERS  = {"x-apisports-key": API_KEY} if API_KEY else {}

OUT_DIR  = Path("data/train")
OUT_CSV  = OUT_DIR / "poisson_inputs.csv"

def read_curated_leagues() -> List[str]:
    ids: List[str] = []
    for path in glob.glob("config/leagues_*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            arr = data if isinstance(data, list) else data.get("leagues") or data.get("items") or []
            for x in arr:
                lid = str(x.get("id") or x.get("league_id") or "").strip()
                if lid and lid not in ids:
                    ids.append(lid)
        except Exception:
            pass
    # fallback sensato (principais ligas)
    if not ids:
        ids = ["39","61","78","135","88","94","140","62","136","179","197","94","203"]
    return ids

def req_json(url: str, params: Dict, retries=5, backoff=2.0) -> Dict:
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            # 429/5xx -> backoff
            if r.status_code in (429,500,502,503,504):
                time.sleep(backoff * (i+1))
            else:
                last = f"{r.status_code} {r.text[:200]}"
                time.sleep(0.5)
        except Exception as e:
            last = str(e)
            time.sleep(backoff * (i+1))
    return {"error": last or "unknown"}

def fetch_fixtures(league_id: str, season: str, limit_last=150) -> List[Dict]:
    url = API_BASE.rstrip("/") + "/fixtures"
    # estratégia simples: jogos terminados (FT), últimos N
    params = {"league": league_id, "season": season, "status": "FT", "last": limit_last}
    data = req_json(url, params)
    if "response" in data and isinstance(data["response"], list):
        return data["response"]
    return []

def league_means(fixtures: List[Dict]) -> Tuple[float,float]:
    if not fixtures:
        return (1.2, 1.2)  # defaults modestos
    h = [int(x.get("goals",{}).get("home",0)) for x in fixtures]
    a = [int(x.get("goals",{}).get("away",0)) for x in fixtures]
    # evitar zero absoluto
    hmu = max(0.3, sum(h)/max(1,len(h)))
    amu = max(0.3, sum(a)/max(1,len(a)))
    return (round(hmu,4), round(amu,4))

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    leagues = read_curated_leagues()
    seasons = os.getenv("SEASONS","2024,2025").split(",")
    seasons = [s.strip() for s in seasons if s.strip()]

    rows: List[List] = []
    for lg in leagues:
        all_fx: List[Dict] = []
        for s in seasons:
            fx = fetch_fixtures(lg, s, limit_last=200)
            all_fx.extend(fx)
        # filtra só com goals válidos
        all_fx = [x for x in all_fx if isinstance(x.get("goals",{}).get("home",None), int)
                                   and isinstance(x.get("goals",{}).get("away",None), int)]
        lam_h, lam_a = league_means(all_fx)
        # escreve cada fixture como uma linha (λ iguais por liga/época — suficiente para λ3)
        for f in all_fx:
            gh = int(f["goals"]["home"])
            ga = int(f["goals"]["away"])
            rows.append([lg, gh, ga, lam_h, lam_a])

    # Escrever SEM FALHAR: se não há dados, cria ficheiro só com cabeçalho
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["league_id","goals_home","goals_away","lambda_home","lambda_away"])
        w.writerows(rows)

    print(f"CSV gerado: {OUT_CSV} ({len(rows)} linhas)")

if __name__ == "__main__":
    main()
