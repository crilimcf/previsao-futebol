# src/utils/calibrator.py
"""
Calibrador leve para probabilidades (Platt / logistic scaling)
para usar por cima do Poisson ou de um modelo clássico.

Guarda e carrega de JSON.
"""

from __future__ import annotations
import json
import math
import os
from typing import List, Tuple, Dict, Any


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class PlattCalibrator:
    """
    Calibrador binário simples.
    y ∈ {0,1}, p ∈ (0,1)
    """
    def __init__(self, a: float = 1.0, b: float = 0.0, name: str = "default"):
        self.a = a
        self.b = b
        self.name = name

    def predict(self, p: float) -> float:
        z = self.a * _logit(p) + self.b
        return _sigmoid(z)

    # ---------- treino ----------
    def fit(self, probs: List[float], targets: List[int], epochs: int = 200, lr: float = 0.05):
        """
        Treino por gradient descent muito simples.
        probs: lista de probabilidades brutas (0..1)
        targets: 0 ou 1 do que realmente aconteceu
        """
        assert len(probs) == len(targets)
        n = len(probs)
        if n == 0:
            return

        a, b = self.a, self.b

        for _ in range(epochs):
            ga = 0.0
            gb = 0.0
            for p, y in zip(probs, targets):
                z = a * _logit(p) + b
                y_hat = _sigmoid(z)
                # derivada do cross entropy w.r.t z: (y_hat - y)
                dz = (y_hat - y)
                ga += dz * _logit(p)
                gb += dz
            ga /= n
            gb /= n
            a -= lr * ga
            b -= lr * gb

        self.a, self.b = a, b

    # ---------- persistência ----------
    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlattCalibrator":
        return cls(a=float(data.get("a", 1.0)), b=float(data.get("b", 0.0)), name=data.get("name", "default"))

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "PlattCalibrator | None":
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# helpers de alto nível --------------------------------------------------

def calibrate_probs(probs: List[float], targets: List[int], name: str, out_path: str) -> PlattCalibrator:
    cal = PlattCalibrator(name=name)
    cal.fit(probs, targets)
    cal.save(out_path)
    return cal
