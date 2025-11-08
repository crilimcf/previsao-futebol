# src/api_routes/metrics.py
from __future__ import annotations
import os, json
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])

METRICS_FILE = os.getenv("METRICS_FILE", "data/stats/metrics.json")

@router.get("")
def get_metrics():
    if not os.path.exists(METRICS_FILE):
        return JSONResponse({"status":"missing"})
    try:
        data = json.loads(open(METRICS_FILE, "r", encoding="utf-8").read())
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"status":"error","detail":str(e)}, status_code=500)
