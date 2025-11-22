import json
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREDICTIONS = ROOT / "data" / "predict" / "predictions.json"
OUT = ROOT / "tmp" / "predictions_check_report.json"

def load_preds(path):
    with io.open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def is_extreme_prob(p):
    return p is None or p <= 0.005 or p >= 0.995

def scan(preds):
    report = {
        'total': len(preds),
        'odds_issues': [],
        'probability_extremes': [],
        'scorer_extremes': [],
    }

    for item in preds:
        mid = item.get('match_id')
        # odds checks
        odds = item.get('odds', {})
        for market, vals in odds.items():
            if isinstance(vals, dict):
                for k, v in vals.items():
                    try:
                        val = float(v)
                    except Exception:
                        continue
                    if val < 1.2 or val > 100:
                        report['odds_issues'].append({
                            'match_id': mid,
                            'market': market,
                            'key': k,
                            'value': val,
                        })

        # prediction probabilities: prefer v2.final when available
        v2 = item.get('v2') or {}
        if v2:
            # look for ou25, btts and p1x2 final values
            ou = v2.get('ou25', {}) or {}
            final_ou = (ou.get('final') or {})
            if final_ou:
                over_p = final_ou.get('over')
                under_p = final_ou.get('under')
                for prob, label in ((over_p, 'over'), (under_p, 'under')):
                    if isinstance(prob, (int, float)) and is_extreme_prob(prob):
                        report['probability_extremes'].append({
                            'match_id': mid,
                            'market': 'over_2_5',
                            'option': label,
                            'prob': prob,
                        })

            btts = v2.get('btts', {}) or {}
            final_btts = (btts.get('final') or {})
            if final_btts:
                yes_p = final_btts.get('yes')
                no_p = final_btts.get('no')
                for prob, label in ((yes_p, 'yes'), (no_p, 'no')):
                    if isinstance(prob, (int, float)) and is_extreme_prob(prob):
                        report['probability_extremes'].append({
                            'match_id': mid,
                            'market': 'btts',
                            'option': label,
                            'prob': prob,
                        })

            p1x2 = v2.get('p1x2', {}) or {}
            final_p1x2 = (p1x2.get('final') or {})
            for opt, prob in (final_p1x2.items() if isinstance(final_p1x2, dict) else []):
                if isinstance(prob, (int, float)) and is_extreme_prob(prob):
                    report['probability_extremes'].append({
                        'match_id': mid,
                        'market': 'winner',
                        'option': opt,
                        'prob': prob,
                    })
        else:
            # fallback: inspect raw predictions block
            preds_block = item.get('predictions', {})
            for mk, info in preds_block.items():
                # info may have 'prob' and 'probs'
                if isinstance(info, dict):
                    p = info.get('prob')
                    if isinstance(p, (int, float)) and is_extreme_prob(p):
                        report['probability_extremes'].append({
                            'match_id': mid,
                            'market': mk,
                            'prob': p,
                        })
                    probs = info.get('probs')
                    if isinstance(probs, dict):
                        for opt, v in probs.items():
                            if isinstance(v, (int, float)) and is_extreme_prob(v):
                                report['probability_extremes'].append({
                                    'match_id': mid,
                                    'market': mk,
                                    'option': opt,
                                    'prob': v,
                                })

        # probable scorers
        ps = item.get('probable_scorers', {}) or {}
        for side in ('home', 'away'):
            lst = ps.get(side) or []
            for player in lst:
                prob = player.get('probability') or player.get('prob') or 0
                pct = player.get('probability_pct') or player.get('probability_pct', None)
                if isinstance(prob, (int, float)) and prob >= 0.995:
                    report['scorer_extremes'].append({
                        'match_id': mid,
                        'side': side,
                        'player': player.get('player') or player.get('name') or player.get('player_name'),
                        'probability': prob,
                        'raw': player,
                    })

    return report

def main():
    preds = load_preds(PREDICTIONS)
    report = scan(preds)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print('Wrote', OUT)
    print('Summary: total=%d odds_issues=%d prob_extremes=%d scorer_extremes=%d' % (
        report['total'], len(report['odds_issues']), len(report['probability_extremes']), len(report['scorer_extremes'])
    ))

if __name__ == '__main__':
    main()
