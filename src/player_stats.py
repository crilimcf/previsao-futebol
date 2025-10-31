# src/player_stats.py

import os
import requests
import logging

logger = logging.getLogger("football_api")

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_BASE = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")


def _headers():
    return {
        "x-apisports-key": API_FOOTBALL_KEY,
    }


def _fetch_squad(team_id: int):
    url = f"{API_FOOTBALL_BASE}players/squads?team={team_id}"
    r = requests.get(url, headers=_headers(), timeout=15)
    return r.json().get("response", [])


def _fetch_players_stats(team_id: int):
    """
    Busca stats de todos os jogadores dessa equipa na época.
    """
    url = f"{API_FOOTBALL_BASE}players?team={team_id}&season={SEASON}"
    r = requests.get(url, headers=_headers(), timeout=15)
    return r.json().get("response", [])


def get_probable_scorer(home_team_id: int = None, away_team_id: int = None):
    """
    Tenta descobrir o jogador mais provável a marcar no jogo.
    Regras:
      - primeiro tenta da equipa da casa
      - se não houver stats, tenta da de fora
      - escolhe quem tem mais goals.total
    """
    if not API_FOOTBALL_KEY:
        return "N/A"

    candidates = []

    for team_id in [home_team_id, away_team_id]:
        if not team_id:
            continue
        try:
            players = _fetch_players_stats(team_id)
            for p in players:
                player_name = p.get("player", {}).get("name")
                stats = p.get("statistics", [])
                if not stats:
                    continue
                # normalmente é 1 elemento por competição
                st = stats[0]
                goals = st.get("goals", {}).get("total") or 0
                appearances = st.get("games", {}).get("appearences") or 0
                candidates.append({
                    "name": player_name,
                    "team_id": team_id,
                    "goals": goals,
                    "appearances": appearances,
                })
        except Exception as e:
            logger.error(f"⚠️ Erro ao buscar stats de jogadores da equipa {team_id}: {e}")

    if not candidates:
        return "N/A"

    # ordena por golos e depois por jogos (quem joga mais tem mais probabilidade de marcar)
    candidates.sort(key=lambda x: (x["goals"], x["appearances"]), reverse=True)
    best = candidates[0]
    return best["name"]
