import requests
import json
import os
import time
import random
import logging
from datetime import date, timedelta
from src import config

logger = logging.getLogger("football_api")
redis = config.redis_client

API_KEY = os.getenv("API_KEY") or os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"
HEADERS = {"x-apisports-key": API_KEY}


# ======================================================
# REDIS CACHE
# ======================================================
def redis_cache_get(key):
    try:
        if redis:
            val = redis.get(key)
            if val:
                return json.loads(val)
    except Exception:
        pass
    return None


def redis_cache_set(key, data, expire=3600):
    try:
        if redis:
            redis.set(key, json.dumps(data), ex=expire)
    except Exception:
        pass


# ======================================================
# SAFE REQUEST
# ======================================================
def safe_request(url, params=None):
    key = f"cache:{url}:{json.dumps(params, sort_keys=True)}"
    cached = redis_cache_get(key)
    if cached:
        return cached
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=5)
        if r.status_code == 200:
            data = r.json().get("response", [])
            redis_cache_set(key, data)
            return data
        else:
            logger.warning(f"⚠️ {r.status_code} em {url}")
            return []
    except Exception as e:
        logger.error(f"❌ Erro em {url}: {e}")
        return []


# ======================================================
# LIGAS
# ======================================================
def get_all_leagues():
    cache_key = "cache:leagues"
    cached = redis_cache_get(cache_key)
    if cached:
        return cached

    leagues = []
    try:
        data = safe_request(f"{BASE_URL}leagues", {"season": SEASON})
        for l in data:
            league = l.get("league", {})
            country = l.get("country", {})
            if league.get("id") and league.get("type") == "League":
                leagues.append({
                    "id": league["id"],
                    "name": league["name"],
                    "logo": league.get("logo"),
                    "country": country.get("name"),
                })
        redis_cache_set(cache_key, leagues, 21600)  # 6h cache
    except Exception as e:
        logger.warning(f"⚠️ Erro ao obter ligas: {e}")
    return leagues[:25]


# ======================================================
# PREVISÃO
# ======================================================
def calculate_prediction(stats_home, stats_away):
    try:
        avg_home = float(stats_home.get("goals", {}).get("for", {}).get("average", {}).get("home", 1.2))
        avg_away = float(stats_away.get("goals", {}).get("for", {}).get("average", {}).get("away", 1.1))
        score_home = max(0, round(avg_home + random.uniform(-0.5, 0.5)))
        score_away = max(0, round(avg_away + random.uniform(-0.5, 0.5)))
        conf = min(0.95, round(0.6 + abs(score_home - score_away) * 0.1 + random.uniform(0.05, 0.15), 2))
        return {"predicted_score": {"home": score_home, "away": score_away}, "confidence": conf}
    except Exception:
        return {"predicted_score": {"home": 1, "away": 1}, "confidence": 0.6}


# ======================================================
# TOP SCORERS
# ======================================================
def get_top_scorers(league_id):
    try:
        data = safe_request(f"{BASE_URL}players/topscorers", {"league": league_id, "season": SEASON})
        return [
            {
                "player": s.get("player", {}).get("name"),
                "team": s.get("statistics", [{}])[0].get("team", {}).get("name"),
                "goals": s.get("statistics", [{}])[0].get("goals", {}).get("total", 0),
            }
            for s in data[:5]
        ]
    except Exception:
        return []


# ======================================================
# FETCH PRINCIPAL
# ======================================================
def fetch_today_matches():
    if not API_KEY:
        logger.error("❌ API_FOOTBALL_KEY ausente.")
        return {"status": "error", "detail": "API key missing"}

    leagues = get_all_leagues()
    matches = []
    total = 0

    for day_offset in range(3):
        match_date = (date.today() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        for league in leagues:
            data = safe_request(f"{BASE_URL}fixtures", {"league": league["id"], "season": SEASON, "date": match_date})
            for f in data:
                fixture = f.get("fixture", {})
                teams = f.get("teams", {})
                if not teams.get("home") or not teams.get("away"):
                    continue

                stats_home = safe_request(f"{BASE_URL}teams/statistics", {"team": teams["home"]["id"], "league": league["id"], "season": SEASON})
                stats_away = safe_request(f"{BASE_URL}teams/statistics", {"team": teams["away"]["id"], "league": league["id"], "season": SEASON})

                pred = calculate_prediction(stats_home if isinstance(stats_home, dict) else {}, stats_away if isinstance(stats_away, dict) else {})
                top_scorers = get_top_scorers(league["id"])

                matches.append({
                    "match_id": fixture.get("id"),
                    "league": league["name"],
                    "league_id": league["id"],
                    "league_logo": league.get("logo"),
                    "home_team": teams.get("home", {}).get("name"),
                    "away_team": teams.get("away", {}).get("name"),
                    "home_logo": teams.get("home", {}).get("logo"),
                    "away_logo": teams.get("away", {}).get("logo"),
                    "date": fixture.get("date"),
                    "predicted_score": pred["predicted_score"],
                    "confidence": pred["confidence"],
                    "top_scorers": top_scorers,
                })
                total += 1

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ {total} previsões salvas em {PRED_PATH}")
    config.update_last_update()
    return {"status": "ok", "total": total}
