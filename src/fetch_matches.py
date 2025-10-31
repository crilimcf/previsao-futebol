import requests
import json
import os
import time
import random
import logging
from datetime import date, timedelta
from src import config
from upstash_redis import Redis

# ============================================
# CONFIGURAÇÕES GERAIS
# ============================================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY}

logger = logging.getLogger("football_api")
redis = config.redis_client  # Redis partilhado do projeto

# ============================================
# FUNÇÕES DE CACHE (Redis)
# ============================================
def redis_cache_get(key):
    """Obtém dados da cache Redis se existir."""
    try:
        if redis:
            cached = redis.get(key)
            if cached:
                return json.loads(cached)
    except Exception:
        pass
    return None


def redis_cache_set(key, data, expire=3600):
    """Grava dados em cache Redis (1h por defeito)."""
    try:
        if redis:
            redis.set(key, json.dumps(data), ex=expire)
    except Exception:
        pass


# ============================================
# FUNÇÃO DE REQUEST COM CACHE E TIMEOUT
# ============================================
def safe_request(url, params=None):
    """Executa pedidos HTTP com cache Redis e timeout curto."""
    key = f"cache:{url}:{json.dumps(params, sort_keys=True)}"
    cached = redis_cache_get(key)
    if cached:
        return cached

    start = time.time()
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=3)
        if r.status_code == 200:
            data = r.json().get("response", [])
            redis_cache_set(key, data)
            elapsed = round(time.time() - start, 2)
            logger.info(f"✅ {url} OK ({elapsed}s)")
            return data
        else:
            logger.warning(f"⚠️ Erro {r.status_code} em {url}")
            return []
    except Exception as e:
        logger.error(f"❌ Timeout/API error em {url}: {e}")
        return []


# ============================================
# OBTÉM TODAS AS LIGAS DISPONÍVEIS (CORRIGIDO)
# ============================================
def get_all_leagues():
    """Obtém automaticamente todas as ligas disponíveis da API-Football, com fallback garantido."""
    cache_key = "cache:all_leagues"
    cached = redis_cache_get(cache_key)
    if cached and len(cached) > 0:
        logger.info(f"📦 {len(cached)} ligas carregadas da cache Redis.")
        return cached

    try:
        url = f"{BASE_URL}leagues"
        data = safe_request(url, {"season": SEASON})
        league_ids = []

        if data and isinstance(data, list):
            for l in data:
                league = l.get("league", {})
                if league.get("id") and l.get("country", {}).get("name"):
                    league_ids.append(league["id"])

        # fallback — se a API falhar ou retornar vazio
        if not league_ids:
            logger.warning("⚠️ Nenhuma liga retornada pela API — usando fallback padrão.")
            league_ids = [39, 140, 135, 78, 61, 94, 88, 2]

        league_ids = list(set(league_ids))
        redis_cache_set(cache_key, league_ids, expire=43200)
        logger.info(f"✅ {len(league_ids)} ligas carregadas e guardadas em cache.")
        return league_ids

    except Exception as e:
        logger.error(f"⚠️ Erro ao obter ligas: {e}")
        # fallback mínimo
        return [39, 140, 135, 78, 61, 94, 88, 2]


# ============================================
# FUNÇÃO DE PREVISÃO DE RESULTADO
# ============================================
def calculate_prediction(stats_home, stats_away):
    """Calcula resultado provável e confiança."""
    try:
        avg_goals_home = float(stats_home.get("goals", {}).get("for", {}).get("average", {}).get("home", 1.2))
        avg_goals_away = float(stats_away.get("goals", {}).get("for", {}).get("average", {}).get("away", 1.1))
        avg_concede_home = float(stats_home.get("goals", {}).get("against", {}).get("average", {}).get("home", 1.0))
        avg_concede_away = float(stats_away.get("goals", {}).get("against", {}).get("average", {}).get("away", 1.0))

        home_score = (avg_goals_home + avg_concede_away) / 2
        away_score = (avg_goals_away + avg_concede_home) / 2

        predicted_home = max(0, round(home_score + random.uniform(-0.4, 0.4)))
        predicted_away = max(0, round(away_score + random.uniform(-0.4, 0.4)))

        confidence = round(
            0.55 + abs(predicted_home - predicted_away) * 0.1 + random.uniform(0.05, 0.15),
            2
        )
        confidence = min(confidence, 0.95)

        return {
            "predicted_score": {"home": predicted_home, "away": predicted_away},
            "confidence": confidence,
        }

    except Exception:
        return {
            "predicted_score": {"home": random.randint(0, 3), "away": random.randint(0, 3)},
            "confidence": round(random.uniform(0.5, 0.7), 2),
        }


# ============================================
# TOP MARCADORES (REAL API-FOOTBALL)
# ============================================
def get_top_scorers(league_id):
    """Obtém os principais marcadores da liga."""
    try:
        url = f"{BASE_URL}players/topscorers"
        scorers = safe_request(url, {"league": league_id, "season": SEASON})
        result = []
        for s in scorers[:25]:  # até 25 principais
            player = s.get("player", {}).get("name")
            team = s.get("statistics", [{}])[0].get("team", {}).get("name")
            goals = s.get("statistics", [{}])[0].get("goals", {}).get("total", 0)
            result.append({
                "player": player,
                "team": team,
                "goals": goals,
                "probability": round(0.4 + goals * 0.03 + random.uniform(0.05, 0.1), 2)
            })
        return result
    except Exception as e:
        logger.warning(f"⚠️ Erro ao buscar marcadores: {e}")
        return []


# ============================================
# FUNÇÃO PRINCIPAL — BUSCAR JOGOS E GERAR PREVISÕES
# ============================================
def fetch_today_matches():
    """Obtém jogos de hoje, amanhã e depois de amanhã e gera previsões completas."""
    if not API_KEY:
        msg = "❌ API_FOOTBALL_KEY não definida."
        print(msg)
        logger.error(msg)
        return {"status": "error", "detail": "API key missing"}

    league_ids = get_all_leagues()
    matches = []
    total = 0

    for day_offset in range(3):  # hoje + 2 dias seguintes
        match_date = (date.today() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        print(f"\n📅 Buscando jogos de {match_date}... ({len(league_ids)} ligas)")

        for league_id in league_ids:
            fixtures_url = f"{BASE_URL}fixtures"
            data = safe_request(fixtures_url, {"league": league_id, "season": SEASON, "date": match_date})

            if not data:
                continue

            for f in data:
                fixture = f.get("fixture", {})
                league = f.get("league", {})
                teams = f.get("teams", {})

                home_id = teams.get("home", {}).get("id")
                away_id = teams.get("away", {}).get("id")

                if not home_id or not away_id:
                    continue

                # Busca estatísticas (com cache)
                stats_home = safe_request(f"{BASE_URL}teams/statistics", {"team": home_id, "league": league_id, "season": SEASON})
                stats_away = safe_request(f"{BASE_URL}teams/statistics", {"team": away_id, "league": league_id, "season": SEASON})

                stats_home_data = stats_home if isinstance(stats_home, dict) else (stats_home[0] if stats_home else {})
                stats_away_data = stats_away if isinstance(stats_away, dict) else (stats_away[0] if stats_away else {})

                # Calcula previsão e obtém marcadores
                pred = calculate_prediction(stats_home_data, stats_away_data)
                top_scorers = get_top_scorers(league_id)

                # Cria registo
                match = {
                    "match_id": fixture.get("id"),
                    "league": league.get("name"),
                    "league_id": league_id,
                    "home_team": teams.get("home", {}).get("name"),
                    "away_team": teams.get("away", {}).get("name"),
                    "date": fixture.get("date"),
                    "predicted_score": pred["predicted_score"],
                    "confidence": pred["confidence"],
                    "top_scorers": top_scorers,
                }
                matches.append(match)
                total += 1

                print(f"⚽ {match['home_team']} vs {match['away_team']} → "
                      f"{pred['predicted_score']['home']}-{pred['predicted_score']['away']} "
                      f"(confiança {pred['confidence']*100:.0f}%)")

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    msg = f"\n✅ {total} previsões salvas em {PRED_PATH}"
    print(msg)
    logger.info(msg)

    try:
        config.update_last_update()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao atualizar Redis: {e}")

    return {"status": "ok", "total": total}


if __name__ == "__main__":
    result = fetch_today_matches()
    print(result)
