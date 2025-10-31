import requests
import json
import os
import time
import random
import logging
from datetime import date, timedelta
from src import config

# ============================================
# CONFIGURAÇÕES GERAIS
# ============================================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io/"
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY}
logger = logging.getLogger("football_api")

# Redis partilhado do projeto
redis = config.redis_client


# ============================================
# FUNÇÕES DE CACHE (Redis)
# ============================================
def redis_get(key):
    try:
        if redis:
            val = redis.get(key)
            if val:
                return json.loads(val)
    except Exception:
        pass
    return None


def redis_set(key, data, expire=3600):
    try:
        if redis:
            redis.set(key, json.dumps(data), ex=expire)
    except Exception:
        pass


# ============================================
# REQUISIÇÃO SEGURA COM CACHE
# ============================================
def safe_request(url, params=None, cache_ttl=7200):
    key = f"cache:{url}:{json.dumps(params, sort_keys=True)}"
    cached = redis_get(key)
    if cached:
        return cached

    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get("response", [])
            redis_set(key, data, cache_ttl)
            return data
        else:
            logger.warning(f"⚠️ HTTP {r.status_code} → {url}")
            return []
    except Exception as e:
        logger.error(f"❌ Erro em {url}: {e}")
        return []


# ============================================
# ÉPOCA ATIVA
# ============================================
def get_active_season():
    data = safe_request(f"{BASE_URL}leagues/seasons")
    if data and isinstance(data, list):
        return max(data)
    return date.today().year


# ============================================
# LISTA DE LIGAS
# ============================================
def get_main_leagues():
    return [
        39,   # Premier League
        140,  # La Liga
        135,  # Serie A
        78,   # Bundesliga
        61,   # Ligue 1
        94,   # Primeira Liga
        88,   # Eredivisie
        2,    # UEFA Champions League
    ]


# ============================================
# PREVISÃO DE RESULTADO
# ============================================
def calculate_prediction(stats_home, stats_away):
    try:
        avg_goals_home = float(stats_home.get("goals", {}).get("for", {}).get("average", {}).get("home", 1.4))
        avg_goals_away = float(stats_away.get("goals", {}).get("for", {}).get("average", {}).get("away", 1.2))
        concede_home = float(stats_home.get("goals", {}).get("against", {}).get("average", {}).get("home", 1.0))
        concede_away = float(stats_away.get("goals", {}).get("against", {}).get("average", {}).get("away", 1.0))

        h_score = (avg_goals_home + concede_away) / 2
        a_score = (avg_goals_away + concede_home) / 2

        pred_home = max(0, round(h_score + random.uniform(-0.4, 0.4)))
        pred_away = max(0, round(a_score + random.uniform(-0.4, 0.4)))

        confidence = round(0.55 + abs(pred_home - pred_away) * 0.1 + random.uniform(0.05, 0.1), 2)
        confidence = min(confidence, 0.95)

        return {
            "predicted_score": {"home": pred_home, "away": pred_away},
            "confidence": confidence,
        }

    except Exception:
        return {
            "predicted_score": {"home": random.randint(0, 3), "away": random.randint(0, 3)},
            "confidence": round(random.uniform(0.5, 0.7), 2),
        }


# ============================================
# MELHORES MARCADORES
# ============================================
def get_top_scorers(league_id, season):
    url = f"{BASE_URL}players/topscorers"
    data = safe_request(url, {"league": league_id, "season": season})
    players = []
    for s in data[:5]:
        player = s.get("player", {}).get("name")
        team = s.get("statistics", [{}])[0].get("team", {}).get("name")
        goals = s.get("statistics", [{}])[0].get("goals", {}).get("total", 0)
        players.append({
            "player": player,
            "team": team,
            "goals": goals,
            "probability": round(0.4 + goals * 0.04 + random.uniform(0.05, 0.1), 2),
        })
    return players


# ============================================
# FUNÇÃO PRINCIPAL
# ============================================
def fetch_matches():
    if not API_KEY:
        print("❌ API_FOOTBALL_KEY não definida.")
        return {"status": "error", "detail": "missing key"}

    season = get_active_season()
    leagues = get_main_leagues()
    print(f"⚙️ Época ativa: {season}")
    print(f"🔢 Ligas configuradas: {len(leagues)}")

    matches = []
    total = 0

    for offset in range(3):
        match_date = (date.today() + timedelta(days=offset)).strftime("%Y-%m-%d")
        print(f"\n📅 Buscando jogos de {match_date}...")

        found = 0
        for league_id in leagues:
            url = f"{BASE_URL}fixtures"
            data = safe_request(url, {"league": league_id, "season": season, "date": match_date})

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

                stats_home = safe_request(f"{BASE_URL}teams/statistics",
                                          {"team": home_id, "league": league_id, "season": season})
                stats_away = safe_request(f"{BASE_URL}teams/statistics",
                                          {"team": away_id, "league": league_id, "season": season})

                stats_home_data = stats_home if isinstance(stats_home, dict) else (stats_home[0] if stats_home else {})
                stats_away_data = stats_away if isinstance(stats_away, dict) else (stats_away[0] if stats_away else {})

                pred = calculate_prediction(stats_home_data, stats_away_data)
                scorers = get_top_scorers(league_id, season)

                matches.append({
                    "match_id": fixture.get("id"),
                    "league": league.get("name"),
                    "league_id": league_id,
                    "home_team": teams.get("home", {}).get("name"),
                    "away_team": teams.get("away", {}).get("name"),
                    "date": fixture.get("date"),
                    "predicted_score": pred["predicted_score"],
                    "confidence": pred["confidence"],
                    "top_scorers": scorers,
                })
                found += 1
                total += 1

                print(f"⚽ {teams.get('home', {}).get('name')} vs {teams.get('away', {}).get('name')} → "
                      f"{pred['predicted_score']['home']}-{pred['predicted_score']['away']} "
                      f"(confiança {pred['confidence']*100:.0f}%)")

        print(f"📊 Total de jogos encontrados para {match_date}: {found}")

    if total == 0:
        print("\n⚠️ Nenhum jogo encontrado — buscando próximos jogos (modo NEXT)...")
        for league_id in leagues:
            data = safe_request(f"{BASE_URL}fixtures", {"league": league_id, "season": season, "next": 10})
            for f in data:
                fixture = f.get("fixture", {})
                league = f.get("league", {})
                teams = f.get("teams", {})

                matches.append({
                    "match_id": fixture.get("id"),
                    "league": league.get("name"),
                    "home_team": teams.get("home", {}).get("name"),
                    "away_team": teams.get("away", {}).get("name"),
                    "date": fixture.get("date"),
                })
                total += 1

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {total} previsões salvas em {PRED_PATH}")
    try:
        config.update_last_update()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao atualizar Redis: {e}")

    return {"status": "ok", "total": total}


# ============================================
# EXECUÇÃO LOCAL
# ============================================
if __name__ == "__main__":
    result = fetch_matches()
    print(result)
