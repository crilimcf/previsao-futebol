#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import json
import csv
from typing import Dict, Any

PRED = Path("data/predict/predictions.json")
RAW = Path("data/raw/matches_raw.json")
OUT = Path("data/train/historico_com_probs.csv")


def _safe_get(d: Dict[str, Any], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def main():
    if not PRED.exists():
        print(f"[skip] predictions not found: {PRED}")
        return
    if not RAW.exists():
        print(f"[skip] raw matches not found: {RAW}")
        return

    print("[info] loading predictions")
    with PRED.open("r", encoding="utf-8") as fh:
        preds = json.load(fh)

    # index predictions by match_id when available
    by_id = {}
    for p in preds:
        mid = p.get("match_id")
        if mid is None:
            continue
        try:
            by_id[int(mid)] = p
        except Exception:
            by_id[mid] = p

    print(f"[info] loaded {len(preds)} predictions ({len(by_id)} with match_id)")

    print("[info] scanning raw matches and joining")
    out_rows = []
    with RAW.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # build secondary index by (date_ymd, home_team_normalized, away_team_normalized)
    def _norm_name(s):
        return (s or "").strip().lower()

    raw_by_key = {}
    for r in raw:
        mid = r.get("match_id")
        if mid is None:
            continue
        # try to get date in yyyy-mm-dd from raw (many files use 'date')
        date_raw = r.get("date") or r.get("date_ymd")
        date_ymd = None
        if isinstance(date_raw, str) and len(date_raw) >= 10:
            # try ISO-like first
            if "-" in date_raw:
                date_ymd = date_raw[:10]
            else:
                # try dd/mm/YYYY -> convert
                parts = date_raw.split("/")
                if len(parts) == 3:
                    dd, mm, yy = parts
                    if len(yy) == 4:
                        date_ymd = f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
        key = (date_ymd, _norm_name(r.get("team1")), _norm_name(r.get("team2")))
        raw_by_key[key] = r

    for r in raw:
        mid = r.get("match_id")
        if mid is None:
            continue
        try:
            mid_int = int(mid)
        except Exception:
            mid_int = mid

        p = by_id.get(mid_int)
        if not p:
            # try matching by (date, home, away)
            p_date = p_date = None
            p_date_raw = None
            if isinstance(p_date_raw, str):
                p_date = p_date_raw[:10]
        # we'll iterate again below to allow fallback matching
        pass

    # iterate raw matches and try to match predictions by id or by (date,teams)
    for r in raw:
        mid = r.get("match_id")
        if mid is None:
            continue
        # first try exact match by id
        try:
            mid_key = int(mid)
        except Exception:
            mid_key = mid

        p = by_id.get(mid_key)
        if not p:
            # fallback by key
            date_raw = r.get("date") or r.get("date_ymd")
            date_ymd = None
            if isinstance(date_raw, str) and len(date_raw) >= 10:
                date_ymd = date_raw[:10]
            key = (date_ymd, _norm_name(r.get("team1")), _norm_name(r.get("team2")))
            p = None
            # find prediction with matching date and teams
            def _name_match(a, b):
                if not a or not b:
                    return False
                na = _norm_name(a)
                nb = _norm_name(b)
                if na == nb:
                    return True
                # support substrings like 'mainz' vs 'fsv mainz 05'
                if len(na) > 2 and len(nb) > 2 and (na in nb or nb in na):
                    return True
                return False

            for pred in preds:
                pred_date = pred.get("date_ymd") or (pred.get("date")[:10] if isinstance(pred.get("date"), str) else None)
                if pred_date != date_ymd:
                    continue
                if _name_match(pred.get("home_team"), r.get("team1")) and _name_match(pred.get("away_team"), r.get("team2")):
                    p = pred
                    break
        if not p:
            continue

        # extract probs
        winner_probs = _safe_get(p, "predictions", "winner", "probs")
        # some older records may have 'probs' under different key names
        if not winner_probs:
            # try 'probs' at top-level predictions.winner
            winner_probs = _safe_get(p, "predictions", "winner")
            if isinstance(winner_probs, dict) and all(k in winner_probs for k in ("home","draw","away")):
                # already ok
                pass
            else:
                winner_probs = None

        if not winner_probs:
            # skip if no 1x2 probabilities available
            continue

        ph = winner_probs.get("home")
        pd = winner_probs.get("draw")
        pa = winner_probs.get("away")
        if ph is None or pd is None or pa is None:
            continue

        # binaries
        p_over25 = _safe_get(p, "predictions", "over_2_5", "prob")
        p_over15 = _safe_get(p, "predictions", "over_1_5", "prob")
        p_btts = _safe_get(p, "predictions", "btts", "prob")

        # outcome
        hg = r.get("team1_goals")
        ag = r.get("team2_goals")
        if hg is None or ag is None:
            continue

        try:
            hg = int(hg)
            ag = int(ag)
        except Exception:
            continue

        result = 0 if hg > ag else (2 if hg < ag else 1)

        league_id = p.get("league_id") or p.get("league") or r.get("league")

        row = {
            "league_id": str(league_id),
            "result": result,
            "home_goals": hg,
            "away_goals": ag,
            "p_home": float(ph),
            "p_draw": float(pd),
            "p_away": float(pa),
        }
        if p_over25 is not None:
            row["p_over25"] = float(p_over25)
        if p_over15 is not None:
            row["p_over15"] = float(p_over15)
        if p_btts is not None:
            row["p_btts"] = float(p_btts)

        # meta
        for k in ("date", "match_id", "home_team", "away_team"):
            if k in p:
                row[k] = p.get(k)
        out_rows.append(row)

    if not out_rows:
        print("[warn] no joined rows produced; check that predictions and raw matches share match_id values")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    keys = [
        "league_id",
        "result",
        "home_goals",
        "away_goals",
        "p_home",
        "p_draw",
        "p_away",
        "p_btts",
        "p_over15",
        "p_over25",
        "date",
        "match_id",
        "home_team",
        "away_team",
    ]

    print(f"[info] writing {OUT} ({len(out_rows)} rows)")
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in keys})

    print("[ok] done")


if __name__ == "__main__":
    main()
