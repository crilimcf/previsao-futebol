# ============================================================
# src/main.py
# ============================================================
import os
import datetime
import logging
import typer
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src import config

# 👉 routers
from src.api_routes import health as health_routes
from src.api_routes import predict as predict_routes
from src.api_routes import meta as meta_routes  # <— NOVO

# ============================================================
# ⚙️ LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# 🎯 CLI (Typer)
# ============================================================
app = typer.Typer(help="Football Prediction Project CLI")

@app.command()
def train():
    from src.train import train_model as train_main
    logger.info("🚀 Training models…")
    train_main()

@app.command()
def predict():
    from src.predict import main as predict_main
    logger.info("⚽ Generating predictions…")
    predict_main()

@app.command()
def validate():
    from scripts.validate_historical_matches import validate_historical_matches as validate_main
    logger.info("🧩 Validating historical match data…")
    validate_main()

def version_callback(value: bool):
    if value:
        typer.echo("Football Prediction CLI v1.0")
        raise typer.Exit()

@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Mostra a versão do CLI"
    )
):
    pass

# ============================================================
# 🌍 FASTAPI APP
# ============================================================
api = FastAPI(title="Previsão Futebol API", version="1.0.6")

# ============================================================
# 🔓 CORS — Corrigido para suportar Vercel e localhost
# ============================================================
ALLOWED_ORIGINS = [
    "https://previsao-futebol.vercel.app",
    "https://*.vercel.app",
    "http://localhost:3000",
]

api.add_middleware(
    CORSMiddleware,
    # Durante testes deixamos aberto; depois pode-se restringir para ALLOWED_ORIGINS
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 🔗 Rotas
# ============================================================
api.include_router(health_routes.router)
api.include_router(predict_routes.router)
api.include_router(meta_routes.router)  # <— NOVO

# ============================================================
# 🩺 Healthcheck
# ============================================================
@api.api_route("/healthz", methods=["GET", "HEAD"], tags=["system"])
def healthz():
    status = {"status": "ok"}
    try:
        # Redis
        if config.redis_client:
            try:
                test_key = "healthz_test"
                config.redis_client.set(test_key, "ok", ex=5)
                val = config.redis_client.get(test_key)
                status["redis"] = "ok" if val == "ok" else "warning"
            except Exception as err:
                logger.warning(f"Redis check failed: {err}")
                status["redis"] = "error"
        else:
            status["redis"] = "missing"

        # Ficheiro de previsões
        pred_path = "data/predict/predictions.json"
        status["predictions_file"] = "exists" if os.path.exists(pred_path) else "missing"

        # Última atualização
        try:
            last_update = config.redis_client.get("football_predictions_last_update") if config.redis_client else None
            status["last_update"] = last_update or "unknown"
        except Exception:
            status["last_update"] = "error"

        status["time_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        status["environment"] = os.getenv("ENV", "production")

        logger.info("✅ /healthz OK")
        return JSONResponse(status)
    except Exception as e:
        logger.error(f"❌ Erro em /healthz: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

# ============================================================
# 🏠 Root endpoint
# ============================================================
@api.api_route("/", methods=["GET", "HEAD"])
def root():
    logger.info("📡 Ping recebido na rota raiz /")
    return {
        "status": "online",
        "service": "previsao-futebol",
        "version": "1.0.6",
        "docs": "/docs",
        "health": "/healthz",
        "time": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

# ============================================================
# 🚀 ENTRY POINT
# ============================================================
if __name__ == "__main__":
    mode = os.getenv("MODE", "cli")
    if mode == "cli":
        app()
    else:
        import uvicorn
        port = int(os.getenv("PORT", 8000))
        logger.info(f"🚀 Iniciando API FastAPI em modo {mode.upper()} na porta {port}…")
        uvicorn.run("src.main:api", host="0.0.0.0", port=port)
