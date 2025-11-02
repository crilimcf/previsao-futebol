import typer
import os
import datetime
import json
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from src.train import train_model as train_main
from src.predict import main as predict_main
from scripts.validate_historical_matches import validate_historical_matches as validate_main
from src import config

app = typer.Typer(help="Football Prediction Project CLI")

# ============================================================
# 🎯 COMANDOS CLI
# ============================================================

@app.command()
def train():
    """Train the models and save artifacts."""
    train_main()

@app.command()
def predict():
    """Make predictions on upcoming matches."""
    predict_main()

@app.command()
def validate():
    """Validate historical match data for consistency."""
    validate_main()


# ============================================================
# 🧠 CALLBACK PRINCIPAL DO CLI
# ============================================================

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
# 🌍 FASTAPI APP (para Render /healthz)
# ============================================================

api = FastAPI(title="Previsão Futebol API", version="1.0.0")

@api.get("/healthz", tags=["system"])
def healthz():
    """Endpoint de monitorização e integridade da API."""
    status = {"status": "ok"}

    try:
        # 🔹 Verifica Redis
        if config.redis_client:
            try:
                test_key = "healthz_test"
                config.redis_client.set(test_key, "ok", ex=5)
                val = config.redis_client.get(test_key)
                status["redis"] = "ok" if val == "ok" else "warning"
            except Exception:
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
        status["time_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        status["environment"] = os.getenv("ENVIRONMENT", "production")

        return JSONResponse(status)
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


# ============================================================
# 🚀 ENTRY POINT UNIVERSAL
# ============================================================

if __name__ == "__main__":
    # Modo CLI
    if os.getenv("MODE", "cli") == "cli":
        app()
    # Modo servidor FastAPI (Render)
    else:
        import uvicorn
        uvicorn.run("src.main:api", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
