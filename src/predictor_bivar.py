# ============================================================
# src/predictor_bivar.py
# ============================================================
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Tuple, List

import numpy as np

from src.ml.bivar import bivar_pmf
from src.ml.calibrator import calibrate_1x2, calibrate_binary  # << NOVO

L3_PATH = Path("models/bivar_lambda3.json")

def _load_lambda3() -> Dict[str, float]:
    if L3_PATH.exists():
        try:
            obj = json.loads(L3_PATH.read_text(encoding="utf-8"))
            d = obj.get("lambda3_per_league", obj)
            return {str(k): float(v) for k, v in d.items()}
        except Exception:
            pass
    return {}

def _default_lambda3(league_id: str) -> float:
    return 0.10

def _grid_probs(l1: float, l2: float, l3: float, max_goals: int = 10) -> np.ndarray:
    g = np.zeros((max_goals + 1, max_goals + 1), dtype=float)
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            g[x, y] = bivar_pmf(l1, l2, l3, x, y)
    s = g.sum()
    if s > 0:
        g /= s
    return g

def _probs_1x2(g: np.ndarray) -> Tuple[float, float, float]:
    ph = np.triu(g, k=1).sum()   # home wins: x>y
    pa = np.tril(g, k=-1).sum()  # away wins: x<y
    pd = np.trace(g)
    return float(ph), float(pd), float(pa)

def _prob_btts(g: np.ndarray) -> float:
    return float(g[1:, 1:].sum())

def _prob_over(g: np.ndarray, line: float) -> float:
    s = 0.0
    max_g = g.shape[0] - 1
    for x in range(max_g + 1):
        for y in range(max_g + 1):
            if (x + y) > line:
                s += g[x, y]
    return float(s)

def _top3_correct_scores(g: np.ndarray) -> List[Dict[str, Any]]:
    flat = []
    max_g = g.shape[0] - 1
    for x in range(max_g + 1):
        for y in range(max_g + 1):
            flat.append((f"{x}-{y}", g[x, y]))
    flat.sort(key=lambda t: t[1], reverse=True)
    res = [{"score": s, "prob": float(p)} for s, p in flat[:3]]
    return res

def enrich_from_file_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    lid = str(rec.get("league_id") or rec.get("leagueId") or "")
    lam_h = float(rec.get("lambda_home") or rec.get("lambdaHome") or 0.0)
    lam_a = float(rec.get("lambda_away") or rec.get("lambdaAway") or 0.0)
    if lam_h <= 0 or lam_a <= 0:
        return rec

    l3map = _load_lambda3()
    l3 = float(l3map.get(lid, _default_lambda3(lid)))

    l1 = max(1e-6, lam_h - l3)
    l2 = max(1e-6, lam_a - l3)

    g = _grid_probs(l1, l2, l3, max_goals=10)

    # --- probs "cruas" do bivariado
    ph_raw, pd_raw, pa_raw = _probs_1x2(g)
    p_btts_raw = _prob_btts(g)
    p_ou25_raw = _prob_over(g, 2.5)
    p_ou15_raw = _prob_over(g, 1.5)

    # --- calibração isotónica por liga (fallback identity)
    ph, pd, pa = calibrate_1x2(lid, ph_raw, pd_raw, pa_raw)
    p_btts = calibrate_binary(lid, "btts",  p_btts_raw)
    p_ou25 = calibrate_binary(lid, "over25", p_ou25_raw)
    p_ou15 = calibrate_binary(lid, "over15", p_ou15_raw)

    top3 = _top3_correct_scores(g)

    out = dict(rec)
    out.setdefault("predictions", {})

    out["predictions"]["winner"] = {
        "class": int(np.argmax([ph, pd, pa])),
        "prob": max(ph, pd, pa),
        "confidence": max(ph, pd, pa),
    }
    out["predictions"]["double_chance"] = {
        "class": int(np.argmax([ph+pd, ph+pa, pd+pa])),
        "prob": max(ph+pd, ph+pa, pd+pa),
    }
    out["predictions"]["over_2_5"] = {"class": int(p_ou25 >= 0.5), "prob": p_ou25}
    out["predictions"]["over_1_5"] = {"class": int(p_ou15 >= 0.5), "prob": p_ou15}
    out["predictions"]["btts"]     = {"class": int(p_btts >= 0.5), "prob": p_btts}
    out["predictions"]["correct_score"] = {
        "best": top3[0]["score"] if top3 else None,
        "top3": top3,
    }

    out["model"] = "bivariate+iso"
    out["lambda_used"] = {"home": lam_h, "away": lam_a, "lambda3": l3}
    return out
