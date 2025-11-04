import os
import json
import socket
import logging
import requests
from datetime import datetime
from upstash_redis import Redis

# ===========================================
# ✅ Forçar IPv4 (evita falhas no Render)
# ===========================================
orig_getaddrinfo = socket.getaddrinfo
def force_ipv4(*args, **kwargs):
    return [info for info in orig_getaddrinfo(*args, **kwargs) if info[0] == socket.AF_INET]
socket.getaddrinfo = force_ipv4

# ===========================================
# 🔧 Configurações principais
# ===========================================
API_KEY = os.getenv("API_FOOTBALL_KEY") or os.getenv("APISPORTS_KEY")
API_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io")
API_BASE = API_BASE.rstrip("/") + "/"  # garante barra final
API_SEASON = os.getenv("API_FOOTBALL_SEASON", str(datetime.utcnow().year))
REDIS_URL = os.getenv("REDIS_URL")

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
# 🔌 Conexão Redis (opcional)
# ===========================================
redis = None
if REDIS_URL:
    try:
        if hasattr(Redis, "from_url"):
            redis = Redis.from_url(REDIS_URL)
        else:
            redis = Redis(url=REDIS_URL)
        logging.info("✅ Ligação HTTP com Upstash Redis estabelecida com sucesso!")
    except Exception as e:
        logging.warning(f"⚠️ Falha ao conectar no Redis: {e}")

# ===========================================
# 🌍 Função genérica para chamada à API-Football
# ===========================================
def _call_api_football(endpoint, params):
    if not API_KEY:
        logging.error("❌ API-Football KEY não definida nas variáveis de ambiente.")
        return {}

    url = f"{API_BASE}{endpoint.lstrip('/')}"
    headers = {"x-apisports-key": API_KEY}

    logging.info(f"🌐 A chamar API-Football: {url} | params={params}")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("errors"):
                if "Ip" in data["errors"]:
                    logging.warning("⚠️ IP não autorizado na API-Football. Verifica whitelist no painel da API.")
            return data
        else:
            logging.warning(f"⚠️ API-Football respondeu {resp.status_code}: {resp.text}")
    except requests.exceptions.Timeout:
        logging.error("⏳ Timeout na chamada da API-Football.")
    except Exception as e:
        logging.error(f"❌ Erro ao chamar API-Football: {e}")
    return {}

# ===========================================
# ⚽ Busca automática dos próximos jogos (next=50)
# ===========================================
def fetch_today_matches():
    """
    Busca os próximos 50 jogos reais em todas as ligas disponíveis.
    """
    all_fixtures = []
    params = {"next": 50, "season": API_SEASON}

    logging.info(f"🌍 API-Football ativo | Época {API_SEASON}")
    logging.info("🔎 A buscar próximos 50 jogos (globais)...")

    data = _call_api_football("fixtures", params)

    if not data or not data.get("response"):
        logging.warning("📭 Nenhum jogo retornado pela API-Football.")
    else:
        for f in data["response"]:
            fixture = f.get("fixture", {})
            league_info = f.get("league", {})
            teams = f.get("teams", {})
            goals = f.get("goals", {})

            all_fixtures.append({
                "league_id": league_info.get("id"),
                "league_name": league_info.get("name"),
                "league_country": league_info.get("country"),
                "date": fixture.get("date"),
                "venue": fixture.get("venue", {}).get("name"),
                "home_team": teams.get("home", {}).get("name"),
                "away_team": teams.get("away", {}).get("name"),
                "home_logo": teams.get("home", {}).get("logo"),
                "away_logo": teams.get("away", {}).get("logo"),
                "predicted_score": {"home": goals.get("home"), "away": goals.get("away")},
                "confidence": 0.0,  # reservado para IA futura
            })

        logging.info(f"📊 {len(all_fixtures)} jogos encontrados nos próximos dias.")

    # ===========================================
    # 💾 Gravar ficheiro local
    # ===========================================
    with open(PREDICTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_fixtures, f, ensure_ascii=False, indent=2)

    logging.info(f"✅ {len(all_fixtures)} jogos gravados em {PREDICTIONS_PATH}")

    # ===========================================
    # 🔁 Atualizar Redis (opcional)
    # ===========================================
    if redis:
        try:
            redis.set("latest_predictions", json.dumps(all_fixtures))
            logging.info("📦 Redis atualizado com previsões atuais.")
        except Exception as e:
            logging.warning(f"⚠️ Erro ao atualizar Redis: {e}")

    return {
        "status": "ok",
        "total": len(all_fixtures),
        "path": PREDICTIONS_PATH,
    }

# ===========================================
# 🚀 Execução direta (para teste local)
# ===========================================
if __name__ == "__main__":
    res = fetch_today_matches()
    print(res)
