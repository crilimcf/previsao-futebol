import os
import json
import socket
import logging
import requests
from datetime import datetime, timedelta
from upstash_redis import Redis

# ✅ Forçar IPv4
orig_getaddrinfo = socket.getaddrinfo
def force_ipv4(*args, **kwargs):
    return [info for info in orig_getaddrinfo(*args, **kwargs) if info[0] == socket.AF_INET]
socket.getaddrinfo = force_ipv4

# =============================
# 🔧 Configurações
# =============================
API_KEY = os.getenv("API_FOOTBALL_KEY")
API_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
API_SEASON = os.getenv("API_FOOTBALL_SEASON", "2024")
WEBSCRAPING_AI_KEY = os.getenv("WEBSCRAPING_AI_KEY") or os.getenv("WEBSCRAPING_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")

PREDICTIONS_PATH = "data/predict/predictions.json"  # 🔹 caminho fixo e garantido
os.makedirs(os.path.dirname(PREDICTIONS_PATH), exist_ok=True)

# =============================
# 🧱 Logging
# =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# =============================
# 🔌 Redis
# =============================
redis = None
if REDIS_URL:
    try:
        redis = Redis.from_url(REDIS_URL)
        logging.info("✅ Ligação HTTP com Upstash Redis estabelecida com sucesso!")
    except Exception as e:
        logging.warning(f"⚠️ Falha ao conectar no Redis: {e}")

# =============================
# 🌍 Função de request à API-Football
# =============================
def _call_api_football(endpoint, params):
    url = f"{API_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"x-apisports-key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if "errors" in data and data["errors"]:
                if "Ip" in data["errors"]:
                    logging.warning("⚠️ IP não autorizado na API-Football.")
            return data
        else:
            logging.warning(f"⚠️ API-Football respondeu {resp.status_code}")
            return {}
    except Exception as e:
        logging.error(f"❌ Erro ao chamar API-Football: {e}")
        return {}

# =============================
# 📅 Busca jogos (3 dias)
# =============================
def fetch_today_matches():
    leagues = [39, 140, 135, 61, 78, 94, 88, 2]  # Premier, LaLiga, SerieA, etc.
    today = datetime.utcnow().date()
    all_fixtures = []

    logging.info(f"🌍 API-Football ativo | Época {API_SEASON}")
    logging.info(f"🔢 Total ligas: {len(leagues)}")

    for offset in range(3):
        match_date = today + timedelta(days=offset)
        fixtures_for_day = []

        logging.info(f"\n📅 Procurando jogos de {match_date}...")
        for league in leagues:
            params = {"league": league, "season": API_SEASON, "date": str(match_date)}
            data = _call_api_football("fixtures", params)
            if not data or not data.get("response"):
                continue

            for f in data["response"]:
                fixture = f.get("fixture", {})
                league_info = f.get("league", {})
                teams = f.get("teams", {})
                goals = f.get("goals", {})

                fixtures_for_day.append({
                    "league_id": league_info.get("id"),
                    "league_name": league_info.get("name"),
                    "league_country": league_info.get("country"),
                    "date": fixture.get("date"),
                    "home_team": teams.get("home", {}).get("name"),
                    "away_team": teams.get("away", {}).get("name"),
                    "home_logo": teams.get("home", {}).get("logo"),
                    "away_logo": teams.get("away", {}).get("logo"),
                    "predicted_score": {"home": goals.get("home"), "away": goals.get("away")},
                    "confidence": 0.0,  # reservado para IA futuramente
                })

        logging.info(f"📊 {len(fixtures_for_day)} jogos para {match_date}")
        all_fixtures.extend(fixtures_for_day)

    # =============================
    # 💾 Gravar ficheiro
    # =============================
    with open(PREDICTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_fixtures, f, ensure_ascii=False, indent=2)
    logging.info(f"✅ {len(all_fixtures)} jogos gravados em {PREDICTIONS_PATH}")

    # Redis
    if redis:
        redis.set("latest_predictions", json.dumps(all_fixtures))
        logging.info("📦 Redis atualizado com previsões atuais")

    return {
        "status": "ok",
        "total": len(all_fixtures),
        "coverage": f"{len(all_fixtures)}/{len(leagues)}",
        "path": PREDICTIONS_PATH,
    }


if __name__ == "__main__":
    res = fetch_today_matches()
    print(res)
