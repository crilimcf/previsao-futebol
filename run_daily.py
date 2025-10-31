import subprocess
import logging
import requests
import os
from datetime import datetime

# ==============================
# CONFIGURAÇÕES
# ==============================
# O teu backend no Render:
API_URL = "https://previsao-futebol.onrender.com/meta/update"

# A mesma chave que já usaste no curl:
API_KEY = os.getenv("ENDPOINT_API_KEY", "d110d6f22b446c54deadcadef7b234f6966af678")

# (Opcional) Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# ==============================
# LOGGING
# ==============================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "run_daily.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("run_daily")


def send_telegram_message(msg: str):
    """Envia mensagem formatada para o Telegram (HTML)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        requests.post(url, data=payload, timeout=10)
        logger.info(f"📤 Notificação Telegram enviada.")
    except Exception as e:
        logger.error(f"⚠️ Falha ao enviar notificação Telegram: {e}")


def main():
    logging.info("🚀 Daily prediction update started...")
    send_telegram_message("🚀 <b>Atualização diária iniciada.</b>")

    # 1️⃣ Corre o pipeline principal
    cmd = "python main.py --mode full"
    logging.info(f"🔧 Executando comando: {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        logging.error("❌ Daily pipeline failed!")
        send_telegram_message("❌ <b>Falha na atualização diária!</b>")
        return

    logging.info("✅ Daily pipeline completed successfully.")
    send_telegram_message("✅ <b>Pipeline diário concluído com sucesso.</b>")

    # 2️⃣ Atualiza o Redis via endpoint do backend
    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        r = requests.post(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"🕒 Last update timestamp saved ({ts})")
            send_telegram_message(f"🕒 <b>Última atualização:</b> {ts}")
        else:
            logging.warning(f"⚠️ Falha ao salvar update ({r.status_code}) → {r.text}")
            send_telegram_message(f"⚠️ <b>Falha ao chamar /meta/update</b>: {r.status_code}")
    except Exception as e:
        logging.error(f"Erro ao chamar API: {e}")
        send_telegram_message(f"❌ <b>Erro ao chamar API:</b> {e}")


if __name__ == "__main__":
    main()
