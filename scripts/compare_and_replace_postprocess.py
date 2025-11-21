#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import shutil
import argparse
from datetime import datetime

P_PROD = Path("data/predict/predictions.json")
P_TMP = Path("tmp/postprocess_applied.json")
BACKUP_DIR = Path("backups")

def key_for(item: dict) -> str:
    # prefer match_id if available
    mid = item.get("match_id") or item.get("id")
    if mid:
        return str(mid)
    # fallback composite
    parts = [str(item.get("league_id") or item.get("league") or "").strip()]
    home = (item.get("home_team") or item.get("home") or item.get("teams", {}).get("home") if isinstance(item.get("teams"), dict) else None)
    away = (item.get("away_team") or item.get("away") or item.get("teams", {}).get("away") if isinstance(item.get("teams"), dict) else None)
    parts.append(str(home or item.get("home_name") or "").strip())
    parts.append(str(away or item.get("away_name") or "").strip())
    # date/time
    parts.append(str(item.get("date") or item.get("fixture_date") or "").strip())
    return "|".join(parts)

def count_extremes(item: dict) -> int:
    c = 0
    v2 = item.get("v2") or {}
    # ou25 final
    try:
        over = v2.get("ou25", {}).get("final", {}).get("over")
        if over is not None:
            if float(over) >= 0.99 or float(over) <= 0.01:
                c += 1
    except Exception:
        pass
    # p1x2 final
    try:
        p1 = v2.get("p1x2", {}).get("final", {})
        if p1:
            for k in ("home", "draw", "away"):
                v = p1.get(k)
                if v is None:
                    continue
                if float(v) >= 0.99 or float(v) <= 0.01:
                    c += 1
                    break
    except Exception:
        pass
    return c

def has_v2(item: dict) -> bool:
    return bool(item.get("v2"))

def load(path: Path):
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Se passado, faz backup e substitui o ficheiro de produção")
    args = ap.parse_args()

    prod = load(P_PROD)
    tmp = load(P_TMP)

    mprod = {key_for(x): x for x in prod}
    mtmp = {key_for(x): x for x in tmp}

    keys = sorted(set(list(mprod.keys()) + list(mtmp.keys())))

    total = len(keys)
    prod_v2 = sum(1 for k in keys if k in mprod and has_v2(mprod[k]))
    tmp_v2 = sum(1 for k in keys if k in mtmp and has_v2(mtmp[k]))
    prod_ext = sum(count_extremes(mprod[k]) for k in keys if k in mprod)
    tmp_ext = sum(count_extremes(mtmp[k]) for k in keys if k in mtmp)

    summary = {
        "total_keys": total,
        "prod_count": len(prod),
        "tmp_count": len(tmp),
        "prod_v2_count": prod_v2,
        "tmp_v2_count": tmp_v2,
        "prod_extreme_count": prod_ext,
        "tmp_extreme_count": tmp_ext,
    }

    out_summary = Path("tmp/postprocess_compare_summary.json")
    out_sample = Path("tmp/postprocess_compare_sample.json")
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # prepare sample diffs
    sample = []
    for k in keys:
        a = mprod.get(k)
        b = mtmp.get(k)
        if a == b:
            continue
        # capture small diff
        item = {"key": k}
        if a is not None:
            item["prod_has_v2"] = bool(a.get("v2"))
            item["prod_over_raw"] = (a.get("predictions", {}).get("over_2_5", {}).get("prob"))
            try:
                item["prod_over_final"] = a.get("v2", {}).get("ou25", {}).get("final", {}).get("over")
            except Exception:
                item["prod_over_final"] = None
        if b is not None:
            item["tmp_has_v2"] = bool(b.get("v2"))
            item["tmp_over_raw"] = (b.get("predictions", {}).get("over_2_5", {}).get("prob"))
            try:
                item["tmp_over_final"] = b.get("v2", {}).get("ou25", {}).get("final", {}).get("over")
            except Exception:
                item["tmp_over_final"] = None
        sample.append(item)
        if len(sample) >= 20:
            break

    out_sample.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote summary to {out_summary} and sample to {out_sample}")

    better = False
    # decision rule: fewer extremes and not fewer v2 entries
    if summary["tmp_extreme_count"] < summary["prod_extreme_count"] and summary["tmp_v2_count"] >= summary["prod_v2_count"]:
        better = True

    if not args.apply:
        print(f"Better according to heuristic: {better} (run with --apply to replace)")
        return

    if not better:
        print("Not replacing: tmp file not judged better by heuristic. No action taken.")
        return

    # backup prod
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bak = BACKUP_DIR / f"predictions.json.bak.{ts}"
    shutil.copy2(P_PROD, bak)
    # copy tmp to prod
    shutil.copy2(P_TMP, P_PROD)
    print(f"Backed up {P_PROD} -> {bak}")
    print(f"Replaced {P_PROD} with {P_TMP}")

    # regenerate audit using existing script
    import subprocess
    subprocess.run(["python", "scripts/run_postprocess_audit.py"], check=False)

if __name__ == '__main__':
    main()
