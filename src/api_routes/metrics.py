# ============================================================
# src/api_routes/metrics.py
# ============================================================
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

# ------------------------------------------------------------
# Tentamos aproveitar as helpers do router v2 (para filtrar por
# data/liga e ler o ficheiro). Mas NÃO deixamos o backend cair
# se o ficheiro/func faltar.
# ------------------------------------------------------------
try:
    from src.api_routes.predictions_v2 import (
        _read_predictions_file,
        _safe_date,
        _filter_by_date_and_league,
    )
except Exception:
    # fallbacks mínimos — suficientes para não rebentar o /metrics
    def _safe_date(s: Optional[str]) -> str:
        if not s:
            from datetime import datetime, timezone
            return datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return s[:10]

    def _read_predictions_file() -> List[Dict[str, Any]]:
        p = Path("data/predict/predictions.json")
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            for k in ("items", "data", "predictions"):
                if isinstance(data.get(k), list):
                    return data[k]
            return []
        except Exception:
            return []

    def _filter_by_date_and_league(
        items: List[Dict[str, Any]],
        date_iso: str,
        league_id: Optional[str],
    ) -> List[Dict[str, Any]]:
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

# ------------------------------------------------------------
# enrichment opcional com o modelo bivariado
# ------------------------------------------------------------
def _try_enrich(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tenta aplicar o enrich_from_file_record (bivariado).
    Se não existir ou falhar, devolve o próprio registo.
    """
    try:
        from src.predictor_bivar import enrich_from_file_record  # type: ignore
    except Exception:
        return rec
    try:
        return enrich_from_file_record(rec)
    except Exception:
        return rec


router = APIRouter(tags=["metrics"])


@router.get("/metrics", summary="Snapshot de métricas/preview v2 por data/ligas")
def metrics(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    sample: int = Query(12, ge=1, le=100, description="número de amostras no payload"),
):
    """
    Devolve:
      - o que temos hoje no ficheiro de previsões (filtrado por data/liga)
      - uma amostra enriquecida com o bivariado (se disponível)
      - e, SE existir data/stats/metrics.json, junta também isso
    Assim consegues comparar o que o backend está a servir com o que o teu
    job de backtest calculou.
    """
    date_iso = _safe_date(date)

    # 1) base: previsões do dia
    base = _filter_by_date_and_league(_read_predictions_file(), date_iso, league_id)
    total_base = len(base)

    # 2) contagem por liga
    leagues_count: Dict[str, int] = defaultdict(int)
    for rec in base:
        lid = str(rec.get("league_id") or rec.get("leagueId") or "")
        leagues_count[lid] += 1

    leagues = [
        {"league_id": k, "count": v}
        for k, v in sorted(leagues_count.items(), key=lambda t: (-t[1], t[0]))
    ]

    # 3) amostra enriquecida
    sample_items: List[Dict[str, Any]] = []
    for it in base[:sample]:
        enriched = _try_enrich(it)
        preds_v2 = enriched.get("predictions") or {}
        preds_v1 = it.get("predictions") or {}

        sample_items.append(
            {
                "match_id": it.get("match_id") or it.get("fixture_id"),
                "league_id": it.get("league_id") or it.get("leagueId"),
                "date": it.get("date"),
                "home": it.get("home_team"),
                "away": it.get("away_team"),
                # o que o v2 calculou (se calculou)
                "v2": {
                    "winner": preds_v2.get("winner"),
                    "double_chance": preds_v2.get("double_chance"),
                    "over_1_5": preds_v2.get("over_1_5"),
                    "over_2_5": preds_v2.get("over_2_5"),
                    "btts": preds_v2.get("btts"),
                    "correct_score_top3": (
                        (preds_v2.get("correct_score") or {}).get("top3")
                        or enriched.get("correct_score_top3")
                    ),
                },
                # o que estava no ficheiro antes de enriquecer
                "v1": preds_v1,
            }
        )

    # 4) métricas de backtest se existirem
    metrics_file = Path("data/stats/metrics.json")
    metrics_payload: Any = None
    if metrics_file.exists():
        try:
            metrics_payload = json.loads(metrics_file.read_text(encoding="utf-8"))
        except Exception:
            metrics_payload = {"error": "metrics.json inválido"}

    return JSONResponse(
        {
            "date": date_iso,
            "total": total_base,
            "leagues": leagues,
            "items": sample_items,
            "stored_metrics": metrics_payload,  # ← pode ser None
        },
        status_code=200,
    )
