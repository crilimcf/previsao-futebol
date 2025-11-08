# src/ml/calibration.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterable, List
import numpy as np

try:
    from sklearn.isotonic import IsotonicRegression  # noqa
    from joblib import load as joblib_load
except Exception:  # fail-open se não existir
    IsotonicRegression = None
    def joblib_load(*_, **__):
        raise FileNotFoundError("joblib indisponível")

MODELS_DIR = Path(os.getenv("CALIB_MODELS_DIR", "models")) / "calibration"

class IdentityCalibrator:
    def predict(self, x: Iterable[float]) -> np.ndarray:
        arr = np.asarray(list(x), dtype=float)
        return np.clip(arr, 0.0, 1.0)

def load_binary_calibrator(league_id: str, name: str) -> object:
    """
    Carrega um calibrador binário (isotónico) p/ liga. Fallback: identidade.
    Ficheiro esperado: models/calibration/<league_id>/<name>.joblib
    """
    try:
        path = MODELS_DIR / str(league_id) / f"{name}.joblib"
        if path.exists():
            return joblib_load(path)
    except Exception:
        pass
    return IdentityCalibrator()

def calibrate_binary(probs: Iterable[float], calibrator: object) -> np.ndarray:
    x = np.asarray(list(probs), dtype=float)
    x = np.clip(x, 0.0, 1.0)
    try:
        y = calibrator.predict(x)
    except Exception:
        y = x
    return np.clip(y, 0.0, 1.0)

def renorm_binary(p_yes: float) -> tuple[float, float]:
    p = float(np.clip(p_yes, 0.0, 1.0))
    return p, 1.0 - p

def renorm_triplet(p1: float, px: float, p2: float) -> tuple[float, float, float]:
    arr = np.clip(np.array([p1, px, p2], dtype=float), 0.0, 1.0)
    s = arr.sum()
    if s <= 0:
        return (1/3, 1/3, 1/3)
    arr = arr / s
    return tuple(float(v) for v in arr)
