# -*- coding: utf-8 -*-
# Bivariate Poisson utilidades (compatível com o teu pipeline)

from math import exp, factorial
from functools import lru_cache

def _safe(x: float, eps: float = 1e-12) -> float:
    return x if x > eps else eps

@lru_cache(maxsize=None)
def _fact(n: int) -> int:
    return factorial(n)

def bivar_pmf(l1: float, l2: float, l3: float, x: int, y: int) -> float:
    """
    PMF do modelo Bivariate Poisson clássico:
      X = U1 + U3, Y = U2 + U3, com U1~Poi(l1), U2~Poi(l2), U3~Poi(l3)
    """
    l1 = max(1e-8, float(l1))
    l2 = max(1e-8, float(l2))
    l3 = max(0.0, float(l3))
    s = 0.0
    m = min(x, y)
    for k in range(m + 1):
        s += (l1 ** (x - k)) / _fact(x - k) * (l2 ** (y - k)) / _fact(y - k) * (l3 ** k) / _fact(k)
    return exp(-(l1 + l2 + l3)) * s

def score_matrix(lambda_home: float, lambda_away: float, l3: float, max_goals: int = 10):
    """
    Mantém os teus λ marginais:
      E[X]=l1+l3=λ_home  ⇒ l1=λ_home-l3 (≥ε)
      E[Y]=l2+l3=λ_away  ⇒ l2=λ_away-l3 (≥ε)
    """
    l3 = max(0.0, float(l3))
    l1 = max(1e-6, float(lambda_home) - l3)
    l2 = max(1e-6, float(lambda_away) - l3)

    mat = [[0.0]*(max_goals+1) for _ in range(max_goals+1)]
    total = 0.0
    for x in range(max_goals+1):
        for y in range(max_goals+1):
            p = bivar_pmf(l1, l2, l3, x, y)
            mat[x][y] = p
            total += p
    if total > 0:
        inv = 1.0/total
        for x in range(max_goals+1):
            for y in range(max_goals+1):
                mat[x][y] *= inv
    return mat

def aggregate_markets(mat):
    """Extrai 1X2, BTTS, Over/Under 2.5 e Top-3 correct score do score matrix."""
    max_g = len(mat)-1
    p_home = sum(mat[x][y] for x in range(max_g+1) for y in range(max_g+1) if x > y)
    p_draw = sum(mat[x][y] for x in range(max_g+1) for y in range(max_g+1) if x == y)
    p_away = 1.0 - p_home - p_draw

    btts = sum(mat[x][y] for x in range(1, max_g+1) for y in range(1, max_g+1))

    over25 = 0.0
    for x in range(max_g+1):
        for y in range(max_g+1):
            if (x + y) > 2:
                over25 += mat[x][y]

    flat = [((x, y), mat[x][y]) for x in range(max_g+1) for y in range(max_g+1)]
    flat.sort(key=lambda t: t[1], reverse=True)
    top3 = [{"score": f"{a}-{b}", "prob": p} for (a, b), p in flat[:3]]

    return {
        "result_1x2": {"home": p_home, "draw": p_draw, "away": p_away},
        "btts": btts,
        "over_2_5": over25,
        "correct_score_top3": top3,
    }
