# src/ml/blend.py
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
import numpy as np

BLEND_FILE = Path(os.getenv("BLEND_FILE", "models/blend_weights.json"))

def _load_weights() -> Dict[str, float]:
    if BLEND_FILE.exists():
        try:
            data = json.loads(BLEND_FILE.read_text(encoding="utf-8"))
            # formato esperado: {"league_weights": {"39": 0.15, ...}, "defaults": {"1x2":0.15,"binary":0.1}}
            return data
        except Exception:
            pass
    # defaults seguros
    return {"league_weights": {}, "defaults": {"1x2": 0.15, "binary": 0.10}}

def league_weight(league_id: str, kind: str) -> float:
    data = _load_weights()
    w = data.get("league_weights", {}).get(str(league_id))
    if isinstance(w, dict):  # por tipo
        return float(w.get(kind, data.get("defaults", {}).get(kind, 0.15)))
    if isinstance(w, (int, float)) and kind == "1x2":
        return float(w)
    return float(data.get("defaults", {}).get(kind, 0.15))

def probs_from_decimal_odds_1x2(home: Optional[float], draw: Optional[float], away: Optional[float]) -> Tuple[float,float,float]:
    arr = []
    for o in (home, draw, away):
        if o and o > 1.0:
            arr.append(1.0/float(o))
        else:
            arr.append(0.0)
    s = sum(arr)
    if s <= 0:
        return (0.0, 0.0, 0.0)
    # Protege contra odds de mercado extremas: clamp implícitas antes de normalizar
    MIN_PM = 0.02
    MAX_PM = 0.98
    clamped = [max(MIN_PM, min(MAX_PM, v)) if v > 0 else 0.0 for v in arr]
    s2 = sum(clamped)
    if s2 <= 0:
        p = [v/s for v in arr]
    else:
        p = [v/s2 for v in clamped]
    # remover vigorish: renormaliza já cumpre
    return (float(p[0]), float(p[1]), float(p[2]))

def probs_from_decimal_odds_binary(yes: Optional[float], no: Optional[float]) -> Tuple[float,float]:
    arr = []
    for o in (yes, no):
        if o and o > 1.0:
            arr.append(1.0/float(o))
        else:
            arr.append(0.0)
    s = sum(arr)
    if s <= 0:
        return (0.0, 0.0)
    # Clamp market implied probabilities to avoid extreme market odds dominating
    MIN_PM = 0.02
    MAX_PM = 0.98
    clamped = [max(MIN_PM, min(MAX_PM, v)) if v > 0 else 0.0 for v in arr]
    s2 = sum(clamped)
    if s2 <= 0:
        p = [v/s for v in arr]
    else:
        p = [v/s2 for v in clamped]
    return (float(p[0]), float(p[1]))

def blend_triplet(league_id: str, p_model: Tuple[float,float,float], odds: Tuple[Optional[float],Optional[float],Optional[float]]) -> Tuple[float,float,float]:
    p_mkt = probs_from_decimal_odds_1x2(*odds)
    w = league_weight(league_id, "1x2")
    pm = np.array(p_model, dtype=float)
    pk = np.array(p_mkt, dtype=float)
    if pk.sum() <= 0:
        return tuple(pm)  # sem odds, fica modelo
    out = np.clip(w*pk + (1.0 - w)*pm, 0.0, 1.0)
    s = out.sum()
    return tuple((out/s).tolist()) if s>0 else tuple(pm)

def blend_binary(league_id: str, p_yes_model: float, odds: Tuple[Optional[float],Optional[float]], kind: str="binary") -> float:
    p_mkt = probs_from_decimal_odds_binary(*odds)
    w = league_weight(league_id, kind if kind in ("binary","o25","btts") else "binary")
    if sum(p_mkt) <= 0:
        return float(np.clip(p_yes_model, 0.0, 1.0))
    p_yes = float(np.clip(w*p_mkt[0] + (1.0 - w)*p_yes_model, 0.0, 1.0))
    return p_yes
