#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
import argparse
import csv
from datetime import datetime, timedelta

# ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import api_fetch_pro


def parse_args():
    ap = argparse.ArgumentParser(description="Fetch historical fixtures via proxy and build CSV for calibrators")
    ap.add_argument("--leagues", nargs="*", help="League IDs to fetch (default: load from config/leagues.json)")
    ap.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD (default: 365 days ago)")
    ap.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default="data/train/historico_com_probs.csv", help="Output CSV path")
    ap.add_argument("--season", default=None, help="Season to pass to proxy (default uses api_fetch_pro.SEASON_CLUBS)")
    return ap.parse_args()


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def _safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def main():
    args = parse_args()
    out_path = Path(args.out)
    if args.from_date:
        start = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    else:
        start = (datetime.utcnow().date() - timedelta(days=365))
    if args.to_date:
        end = datetime.strptime(args.to_date, "%Y-%m-%d").date()
    else:
        end = datetime.utcnow().date()

    season = args.season or api_fetch_pro.SEASON_CLUBS

    # leagues
    leagues = []
    if args.leagues:
        leagues = [int(x) for x in args.leagues]
    else:
        # try to load from config/leagues.json (same format used elsewhere)
        try:
            import json
            cfg = Path("config/leagues.json")
            if cfg.exists():
                raw = json.loads(cfg.read_text(encoding="utf-8"))
                for o in raw:
                    lid = o.get("id")
                    try:
                        leagues.append(int(lid))
                    except Exception:
                        continue
        except Exception:
            pass

    if not leagues:
        print("[warn] no leagues specified and config missing/empty; aborting")
        return

    rows = []
    total = 0
    for lid in leagues:
        print(f"[info] fetching league {lid} from {start} to {end}")
        # API-Football supports from/to range on fixtures; proxy_get returns dict with 'response'
        payload = api_fetch_pro.proxy_get("/fixtures", {"league": lid, "season": season, "from": start.isoformat(), "to": end.isoformat()})
        fixtures = api_fetch_pro._extract_fixtures(payload)
        print(f"  -> {len(fixtures)} fixtures returned by proxy for league {lid}")

        for fix in fixtures:
            # only use finished fixtures with final score
            goals = _safe_get(fix, "goals") or _safe_get(fix, "score") or {}
            # try several spots for fulltime
            hg = _safe_get(goals, "home")
            ag = _safe_get(goals, "away")
            if hg is None or ag is None:
                # try nested structure fixture->goals
                hg = _safe_get(fix, "fixture", "goals", "home")
                ag = _safe_get(fix, "fixture", "goals", "away")
            if hg is None or ag is None:
                continue

            # build model prediction for this fixture
            pred = api_fetch_pro.build_prediction_from_fixture(fix)
            if not pred:
                continue

            ph = _safe_get(pred, "predictions", "winner", "probs", "home")
            pd = _safe_get(pred, "predictions", "winner", "probs", "draw")
            pa = _safe_get(pred, "predictions", "winner", "probs", "away")
            p_over25 = _safe_get(pred, "predictions", "over_2_5", "prob")
            p_over15 = _safe_get(pred, "predictions", "over_1_5", "prob")
            p_btts = _safe_get(pred, "predictions", "btts", "prob")

            try:
                hg_i = int(hg)
                ag_i = int(ag)
            except Exception:
                continue

            result = 0 if hg_i > ag_i else (2 if hg_i < ag_i else 1)

            row = {
                "league_id": str(lid),
                "result": result,
                "home_goals": hg_i,
                "away_goals": ag_i,
                "p_home": float(ph) if ph is not None else "",
                "p_draw": float(pd) if pd is not None else "",
                "p_away": float(pa) if pa is not None else "",
            }
            if p_btts is not None:
                row["p_btts"] = float(p_btts)
            if p_over15 is not None:
                row["p_over15"] = float(p_over15)
            if p_over25 is not None:
                row["p_over25"] = float(p_over25)

            # meta
            mdate = _safe_get(fix, "fixture", "date") or _safe_get(fix, "date")
            if isinstance(mdate, str):
                row["date"] = mdate
            fid = _safe_get(fix, "fixture", "id") or _safe_get(fix, "id")
            if fid is not None:
                row["match_id"] = fid
            home_name = _safe_get(fix, "teams", "home", "name") or _safe_get(fix, "team1")
            away_name = _safe_get(fix, "teams", "away", "name") or _safe_get(fix, "team2")
            if home_name:
                row["home_team"] = home_name
            if away_name:
                row["away_team"] = away_name

            rows.append(row)
            total += 1

    if not rows:
        print("[warn] no historical rows collected")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
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

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})

    print(f"[ok] written {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
