from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from src.api_routes import health, predict
from src import config
from src.fetch_matches import fetch_today_matches  # 👈 Importa a função que busca os jogos
import os
import json
import threading
import time
import logging
import requests

# ======================================
# CONFIGURAÇÃO DE LOGGING
# ======================================
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "updates.log")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("football_api")

# ======================================
# TELEGRAM CONFIG
# ======================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")

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

# ======================================
# Caminhos principais
# ======================================
PREDICTIONS_PATH = os.path.abspath(os.getenv("PREDICTIONS_PATH", "data/predict/predictions.json"))
WATCHED_FILES = [
    "data/stats/prediction_stats.json",
    "data/predict/predictions.json",
]

# ======================================
# Lifespan – Carrega previsões ao iniciar
# ======================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with open(PREDICTIONS_PATH, encoding="utf-8") as f:
            app.state.predictions = json.load(f)
            msg = f"✅ <b>{len(app.state.predictions)} previsões carregadas</b> com sucesso."
            print(msg)
            logger.info(msg)
            send_telegram_message(msg)
    except FileNotFoundError:
        app.state.predictions = []
        msg = "⚠️ <b>Ficheiro de previsões não encontrado</b>"
        print(msg)
        logger.warning(msg)
        send_telegram_message(msg)
    except Exception as e:
        app.state.predictions = []
        msg = f"❌ <b>Erro ao carregar previsões:</b>\n<i>{e}</i>"
        print(msg)
        logger.error(msg)
        send_telegram_message(msg)

    logger.info("🚀 API inicializada com agendamento automático ativo (00:30).")
    send_telegram_message("🚀 <b>API Football Prediction</b> iniciada com agendamento automático <b>(00:30)</b>.")
    yield
    logger.info("🛑 API encerrada.")
    send_telegram_message("🛑 <b>API encerrada.</b>")

# ======================================
# Atualização automática diária (00:30)
# ======================================
scheduler = BackgroundScheduler(timezone="Europe/Lisbon")

def daily_update_job():
    """Executa atualização automática no Redis + fetch dos jogos às 00:30."""
    try:
        # 1️⃣ Buscar jogos reais
        result = fetch_today_matches()
        total = result.get("total", 0)
        
        # 2️⃣ Atualizar timestamp no Redis
        if config.redis_client:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            config.redis_client.set(config.LAST_UPDATE_KEY, now_str)
            msg = (
                f"🌙 <b>Atualização automática concluída</b>\n"
                f"🕒 <code>{now_str}</code>\n"
                f"⚽ <b>{total} jogos</b> atualizados com sucesso!"
            )
        else:
            msg = "⚠️ <b>Redis desativado</b> — atualização automática ignorada."

        print(msg)
        logger.info(msg)
        send_telegram_message(msg)

    except Exception as e:
        msg = f"⚠️ <b>Erro ao executar atualização automática:</b>\n<i>{e}</i>"
        print(msg)
        logger.error(msg)
        send_telegram_message(msg)

# Agenda a tarefa diária
scheduler.add_job(daily_update_job, "cron", hour=0, minute=30)
scheduler.start()
logger.info("🕒 Agendamento diário configurado para 00:30.")

# ======================================
# Monitor automático de ficheiros
# ======================================
def watch_files():
    """Monitoriza ficheiros e atualiza o Redis ao detetar alterações."""
    last_mod_times = {f: None for f in WATCHED_FILES}
    while True:
        for fpath in WATCHED_FILES:
            if os.path.exists(fpath):
                mod_time = os.path.getmtime(fpath)
                if last_mod_times[fpath] != mod_time:
                    last_mod_times[fpath] = mod_time
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if config.redis_client:
                        config.redis_client.set(config.LAST_UPDATE_KEY, ts)
                        msg = (
                            f"🔁 <b>Ficheiro atualizado:</b>\n"
                            f"📂 <code>{fpath}</code>\n"
                            f"🕒 <code>{ts}</code>"
                        )
                        print(msg)
                        logger.info(msg)
                        send_telegram_message(msg)
        time.sleep(10)

# Inicia o monitor de ficheiros em background
threading.Thread(target=watch_files, daemon=True).start()
logger.info("👀 Monitor de ficheiros iniciado.")

# ======================================
# Criação da aplicação FastAPI
# ======================================
is_dev = os.getenv("ENV", "dev") == "dev"

app = FastAPI(
    title="Football Prediction API",
    description="API for football match predictions",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if is_dev else None,
    redoc_url="/redoc" if is_dev else None,
    openapi_url="/openapi.json" if is_dev else None,
)

# ======================================
# Configuração CORS
# ======================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://previsao-futebol.vercel.app",
        "https://previsao-futebol-6q2ejj6lc-carlos-projects-e7f825c1.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================
# Inclusão das rotas
# ======================================
app.include_router(health.router)
app.include_router(predict.router)

# ======================================
# Rota raiz opcional
# ======================================
@app.get("/")
def home():
    last_update = (
        config.redis_client.get(config.LAST_UPDATE_KEY)
        if config.redis_client else "N/A"
    )
    return {
        "message": "API Football Prediction está ativa 🚀",
        "last_update": last_update,
    }
