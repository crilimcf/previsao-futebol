from fastapi import APIRouter, HTTPException, Header
from datetime import datetime
from src import config
from src.fetch_matches import fetch_today_matches
import os
import json
import logging

router = APIRouter()
logger = logging.getLogger("football_api")

# ======================================================
# 🔐 Verificação de Token
# ======================================================
def verify_token(auth_header: str | None):
    expected = os.getenv("ENDPOINT_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="Server missing ENDPOINT_API_KEY.")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format.")
    token = auth_header.split(" ")[1]
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return True


# ======================================================
# 📊 Endpoint principal de previsões
# ======================================================
@router.get("/predictions", tags=["Predictions"])
def get_predictions():
    path = "data/predict/predictions.json"
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Erro em /predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================
# 🔁 Atualização manual
# ======================================================
@router.post("/meta/update", tags=["Meta"])
def manual_update(authorization: str = Header(None)):
    verify_token(authorization)
    try:
        result = fetch_today_matches()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if config.redis_client:
            config.redis_client.set(config.LAST_UPDATE_KEY, now_str)
        logger.info(f"✅ Atualização manual concluída às {now_str}")
        return {"status": "ok", "last_update": now_str, "total_matches": result["total"]}
    except Exception as e:
        logger.error(f"❌ Erro no update manual: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================
# 🧠 Executa previsões IA
# ======================================================
@router.post("/predict", tags=["AI"])
def run_predictions(authorization: str = Header(None)):
    verify_token(authorization)
    try:
        from src.predict import main as run_model
        run_model()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if config.redis_client:
            config.redis_client.set(config.LAST_UPDATE_KEY, now_str)
        return {"status": "ok", "detail": f"Previsões IA atualizadas em {now_str}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================
# 📈 Estado geral
# ======================================================
@router.get("/meta/status", tags=["Meta"])
def meta_status():
    redis_ok = False
    redis_val = None
    if config.redis_client:
        try:
            redis_val = config.redis_client.get(config.LAST_UPDATE_KEY)
            redis_ok = True
        except Exception:
            redis_ok = False

    predictions_file = "data/predict/predictions.json"
    predictions_exists = os.path.exists(predictions_file)
    total_predictions = 0
    if predictions_exists:
        try:
            with open(predictions_file, "r", encoding="utf-8") as f:
                total_predictions = len(json.load(f))
        except Exception:
            pass

    return {
        "redis_connected": redis_ok,
        "last_update": redis_val,
        "predictions_file": predictions_exists,
        "total_predictions": total_predictions,
    }


# ======================================================
# 🕒 Última atualização (novo)
# ======================================================
@router.get("/meta/last-update", tags=["Meta"])
def meta_last_update():
    if config.redis_client:
        try:
            val = config.redis_client.get(config.LAST_UPDATE_KEY)
            return {"last_update": val or "unknown"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"last_update": "N/A"}


# ======================================================
# 📊 Estatísticas (novo)
# ======================================================
@router.get("/stats", tags=["Stats"])
def get_stats():
    path = "data/stats/prediction_stats.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Erro ao ler ficheiro JSON.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================
# 🧩 Último treino IA
# ======================================================
@router.get("/meta/last-train", tags=["AI"])
def last_train():
    try:
        train_file = "data/meta/last_train.json"
        if not os.path.exists(train_file):
            return {"status": "missing", "detail": "Nenhum treino encontrado."}
        with open(train_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
