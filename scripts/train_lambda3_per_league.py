# scripts/train_lambda3_per_league.py
import json, math
from pathlib import Path
import pandas as pd
from scipy.optimize import minimize

from src.ml.bivar import bivar_pmf, _safe

DATA = Path("data/train/poisson_inputs.csv")
OUT  = Path("models/bivar_lambda3.json")

def _neg_loglik_league(df):
    def nll(params):
        l3 = max(0.0, float(params[0]))
        s = 0.0
        for _, r in df.iterrows():
            l1 = max(1e-6, float(r["lambda_home"]) - l3)
            l2 = max(1e-6, float(r["lambda_away"]) - l3)
            x, y = int(r["goals_home"]), int(r["goals_away"])
            p = bivar_pmf(l1, l2, l3, x, y)
            s += -math.log(_safe(p))
        return s
    res = minimize(nll, x0=[0.10], bounds=[(0.0, 0.8)], method="L-BFGS-B")
    return max(0.0, float(res.x[0])), float(res.fun)

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not DATA.exists():
        print(f"[λ3] CSV não encontrado: {DATA} — escrevendo vazio e saindo 0.")
        OUT.write_text(json.dumps({"lambda3_per_league": {}}, ensure_ascii=False, indent=2))
        return

    df = pd.read_csv(DATA)
    needed = {"league_id","goals_home","goals_away","lambda_home","lambda_away"}
    if df.empty or not needed.issubset(df.columns):
        print("[λ3] CSV vazio/colunas em falta — escrevendo vazio.")
        OUT.write_text(json.dumps({"lambda3_per_league": {}}, ensure_ascii=False, indent=2))
        return

    df = df.dropna(subset=list(needed))
    out = {}
    for lg, grp in df.groupby("league_id"):
        try:
            l3, _ = _neg_loglik_league(grp)
            out[str(lg)] = round(l3, 4)
            print(f"[λ3] league {lg}: {out[str(lg)]}")
        except Exception as e:
            print(f"[λ3] erro liga {lg}: {e}")

    OUT.write_text(json.dumps({"lambda3_per_league": out}, ensure_ascii=False, indent=2))
    print(f"[λ3] gravado: {OUT}")

if __name__ == "__main__":
    main()
