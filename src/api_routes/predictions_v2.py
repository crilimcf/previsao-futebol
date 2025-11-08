# ============================================================
# src/api_routes/predictions_v2.py
# ============================================================
from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/predictions/v2", tags=["predictions-v2"])

_PRED_PATH = Path(os.getenv("PREDICTIONS_PATH", "data/predict/predictions.json"))

def _safe_date(s: Optional[str]) -> str:
    if not s:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return s[:10]

def _read_predictions_file() -> List[Dict[str, Any]]:
    if not _PRED_PATH.exists():
        return []
    try:
        data = json.loads(_PRED_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("items", "data", "predictions"):
                if isinstance(data.get(k), list):
                    return data[k]
        return []
    except Exception:
        return []

def _filter_by_date_and_league(items: List[Dict[str, Any]],
                               date_iso: str,
                               league_id: Optional[str]) -> List[Dict[str, Any]]:
    out = []
    for it in items:
        d = str(it.get("date") or it.get("match_date") or "")
        if d[:10] != date_iso:
            continue
        if league_id:
            lid = str(it.get("league_id") or it.get("leagueId") or it.get("league") or "")
            if str(league_id) != lid:
                continue
        out.append(it)
    return out

# --------- bivariado opcional ----------
def _try_enrich(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tenta enriquecer via bivariado; se falhar, devolve o rec original.
    Requer que rec tenha lambda_home e lambda_away.
    """
    try:
        from src.predictor_bivar import enrich_from_file_record  # import lazy
        return enrich_from_file_record(rec)
    except Exception:
        return rec

@router.get("", summary="Predições v2 (toggle modelo/file + fallback)")
def get_predictions_v2(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="'model' para forçar bivariado; padrão usa ficheiro salvo"),
):
    date_iso = _safe_date(date)
    use_model = (os.getenv("V2_MODELS_ENABLED", "false").lower() == "true") or (source == "model")

    base = _filter_by_date_and_league(_read_predictions_file(), date_iso, league_id)
    if not base:
        return JSONResponse([], status_code=200)

    if not use_model:
        return JSONResponse(base, status_code=200)

    # tenta enriquecer com bivariado (safe per-record)
    out = []
    for rec in base:
        out.append(_try_enrich(rec))
    return JSONResponse(out, status_code=200)
