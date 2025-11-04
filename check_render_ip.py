import requests
import socket
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

def get_public_ip():
    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text
        logging.info(f"🌍 IP público detectado: {ip}")
        return ip
    except Exception as e:
        logging.error(f"❌ Erro ao obter IP público: {e}")
        return None

def get_host_info():
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        logging.info(f"💻 Hostname: {hostname}")
        logging.info(f"🏠 IP local: {local_ip}")
    except Exception as e:
        logging.error(f"⚠️ Erro ao obter info local: {e}")

if __name__ == "__main__":
    logging.info("🔍 Verificando IP público do servidor Render...")
    get_host_info()
    get_public_ip()
