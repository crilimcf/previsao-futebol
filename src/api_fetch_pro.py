# src/api_fetch_pro.py
import os
import json
import math
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from datetime import date, timedelta

import requests

from src import config
from src.probable_scorers import probable_scorers_for_match  # NOVO

# ===========================================================
# LOG
# ===========================================================
logger = logging.getLogger("football_api")
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ===========================================================
# ENV
# ===========================================================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv(
    "API_FOOTBALL_BASE",
    "https://v3.football.api-sports.io/",
).rstrip("/") + "/"

# Season “normal” de clubes
SEASON_CLUBS = os.getenv("API_FOOTBALL_SEASON", "2025")

# World Cup – Qualification Europe (seleções A masculinas)
WCQ_EUROPE_LEAGUE_ID = int(os.getenv("API_FOOTBALL_WCQ_EUROPE_LEAGUE_ID", "32"))
WCQ_EUROPE_SEASON = os.getenv("API_FOOTBALL_WCQ_EUROPE_SEASON", "2024")

# Proxy seguro (Render)
PROXY_BASE = os.getenv(
    "API_PROXY_URL",
    "https://football-proxy-4ymo.onrender.com",
).rstrip("/") + "/"
PROXY_TOKEN = os.getenv("API_PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")

# ficheiro de saída
PRED_PATH = os.path.join("data", "predict", "predictions.json")

# Flag para camada ML opcional (Over 2.5)
USE_ML_LAYER = os.getenv("ML_LAYER_ENABLED", "false").lower() == "true"

# ===========================================================
# LEAGUES ALLOWLIST
# ===========================================================
LEAGUES_CONFIG_PATH = Path("config/leagues.json")
ALLOWED_LEAGUES: set[int] = set()
try:
    if LEAGUES_CONFIG_PATH.exists():
        raw = json.loads(LEAGUES_CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            for obj in raw:
                lid = obj.get("id")
                try:
                    ALLOWED_LEAGUES.add(int(lid))
                except Exception:
                    continue
    logger.info(f"✅ Allowlist de ligas carregada: {sorted(ALLOWED_LEAGUES)}")
except Exception as e:
    logger.warning(f"⚠️ Falha ao ler config/leagues.json: {e}")
    ALLOWED_LEAGUES = set()

# ===========================================================
# HEADERS API-FOOTBALL
# ===========================================================
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# ===========================================================
# Redis helper (cache leve)
# ===========================================================
def redis_cache_get(key: str) -> Optional[Any]:
    try:
        if config.redis_client:
            raw = config.redis_client.get(key)
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return None


def redis_cache_set(key: str, value: Any, ex: int = 1800) -> None:
    try:
        if config.redis_client:
            config.redis_client.set(key, json.dumps(value), ex=ex)
    except Exception:
        pass


# ===========================================================
# HTTP helpers
# ===========================================================
def proxy_get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Chama o proxy (Render) com URL join correto + x-proxy-token.
    Retorna JSON (dict) ou None.

    Proteções:
      - cache leve em Redis por (path+params)
      - se der erro, tenta usar cache antiga
    """
    url = urljoin(PROXY_BASE, path.lstrip("/"))
    params = params or {}

    cache_key = f"proxy:{path}:{json.dumps(params, sort_keys=True)}"
    try:
        r = requests.get(
            url,
            params=params,
            headers={"x-proxy-token": PROXY_TOKEN, "Accept": "application/json"},
            timeout=timeout,
        )
        if r.status_code == 200:
            data = r.json()
            # cache suave: 10 minutos
            redis_cache_set(cache_key, data, ex=600)
            return data

        logger.error(f"❌ Proxy {url} {r.status_code}: {r.text[:200]}")
        cached = redis_cache_get(cache_key)
        if cached is not None:
            logger.warning(
                f"⚠️ A usar resposta em cache de proxy para {path} "
                f"(params={params}) após erro {r.status_code}."
            )
            return cached
        return None

    except Exception as e:
        logger.error(f"❌ Proxy erro {url}: {e}")
        cached = redis_cache_get(cache_key)
        if cached is not None:
            logger.warning(
                f"⚠️ A usar resposta em cache de proxy para {path} "
                f"(params={params}) após exceção."
            )
            return cached
        return None


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Any:
    """
    GET à API-Football com cache em Redis (leve).
    Retorna já o campo 'response' normalizado (list/dict).
    """
    if not API_KEY:
        logger.warning("⚠️ API_FOOTBALL_KEY não definida. api_get() sem chave.")
        return []

    url = urljoin(BASE_URL, endpoint.lstrip("/"))
    cache_key = f"cache:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
    cached = redis_cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        r = requests.get(url, headers=HEADERS, params=params or {}, timeout=timeout)
        if r.status_code == 200:
            data = r.json().get("response", [])
            redis_cache_set(cache_key, data, ex=1800)
            return data
        logger.warning(f"⚠️ API {endpoint} {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"❌ API erro {endpoint}: {e}")
    return []


# ===========================================================
# Poisson helpers (com fallback)
# ===========================================================
try:
    from src.utils.poisson import (
        poisson_score_probs,
        outcome_probs_from_matrix,
        btts_prob_from_matrix,
        over_under_prob_from_matrix,
        top_k_scores_from_matrix,
    )
except Exception:

    def _poisson_pmf(lmbda: float, k: int) -> float:
        if lmbda <= 0:
            return 1.0 if k == 0 else 0.0
        try:
            return math.exp(-lmbda) * (lmbda**k) / math.factorial(k)
        except OverflowError:
            return 0.0

    def poisson_score_probs(
        lambda_home: float,
        lambda_away: float,
        max_goals: int = 6,
    ) -> List[List[float]]:
        mat: List[List[float]] = []
        for h in range(max_goals + 1):
            row = []
            ph = _poisson_pmf(lambda_home, h)
            for a in range(max_goals + 1):
                pa = _poisson_pmf(lambda_away, a)
                row.append(ph * pa)
            mat.append(row)
        s = sum(sum(r) for r in mat)
        if s > 0:
            mat = [[x / s for x in r] for r in mat]
        return mat

    def outcome_probs_from_matrix(mat: List[List[float]]) -> Tuple[float, float, float]:
        ph, pd, pa = 0.0, 0.0, 0.0
        n = len(mat)
        for h in range(n):
            for a in range(n):
                v = mat[h][a]
                if h > a:
                    ph += v
                elif h == a:
                    pd += v
                else:
                    pa += v
        return ph, pd, pa

    def btts_prob_from_matrix(mat: List[List[float]]) -> float:
        n = len(mat)
        p = 0.0
        for h in range(1, n):
            for a in range(1, n):
                p += mat[h][a]
        return p

    def over_under_prob_from_matrix(
        mat: List[List[float]],
        line: float,
    ) -> Tuple[float, float]:
        n = len(mat)
        p_over = 0.0
        for h in range(n):
            for a in range(n):
                if (h + a) > line:
                    p_over += mat[h][a]
        p_under = 1.0 - p_over
        return p_over, p_under

    def top_k_scores_from_matrix(
        mat: List[List[float]],
        k: int = 3,
    ) -> List[Tuple[str, float]]:
        pairs: List[Tuple[str, float]] = []
        n = len(mat)
        for h in range(n):
            for a in range(n):
                pairs.append((f"{h}-{a}", mat[h][a]))
        pairs.sort(key=lambda t: t[1], reverse=True)
        return pairs[:k]


# ===========================================================
# Camada ML opcional (Over 2.5)
# ===========================================================
_ml_over25 = None
try:
    from src.ml.predict_over25 import predict_over25 as _ml_over25
except Exception:
    _ml_over25 = None


def apply_ml_over25(
    lambda_home: float,
    lambda_away: float,
    match_conf: float,
    ph: float,
    p_over25_poisson: float,
) -> float:
    """
    Aplica modelo ML para recalibrar probabilidade de Over 2.5.
    Se não houver modelo ou flag desativada, devolve o valor original.
    """
    if not USE_ML_LAYER or _ml_over25 is None:
        return p_over25_poisson
    try:
        return float(
            _ml_over25(lambda_home, lambda_away, match_conf, ph, p_over25_poisson)
        )
    except Exception:
        return p_over25_poisson


# ===========================================================
# Modelagem prob/odds
# ===========================================================
def clamp_prob(p: float, eps: float = 1e-3) -> float:
    """
    Garante probabilidade dentro de [eps, 1-eps].
    eps maior para evitar odds ridículas (1e8, etc.).
    """
    return max(eps, min(1.0 - eps, p))


def implied_odds(
    p: float,
    min_odds: float = 1.01,
    max_odds: float = 50.0,
) -> float:
    """
    Converte probabilidade em odd decimal, limitada a um intervalo razoável.
    """
    p = clamp_prob(p, 1e-3)
    odds = 1.0 / p
    odds = max(min_odds, min(max_odds, odds))
    return round(odds, 2)


def pick_dc_class(
    ph: float,
    pd: float,
    pa: float,
) -> Tuple[int, float, Dict[str, float]]:
    """
    0 = 1X, 1 = 12, 2 = X2

    Devolve:
      - class (0/1/2)
      - probabilidade da melhor opção
      - dict com as três probabilidades
    """
    p_1x = ph + pd
    p_12 = ph + pa
    p_x2 = pd + pa

    opts = [
        (0, p_1x),
        (1, p_12),
        (2, p_x2),
    ]
    best = max(opts, key=lambda t: t[1])
    dc_probs = {"1X": p_1x, "12": p_12, "X2": p_x2}
    return best[0], best[1], dc_probs


# ===========================================================
# Estatísticas & features
# ===========================================================
def _season_for_league(league_id: int) -> str:
    """Escolhe a season correcta consoante a liga."""
    if league_id == WCQ_EUROPE_LEAGUE_ID:
        return WCQ_EUROPE_SEASON
    return SEASON_CLUBS


def team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    season = _season_for_league(league_id)
    data = api_get(
        "teams/statistics",
        {"team": team_id, "league": league_id, "season": season},
    )
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}


def compute_lambdas(
    stats_home: Dict[str, Any],
    stats_away: Dict[str, Any],
) -> Tuple[float, float]:
    def _get_float(v, default=1.0):
        try:
            if isinstance(v, str):
                v = v.replace(",", ".")
            return float(v)
        except Exception:
            return float(default)

    avg_goals_home = _get_float(
        stats_home.get("goals", {}).get("for", {}).get("average", {}).get("home", 1.2)
    )
    avg_goals_away = _get_float(
        stats_away.get("goals", {}).get("for", {}).get("average", {}).get("away", 1.1)
    )
    avg_conc_home = _get_float(
        stats_home.get("goals", {})
        .get("against", {})
        .get("average", {})
        .get("home", 1.0)
    )
    avg_conc_away = _get_float(
        stats_away.get("goals", {})
        .get("against", {})
        .get("average", {})
        .get("away", 1.0)
    )

    lam_home = max(0.05, (avg_goals_home + avg_conc_away) / 2.0)
    lam_away = max(0.05, (avg_goals_away + avg_conc_home) / 2.0)
    return lam_home, lam_away


# ===========================================================
# Core de previsão por fixture
# ===========================================================
def build_prediction_from_fixture(fix: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fixture = fix.get("fixture", {})
        league = fix.get("league", {})
        teams = fix.get("teams", {})

        league_id = int(league.get("id"))
        league_name = league.get("name")
        country = league.get("country")

        # -------------------------
        # Filtro de ligas (allowlist)
        # -------------------------
        if ALLOWED_LEAGUES:
            if league_id not in ALLOWED_LEAGUES and league_id != WCQ_EUROPE_LEAGUE_ID:
                # ignora ligas não desejadas
                return None

        home = teams.get("home", {})
        away = teams.get("away", {})

        home_id = home.get("id")
        away_id = away.get("id")
        if not home_id or not away_id:
            return None

        stats_h = team_stats(home_id, league_id)
        stats_a = team_stats(away_id, league_id)

        lam_h, lam_a = compute_lambdas(stats_h, stats_a)
        mat = poisson_score_probs(lam_h, lam_a, max_goals=6)

        ph, pd, pa = outcome_probs_from_matrix(mat)
        p_btts = btts_prob_from_matrix(mat)
        p_over25, p_under25 = over_under_prob_from_matrix(mat, 2.5)
        p_over15, p_under15 = over_under_prob_from_matrix(mat, 1.5)

        dc_class, p_dc, dc_probs = pick_dc_class(ph, pd, pa)

        winner_class = int(
            max(
                [
                    (0, ph),
                    (1, pd),
                    (2, pa),
                ],
                key=lambda t: t[1],
            )[0]
        )
        winner_conf = max(ph, pd, pa)

        # ============================
        # Camada ML para Over 2.5 (opcional)
        # ============================
        if USE_ML_LAYER:
            ml_p_over25 = apply_ml_over25(
                lambda_home=lam_h,
                lambda_away=lam_a,
                match_conf=float(winner_conf),
                ph=float(ph),
                p_over25_poisson=float(p_over25),
            )
            ml_p_over25 = clamp_prob(ml_p_over25)
            p_over25 = ml_p_over25
            p_under25 = 1.0 - p_over25

        top3 = [
            {"score": s, "prob": float(p)}
            for (s, p) in top_k_scores_from_matrix(mat, k=3)
        ]

        # season correcta para topscorers (ranking geral da liga)
        season = _season_for_league(league_id)
        scorers_cache_key = f"topscorers:{league_id}:{season}"
        top_scorers = redis_cache_get(scorers_cache_key)
        if top_scorers is None:
            tops = api_get(
                "players/topscorers",
                {"league": league_id, "season": season},
            )
            res = []
            for s in (tops or [])[:5]:
                player = (s.get("player") or {}).get("name")
                stat0 = (s.get("statistics") or [{}])[0]
                team = (stat0.get("team") or {}).get("name")
                goals = (stat0.get("goals") or {}).get("total", 0)
                res.append(
                    {"player": player, "team": team, "goals": int(goals or 0)}
                )
            top_scorers = res
            redis_cache_set(scorers_cache_key, top_scorers, ex=12 * 3600)

        # ============================
        # Marcadores prováveis por jogo (plantel atual + lesões)
        # ============================
        try:
            probable_scorers = probable_scorers_for_match(fix, limit=4)
        except Exception as e_ps:
            logger.warning(
                f"⚠️ Erro a calcular marcadores prováveis para fixture "
                f"{fixture.get('id')}: {e_ps}"
            )
            probable_scorers = {"home": [], "away": []}

        odds_map = {
            "winner": {
                "home": implied_odds(ph),
                "draw": implied_odds(pd),
                "away": implied_odds(pa),
            },
            "over_2_5": {
                "over": implied_odds(p_over25),
                "under": implied_odds(p_under25),
            },
            "over_1_5": {
                "over": implied_odds(p_over15),
                "under": implied_odds(p_under15),
            },
            "btts": {
                "yes": implied_odds(p_btts),
                "no": implied_odds(1.0 - p_btts),
            },
        }

        pred_score = top3[0]["score"] if top3 else "1-1"
        try:
            hs, as_ = pred_score.split("-")
            ps_obj = {"home": int(hs), "away": int(as_)}
        except Exception:
            ps_obj = {"home": None, "away": None}

        # ============================
        # Explicação "tipo tips" para o frontend
        # ============================
        explanation: List[str] = []

        exp_gols = lam_h + lam_a
        explanation.append(
            f"Golos esperados: {exp_gols:.2f} no total "
            f"(casa {lam_h:.2f}, fora {lam_a:.2f})."
        )

        if winner_class == 0:
            explanation.append(
                f"Casa ligeiramente favorita (1X), "
                f"prob. {ph*100:.0f}% para vitória."
            )
        elif winner_class == 1:
            explanation.append(f"Jogo equilibrado, prob. de empate {pd*100:.0f}%.")
        else:
            explanation.append(
                f"Visitante em vantagem (X2), prob. {pa*100:.0f}% para não perder."
            )

        if p_over25 >= 0.6:
            explanation.append(
                f"Tendência para Over 2.5 golos ({p_over25*100:.0f}%)."
            )
        elif p_over25 <= 0.4:
            explanation.append(
                f"Tendência para Under 2.5 golos ({(1-p_over25)*100:.0f}%)."
            )

        if p_btts >= 0.55:
            explanation.append(
                f"Boa probabilidade de ambas marcarem (BTTS Sim {p_btts*100:.0f}%)."
            )
        elif p_btts <= 0.40:
            explanation.append(
                f"Pouca probabilidade de ambas marcarem "
                f"(BTTS Não {(1-p_btts)*100:.0f}%)."
            )

        winner_label_map = {0: "home", 1: "draw", 2: "away"}
        dc_label_map = {0: "1X", 1: "12", 2: "X2"}

        out = {
            "match_id": fixture.get("id"),
            "league_id": league_id,
            "league": league_name,
            "country": country,
            "date": fixture.get("date"),
            "date_ymd": (fixture.get("date") or "")[:10],
            "home_team": home.get("name"),
            "away_team": away.get("name"),
            "home_logo": home.get("logo"),
            "away_logo": away.get("logo"),

            # lambdas guardadas para treino/analytics
            "lambda_home": float(lam_h),
            "lambda_away": float(lam_a),

            "odds": odds_map,
            "predictions": {
                "winner": {
                    "class": winner_class,
                    "label": winner_label_map.get(winner_class),
                    "confidence": float(winner_conf),
                    "prob": float(winner_conf),
                    "probs": {
                        "home": float(ph),
                        "draw": float(pd),
                        "away": float(pa),
                    },
                },
                "over_2_5": {
                    "class": int(p_over25 >= 0.5),
                    "confidence": float(p_over25),
                    "prob": float(p_over25),
                },
                "over_1_5": {
                    "class": int(p_over15 >= 0.5),
                    "confidence": float(p_over15),
                    "prob": float(p_over15),
                },
                "double_chance": {
                    "class": dc_class,
                    "label": dc_label_map.get(dc_class),
                    "confidence": float(p_dc),
                    "probs": {
                        "1X": float(dc_probs["1X"]),
                        "12": float(dc_probs["12"]),
                        "X2": float(dc_probs["X2"]),
                    },
                },
                "btts": {
                    "class": int(p_btts >= 0.5),
                    "confidence": float(p_btts),
                    "prob": float(p_btts),
                },
            },
            "correct_score_top3": top3,
            "top_scorers": top_scorers,
            "probable_scorers": probable_scorers,
            "probable_scorers_home": (
                probable_scorers.get("home")
                if isinstance(probable_scorers, dict)
                else []
            ),
            "probable_scorers_away": (
                probable_scorers.get("away")
                if isinstance(probable_scorers, dict)
                else []
            ),
            "predicted_score": ps_obj,
            "confidence": float(winner_conf),

            # texto para o front
            "explanation": explanation,
        }
        return out
    except Exception as e:
        logger.error(f"❌ build_prediction_from_fixture() erro: {e}")
        return None


# ===========================================================
# PIPELINE
# ===========================================================
def _dedupe_fixtures(fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicados com base no fixture.id."""
    seen: set[int] = set()
    out: List[Dict[str, Any]] = []
    for f in fixtures:
        try:
            fid = int(f.get("fixture", {}).get("id"))
        except Exception:
            fid = None
        if fid and fid not in seen:
            seen.add(fid)
            out.append(f)
    return out


def _extract_fixtures(payload: Any) -> List[Dict[str, Any]]:
    """
    Extrai lista de fixtures de vários formatos possíveis:
      - dict com 'response': [...]
      - dict com 'data' → pode ter 'response' ou já ser lista
      - lista direta
    """
    if not payload:
        return []

    # já é lista de fixtures
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        # formato API-Football normal
        resp = payload.get("response")
        if isinstance(resp, list):
            return [x for x in resp if isinstance(x, dict)]

        # formato possivelmente embrulhado em "data"
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            resp2 = data.get("response")
            if isinstance(resp2, list):
                return [x for x in resp2 if isinstance(x, dict)]

    return []


def collect_fixtures(days: int = 3) -> List[Dict[str, Any]]:
    """
    Busca fixtures via proxy por data (hoje + N-1 dias).

    Inclui:
      - Ligas de clubes com season SEASON_CLUBS
      - World Cup - Qualification Europe (league 32, season 2024)

    Se depois do dedupe não houver fixtures válidas (sem fixture.id),
    faz fallback para /fixtures?next=50.
    """
    try:
        days = int(days)
    except Exception:
        days = 3
    if days < 1:
        days = 1
    if days > 7:
        days = 7

    raw_fixtures: List[Dict[str, Any]] = []

    for d in range(days):
        iso = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")

        # 1) Clubes (season “normal”)
        payload_clubs = proxy_get("/fixtures", {"date": iso, "season": SEASON_CLUBS})
        fixtures_clubs = _extract_fixtures(payload_clubs)
        if fixtures_clubs:
            raw_fixtures.extend(fixtures_clubs)
        else:
            logger.warning(
                f"⚠️ Sem fixtures (clubes) via proxy para {iso} (season={SEASON_CLUBS}). "
                f"payload_type={type(payload_clubs).__name__}"
            )

        # 2) World Cup - Qualification Europe (seleções)
        if WCQ_EUROPE_LEAGUE_ID:
            payload_wcq = proxy_get(
                "/fixtures",
                {"date": iso, "league": WCQ_EUROPE_LEAGUE_ID, "season": WCQ_EUROPE_SEASON},
            )
            fixtures_wcq = _extract_fixtures(payload_wcq)
            if fixtures_wcq:
                raw_fixtures.extend(fixtures_wcq)
            else:
                logger.info(
                    f"ℹ️ Sem fixtures WCQ Europe para {iso} "
                    f"(league={WCQ_EUROPE_LEAGUE_ID}, season={WCQ_EUROPE_SEASON}). "
                    f"payload_type={type(payload_wcq).__name__}"
                )

        # pausazinha para não saturar proxy/API
        time.sleep(0.2)

    # dedupe com base em fixture.id
    fixtures = _dedupe_fixtures(raw_fixtures)

    # Se depois disto não houver nenhum jogo válido, faz fallback “next 50”
    if not fixtures:
        logger.warning(
            "⚠️ Nenhuma fixture válida por data (sem fixture.id). "
            "A usar fallback /fixtures?next=50."
        )
        # IMPORTANTE: aqui não passo season, deixo o API-Football escolher
        payload = proxy_get("/fixtures", {"next": 50})
        fixtures_fb = _extract_fixtures(payload)
        fixtures = _dedupe_fixtures(fixtures_fb)

    logger.info(f"📊 Total fixtures após merge + dedupe: {len(fixtures)}")
    return fixtures


def fetch_and_save_predictions(days: int = 3) -> Dict[str, Any]:
    """
    Corre o pipeline completo:
      - busca fixtures (clubes + WCQ Europe) para hoje + N-1 dias
      - calcula previsões
      - grava em data/predict/predictions.json

    Proteções:
      - se não houver fixtures ou previsões, NÃO sobrescreve o ficheiro antigo
    """
    total = 0
    matches: List[Dict[str, Any]] = []

    logger.info(
        f"🌍 API-Football ativo | Época clubes={SEASON_CLUBS}, "
        f"WCQ_Europe={WCQ_EUROPE_SEASON}, days={days}"
    )
    fixtures = collect_fixtures(days=days)
    logger.info(f"📊 {len(fixtures)} fixtures carregados (proxy).")

    if not fixtures:
        logger.warning(
            "⚠️ Nenhuma fixture obtida (possível erro 429 do proxy/API "
            "ou payload inesperado). "
            "A NÃO sobrescrever data/predict/predictions.json."
        )
        return {"status": "no-fixtures", "total": 0}

    for f in fixtures:
        pred = build_prediction_from_fixture(f)
        if pred:
            matches.append(pred)
            total += 1

    if total == 0:
        logger.warning(
            "⚠️ Nenhuma previsão calculada a partir das fixtures "
            "(todas filtradas ou erro). "
            "A NÃO sobrescrever data/predict/predictions.json."
        )
        return {"status": "no-predictions", "total": 0}

    matches_sorted = sorted(
        matches,
        key=lambda x: x["predictions"]["winner"]["confidence"],
        reverse=True,
    )

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(matches_sorted, fp, ensure_ascii=False, indent=2)

    logger.info(f"✅ {total} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": total}


# ===========================================================
# ENTRYPOINTS PÚBLICOS
# ===========================================================
def update_predictions(days: int = 3, force: bool = False) -> Dict[str, Any]:
    """
    Função pública usada por:
      - src.fetch_matches.fetch_today_matches() (via /meta/update)
      - GitHub Actions ou scripts externos.

    'days' = quantos dias a partir de hoje (ex: 3 -> hoje + 2).
    """
    try:
        d = int(days) if days is not None else 3
    except Exception:
        d = 3

    logger.info("🔁 update_predictions chamado (days=%s, force=%s)", d, force)
    return fetch_and_save_predictions(days=d)


if __name__ == "__main__":
    try:
        default_days = int(os.getenv("API_FETCH_DAYS", "3"))
    except Exception:
        default_days = 3

    update_predictions(days=default_days, force=True)
