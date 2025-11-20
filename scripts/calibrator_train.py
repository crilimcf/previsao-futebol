#!/usr/bin/env python3
import os
import json
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
import joblib

HISTORY = "data/training/history.jsonl"
MODEL_DIR = "data/model"
MODEL_PATH = f"{MODEL_DIR}/calibrator.joblib"

MIN_SAMPLES = 400        # mínimo total
WINDOW_DAYS = 180        # janela de histórico
RANDOM_SEED = 42

def load_history():
    if not os.path.exists(HISTORY):
        return pd.DataFrame()
    rows = []
    with open(HISTORY, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # filtra janela temporal
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        cutoff = pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=WINDOW_DAYS)
        df = df[df["date"] >= cutoff]
    df = df.dropna(subset=["p_home","p_draw","p_away","p_over25","p_btts","y_home","y_draw","y_away","y_over25","y_btts"])
    return df

def fit_iso(x, y):
    # Isotonic 0..1, monotónica, extrapolação por clip
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return iso

def main():
    df = load_history()
    if len(df) < MIN_SAMPLES:
        print(f"Not enough samples ({len(df)}) — keep current model if any.")
        return 0

    # embaralha para robustez
    df = df.sample(frac=1.0, random_state=RANDOM_SEED)

    # Winner: one-vs-rest calibra p_home, p_draw, p_away
    cal_home = fit_iso(df["p_home"], df["y_home"])
    cal_draw = fit_iso(df["p_draw"], df["y_draw"])
    cal_away = fit_iso(df["p_away"], df["y_away"])

    # Over 2.5
    cal_o25  = fit_iso(df["p_over25"], df["y_over25"])

    # BTTS
    cal_btts = fit_iso(df["p_btts"], df["y_btts"])

    model = {
        "version": 1,
        "trained_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {
            "total": int(len(df)),
            "pos_home": int(df["y_home"].sum()),
            "pos_draw": int(df["y_draw"].sum()),
            "pos_away": int(df["y_away"].sum()),
            "pos_over25": int(df["y_over25"].sum()),
            "pos_btts": int(df["y_btts"].sum()),
        },
        "winner": {"home": cal_home, "draw": cal_draw, "away": cal_away},
        "over_2_5": cal_o25,
        "btts": cal_btts,
    }

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH, compress=3)
    print(f"Saved calibrator to {MODEL_PATH}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
