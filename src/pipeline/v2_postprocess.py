# src/pipeline/v2_postprocess.py
from __future__ import annotations
from typing import Dict, Any, Tuple
from src.ml.calibration import load_binary_calibrator, calibrate_binary, renorm_binary, renorm_triplet
from src.ml.blend import blend_triplet, blend_binary

def _num(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def _extract_model_1x2(p: Dict[str, Any]) -> Tuple[float,float,float]:
    # aceita winner.class + confidence/prob ou winner probs diretas
    w = (p or {}).get("winner", {})
    # se vier como probs diretas
    for k in ("home","draw","away"):
        if isinstance(w.get(k), (int,float)):
            h = _num(w.get("home"), 0.33)
            d = _num(w.get("draw"), 0.33)
            a = _num(w.get("away"), 0.34)
            return renorm_triplet(h, d, a)
    # senão, usar classe + prob como “força” (fallback simples)
    cl = w.get("class", None)  # 0=home,1=draw,2=away
    pr = _num(w.get("prob"), None) or _num(w.get("confidence"), None) or 0.5
    base = [0.25, 0.25, 0.25]
    if cl in (0,1,2):
        base[cl] = float(pr)
        rest = (1.0 - base[cl]) / 2.0
        for i in range(3):
            if i != cl:
                base[i] = rest
    return renorm_triplet(*base)

def _extract_model_binary(node: Dict[str, Any]) -> float:
    # aceita 'prob/confidence' (1=Sim)
    p = _num(node.get("prob"), None)
    if p is None:
        p = _num(node.get("confidence"), 0.5)
    return float(max(0.0, min(1.0, p)))

def _extract_odds_1x2(odds: Dict[str, Any]) -> Tuple[float,float,float]:
    o = odds.get("winner") or odds.get("1x2") or {}
    return (_num(o.get("home"), None), _num(o.get("draw"), None), _num(o.get("away"), None))

def _extract_odds_binary(odds: Dict[str, Any], key_yes="yes", key_no="no") -> Tuple[float,float]:
    o = odds or {}
    return (_num(o.get(key_yes), None), _num(o.get(key_no), None))

def postprocess_item(item: Dict[str, Any], league_id: str) -> Dict[str, Any]:
    preds = (item or {}).get("predictions", {}) or {}
    odds  = (item or {}).get("odds", {}) or {}

    # ------- 1X2 -------
    p_model_1x2 = _extract_model_1x2(preds)
    p_blended_1x2 = blend_triplet(league_id, p_model_1x2, _extract_odds_1x2(odds))
    item.setdefault("v2", {})["p1x2"] = {
        "model": {"home": p_model_1x2[0], "draw": p_model_1x2[1], "away": p_model_1x2[2]},
        "final": {"home": p_blended_1x2[0], "draw": p_blended_1x2[1], "away": p_blended_1x2[2]},
    }

    # ------- O/U 2.5 -------
    ou25 = preds.get("over_2_5") or {}
    p_yes_model = _extract_model_binary(ou25)
    # calibrar binário (se existir)
    cal_ou25 = load_binary_calibrator(league_id, "ou25")
    p_yes_cal = float(calibrate_binary([p_yes_model], cal_ou25)[0])
    p_yes_final = blend_binary(league_id, p_yes_cal, _extract_odds_binary((odds.get("over_2_5") or {}), "over", "under"), "o25")
    py, pn = renorm_binary(p_yes_final)
    item["v2"]["ou25"] = {"model": p_yes_model, "calibrated": p_yes_cal, "final": {"over": py, "under": pn}}

    # ------- BTTS -------
    btts = preds.get("btts") or {}
    p_yes_model = _extract_model_binary(btts)
    cal_btts = load_binary_calibrator(league_id, "btts")
    p_yes_cal = float(calibrate_binary([p_yes_model], cal_btts)[0])
    p_yes_final = blend_binary(league_id, p_yes_cal, _extract_odds_binary((odds.get("btts") or {}), "yes", "no"), "btts")
    py, pn = renorm_binary(p_yes_final)
    item["v2"]["btts"] = {"model": p_yes_model, "calibrated": p_yes_cal, "final": {"yes": py, "no": pn}}

    return item
