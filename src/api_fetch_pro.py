# src/api_fetch_pro.py
import os
import json
import math
import time
import logging
import statistics as stats
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from datetime import date, timedelta

import requests
from src import config

logger = logging.getLogger("football_api")
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ==============================
# ENV
# ==============================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/"
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")

PROXY_BASE = os.getenv("API_PROXY_URL", "https://football-proxy-4ymo.onrender.com").rstrip("/") + "/"
PROXY_TOKEN = os.getenv("API_PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")

PRED_PATH = os.path.join("data", "predict", "predictions.json")
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# ==============================
# Redis cache
# ==============================
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

# ==============================
# HTTP
# ==============================
def proxy_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Optional[Dict[str, Any]]:
    url = urljoin(PROXY_BASE, path.lstrip("/"))
    try:
        r = requests.get(
            url,
            params=params or {},
            headers={"x-proxy-token": PROXY_TOKEN, "Accept": "application/json"},
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json()
        logger.warning(f"Proxy {url} -> {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.warning(f"Proxy erro {url}: {e}")
    return None


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Any:
    if not API_KEY:
        logger.warning("API_FOOTBALL_KEY ausente.")
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
        logger.warning(f"API {endpoint} -> {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"API erro {endpoint}: {e}")
    return []

# ==============================
# Poisson (fallback simples)
# ==============================
def _poisson_pmf(lmbda: float, k: int) -> float:
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)
    except OverflowError:
        return 0.0


def poisson_score_probs(lambda_home: float, lambda_away: float, max_goals: int = 6) -> List[List[float]]:
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


def over_under_prob_from_matrix(mat: List[List[float]], line: float) -> Tuple[float, float]:
    n = len(mat)
    p_over = 0.0
    for h in range(n):
        for a in range(n):
            if (h + a) > line:
                p_over += mat[h][a]
    return p_over, 1.0 - p_over


def top_k_scores_from_matrix(mat: List[List[float]], k: int = 3) -> List[Tuple[str, float]]:
    pairs: List[Tuple[str, float]] = []
    n = len(mat)
    for h in range(n):
        for a in range(n):
            pairs.append((f"{h}-{a}", mat[h][a]))
    pairs.sort(key=lambda t: t[1], reverse=True)
    return pairs[:k]

# ==============================
# Odds helpers
# ==============================
def _median_or_none(vals: List[float]) -> Optional[float]:
    vals = [v for v in vals if isinstance(v, (int, float)) and 1.05 <= v <= 100.0]
    if not vals:
        return None
    try:
        return round(float(stats.median(vals)), 2)
    except Exception:
        return None


def _parse_over_under(bet: Dict[str, Any], line: float) -> Tuple[Optional[float], Optional[float]]:
    over_list: List[float] = []
    under_list: List[float] = []
    for v in bet.get("values", []) or []:
        label = (v.get("value") or "").lower().replace(",", ".").strip()
        odd_raw = v.get("odd")
        if odd_raw is None:
            continue
        try:
            odd = float(str(odd_raw).replace(",", "."))
        except Exception:
            continue
        if label == f"over {line}".lower():
            over_list.append(odd)
        elif label == f"under {line}".lower():
            under_list.append(odd)
    return _median_or_none(over_list), _median_or_none(under_list)


def _parse_match_winner(bet: Dict[str, Any]) -> Dict[str, Optional[float]]:
    out = {"home": None, "draw": None, "away": None}
    buff = {"home": [], "draw": [], "away": []}
    for v in bet.get("values", []) or []:
        label = (v.get("value") or "").lower().strip()
        odd_raw = v.get("odd")
        if odd_raw is None:
            continue
        try:
            odd = float(str(odd_raw).replace(",", "."))
        except Exception:
            continue
        if label in ("home", "1"):
            buff["home"].append(odd)
        elif label in ("draw", "x"):
            buff["draw"].append(odd)
        elif label in ("away", "2"):
            buff["away"].append(odd)
    for k in out.keys():
        out[k] = _median_or_none(buff[k])
    return out


def _parse_btts(bet: Dict[str, Any]) -> Dict[str, Optional[float]]:
    out = {"yes": None, "no": None}
    buff = {"yes": [], "no": []}
    for v in bet.get("values", []) or []:
        label = (v.get("value") or "").lower().strip()
        odd_raw = v.get("odd")
        if odd_raw is None:
            continue
        try:
            odd = float(str(odd_raw).replace(",", "."))
        except Exception:
            continue
        if "yes" in label:
            buff["yes"].append(odd)
        elif "no" in label:
            buff["no"].append(odd)
    out["yes"] = _median_or_none(buff["yes"])
    out["no"] = _median_or_none(buff["no"])
    return out


def get_market_odds(fixture_id: int) -> Dict[str, Any]:
    """
    Odds reais. Tenta via proxy/API com season; se vier vazio, tenta SEM season
    (útil para torneios internacionais).
    """

    def _read_payload(params: Dict[str, Any]) -> Dict[str, Any]:
        # 1) proxy
        pj = proxy_get("/odds", params)
        if pj and isinstance(pj.get("response"), list):
            return pj
        # 2) API direta
        resp = api_get("odds", params)
        return {"response": resp if isinstance(resp, list) else []}

    out = {
        "winner": {"home": None, "draw": None, "away": None},
        "over_2_5": {"over": None, "under": None},
        "btts": {"yes": None, "no": None},
    }

    # primeiro com season
    payload = _read_payload({"fixture": fixture_id, "season": SEASON})

    def _merge_payload(pl: Dict[str, Any]) -> None:
        try:
            for item in pl.get("response", []):
                for bm in item.get("bookmakers", []) or []:
                    for bet in bm.get("bets", []) or []:
                        name = (bet.get("name") or "").lower().strip()
                        if name in ("match winner", "1x2"):
                            w = _parse_match_winner(bet)
                            for k, v in w.items():
                                if v is not None:
                                    out["winner"][k] = (
                                        v
                                        if out["winner"][k] is None
                                        else round((out["winner"][k] + v) / 2, 2)
                                    )
                        if "over/under" in name or "under/over" in name:
                            over, under = _parse_over_under(bet, 2.5)
                            if over is not None:
                                out["over_2_5"]["over"] = (
                                    over
                                    if out["over_2_5"]["over"] is None
                                    else round((out["over_2_5"]["over"] + over) / 2, 2)
                                )
                            if under is not None:
                                out["over_2_5"]["under"] = (
                                    under
                                    if out["over_2_5"]["under"] is None
                                    else round((out["over_2_5"]["under"] + under) / 2, 2)
                                )
                        if "both teams to score" in name or "btts" in name:
                            b = _parse_btts(bet)
                            for k, v in b.items():
                                if v is not None:
                                    out["btts"][k] = (
                                        v
                                        if out["btts"][k] is None
                                        else round((out["btts"][k] + v) / 2, 2)
                                    )
        except Exception as e:
            logger.debug(f"odds parse fail {fixture_id}: {e}")

    _merge_payload(payload)

    # se nada útil, tenta sem season
    if not any(v for v in out["winner"].values()) and not any(
        v for v in out["over_2_5"].values()
    ) and not any(v for v in out["btts"].values()):
        payload2 = _read_payload({"fixture": fixture_id})
        _merge_payload(payload2)

    # valida ranges
    for sect in (out["winner"], out["over_2_5"], out["btts"]):
        for k, v in list(sect.items()):
            if isinstance(v, (int, float)) and not (1.05 <= v <= 100.0):
                sect[k] = None
    return out

# ==============================
# Fixtures helpers
# ==============================
def _dedupe_fixtures(arr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for f in arr or []:
        fid = (((f or {}).get("fixture") or {}).get("id"))
        if fid and fid not in seen:
            seen.add(fid)
            out.append(f)
    return out

# ==============================
# Features/Stats
# ==============================
def team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    data = api_get(
        "teams/statistics",
        {"team": team_id, "league": league_id, "season": SEASON},
    )
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}


def compute_lambdas(
    stats_home: Dict[str, Any], stats_away: Dict[str, Any]
) -> Tuple[float, float]:
    def _get_float(path, default=1.0):
        try:
            v = path
            if isinstance(v, str):
                v = v.replace(",", ".")
            return float(v)
        except Exception:
            return float(default)

    avg_goals_home = _get_float(
        stats_home.get("goals", {})
        .get("for", {})
        .get("average", {})
        .get("home", 1.2)
    )
    avg_goals_away = _get_float(
        stats_away.get("goals", {})
        .get("for", {})
        .get("average", {})
        .get("away", 1.1)
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


def clamp_prob(p: float, eps: float = 1e-6) -> float:
    return max(eps, min(1.0 - eps, p))


def implied_odds(p: float) -> float:
    p = clamp_prob(p)
    return round(1.0 / p, 2)


def pick_dc_class(ph: float, pd: float, pa: float) -> Tuple[int, float]:
    opts = [(0, ph + pd), (1, ph + pa), (2, pd + pa)]
    best = max(opts, key=lambda t: t[1])
    return best[0], best[1]

# ==============================
# Top scorers cache
# ==============================
def _get_top_scorers_cached(league_id: int) -> List[Dict[str, Any]]:
    key = f"topscorers:{league_id}:{SEASON}"
    cached = redis_cache_get(key)
    if cached is not None:
        return cached
    tops = api_get("players/topscorers", {"league": league_id, "season": SEASON})
    res: List[Dict[str, Any]] = []
    for s in (tops or [])[:5]:
        player = (s.get("player") or {}).get("name")
        stat0 = (s.get("statistics") or [{}])[0]
        team = (stat0.get("team") or {}).get("name")
        goals = (stat0.get("goals") or {}).get("total", 0)
        res.append({"player": player, "team": team, "goals": int(goals or 0)})
    redis_cache_set(key, res, ex=12 * 3600)
    return res

# ==============================
# Build prediction
# ==============================
def build_prediction_from_fixture(fix: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fixture = fix.get("fixture", {})
        league = fix.get("league", {})
        teams = fix.get("teams", {})

        league_id = int(league.get("id"))
        league_name = league.get("name")
        country = league.get("country")

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
        dc_class, p_dc = pick_dc_class(ph, pd, pa)

        winner_class = int(max([(0, ph), (1, pd), (2, pa)], key=lambda t: t[1])[0])
        winner_conf = max(ph, pd, pa)
        top3 = [
            {"score": s, "prob": float(p)}
            for (s, p) in top_k_scores_from_matrix(mat, k=3)
        ]

        # Odds (modelo) como base
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
        odds_source = "model"

        # Tenta odds reais (com e sem season dentro de get_market_odds)
        fix_id = fixture.get("id")
        if fix_id:
            mkt = get_market_odds(int(fix_id))
            if any(isinstance(v, (int, float)) for v in mkt["winner"].values()):
                for k in ("home", "draw", "away"):
                    if isinstance(mkt["winner"].get(k), (int, float)):
                        odds_map["winner"][k] = mkt["winner"][k]
                        odds_source = "market"
            if isinstance(mkt["over_2_5"].get("over"), (int, float)) and isinstance(
                mkt["over_2_5"].get("under"), (int, float)
            ):
                odds_map["over_2_5"]["over"] = mkt["over_2_5"]["over"]
                odds_map["over_2_5"]["under"] = mkt["over_2_5"]["under"]
                odds_source = "market"
            if isinstance(mkt["btts"].get("yes"), (int, float)) and isinstance(
                mkt["btts"].get("no"), (int, float)
            ):
                odds_map["btts"]["yes"] = mkt["btts"]["yes"]
                odds_map["btts"]["no"] = mkt["btts"]["no"]
                odds_source = "market"

        pred_score = top3[0]["score"] if top3 else "1-1"
        try:
            hs, as_ = pred_score.split("-")
            ps_obj = {"home": int(hs), "away": int(as_)}
        except Exception:
            ps_obj = {"home": None, "away": None}

        out = {
            "match_id": fixture.get("id"),
            "league_id": league_id,
            "league": league_name,
            "country": country,
            "date": fixture.get("date"),
            "home_team": home.get("name"),
            "away_team": away.get("name"),
            "home_logo": home.get("logo"),
            "away_logo": away.get("logo"),
            "odds_source": odds_source,
            "odds": odds_map,
            "predictions": {
                "winner": {
                    "class": winner_class,
                    "confidence": float(winner_conf),
                },
                "over_2_5": {
                    "class": int(p_over25 >= 0.5),
                    "confidence": float(p_over25),
                },
                "over_1_5": {
                    "class": int(p_over15 >= 0.5),
                    "confidence": float(p_over15),
                },
                "double_chance": {
                    "class": dc_class,
                    "confidence": float(p_dc),
                },
                "btts": {
                    "class": int(p_btts >= 0.5),
                    "confidence": float(p_btts),
                },
            },
            "correct_score_top3": top3,
            "top_scorers": _get_top_scorers_cached(league_id),
            "predicted_score": ps_obj,
            "confidence": float(winner_conf),
        }
        return out
    except Exception as e:
        logger.error(f"build_prediction_from_fixture() erro: {e}")
        return None

# ==============================
# Fixtures & pipeline
# ==============================
def collect_fixtures(days: int = 3) -> List[Dict[str, Any]]:
    """
    Junta fixtures de clubes via proxy, usando apenas date + season.
    Sem filtros de seleções.
    """
    fixtures: List[Dict[str, Any]] = []
    for d in range(days):
        iso = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")

        pj = proxy_get("/fixtures", {"date": iso, "season": SEASON})
        if pj and isinstance(pj.get("response"), list):
            logger.info(f"collect_fixtures: {iso} season={SEASON} -> {len(pj['response'])} fixtures")
            fixtures.extend(pj["response"])
        else:
            logger.info(f"collect_fixtures: {iso} season={SEASON} -> 0 fixtures")

        time.sleep(0.2)

    fixtures = _dedupe_fixtures(fixtures)

    # Fallback: se por algum motivo não houver nada, tenta next=50
    if not fixtures:
        pj = proxy_get("/fixtures", {"next": 50, "season": SEASON})
        if pj and isinstance(pj.get("response"), list):
            fixtures = _dedupe_fixtures(pj["response"])
            logger.info(f"collect_fixtures: fallback next=50 -> {len(fixtures)} fixtures")

    return fixtures


def fetch_and_save_predictions() -> Dict[str, Any]:
    total = 0
    matches: List[Dict[str, Any]] = []
    logger.info(f"API-Football ativo | Época {SEASON}")
    fixtures = collect_fixtures(days=3)
    logger.info(f"{len(fixtures)} fixtures carregados (proxy).")
    for f in fixtures:
        pred = build_prediction_from_fixture(f)
        if pred:
            matches.append(pred)
            total += 1
    matches_sorted = sorted(
        matches,
        key=lambda x: x["predictions"]["winner"]["confidence"],
        reverse=True,
    )
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(matches_sorted, fp, ensure_ascii=False, indent=2)
    logger.info(f"{total} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": total}
