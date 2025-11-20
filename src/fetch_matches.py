
# src/fetch_matches.py
import os
import json
import logging

from typing import Any, Dict, List, Optional, Set
from src.config import redis_get, redis_set
import requests

# Aliases for legacy code
_rget = redis_get
_rset = redis_set

def _get_api(endpoint: str, params: dict) -> Any:
    url = BASE_URL + endpoint
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response")
    except Exception as e:
        logger.warning(f"API request failed: {e}")
        return None



logger = logging.getLogger("football_api")

# =========================
# ENV & CONSTANTES
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = (os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# Preferência de bookies ao ler odds reais
PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

# Limites
REQUEST_TIMEOUT = 6
MAX_GOALS = 6     # Poisson 0..6
DAYS_AHEAD  = 5   # hoje + 4 dias


# =========================
# Players → taxas por 90 + pesos
# =========================
def _team_players_rates(team_id: int) -> List[Dict[str, Any]]:
    """
    Recolhe jogadores de uma equipa (com paginação leve) e calcula:
      - g90 suavizado
      - peso = g90 * fator_minutos * fator_posição
    Guarda em cache 24h.
    """
    # v2 do cache key para forçar refetch após introduzir filtro por plantel atual
    ck = f"cache:players:{team_id}:{SEASON}:v2"
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    squad_ids: Optional[Set[int]] = None
    try:
        from src import probable_scorers
        squad_ids = probable_scorers.get_current_squad_ids(team_id)
    except Exception as e:  # pragma: no cover - apenas informativo
        logger.warning(f"⚠️ Falha ao obter plantel atual para equipa {team_id}: {e}")
    has_squad_filter = bool(squad_ids)

    out: List[Dict[str, Any]] = []
    for page in range(1, 4):  # até 3 páginas por segurança (geralmente 1-2)
        arr = _get_api("players", {"team": team_id, "season": SEASON, "page": page}) or []
        if not arr:
            break
        for row in arr:
            player = row.get("player") or {}
            player_id = player.get("id")
            if has_squad_filter and (not isinstance(player_id, int) or player_id not in squad_ids):
                continue
            stats_list = row.get("statistics") or []
            if not stats_list:
                continue
            st = stats_list[0]
            team_info = st.get("team") or {}
            team_from_stats = team_info.get("id")
            # Se o endpoint devolver estatísticas por equipa anterior, ignoramos.
            if isinstance(team_from_stats, int) and team_from_stats != team_id:
                continue
            games = st.get("games") or {}
            goals_d = st.get("goals") or {}
            name = player.get("name")
            position = (games.get("position") or player.get("position") or "") or ""
            minutes = games.get("minutes") or 0
            apps = games.get("appearences") or games.get("appearances") or 0  # API tem variações
            goals = goals_d.get("total") or 0
            # g/90 com suavização (evita amostras pequenas)
            if minutes and minutes > 0:
                g90 = (goals + 0.2) / ((minutes / 90.0) + 0.2)
            else:
                g90 = 0.0
            # fator minutos: saturação a 900' (10 jogos)
            min_factor = min(1.0, (minutes or 0) / 900.0)
            # fator por posição
            pos = (position or "").lower()
            if pos.startswith("f"):       # Forward
                pos_w = 1.00
            elif pos.startswith("m"):     # Midfielder
                pos_w = 0.60
            elif pos.startswith("d"):     # Defender
                pos_w = 0.25
            else:
                pos_w = 0.10
            peso = g90 * min_factor * pos_w
            out.append({
                "id": player_id,
                "name": name,
                "position": position,
                "minutes": minutes,
                "apps": apps,
                "goals": goals,
                "g90": g90,
                "peso": peso,
            })

            peso = g90 * min_factor * pos_w

            out.append({
                "id": player_id,
                "name": name,
                "position": position,
                "minutes": minutes,
                "apps": apps,
                "goals": goals,
                "g90": g90,
                "peso": peso,
            })

    # Salva em cache por 24h
    _rset(ck, json.dumps(out), ex=86400)
    return out
