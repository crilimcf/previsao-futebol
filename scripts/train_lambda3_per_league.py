# -*- coding: utf-8 -*-
"""
Treina λ3 (correlação) por liga mantendo λ_home/λ_away marginais.
Inputs: data/train/poisson_inputs.csv  (gera-se automaticamente no workflow)
Output: models/bivar_lambda3.json
"""

import json, math
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.optimize import minimize

from src.ml.bivar import bivar_pmf, _safe  # usa as tuas funções

DATA = Path("data/train/poisson_inputs.csv")
OUT  = Path("models/bivar_lambda3.json")
MIN_ROWS_PER_LEAGUE = 30     # se menos do que isto, mantemos valor anterior
DEFAULT_L3 = 0.05            # fallback suave

def _neg_loglik_league(df: pd.DataFrame):
    def nll(params):
        l3 = max(0.0, float(params[0]))
        s = 0.0
        for _, r in df.iterrows():
            lam_h = float(r["lambda_home"])
            lam_a = float(r["lambda_away"])
            x, y  = int(r["goals_home"]), int(r["goals_away"])
            l1 = max(1e-6, lam_h - l3)
            l2 = max(1e-6, lam_a - l3)
            p = bivar_pmf(l1, l2, l3, x, y)
            s += -math.log(_safe(p))
        return s
    res = minimize(nll, x0=[0.10], bounds=[(0.0, 0.8)], method="L-BFGS-B")
    return max(0.0, float(res.x[0])), float(res.fun)

def load_prev_model() -> dict:
    if OUT.exists():
        try:
            j = json.loads(OUT.read_text(encoding="utf-8"))
            return j.get("lambda3_per_league", {}) or {}
        except Exception:
            return {}
    return {}

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prev = load_prev_model()

    if not DATA.exists():
        # sem CSV: mantém anterior (ou vazio) e sai sem crash
        OUT.write_text(json.dumps({"lambda3_per_league": prev}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[info] CSV não existe. Mantido modelo anterior. ({OUT})")
        return

    df = pd.read_csv(DATA)
    # valida formato mínimo
    need_cols = {"league_id","goals_home","goals_away","lambda_home","lambda_away"}
    if not need_cols.issubset(set(df.columns)):
        # cabeçalho errado: mantém anterior
        OUT.write_text(json.dumps({"lambda3_per_league": prev}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[info] CSV sem colunas mínimas. Mantido modelo anterior. ({OUT})")
        return

    df = df.dropna(subset=list(need_cols)).copy()
    if df.empty:
        OUT.write_text(json.dumps({"lambda3_per_league": prev}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[info] CSV vazio. Mantido modelo anterior. ({OUT})")
        return

    out = dict(prev)  # parte do anterior
    for lg, grp in df.groupby("league_id"):
        lg = str(lg)
        try:
            if len(grp) < MIN_ROWS_PER_LEAGUE:
                # poucos dados: mantém anterior (ou default)
                out[lg] = float(prev.get(lg, DEFAULT_L3))
                print(f"[λ3] league {lg}: poucos dados ({len(grp)}) -> {out[lg]} (prev/default)")
                continue
            l3, _ = _neg_loglik_league(grp)
            out[lg] = round(l3, 4)
            print(f"[λ3] league {lg}: {out[lg]} (n={len(grp)})")
        except Exception as e:
            out[lg] = float(prev.get(lg, DEFAULT_L3))
            print(f"[λ3] league {lg}: erro '{e}' -> {out[lg]} (prev/default)")

    OUT.write_text(json.dumps({"lambda3_per_league": out}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"gravado: {OUT}")

if __name__ == "__main__":
    main()
