# ============================================================
# scripts/export_historico_for_calibration.py
# Gera data/train/historico_com_probs.csv a partir do
# data/train/poisson_inputs.csv (que já tens no CI).
#
# Requisitos do CSV de entrada:
#  - league_id, goals_home, goals_away, lambda_home, lambda_away
# Opcional:
#  - date, match_id, home_team, away_team
#
# Saída:
#  - historico_com_probs.csv com colunas:
#    league_id, result(0/1/2), p_home, p_draw, p_away,
#    (e copia meta: date, match_id, home_team, away_team se houver)
# ============================================================
from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
from src.ml.bivar import bivar_pmf

IN  = Path("data/train/poisson_inputs.csv")
OUT = Path("data/train/historico_com_probs.csv")

def _grid_probs(l1: float, l2: float, l3: float, max_goals: int = 10) -> np.ndarray:
    g = np.zeros((max_goals + 1, max_goals + 1), dtype=float)
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            g[x, y] = bivar_pmf(l1, l2, l3, x, y)
    s = g.sum()
    if s > 0:
        g /= s
    return g

def _probs_1x2(g: np.ndarray):
    ph = np.triu(g, k=1).sum()   # x>y
    pa = np.tril(g, k=-1).sum()  # x<y
    pd = np.trace(g)
    return float(ph), float(pd), float(pa)

def main():
    if not IN.exists():
        print(f"[skip] não encontrei {IN}; nada a fazer.")
        return

    df = pd.read_csv(IN)
    need = {"league_id","goals_home","goals_away","lambda_home","lambda_away"}
    if not need.issubset(df.columns):
        raise SystemExit(f"CSV precisa colunas: {sorted(need)}")

    rows = []
    for _, r in df.dropna(subset=list(need)).iterrows():
        lid = str(r["league_id"])
        gh  = int(r["goals_home"])
        ga  = int(r["goals_away"])
        lh  = float(r["lambda_home"])
        la  = float(r["lambda_away"])

        # λ3 heurístico só para construir histórico (o treino "a sério" de λ3 faz-se noutro job)
        lam3 = max(0.0, min(0.8, min(lh, la) * 0.2))
        l1 = max(1e-6, lh - lam3)
        l2 = max(1e-6, la - lam3)

        g  = _grid_probs(l1, l2, lam3, 10)
        p_home, p_draw, p_away = _probs_1x2(g)

        result = 0 if gh > ga else (2 if gh < ga else 1)

        out = {
            "league_id": lid,
            "result": result,
            "p_home": p_home,
            "p_draw": p_draw,
            "p_away": p_away,
        }
        for k in ("date","match_id","home_team","away_team"):
            if k in df.columns:
                out[k] = r.get(k)
        rows.append(out)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT, index=False, encoding="utf-8")
    print(f"[ok] gravado: {OUT} (n={len(rows)})")

if __name__ == "__main__":
    main()
