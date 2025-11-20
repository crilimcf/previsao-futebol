# ============================================================
# scripts/backtest_metrics.py
# ============================================================
import json
import math
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
from datetime import datetime

def brier_score(y_prob, y_true):
    # para 1X2: y_true ∈ {0,1,2}; y_prob=(pH,pD,pA)
    s = 0.0
    n = 0
    for (ph, pdraw, pa), y in zip(y_prob, y_true):
        onehot = np.array([0.0, 0.0, 0.0])
        onehot[int(y)] = 1.0
        p = np.array([ph, pd, pa], dtype=float)
        s += np.sum((p - onehot) ** 2)
        n += 1
    return float(s / max(1, n))

def log_loss(y_prob, y_true, eps=1e-12):
    s = 0.0
    n = 0
    for (ph, pdraw, pa), y in zip(y_prob, y_true):
        p = [ph, pd, pa][int(y)]
        p = max(eps, min(1.0, p))
        s += -math.log(p)
        n += 1
    return float(s / max(1, n))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/train/historico_com_probs.csv")
    ap.add_argument("--out", default="data/stats/metrics.json")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        # output mínimo para /metrics não 404
        out = {
            "status": "missing_history",
            "updated_at": datetime.utcnow().isoformat(),
            "brier": None,
            "logloss": None,
            "accuracy_1x2": None,
        }
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"missing history -> wrote stub {out_path}")
        return

    df = pd.read_csv(csv_path)
    # espera colunas: result (0=home,1=draw,2=away), p_home,p_draw,p_away
    df = df.dropna(subset=["result","p_home","p_draw","p_away"])
    y_true = df["result"].astype(int).tolist()
    y_prob = df[["p_home","p_draw","p_away"]].astype(float).values.tolist()

    brier = brier_score(y_prob, y_true)
    ll    = log_loss(y_prob, y_true)
    acc   = float((df[["p_home","p_draw","p_away"]].idxmax(axis=1).map({"p_home":0,"p_draw":1,"p_away":2}) == df["result"]).mean())

    out = {
        "status": "ok",
        "updated_at": datetime.utcnow().isoformat(),
        "brier": brier,
        "logloss": ll,
        "accuracy_1x2": acc,
        "n": int(len(df))
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"metrics -> {out_path}")

if __name__ == "__main__":
    main()
