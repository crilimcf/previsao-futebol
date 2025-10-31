import subprocess
import logging
import requests
import os
from datetime import datetime

# ======================================
# CONFIGURAÇÕES PRINCIPAIS
# ======================================
API_URL = "https://previsao-futebol.onrender.com/meta/update"
API_KEY = os.getenv("ENDPOINT_API_KEY", "d110d6f22b446c54deadcadef7b234f6966af678")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# ======================================
# GARANTIR EXISTÊNCIA DA PASTA DE LOGS
# ======================================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ======================================
# CONFIGURAÇÃO DE LOGGING
# ======================================
LOG_FILE = os.path.join(LOG_DIR, "run_daily.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("daily_update")

# ======================================
# FUNÇÃO TELEGRAM
# ======================================
def send_telegram_message(msg: str):
    """Envia logs ou status para o Telegram."""
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
        logger.info("📤 Mensagem enviada para o Telegram.")
    except Exception as e:
        logger.error(f"⚠️ Erro ao enviar mensagem para o Telegram: {e}")

# ======================================
# EXECUÇÃO PRINCIPAL
# ======================================
def main():
    logger.info("🚀 Início da atualização diária de previsões...")
    send_telegram_message("🚀 <b>Atualização diária iniciada.</b>")

    # 1️⃣ Executa o pipeline principal
    cmd = "python main.py --mode full"
    logger.info(f"🔧 Executando comando: {cmd}")
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        logger.error("❌ Pipeline diário falhou!")
        send_telegram_message("❌ <b>Falha na atualização diária!</b>")
        return

    logger.info("✅ Pipeline diário concluído com sucesso.")
    send_telegram_message("✅ <b>Pipeline diário concluído com sucesso.</b>")

    # 2️⃣ Atualiza o Redis via endpoint
    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        r = requests.post(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"🕒 Última atualização salva ({ts})")
            send_telegram_message(f"🕒 <b>Última atualização:</b> {ts}")
        else:
            logger.warning(f"⚠️ Falha ao atualizar Redis ({r.status_code}) → {r.text}")
            send_telegram_message(
                f"⚠️ <b>Falha ao chamar /meta/update</b>: {r.status_code}"
            )
    except Exception as e:
        logger.error(f"❌ Erro ao comunicar com a API: {e}")
        send_telegram_message(f"❌ <b>Erro ao comunicar com a API:</b> {e}")

    logger.info("🏁 Processo concluído.")
    send_telegram_message("🏁 <b>Processo diário concluído.</b>")

# ======================================
# EXECUÇÃO DIRETA
# ======================================
if __name__ == "__main__":
    main()
