# ===============================================================
# src/ml/train_over25_model.py
# Treina modelo ML para prever probabilidade de Over 2.5 golos
# ===============================================================
import json
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
import joblib

DATA_FILE = Path("data/predict/predictions.json")
MODEL_FILE = Path("data/models/over25_model.pkl")
MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_training_data() -> pd.DataFrame:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"{DATA_FILE} não encontrado.")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for rec in data:
        try:
            lam_home = rec.get("lambda_home") or 1.2
            lam_away = rec.get("lambda_away") or 1.1
            conf = rec.get("confidence", 0.5)
            winner_conf = rec.get("predictions", {}).get("winner", {}).get("confidence", 0.5)
            ou = rec.get("predictions", {}).get("over_2_5", {}).get("class", 0)
            ou_conf = rec.get("predictions", {}).get("over_2_5", {}).get("confidence", 0.5)

            rows.append({
                "lambda_home": lam_home,
                "lambda_away": lam_away,
                "conf": conf,
                "winner_conf": winner_conf,
                "ou_conf": ou_conf,
                "target_over25": ou,  # se houve mais de 2.5 golos
            })
        except Exception:
            continue
    return pd.DataFrame(rows)

def train_model():
    df = load_training_data()
    X = df[["lambda_home", "lambda_away", "conf", "winner_conf", "ou_conf"]]
    y = df["target_over25"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    clf = GradientBoostingClassifier(n_estimators=150, learning_rate=0.05, max_depth=3)
    calibrated = CalibratedClassifierCV(clf, method="isotonic", cv=3)
    calibrated.fit(X_train, y_train)

    acc = calibrated.score(X_test, y_test)
    print(f"✅ Modelo treinado — Acurácia: {acc:.3f}")

    joblib.dump(calibrated, MODEL_FILE)
    print(f"💾 Guardado em {MODEL_FILE}")

if __name__ == "__main__":
    train_model()
