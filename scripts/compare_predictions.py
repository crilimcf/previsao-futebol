#!/usr/bin/env python3
"""
Compare local predictions file with production predictions (v2) and produce a report.

Usage:
  python scripts/compare_predictions.py --local data/predict/predictions.json --prod tmp/prod_predictions_v2.json --out tmp/compare_report.json

Report includes:
 - per-match diffs for p1x2 probs (max absolute diff per match)
 - flags for probabilities equal to 0.0 or 1.0
 - summary counts
"""
import argparse
import json
from pathlib import Path


def load_json(path):
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding='utf-8'))


def index_by_match(items):
    idx = {}
    for it in items:
        mid = it.get('match_id') or it.get('id')
        if mid is None:
            continue
        idx[int(mid)] = it
    return idx


def safe_get_p1x2_probs(entry):
    # Try v2.final.p1x2, then v2.p1x2.final, then predictions.winner.probs
    if not entry:
        return None
    v2 = entry.get('v2') or entry.get('v_2')
    if v2:
        p1 = v2.get('p1x2') or v2.get('p1_x2')
        if p1:
            final = p1.get('final') or p1.get('calibrated') or p1.get('model')
            if isinstance(final, dict) and all(k in final for k in ('home','draw','away')):
                return { 'home': float(final['home']), 'draw': float(final['draw']), 'away': float(final['away']) }
    # fallback
    preds = entry.get('predictions') or entry
    winner = preds.get('winner') if isinstance(preds, dict) else None
    if winner and isinstance(winner.get('probs'), dict):
        return { 'home': float(winner['probs'].get('home',0)), 'draw': float(winner['probs'].get('draw',0)), 'away': float(winner['probs'].get('away',0)) }
    return None


def compare(local_idx, prod_idx):
    report = {'matches_compared':0, 'missing_in_prod':0, 'missing_in_local':0, 'max_diff_over_05':0, 'rows':[]}
    all_ids = set(local_idx.keys()) | set(prod_idx.keys())
    for mid in sorted(all_ids):
        l = local_idx.get(mid)
        p = prod_idx.get(mid)
        row = {'match_id': mid}
        if not l:
            report['missing_in_local'] += 1
            row['status'] = 'missing_local'
            report['rows'].append(row)
            continue
        if not p:
            report['missing_in_prod'] += 1
            row['status'] = 'missing_prod'
            report['rows'].append(row)
            continue
        lp = safe_get_p1x2_probs(l)
        pp = safe_get_p1x2_probs(p)
        row['status'] = 'ok'
        if lp is None or pp is None:
            row['note'] = 'missing_probs'
            report['rows'].append(row)
            continue
        diffs = {k: abs(lp[k]-pp.get(k,0)) for k in ('home','draw','away')}
        row['lp'] = lp
        row['pp'] = pp
        row['diffs'] = diffs
        maxd = max(diffs.values())
        row['max_diff'] = maxd
        if maxd > 0.05:
            report['max_diff_over_05'] += 1
        # extreme probs
        extremes = []
        for src,name in (('local','lp'),('prod','pp')):
            probs = lp if src=='local' else pp
            for k,v in probs.items():
                if v <= 0.0 or v >= 1.0:
                    extremes.append({'src':src,'side':k,'value':v})
        if extremes:
            row['extremes'] = extremes
        report['rows'].append(row)
        report['matches_compared'] += 1
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local', required=True)
    parser.add_argument('--prod', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()

    local = load_json(args.local)
    prod = load_json(args.prod)
    local_idx = index_by_match(local)
    prod_idx = index_by_match(prod)
    report = compare(local_idx, prod_idx)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Wrote report to', args.out)


if __name__ == '__main__':
    main()
