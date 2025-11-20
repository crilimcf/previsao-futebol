# ============================================================
# src/api_routes/predictions_v2.py
# ============================================================
from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("api.predictions_v2")

router = APIRouter(prefix="/predictions/v2", tags=["predictions-v2"])

_PRED_PATH = Path(os.getenv("PREDICTIONS_PATH", "data/predict/predictions.json"))
_LEAGUES_CFG = Path(os.getenv("LEAGUES_CONFIG", "config/leagues.json"))


# ----------------- allowlist de ligas -----------------
def _load_allowed_leagues() -> Optional[Set[str]]:
    if not _LEAGUES_CFG.exists():
        return None
    try:
        text = _LEAGUES_CFG.read_text(encoding="utf-8")
        data = json.loads(text) or []
        allowed: Set[str] = set()
        if isinstance(data, list):
            cfg_list = data
        else:
            cfg_list = data.get("leagues") or []
        for obj in cfg_list:
            lid = obj.get("id")
            if lid is not None:
                allowed.add(str(lid))
        return allowed or None
    except Exception as e:
        logger.warning(f"Falha a ler leagues.json ({_LEAGUES_CFG}): {e}")
        return None


_ALLOWED_LEAGUES: Optional[Set[str]] = _load_allowed_leagues()


def _is_allowed_league(rec: Dict[str, Any]) -> bool:
    if not _ALLOWED_LEAGUES:
        return True
    lid = rec.get("league_id") or rec.get("leagueId")
    if lid is None:
        return False
    return str(lid) in _ALLOWED_LEAGUES


# ----------------- helpers ficheiro -----------------
def _read_predictions_file() -> List[Dict[str, Any]]:
    """Lê o ficheiro de previsões e devolve SEMPRE uma lista."""
    if not _PRED_PATH.exists():
        logger.warning(f"⚠️ Ficheiro {_PRED_PATH} não existe.")
        return []

    try:
        text = _PRED_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        logger.error(f"❌ Erro a ler {_PRED_PATH}: {e}")
        return []

    items: List[Dict[str, Any]] = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # compat: antigos formatos com "items" / "data" / "predictions"
        for key in ("items", "data", "predictions"):
            v = data.get(key)
            if isinstance(v, list):
                items = v
                break

    logger.info(f"📥 predictions_v2: carregados {len(items)} registos de {_PRED_PATH}")
    return items


def _filter_by_date(items: List[Dict[str, Any]], date_iso: Optional[str]) -> List[Dict[str, Any]]:
    """Filtra por data YYYY-MM-DD (se for None, não filtra)."""
    if not date_iso:
        return items

    target = date_iso[:10]
    out: List[Dict[str, Any]] = []
    for it in items:
        d = str(it.get("date") or it.get("match_date") or "")
        if d[:10] == target:
            out.append(it)
    return out


def _filter_by_league(items: List[Dict[str, Any]], league_id: Optional[str]) -> List[Dict[str, Any]]:
    """Filtra por league_id, aceitando strings/ints ('32', 32, etc.)."""
    if not league_id:
        return items

    wanted = str(league_id).strip()
    out: List[Dict[str, Any]] = []
    for it in items:
        lid = str(
            it.get("league_id")
            or it.get("leagueId")
            or ""
        ).strip()
        if lid == wanted:
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


# ============================================================
# /predictions/v2  (principal para o frontend)
# ============================================================
@router.get(
    "",
    summary="Predições v2 (ficheiro + opcional bivariado)",
)
def get_predictions_v2(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None, description="ID da liga (ex: '32')"),
    source: Optional[str] = Query(
        None,
        description="'model' para forçar bivariado; por omissão usa só o ficheiro salvo",
    ),
):
    """
    Lê data/predict/predictions.json e devolve as predições para a data/league pedidas.
    - Se V2_MODELS_ENABLED=true OU source=model => tenta enriquecer com modelo bivariado.
    - Caso contrário, devolve o que está no ficheiro tal como foi gravado pelo /meta/update.

    IMPORTANTE: devolve SEMPRE uma LISTA JSON, mesmo que só haja 1 jogo.
    """
    items = _read_predictions_file()
    total_raw = len(items)

    # filtros por data / liga
    items = _filter_by_date(items, date)
    items = _filter_by_league(items, league_id)

    # aplica allowlist de ligas (para esconder ligas que não queres)
    if _ALLOWED_LEAGUES:
        items = [rec for rec in items if _is_allowed_league(rec)]

    if not items:
        logger.info(
            f"📤 /predictions/v2 sem resultados | "
            f"date={date} league_id={league_id} total_raw={total_raw}"
        )
        # devolve lista vazia, NUNCA objeto
        return JSONResponse([], status_code=200)

    use_model = (os.getenv("V2_MODELS_ENABLED", "false").lower() == "true") or (source == "model")

    if not use_model:
        logger.info(
            f"📤 /predictions/v2 (file-only) | date={date} league_id={league_id} "
            f"count={len(items)}"
        )
        # devolve SEMPRE lista
        return JSONResponse(items, status_code=200)

    # tenta enriquecer com bivariado (safe per-record)
    out: List[Dict[str, Any]] = []
    for rec in items:
        out.append(_try_enrich(rec))

    logger.info(
        f"📤 /predictions/v2 (enriched) | date={date} league_id={league_id} "
        f"count={len(out)}"
    )
    # devolve SEMPRE lista
    return JSONResponse(out, status_code=200)


# ============================================================
# /predictions/v2/raw  (debug)
# ============================================================
@router.get(
    "/raw",
    summary="Dump bruto de predictions.json (debug)",
)
def get_predictions_raw():
    """
    Endpoint de debug: devolve tudo o que está em data/predict/predictions.json,
    sem filtros (mas ainda assim respeita a allowlist de ligas, se existir).
    """
    items = _read_predictions_file()
    if _ALLOWED_LEAGUES:
        items = [rec for rec in items if _is_allowed_league(rec)]
    return {"total": len(items), "items": items}
