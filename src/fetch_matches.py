# src/fetch_matches.py

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

import requests
from src.config import redis_get, redis_set

logger = logging.getLogger("football_api")

# Aliases for legacy code
_rget = redis_get
_rset = redis_set

# =========================
# ENV & CONSTANTES
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = (
    os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
    .rstrip("/")
    + "/"
)
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

REQUEST_TIMEOUT = 6
MAX_GOALS = 6
DAYS_AHEAD = 5  # hoje + 4 dias


def _get_api(endpoint: str, params: dict) -> Any:
    """
    Pequeno helper para chamar a API-FOOTBALL
    e devolver só o campo "response".
    """
    url = BASE_URL + endpoint.lstrip("/")
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response")
    except Exception as e:
        logger.warning(f"API request failed ({url}): {e}")
        return None


# =========================
# Players → taxas por 90 + pesos
# =========================
def _team_players_rates(team_id: int) -> List[Dict[str, Any]]:
    """
    Recolhe jogadores de uma equipa e calcula:
      - g90 suavizado
      - peso = g90 * fator_minutos * fator_posição

    Usa:
      - /players?team={team_id}&season={SEASON}
      - filtro por plantel atual via probable_scorers.get_current_squad_ids
    Guarda em cache 24h em Redis.
    """
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
    except Exception as e:
        logger.warning(f"⚠️ Falha ao obter plantel atual para equipa {team_id}: {e}")
    has_squad_filter = bool(squad_ids)

    out: List[Dict[str, Any]] = []
    for page in range(1, 4):
        arr = _get_api(
            "players",
            {"team": team_id, "season": SEASON, "page": page},
        ) or []
        if not arr:
            break

        for row in arr:
            player = row.get("player") or {}
            player_id = player.get("id")

            if has_squad_filter and (
                not isinstance(player_id, int) or player_id not in squad_ids
            ):
                continue

            stats_list = row.get("statistics") or []
            if not stats_list:
                continue

            st = stats_list[0]
            team_info = st.get("team") or {}
            team_from_stats = team_info.get("id")

            if isinstance(team_from_stats, int) and team_from_stats != team_id:
                continue

            games = st.get("games") or {}
            goals_d = st.get("goals") or {}

            name = player.get("name")
            position = (games.get("position") or player.get("position") or "") or ""
            minutes = games.get("minutes") or 0
            apps = (
                games.get("appearences")
                or games.get("appearances")
                or 0
            )
            goals = goals_d.get("total") or 0

            if minutes and minutes > 0:
                g90 = (goals + 0.2) / ((minutes / 90.0) + 0.2)
            else:
                g90 = 0.0

            min_factor = min(1.0, (minutes or 0) / 900.0)

            pos = (position or "").lower()
            if pos.startswith("f"):
                pos_w = 1.00
            elif pos.startswith("m"):
                pos_w = 0.60
            elif pos.startswith("d"):
                pos_w = 0.25
            else:
                pos_w = 0.10

            peso = g90 * min_factor * pos_w

            out.append(
                {
                    "id": player_id,
                    "name": name,
                    "position": position,
                    "minutes": minutes,
                    "apps": apps,
                    "goals": goals,
                    "g90": g90,
                    "peso": peso,
                }
            )

    _rset(ck, json.dumps(out), ex=86400)
    return out


# ----------------------------------------------------------------------
# Wrapper de compatibilidade para /meta/update
# ----------------------------------------------------------------------
def fetch_today_matches(days: int = 3) -> Optional[Dict[str, Any]]:
    """
    Compatibilidade com src/api_routes/predict.py.

    /meta/update chama fetch_today_matches() mas hoje a lógica
    principal de atualização está em src/api_fetch_pro.
    """
    logger.info("fetch_today_matches() chamado com days=%s", days)

    try:
        from src import api_fetch_pro  # type: ignore
    except Exception as exc:
        logger.warning("api_fetch_pro não encontrado; nada para atualizar: %s", exc)
        return None

    # 1) Preferimos update_predictions (API oficial)
    if hasattr(api_fetch_pro, "update_predictions"):
        fn = getattr(api_fetch_pro, "update_predictions")
        logger.info("A chamar api_fetch_pro.update_predictions(days=%s)", days)
        try:
            return fn(days=days, force=False)  # type: ignore[call-arg]
        except TypeError:
            try:
                return fn(days=days)  # type: ignore[call-arg]
            except TypeError:
                return fn()  # type: ignore[call-arg]

    # 2) Versões antigas com fetch_and_save_predictions
    if hasattr(api_fetch_pro, "fetch_and_save_predictions"):
        fn = getattr(api_fetch_pro, "fetch_and_save_predictions")
        logger.info("A chamar api_fetch_pro.fetch_and_save_predictions(days=%s)", days)
        try:
            return fn(days=days)  # type: ignore[call-arg]
        except TypeError:
            return fn()  # type: ignore[call-arg]

    # 3) Fallbacks bem antigos: main()/run()
    for attr in ("main", "run"):
        fn = getattr(api_fetch_pro, attr, None)
        if not callable(fn):
            continue

        logger.info("A chamar api_fetch_pro.%s(days=%s)", attr, days)
        try:
            return fn(days=days)  # type: ignore[call-arg]
        except TypeError:
            return fn()  # type: ignore[call-arg]

    logger.info(
        "api_fetch_pro não expõe nenhuma função pública "
        "(update_predictions/fetch_and_save_predictions/main/run); "
        "fetch_today_matches terminou sem executar atualização."
    )
    return None
