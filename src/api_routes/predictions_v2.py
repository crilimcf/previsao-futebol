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

# Enriquecimento bivariado (usa o que já tens)
from src.predictor_bivar import enrich_from_file_record

# --- Toggle / Kill-switch (usa flags.py se existir, senão ENV) ---
try:
    from src.utils.flags import is_v2_enabled as _is_v2_enabled
    from src.utils.flags import note_v2_failure as _note_v2_failure
except Exception:
    def _is_v2_enabled() -> bool:
        return os.getenv("V2_MODELS_ENABLED", "false").lower() == "true"
    def _note_v2_failure() -> None:
        return None

router = APIRouter(prefix="/predictions/v2", tags=["predictions-v2"])

_PRED_PATH = Path("data/predict/predictions.json")

def _safe_date(s: Optional[str]) -> str:
    """YYYY-MM-DD. Se None, usa hoje (UTC)."""
    if not s:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return s[:10]

def _read_predictions_file() -> List[Dict[str, Any]]:
    """Lê o ficheiro de previsões (v1). Aceita list direta ou chaves comuns."""
    if not _PRED_PATH.exists():
        return []
    try:
        data = json.loads(_PRED_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("items", "data", "predictions"):
                arr = data.get(k)
                if isinstance(arr, list):
                    return arr
        return []
    except Exception:
        return []

def _extract_league_id(it: Dict[str, Any]) -> str:
    """
    Extrai league_id em vários formatos possíveis:
    - top-level: league_id, leagueId, league (string)
    - nested: league: { id: ... }
    """
    # nested object
    lg = it.get("league")
    if isinstance(lg, dict) and "id" in lg:
        return str(lg.get("id") or "")
    # direct keys
    for k in ("league_id", "leagueId", "league"):
        v = it.get(k)
        if v is None:
            continue
        return str(v)
    return ""

def _extract_date_iso(it: Dict[str, Any]) -> str:
    """
    Extrai data ISO (YYYY-MM-DD) a partir de várias chaves possíveis.
    """
    for k in ("date", "match_date", "fixture_date"):
        v = it.get(k)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    # Último recurso: tentar converter se vier num campo 'fixture'->'date'
    fx = it.get("fixture")
    if isinstance(fx, dict) and isinstance(fx.get("date"), str) and len(fx["date"]) >= 10:
        return fx["date"][:10]
    return ""

def _filter_by_date_and_league(items: List[Dict[str, Any]], date_iso: str, league_id: Optional[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lg_target = str(league_id) if league_id is not None else None
    for it in items:
        d = _extract_date_iso(it)
        if d != date_iso:
            continue
        if lg_target is not None:
            lid = _extract_league_id(it)
            if lid != lg_target:
                continue
        out.append(it)
    return out

@router.get("", summary="Predições v2 (modelo bivariado + fallback)")
def get_predictions_v2(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    source: Optional[str] = Query(
        None,
        description="'model' para forçar bivariado; 'file' para forçar ficheiro; default usa flag/env"
    ),
):
    date_iso = _safe_date(date)

    # origem: file | model | (auto por flag/env)
    if source == "file":
        use_model = False
    elif source == "model":
        use_model = True
    else:
        use_model = _is_v2_enabled()

    base = _filter_by_date_and_league(_read_predictions_file(), date_iso, league_id)

    # Se não houver nada no ficheiro, devolve vazio (não 404)
    if not base:
        return JSONResponse([], status_code=200)

    # Se v2 OFF → devolve ficheiro tal como está
    if not use_model:
        return JSONResponse(base, status_code=200)

    # Tenta enriquecer com bivariado; qualquer erro num jogo → fallback para esse jogo
    out: List[Dict[str, Any]] = []
    try:
        for rec in base:
            try:
                enr = enrich_from_file_record(rec)
                out.append(enr if enr else rec)
            except Exception:
                # erro pontual naquele registo → conta mas não quebra
                out.append(rec)
        return JSONResponse(out, status_code=200)
    except Exception:
        # erro global → conta falha e devolve ficheiro “cru”
        _note_v2_failure()
        return JSONResponse(base, status_code=200)
