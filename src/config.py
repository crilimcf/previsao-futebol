# src/config.py
import os
import logging
from typing import Optional, Any

logger = logging.getLogger("config")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# =========================
# Chaves/constantes gerais
# =========================
ENDPOINT_API_KEY = os.getenv("ENDPOINT_API_KEY", "")

# Caminhos de dados
PREDICTIONS_DIR = os.getenv("PREDICTIONS_DIR", "data/predict")
PREDICTIONS_PATH = os.path.join(PREDICTIONS_DIR, "predictions.json")
PREDICTIONS_HISTORY_PATH = os.path.join(PREDICTIONS_DIR, "predictions_history.json")

# Chave de last-update (podes alterar via env)
LAST_UPDATE_KEY = os.getenv("LAST_UPDATE_KEY", "football_predictions_last_update")

# =========================
# Redis (suporta 2 modos)
# =========================
redis_client: Any = None
_client_mode = "none"

# Preferência 1: Upstash REST (https:// + token)
REST_URL = (
    os.getenv("UPSTASH_REDIS_REST_URL")
    or os.getenv("REDIS_REST_URL")
    or (os.getenv("REDIS_URL") if (os.getenv("REDIS_URL") or "").startswith("https://") else None)
)
REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("REDIS_TOKEN")

# Preferência 2: Dialecto Redis (redis:// ou rediss://)
CACHE_URL = os.getenv("REDIS_URL") if (os.getenv("REDIS_URL") or "").startswith(("redis://", "rediss://")) else None
CACHE_USERNAME = os.getenv("REDIS_USERNAME") or os.getenv("UPSTASH_USERNAME") or "default"
CACHE_PASSWORD = os.getenv("REDIS_PASSWORD") or os.getenv("REDIS_TOKEN")  # Upstash TLS usa o token como password

try:
    if REST_URL and REST_TOKEN:
        # Upstash REST
        try:
            from upstash_redis import Redis as UpstashRedis  # pip install upstash-redis
            redis_client = UpstashRedis(url=REST_URL, token=REST_TOKEN)
            _client_mode = "upstash-rest"
            logger.info("✅ Ligação HTTP com Upstash Redis (REST) configurada.")
        except Exception as e:
            logger.warning(f"⚠️ Falha a inicializar Upstash REST: {e}")

    if redis_client is None and CACHE_URL:
        # redis-py (redis:// | rediss://)
        try:
            import redis  # pip install redis
            # Se o URL já tiver credenciais embebidas, from_url trata disso.
            # Caso contrário, passamos username/password.
            if "@" in CACHE_URL or (":" in CACHE_URL.split("://", 1)[1].split("/", 1)[0]):
                r = redis.from_url(CACHE_URL, decode_responses=True)
            else:
                r = redis.from_url(CACHE_URL, username=CACHE_USERNAME, password=CACHE_PASSWORD, decode_responses=True)
            # ping rápido
            r.ping()
            redis_client = r
            _client_mode = "redis-py"
            logger.info("✅ Ligação Redis (redis/ rediss) configurada.")
        except Exception as e:
            logger.warning(f"⚠️ Falha a inicializar redis-py: {e}")

    if redis_client is None:
        logger.warning("⚠️ Redis não configurado — variables REST_URL/REST_TOKEN ou REDIS_URL em falta.")
except Exception as e:
    logger.warning(f"⚠️ Erro genérico na configuração de Redis: {e}")


# =========================
# Helpers de Redis
# =========================
def redis_set(key: str, value: str, ex: Optional[int] = None) -> bool:
    if not redis_client:
        return False

    try:
        if _client_mode == "upstash-rest":
            # upstash-redis REST usa 'ex' como kwargs em set
            if ex:
                redis_client.set(key, value, ex=ex)
            else:
                redis_client.set(key, value)
            return True
        elif _client_mode == "redis-py":
            redis_client.set(name=key, value=value, ex=ex)
            return True
    except Exception as e:
        logger.warning(f"⚠️ Falha redis_set({key}): {e}")
    return False


def redis_get(key: str) -> Optional[str]:
    if not redis_client:
        return None
    try:
        if _client_mode in ("upstash-rest", "redis-py"):
            return redis_client.get(key)
    except Exception as e:
        logger.warning(f"⚠️ Falha redis_get({key}): {e}")
    return None
