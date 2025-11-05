# src/train_calibrator.py
import csv
import os
from typing import List

from src.utils.calibrator import calibrate_probs

DATASET_PATH = "data/training/matches.csv"
OUT_DIR = "data/model"
OUT_FILE = os.path.join(OUT_DIR, "calibration.json")


def _read_column(rows, p_col: str, y_col: str):
    probs: List[float] = []
    ys: List[int] = []
    for r in rows:
      try:
        p = float(r[p_col])
        y = int(r[y_col])
      except Exception:
        continue
      if p <= 0 or p >= 1:
        continue
      probs.append(p)
      ys.append(y)
    return probs, ys


def main():
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Ficheiro de treino não encontrado: {DATASET_PATH}")

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        rows = list(rdr)

    os.makedirs(OUT_DIR, exist_ok=True)

    all_cals = {}

    # 1) winner
    probs, ys = _read_column(rows, "p_home", "y_home")
    if probs:
        cal = calibrate_probs(probs, ys, name="winner", out_path=os.path.join(OUT_DIR, "cal_winner.json"))
        all_cals["winner"] = cal.to_dict()

    # 2) over 2.5
    probs, ys = _read_column(rows, "p_over25", "y_over25")
    if probs:
        cal = calibrate_probs(probs, ys, name="over_2_5", out_path=os.path.join(OUT_DIR, "cal_over25.json"))
        all_cals["over_2_5"] = cal.to_dict()

    # 3) BTTS
    probs, ys = _read_column(rows, "p_btts", "y_btts")
    if probs:
        cal = calibrate_probs(probs, ys, name="btts", out_path=os.path.join(OUT_DIR, "cal_btts.json"))
        all_cals["btts"] = cal.to_dict()

    # guarda índice
    import json
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_cals, f, ensure_ascii=False, indent=2)

    print(f"✅ Calibradores treinados e guardados em {OUT_DIR}")


if __name__ == "__main__":
    main()
