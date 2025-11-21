#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import json
from collections import defaultdict
import sys
from pathlib import Path as _P
# ensure repo root on sys.path
sys.path.insert(0, str((_P(__file__).resolve().parents[1])) )
from src.pipeline.v2_postprocess import postprocess_item

PRED = Path("data/predict/predictions.json")
OUT = Path("tmp/postprocess_all.json")
AUDIT = Path("tmp/postprocess_audit_by_league.csv")

def main():
    if not PRED.exists():
        print(f"[skip] predictions not found: {PRED}")
        return
    preds = json.loads(PRED.read_text(encoding="utf-8"))
    out = []
    stats = defaultdict(lambda: {"count":0, "over_ge_0_99":0, "over_le_0_01":0, "raw_over_ge_0_99":0, "raw_over_le_0_01":0})

    for p in preds:
        lid = str(p.get("league_id") or p.get("league") or "")
        try:
            res = postprocess_item(p.copy(), lid)
        except Exception as e:
            # continue on errors
            p.setdefault("v2", {})["error"] = str(e)
            out.append(p)
            continue

        out.append(res)
        stats[lid]["count"] += 1
        # final over prob
        try:
            final_over = res.get("v2", {}).get("ou25", {}).get("final", {}).get("over")
            raw_over = (res.get("predictions", {}).get("over_2_5", {}).get("prob"))
            if final_over is not None:
                if final_over >= 0.99:
                    stats[lid]["over_ge_0_99"] += 1
                if final_over <= 0.01:
                    stats[lid]["over_le_0_01"] += 1
            if raw_over is not None:
                try:
                    ro = float(raw_over)
                    if ro >= 0.99:
                        stats[lid]["raw_over_ge_0_99"] += 1
                    if ro <= 0.01:
                        stats[lid]["raw_over_le_0_01"] += 1
                except Exception:
                    pass
        except Exception:
            pass

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # write CSV audit
    with AUDIT.open("w", encoding="utf-8") as fh:
        fh.write("league_id,count,final_over>=0.99,final_over<=0.01,raw_over>=0.99,raw_over<=0.01\n")
        for k,v in sorted(stats.items(), key=lambda x: -x[1]["count"]):
            fh.write(f"{k},{v['count']},{v['over_ge_0_99']},{v['over_le_0_01']},{v['raw_over_ge_0_99']},{v['raw_over_le_0_01']}\n")

    print(f"[ok] processed {len(out)} items. outputs: {OUT}, {AUDIT}")

if __name__ == "__main__":
    main()
