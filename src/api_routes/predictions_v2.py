# -*- coding: utf-8 -*-
from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any

from src.predictor_bivar import predict_with_bivar

router = APIRouter()

def generate_matches_for_date(date: str, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    ADAPTA ESTE LOADER à tua infra. Deve devolver uma lista de dicionários,
    cada um com: league_id, lambda_home, lambda_away, home_team, away_team, league_name, country, date, match_id.
    """
    # Exemplo mínimo (placeholder):
    # from src.your_loader import load_matches_with_lambdas
    # return load_matches_with_lambdas(date=date, league_id=league_id)
    return []

@router.get("/predictions/v2")
def predictions_v2(date: str = Query(...), league_id: Optional[str] = None):
    matches = generate_matches_for_date(date=date, league_id=league_id)
    out = [predict_with_bivar(m) for m in matches]
    return out
