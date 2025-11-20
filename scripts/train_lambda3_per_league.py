# ============================================================
# scripts/train_lambda3_per_league.py
# ============================================================
# --- garantir import do pacote local "src" mesmo no CI ---
import sys
from pathlib import Path
import json
import math
import pandas as pd
from scipy.optimize import minimize
from src.ml.bivar import bivar_pmf, _safe
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ----------------------------------------------------------

DATA = Path("data/train/poisson_inputs.csv")
OUT  = Path("models/bivar_lambda3.json")

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
        raise FileNotFoundError(f"Falta {DATA}. Exporta o CSV com λ_home/λ_away e resultados.")
    df = pd.read_csv(DATA)
    df = df.dropna(subset=["league_id","goals_home","goals_away","lambda_home","lambda_away"])
    out = {}
    for lg, grp in df.groupby("league_id"):
        l3, _ = _neg_loglik_league(grp)
        out[str(lg)] = round(l3, 4)
        print(f"[λ3] league {lg}: {out[str(lg)]}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"lambda3_per_league": out}, ensure_ascii=False, indent=2))
    print(f"gravado: {OUT}")

if __name__ == "__main__":
    main()
