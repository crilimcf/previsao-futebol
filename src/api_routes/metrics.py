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

from src.api_routes.predictions_v2 import _read_predictions_file, _safe_date, _filter_by_date_and_league
from src.predictor_bivar import enrich_from_file_record

router = APIRouter(tags=["metrics"])

@router.get("/metrics", summary="Snapshot de métricas/preview v2 por data/ligas")
def metrics(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    sample: int = Query(12, ge=1, le=100, description="número de amostras no payload"),
):
    date_iso = _safe_date(date)
    base = _filter_by_date_and_league(_read_predictions_file(), date_iso, league_id)
    if not base:
        return JSONResponse({"date": date_iso, "total": 0, "leagues": [], "items": []}, status_code=200)

    leagues_count = defaultdict(int)
    enriched: List[Dict[str, Any]] = []
    for rec in base:
        leagues_count[str(rec.get("league_id") or rec.get("leagueId") or "")] += 1
        try:
            enriched.append(enrich_from_file_record(rec))
        except Exception:
            enriched.append(rec)

    leagues = [{"league_id": k, "count": v} for k, v in sorted(leagues_count.items(), key=lambda t: (-t[1], t[0]))]

    # corta amostra simpática
    sample_items = []
    for it in enriched[:sample]:
        p = it.get("predictions") or {}
        sample_items.append({
            "match_id": it.get("match_id"),
            "league_id": it.get("league_id"),
            "date": it.get("date"),
            "home": it.get("home_team"),
            "away": it.get("away_team"),
            "v2": {
                "winner": p.get("winner"),
                "double_chance": p.get("double_chance"),
                "over_1_5": p.get("over_1_5"),
                "over_2_5": p.get("over_2_5"),
                "btts": p.get("btts"),
                "correct_score_top3": (p.get("correct_score") or {}).get("top3"),
            },
            # se o v1 trouxer prob/confidence, mostramos para comparação leve
            "v1": (it.get("predictions") if it.get("predictions", {}).get("correct_score") is None else {}),
        })

    return JSONResponse({
        "date": date_iso,
        "total": len(base),
        "leagues": leagues,
        "items": sample_items,
    }, status_code=200)
