# ===============================================================
# src/ml/predict_over25.py
# Lê modelo treinado e prevê probabilidade ajustada Over 2.5
# ===============================================================
import joblib
import numpy as np
from pathlib import Path

MODEL_FILE = Path("data/models/over25_model.pkl")

_model = None

def _load_model():
    global _model
    if _model is None and MODEL_FILE.exists():
        try:
            _model = joblib.load(MODEL_FILE)
            print("🤖 Modelo ML Over2.5 carregado.")
        except Exception as e:
            print(f"⚠️ Falha ao carregar modelo: {e}")

def predict_over25(lambda_home: float, lambda_away: float, conf: float, winner_conf: float, ou_conf: float) -> float:
    _load_model()
    if not _model:
        return ou_conf  # fallback: mantém o valor Poisson

    X = np.array([[lambda_home, lambda_away, conf, winner_conf, ou_conf]])
    try:
        proba = _model.predict_proba(X)[0][1]
        return float(proba)
    except Exception:
        return ou_conf
