# src/api_routes/meta.py
from fastapi import APIRouter, Query
from src.api_fetch_pro import fetch_and_save_predictions
import json
import os
import logging

router = APIRouter()
logger = logging.getLogger("api.meta")

DATA_PATH = os.path.join("data", "predict", "predictions.json")

# ===========================================================
# /meta/update
# ===========================================================
@router.post("/meta/update")
def meta_update(days: int = Query(3)):
    """Atualiza previsões (fixtures + WCQ Europe)."""
    try:
        result = fetch_and_save_predictions(days=days)
        logger.info(f"🌀 meta/update executado | total={result['total']}")
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"❌ Erro meta/update: {e}")
        return {"status": "error", "error": str(e)}

# ===========================================================
# /meta/leagues
# ===========================================================
@router.get("/meta/leagues")
def meta_leagues():
    """Lista ligas e nº de jogos previstos."""
    if not os.path.exists(DATA_PATH):
        return {"leagues": []}

    with open(DATA_PATH, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    leagues = {}
    for m in data:
        lid = str(m.get("league_id"))
        leagues.setdefault(lid, {
            "id": lid,
            "name": m.get("league"),
            "country": m.get("country"),
            "matches": 0,
        })
        leagues[lid]["matches"] += 1

    return {"leagues": list(leagues.values())}
