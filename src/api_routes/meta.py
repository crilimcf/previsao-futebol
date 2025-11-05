# src/api_routes/meta.py
import os
import json
import logging
from typing import Dict, List, Any
from fastapi import APIRouter

router = APIRouter(prefix="/meta", tags=["meta"])
log = logging.getLogger("meta")

def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        # utf-8-sig para tolerar BOM
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Falha a ler {path}: {e}")
        return None

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
