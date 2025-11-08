# scripts/backtest_metrics.py
import json, math
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

OUT = Path("data/stats/metrics.json")

EPS = 1e-12

def brier_multiclass(p: np.ndarray, y_idx: int) -> float:
    # p shape (3,), y_idx in {0,1,2}
    t = np.zeros(3); t[y_idx] = 1.0
    return float(np.sum((p - t)**2))

def logloss_multiclass(p: np.ndarray, y_idx: int) -> float:
    return float(-math.log(max(EPS, float(p[y_idx]))))

def ece_binary(p_yes: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    # Expected Calibration Error
    bins_edges = np.linspace(0,1,bins+1)
    ece = 0.0
    for i in range(bins):
        m = (p_yes >= bins_edges[i]) & (p_yes < bins_edges[i+1] if i<bins-1 else p_yes <= 1)
        if m.sum() == 0: 
            continue
        conf = p_yes[m].mean()
        acc  = y[m].mean()
        ece += (m.mean()) * abs(conf - acc)
    return float(ece)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="historico com probs e resultados")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    # outcome indices
    res = np.where(df["goals_home"]>df["goals_away"], 0, np.where(df["goals_home"]<df["goals_away"], 2, 1))
    p1x2 = df[["p_home","p_draw","p_away"]].to_numpy(dtype=float)
    p1x2 = np.clip(p1x2, 0.0, 1.0); p1x2 = p1x2 / np.maximum(1e-12, p1x2.sum(axis=1, keepdims=True))

    briers = [brier_multiclass(p1x2[i], int(res[i])) for i in range(len(df))]
    lls    = [logloss_multiclass(p1x2[i], int(res[i])) for i in range(len(df))]

    # binários
    over25 = (df["goals_home"] + df["goals_away"] >= 3).astype(int).to_numpy()
    p_o25  = np.clip(df["p_o25"].to_numpy(dtype=float), 0.0, 1.0)

    bttsY  = ( (df["goals_home"]>0) & (df["goals_away"]>0) ).astype(int).to_numpy()
    p_btts = np.clip(df["p_bttsY"].to_numpy(dtype=float), 0.0, 1.0)

    out = {
        "global": {
            "n": int(len(df)),
            "brier_1x2": float(np.mean(briers)) if len(briers) else None,
            "logloss_1x2": float(np.mean(lls)) if len(lls) else None,
            "hitrate_1x2_argmax": float(np.mean(np.argmax(p1x2, axis=1)==res)) if len(df) else None,
            "ece_o25": ece_binary(p_o25, over25),
            "ece_btts": ece_binary(p_btts, bttsY),
        }
    }

    # por liga
    leagues = {}
    for lg, grp in df.groupby("league_id"):
        gres = np.where(grp["goals_home"]>grp["goals_away"], 0, np.where(grp["goals_home"]<grp["goals_away"], 2, 1))
        gp = grp[["p_home","p_draw","p_away"]].to_numpy(dtype=float)
        gp = np.clip(gp, 0.0, 1.0); gp = gp / np.maximum(1e-12, gp.sum(axis=1, keepdims=True))
        b = [brier_multiclass(gp[i], int(gres[i])) for i in range(len(grp))]
        l = [logloss_multiclass(gp[i], int(gres[i])) for i in range(len(grp))]
        o = ((grp["goals_home"]+grp["goals_away"])>=3).astype(int).to_numpy()
        po= np.clip(grp["p_o25"].to_numpy(dtype=float), 0.0, 1.0)
        bb= ((grp["goals_home"]>0)&(grp["goals_away"]>0)).astype(int).to_numpy()
        pb= np.clip(grp["p_bttsY"].to_numpy(dtype=float), 0.0, 1.0)
        leagues[str(lg)] = {
            "n": int(len(grp)),
            "brier_1x2": float(np.mean(b)) if len(b) else None,
            "logloss_1x2": float(np.mean(l)) if len(l) else None,
            "hitrate_1x2_argmax": float(np.mean(np.argmax(gp,axis=1)==gres)) if len(grp) else None,
            "ece_o25": ece_binary(po, o) if len(grp) else None,
            "ece_btts": ece_binary(pb, bb) if len(grp) else None,
        }
    out["by_league"] = leagues

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"gravado: {args.out}")

if __name__ == "__main__":
    main()
