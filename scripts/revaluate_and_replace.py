#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import argparse
import shutil
from datetime import datetime

P_PROD = Path("data/predict/predictions.json")
P_TMP = Path("tmp/postprocess_applied.json")
BACKUP_DIR = Path("backups")

def has_v2(item: dict) -> bool:
    return bool(item.get("v2"))

def count_extremes_item(item: dict, low: float, high: float) -> int:
    c = 0
    v2 = item.get("v2") or {}
    try:
        over = v2.get("ou25", {}).get("final", {}).get("over")
        if over is not None:
            v = float(over)
            if v <= low or v >= high:
                c += 1
    except Exception:
        pass
    try:
        p1 = v2.get("p1x2", {}).get("final", {})
        if p1:
            for k in ("home", "draw", "away"):
                v = p1.get(k)
                if v is None:
                    continue
                vv = float(v)
                if vv <= low or vv >= high:
                    c += 1
                    break
    except Exception:
        pass
    return c

def load(p: Path):
    if not p.exists():
        raise SystemExit(f"File not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--low", type=float, default=0.005, help="lower threshold for extremes (<= low)")
    ap.add_argument("--high", type=float, default=0.995, help="upper threshold for extremes (>= high)")
    ap.add_argument("--apply", action="store_true", help="If passed and tmp is better, backup and replace prod")
    args = ap.parse_args()

    prod = load(P_PROD)
    tmp = load(P_TMP)

    prod_v2 = sum(1 for x in prod if has_v2(x))
    tmp_v2 = sum(1 for x in tmp if has_v2(x))
    prod_ext = sum(count_extremes_item(x, args.low, args.high) for x in prod)
    tmp_ext = sum(count_extremes_item(x, args.low, args.high) for x in tmp)

    summary = {
        "prod_count": len(prod),
        "tmp_count": len(tmp),
        "prod_v2_count": prod_v2,
        "tmp_v2_count": tmp_v2,
        "prod_extreme_count": prod_ext,
        "tmp_extreme_count": tmp_ext,
        "low": args.low,
        "high": args.high,
    }

    out = Path("tmp/postprocess_reval_summary.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # decision: tmp is better if tmp_ext <= prod_ext and tmp_v2 >= prod_v2
    better = (tmp_ext <= prod_ext) and (tmp_v2 >= prod_v2)
    print(f"Better with thresholds low={args.low} high={args.high}: {better}")

    if args.apply and better:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        bak = BACKUP_DIR / f"predictions.json.bak.{ts}"
        shutil.copy2(P_PROD, bak)
        shutil.copy2(P_TMP, P_PROD)
        print(f"Backed up {P_PROD} -> {bak} and replaced with {P_TMP}")
        # rerun audit
        import subprocess
        subprocess.run(["python", "scripts/run_postprocess_audit.py"], check=False)
    elif args.apply and not better:
        print("Not replacing: tmp not judged better under these thresholds.")

if __name__ == '__main__':
    main()
