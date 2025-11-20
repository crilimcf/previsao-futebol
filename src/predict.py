# src/api_routes/predict.py
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
import os
import json
import logging
import datetime
import pathlib
from typing import Optional, List, Any, Dict
from src import config

router = APIRouter(tags=["predictions"])

logger = logging.getLogger("routes.predict")

PRED_PATH = config.PREDICTIONS_PATH
HISTORY_PATH = config.PREDICTIONS_HISTORY_PATH
ENDPOINT_TOKEN = os.getenv("ENDPOINT_API_KEY", "")  # ou config.ENDPOINT_API_KEY

def _read_json_lenient(path: str) -> Any:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        try:
            data = pathlib.Path(path).read_bytes().decode("utf-8-sig")
            return json.loads(data)
        except Exception:
            logger.error(f"Erro a ler JSON ({path}): {e}")
            raise

def _write_json_no_bom(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _require_auth(authorization: Optional[str] = Header(None)) -> None:
    token_conf = ENDPOINT_TOKEN
    if not token_conf:
        return  # ambiente de dev
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    token = authorization.split(" ", 1)[1].strip()
    if token != token_conf:
        raise HTTPException(status_code=403, detail="Invalid token.")

@router.get("/predictions")
def get_predictions():
    try:
        data = _read_json_lenient(PRED_PATH)
        if isinstance(data, dict):
            for key in ("data", "matches", "response", "items"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                data = []
        if not isinstance(data, list):
            data = []
        return JSONResponse(data)
    except Exception as e:
        logger.error(f"Erro em /predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
def get_stats():
    try:
        data: List[Dict[str, Any]] = _read_json_lenient(PRED_PATH) or []
        if not isinstance(data, list):
            data = []
        total = len(data)
        by_league: Dict[str, int] = {}
        for m in data:
            lg = str(m.get("league") or m.get("league_name") or m.get("league_id") or "unknown")
            by_league[lg] = by_league.get(lg, 0) + 1
        return {"total": total, "by_league": by_league}
    except Exception as e:
        logger.error(f"Erro em /stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/meta/update")
def meta_update(_: None = Depends(_require_auth)):
    """
    Recorre o teu predictor e atualiza Redis/last_update.
    """
    try:
        from src.predict import main as predict_main
        predict_main()

        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        # grava last_update via helpers (funciona REST e redis-py)
        config.redis_set(config.LAST_UPDATE_KEY, ts, ex=7*24*3600)
        total = len(_read_json_lenient(PRED_PATH) or [])
        return {"status": "ok", "last_update": ts, "total_matches": total}
    except Exception as e:
        logger.error(f"Erro em /meta/update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meta/last-update")
def last_update():
    """
    Lê last_update do Redis; cai para mtime do ficheiro se necessário.
    """
    try:
        ts = config.redis_get(config.LAST_UPDATE_KEY)
        if not ts:
            if os.path.exists(PRED_PATH):
                mtime = datetime.datetime.utcfromtimestamp(os.path.getmtime(PRED_PATH))
                ts = mtime.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts = "unknown"
        return {"last_update": ts}
    except Exception as e:
        logger.error(f"Erro em /meta/last-update: {e}")
        raise HTTPException(status_code=500, detail=str(e))
