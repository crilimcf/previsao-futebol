# src/api_routes/meta.py
import os
import re
import json
import logging
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

# pipeline PRO (gera predictions.json com odds de mercado quando possível)
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
    Chave para autorizar /meta/update.
    Aceita:
      - ENDPOINT_API_KEY (recomendado)
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
        # modo dev/sem chave definida: não bloqueia
        log.warning("⚠️ ENDPOINT_API_KEY/API_UPDATE_TOKEN/API_TOKEN não configurado — /meta/update sem proteção.")
        return True

    cand = _extract_bearer(authorization) or (x_endpoint_key or "").strip() or (key_query or "").strip()
    return bool(cand) and cand == expected

# -------------------- classificação de ligas --------------------
INTL_COUNTRIES = {
    "World", "Europe", "South America", "North & Central America",
    "Africa", "Asia", "Oceania", "International"
}
INTL_KW = [
    "world cup", "qualification", "qualifiers", "nations league",
    "uefa euro", "european championship",
    "africa cup of nations", "afcon", "asian cup",
    "copa america", "gold cup", "friendly"
]
YOUTH_RE = re.compile(r"\bU(15|16|17|18|19|20|21|22|23)\b", re.I)
WOMEN_RE = re.compile(r"\b(women|fem|fémin)\b", re.I)

def _is_youth_or_women(s: Optional[str]) -> bool:
    if not s:
        return False
    return bool(YOUTH_RE.search(s)) or bool(WOMEN_RE.search(s))

def _is_international(country: Optional[str], name: Optional[str]) -> bool:
    c = (country or "").strip()
    n = (name or "").lower()
    if c in INTL_COUNTRIES:
        return True
    return any(kw in n for kw in INTL_KW)

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
    Dispara refresh das previsões (fixtures + odds + poisson + topscorers)
    e grava em data/predict/predictions.json.

    Auth: Authorization: Bearer <token>  |  X-Endpoint-Key: <token>  |  ?key=<token>
    O <token> deve corresponder a ENDPOINT_API_KEY (ou API_UPDATE_TOKEN/API_TOKEN).
    """
    if not _is_authorized(authorization, x_endpoint_key, key):
        return JSONResponse({"status": "forbidden"}, status_code=403)
    try:
        # Nota: fetch_and_save_predictions() atual não recebe "days".
        out = fetch_and_save_predictions()
        return JSONResponse({"status": "ok", **(out or {})})
    except Exception as e:
        log.exception("Erro no update:")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

@router.get("/leagues")
def leagues():
    """
    Devolve uma LISTA de ligas conhecida a partir de predictions.json.
    - Dedupe por "id"
    - Exclui U-xx e Women
    - Internacionais (Seleções A) primeiro; depois País e Nome
    - Fallback para config/leagues.json se predictions.json faltar
    """
    leagues_map: Dict[int, Dict[str, Any]] = {}

    # 1) predictions.json (fonte principal)
    preds = _read_json("data/predict/predictions.json") or []
    try:
        for p in preds:
            # liga: id correto SEM usar 'league' (nome) como id
            lid = p.get("league_id") or p.get("leagueId")
            try:
                lid = int(lid)
            except Exception:
                continue
            if not lid:
                continue

            name = p.get("league_name") or p.get("league") or ""
            country = p.get("country") or ""

            # excluir juvenis/mulheres pelo nome da liga
            if _is_youth_or_women(name):
                continue

            # registo
            if lid not in leagues_map:
                leagues_map[lid] = {"id": lid, "name": name, "country": country}
            else:
                # preenche campos em falta (se houver)
                if not leagues_map[lid].get("name") and name:
                    leagues_map[lid]["name"] = name
                if not leagues_map[lid].get("country") and country:
                    leagues_map[lid]["country"] = country
    except Exception as e:
        log.warning(f"Falha a extrair ligas de predictions.json: {e}")

    # 2) fallback: config/leagues.json (curadas)
    if not leagues_map:
        cfg = _read_json("config/leagues.json") or []
        try:
            for row in cfg:
                lid = row.get("id") or row.get("league_id")
                try:
                    lid = int(lid)
                except Exception:
                    continue
                if not lid:
                    continue
                name = row.get("name") or row.get("league") or ""
                country = row.get("country") or ""
                if _is_youth_or_women(name):
                    continue
                if lid not in leagues_map:
                    leagues_map[lid] = {"id": lid, "name": name, "country": country}
        except Exception as e:
            log.warning(f"Falha a extrair ligas de config/leagues.json: {e}")

    items: List[Dict[str, Any]] = list(leagues_map.values())

    # ordenação: internacionais primeiro, depois país/nome
    def sort_key(x: Dict[str, Any]):
        intl = 0 if _is_international(x.get("country"), x.get("name")) else 1
        return (intl, (x.get("country") or "ZZZ"), (x.get("name") or ""))

    items.sort(key=sort_key)
    # ⚠️ devolve LISTA simples (frontend espera array)
    return items

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
