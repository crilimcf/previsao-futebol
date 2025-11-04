import subprocess
import logging
import requests
import os
from datetime import datetime

API_URL = "https://previsao-futebol.onrender.com/meta/update"
API_KEY = os.getenv("ENDPOINT_API_KEY", "d110d6f22b446c54deadcadef7b234f6966af678")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")


def send_telegram_message(msg: str):
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


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logging.info("🚀 Início da atualização semanal...")
    send_telegram_message("🚀 <b>Atualização semanal iniciada</b>")

    cmd = "python -m src.predict"
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        logging.error("❌ Erro na execução do pipeline!")
        send_telegram_message("❌ <b>Falha na atualização semanal!</b>")
        return

    logging.info("✅ Pipeline concluído com sucesso.")
    send_telegram_message("✅ <b>Atualização semanal concluída.</b>")

    try:
        headers = {"Authorization": f"Bearer {API_KEY}"}
        r = requests.post(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"🕒 Timestamp atualizado ({ts})")
            send_telegram_message(f"🕒 <b>Última atualização:</b> {ts}")
        else:
            logging.warning(f"⚠️ Falha ao chamar /meta/update ({r.status_code}) → {r.text}")
    except Exception as e:
        logging.error(f"Erro ao chamar API: {e}")
        send_telegram_message(f"❌ <b>Erro ao chamar API:</b> {e}")


if __name__ == "__main__":
    main()
