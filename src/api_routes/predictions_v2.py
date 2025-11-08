# src/api_routes/predictions_v2.py
from __future__ import annotations
import os, json, datetime
from typing import List, Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.pipeline.v2_postprocess import postprocess_item

router = APIRouter(prefix="/predictions", tags=["predictions-v2"])

BASE_FILE = os.getenv("PREDICTIONS_FILE", "data/predict/predictions.json")

def _iso_date(d: str) -> str:
    try:
        # aceita "YYYY-MM-DD" ou "YYYY-MM-DD HH:MM:SS"
        return d[:10]
    except Exception:
        return ""

@router.get("/v2")
def predictions_v2(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(default=None),
) -> JSONResponse:
    """
    Lê o ficheiro v1 (predictions.json), aplica pós-processo/calibração/blend e devolve.
    Fail-open: se faltar algo, devolve base.
    """
    if not os.path.exists(BASE_FILE):
        return JSONResponse([])

    try:
        data = json.loads(open(BASE_FILE, "r", encoding="utf-8").read())
        if not isinstance(data, list):
            return JSONResponse([])

        out = []
        for item in data:
            try:
                # filtros
                if date:
                    d_item = _iso_date(item.get("date") or item.get("match_date") or "")
                    if d_item != date: 
                        continue
                if league_id:
                    lid = str(item.get("league_id") or item.get("leagueId") or item.get("league", ""))
                    if str(lid) != str(league_id):
                        continue

                lid = str(item.get("league_id") or item.get("leagueId") or "")
                enriched = postprocess_item(item, league_id=lid if lid else "0")
                out.append(enriched)
            except Exception:
                # item malformado? devolve como veio
                out.append(item)
        return JSONResponse(out)
    except Exception:
        return JSONResponse([])
