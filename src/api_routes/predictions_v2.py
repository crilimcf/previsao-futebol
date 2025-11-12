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

INTL_COUNTRIES = {"World", "International"}
INTL_KWS = (
    "world", "uefa", "euro", "nations", "qualif", "qualification",
    "friendlies", "copa", "africa cup", "asian cup", "gold cup"
)
YOUTH_PAT = (" u15", " u16", " u17", " u18", " u19", " u20", " u21", " u22", " u23")
WOMEN_PAT = (" women", " feminino", " fémin", " fem ", " w ", " w-")

def _is_youth_or_women(name: Optional[str]) -> bool:
    if not name:
        return False
    n = (" " + str(name).lower() + " ")
    return any(p in n for p in YOUTH_PAT) or any(p in n for p in WOMEN_PAT)

def _is_international_row(p: Dict[str, Any]) -> bool:
    country = (p.get("country") or "").strip()
    lname = (p.get("league_name") or p.get("league") or "").strip().lower()
    return (country in INTL_COUNTRIES) or any(kw in lname for kw in INTL_KWS)

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

def _filter(items: List[Dict[str, Any]],
            date_iso: str,
            league_id: Optional[str],
            intl: Optional[bool]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        d = str(it.get("date") or it.get("match_date") or "")
        if d[:10] != date_iso:
            continue
        if league_id:
            lid = str(it.get("league_id") or it.get("leagueId") or "")
            if lid != str(league_id):
                continue
        if intl is True:
            if not _is_international_row(it):
                continue
            h = (it.get("home_team") or "").strip()
            a = (it.get("away_team") or "").strip()
            if _is_youth_or_women(h) or _is_youth_or_women(a):
                continue
        elif intl is False:
            if _is_international_row(it):
                continue
        out.append(it)
    return out

# --------- bivariado opcional ----------
def _try_enrich(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Tenta enriquecer via bivariado; se falhar, devolve o rec original."""
    try:
        from src.predictor_bivar import enrich_from_file_record  # import lazy
        return enrich_from_file_record(rec)
    except Exception:
        return rec

@router.get("", summary="Predições v2 (toggle modelo/file + filtros)")
def get_predictions_v2(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    intl: Optional[bool] = Query(None, description="True=apenas seleções A; False=excluir internacionais; None=tudo"),
    source: Optional[str] = Query(None, description="'model' para forçar bivariado; padrão usa ficheiro salvo"),
    limit: int = Query(0, ge=0, le=1000),
):
    date_iso = _safe_date(date)
    use_model = (os.getenv("V2_MODELS_ENABLED", "false").lower() == "true") or (source == "model")

    base = _filter(_read_predictions_file(), date_iso, league_id, intl)
    if not base:
        return JSONResponse([], status_code=200)

    if not use_model:
        out = base
    else:
        out = [_try_enrich(rec) for rec in base]

    if limit > 0:
        out = out[:limit]

    return JSONResponse(out, status_code=200)
