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

# ================== ENV ==================
API_KEY = os.getenv("API_FOOTBALL_KEY")
# usar SEMPRE o endpoint direto para odds/statistics
API_FOOTBALL_DIRECT = os.getenv("API_FOOTBALL_DIRECT", "https://v3.football.api-sports.io/").rstrip("/") + "/"
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")

# Proxy (apenas para fixtures, se quiseres)
PROXY_BASE = os.getenv("API_PROXY_URL", "https://football-proxy-4ymo.onrender.com").rstrip("/") + "/"
PROXY_TOKEN = os.getenv("API_PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")

PRED_PATH = os.path.join("data", "predict", "predictions.json")
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# ============== Redis cache leve ==============
def _rget(key: str):
    try:
        if config.redis_client:
            raw = config.redis_client.get(key)
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return None

def _rset(key: str, val: Any, ex: int = 1800):
    try:
        if config.redis_client:
            config.redis_client.set(key, json.dumps(val), ex=ex)
    except Exception:
        pass

# ============== HTTP helpers ==============
def proxy_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Optional[Dict[str, Any]]:
    url = urljoin(PROXY_BASE, path.lstrip("/"))
    try:
        r = requests.get(url, params=params or {}, headers={"x-proxy-token": PROXY_TOKEN, "Accept": "application/json"}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        logger.error(f"Proxy {url} {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"Proxy erro {url}: {e}")
    return None

def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8) -> Any:
    """Chama diretamente a API-Football (usa API_FOOTBALL_KEY)."""
    if not API_KEY:
        logger.warning("API_FOOTBALL_KEY ausente.")
        return []
    url = urljoin(API_FOOTBALL_DIRECT, endpoint.lstrip("/"))
    cache_key = f"af:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
    cached = _rget(cache_key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, headers=HEADERS, params=params or {}, timeout=timeout)
        if r.status_code == 200:
            data = r.json().get("response", [])
            _rset(cache_key, data, ex=1800)
            return data
        logger.warning(f"API {endpoint} {r.status_code}: {r.text[:200]}")
    except Exception as e:
        logger.error(f"API erro {endpoint}: {e}")
    return []

# ============== Poisson fallback ==============
def _pmf(lmbda: float, k: int) -> float:
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
        ph = _pmf(lambda_home, h)
        for a in range(max_goals + 1):
            pa = _pmf(lambda_away, a)
            row.append(ph * pa)
        mat.append(row)
    s = sum(sum(r) for r in mat)
    if s > 0:
        inv = 1.0 / s
        mat = [[x * inv for x in r] for r in mat]
    return mat

def outcome_probs_from_matrix(mat: List[List[float]]) -> Tuple[float, float, float]:
    ph = pd = pa = 0.0
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

def top_k_scores_from_matrix(mat: List[List[float]], k: int = 3):
    pairs = []
    n = len(mat)
    for h in range(n):
        for a in range(n):
            pairs.append((f"{h}-{a}", mat[h][a]))
    pairs.sort(key=lambda t: t[1], reverse=True)
    return pairs[:k]

# ============== Probs → odds util ==============
def clamp_prob(p: float, eps: float = 1e-6) -> float:
    return max(eps, min(1.0 - eps, p))

def implied_odds(p: float) -> float:
    p = clamp_prob(p, 1e-6)
    return round(1.0 / p, 2)

def pick_dc_class(ph: float, pd: float, pa: float) -> Tuple[int, float]:
    opts = [(0, ph + pd), (1, ph + pa), (2, pd + pa)]
    best = max(opts, key=lambda t: t[1])
    return best[0], best[1]

# ============== Estatísticas ==============
def team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    data = api_get("teams/statistics", {"team": team_id, "league": league_id, "season": SEASON})
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}

def compute_lambdas(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    def _f(x, d=1.0):
        try:
            if isinstance(x, str): x = x.replace(",", ".")
            return float(x)
        except Exception:
            return float(d)
    avg_h_for   = _f(stats_home.get("goals",{}).get("for",{}).get("average",{}).get("home",1.2))
    avg_a_for   = _f(stats_away.get("goals",{}).get("for",{}).get("average",{}).get("away",1.1))
    avg_h_again = _f(stats_home.get("goals",{}).get("against",{}).get("average",{}).get("home",1.0))
    avg_a_again = _f(stats_away.get("goals",{}).get("against",{}).get("average",{}).get("away",1.0))
    lam_h = max(0.05, (avg_h_for + avg_a_again) / 2.0)
    lam_a = max(0.05, (avg_a_for + avg_h_again) / 2.0)
    return lam_h, lam_a

# ============== Odds reais: O/U 2.5 ==============
def get_real_ou25_from_odds_endpoint(fixture_id: int) -> Optional[Dict[str, float]]:
    """
    Lê /odds (API-Football) e extrai Over/Under 2.5.
    Devolve {"over": x.xx, "under": y.yy} ou None se não existir.
    """
    try:
        arr = api_get("odds", {"fixture": fixture_id, "season": SEASON})
        # arr = [ { "bookmakers":[ { "name": "...", "bets":[ {"name":"Over/Under","values":[{"value":"Over 2.5","odd":"1.85"}, ...]} ] } ] } , ...]
        overs, unders = [], []
        for item in (arr or []):
            for bm in item.get("bookmakers", []) or []:
                for bet in bm.get("bets", []) or []:
                    name = (bet.get("name") or "").lower()
                    if "over/under" not in name:
                        continue
                    for v in bet.get("values", []) or []:
                        label = (v.get("value") or "").lower().replace(",", ".").strip()
                        odd_s = (v.get("odd") or "").replace(",", ".").strip()
                        try:
                            odd = float(odd_s)
                        except Exception:
                            continue
                        if label == "over 2.5":
                            overs.append(odd)
                        elif label == "under 2.5":
                            unders.append(odd)
        if overs and unders:
            # usa a mediana para reduzir outliers
            overs.sort(); unders.sort()
            o = overs[len(overs)//2]
            u = unders[len(unders)//2]
            # sanity check (1.2..100)
            if 1.2 <= o <= 100 and 1.2 <= u <= 100:
                return {"over": round(o,2), "under": round(u,2)}
    except Exception as e:
        logger.debug(f"odds/ou25 fixture={fixture_id}: {e}")
    return None

# ============== Fixtures (proxy + fallback) ==============
def collect_fixtures(days: int = 3) -> List[Dict[str, Any]]:
    fixtures: List[Dict[str, Any]] = []
    for d in range(days):
        iso = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        payload = proxy_get("/fixtures", {"date": iso, "season": SEASON})
        if payload and isinstance(payload, dict) and isinstance(payload.get("response"), list):
            fixtures.extend(payload["response"])
        time.sleep(0.15)
    if not fixtures:
        payload = proxy_get("/fixtures", {"next": 50})
        if payload and isinstance(payload, dict) and isinstance(payload.get("response"), list):
            fixtures = payload["response"]
    return fixtures

# ============== Build prediction por jogo ==============
def build_prediction_from_fixture(fix: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fixture = fix.get("fixture") or {}
        league  = fix.get("league")  or {}
        teams   = fix.get("teams")   or {}

        fid = fixture.get("id")
        lid = league.get("id")
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        if not fid or not home.get("id") or not away.get("id"):
            return None

        stats_h = team_stats(home["id"], lid)
        stats_a = team_stats(away["id"], lid)

        lam_h, lam_a = compute_lambdas(stats_h, stats_a)
        mat = poisson_score_probs(lam_h, lam_a, max_goals=6)

        ph, pd, pa = outcome_probs_from_matrix(mat)
        p_btts = btts_prob_from_matrix(mat)
        p_o25, p_u25 = over_under_prob_from_matrix(mat, 2.5)
        p_o15, p_u15 = over_under_prob_from_matrix(mat, 1.5)
        dc_cls, p_dc = pick_dc_class(ph, pd, pa)

        top3 = [{"score": s, "prob": float(p)} for (s, p) in top_k_scores_from_matrix(mat, k=3)]
        pred_score = top3[0]["score"] if top3 else "1-1"
        try:
            hs, as_ = pred_score.split("-")
            ps_obj = {"home": int(hs), "away": int(as_)}
        except Exception:
            ps_obj = {"home": None, "away": None}

        # --- TOP SCORERS (cache 12h) ---
        scorers_key = f"topsc:{lid}:{SEASON}"
        top_scorers = _rget(scorers_key)
        if top_scorers is None:
            tops = api_get("players/topscorers", {"league": lid, "season": SEASON})
            res = []
            for s in (tops or [])[:5]:
                pl = (s.get("player") or {}).get("name")
                st0 = (s.get("statistics") or [{}])[0]
                tm = (st0.get("team") or {}).get("name")
                gl = int(((st0.get("goals") or {}).get("total")) or 0)
                res.append({"player": pl, "team": tm, "goals": gl})
            top_scorers = res
            _rset(scorers_key, top_scorers, ex=12*3600)

        # --- ODDS ---
        # 1) implied para 1X2/BTTS/OU1.5
        odds_map = {
            "winner": {"home": implied_odds(ph), "draw": implied_odds(pd), "away": implied_odds(pa)},
            "over_1_5": {"over": implied_odds(p_o15), "under": implied_odds(p_u15)},
            "btts": {"yes": implied_odds(p_btts), "no": implied_odds(1.0 - p_btts)},
        }
        # 2) tentar OU 2.5 REAL via /odds
        ou25_real = get_real_ou25_from_odds_endpoint(int(fid))
        if ou25_real:
            odds_map.setdefault("over_under", {})["2.5"] = ou25_real
        else:
            # se não houver, NÃO força implied em over_under["2.5"]; o UI esconderá
            pass

        return {
            "match_id": fid,
            "league_id": lid,
            "league": league.get("name"),
            "country": league.get("country"),
            "date": fixture.get("date"),
            "home_team": home.get("name"),
            "away_team": away.get("name"),
            "home_logo": home.get("logo"),
            "away_logo": away.get("logo"),
            "odds": odds_map,
            "predictions": {
                "winner": {"class": int(max([(0,ph),(1,pd),(2,pa)], key=lambda t:t[1])[0]), "confidence": float(max(ph,pd,pa))},
                "over_2_5": {"class": int(p_o25 >= 0.5), "confidence": float(p_o25)},
                "over_1_5": {"class": int(p_o15 >= 0.5), "confidence": float(p_o15)},
                "double_chance": {"class": dc_cls, "confidence": float(p_dc)},
                "btts": {"class": int(p_btts >= 0.5), "confidence": float(p_btts)},
            },
            "correct_score_top3": top3,
            "top_scorers": top_scorers,
            "predicted_score": ps_obj,
            "confidence": float(max(ph,pd,pa)),
        }
    except Exception as e:
        logger.error(f"build_prediction_from_fixture erro: {e}")
        return None

# ============== Pipeline ==============
def fetch_and_save_predictions() -> Dict[str, Any]:
    total = 0
    matches: List[Dict[str, Any]] = []
    fixtures = collect_fixtures(days=3)
    for f in fixtures:
        p = build_prediction_from_fixture(f)
        if p:
            matches.append(p); total += 1
    matches.sort(key=lambda x: x["predictions"]["winner"]["confidence"], reverse=True)
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(matches, fp, ensure_ascii=False, indent=2)
    return {"status":"ok","total": total}
