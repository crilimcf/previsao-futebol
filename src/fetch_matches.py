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

# Preferência de bookies ao ler odds reais
PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

# Limites
REQUEST_TIMEOUT = 6
MAX_GOALS = 6     # Poisson 0..6
DAYS_AHEAD  = 5   # hoje + 4 dias
MAX_CALLS_PER_RUN = 50  # limite global de chamadas API num único run

# Cache TTLs
PLAYERS_CACHE_TTL = 24 * 3600       # 24h
TOPSCORERS_CACHE_TTL = 12 * 3600    # 12h
TEAMS_STATS_TTL = 6 * 3600          # 6h
GENERIC_CACHE_TTL = 1800            # 30m

# =========================
# Redis helper (via config)
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
                time.sleep(WAIT_SECONDS * (attempt + 1))  # espera exponencial
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
# RESTO DO SCRIPT (inalterado)
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

# Funções seguintes (_fixtures_by_date, _team_stats, _odds_by_fixture, etc.)
# continuam exatamente como estavam no teu ficheiro original.
# Nenhum cálculo de Poisson, odds ou gravação foi alterado.
# Apenas a função _get_api passou a controlar as chamadas à API-Football.
