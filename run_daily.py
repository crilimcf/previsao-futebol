from dotenv import load_dotenv
load_dotenv()
import subprocess
import logging
import requests
import os
from datetime import datetime

# ==============================
# CONFIGURAÇÕES
# ==============================
# URL do backend (Render)
API_URL = "https://previsao-futebol.onrender.com/meta/update"

# Chave de autenticação (do .env, GitHub Secrets ou Render Env)
API_KEY = os.getenv("ENDPOINT_API_KEY", "d110d6f22b446c54deadcadef7b234f6966af678")

# Telegram (opcional)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# ==============================
# LOGGING (compatível com GitHub Actions)
# ==============================
LOG_DIR = "logs"
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    log_handlers = [
        logging.FileHandler(os.path.join(LOG_DIR, "run_daily.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
except Exception:
    # Caso não haja permissão (ex: GitHub Actions), só envia para stdout
    log_handlers = [logging.StreamHandler()]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=log_handlers
)
logger = logging.getLogger("run_daily")


# ==============================
# FUNÇÕES AUXILIARES
# ==============================
def send_telegram_message(msg: str):
    """Envia mensagem para o Telegram (HTML)."""
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
        logger.info("📤 Notificação Telegram enviada.")
    except Exception as e:
        logger.error(f"⚠️ Falha ao enviar notificação Telegram: {e}")


# ==============================
# EXECUÇÃO PRINCIPAL
# ==============================
def main():
    logger.info("🚀 Atualização diária iniciada...")
    send_telegram_message("🚀 <b>Atualização diária iniciada.</b>")

    # 1️⃣ Executa o pipeline principal
    cmd = "python main.py --mode full"
    logger.info(f"🔧 Executando: {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        logger.error("❌ Pipeline diário falhou!")
        send_telegram_message("❌ <b>Falha na atualização diária!</b>")
        return

    logger.info("✅ Pipeline diário concluído com sucesso.")
    send_telegram_message("✅ <b>Pipeline diário concluído com sucesso.</b>")

    # 2️⃣ Atualiza Redis via endpoint backend
    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        r = requests.post(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"🕒 Última atualização salva ({ts})")
            send_telegram_message(f"🕒 <b>Última atualização:</b> {ts}")
        else:
            logger.warning(f"⚠️ Falha ao chamar /meta/update ({r.status_code}) → {r.text}")
            send_telegram_message(f"⚠️ <b>Falha ao chamar /meta/update</b>: {r.status_code}")
    except Exception as e:
        logger.error(f"❌ Erro ao chamar API: {e}")
        send_telegram_message(f"❌ <b>Erro ao chamar API:</b> {e}")


# ==============================
# ENTRY POINT
# ==============================
if __name__ == "__main__":
    main()
