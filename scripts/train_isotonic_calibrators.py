# ============================================================
# scripts/train_isotonic_calibrators.py
# ============================================================
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

# ---- Config ----
MIN_SAMPLES = 150  # mínimo por liga para calibrar
EPS = 1e-9


# ------------------------------
# Utilitários
# ------------------------------
def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _clip01(a) -> np.ndarray:
    x = np.asarray(a, dtype=float)
    return np.clip(x, EPS, 1.0 - EPS)


def _has_two_classes(y: np.ndarray) -> bool:
    u = np.unique(y.astype(int))
    return u.size >= 2 and not (u.size == 1)


def _has_variation(x: np.ndarray) -> bool:
    # Isotonic precisa de variação em x
    return np.nanstd(x) > 0.0


def _ok_for_isotonic(x: np.ndarray, y: np.ndarray) -> bool:
    return len(x) >= MIN_SAMPLES and _has_two_classes(y) and _has_variation(x)


def _train_binary(x, y) -> Optional[IsotonicRegression]:
    x = _clip01(x)
    y = np.asarray(y, dtype=float)
    if not _ok_for_isotonic(x, y):
        return None
    try:
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(x, y)
        return iso
    except Exception:
        return None


def _derive_results_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante colunas: result (0=home,1=draw,2=away),
                     btts_result (0/1),
                     over15_result (0/1),
                     over25_result (0/1)
    Se *_result faltarem mas existir home_goals/away_goals, derivamos.
    """
    out = df.copy()
    # result 1x2
    if "result" not in out.columns:
        if {"home_goals", "away_goals"}.issubset(out.columns):
            hg = out["home_goals"].astype(float)
            ag = out["away_goals"].astype(float)
            res = np.where(hg > ag, 0, np.where(hg < ag, 2, 1))
            out["result"] = res.astype(int)
        else:
            raise SystemExit("CSV precisa de 'result' OU de 'home_goals' e 'away_goals'.")

    # btts_result
    if "btts_result" not in out.columns and {"home_goals", "away_goals"}.issubset(out.columns):
        out["btts_result"] = ((out["home_goals"] > 0) & (out["away_goals"] > 0)).astype(int)

    # over15_result
    if "over15_result" not in out.columns and {"home_goals", "away_goals"}.issubset(out.columns):
        out["over15_result"] = ((out["home_goals"] + out["away_goals"]) >= 2).astype(int)

    # over25_result
    if "over25_result" not in out.columns and {"home_goals", "away_goals"}.issubset(out.columns):
        out["over25_result"] = ((out["home_goals"] + out["away_goals"]) >= 3).astype(int)

    return out


def _train_1x2(df: pd.DataFrame) -> Optional[Dict[str, IsotonicRegression]]:
    """
    One-vs-rest: calibramos 3 modelos (home/draw/away) separadamente.
    Na aplicação, depois renormalizas para somar 1.
    """
    if not {"p_home", "p_draw", "p_away", "result"}.issubset(df.columns):
        return None

    x_home = df["p_home"].to_numpy(dtype=float)
    x_draw = df["p_draw"].to_numpy(dtype=float)
    x_away = df["p_away"].to_numpy(dtype=float)
    y = df["result"].to_numpy(dtype=int)

    m_home = _train_binary(x_home, (y == 0).astype(int))
    m_draw = _train_binary(x_draw, (y == 1).astype(int))
    m_away = _train_binary(x_away, (y == 2).astype(int))

    if m_home and m_draw and m_away:
        return {"home": m_home, "draw": m_draw, "away": m_away}
    return None


def _train_binary_if_present(
    grp: pd.DataFrame,
    p_col: str,
    y_col: str,
) -> Tuple[Optional[IsotonicRegression], str]:
    if p_col in grp.columns and y_col in grp.columns:
        m = _train_binary(grp[p_col].to_numpy(dtype=float), grp[y_col].to_numpy(dtype=int))
        if m:
            return m, "ok"
        return None, "dados insuficientes"
    return None, "colunas em falta"


# ------------------------------
# Main
# ------------------------------
def main():
    ap = argparse.ArgumentParser(description="Treina calibradores isotónicos por liga.")
    ap.add_argument("--csv", default="data/train/historico_com_probs.csv")
    ap.add_argument("--outdir", default="models/calibrators")
    ap.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    args = ap.parse_args()

    global MIN_SAMPLES
    MIN_SAMPLES = int(args.min_samples)

    csv = Path(args.csv)
    outdir = Path(args.outdir)
    _ensure_dir(outdir)

    if not csv.exists():
        print(f"[skip] histórico não encontrado: {csv}")
        return

    df = pd.read_csv(csv)

    # requisitos mínimos de prob 1x2
    needed_probs = {"p_home", "p_draw", "p_away"}
    if not needed_probs.issubset(df.columns):
        raise SystemExit(f"CSV precisa conter colunas de prob 1x2: {sorted(needed_probs)}")

    # validações de intervalo [0,1], remove NaNs/inf
    for c in ["p_home", "p_draw", "p_away", "p_btts", "p_over15", "p_over25"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df[(df[c] >= 0.0) & (df[c] <= 1.0) | df[c].isna()]

    # garantir resultado/targets
    df = _derive_results_if_needed(df)

    # limpar linhas inválidas
    base_cols = ["league_id", "result", "p_home", "p_draw", "p_away"]
    df = df.dropna(subset=[c for c in base_cols if c in df.columns])
    df["league_id"] = df["league_id"].astype(str)
    df["result"] = df["result"].astype(int)

    # por liga
    saved = []
    bylg = df.groupby("league_id", dropna=False)
    for lg, grp in bylg:
        lg_str = str(lg)
        n = len(grp)
        print(f"[*] Liga {lg_str}: n={n}")

        # 1) 1x2
        m_1x2 = _train_1x2(grp)
        if m_1x2:
            f = outdir / f"{lg_str}_1x2.pkl"
            joblib.dump(m_1x2, f)
            print(f"  ✓ 1x2: {f}")
            saved.append(str(f))
        else:
            print("  - 1x2: dados insuficientes/sem variação -> skip")

        # 2) BTTS
        m_btts, status = _train_binary_if_present(grp, "p_btts", "btts_result")
        if m_btts:
            f = outdir / f"{lg_str}_btts.pkl"
            joblib.dump(m_btts, f)
            print(f"  ✓ BTTS: {f}")
            saved.append(str(f))
        else:
            print(f"  - BTTS: {status}")

        # 3) Over 1.5
        m_o15, status = _train_binary_if_present(grp, "p_over15", "over15_result")
        if m_o15:
            f = outdir / f"{lg_str}_over15.pkl"
            joblib.dump(m_o15, f)
            print(f"  ✓ Over1.5: {f}")
            saved.append(str(f))
        else:
            print(f"  - Over1.5: {status}")

        # 4) Over 2.5
        m_o25, status = _train_binary_if_present(grp, "p_over25", "over25_result")
        if m_o25:
            f = outdir / f"{lg_str}_over25.pkl"
            joblib.dump(m_o25, f)
            print(f"  ✓ Over2.5: {f}")
            saved.append(str(f))
        else:
            print(f"  - Over2.5: {status}")

    # manifest simples
    manifest = {
        "min_samples": MIN_SAMPLES,
        "output_dir": str(outdir),
        "files": saved,
    }
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResumo guardado em: {outdir / 'manifest.json'}")


if __name__ == "__main__":
    main()
