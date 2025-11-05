# src/config.py
import os
import logging
import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# --------- Chaves & defaults ----------
ENDPOINT_API_KEY = os.getenv("ENDPOINT_API_KEY", "")
LAST_UPDATE_KEY = os.getenv("LAST_UPDATE_KEY", "football_predictions_last_update")

# --------- Detectar backends Redis ----------
REST_URL = (
    os.getenv("UPSTASH_REDIS_REST_URL")
    or os.getenv("UPSTASH_REDIS_URL")  # compat legacy
    or (os.getenv("REDIS_URL") if (os.getenv("REDIS_URL") or "").startswith("https://") else None)
)
REST_TOKEN = (
    os.getenv("UPSTASH_REDIS_REST_TOKEN")
    or os.getenv("UPSTASH_REDIS_TOKEN")  # compat legacy
    or os.getenv("REDIS_TOKEN")
)

SOCKET_URL = None
_raw_ru = os.getenv("REDIS_URL", "")
if _raw_ru.startswith("redis://") or _raw_ru.startswith("rediss://"):
    SOCKET_URL = _raw_ru

redis_client = None
_used_backend = None

# --------- Preferir REST (Upstash HTTP) ----------
if REST_URL and REST_TOKEN:
    try:
        from upstash_redis import Redis as UpstashRedis

        class SimpleRedisAdapter:
            def __init__(self, url: str, token: str):
                self._c = UpstashRedis(url=url, token=token)

            def get(self, key: str) -> Optional[str]:
                v = self._c.get(key)
                if isinstance(v, bytes):
                    try:
                        return v.decode("utf-8")
                    except Exception:
                        return None
                return v

            def set(self, key: str, value: str, ex: Optional[int] = None):
                # Upstash aceita ex (segundos)
                return self._c.set(key, value, ex=ex)

            def delete(self, key: str):
                try:
                    return self._c.delete(key)
                except Exception:
                    return None

            # para compat com algum código que chama .info()
            def info(self):
                return {}

        redis_client = SimpleRedisAdapter(REST_URL, REST_TOKEN)
        _used_backend = "rest"
        logger.info("✅ Ligação HTTP com Upstash Redis (REST) configurada.")
    except Exception as e:
        logger.error(f"❌ Falha a inicializar Upstash REST: {e}")

# --------- Fallback: socket (apenas se REST falhar/ausente) ----------
if not redis_client and SOCKET_URL:
    try:
        import redis as redis_py  # redis-py
        # Conexão simples; para rediss:// o token pode vir embutido no URL
        redis_client = redis_py.Redis.from_url(SOCKET_URL, decode_responses=True)
        _used_backend = "socket"
        logger.info("✅ Ligação Redis por socket configurada.")
    except Exception as e:
        logger.warning(f"⚠️ Falha a inicializar Redis socket: {e}")

# --------- Sem Redis ----------
if not redis_client:
    logger.warning("⚠️ Redis não configurado — defina UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN (recomendado).")

# --------- Helpers ----------
def redis_get(key: str) -> Optional[str]:
    try:
        return redis_client.get(key) if redis_client else None
    except Exception as e:
        logger.warning(f"Redis GET falhou: {e}")
        return None

def redis_set(key: str, value: str, ex: Optional[int] = None):
    try:
        if redis_client:
            return redis_client.set(key, value, ex=ex)
    except Exception as e:
        logger.warning(f"Redis SET falhou: {e}")
    return None

def update_last_update() -> str:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # manter 7 dias de TTL
    redis_set(LAST_UPDATE_KEY, ts, ex=7 * 24 * 3600)
    return ts
