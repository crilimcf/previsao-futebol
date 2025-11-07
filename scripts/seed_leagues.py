#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera listas curadas de ligas/taças por época (2024, 2025, …) a partir da API-Football
e fixa os IDs num ficheiro config/leagues_ids.json para uso em épocas futuras.

Env vars:
  API_FOOTBALL_KEY      -> chave da API-Football
  API_FOOTBALL_BASE     -> (opcional) default https://v3.football.api-sports.io/
  API_FOOTBALL_SEASONS  -> "2024,2025"
"""

from __future__ import annotations
import os, json, unicodedata, requests, sys, pathlib, re
from typing import Dict, List, Any, Set, Tuple

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE = (os.getenv("API_FOOTBALL_BASE") or "https://v3.football.api-sports.io/").rstrip("/") + "/"
SEASONS = [s.strip() for s in (os.getenv("API_FOOTBALL_SEASONS") or "2024,2025").split(",") if s.strip()]
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

CFG_DIR = pathlib.Path("config")
CFG_DIR.mkdir(parents=True, exist_ok=True)
IDS_PATH = CFG_DIR / "leagues_ids.json"

def nrm(s: str) -> str:
    """normaliza: tira acentos, põe minúsculas e remove pontuação/hífens."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)   # <- remove hífens/pontuação
    return " ".join(s.split())

def fetch(endpoint: str, **params):
    url = BASE + endpoint.lstrip("/")
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    if r.status_code >= 400:
        print(f"[HTTP {r.status_code}] {url}")
        try:
            print(r.json())
        except Exception:
            print(r.text)
        r.raise_for_status()
    return r.json()

def load_ids() -> Dict[str, Dict[str, Any]]:
    if IDS_PATH.exists():
        try:
            with open(IDS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def save_ids(ids_map: Dict[str, Dict[str, Any]]):
    with open(IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(ids_map, f, ensure_ascii=False, indent=2)

# Preferências por competição (IDs conhecidos e “palavras proibidas” para L1)
PREFERRED_IDS: Dict[str, int] = {
    "BEL-L1": 144,   # Belgium Pro League (First Division A)
    "KSA-L1": 152,   # Saudi Pro League
}
BANNED_HINTS_TOP: Set[str] = {
    "challenger", "division b", "first division b", "segunda", "league two", "second division", "serie b"
}
def is_top_tier_key(key: str) -> bool:
    return key.endswith("-L1")

# ------------------------------------------------------------------------------------
# TARGETS: (key, country, type, {keywords…}, preferred_name)
# ------------------------------------------------------------------------------------
TARGETS: List[Tuple[str, str, str, Set[str], str]] = [
    # 🇵🇹 Portugal
    ("POR-L1", "Portugal", "League", {"primeira liga", "liga portugal"}, "Liga Portugal"),
    ("POR-L2", "Portugal", "League", {"liga portugal 2", "segunda liga", "liga 2"}, "Liga Portugal 2"),
    ("POR-CUP", "Portugal", "Cup", {"taca de portugal", "taça de portugal"}, "Taça de Portugal"),
    ("POR-LCUP", "Portugal", "Cup", {"taca da liga", "allianz cup", "taça da liga"}, "Taça da Liga"),

    # 🇪🇸 Spain
    ("ESP-L1", "Spain", "League", {"la liga", "laliga", "la liga ea sports"}, "La Liga"),
    ("ESP-L2", "Spain", "League", {"segunda division", "laliga 2", "segunda división"}, "Segunda División"),
    ("ESP-CUP", "Spain", "Cup", {"copa del rey", "taça del rey", "copa do rei"}, "Copa del Rey"),

    # 🇫🇷 France
    ("FRA-L1", "France", "League", {"ligue 1"}, "Ligue 1"),
    ("FRA-L2", "France", "League", {"ligue 2"}, "Ligue 2"),
    ("FRA-CUP", "France", "Cup", {"coupe de france", "taca da franca", "taça da frança"}, "Coupe de France"),
    ("FRA-LCUP", "France", "Cup", {"coupe de la ligue", "taca da liga franca"}, "Coupe de la Ligue"),  # descontinuada

    # 🏴 England
    ("ENG-L1", "England", "League", {"premier league"}, "Premier League"),
    ("ENG-L2", "England", "League", {"championship"}, "Championship"),
    ("ENG-FA", "England", "Cup", {"fa cup", "taca de inglaterra", "taça de inglaterra"}, "FA Cup"),
    ("ENG-LCUP", "England", "Cup", {"efl cup", "league cup", "carabao cup", "taça da liga"}, "EFL Cup"),

    # 🇩🇪 Germany
    ("GER-L1", "Germany", "League", {"bundesliga"}, "Bundesliga"),
    ("GER-L2", "Germany", "League", {"2. bundesliga", "2 bundesliga", "zweite bundesliga"}, "2. Bundesliga"),
    ("GER-CUP", "Germany", "Cup", {"dfb pokal", "taca da alemanha", "taça da alemanha"}, "DFB-Pokal"),

    # 🇮🇹 Italy
    ("ITA-L1", "Italy", "League", {"serie a"}, "Serie A"),
    ("ITA-L2", "Italy", "League", {"serie b"}, "Serie B"),
    ("ITA-CUP", "Italy", "Cup", {"coppa italia", "taca de italia", "taça de italia"}, "Coppa Italia"),

    # 🇳🇱 Netherlands
    ("NED-L1", "Netherlands", "League", {"eredivisie"}, "Eredivisie"),

    # 🇧🇪 Belgium
    ("BEL-L1", "Belgium", "League", {"pro league", "first division a", "jupiler pro league"}, "Pro League"),

    # 🇸🇨 Scotland
    ("SCO-L1", "Scotland", "League", {"premiership", "scottish premiership"}, "Premiership"),

    # 🇹🇷 Turkey
    ("TUR-L1", "Turkey", "League", {"super lig", "süper lig"}, "Süper Lig"),

    # 🇬🇷 Greece
    ("GRE-L1", "Greece", "League", {"super league", "super league 1"}, "Super League 1"),

    # 🇨🇭 Switzerland
    ("SUI-L1", "Switzerland", "League", {"super league"}, "Super League"),

    # 🇩🇰 Denmark
    ("DEN-L1", "Denmark", "League", {"superliga"}, "Superliga"),

    # 🇦🇹 Austria
    ("AUT-L1", "Austria", "League", {"bundesliga"}, "Bundesliga"),

    # 🇧🇷 Brazil
    ("BRA-L1", "Brazil", "League", {"serie a", "brasileirao", "brasileirão"}, "Serie A (Brasileirão)"),
    ("BRA-CUP", "Brazil", "Cup", {"copa do brasil"}, "Copa do Brasil"),

    # 🇸🇦 Saudi Arabia (inclui “Roshn”)
    ("KSA-L1", "Saudi Arabia", "League",
     {"pro league", "saudi pro league", "saudi professional league", "saudi league", "roshn", "roshn saudi league"},
     "Saudi Pro League"),

    # 🌍 UEFA
    ("UEFA-UCL", "World", "Cup", {"uefa champions league"}, "UEFA Champions League"),
    ("UEFA-UEL", "World", "Cup", {"uefa europa league"}, "UEFA Europa League"),
    ("UEFA-UECL", "World", "Cup", {"uefa europa conference league"}, "UEFA Europa Conference League"),
]

def pick_best(leagues: List[Dict[str, Any]], key: str, country: str, ltype: str,
              keywords: Set[str], preferred: str) -> Dict[str, Any] | None:
    c = nrm(country)
    t = nrm(ltype)
    ks = {nrm(k) for k in keywords}
    pref = nrm(preferred)
    best = None
    best_score = -10

    for item in leagues:
        league = item.get("league", {}) or {}
        countryObj = item.get("country", {}) or {}
        name_raw = league.get("name", "")
        name = nrm(name_raw)
        type_ = nrm(league.get("type", ""))
        ctry = nrm(countryObj.get("name", ""))

        # tolerância para UEFA (country "World")
        country_ok = (c == "world" and ctry in {"world", ""}) or (ctry == c)
        if not country_ok or type_ != t:
            continue

        # precisa casar pelo menos um keyword
        if not any(k in name for k in ks):
            continue

        score = 0
        # força pelos keywords
        for k in ks:
            if k in name:
                score += 10 + len(k)

        # preferências
        if name == pref:
            score += 30
        elif pref in name:
            score += 8

        # ID preferido conhecido
        pref_id = PREFERRED_IDS.get(key)
        if pref_id is not None and int(league.get("id", -1)) == pref_id:
            score += 100

        # evitar 2.as divisões quando queremos L1
        if is_top_tier_key(key) and any(b in name for b in BANNED_HINTS_TOP):
            score -= 80

        if score > best_score:
            best_score = score
            best = {
                "id": int(league["id"]),
                "name": name_raw,
                "country": countryObj.get("name") or country,
                "type": league.get("type"),
            }

    return best

def season_run(season: str, ids_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    print(f"→ A obter /leagues para season={season} ...")
    data = fetch("leagues", season=season)
    resp = data.get("response", []) or []

    out: List[Dict[str, Any]] = []
    seen_ids: Set[int] = set()

    for key, country, ltype, keywords, preferred in TARGETS:
        m = pick_best(resp, key, country, ltype, keywords, preferred)
        if m:
            if m["id"] not in seen_ids:
                out.append(m); seen_ids.add(m["id"])
            # atualiza mapeamento fixo
            ids_map[key] = {
                "id": m["id"], "country": country, "type": ltype,
                "preferred": preferred, "last_name": m.get("name"),
            }
        else:
            # carry-over (ID fixo de época anterior)
            fixed = ids_map.get(key)
            if fixed:
                entry = {
                    "id": int(fixed["id"]),
                    "name": fixed.get("last_name") or fixed.get("preferred") or preferred,
                    "country": country, "type": ltype,
                }
                if entry["id"] not in seen_ids:
                    out.append(entry); seen_ids.add(entry["id"])
                print(f"[INFO] Usado ID fixo {entry['id']} para {country}/{ltype} ({preferred}) em {season}")
            else:
                anykw = next(iter(keywords)) if keywords else "—"
                print(f"[WARN] Não encontrado: {country} / {ltype} / {anykw}")

    out.sort(key=lambda x: (x.get("country") or "", x.get("type") or "", x.get("name") or ""))

    path = CFG_DIR / f"leagues_{season}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✅ Gravado {path} com {len(out)} ligas/taças.")

    return out

def main():
    if not API_KEY:
        print("ERRO: define API_FOOTBALL_KEY no ambiente.")
        sys.exit(1)

    ids_map = load_ids()
    latest: List[Dict[str, Any]] | None = None

    for s in SEASONS:
        latest = season_run(s, ids_map)
        save_ids(ids_map)

    if latest is not None:
        with open(CFG_DIR / "leagues.json", "w", encoding="utf-8") as f:
            json.dump(latest, f, ensure_ascii=False, indent=2)
        print("ℹ️  Também gravei config/leagues.json com a lista da época mais recente.")

    save_ids(ids_map)
    print(f"🔒 IDs fixos atualizados em {IDS_PATH}")

if __name__ == "__main__":
    main()
