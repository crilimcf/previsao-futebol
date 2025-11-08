# ============================================================
# src/predictor_bivar.py
# Enriquecimento de um registo de predictions.json com
# probabilidades via Bivariate Poisson (λ1, λ2, λ3).
# - Lê λ3 por liga de models/bivar_lambda3.json (fallback 0.08).
# - Requer λ_home/λ_away no próprio registo; se faltarem -> devolve sem mexer.
# - Calcula 1X2, Over 2.5/1.5, BTTS e Top-3 Correct Score.
# - Nunca lança exceção para não partir o serviço.
# ============================================================

from __future__ import annotations
import json
from math import isfinite
from pathlib import Path
from typing import Any, Dict, Tuple, Optional, List

try:
    # já está no repo
    from src.ml.bivar import bivar_pmf  # type: ignore
except Exception:
    # fallback super defensivo (não deve acontecer)
    def bivar_pmf(l1: float, l2: float, l3: float, x: int, y: int) -> float:  # type: ignore
        return 0.0

_L3_PATH = Path("models/bivar_lambda3.json")
_L3_CACHE: Optional[Tuple[dict, float]] = None  # (mapa, mtime)


def _load_lambda3_map() -> dict:
    global _L3_CACHE
    try:
        mtime = _L3_PATH.stat().st_mtime
        if _L3_CACHE and _L3_CACHE[1] == mtime:
            return _L3_CACHE[0]
        data = json.loads(_L3_PATH.read_text(encoding="utf-8"))
        # aceita {"lambda3_per_league": {...}} ou só {"123": 0.12}
        if isinstance(data, dict) and "lambda3_per_league" in data:
            m = data["lambda3_per_league"] or {}
        else:
            m = data if isinstance(data, dict) else {}
        _L3_CACHE = (m, mtime)
        return m
    except Exception:
        return {}


def _get_str(o: Any, *keys: str) -> str:
    for k in keys:
        v = o.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _get_float(o: Any, *keys: str) -> Optional[float]:
    for k in keys:
        v = o.get(k)
        if v is None:
            continue
        try:
            f = float(v)
            if isfinite(f):
                return f
        except Exception:
            continue
    return None


def _sum_probs(l1: float, l2: float, l3: float, max_goals: int = 10) -> Dict[str, Any]:
    """Gera distribuição conjunta e resume mercados."""
    mat: List[List[float]] = []
    p_home = p_draw = p_away = 0.0
    p_over25 = p_over15 = 0.0
    p_btts = 0.0
    top: List[Tuple[str, float]] = []

    for x in range(max_goals + 1):
        row = []
        for y in range(max_goals + 1):
            p = bivar_pmf(l1, l2, l3, x, y)
            row.append(p)
            if x > y:
                p_home += p
            elif x == y:
                p_draw += p
            else:
                p_away += p
            if (x + y) >= 3:
                p_over25 += p
            if (x + y) >= 2:
                p_over15 += p
            if x >= 1 and y >= 1:
                p_btts += p
            top.append((f"{x}-{y}", p))
        mat.append(row)

    # top-3 correct scores
    top.sort(key=lambda t: t[1], reverse=True)
    top3 = [{"score": s, "prob": round(max(0.0, min(1.0, p)), 6)} for s, p in top[:3]]

    return {
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_over25": p_over25,
        "p_over15": p_over15,
        "p_btts": p_btts,
        "top3": top3,
    }


def _double_chance(p_home: float, p_draw: float, p_away: float) -> Tuple[int, float]:
    """Retorna (classe, prob) onde classe: 0=1X, 1=12, 2=X2."""
    opts = [
        (0, p_home + p_draw),  # 1X
        (1, p_home + p_away),  # 12
        (2, p_draw + p_away),  # X2
    ]
    opts.sort(key=lambda t: t[1], reverse=True)
    return opts[0]


def enrich_from_file_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriquecimento seguro. Se faltar algo essencial, devolve o registo inalterado.
    Espera:
      - rec["lambda_home"], rec["lambda_away"]  (marginais já calculados no teu pipeline)
      - league_id para buscar λ3; fallback l3=0.08
    """
    try:
        lam_h = _get_float(rec, "lambda_home", "lam_home", "lambdaH")
        lam_a = _get_float(rec, "lambda_away", "lam_away", "lambdaA")
        if lam_h is None or lam_a is None or lam_h <= 0 or lam_a <= 0:
            return rec  # sem marginais, não faço nada

        # λ3 por liga
        lg = _get_str(rec, "league_id", "leagueId", "league", "league_code")
        l3_map = _load_lambda3_map()
        lam3 = float(l3_map.get(str(lg), 0.08))
        lam1 = max(1e-6, lam_h - lam3)
        lam2 = max(1e-6, lam_a - lam3)

        s = _sum_probs(lam1, lam2, lam3, max_goals=10)
        p_home = s["p_home"]
        p_draw = s["p_draw"]
        p_away = s["p_away"]

        # Winner
        winner_class = int(max(enumerate([p_home, p_draw, p_away]), key=lambda t: t[1])[0])  # 0=Casa,1=Empate,2=Fora
        winner_prob = [p_home, p_draw, p_away][winner_class]

        # Double chance
        dc_class, dc_prob = _double_chance(p_home, p_draw, p_away)

        # O/U & BTTS
        p_o25 = s["p_over25"]
        p_o15 = s["p_over15"]
        p_btts = s["p_btts"]

        # Monta estrutura de saída compatível com o frontend
        out = dict(rec)  # shallow copy
        preds = dict(out.get("predictions") or {})

        preds["winner"] = {"class": winner_class, "prob": round(winner_prob, 6)}
        preds["double_chance"] = {"class": dc_class, "prob": round(dc_prob, 6)}
        preds["over_2_5"] = {"class": int(p_o25 >= 0.5), "prob": round(p_o25, 6)}
        preds["over_1_5"] = {"class": int(p_o15 >= 0.5), "prob": round(p_o15, 6)}
        preds["btts"] = {"class": int(p_btts >= 0.5), "prob": round(p_btts, 6)}
        preds["correct_score"] = {
            "best": s["top3"][0]["score"] if s["top3"] else None,
            "top3": s["top3"],
        }

        out["predictions"] = preds
        out["model"] = "v2-bivar"
        out["lambda_used"] = {"home": lam_h, "away": lam_a, "l3": lam3}
        return out
    except Exception:
        return rec  # nunca quebrar
