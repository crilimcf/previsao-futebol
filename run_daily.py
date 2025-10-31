import subprocess
import logging
import requests
import os
from datetime import datetime

# ==============================
# CONFIGURAÇÕES
# ==============================
# URL do teu backend no Render:
API_URL = "https://previsao-futebol.onrender.com/meta/update"

# A mesma chave usada no curl (ENDPOINT_API_KEY)
API_KEY = os.getenv("ENDPOINT_API_KEY", "d110d6f22b446c54deadcadef7b234f6966af678")

# Telegram (opcional, mas recomendado)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

# Caminho do log local
LOG_FILE = "logs/daily_update.log"
os.makedirs("logs", exist_ok=True)


# ==============================
# FUNÇÃO → Envia mensagem Telegram
# ==============================
def send_telegram_message(msg: str):
    """Envia logs e notificações para o Telegram (opcional)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        logging.error(f"Telegram error: {e}")


# ==============================
# FUNÇÃO PRINCIPAL
# ==============================
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    logging.info("🚀 Daily prediction update started...")
    send_telegram_message("🚀 <b>Atualização diária iniciada.</b>")

    # 1️⃣ Executa o pipeline principal (gera previsões)
    cmd = "python main.py --mode full"
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        logging.error("❌ Daily pipeline failed!")
        send_telegram_message("❌ <b>Falha na atualização diária!</b>")
        return

    logging.info("✅ Daily pipeline completed successfully.")
    send_telegram_message("✅ <b>Pipeline diário concluído.</b>")

    # 2️⃣ Atualiza o backend (Redis no Render)
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
        logging.error(f"❌ Erro ao chamar API: {e}")
        send_telegram_message(f"❌ <b>Erro ao chamar API:</b> {e}")


# ==============================
# EXECUÇÃO DIRETA
# ==============================
if __name__ == "__main__":
    main()
