import subprocess
import logging
import requests
import os
from datetime import datetime

# ======================================
# CONFIGURAÇÕES PRINCIPAIS
# ======================================
# URL do backend (Render)
API_URL = "https://previsao-futebol.onrender.com/meta/update"

# Chave de autenticação (mesma que usas no curl)
API_KEY = os.getenv("ENDPOINT_API_KEY", "d110d6f22b446c54deadcadef7b234f6966af678")

# Telegram (opcional)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# ======================================
# LOGGING
# ======================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/run_daily.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("daily_update")

# ======================================
# FUNÇÕES AUXILIARES
# ======================================
def send_telegram_message(msg: str):
    """Envia mensagens para o Telegram (se configurado)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        logger.error(f"⚠️ Erro ao enviar mensagem Telegram: {e}")

# ======================================
# PIPELINE DIÁRIO
# ======================================
def main():
    logger.info("🚀 Iniciando atualização diária de previsões...")
    send_telegram_message("🚀 <b>Atualização diária iniciada.</b>")

    # 1️⃣ Corre o pipeline principal (gera novas previsões)
    cmd = "python main.py --mode full"
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        logger.error("❌ Erro ao executar pipeline diário.")
        send_telegram_message("❌ <b>Falha na execução do pipeline diário.</b>")
        return

    logger.info("✅ Pipeline diário concluído com sucesso.")
    send_telegram_message("✅ <b>Pipeline diário concluído com sucesso.</b>")

    # 2️⃣ Atualiza timestamp via backend
    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        r = requests.post(API_URL, headers=headers, timeout=15)

        if r.status_code == 200:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"🕒 Timestamp atualizado com sucesso ({ts})")
            send_telegram_message(f"🕒 <b>Última atualização:</b> {ts}")
        else:
            logger.warning(f"⚠️ Falha ao atualizar Redis ({r.status_code}) → {r.text}")
            send_telegram_message(f"⚠️ <b>Falha ao chamar /meta/update:</b> {r.status_code}")
    except Exception as e:
        logger.error(f"❌ Erro ao contactar API: {e}")
        send_telegram_message(f"❌ <b>Erro ao contactar API:</b> {e}")


if __name__ == "__main__":
    main()
