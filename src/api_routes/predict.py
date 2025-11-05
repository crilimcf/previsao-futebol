# src/api_routes/predict.py
import os
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query, HTTPException

from src import config

router = APIRouter(tags=["predictions"])
log = logging.getLogger("predict")

# Caminhos
PRED_PATH = "data/predict/predictions.json"
STATS_PATH = "data/predict/stats.json"          # mantém o que tinhas
META_PATH = "data/predict/meta.json"
LEAGUES_CFG = "config/leagues.json"
MODEL_DIR = "data/model"
MODEL_PATH = os.path.join(MODEL_DIR, "calibrator.joblib")

# --------------------------------------------------------
# Opcional / retro-compat: calibração logística (a,b)
# --------------------------------------------------------
def _load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _load_ab_calibrators() -> Dict[str, Dict[str, float]]:
    """
    Lê ficheiros antigos de calibração (logit a,b) se existirem.
    Retorna p.e. {"winner":{"a":..,"b":..}, "over_2_5":{...}, "btts":{...}}
    """
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
    """Aplica calibração logística (a,b) a uma probabilidade p."""
    if p is None or cal is None:
        return p
    a = float(cal.get("a", 1.0))
    b = float(cal.get("b", 0.0))
    eps = 1e-6
    x = min(max(float(p), eps), 1 - eps)
    import math
    z = a * math.log(x / (1 - x)) + b
    return 1.0 / (1.0 + math.exp(-z))

# --------------------------------------------------------
# Calibrador via joblib (IsotonicRegression) com cache
# --------------------------------------------------------
_JOBLIB_AVAILABLE = True
try:
    import joblib  # type: ignore
except Exception:
    _JOBLIB_AVAILABLE = False
    joblib = None  # type: ignore

_cal_cache: Dict[str, Any] = {"mtime": 0.0, "model": None}

def _load_joblib_model() -> Optional[Dict[str, Any]]:
    """
    Carrega data/model/calibrator.joblib se existir e se joblib/sklearn estiverem instalados.
    Usa cache por mtime para não reabrir em todos os requests.
    Estrutura esperada:
      {
        "winner": {"home": IsotonicRegression, "draw": ..., "away": ...},
        "over_2_5": IsotonicRegression,
        "btts": IsotonicRegression,
        ... meta ...
      }
    """
    if not _JOBLIB_AVAILABLE or not os.path.exists(MODEL_PATH):
        return None
    try:
        mtime = os.path.getmtime(MODEL_PATH)
    except Exception:
        return None

    if _cal_cache["model"] is not None and _cal_cache["mtime"] == mtime:
        return _cal_cache["model"]

    try:
        model = joblib.load(MODEL_PATH)  # pode requerer scikit-learn instalado
        _cal_cache["model"] = model
        _cal_cache["mtime"] = mtime
        log.info("Calibrador joblib carregado.")
        return model
    except Exception as e:
        log.warning(f"Falha ao carregar calibrator.joblib: {e}")
        return None

def _apply_isotonic(model: Dict[str, Any], label: str, p: Optional[float]) -> Optional[float]:
    """
    Aplica isotonic regression ao valor p conforme o label/mercado.
    - Winner usa model['winner'][home/draw/away]
    - over_2_5 usa model['over_2_5']
    - btts usa model['btts']
    """
    if p is None:
        return None
    try:
        if label in ("home", "draw", "away"):
            f = model.get("winner", {}).get(label)
            if f is None:
                return p
            out = float(f.predict([float(p)])[0])
            return max(0.0, min(1.0, out))
        elif label == "over_2_5":
            f = model.get("over_2_5")
            if f is None:
                return p
            out = float(f.predict([float(p)])[0])
            return max(0.0, min(1.0, out))
        elif label == "btts":
            f = model.get("btts")
            if f is None:
                return p
            out = float(f.predict([float(p)])[0])
            return max(0.0, min(1.0, out))
        else:
            return p
    except Exception:
        return p

# --------------------------------------------------------
# Helpers
# --------------------------------------------------------
def _winner_class_to_key(c: Optional[int]) -> Optional[str]:
    # 0=home, 1=draw, 2=away (convenção do teu pipeline)
    return {0: "home", 1: "draw", 2: "away"}.get(c) if c is not None else None

def _iter_predictions_filtered(data: List[Dict[str, Any]], date: Optional[str], league_id: Optional[str]):
    for row in data:
        if date and (row.get("date") or "").split("T")[0] != date:
            continue
        if league_id and str(row.get("league_id")) != str(league_id):
            continue
        yield row

# --------------------------------------------------------
# /predictions  (com calibração joblib -> fallback logit -> raw)
# --------------------------------------------------------
@router.get("/predictions")
def get_predictions(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    league_id: Optional[str] = Query(None),
    raw: bool = Query(False, description="Se true, não aplica calibração"),
):
    """
    Lê data/predict/predictions.json e aplica calibração:
      1) se existir calibrator.joblib (isotonic), usa-o;
      2) senão se existirem ficheiros (a,b), usa logit;
      3) senão devolve sem calibrar.
    NOTA: como o ficheiro já traz as probs Poisson calculadas,
    aqui só ajustamos as probabilidades (não recalculamos Poisson).
    """
    data = _load_json(PRED_PATH) or []
    if not isinstance(data, list):
        raise HTTPException(status_code=500, detail="predictions.json mal formatado")

    model = None if raw else _load_joblib_model()
    ab_cals = {} if raw or model else _load_ab_calibrators()

    out: List[Dict[str, Any]] = []
    for row in _iter_predictions_filtered(data, date, league_id):
        preds = row.get("predictions") or {}

        # -------- Winner --------
        if "winner" in preds:
            w = preds.get("winner") or {}
            # prob/confidence do "classe vencedora"
            p_raw = w.get("prob", w.get("confidence"))
            c = w.get("class")  # 0,1,2
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

        # -------- Over 2.5 --------
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

        # -------- BTTS --------
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
        out.append(row)

    return out

# --------------------------------------------------------
# /stats (como já tinhas)
# --------------------------------------------------------
@router.get("/stats")
def get_stats():
    return _load_json(STATS_PATH) or {}

# --------------------------------------------------------
# /meta/last-update (como já tinhas)
# --------------------------------------------------------
@router.get("/meta/last-update")
def last_update():
    if config.redis_client:
        lu = config.redis_client.get("football_predictions_last_update")
        return {"last_update": lu or None}
    data = _load_json(META_PATH) or {}
    return {"last_update": data.get("last_update")}

# --------------------------------------------------------
# /meta/leagues  -> lista ligas conhecidas (predictions.json ou config/leagues.json)
# --------------------------------------------------------
@router.get("/meta/leagues")
def meta_leagues(
    date: Optional[str] = Query(None, description="Se fornecido, apenas ligas com jogos nesse dia")
):
    leagues: Dict[str, Dict[str, Any]] = {}

    data = _load_json(PRED_PATH)
    if isinstance(data, list) and data:
        for row in data:
            if date and (row.get("date") or "").split("T")[0] != date:
                continue
            lid = row.get("league_id")
            if lid is None:
                continue
            lid = str(lid)
            name = row.get("league_name") or row.get("league") or ""
            country = row.get("country") or ""
            leagues.setdefault(lid, {"id": lid, "name": name, "country": country, "matches": 0})
            leagues[lid]["matches"] += 1

    # fallback se não houver predictions
    if not leagues and os.path.exists(LEAGUES_CFG):
        try:
            cfg = _load_json(LEAGUES_CFG) or []
            for obj in cfg:
                lid = str(obj.get("id"))
                if not lid:
                    continue
                leagues.setdefault(lid, {
                    "id": lid,
                    "name": obj.get("name") or "",
                    "country": obj.get("country") or "",
                    "matches": 0
                })
        except Exception:
            pass

    # ordena por país/nome
    arr = list(leagues.values())
    arr.sort(key=lambda x: (x.get("country") or "", x.get("name") or ""))
    return {"leagues": arr}

# --------------------------------------------------------
# /meta/update  -> corre o gerador e atualiza ficheiros/redis
# --------------------------------------------------------
@router.post("/meta/update")
def manual_update():
    """
    Chama o teu gerador de previsões (vai à API-Football, reconstrói o predictions.json,
    atualiza Redis/meta). Mantive a tua integração.
    """
    from src.predict import main as predict_main  # type: ignore
    predict_main()
    return {
        "status": "ok",
        "message": "Atualização manual concluída.",
    }
