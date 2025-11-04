# src/api_routes/predict.py
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
import os, json, logging, datetime, pathlib
from typing import Optional, List, Any, Dict
from src import config

router = APIRouter(tags=["predictions"])

logger = logging.getLogger("routes.predict")

PRED_PATH = "data/predict/predictions.json"
HISTORY_PATH = "data/predict/predictions_history.json"
LAST_UPDATE_KEY = "football_predictions_last_update"
ENDPOINT_TOKEN = os.getenv("ENDPOINT_API_KEY", "")

def _read_json_lenient(path: str) -> Any:
    """
    Lê JSON aceitando BOM se existir.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        # fallback extra — tenta ler como bytes e decodificar com utf-8-sig
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
    if not ENDPOINT_TOKEN:
        # se não houver token configurado, não bloqueia (ambiente de dev)
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    token = authorization.split(" ", 1)[1].strip()
    if token != ENDPOINT_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token.")

@router.get("/predictions")
def get_predictions():
    try:
        data = _read_json_lenient(PRED_PATH)
        # Normaliza sempre para lista
        if isinstance(data, dict):
            # alguns pipelines guardam {"data":[...]}
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
    """
    Estatísticas simples por liga e contagem total.
    """
    try:
        data: List[Dict[str, Any]] = _read_json_lenient(PRED_PATH) or []
        if not isinstance(data, list):
            data = []
        total = len(data)
        by_league: Dict[str, int] = {}
        for m in data:
            lg = str(m.get("league") or m.get("league_name") or m.get("league_id") or "unknown")
            by_league[lg] = by_league.get(lg, 0) + 1
        return {
            "total": total,
            "by_league": by_league,
        }
    except Exception as e:
        logger.error(f"Erro em /stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/meta/update")
def meta_update(_: None = Depends(_require_auth)):
    """
    Recorre o teu predictor e atualiza Redis com timestamp.
    """
    try:
        from src.predict import main as predict_main
        predict_main()

        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if config.redis_client:
            try:
                config.redis_client.set(LAST_UPDATE_KEY, ts, ex=7*24*3600)
            except Exception as err:
                logger.warning(f"Falha a gravar last_update no Redis: {err}")
        return {"status": "ok", "last_update": ts, "total_matches": len(_read_json_lenient(PRED_PATH) or [])}
    except Exception as e:
        logger.error(f"Erro em /meta/update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meta/last-update")
def last_update():
    """
    Lê o last_update do Redis; se não houver, usa mtime do ficheiro.
    """
    try:
        ts = None
        if config.redis_client:
            try:
                ts = config.redis_client.get(LAST_UPDATE_KEY)
            except Exception as err:
                logger.warning(f"Falha a ler Redis: {err}")
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
