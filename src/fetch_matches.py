import os
import json
import time
import socket
import logging
import requests
from datetime import datetime, timedelta
from upstash_redis import Redis

# ✅ Forçar IPv4 para evitar IPv6 bloqueado pela API-Football
orig_getaddrinfo = socket.getaddrinfo
def force_ipv4(*args, **kwargs):
    return [info for info in orig_getaddrinfo(*args, **kwargs) if info[0] == socket.AF_INET]
socket.getaddrinfo = force_ipv4

# =============================
# 🔧 Configurações e variáveis
# =============================
API_KEY = os.getenv("API_FOOTBALL_KEY")
API_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
API_SEASON = os.getenv("API_FOOTBALL_SEASON", "2024")
WEBSCRAPING_AI_KEY = os.getenv("WEBSCRAPING_AI_KEY") or os.getenv("WEBSCRAPING_API_KEY")
REDIS_URL = os.getenv("REDIS_URL")
PREDICTIONS_PATH = os.getenv("PREDICTIONS_PATH", "data/predict/predictions.json")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =============================
# 🧱 Setup básico
# =============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# Redis Upstash
redis = None
if REDIS_URL:
    try:
        redis = Redis.from_url(REDIS_URL)
        logging.info("✅ Ligação HTTP com Upstash Redis estabelecida com sucesso!")
    except Exception as e:
        logging.warning(f"⚠️ Falha ao conectar no Redis: {e}")

# =============================
# 🌍 Função principal de request
# =============================
def _call_api_football(endpoint, params):
    """Chama a API-Football via HTTPS e faz fallback via WebScraping.AI se necessário."""
    url = f"{API_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"x-apisports-key": API_KEY}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if "errors" in data and data["errors"]:
                if "Ip" in data["errors"]:
                    logging.warning("⚠️ API-Football devolveu erro de IP — tentativa via WebScraping.AI")
                    return _call_via_webscraping(url)
            return data
        else:
            logging.warning(f"⚠️ API-Football respondeu com código {resp.status_code}")
            return {}
    except Exception as e:
        logging.error(f"❌ Erro ao chamar API-Football: {e}")
        return {}

# =============================
# 🕷️ Fallback via WebScraping.AI
# =============================
def _call_via_webscraping(target_url):
    if not WEBSCRAPING_AI_KEY:
        logging.warning("❌ WEBSCRAPING_AI_KEY não definida — não dá para contornar o IP.")
        return {}

    api_url = (
        f"https://api.webscraping.ai/html?api_key={WEBSCRAPING_AI_KEY}"
        f"&extractor=json&url={target_url}"
    )
    logging.info(f"🕷️ Chamando WebScraping.AI (modo JSON extraction): {target_url}")

    try:
        resp = requests.get(api_url, timeout=30)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return data
                else:
                    logging.warning("⚠️ WebScraping.AI devolveu conteúdo não JSON — não foi possível extrair dados.")
                    return {}
            except json.JSONDecodeError:
                logging.warning("⚠️ WebScraping.AI devolveu HTML em vez de JSON.")
                return {}
        else:
            logging.warning(f"⚠️ WebScraping.AI devolveu código {resp.status_code}")
            return {}
    except Exception as e:
        logging.error(f"❌ Erro ao usar WebScraping.AI: {e}")
        return {}

# =============================
# 📅 Função para buscar jogos
# =============================
def fetch_today_matches():
    leagues = [39, 140, 135, 61, 78, 94, 88, 2]  # Premier, LaLiga, Serie A, etc.
    today = datetime.utcnow().date()
    all_fixtures = []

    logging.info(f"🌍 Modo: API-Football (com fallback via WebScraping.AI)")
    logging.info(f"⚙️ Época ativa: {API_SEASON}")
    logging.info(f"🔢 Total de ligas a consultar: {len(leagues)}")

    for offset in range(3):  # próximos 3 dias
        match_date = today + timedelta(days=offset)
        logging.info(f"\n📅 Buscando jogos de {match_date}...")
        fixtures_for_day = []

        for league in leagues:
            params = {"league": league, "season": API_SEASON, "date": str(match_date)}
            data = _call_api_football("fixtures", params)
            if not data or not data.get("response"):
                continue

            for f in data["response"]:
                fixture = f.get("fixture", {})
                teams = f.get("teams", {})
                goals = f.get("goals", {})
                fixtures_for_day.append({
                    "date": fixture.get("date"),
                    "league": league,
                    "home": teams.get("home", {}).get("name"),
                    "away": teams.get("away", {}).get("name"),
                    "goals_home": goals.get("home"),
                    "goals_away": goals.get("away"),
                })

        logging.info(f"📊 Total de jogos encontrados para {match_date}: {len(fixtures_for_day)}")
        all_fixtures.extend(fixtures_for_day)

    # Salvar previsões
    os.makedirs(os.path.dirname(PREDICTIONS_PATH), exist_ok=True)
    with open(PREDICTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_fixtures, f, ensure_ascii=False, indent=2)
    logging.info(f"✅ {len(all_fixtures)} previsões salvas em {PREDICTIONS_PATH}")

    if redis:
        redis.set("latest_predictions", json.dumps(all_fixtures))
        logging.info(f"📋 Cobertura: {len(all_fixtures)}/{len(leagues)} ligas devolveram jogos.")

    return {"status": "ok", "total": len(all_fixtures), "coverage": f"{len(all_fixtures)}/{len(leagues)}"}


if __name__ == "__main__":
    res = fetch_today_matches()
    print(res)
