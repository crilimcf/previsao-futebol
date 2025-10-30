import os
from datetime import datetime
from dotenv import load_dotenv
from upstash_redis import Redis

load_dotenv()

LAST_UPDATE_KEY = "football_predictions_last_update"

# --- Configuração Upstash Redis manual ---
REDIS_URL = "https://dear-squid-35681.upstash.io"
REDIS_TOKEN = "AYthAAIncDFjZDJkNDY2ZGRlOTk0NTE2ODA3MTJkMzRjNGZkZmUyNXAxMzU2ODE"

redis_client = None

try:
    redis_client = Redis(url=REDIS_URL, token=REDIS_TOKEN)
    # Teste rápido
    redis_client.set("test_key", "ok")
    print("✅ Ligação HTTP com Upstash Redis estabelecida com sucesso!")
except Exception as e:
    print(f"❌ Erro ao conectar ao Upstash Redis: {e}")
    redis_client = None


def update_last_update():
    """Atualiza a chave de último update no Redis."""
    if not redis_client:
        return {"status": "redis_disabled"}
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        redis_client.set(LAST_UPDATE_KEY, ts)
        return {"status": "ok", "last_update": ts}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
