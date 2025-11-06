#!/usr/bin/env python3
import os
import json
import requests
import unicodedata
from typing import List, Dict, Any, Set
from datetime import datetime

def normalize_base(url: str | None) -> str:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return "https://v3.football.api-sports.io/"
    return u.rstrip("/") + "/"

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = normalize_base(os.getenv("API_FOOTBALL_BASE"))
SEASONS_ENV = os.getenv("API_FOOTBALL_SEASONS") or os.getenv("API_FOOTBALL_SEASON") or "2024,2025"
FORCE_DISCOVER = os.getenv("FORCE_DISCOVER", "0").strip() in {"1", "true", "yes"}
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# Mantém competições da UEFA (descobertas por nome na 1ª execução; depois ficam por ID)
UEFA_NAMES: Set[str] = {
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Europa Conference League",
}

# --- LISTA EXATA DO QUE QUERES POR PAÍS ---
# match por nome é "accent-insensitive" e por substring (para apanhar sponsors).
ALLOWED_BY_COUNTRY: Dict[str, Dict[str, Set[str]]] = {
    # Portugal
    "Portugal": {
        "League": {
            "Primeira Liga", "Liga Portugal",
            "Liga Portugal 2", "Segunda Liga", "LigaPro",
        },
        "Cup": {
            "Taça de Portugal", "Taca de Portugal",
            "Taça da Liga", "Taca da Liga", "Allianz Cup", "League Cup",
        },
    },
    # Espanha
    "Spain": {
        "League": {
            "La Liga", "LaLiga", "La Liga EA Sports", "Primera Division",
            "Segunda Division", "LaLiga 2", "LaLiga Hypermotion",
        },
        "Cup": {"Copa del Rey"},
    },
    # França
    "France": {
        "League": {"Ligue 1", "Ligue 2", "Ligue 2 BKT"},
        "Cup": {"Coupe de France", "Coupe de la Ligue"},
    },
    # Inglaterra
    "England": {
        "League": {"Premier League", "Championship", "EFL Championship"},
        "Cup": {"FA Cup", "Emirates FA Cup", "EFL Cup", "Carabao Cup", "League Cup"},
    },
    # Alemanha
    "Germany": {
        "League": {"Bundesliga", "2. Bundesliga", "2 Bundesliga"},
        "Cup": {"DFB-Pokal", "DFB Pokal"},
    },
    # Itália
    "Italy": {
        "League": {"Serie A", "Serie B"},
        "Cup": {"Coppa Italia"},
    },
    # Outros (1ª divisão apenas)
    "Netherlands": {"League": {"Eredivisie"}, "Cup": set()},
    "Belgium": {"League": {"Pro League", "First Division A", "Jupiler Pro League"}, "Cup": set()},
    "Scotland": {"League": {"Premiership", "Scottish Premiership"}, "Cup": set()},
    "Turkey": {"League": {"Super Lig", "Süper Lig"}, "Cup": set()},
    "Greece": {"League": {"Super League 1", "Super League Greece"}, "Cup": set()},
    "Switzerland": {"League": {"Super League"}, "Cup": set()},
    "Denmark": {"League": {"Superliga"}, "Cup": set()},
    "Austria": {"League": {"Bundesliga"}, "Cup": set()},
    "Brazil": {
        "League": {"Serie A", "Brasileirao", "Brasileirão"},
        "Cup": {"Copa do Brasil", "Copa do Brazil"},  # variação por segurança
    },
    "Saudi Arabia": {"League": {"Pro League", "Saudi Professional League", "Saudi League"}, "Cup": set()},
}

IDS_FILE = os.path.join("config", "leagues_ids.json")

def fetch_json(endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    url = BASE_URL + endpoint.lstrip("/")
    r = requests.get(url, headers=HEADERS, params=params or {}, timeout=25)
    r.raise_for_status()
    return r.json()

def fetch_leagues_for_season(season: str) -> List[Dict[str, Any]]:
    data = fetch_json("leagues", params={"season": season})
    return data.get("response", [])

def strip_accents_lower(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().split())

def matches_any(name: str, patterns: Set[str]) -> bool:
    if not name or not patterns:
        return False
    n = strip_accents_lower(name)
    for p in patterns:
        if strip_accents_lower(p) in n:
            return True
    return False

def is_allowed_by_name(country: str, ltype: str, lname: str) -> bool:
    cfg = ALLOWED_BY_COUNTRY.get(country)
    if not cfg:
        return False
    if ltype == "League":
        return matches_any(lname, cfg.get("League", set()))
    if ltype == "Cup":
        return matches_any(lname, cfg.get("Cup", set()))
    return False

def discover_ids(seasons: List[str]) -> Dict[str, Any]:
    ids: Set[int] = set()
    details: Dict[int, Dict[str, Any]] = {}

    for season in seasons:
        leagues = fetch_leagues_for_season(season)
        for item in leagues:
            league = item.get("league") or {}
            country = item.get("country") or {}
            lid = league.get("id")
            lname = (league.get("name") or "").strip()
            ltype = (league.get("type") or "").strip()  # "League" | "Cup"
            cname = (country.get("name") or "").strip()
            if not lid or not lname or not cname:
                continue

            # UEFA por nome
            if lname in UEFA_NAMES:
                ids.add(int(lid))
                details[int(lid)] = {"id": int(lid), "name": lname, "country": cname, "type": ltype}
                continue

            # País/taça/ligas pedidas
            if is_allowed_by_name(cname, ltype, lname):
                ids.add(int(lid))
                # guarda o último visto (nome pode mudar por sponsor)
                details[int(lid)] = {"id": int(lid), "name": lname, "country": cname, "type": ltype}

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "seasons_considered": seasons,
        "ids": sorted(ids),
        "details": sorted(details.values(), key=lambda x: (x["country"], x["type"], x["name"])),
    }
    os.makedirs("config", exist_ok=True)
    with open(IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[discover] Gravado {IDS_FILE} com {len(payload['ids'])} IDs fixados.")
    return payload

def load_saved_ids() -> Dict[str, Any] | None:
    if not os.path.exists(IDS_FILE):
        return None
    with open(IDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def run_for_season(season: str, fixed_ids: Set[int]) -> int:
    # Um único call por época; depois filtramos pelos IDs
    leagues = fetch_leagues_for_season(season)
    out = []
    seen: Set[int] = set()

    for item in leagues:
        league = item.get("league") or {}
        country = item.get("country") or {}
        lid = int(league.get("id") or 0)
        if not lid:
            continue
        if lid not in fixed_ids:
            continue

        lname = (league.get("name") or "").strip()
        ltype = (league.get("type") or "").strip()
        cname = (country.get("name") or "").strip()

        if lid in seen:
            continue
        seen.add(lid)
        out.append({"id": lid, "name": lname, "country": cname, "type": ltype})

    out.sort(key=lambda x: (x.get("country") or "", x.get("type") or "", x.get("name") or ""))

    os.makedirs("config", exist_ok=True)
    out_path = os.path.join("config", f"leagues_{season}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[{season}] Gravado {out_path} com {len(out)} competições (IDs fixos).")
    return len(out)

def main() -> int:
    if not API_KEY:
        print("API_FOOTBALL_KEY não definida.")
        return 1

    seasons = [s.strip() for s in SEASONS_ENV.split(",") if s.strip()]
    if not seasons:
        seasons = ["2024", "2025"]

    saved = None if FORCE_DISCOVER else load_saved_ids()
    if saved is None:
        saved = discover_ids(seasons)

    fixed_ids = set(saved.get("ids", []))

    total = 0
    for s in seasons:
        total += run_for_season(s, fixed_ids)

    print(f"Total de entradas geradas (todas as épocas): {total}")
    print("Sugestão: para atualizar a lista de IDs, apaga config/leagues_ids.json ou corre com FORCE_DISCOVER=1.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
