#!/usr/bin/env python3
import os, json, requests
from typing import List, Dict, Any

API_KEY  = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = (os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/")
SEASON   = os.getenv("API_FOOTBALL_SEASON", "2025")
HEADERS  = {"x-apisports-key": API_KEY} if API_KEY else {}

# Países alvo: Europa + Brasil + Arábia Saudita + competições UEFA
EUROPE = {
    "UEFA Europa League","UEFA Champions League","UEFA Europa League","Primeira Liga"
   
}


TARGET_COUNTRIES = EUROPE | EXTRA

def fetch_leagues_for_season() -> List[Dict[str, Any]]:
    url = BASE_URL + "leagues"
    r = requests.get(url, headers=HEADERS, params={"season": SEASON}, timeout=20)
    r.raise_for_status()
    return r.json().get("response", [])

def main() -> int:
    if not API_KEY:
        print("API_FOOTBALL_KEY não definida.")
        return 1

    data = fetch_leagues_for_season()
    out: List[Dict[str, Any]] = []
    seen = set()

    for item in data:
        league = item.get("league") or {}
        country = item.get("country") or {}
        lid = league.get("id")
        lname = league.get("name") or ""
        cname = country.get("name") or ""

        if not lid or not lname or not cname:
            continue

        # Filtra por países alvo
        if cname not in TARGET_COUNTRIES:
            continue

        key = f"{lid}"
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
