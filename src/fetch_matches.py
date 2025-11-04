import os
import json
import socket
import logging
import requests
from datetime import datetime
from upstash_redis import Redis

# ===========================================
# ✅ Forçar IPv4
# ===========================================
orig_getaddrinfo = socket.getaddrinfo
def force_ipv4(*args, **kwargs):
    return [info for info in orig_getaddrinfo(*args, **kwargs) if info[0] == socket.AF_INET]
socket.getaddrinfo = force_ipv4

# ===========================================
# 🔧 Configurações dinâmicas
# ===========================================
now = datetime.utcnow()
API_SEASON = str(now.year if now.month >= 8 else now.year - 1)  # muda em agosto

API_KEY = os.getenv("API_FOOTBALL_KEY") or os.getenv("APISPORTS_KEY")
API_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io").rstrip("/") + "/"
WEBSCRAPING_AI_KEY = os.getenv("WEBSCRAPING_AI_KEY") or os.getenv("WEBSCRAPING_API_KEY")

REDIS_URL = os.getenv("REDIS_URL")
REDIS_TOKEN = os.getenv("REDIS_TOKEN")

PREDICTIONS_PATH = "data/predict/predictions.json"
os.makedirs(os.path.dirname(PREDICTIONS_PATH), exist_ok=True)

# ===========================================
# 🧱 Logging
# ===========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ===========================================
# 🔌 Redis (compatível com Render / Upstash)
# ===========================================
redis = None
try:
    if REDIS_URL and REDIS_TOKEN:
        redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)
    elif REDIS_URL:
        redis = Redis.from_url(REDIS_URL)
    if redis:
        logging.info("✅ Ligação HTTP com Upstash Redis estabelecida com sucesso!")
    else:
        logging.warning("⚠️ Redis não configurado — variáveis REDIS_URL ou REDIS_TOKEN ausentes.")
except Exception as e:
    logging.warning(f"⚠️ Falha ao conectar no Redis: {e}")

# ===========================================
# 🌍 Função de request à API-Football
# ===========================================
def _call_api_football(endpoint, params):
    if not API_KEY:
        logging.error("❌ API-Football KEY não definida nas variáveis de ambiente.")
        return {}

    url = f"{API_BASE}{endpoint.lstrip('/')}"
    headers = {"x-apisports-key": API_KEY}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            if "errors" in data and data["errors"]:
                if "Ip" in data["errors"]:
                    logging.warning("⚠️ IP não autorizado na API-Football. Verifica whitelist no painel API-Sports.")
            return data
        else:
            logging.warning(f"⚠️ API-Football respondeu {resp.status_code}: {resp.text}")
            return {}
    except requests.exceptions.Timeout:
        logging.error("⏳ Timeout na chamada da API-Football.")
    except Exception as e:
        logging.error(f"❌ Erro ao chamar API-Football: {e}")
    return {}

# ===========================================
# 📅 Busca próximos jogos (automático, com fallback de temporada)
# ===========================================
def fetch_today_matches():
    logging.info(f"🌍 API-Football ativo | Época {API_SEASON}")
    all_fixtures = []

    # Ajuste automático da época
    current_year = datetime.utcnow().year
    season = API_SEASON
    if int(API_SEASON) > current_year:
        season = str(current_year)
    elif int(API_SEASON) < 2024:
        season = "2024"

    # Busca global dos próximos jogos
    params = {"next": 50, "season": season}
    logging.info(f"🔎 A buscar próximos 50 jogos (época {season})...")

    data = _call_api_football("fixtures", params)
    if not data or not data.get("response"):
        logging.warning("📭 Nenhum jogo retornado pela API-Football.")
    else:
        for f in data["response"]:
            fixture = f.get("fixture", {})
            league = f.get("league", {})
            teams = f.get("teams", {})
            goals = f.get("goals", {})

            all_fixtures.append({
                "fixture_id": fixture.get("id"),
                "league_id": league.get("id"),
                "league_name": league.get("name"),
                "country": league.get("country"),
                "date": fixture.get("date"),
                "home_team": teams.get("home", {}).get("name"),
                "away_team": teams.get("away", {}).get("name"),
                "home_logo": teams.get("home", {}).get("logo"),
                "away_logo": teams.get("away", {}).get("logo"),
                "predicted_score": {"home": goals.get("home"), "away": goals.get("away")},
                "confidence": 0.0,
            })

    logging.info(f"📊 {len(all_fixtures)} jogos processados pela API-Football.")

    # ===========================================
    # 💾 Gravar ficheiro local com segurança
    # ===========================================
    try:
        os.makedirs(os.path.dirname(PREDICTIONS_PATH), exist_ok=True)
        temp_path = PREDICTIONS_PATH + ".tmp"

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(all_fixtures, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, PREDICTIONS_PATH)
        logging.info(f"✅ {len(all_fixtures)} jogos gravados em {PREDICTIONS_PATH}")
    except Exception as e:
        logging.error(f"❌ Erro ao gravar ficheiro de previsões: {e}")

    # ===========================================
    # 🔁 Atualizar Redis
    # ===========================================
    if redis:
        try:
            redis.set("latest_predictions", json.dumps(all_fixtures))
            redis.set("meta:last_update", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            redis.set("meta:total_matches", len(all_fixtures))
            redis.set("meta:season", season)
            logging.info("📦 Redis atualizado com previsões atuais e metadados.")
        except Exception as e:
            logging.warning(f"⚠️ Erro ao atualizar Redis: {e}")

    return {
        "status": "ok",
        "total": len(all_fixtures),
        "season": season,
        "path": PREDICTIONS_PATH,
    }

# ===========================================
# 🚀 Execução direta (para testes locais)
# ===========================================
if __name__ == "__main__":
    try:
        ip = requests.get("https://api.ipify.org").text
        logging.info(f"🌐 IP público atual: {ip}")
    except Exception:
        logging.warning("⚠️ Não foi possível obter o IP público.")

    res = fetch_today_matches()
    print(res)
