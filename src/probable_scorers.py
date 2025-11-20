from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Set

import requests
from src import config

logger = logging.getLogger("football_api.scorers")

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = (os.getenv("API_FOOTBALL_BASE") or "https://v3.football.api-sports.io/").rstrip("/") + "/"
HEADERS = {
    "x-apisports-key": API_KEY,
    "Accept": "application/json",
} if API_KEY else {}

DEFAULT_TIMEOUT = 15


class ApiFootballError(RuntimeError):
    """Erro genérico ao chamar API-FOOTBALL para marcadores prováveis."""


# -------------------------------------------------------------------
# Redis cache leve (partilha com o que já tens no api_fetch_pro.py)
# -------------------------------------------------------------------
def redis_cache_get(key: str):
    try:
        if config.redis_client:
            raw = config.redis_client.get(key)
            if raw:
                return json.loads(raw)
    except Exception:
        # não queremos que um erro no Redis parta tudo
        logger.debug("Falha ao ler do Redis (key=%s)", key, exc_info=True)
    return None


def redis_cache_set(key: str, value: Any, ex: int = 4 * 3600) -> None:
    try:
        if config.redis_client:
            config.redis_client.set(key, json.dumps(value), ex=ex)
    except Exception:
        # idem, falha no Redis não deve rebentar o endpoint
        logger.debug("Falha ao escrever no Redis (key=%s)", key, exc_info=True)


session = requests.Session()


def _api_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    GET diretamente à API-FOOTBALL com cache em Redis.
    Aqui NÃO usamos o proxy porque /players, /injuries, /players/squads
    são chamados com mais frequência e queremos reusar o cache por chave.
    """
    if not API_KEY:
        raise ApiFootballError("API_FOOTBALL_KEY não está definido nas variáveis de ambiente.")

    url = BASE_URL + path.lstrip("/")
    params = params or {}

    cache_key = f"scorers:{path}:{json.dumps(params, sort_keys=True)}"
    cached = redis_cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = session.get(url, headers=HEADERS, params=params, timeout=DEFAULT_TIMEOUT)
    except Exception as exc:
        raise ApiFootballError(f"Erro ao chamar {url}: {exc}") from exc

    if resp.status_code != 200:
        raise ApiFootballError(f"Erro {resp.status_code} em {url}: {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiFootballError(f"Resposta JSON inválida em {url}: {resp.text[:200]}") from exc

    redis_cache_set(cache_key, data, ex=4 * 3600)
    return data


# -------------------------------------------------------------------
# Helpers específicos: plantel atual, lesões e estatísticas
# -------------------------------------------------------------------
@lru_cache(maxsize=256)
def get_current_squad_ids(team_id: int) -> Set[int]:
    """
    Usa /players/squads para obter o PLANTEL ATUAL do clube.
    Isto evita ex-jogadores (tipo Di María no Benfica) aparecerem.
    """
    payload = _api_get("players/squads", {"team": team_id})
    ids: Set[int] = set()
    for item in payload.get("response") or []:
        for p in item.get("players") or []:
            pid = p.get("id")
            if isinstance(pid, int):
                ids.add(pid)

    logger.info("Plantel atual carregado para team_id=%s (%d jogadores)", team_id, len(ids))
    return ids


@lru_cache(maxsize=256)
def get_players_for_team_season(team_id: int, season: int) -> List[Dict[str, Any]]:
    """
    Vai buscar TODAS as estatísticas de jogadores para uma equipa+época.

    Usa /players?team=...&season=... com paginação.
    """
    results: List[Dict[str, Any]] = []
    page = 1

    while True:
        payload = _api_get("players", {"team": team_id, "season": season, "page": page})
        response = payload.get("response") or []
        if not response:
            break

        results.extend(response)

        paging = payload.get("paging") or {}
        current = int(paging.get("current") or page)
        total = int(paging.get("total") or current)
        if current >= total:
            break
        page += 1

    logger.info(
        "Estatísticas de jogadores carregadas para team_id=%s season=%s (total=%d registos)",
        team_id,
        season,
        len(results),
    )
    return results


@lru_cache(maxsize=512)
def get_injured_players_for_fixture(fixture_id: int) -> Set[int]:
    """
    Devolve conjunto de IDs de jogadores lesionados / ausentes para um fixture.
    Usa /injuries?fixture=...
    """
    payload = _api_get("injuries", {"fixture": fixture_id})
    injured: Set[int] = set()
    for item in payload.get("response") or []:
        player = item.get("player") or {}
        pid = player.get("id")
        if isinstance(pid, int):
            injured.add(pid)

    logger.info("Injuries para fixture_id=%s: %d jogadores", fixture_id, len(injured))
    return injured


def _calc_score_from_stats(stats: Dict[str, Any]) -> float:
    """
    Score simples para ordenar marcadores:

      score = golos_totais + golos_por_90_min
    """
    games = stats.get("games") or {}
    goals = stats.get("goals") or {}

    minutes = float(games.get("minutes") or 0) or 0.0
    total_goals = float(goals.get("total") or 0) or 0.0

    if minutes <= 0 or total_goals <= 0:
        return 0.0

    goals_per_90 = (total_goals * 90.0) / minutes
    return total_goals + goals_per_90


def _iter_candidate_players(
    team_id: int,
    season: int,
    injured_ids: Iterable[int],
) -> Iterable[Dict[str, Any]]:
    """
    Gera jogadores candidatos a marcar golo para uma equipa:

    - só quem está NO PLANTEL ATUAL (players/squads)
    - exclui lesionados/ausentes (injuries por fixture)
    - exclui quem não tem golos / minutos nesta época
    """
    injured_set = set(injured_ids or [])
    squad_ids = get_current_squad_ids(team_id)

    for item in get_players_for_team_season(team_id, season):
        player = item.get("player") or {}
        pid = player.get("id")
        if not isinstance(pid, int):
            continue

        # fora se já não está no plantel atual (ex-jogadores)
        if squad_ids and pid not in squad_ids:
            continue

        # fora se está lesionado/ausente no fixture
        if pid in injured_set:
            continue

        statistics = item.get("statistics") or []
        if not statistics:
            continue

        # escolhe as stats relativas AO CLUBE ATUAL
        stats = next(
            (
                st
                for st in statistics
                if (st.get("team") or {}).get("id") == team_id
            ),
            None,
        )
        if not stats:
            continue

        score = _calc_score_from_stats(stats)
        if score <= 0:
            continue

        team_info = stats.get("team") or {}
        games = stats.get("games") or {}

        yield {
            "player_id": pid,
            "name": player.get("name"),
            "team_id": int(team_info.get("id") or team_id),
            "team_name": team_info.get("name"),
            "position": games.get("position") or player.get("position"),
            "photo": player.get("photo"),
            "stats": {
                "goals": stats.get("goals"),
                "games": games,
            },
            "score": float(score),
        }


def _normalize_probabilities(players: List[Dict[str, Any]]) -> None:
    total_score = sum(float(p.get("score") or 0.0) for p in players)
    if total_score <= 0:
        for p in players:
            p["probability"] = 0.0
            p["probability_pct"] = 0.0
        return

    for p in players:
        prob = float(p.get("score") or 0.0) / total_score
        p["probability"] = prob
        p["probability_pct"] = round(prob * 100.0, 1)


def probable_scorers_for_team(
    team_id: int,
    season: int,
    injured_ids: Iterable[int] | None = None,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    """
    Lista de marcadores prováveis para uma equipa numa época:

    [
      {
        "player_id": 123,
        "name": "João Mário",
        "team_id": 211,
        "team_name": "Benfica",
        "position": "M",
        "photo": "https://...",
        "stats": {...},
        "probability": 0.31,
        "probability_pct": 31.0
      },
      ...
    ]
    """
    injured_ids = set(injured_ids or [])
    candidates = list(_iter_candidate_players(team_id, season, injured_ids))

    candidates.sort(key=lambda p: float(p.get("score") or 0.0), reverse=True)
    if limit > 0:
        candidates = candidates[:limit]

    _normalize_probabilities(candidates)

    # já não precisamos expor 'score' para o frontend
    for c in candidates:
        c.pop("score", None)

    return candidates


def probable_scorers_for_match(
    fixture_payload: Dict[str, Any],
    limit: int = 4,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    A partir de um objeto fixture COMPLETO (o que vem de /fixtures),
    calcula marcadores prováveis para casa/fora usando:

      - season REAL do jogo (league.season)
      - plantel atual do clube (players/squads)
      - jogadores lesionados/ausentes (injuries?fixture=)

    Retorno:
    {
      "home": [...],
      "away": [...]
    }
    """
    fx = fixture_payload.get("fixture") or {}
    lg = fixture_payload.get("league") or {}
    teams = fixture_payload.get("teams") or {}

    try:
        fixture_id = int(fx.get("id") or 0)
        season = int(lg.get("season") or 0)
        home_team_id = int((teams.get("home") or {}).get("id") or 0)
        away_team_id = int((teams.get("away") or {}).get("id") or 0)
    except Exception as exc:
        raise ApiFootballError(
            f"Fixture inválido para probable_scorers: {exc} | {fixture_payload!r}"
        ) from exc

    if not (fixture_id and season and home_team_id and away_team_id):
        raise ApiFootballError(f"Dados incompletos no fixture: {fixture_payload!r}")

    injured_ids = get_injured_players_for_fixture(fixture_id)

    home = probable_scorers_for_team(
        home_team_id, season, injured_ids=injured_ids, limit=limit
    )
    away = probable_scorers_for_team(
        away_team_id, season, injured_ids=injured_ids, limit=limit
    )

    return {"home": home, "away": away}


# --- Utilitário para garantir atualização do plantel em memória ---
def clear_squad_lru_cache(team_id: int | None = None) -> None:
    """
    Limpa o cache em memória (LRU) dos plantéis e stats de jogadores.
    O parâmetro team_id é ignorado, existe só por compatibilidade.
    """
    try:
        get_current_squad_ids.cache_clear()
        get_players_for_team_season.cache_clear()
    except Exception:
        logger.debug("Falha ao limpar caches de plantel", exc_info=True)
