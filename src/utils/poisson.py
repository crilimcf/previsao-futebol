# src/utils/poisson.py
from __future__ import annotations
import math
from typing import List, Tuple, Dict

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def score_matrix(lam_home: float, lam_away: float, max_goals: int = 6) -> List[List[float]]:
    mat = []
    for i in range(max_goals + 1):
        row = []
        p_i = poisson_pmf(i, lam_home)
        for j in range(max_goals + 1):
            p_j = poisson_pmf(j, lam_away)
            row.append(p_i * p_j)
        mat.append(row)
    return mat

def probs_from_matrix(mat: List[List[float]]) -> Dict[str, float]:
    max_g = len(mat) - 1
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    p_o15 = 0.0
    p_o25 = 0.0
    p_btts = 0.0

    for i in range(max_g + 1):
        for j in range(max_g + 1):
            p = mat[i][j]
            if i > j: p_home += p
            elif i == j: p_draw += p
            else: p_away += p

            if i + j >= 2: p_o15 += p
            if i + j >= 3: p_o25 += p
            if i >= 1 and j >= 1: p_btts += p

    return {
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "over_1_5": p_o15,
        "over_2_5": p_o25,
        "btts_yes": p_btts
    }

def top_correct_scores(mat: List[List[float]], n: int = 3) -> List[Tuple[str, float]]:
    pairs: List[Tuple[str, float]] = []
    max_g = len(mat) - 1
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            pairs.append((f"{i}-{j}", mat[i][j]))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:n]
