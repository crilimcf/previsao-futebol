# src/ml/calibrator.py
import json, os, math
from typing import Dict

CALIB_PATH = "data/meta/calibration.json"

def _sigmoid(z: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-z))
    except OverflowError:
        return 0.0 if z < 0 else 1.0

def _logit(p: float) -> float:
    eps = 1e-6
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))

def load_coeffs(path: str = CALIB_PATH) -> Dict[str, Dict[str, float]]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or {}

def save_coeffs(coeffs: Dict[str, Dict[str, float]], path: str = CALIB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(coeffs, f, ensure_ascii=False, indent=2)

def calibrate_prob(p: float, model: str, coeffs: Dict[str, Dict[str, float]] | None = None) -> float:
    """Aplica Platt-like: sigmoid(a*logit(p)+b). Se não houver coeficientes, devolve p."""
    coeffs = coeffs or load_coeffs()
    ab = (coeffs.get(model) or {})
    a = float(ab.get("a", 1.0))
    b = float(ab.get("b", 0.0))
    return _sigmoid(a * _logit(float(p)) + b)
