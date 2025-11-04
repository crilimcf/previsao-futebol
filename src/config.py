import os
import logging
from upstash_redis import Redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("config")

# Redis (Upstash)
REDIS_URL = os.getenv("REDIS_URL")
REDIS_TOKEN = os.getenv("REDIS_TOKEN")

redis_client = None
if REDIS_URL and REDIS_TOKEN:
    try:
        redis_client = Redis(url=REDIS_URL, token=REDIS_TOKEN)
        logger.info("✅ Ligação Redis OK.")
    except Exception as e:
        logger.warning(f"⚠️ Falha ao conectar ao Redis: {e}")
else:
    logger.warning("⚠️ Variáveis REDIS_URL ou REDIS_TOKEN ausentes.")


def update_last_update():
    """Atualiza a data da última previsão no Redis."""
    import datetime
    if not redis_client:
        return
    try:
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        redis_client.set("football_predictions_last_update", ts)
        logger.info(f"🕒 Última atualização registada no Redis ({ts})")
    except Exception as e:
        logger.error(f"⚠️ Falha ao atualizar timestamp: {e}")
