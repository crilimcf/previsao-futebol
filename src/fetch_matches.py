# src/fetch_matches.py
import os
import json
import math
import time
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

PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

REQUEST_TIMEOUT = 6
MAX_GOALS = 6
DAYS_AHEAD = 5
MAX_CALLS_PER_RUN = 50  # proteção extra

PLAYERS_CACHE_TTL = 24 * 3600
TOPSCORERS_CACHE_TTL = 12 * 3600
TEAMS_STATS_TTL = 6 * 3600
GENERIC_CACHE_TTL = 1800

# =========================
# Redis helper
# =========================
redis = config.redis_client

def _rget(key: str) -> Optional[str]:
    try:
        return redis.get(key) if redis else None
    except Exception:
        return None

def _rset(key: str, value: str, ex: Optional[int] = GENERIC_CACHE_TTL):
    try:
        if redis:
            redis.set(key, value, ex=ex)
    except Exception:
        pass

# =========================
# HTTP + CACHE + RATE-LIMIT
# =========================
_call_counter = 0

def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    p = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return f"cache:{url}:{p}"

def _get_api(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    GET à API-Football com cache Redis e controlo de rate-limit.
    Faz retry automático em 429 Too Many Requests e limita total de chamadas por run.
    """
    global _call_counter

    if not API_KEY:
        logger.error("❌ API_FOOTBALL_KEY não definida.")
        return []

    if _call_counter >= MAX_CALLS_PER_RUN:
        logger.warning(f"⚠️ Limite global de chamadas atingido ({MAX_CALLS_PER_RUN}), ignorando {endpoint}")
        return []

    url = BASE_URL + endpoint.lstrip("/")
    key = _cache_key(url, params)

    cached = _rget(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    MAX_RETRIES = 5
    WAIT_SECONDS = 2

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, params=params or {}, timeout=REQUEST_TIMEOUT)
            _call_counter += 1

            if r.status_code == 200:
                body = r.json()
                data = body.get("response", body)
                _rset(key, json.dumps(data), ex=GENERIC_CACHE_TTL)
                time.sleep(1)  # respeita ~1 req/s
                return data

            elif r.status_code == 429:
                logger.warning(f"⚠️ API {endpoint} -> HTTP 429 Too Many Requests (tentativa {attempt+1}/{MAX_RETRIES})")
                time.sleep(WAIT_SECONDS * (attempt + 1))
                continue

            else:
                logger.warning(f"⚠️ API {endpoint} -> HTTP {r.status_code}: {r.text[:200]}")
                return []

        except Exception as e:
            logger.error(f"❌ API {endpoint} erro: {e}")
            time.sleep(2)
            continue

    logger.error(f"❌ API {endpoint} falhou após {MAX_RETRIES} tentativas.")
    return []

# =========================
# LIGAS + FIXTURES
# =========================
def _load_target_league_ids() -> List[int]:
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

    ck = "cache:all_leagues_ids"
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    data = _get_api("leagues", {"season": SEASON}) or []
    ids: List[int] = []
    try:
        for item in data:
            lg = item.get("league", {})
            if lg.get("id"):
                ids.append(int(lg["id"]))
        ids = sorted(list(set(ids)))
        _rset(ck, json.dumps(ids), ex=12 * 3600)
    except Exception as e:
        logger.warning(f"⚠️ erro a obter ligas: {e}")
        ids = [39, 140, 135, 78, 61, 94, 88, 2]
    return ids

def _fixtures_by_date(yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    return _get_api("fixtures", {"date": yyyy_mm_dd, "season": SEASON}) or []

# =========================
# FUNÇÃO PRINCIPAL
# =========================
def fetch_today_matches() -> Dict[str, Any]:
    """
    Busca fixtures (hoje + próximos dias), odds, stats, etc.
    Gera previsões simples e guarda em data/predict/predictions.json
    """
    if not API_KEY:
        msg = "❌ API_FOOTBALL_KEY não definida."
        logger.error(msg)
        return {"status": "error", "detail": "API key missing", "total": 0}

    target_leagues = set(_load_target_league_ids())
    fixtures_all: List[Dict[str, Any]] = []

    for d in range(DAYS_AHEAD):
        ymd = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        day_fixtures = _fixtures_by_date(ymd) or []
        for f in day_fixtures:
            lg = f.get("league") or {}
            if not lg.get("id"):
                continue
            if target_leagues and int(lg["id"]) not in target_leagues:
                continue
            fixtures_all.append(f)

    out = []
    for f in fixtures_all:
        league = (f.get("league") or {}).get("name", "?")
        home = ((f.get("teams") or {}).get("home") or {}).get("name", "?")
        away = ((f.get("teams") or {}).get("away") or {}).get("name", "?")
        logger.info(f"📅 {league}: {home} vs {away}")

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    logger.info(f"✅ {len(out)} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": len(out)}

if __name__ == "__main__":
    print(fetch_today_matches())
