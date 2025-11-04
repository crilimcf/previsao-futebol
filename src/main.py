import typer
import os
import datetime
import json
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from src.train import train_model as train_main
from src.predict import main as predict_main
from scripts.validate_historical_matches import validate_historical_matches as validate_main
from src import config

# ============================================================
# ⚙️ CONFIGURAÇÃO DE LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# ============================================================
# 🎯 CLI PRINCIPAL (Typer)
# ============================================================

app = typer.Typer(help="Football Prediction Project CLI")

@app.command()
def train():
    """Train the models and save artifacts."""
    logger.info("🚀 Training models...")
    train_main()

@app.command()
def predict():
    """Make predictions on upcoming matches."""
    logger.info("⚽ Generating predictions...")
    predict_main()

@app.command()
def validate():
    """Validate historical match data for consistency."""
    logger.info("🧩 Validating historical match data...")
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
# 🌍 FASTAPI APP (Render + UptimeRobot /healthz)
# ============================================================

api = FastAPI(title="Previsão Futebol API", version="1.0.2")

@api.api_route("/healthz", methods=["GET", "HEAD"], tags=["system"])
def healthz():
    """Endpoint de monitorização e integridade da API (suporta HEAD para UptimeRobot)."""
    status = {"status": "ok"}
    try:
        # 🔹 Verifica Redis
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

        # 🔹 Verifica ficheiro de previsões
        pred_path = "data/predict/predictions.json"
        status["predictions_file"] = "exists" if os.path.exists(pred_path) else "missing"

        # 🔹 Última atualização
        try:
            last_update = config.redis_client.get("football_predictions_last_update")
            if last_update:
                status["last_update"] = last_update
            else:
                status["last_update"] = "unknown"
        except Exception:
            status["last_update"] = "error"

        # 🔹 Informações gerais
        status["time_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        status["environment"] = os.getenv("ENV", "production")

        logger.info("✅ API viva e monitorizada via /healthz")
        return JSONResponse(status)

    except Exception as e:
        logger.error(f"❌ Erro em /healthz: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


# ============================================================
# 🏠 ROTA RAIZ (para testes e status rápido)
# ============================================================

@api.api_route("/", methods=["GET", "HEAD"])
def root():
    """Retorna estado geral da API (GET e HEAD permitidos)."""
    logger.info("📡 Ping recebido na rota raiz /")
    return {
        "status": "online",
        "service": "previsao-futebol",
        "version": "1.0.2",
        "docs": "/docs",
        "health": "/healthz",
        "time": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }


# ============================================================
# 🚀 ENTRY POINT UNIVERSAL
# ============================================================

if __name__ == "__main__":
    mode = os.getenv("MODE", "cli")

    if mode == "cli":
        app()
    else:
        import uvicorn
        port = int(os.getenv("PORT", 8000))
        logger.info(f"🚀 Iniciando API FastAPI em modo {mode.upper()} na porta {port}...")
        uvicorn.run("main:api", host="0.0.0.0", port=port)
