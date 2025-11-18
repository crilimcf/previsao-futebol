# src/api_routes/meta.py
import os
import json
import logging
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

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
        out = fetch_and_save_predictions(days=days) or {}
        # resposta FINAL (sem "result" aninhado)
        return JSONResponse({"status": "ok", "days": days, **out})
    except Exception as e:
        log.exception("Erro no update:")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


@router.get("/leagues")
def leagues():
    """
    Devolve a lista de ligas conhecidas com nº de jogos:
    - Lido a partir de data/predict/predictions.json
    - Se vazio, faz fallback para config/leagues.json (matches=0)
    """
    leagues_map: Dict[str, Dict[str, Any]] = {}

    # 1) predictions.json (mais real do dia)
    preds = _read_json("data/predict/predictions.json") or []
    try:
        for p in preds:
            lid = str(p.get("league_id") or p.get("league") or "").strip()
            if not lid:
                continue
            name = p.get("league") or p.get("league_name") or "League"
            country = p.get("country")
            rec = leagues_map.get(lid)
            if not rec:
                rec = {"id": lid, "name": name, "country": country, "matches": 0}
                leagues_map[lid] = rec
            rec["matches"] += 1
    except Exception as e:
        log.warning(f"Falha a extrair ligas de predictions.json: {e}")

    # 2) fallback: config/leagues.json (se predictions vazio)
    if not leagues_map:
        cfg = _read_json("config/leagues.json") or []
        try:
            for row in cfg:
                lid = str(row.get("id") or row.get("league_id") or "").strip()
                if not lid:
                    continue
                name = row.get("name") or row.get("league") or "League"
                country = row.get("country")
                leagues_map[lid] = {"id": lid, "name": name, "country": country, "matches": 0}
        except Exception as e:
            log.warning(f"Falha a extrair ligas de config/leagues.json: {e}")

    items: List[Dict[str, Any]] = sorted(
        leagues_map.values(),
        key=lambda x: ((x.get("country") or ""), (x.get("name") or ""))
    )
    return {"leagues": items}


@router.get("/calibration")
def calibration_info():
    base = "data/model"
    out: Dict[str, Any] = {}
    for name in ["calibration.json", "cal_winner.json", "cal_over25.json", "cal_btts.json"]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    out[name] = json.load(f)
            except Exception as e:
                out[name] = {"error": str(e)}
    return out or {"status": "no-calibration"}
