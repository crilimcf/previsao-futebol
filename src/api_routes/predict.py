from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src.auth import verify_token
from datetime import datetime
import os
import json
from src import config

router = APIRouter()


# ==========================
# MODELOS DE DADOS
# ==========================

class Odds(BaseModel):
    home: float
    draw: float
    away: float


class MatchInput(BaseModel):
    match_id: int
    date: str
    time: str
    league: str
    home_team: str
    away_team: str
    odds: Optional[Odds] = None


# ==========================
# ENDPOINTS PRINCIPAIS
# ==========================

@router.get("/predictions", tags=["Predictions"])
def get_predictions(request: Request, token: bool = Depends(verify_token)):
    """Devolve todas as previsões armazenadas na aplicação."""
    return request.app.state.predictions


@router.get("/predictions/{match_id}", tags=["Predictions"])
def get_prediction_by_id(match_id: int, request: Request, token: bool = Depends(verify_token)):
    """Devolve a previsão de um jogo específico."""
    for match in request.app.state.predictions:
        if str(match.get("match_id")) == str(match_id):
            return match
    raise HTTPException(status_code=404, detail="Prediction for this match_id not found.")


@router.get("/stats", response_class=Response, tags=["Predictions"])
def get_prediction_stats(token: bool = Depends(verify_token)):
    """Lê as estatísticas agregadas do ficheiro JSON."""
    stats_path = os.path.join("data", "stats", "prediction_stats.json")
    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
        return Response(content=json.dumps(stats), media_type="application/json")
    except FileNotFoundError:
        return Response(
            content=json.dumps({"error": "Stats file not found"}),
            media_type="application/json",
            status_code=404,
        )
    except Exception as e:
        return Response(
            content=json.dumps({"error": str(e)}),
            media_type="application/json",
            status_code=500,
        )


# ==========================
# META - ÚLTIMA ATUALIZAÇÃO
# ==========================

@router.get("/meta/last-update", tags=["Meta"])
def get_last_update(token: bool = Depends(verify_token)):
    """
    Obtém a data/hora da última atualização de previsões.
    Lê o valor da chave no Upstash Redis.
    """
    try:
        if not config.redis_client:
            return {"last_update": "N/A"}

        value = config.redis_client.get(config.LAST_UPDATE_KEY)
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return {"last_update": value or "N/A"}
    except Exception as e:
        print("⚠️ Erro ao ler do Redis:", e)
        return {"last_update": "N/A"}


# ==========================
# REGISTO AUTOMÁTICO DA DATA DE ATUALIZAÇÃO
# ==========================

@router.post("/meta/update", tags=["Meta"])
def set_last_update(token: bool = Depends(verify_token)):
    """
    Atualiza manualmente (ou via script) o timestamp da última atualização.
    Usa o cliente Upstash Redis (HTTP).
    """
    try:
        if not config.redis_client:
            raise Exception("Redis client not initialized")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = config.redis_client.set(config.LAST_UPDATE_KEY, now_str)

        print(f"🕒 Última atualização registada no Redis: {now_str}")
        return {"status": "ok", "last_update": now_str, "redis_result": str(result)}
    except Exception as e:
        print(f"⚠️ Erro ao atualizar last_update no Redis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================
# STATUS DO REDIS
# ==========================

@router.get("/meta/status", tags=["Meta"])
def get_redis_status():
    """
    Mostra o estado atual da ligação Redis e o último update.
    Útil para debugging e monitorização em produção.
    """
    try:
        if not config.redis_client:
            return {"status": "offline", "error": "Redis client not initialized"}

        # Teste simples
        ping = config.redis_client.ping()
        last_update = config.redis_client.get(config.LAST_UPDATE_KEY)
        if isinstance(last_update, bytes):
            last_update = last_update.decode("utf-8")

        return {
            "status": "online" if ping else "error",
            "ping": bool(ping),
            "last_update": last_update or "N/A"
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ==========================
# AUTO-INIT AO ARRANCAR SERVIDOR
# ==========================

def initialize_last_update():
    """Garante que a chave de last_update existe ao iniciar o backend."""
    if not config.redis_client:
        print("⚠️ Redis desativado — a chave last_update não será inicializada.")
        return

    try:
        existing = config.redis_client.get(config.LAST_UPDATE_KEY)
        if not existing:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            config.redis_client.set(config.LAST_UPDATE_KEY, now_str)
            print(f"🟢 Chave '{config.LAST_UPDATE_KEY}' criada automaticamente: {now_str}")
        else:
            print(f"✅ Chave '{config.LAST_UPDATE_KEY}' já existente: {existing}")
    except Exception as e:
        print(f"⚠️ Erro ao inicializar chave last_update: {e}")


# Executa ao importar este módulo
initialize_last_update()
