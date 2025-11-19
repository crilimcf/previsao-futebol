# ================================================================
# src/models/dixon_coles.py
# Implementa o modelo de Dixon–Coles com decaimento temporal
# para estimar forças de ataque/defesa e home_advantage
# ================================================================
import math
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple
import json

RATINGS_FILE = Path("data/models/dixon_coles_ratings.json")

def load_match_data(csv_path: str) -> pd.DataFrame:
    """CSV com colunas: date, home_team, away_team, home_goals, away_goals"""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date")
    return df

def decay_weight(days: int, tau: float = 180.0) -> float:
    """Fator de decaimento exponencial: jogos recentes pesam mais."""
    return math.exp(-days / tau)

def train_ratings(df: pd.DataFrame, max_iter: int = 500, tol: float = 1e-5):
    teams = sorted(set(df["home_team"]).union(df["away_team"]))
    attack = {t: 0.0 for t in teams}
    defense = {t: 0.0 for t in teams}
    home_adv = 0.2  # vantagem inicial casa

    last_date = df["date"].max()

    for _ in range(max_iter):
        diffs = []
        for _, row in df.iterrows():
            dh = (last_date - row["date"]).days
            w = decay_weight(dh)
            home, away = row["home_team"], row["away_team"]
            gh, ga = row["home_goals"], row["away_goals"]

            lam_h = math.exp(attack[home] - defense[away] + home_adv)
            lam_a = math.exp(attack[away] - defense[home])

            # Gradientes simples
            attack[home] += 0.001 * w * (gh - lam_h)
            defense[away] -= 0.001 * w * (gh - lam_h)
            attack[away] += 0.001 * w * (ga - lam_a)
            defense[home] -= 0.001 * w * (ga - lam_a)
            home_adv += 0.0001 * w * ((gh - ga) - (lam_h - lam_a))
            diffs.append(abs(gh - lam_h) + abs(ga - lam_a))
        if np.mean(diffs) < tol:
            break

    return {"attack": attack, "defense": defense, "home_adv": home_adv}

def save_ratings(ratings: Dict[str, Dict[str, float]]):
    RATINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RATINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)

def load_ratings() -> Dict[str, Dict[str, float]]:
    if RATINGS_FILE.exists():
        return json.loads(RATINGS_FILE.read_text(encoding="utf-8"))
    return {"attack": {}, "defense": {}, "home_adv": 0.2}

def predict_goals(home_team: str, away_team: str, ratings: Dict[str, Dict[str, float]]) -> Tuple[float, float]:
    atk = ratings["attack"]
    dfn = ratings["defense"]
    home_adv = ratings.get("home_adv", 0.2)
    lam_home = math.exp(atk.get(home_team, 0.0) - dfn.get(away_team, 0.0) + home_adv)
    lam_away = math.exp(atk.get(away_team, 0.0) - dfn.get(home_team, 0.0))
    return lam_home, lam_away

if __name__ == "__main__":
    df = load_match_data("data/historico_jogos.csv")
    ratings = train_ratings(df)
    save_ratings(ratings)
    print("✅ Dixon–Coles treinado e salvo em", RATINGS_FILE)
