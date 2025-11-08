# -*- coding: utf-8 -*-
from __future__ import annotations
from fastapi import APIRouter
from pathlib import Path
import json
from datetime import datetime, timezone

router = APIRouter()

PRED_FILE = Path("data/predict/predictions.json")
STATS_FILE = Path("data/stats/prediction_stats.json")

@router.get("/metrics", tags=["metrics"])
def metrics():
    out = {
        "time_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "predictions_count": 0,
        "stats": {},
        "sources": {},
    }
    if PRED_FILE.exists():
        try:
            raw = json.loads(PRED_FILE.read_text(encoding="utf-8"))
            arr = raw if isinstance(raw, list) else raw.get("data") or raw.get("items") or raw.get("predictions") or []
            out["predictions_count"] = len(arr) if isinstance(arr, list) else 0
            out["sources"]["predictions_json"] = "ok"
        except Exception:
            out["sources"]["predictions_json"] = "error"
    else:
        out["sources"]["predictions_json"] = "missing"

    if STATS_FILE.exists():
        try:
            out["stats"] = json.loads(STATS_FILE.read_text(encoding="utf-8"))
            out["sources"]["stats_json"] = "ok"
        except Exception:
            out["sources"]["stats_json"] = "error"
    else:
        out["sources"]["stats_json"] = "missing"

    return out
