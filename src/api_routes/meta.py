# src/api_routes/meta.py
import os
import json
import logging
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

# usamos o pipeline PRO (odds reais via /odds do proxy)
from src.api_fetch_pro import fetch_and_save_predictions

router = APIRouter(prefix="/meta", tags=["meta"])
log = logging.getLogger("meta")


# -------------------- helpers --------------------
def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:  # tolera BOM
            return json.load(f)
    except Exception as e:
        log.warning(f"Falha a ler {path}: {e}")
        return None


def _expected_key() -> Optional[str]:
    """
    Procura a chave certa para autorizar /meta/update.
    Suporta qualquer uma destas env vars, para compat:
      - ENDPOINT_API_KEY  (recomendado)
      - API_UPDATE_TOKEN
      - API_TOKEN
    """
    return (
        os.getenv("ENDPOINT_API_KEY")
        or os.getenv("API_UPDATE_TOKEN")
        or os.getenv("API_TOKEN")
        or None
    )


def _extract_bearer(token_hdr: str) -> Optional[str]:
    if not token_hdr:
        return None
    token_hdr = token_hdr.strip()
    if token_hdr.lower().startswith("bearer "):
        return token_hdr[7:].strip()
    return None


def _is_authorized(authorization: str, x_endpoint_key: str, key_query: Optional[str]) -> bool:
    """
    Aceita:
      - Authorization: Bearer <token>
      - X-Endpoint-Key: <token>
      - ?key=<token>
    """
    expected = _expected_key()
    if not expected:
        # Se não houver chave configurada no ambiente, não bloqueia (modo dev)
        log.warning("⚠️ ENDPOINT_API_KEY/API_UPDATE_TOKEN/API_TOKEN não configurado — /meta/update sem proteção.")
        return True

    cand = _extract_bearer(authorization) or (x_endpoint_key or "").strip() or (key_query or "").strip()
    return bool(cand) and cand == expected


# -------------------- endpoints --------------------
@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.post("/update")
def update_predictions(
    authorization: str = Header(default=""),
    x_endpoint_key: str = Header(default=""),
    key: Optional[str] = Query(default=None),
    days: int = Query(default=3, ge=1, le=7),
):
    """
    Dispara o refresh das previsões (fixtures + odds reais + poisson + topscorers) e grava data/predict/predictions.json.

    Auth: Authorization: Bearer <token>  |  X-Endpoint-Key: <token>  |  ?key=<token>
    O <token> deve corresponder a ENDPOINT_API_KEY (ou API_UPDATE_TOKEN/API_TOKEN) no ambiente do backend.
    """
    if not _is_authorized(authorization, x_endpoint_key, key):
        return JSONResponse({"status": "forbidden"}, status_code=403)

    try:
        # fetch_and_save_predictions já grava o ficheiro final e retorna {"status":"ok","total":N}
        out = fetch_and_save_predictions()
        return JSONResponse({"status": "ok", **(out or {})})
    except Exception as e:
        log.exception("Erro no update:")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@router.get("/leagues")
def leagues():
    """
    Devolve a lista de ligas conhecidas:
    - Primeiro tenta inferir de data/predict/predictions.json
    - Caso vazio, tenta config/leagues.json
    """
    leagues_map: Dict[str, Dict[str, Any]] = {}

    # 1) predictions.json (mais real do dia)
    preds = _read_json("data/predict/predictions.json") or []
    try:
        for p in preds:
            lid = str(p.get("league_id") or p.get("league") or "").strip()
            if not lid:
                continue
            name = p.get("league_name") or p.get("league") or "League"
            country = p.get("country")
            leagues_map[lid] = {"id": lid, "name": name, "country": country}
    except Exception as e:
        log.warning(f"Falha a extrair ligas de predictions.json: {e}")

    # 2) fallback: config/leagues.json
    if not leagues_map:
        cfg = _read_json("config/leagues.json") or []
        try:
            for row in cfg:
                lid = str(row.get("id") or row.get("league_id") or "").strip()
                if not lid:
                    continue
                name = row.get("name") or row.get("league") or "League"
                country = row.get("country")
                leagues_map[lid] = {"id": lid, "name": name, "country": country}
        except Exception as e:
            log.warning(f"Falha a extrair ligas de config/leagues.json: {e}")

    items: List[Dict[str, Any]] = sorted(
        leagues_map.values(),
        key=lambda x: ((x.get("country") or ""), (x.get("name") or ""))
    )
    return {"count": len(items), "items": items}


@router.get("/calibration")
def calibration_info():
    base = "data/model"
    out = {}
    for name in ["calibration.json", "cal_winner.json", "cal_over25.json", "cal_btts.json"]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    out[name] = json.load(f)
            except Exception as e:
                out[name] = {"error": str(e)}
    return out or {"status": "no-calibration"}
