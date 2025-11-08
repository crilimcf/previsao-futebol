# ============================================================
# src/api_routes/predictions_v2.py
# Rota v2 com toggle/env e fallback por registo.
# - Lê predictions do ficheiro (ou do dict com chaves comuns)
# - Filtra por data/league_id
# - Se V2_MODELS_ENABLED=true ou source=model, tenta enriquecer
#   com predictor_bivar.enrich_from_file_record; se não existir,
#   ou der erro por jogo, faz fallback ao registo original.
# ============================================================

from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/predictions/v2", tags=["predictions-v2"])

# Caminho do ficheiro pode vir do ambiente (render.yaml)
_PRED_PATH = Path(os.getenv("PREDICTIONS_PATH", "data/predict/predictions.json"))

# ------------------------------------------------------------
# Import "suave" do enriquecedor bivariado
# ------------------------------------------------------------
_HAS_ENRICH = False
def _enrich_passthrough(rec: Dict[str, Any]) -> Dict[str, Any]:
    # devolve o próprio registo (fallback)
    return rec

try:
    # Se existir e exportar a função, usamos
    from src.predictor_bivar import enrich_from_file_record as _enrich  # type: ignore
    _HAS_ENRICH = True
except Exception:
    # Fallback: não bloqueia o arranque
    _enrich = _enrich_passthrough  # type: ignore
    _HAS_ENRICH = False


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _safe_date(s: Optional[str]) -> str:
    # YYYY-MM-DD; se None, usa hoje UTC
    if not s:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return str(s)[:10]

def _read_predictions_file() -> List[Dict[str, Any]]:
    if not _PRED_PATH.exists():
        return []
    try:
        raw = _PRED_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("items", "data", "predictions", "records"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
        return []
    except Exception:
        return []

def _filter_by_date_and_league(
    items: List[Dict[str, Any]],
    date_iso: str,
    league_id: Optional[str],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        d = str(it.get("date") or it.get("match_date") or "")
        if d[:10] != date_iso:
            continue
        if league_id:
            lid = str(
                it.get("league_id")
                or it.get("leagueId")
                or it.get("league")
                or it.get("league_code")
                or ""
            )
            if str(league_id) != lid:
                continue
        out.append(it)
    return out


# ------------------------------------------------------------
# Endpoint
# ------------------------------------------------------------
@router.get("", summary="Predições v2 (toggle modelo/file + fallback por jogo)")
def get_predictions_v2(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    source: Optional[str] = Query(
        None,
        description="'model' força bivariado; 'file' força ficheiro; vazio usa env V2_MODELS_ENABLED",
    ),
):
    date_iso = _safe_date(date)
    env_toggle = os.getenv("V2_MODELS_ENABLED", "false").lower() == "true"
    use_model = (source == "model") or (source is None and env_toggle)

    base = _filter_by_date_and_league(_read_predictions_file(), date_iso, league_id)

    # Sem jogos -> lista vazia
    if not base:
        return JSONResponse([], status_code=200)

    # Se não queremos modelo, ou não temos enriquecedor carregado, devolve base
    if not use_model or not _HAS_ENRICH:
        return JSONResponse(base, status_code=200)

    # Enriquecimento por jogo com fallback
    out: List[Dict[str, Any]] = []
    for rec in base:
        try:
            out.append(_enrich(rec))  # type: ignore[misc]
        except Exception:
            out.append(rec)  # fallback silencioso por registo

    return JSONResponse(out, status_code=200)
