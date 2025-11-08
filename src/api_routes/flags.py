# src/api_routes/flags.py
import os
from fastapi import APIRouter, Header, HTTPException
from src.utils.flags import is_v2_enabled, set_v2_enabled

router = APIRouter(prefix="/meta/flags", tags=["meta"])

API_TOKEN = os.getenv("API_TOKEN", "")

def _auth(authorization: str | None):
    if not API_TOKEN or authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.get("/")
def list_flags():
    return {"v2_enabled": is_v2_enabled()}

@router.post("/v2")
def toggle_v2(enabled: bool, authorization: str | None = Header(default=None)):
    _auth(authorization)
    set_v2_enabled(bool(enabled))
    return {"ok": True, "v2_enabled": is_v2_enabled()}
