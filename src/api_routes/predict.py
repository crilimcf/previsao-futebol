# src/api_routes/predict.py
import os
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, HTTPException

from src import config

router = APIRouter(tags=["predictions"])
log = logging.getLogger("predict")

# Caminhos
PRED_PATH   = "data/predict/predictions.json"
STATS_PATH  = "data/predict/stats.json"
META_PATH   = "data/predict/meta.json"
LEAGUES_CFG = "config/leagues.json"
MODEL_DIR   = "data/model"
MODEL_PATH  = os.path.join(MODEL_DIR, "calibrator.joblib")


# ------------------ utils ------------------
def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ------------------ leagues allowlist ------------------
def _load_leagues_cfg() -> Dict[str, Dict[str, Any]]:
    """
    Lê config/leagues.json (a tua lista oficial) e devolve
    um dicionário { "id_str": {id, name, country, type} }.
    """
    res: Dict[str, Dict[str, Any]] = {}
    cfg = _load_json(LEAGUES_CFG) or []
    if isinstance(cfg, list):
        for obj in cfg:
            lid = obj.get("id")
            if lid is None:
                continue
            lid_str = str(lid)
            res[lid_str] = {
                "id": lid_str,
                "name": obj.get("name") or "",
                "country": obj.get("country") or "",
                "type": obj.get("type") or "",
            }
    return res


# -------- calib (a,b) retro-compat --------
def _load_ab_calibrators() -> Dict[str, Dict[str, float]]:
    res: Dict[str, Dict[str, float]] = {}
    idx_path = os.path.join(MODEL_DIR, "calibration.json")
    if os.path.exists(idx_path):
        try:
            data = _load_json(idx_path) or {}
            for k, v in data.items():
                if isinstance(v, dict) and "a" in v and "b" in v:
                    res[k] = {"a": float(v["a"]), "b": float(v["b"])}
        except Exception as e:
            log.warning(f"Falha a ler calibration.json: {e}")

    for fname, key in [
        ("cal_winner.json", "winner"),
        ("cal_over25.json", "over_2_5"),
        ("cal_btts.json", "btts"),
    ]:
        path = os.path.join(MODEL_DIR, fname)
        if key not in res and os.path.exists(path):
            try:
                v = _load_json(path) or {}
                if "a" in v and "b" in v:
                    res[key] = {"a": float(v["a"]), "b": float(v["b"])}
            except Exception:
                pass
    return res


def _calibrate_logit(p: Optional[float], cal: Optional[Dict[str, float]]) -> Optional[float]:
    if p is None or cal is None:
        return p
    a = float(cal.get("a", 1.0))
    b = float(cal.get("b", 0.0))
    eps = 1e-6
    import math
    x = min(max(float(p), eps), 1 - eps)
    z = a * math.log(x / (1 - x)) + b
    return 1.0 / (1.0 + math.exp(-z))


# -------- joblib (isotonic) com cache --------
_JOBLIB_AVAILABLE = True
try:
    import joblib  # type: ignore
except Exception:
    _JOBLIB_AVAILABLE = False
    joblib = None  # type: ignore

_cal_cache: Dict[str, Any] = {"mtime": 0.0, "model": None}


def _load_joblib_model() -> Optional[Dict[str, Any]]:
    if not _JOBLIB_AVAILABLE or not os.path.exists(MODEL_PATH):
        return None
    try:
        mtime = os.path.getmtime(MODEL_PATH)
    except Exception:
        return None

    if _cal_cache["model"] is not None and _cal_cache["mtime"] == mtime:
        return _cal_cache["model"]

    try:
        model = joblib.load(MODEL_PATH)
        _cal_cache["model"] = model
        _cal_cache["mtime"] = mtime
        log.info("Calibrador joblib carregado.")
        return model
    except Exception as e:
        log.warning(f"Falha ao carregar calibrator.joblib: {e}")
        return None


def _apply_isotonic(model: Dict[str, Any], label: str, p: Optional[float]) -> Optional[float]:
    if p is None:
        return None
    try:
        if label in ("home", "draw", "away"):
            f = model.get("winner", {}).get(label)
        else:
            f = model.get(label)
        if f is None:
            return p
        out = float(f.predict([float(p)])[0])
        return max(0.0, min(1.0, out))
    except Exception:
        return p


# ------------------ helpers ------------------
def _winner_class_to_key(c: Optional[int]) -> Optional[str]:
    return {0: "home", 1: "draw", 2: "away"}.get(c) if c is not None else None


def _iter_predictions_filtered(
    data: List[Dict[str, Any]],
    date: Optional[str],
    league_id: Optional[str],
):
    for row in data:
        row_ymd = row.get("date_ymd") or (row.get("date") or "")[:10]
        if date and row_ymd != date:
            continue
        if league_id and str(row.get("league_id")) != str(league_id):
            continue
        yield row


# ------------------ /predictions ------------------
@router.get("/predictions")
def get_predictions(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    raw: bool = Query(False, description="Se true, não aplica calibração"),
):
    data = _load_json(PRED_PATH) or []
    if not isinstance(data, list):
        raise HTTPException(status_code=500, detail="predictions.json mal formatado")

    model = None if raw else _load_joblib_model()
    ab_cals = {} if raw or model else _load_ab_calibrators()

    out: List[Dict[str, Any]] = []
    for row in _iter_predictions_filtered(data, date, league_id):
        preds = row.get("predictions") or {}

        # Winner
        if "winner" in preds:
            w = preds.get("winner") or {}
            # prob == confidence (retro-compat)
            p_raw = w.get("prob", w.get("confidence"))
            c = w.get("class")
            cls_key = _winner_class_to_key(c)

            if model and cls_key:
                p_adj = _apply_isotonic(model, cls_key, p_raw)
            elif ab_cals.get("winner") and p_raw is not None:
                p_adj = _calibrate_logit(p_raw, ab_cals.get("winner"))
            else:
                p_adj = p_raw

            if p_adj is not None:
                preds["winner"]["prob"] = float(p_adj)
                preds["winner"]["confidence"] = float(p_adj)

        # Over 2.5
        if "over_2_5" in preds:
            o = preds.get("over_2_5") or {}
            p_raw = o.get("prob", o.get("confidence"))
            if model:
                p_adj = _apply_isotonic(model, "over_2_5", p_raw)
            elif ab_cals.get("over_2_5") and p_raw is not None:
                p_adj = _calibrate_logit(p_raw, ab_cals.get("over_2_5"))
            else:
                p_adj = p_raw
            if p_adj is not None:
                preds["over_2_5"]["prob"] = float(p_adj)
                preds["over_2_5"]["confidence"] = float(p_adj)

        # BTTS
        if "btts" in preds:
            b = preds.get("btts") or {}
            p_raw = b.get("prob", b.get("confidence"))
            if model:
                p_adj = _apply_isotonic(model, "btts", p_raw)
            elif ab_cals.get("btts") and p_raw is not None:
                p_adj = _calibrate_logit(p_raw, ab_cals.get("btts"))
            else:
                p_adj = p_raw
            if p_adj is not None:
                preds["btts"]["prob"] = float(p_adj)
                preds["btts"]["confidence"] = float(p_adj)

        row["predictions"] = preds

        # ---------- Compat extra para marcadores prováveis ----------
        # Se vierem em {"home": [...], "away": [...]}, expõe também
        # chaves simples que o frontend possa usar diretamente.
        ps = row.get("probable_scorers") or {}
        if isinstance(ps, dict):
            row.setdefault("probable_scorers_home", ps.get("home") or [])
            row.setdefault("probable_scorers_away", ps.get("away") or [])

        out.append(row)

    return out


# ------------------ /stats ------------------
@router.get("/stats")
def get_stats():
    return _load_json(STATS_PATH) or {}


# ------------------ /meta/last-update ------------------
@router.get("/meta/last-update")
def last_update():
    if config.redis_client:
        lu = config.redis_client.get("football_predictions_last_update")
        return {"last_update": lu or None}
    data = _load_json(META_PATH) or {}
    return {"last_update": data.get("last_update")}


# ------------------ /meta/leagues ------------------
@router.get("/meta/leagues")
def meta_leagues(
    date: Optional[str] = Query(None, description="Se fornecido, apenas ligas com jogos nesse dia"),
):
    """
    Lista de ligas visíveis no frontend.
    - Usa sempre o allowlist de config/leagues.json
    - Só conta 'matches' para ligas que existem no ficheiro de config.
    """
    allowed_map = _load_leagues_cfg()  # { "id_str": {id,name,country,type} }
    allowed_ids = set(allowed_map.keys())

    leagues: Dict[str, Dict[str, Any]] = {}

    data = _load_json(PRED_PATH)
    if isinstance(data, list) and data:
        for row in data:
            row_ymd = row.get("date_ymd") or (row.get("date") or "")[:10]
            if date and row_ymd != date:
                continue

            lid = row.get("league_id")
            if lid is None:
                continue
            lid_str = str(lid)

            # Se houver allowlist e esta liga não estiver lá -> ignora
            if allowed_ids and lid_str not in allowed_ids:
                continue

            meta = allowed_map.get(lid_str, {})
            name = meta.get("name") or row.get("league_name") or row.get("league") or ""
            country = meta.get("country") or row.get("country") or ""

            leagues.setdefault(
                lid_str,
                {
                    "id": lid_str,
                    "name": name,
                    "country": country,
                    "matches": 0,
                },
            )
            leagues[lid_str]["matches"] += 1

    # fallback se não houver matches (por ex. dia sem jogos / predictions vazio)
    if not leagues and allowed_map:
        for lid_str, meta in allowed_map.items():
            leagues.setdefault(
                lid_str,
                {
                    "id": lid_str,
                    "name": meta.get("name") or "",
                    "country": meta.get("country") or "",
                    "matches": 0,
                },
            )

    arr = list(leagues.values())
    arr.sort(key=lambda x: (x.get("country") or "", x.get("name") or ""))
    return {"leagues": arr}


# ------------------ /meta/update ------------------
@router.post("/meta/update")
def manual_update():
    """
    Chama o gerador de previsões (vai à API-Football, reconstrói
    predictions.json e atualiza meta/Redis).
    """
    from src.fetch_matches import fetch_today_matches

    res = fetch_today_matches()
    return {"status": "ok", "result": res}
