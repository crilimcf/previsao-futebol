# -*- coding: utf-8 -*-
"""
Treina λ3 (correlação) por liga mantendo os λ_home/λ_away marginais.

Entrada (CSV): data/train/poisson_inputs.csv
  colunas necessárias: league_id, goals_home, goals_away, lambda_home, lambda_away

Saída (JSON): models/bivar_lambda3.json
  formato: {"lambda3_per_league": {"39": 0.12, "61": 0.08, ...}}

Env vars opcionais:
  BIVAR_TRAIN_DATA   -> caminho do CSV (default: data/train/poisson_inputs.csv)
  BIVAR_L3_OUTPUT    -> caminho do JSON (default: models/bivar_lambda3.json)
  BIVAR_MIN_ROWS     -> nº mínimo de jogos por liga (default: 30)
"""

from __future__ import annotations

import os
import sys
import json
import math
from pathlib import Path
from typing import Tuple, Dict

import numpy as np
import pandas as pd
from scipy.optimize import minimize

# --- garantir que a raiz do repositório está no sys.path (para importar src.*) ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# ----------------------------------------------------------------------------------

from src.ml.bivar import bivar_pmf, _safe  # type: ignore

DATA = Path(os.getenv("BIVAR_TRAIN_DATA", "data/train/poisson_inputs.csv"))
OUT = Path(os.getenv("BIVAR_L3_OUTPUT", "models/bivar_lambda3.json"))
MIN_ROWS = int(os.getenv("BIVAR_MIN_ROWS", "30"))


def _nll_for_league(df: pd.DataFrame) -> Tuple[float, float]:
    """
    Calcula o λ3 que minimiza a negative log-likelihood para uma liga.
    Retorna (lambda3, nll).

    Regras:
      - λ3 >= 0
      - λ3 < min(lambda_home, lambda_away) (aproximadamente)
    """
    # limite superior seguro: abaixo do quantil 5% do mínimo (λ_home, λ_away)
    mins = np.minimum(df["lambda_home"].to_numpy(dtype=float),
                      df["lambda_away"].to_numpy(dtype=float))
    l3_upper = float(np.nanquantile(mins, 0.05)) * 0.9 if len(mins) else 0.0
    # salvaguardas
    if not np.isfinite(l3_upper) or l3_upper <= 1e-6:
        l3_upper = 0.8  # fallback conservador (como tinhas)
    l3_upper = max(1e-6, min(l3_upper, 2.0))  # clamp final

    def nll(params: np.ndarray) -> float:
        l3 = max(0.0, float(params[0]))
        s = 0.0
        # penalização dura se λ3 ultrapassar λ mínimo de alguma linha
        # (mesmo com bound, isto protege contra degenerescências numéricas)
        for _, r in df.iterrows():
            lam_h = float(r["lambda_home"])
            lam_a = float(r["lambda_away"])
            safe_min = min(lam_h, lam_a) - 1e-9
            if l3 >= safe_min:
                s += 1e6 * (l3 - safe_min + 1e-6)
                continue

            l1 = max(1e-6, lam_h - l3)
            l2 = max(1e-6, lam_a - l3)
            x = int(r["goals_home"])
            y = int(r["goals_away"])
            p = bivar_pmf(l1, l2, l3, x, y)
            s += -math.log(_safe(p))
        return s

    x0 = min(0.10, l3_upper * 0.5)
    res = minimize(
        nll,
        x0=[x0],
        bounds=[(0.0, l3_upper)],
        method="L-BFGS-B",
    )
    l3_hat = max(0.0, float(res.x[0]))
    return l3_hat, float(res.fun)


def _validate_input(df: pd.DataFrame) -> pd.DataFrame:
    required = {"league_id", "goals_home", "goals_away", "lambda_home", "lambda_away"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV inválido: faltam colunas {sorted(missing)}")

    # tipos & limpeza
    df = df.copy()
    df = df.dropna(subset=list(required))

    # Coerção de tipos
    df["league_id"] = df["league_id"].astype(str)
    for c in ["goals_home", "goals_away"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in ["lambda_home", "lambda_away"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # remover linhas inválidas (λ <= 0)
    df = df[(df["lambda_home"] > 0) & (df["lambda_away"] > 0)]
    return df


def main() -> None:
    if not DATA.exists():
        raise FileNotFoundError(
            f"Falta {DATA}. Exporta primeiro o CSV com λ_home/λ_away e resultados."
        )

    df_raw = pd.read_csv(DATA)
    df = _validate_input(df_raw)

    if df.empty:
        raise ValueError("Dataset vazio após validação.")

    results: Dict[str, float] = {}
    skipped: Dict[str, int] = {}

    for lg, grp in df.groupby("league_id", sort=False):
        n = len(grp)
        if n < MIN_ROWS:
            skipped[str(lg)] = n
            continue
        try:
            l3, _ = _nll_for_league(grp)
            results[str(lg)] = round(l3, 4)
            print(f"[λ3] league {lg}: {results[str(lg)]}  (n={n})")
        except Exception as e:
            print(f"[warn] falhou treino λ3 para liga {lg} (n={n}): {e}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "lambda3_per_league": results,
        "meta": {
            "min_rows": MIN_ROWS,
            "trained_leagues": len(results),
            "skipped_leagues": skipped,  # liga -> nº de linhas (útil p/ debugging)
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✔ gravado: {OUT} ({len(results)} ligas; skipped={len(skipped)})")


if __name__ == "__main__":
    main()
