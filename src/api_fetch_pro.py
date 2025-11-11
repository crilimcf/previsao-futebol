# src/api_fetch_pro.py
import os
import json
import math
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from datetime import date, timedelta

import requests
from src import config

logger = logging.getLogger("football_api")
logging.getLogger("urllib3").setLevel(logging.WARNING)

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/"
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")

# Proxy (apenas para fixtures, se quiseres). Se não estiver definido, ignoramos.
PROXY_BASE = os.getenv("API_PROXY_URL", "https://football-proxy-4ymo.onrender.com").rstrip("/") + "/"
PROXY_TOKEN = os.getenv("API_PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")

PRED_PATH = os.path.join("data", "predict", "predictions.json")
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# ---------------- Redis cache leve ----------------
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

# ---------------- HTTP helpers ----------------
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
        logger.error(f"❌ Proxy {url} {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"❌ Proxy erro {url}: {e}")
    return None

def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Any:
    """GET à API-Football com cache em Redis (retorna já 'response')."""
    if not API_KEY:
        logger.warning("⚠️ API_FOOTBALL_KEY não definida.")
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

# ---------------- Poisson helpers mínimos ----------------
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
            if h > a: ph += v
            elif h == a: pd += v
            else: pa += v
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

def pick_dc_class(ph: float, pd: float, pa: float) -> Tuple[int, float]:
    # 0=1X, 1=12, 2=X2
    opts = [(0, ph + pd), (1, ph + pa), (2, pd + pa)]
    best = max(opts, key=lambda t: t[1])
    return best[0], best[1]

# ---------------- Stats & lambdas ----------------
def team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    data = api_get("teams/statistics", {"team": team_id, "league": league_id, "season": SEASON})
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}

def compute_lambdas(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    def _get_float(v, default=1.0):
        try:
            if isinstance(v, str):
                v = v.replace(",", ".")
            return float(v)
        except Exception:
            return float(default)
    avg_goals_home = _get_float(stats_home.get("goals", {}).get("for", {}).get("average", {}).get("home", 1.2))
    avg_goals_away = _get_float(stats_away.get("goals", {}).get("for", {}).get("average", {}).get("away", 1.1))
    avg_conc_home  = _get_float(stats_home.get("goals", {}).get("against", {}).get("average", {}).get("home", 1.0))
    avg_conc_away  = _get_float(stats_away.get("goals", {}).get("against", {}).get("average", {}).get("away", 1.0))
    lam_home = max(0.05, (avg_goals_home + avg_conc_away) / 2.0)
    lam_away = max(0.05, (avg_goals_away + avg_conc_home) / 2.0)
    return lam_home, lam_away

# ---------------- Odds reais da API-Football ----------------
def _f(x) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None

def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0

def get_book_odds_for_fixture(fixture_id: int) -> Dict[str, Any]:
    """
    Lê /odds da API-Football e devolve apenas mercados reais.
    NUNCA usa implied aqui. Se não existir, devolve sem o mercado.
    """
    out: Dict[str, Any] = {}
    try:
        # usa API direta (tem cache em api_get, mas odds mudam; aqui chamamos sem cache)
        url = urljoin(BASE_URL, "odds")
        r = requests.get(url, headers=HEADERS, params={"fixture": fixture_id, "season": SEASON}, timeout=8)
        r.raise_for_status()
        data = r.json().get("response", [])
    except Exception as e:
        logger.debug(f"odds fetch fail for {fixture_id}: {e}")
        return out

    # coletores de todas as casas
    pool_1x2 = {"home": [], "draw": [], "away": []}
    pool_ou25 = {"over": [], "under": []}
    pool_ou15 = {"over": [], "under": []}
    pool_btts = {"yes": [], "no": []}

    for item in data:
        for bm in item.get("bookmakers", []) or []:
            for bet in bm.get("bets", []) or []:
                name = (bet.get("name") or "").lower().strip()
                values = bet.get("values") or []

                # 1X2 / Match Winner
                if name in ("match winner", "1x2"):
                    h = d = a = None
                    for v in values:
                        label = (v.get("value") or "").strip().lower()
                        odd = _f(v.get("odd"))
                        if odd is None: 
                            continue
                        if label in ("home", "1"):
                            h = odd
                        elif label in ("draw", "x"):
                            d = odd
                        elif label in ("away", "2"):
                            a = odd
                    if h: pool_1x2["home"].append(h)
                    if d: pool_1x2["draw"].append(d)
                    if a: pool_1x2["away"].append(a)

                # Over/Under
                if "over/under" in name or "under/over" in name:
                    for v in values:
                        label = (v.get("value") or "").lower()
                        odd = _f(v.get("odd"))
                        if odd is None:
                            continue
                        if "over 2.5" in label:
                            pool_ou25["over"].append(odd)
                        elif "under 2.5" in label:
                            pool_ou25["under"].append(odd)
                        elif "over 1.5" in label:
                            pool_ou15["over"].append(odd)
                        elif "under 1.5" in label:
                            pool_ou15["under"].append(odd)

                # BTTS
                if "both teams to score" in name or "btts" in name:
                    y = n = None
                    for v in values:
                        label = (v.get("value") or "").lower()
                        odd = _f(v.get("odd"))
                        if odd is None:
                            continue
                        if "yes" in label:
                            y = odd
                        elif "no" in label:
                            n = odd
                    if y: pool_btts["yes"].append(y)
                    if n: pool_btts["no"].append(n)

    # Medianas por mercado (evita outliers)
    if all(pool_1x2[k] for k in ("home", "draw", "away")):
        out["winner"] = {
            "home": round(_median(pool_1x2["home"]), 2),
            "draw": round(_median(pool_1x2["draw"]), 2),
            "away": round(_median(pool_1x2["away"]), 2),
            "source": "bookmaker",
        }
    if all(pool_ou25[k] for k in ("over", "under")):
        out["over_2_5"] = {
            "over": round(_median(pool_ou25["over"]), 2),
            "under": round(_median(pool_ou25["under"]), 2),
            "line": 2.5,
            "source": "bookmaker",
        }
    if all(pool_ou15[k] for k in ("over", "under")):
        out["over_1_5"] = {
            "over": round(_median(pool_ou15["over"]), 2),
            "under": round(_median(pool_ou15["under"]), 2),
            "line": 1.5,
            "source": "bookmaker",
        }
    if all(pool_btts[k] for k in ("yes", "no")):
        out["btts"] = {
            "yes": round(_median(pool_btts["yes"]), 2),
            "no": round(_median(pool_btts["no"]), 2),
            "source": "bookmaker",
        }

    return out

# ---------------- Prediction builder ----------------
def build_prediction_from_fixture(fix: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fixture = fix.get("fixture", {})
        league = fix.get("league", {})
        teams = fix.get("teams", {})

        league_id = int(league.get("id"))
        league_name = league.get("name")
        country = league.get("country")

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}
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

        top3 = [{"score": s, "prob": float(p)} for (s, p) in top_k_scores_from_matrix(mat, k=3)]

        # topscorers (cache por liga)
        scorers_cache_key = f"topscorers:{league_id}:{SEASON}"
        top_scorers = redis_cache_get(scorers_cache_key)
        if top_scorers is None:
            tops = api_get("players/topscorers", {"league": league_id, "season": SEASON})
            res = []
            for s in (tops or [])[:5]:
                player = (s.get("player") or {}).get("name")
                stat0 = (s.get("statistics") or [{}])[0]
                team = (stat0.get("team") or {}).get("name")
                goals = (stat0.get("goals") or {}).get("total", 0)
                res.append({"player": player, "team": team, "goals": int(goals or 0)})
            top_scorers = res
            redis_cache_set(scorers_cache_key, top_scorers, ex=12 * 3600)

        # >>> Odds reais: só preenche se vier do /odds; senão não coloca o mercado <<<
        book_odds = get_book_odds_for_fixture(int(fixture.get("id")))
        odds_map: Dict[str, Any] = {}
        if "winner" in book_odds:
            odds_map["winner"] = book_odds["winner"]
        if "over_2_5" in book_odds:
            odds_map["over_2_5"] = book_odds["over_2_5"]
        if "over_1_5" in book_odds:
            odds_map["over_1_5"] = book_odds["over_1_5"]
        if "btts" in book_odds:
            odds_map["btts"] = book_odds["btts"]
        # (Sem fallback a implied — desaparece do JSON se não houver real.)

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
            "odds": odds_map,  # <- pode vir parcial ou vazio
            "predictions": {
                "winner": {"class": winner_class, "confidence": float(winner_conf)},
                "over_2_5": {"class": int(p_over25 >= 0.5), "confidence": float(p_over25)},
                "over_1_5": {"class": int(p_over15 >= 0.5), "confidence": float(p_over15)},
                "double_chance": {"class": dc_class, "confidence": float(p_dc)},
                "btts": {"class": int(p_btts >= 0.5), "confidence": float(p_btts)},
            },
            "correct_score_top3": top3,
            "top_scorers": top_scorers,
            "predicted_score": ps_obj,
            "confidence": float(winner_conf),
        }
        return out
    except Exception as e:
        logger.error(f"❌ build_prediction_from_fixture() erro: {e}")
        return None

# ---------------- Pipeline ----------------
def collect_fixtures(days: int = 3) -> List[Dict[str, Any]]:
    fixtures: List[Dict[str, Any]] = []
    for d in range(days):
        iso = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        payload = proxy_get("/fixtures", {"date": iso, "season": SEASON})
        if payload and isinstance(payload, dict) and isinstance(payload.get("response"), list):
            fixtures.extend(payload["response"])
        else:
            # fallback direto à API se o proxy não responder
            direct = api_get("fixtures", {"date": iso, "season": SEASON})
            if isinstance(direct, list):
                fixtures.extend(direct)
        time.sleep(0.2)

    if not fixtures:
        payload = proxy_get("/fixtures", {"next": 50})
        if payload and isinstance(payload, dict) and isinstance(payload.get("response"), list):
            fixtures = payload["response"]
        else:
            direct = api_get("fixtures", {"next": 50})
            if isinstance(direct, list):
                fixtures = direct
    return fixtures

def fetch_and_save_predictions() -> Dict[str, Any]:
    total = 0
    matches: List[Dict[str, Any]] = []

    logger.info(f"🌍 API-Football ativo | Época {SEASON}")
    fixtures = collect_fixtures(days=3)
    logger.info(f"📊 {len(fixtures)} fixtures carregados.")

    for f in fixtures:
        pred = build_prediction_from_fixture(f)
        if pred:
            matches.append(pred)
            total += 1

    matches_sorted = sorted(matches, key=lambda x: x["predictions"]["winner"]["confidence"], reverse=True)

    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(matches_sorted, fp, ensure_ascii=False, indent=2)

    logger.info(f"✅ {total} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": total}
