from __future__ import annotations
from typing import Optional, Tuple
from pathlib import Path

from src.ml import calibrator as _cal


def load_binary_calibrator(league_id: str, key: str):
    """Carrega o pkl do calibrador binário (se existir).

    Retorna o objeto (ou None) que pode ser passado para `calibrate_binary`.
    """
    fname = Path(_cal.CALDIR) / f"{league_id}_{key}.pkl"
    return _cal._load_pkl(str(fname))


def calibrate_binary(probs: list[float], model) -> list[float]:
    """Aplica o calibrador (ou identity se model for None). Espera lista de probs e devolve lista."""
    out = []
    if not model:
        return [float(max(0.0, min(1.0, p))) for p in probs]
    try:
        for p in probs:
            v = float(model.predict([float(max(0.0, min(1.0, p)))])[0])
            out.append(max(0.0, min(1.0, v)))
        return out
    except Exception:
        return [float(max(0.0, min(1.0, p))) for p in probs]


def renorm_binary(p: float) -> Tuple[float, float]:
    p = float(max(0.0, min(1.0, p)))
    return p, float(max(0.0, min(1.0, 1.0 - p)))


def renorm_triplet(a: float, b: float, c: float) -> Tuple[float, float, float]:
    vals = [max(0.0, min(1.0, float(a))), max(0.0, min(1.0, float(b))), max(0.0, min(1.0, float(c)))]
    s = sum(vals)
    if s <= 0:
        return 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0
    return vals[0] / s, vals[1] / s, vals[2] / s
