# scripts/train_lambda3_per_league.py
import json, math
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.optimize import minimize

DATA = Path("data/train/poisson_inputs.csv")
OUT  = Path("models/bivar_lambda3.json")

def _safe(x: float) -> float:
    return max(1e-12, min(1.0, float(x)))

def bivar_pmf(l1: float, l2: float, l3: float, x: int, y: int) -> float:
    # PMF diagonal-inflated (modelo Marshall–Olkin simplificado)
    # fallback: produto de Poisson quando l3~0
    from math import exp, factorial
    l1 = max(1e-6, float(l1)); l2 = max(1e-6, float(l2)); l3 = max(0.0, float(l3))
    # aproximação segura (se quiseres, substitui pelo teu bivar oficial)
    lam_x = l1 + l3
    lam_y = l2 + l3
    px = (lam_x**x)*exp(-lam_x)/max(1, factorial(x))
    py = (lam_y**y)*exp(-lam_y)/max(1, factorial(y))
    # pequeno acoplamento diagonal: reforço nas células x==y proporcional a l3
    if x == y:
        return _safe(px*py*(1.0 + min(0.3, l3)))
    return _safe(px*py)

def _neg_loglik_league(df):
    def nll(params):
        l3 = max(0.0, float(params[0]))
        s = 0.0
        for _, r in df.iterrows():
            lam_h = float(r["lambda_home"])
            lam_a = float(r["lambda_away"])
            x, y   = int(r["goals_home"]), int(r["goals_away"])
            l1 = max(1e-6, lam_h - l3)
            l2 = max(1e-6, lam_a - l3)
            p = bivar_pmf(l1, l2, l3, x, y)
            s += -math.log(_safe(p))
        return s
    res = minimize(nll, x0=[0.10], bounds=[(0.0, 0.8)], method="L-BFGS-B")
    return max(0.0, float(res.x[0])), float(res.fun)

def main():
    if not DATA.exists():
        raise FileNotFoundError(f"Falta {DATA}. Exporta primeiro o CSV com λ_home/λ_away e resultados.")
    df = pd.read_csv(DATA)
    df = df.dropna(subset=["league_id","goals_home","goals_away","lambda_home","lambda_away"])
    out = {}
    for lg, grp in df.groupby("league_id"):
        l3, _ = _neg_loglik_league(grp)
        out[str(int(lg))] = round(l3, 4)
        print(f"[λ3] league {int(lg)}: {out[str(int(lg))]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"lambda3_per_league": out}, ensure_ascii=False, indent=2))
    print(f"gravado: {OUT}")

if __name__ == "__main__":
    main()
