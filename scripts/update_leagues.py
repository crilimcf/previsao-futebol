#!/usr/bin/env python3
import os
import json
import requests
from typing import List, Dict, Any, Set

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = (os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2024")
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# Ligas UEFA a incluir mesmo que country seja "World"
EXTRA_LEAGUES: Set[str] = {
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Europa Conference League",



}

def fetch_json(endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = BASE_URL + endpoint.lstrip("/")
    r = requests.get(url, headers=HEADERS, params=params or {}, timeout=25)
    r.raise_for_status()
    return r.json()

def get_target_countries() -> Set[str]:
    """
    Constrói o conjunto de países-alvo:
      - Todos os países com continent == 'Europe'
      - + Brasil
      - + Arábia Saudita
    Se o /countries falhar, usa uma lista fallback estática.
    """
    try:
        data = fetch_json("countries")
        resp = data.get("response", [])
        europe = {c.get("name") for c in resp if (c or {}).get("continent") == "Europe"}
        europe.discard(None)
        europe.update({"Saudi Arabia"})
        return europe
    except Exception as e:
        print(f"[aviso] Falhou /countries ({e}), usando fallback estático.")
        europe_fallback = {
            "Portugal","Spain","England","France","Germany","Italy","Netherlands","Belgium",
            "Turkey","Greece","Switzerland","Denmark","Croatia","Hungary",

        }
        europe_fallback.update({"Brazil", "Saudi Arabia"})
        return europe_fallback

def fetch_leagues_for_season() -> List[Dict[str, Any]]:
    # 'current=true' ajuda a reduzir ruído (se a tua conta permitir)
    params = {"season": SEASON}
    try:
        data = fetch_json("leagues", params=params)
        return data.get("response", [])
    except requests.HTTPError as e:
        print(f"[erro] HTTP ao pedir /leagues: {e}")
        raise

def main() -> int:
    if not API_KEY:
        print("API_FOOTBALL_KEY não definida.")
        return 1

    target_countries = get_target_countries()
    leagues = fetch_leagues_for_season()

    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for item in leagues:
        league = item.get("league") or {}
        country = item.get("country") or {}
        lid = league.get("id")
        lname = (league.get("name") or "").strip()
        cname = (country.get("name") or "").strip()

        if not lid or not lname or not cname:
            continue

        # Mantém se for país-alvo OU se for liga UEFA especial
        if not (cname in target_countries or lname in EXTRA_LEAGUES):
            continue

        key = str(lid)
        if key in seen:
            continue
        seen.add(key)

        out.append({"id": int(lid), "name": lname, "country": cname})

    out.sort(key=lambda x: (x.get("country") or "", x.get("name") or ""))

    os.makedirs("config", exist_ok=True)
    with open("config/leagues.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Gravado config/leagues.json com {len(out)} ligas.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
