import json
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "predict" / "predictions.json"

def summarize(n=5):
    with io.open(P, 'r', encoding='utf-8') as f:
        preds = json.load(f)

    out = []
    for item in preds[:n]:
        s = {
            'match_id': item.get('match_id'),
            'date': item.get('date'),
            'league': item.get('league'),
            'home': item.get('home_team'),
            'away': item.get('away_team'),
            'odds_winner': item.get('odds', {}).get('winner'),
            'pred_winner': item.get('predictions', {}).get('winner'),
            'over_2_5': item.get('v2', {}).get('ou25') or item.get('predictions', {}).get('over_2_5'),
            'btts': item.get('v2', {}).get('btts') or item.get('predictions', {}).get('btts'),
            'probable_scorers': item.get('probable_scorers') or item.get('probable_scorers_home') or item.get('probable_scorers_away')
        }
        out.append(s)

    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    summarize(5)
