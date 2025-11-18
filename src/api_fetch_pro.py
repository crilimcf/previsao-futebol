# src/api_fetch_pro.py
import os
import json
import math
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from datetime import date, timedelta

import requests
from src import config

# ===========================================================
# LOG
# ===========================================================
logger = logging.getLogger("football_api")
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ===========================================================
# ENV
# ===========================================================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/"

SEASON_CLUBS = os.getenv("API_FOOTBALL_SEASON", "2025")

WCQ_EUROPE_LEAGUE_ID = int(os.getenv("API_FOOTBALL_WCQ_EUROPE_LEAGUE_ID", "32"))
WCQ_EUROPE_SEASON = os.getenv("API_FOOTBALL_WCQ_EUROPE_SEASON", "2024")

PROXY_BASE = os.getenv("API_PROXY_URL", "https://football-proxy-4ymo.onrender.com").rstrip("/") + "/"
PROXY_TOKEN = os.getenv("API_PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")

PRED_PATH = os.path.join("data", "predict", "predictions.json")

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# ===========================================================
# REDIS HELPER
# ===========================================================
def redis_cache_get(key: str) -> Optional[Any]:
    try:
        if config.redis_client:
            raw = config.redis_client.get(key)
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return None


def redis_cache_set(key: str, value: Any, ex: int = 1800) -> None:
    try:
        if config.redis_client:
            config.redis_client.set(key, json.dumps(value), ex=ex)
    except Exception:
        pass

# ===========================================================
# HTTP HELPERS
# ===========================================================
def proxy_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Optional[Dict[str, Any]]:
    """Chama o proxy seguro (Render)."""
    url = urljoin(PROXY_BASE, path.lstrip("/"))
    try:
        r = requests.get(url, params=params or {}, headers={"x-proxy-token": PROXY_TOKEN}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"⚠️ Proxy {url} {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"❌ Proxy erro {url}: {e}")
    return None

# ===========================================================
# POISSON + ODDS
# ===========================================================
def _poisson_pmf(lmbda: float, k: int) -> float:
    try:
        return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)
    except Exception:
        return 0.0

def poisson_score_probs(lambda_home: float, lambda_away: float, max_goals: int = 6) -> List[List[float]]:
    mat = []
    for h in range(max_goals + 1):
        row = []
        for a in range(max_goals + 1):
            row.append(_poisson_pmf(lambda_home, h) * _poisson_pmf(lambda_away, a))
        mat.append(row)
    s = sum(sum(r) for r in mat)
    return [[x / s for x in r] for r in mat] if s else mat

def outcome_probs_from_matrix(mat: List[List[float]]) -> Tuple[float, float, float]:
    ph, pd, pa = 0.0, 0.0, 0.0
    for h in range(len(mat)):
        for a in range(len(mat[h])):
            if h > a:
                ph += mat[h][a]
            elif h == a:
                pd += mat[h][a]
            else:
                pa += mat[h][a]
    return ph, pd, pa

def implied_odds(p: float) -> float:
    return round(1 / max(p, 1e-6), 2)

# ===========================================================
# FIXTURES COLLECTOR
# ===========================================================
def _dedupe(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, result = set(), []
    for f in fixtures:
        fid = f.get("fixture", {}).get("id")
        if fid and fid not in seen:
            seen.add(fid)
            result.append(f)
    return result


def collect_fixtures(days: int = 3) -> List[Dict[str, Any]]:
    fixtures: List[Dict[str, Any]] = []

    # Clubes
    for d in range(days):
        iso = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        payload = proxy_get("/fixtures", {"date": iso, "season": SEASON_CLUBS})
        if payload and isinstance(payload.get("response"), list):
            logger.info(f"📅 {iso} | {len(payload['response'])} jogos (clubes)")
            fixtures.extend(payload["response"])
        else:
            logger.warning(f"⚠️ {iso} sem jogos (clubes).")
        time.sleep(0.15)

    # World Cup - Qualification Europe
    payload_wcq = proxy_get("/fixtures", {"league": WCQ_EUROPE_LEAGUE_ID, "season": WCQ_EUROPE_SEASON, "next": 50})
    if payload_wcq and isinstance(payload_wcq.get("response"), list):
        logger.info(f"🌍 WCQ Europe | {len(payload_wcq['response'])} jogos (league 32)")
        fixtures.extend(payload_wcq["response"])
    else:
        logger.warning(f"⚠️ Nenhum jogo WCQ Europe via proxy")

    fixtures = _dedupe(fixtures)
    logger.info(f"📊 Total fixtures após dedupe: {len(fixtures)}")

    # Log por liga
    by_league = {}
    for f in fixtures:
        lid = int(f.get("league", {}).get("id", 0))
        if lid:
            by_league[lid] = by_league.get(lid, 0) + 1
    logger.info(f"📊 Fixtures por liga: {by_league}")

    return fixtures

# ===========================================================
# PREDICTION SIMULATOR (simplificado)
# ===========================================================
def build_prediction_from_fixture(fix: Dict[str, Any]) -> Dict[str, Any]:
    f = fix["fixture"]
    l = fix["league"]
    t = fix["teams"]

    mat = poisson_score_probs(1.4, 1.1)
    ph, pd, pa = outcome_probs_from_matrix(mat)
    odds = {"home": implied_odds(ph), "draw": implied_odds(pd), "away": implied_odds(pa)}

    return {
        "match_id": f.get("id"),
        "league_id": l.get("id"),
        "league": l.get("name"),
        "country": l.get("country"),
        "date": f.get("date"),
        "home_team": t["home"]["name"],
        "away_team": t["away"]["name"],
        "odds": odds,
        "confidence": max(ph, pd, pa),
    }

# ===========================================================
# PIPELINE
# ===========================================================
def fetch_and_save_predictions(days: int = 3) -> Dict[str, Any]:
    fixtures = collect_fixtures(days)
    preds = [build_prediction_from_fixture(f) for f in fixtures if f]
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(preds, fp, ensure_ascii=False, indent=2)
    logger.info(f"✅ {len(preds)} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": len(preds), "days": days}
