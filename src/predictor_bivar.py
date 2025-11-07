# -*- coding: utf-8 -*-
from pathlib import Path
import json
from typing import Dict, Any

from src.ml.bivar import score_matrix, aggregate_markets

L3_PATH = Path("models/bivar_lambda3.json")

def load_lambda3():
    if L3_PATH.exists():
        j = json.loads(L3_PATH.read_text())
        return j.get("lambda3_per_league", {})
    return {}

L3 = load_lambda3()

def predict_with_bivar(match: Dict[str, Any]) -> Dict[str, Any]:
    """
    match precisa conter:
      - league_id
      - lambda_home, lambda_away (vindos do teu Poisson)
      - home_team, away_team, league_name, country, date, match_id (quando possível)
    """
    league_id = str(match.get("league_id"))
    lam_h = float(match["lambda_home"])
    lam_a = float(match["lambda_away"])
    l3 = float(L3.get(league_id, 0.0))

    mat = score_matrix(lam_h, lam_a, l3, max_goals=10)
    mk  = aggregate_markets(mat)

    # class winner: 0=home, 1=draw, 2=away
    probs = mk["result_1x2"]
    if probs["home"] >= probs["draw"] and probs["home"] >= probs["away"]:
        winner_class = 0
        winner_prob  = probs["home"]
    elif probs["away"] >= probs["home"] and probs["away"] >= probs["draw"]:
        winner_class = 2
        winner_prob  = probs["away"]
    else:
        winner_class = 1
        winner_prob  = probs["draw"]

    return {
        "match_id": match.get("match_id"),
        "league_id": match.get("league_id"),
        "league_name": match.get("league_name"),
        "country": match.get("country"),
        "date": match.get("date"),
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "predictions": {
            "winner": {"class": winner_class, "prob": winner_prob},
            "over_2_5": {"class": int(mk["over_2_5"]>=0.5), "prob": mk["over_2_5"]},
            "over_1_5": {"class": None, "prob": None},      # opcional preencher
            "double_chance": {"class": None, "prob": None}, # opcional preencher
            "btts": {"class": int(mk["btts"]>=0.5), "prob": mk["btts"]},
            "correct_score": {
                "best": mk["correct_score_top3"][0]["score"],
                "top3": mk["correct_score_top3"],
            },
        },
        "correct_score_top3": mk["correct_score_top3"],
    }
