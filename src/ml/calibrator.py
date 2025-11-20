# ============================================================
# src/ml/calibrator.py
# ============================================================
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
from typing import Dict, Tuple, Optional

import joblib

# Estrutura esperada em models/calibrators/:
#  └─ {league_id}_1x2.pkl     -> dict {'home': IsoReg, 'draw': IsoReg, 'away': IsoReg}
#  └─ {league_id}_btts.pkl    -> IsotonicRegression (prob de "Sim")
#  └─ {league_id}_over15.pkl  -> IsotonicRegression (prob de Over 1.5)
#  └─ {league_id}_over25.pkl  -> IsotonicRegression (prob de Over 2.5)

CALDIR = Path("models/calibrators")

def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))

@lru_cache(maxsize=512)
def _load_pkl(path: str):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return joblib.load(p)
    except Exception:
        return None

def calibrate_1x2(league_id: str, ph: float, pd: float, pa: float) -> Tuple[float, float, float]:
    """Calibra probs 1X2 por liga. Se faltar pkl, devolve identity + normalização."""
    fname = CALDIR / f"{league_id}_1x2.pkl"
    model: Optional[Dict[str, any]] = _load_pkl(str(fname))
    ph, pd, pa = map(_clip01, (ph, pd, pa))
    s = ph + pd + pa
    if s <= 0:
        return 1/3, 1/3, 1/3
    ph, pd, pa = ph/s, pd/s, pa/s

    if not model or not all(k in model for k in ("home", "draw", "away")):
        return ph, pd, pa

    try:
        ph_c = float(model["home"].predict([ph])[0])
        pd_c = float(model["draw"].predict([pd])[0])
        pa_c = float(model["away"].predict([pa])[0])
        ph_c, pd_c, pa_c = map(_clip01, (ph_c, pd_c, pa_c))
        s2 = ph_c + pd_c + pa_c
        if s2 <= 0:
            return ph, pd, pa
        return ph_c/s2, pd_c/s2, pa_c/s2
    except Exception:
        return ph, pd, pa

def calibrate_binary(league_id: str, key: str, p: float) -> float:
    """
    key ∈ {'btts','over15','over25'}.
    Se faltar pkl, devolve prob original (clip 0-1).
    """
    fname = CALDIR / f"{league_id}_{key}.pkl"
    model = _load_pkl(str(fname))
    p = _clip01(p)
    if not model:
        return p
    try:
        pc = float(model.predict([p])[0])
        return _clip01(pc)
    except Exception:
        return p
