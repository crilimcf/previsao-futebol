# src/api_fetch_pro.py
import os
import re
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

# ===================== ENV =====================
API_KEY   = os.getenv("API_FOOTBALL_KEY")
BASE_URL  = (os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").rstrip("/") + "/")
SEASON    = os.getenv("API_FOOTBALL_SEASON", "2025")

PROXY_BASE  = (os.getenv("API_PROXY_URL", "https://football-proxy-4ymo.onrender.com").rstrip("/") + "/")
PROXY_TOKEN = os.getenv("API_PROXY_TOKEN", "CF_Proxy_2025_Secret_!@#839")

PRED_PATH = os.path.join("data", "predict", "predictions.json")
HEADERS   = {"x-apisports-key": API_KEY} if API_KEY else {}

# ===================== Regex filtros =====================
YOUTH_RE  = re.compile(r"\bU(15|16|17|18|19|20|21|22|23)\b", re.I)
WOMEN_RE  = re.compile(r"\b(women|fem|fémin|feminina|feminino)\b", re.I)

# ===================== Redis cache =====================
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

# ===================== HTTP helpers =====================
def proxy_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Optional[Dict[str, Any]]:
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

def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Any:
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

# ===================== Poisson (fallback simples) =====================
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

# ===================== Odds helpers =====================
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
    for v in (bet.get("values") or []):
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

def _parse_match_winner(bet: Dict[str, Any], acc: Dict[str, List[float]]) -> None:
    for v in (bet.get("values") or []):
        label = (v.get("value") or "").lower().strip()
        odd_raw = v.get("odd")
        if odd_raw is None:
            continue
        try:
            odd = float(str(odd_raw).replace(",", "."))
        except Exception:
            continue
        if label in ("home", "1"):
            acc["home"].append(odd)
        elif label in ("draw", "x"):
            acc["draw"].append(odd)
        elif label in ("away", "2"):
            acc["away"].append(odd)

def _parse_btts(bet: Dict[str, Any], acc: Dict[str, List[float]]) -> None:
    for v in (bet.get("values") or []):
        label = (v.get("value") or "").lower().strip()
        odd_raw = v.get("odd")
        if odd_raw is None:
            continue
        try:
            odd = float(str(odd_raw).replace(",", "."))
        except Exception:
            continue
        if "yes" in label:
            acc["yes"].append(odd)
        elif "no" in label:
            acc["no"].append(odd)

def get_market_odds(fixture_id: int) -> Dict[str, Any]:
    """
    Busca odds de mercado (mediana entre bookmakers).
    Ordem de tentativa:
      1) proxy /odds (SEM season)
      2) proxy /odds (COM season)
      3) API /odds (SEM season)
      4) API /odds (COM season)
    """
    payload: Optional[Dict[str, Any]] = None

    # 1) proxy sem season
    try:
        pj = proxy_get("/odds", {"fixture": fixture_id})
        if pj and isinstance(pj.get("response"), list) and pj["response"]:
            payload = pj
    except Exception:
        payload = None

    # 2) proxy com season
    if payload is None:
        pj = proxy_get("/odds", {"fixture": fixture_id, "season": SEASON})
        if pj and isinstance(pj.get("response"), list) and pj["response"]:
            payload = pj

    # 3) api direta sem season
    if payload is None:
        resp = api_get("odds", {"fixture": fixture_id})
        payload = {"response": resp if isinstance(resp, list) else []}

    # 4) api direta com season
    if not payload.get("response"):
        resp = api_get("odds", {"fixture": fixture_id, "season": SEASON})
        payload = {"response": resp if isinstance(resp, list) else []}

    # acumular listas e tirar mediana no fim
    acc_winner = {"home": [], "draw": [], "away": []}
    acc_ou25   = {"over": [], "under": []}
    acc_btts   = {"yes": [], "no": []}

    try:
        for item in payload.get("response", []):
            for bm in (item.get("bookmakers") or []):
                for bet in (bm.get("bets") or []):
                    name = (bet.get("name") or "").lower().strip()
                    if name in ("match winner", "1x2"):
                        _parse_match_winner(bet, acc_winner)
                    elif ("over/under" in name) or ("under/over" in name):
                        over, under = _parse_over_under(bet, 2.5)
                        if over is not None:  acc_ou25["over"].append(over)
                        if under is not None: acc_ou25["under"].append(under)
                    elif ("both teams to score" in name) or ("btts" in name):
                        _parse_btts(bet, acc_btts)
    except Exception as e:
        logger.debug(f"odds parse fail {fixture_id}: {e}")

    out = {
        "winner": {
            "home": _median_or_none(acc_winner["home"]),
            "draw": _median_or_none(acc_winner["draw"]),
            "away": _median_or_none(acc_winner["away"]),
        },
        "over_2_5": {
            "over":  _median_or_none(acc_ou25["over"]),
            "under": _median_or_none(acc_ou25["under"]),
        },
        "btts": {
            "yes": _median_or_none(acc_btts["yes"]),
            "no":  _median_or_none(acc_btts["no"]),
        },
    }

    # range sanity
    for sect in (out["winner"], out["over_2_5"], out["btts"]):
        for k, v in list(sect.items()):
            if isinstance(v, (int, float)) and not (1.05 <= v <= 100.0):
                sect[k] = None
    return out

# ===================== Features/Stats =====================
def team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    data = api_get("teams/statistics", {"team": team_id, "league": league_id, "season": SEASON})
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}

def compute_lambdas(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    def _get_float(path, default=1.0):
        try:
            v = path
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

def clamp_prob(p: float, eps: float = 1e-6) -> float:
    return max(eps, min(1.0 - eps, p))

def implied_odds(p: float) -> float:
    p = clamp_prob(p)
    return round(1.0 / p, 2)

def pick_dc_class(ph: float, pd: float, pa: float) -> Tuple[int, float]:
    opts = [(0, ph+pd), (1, ph+pa), (2, pd+pa)]
    best = max(opts, key=lambda t: t[1])
    return best[0], best[1]

# ===================== Seletores auxiliares =====================
def _is_youth_or_women_league(name: str) -> bool:
    n = (name or "").lower()
    return bool(YOUTH_RE.search(n) or WOMEN_RE.search(n))

def _dedupe_fixtures(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        fid = ((it.get("fixture") or {}).get("id")) or it.get("id")
        if fid and fid not in seen:
            seen.add(fid)
            out.append(it)
    return out

# ===================== Build prediction =====================
def build_prediction_from_fixture(fix: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        fixture = fix.get("fixture", {}) or {}
        league  = fix.get("league", {}) or {}
        teams   = fix.get("teams", {}) or {}

        league_id   = league.get("id")
        league_name = league.get("name")
        country     = league.get("country")

        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}
        home_id = home.get("id")
        away_id = away.get("id")
        if not home_id or not away_id or not league_id:
            return None

        # filtro U-xx/Women pela liga (mantém clubes e Seleções A)
        if _is_youth_or_women_league(league_name or ""):
            return None

        stats_h = team_stats(int(home_id), int(league_id))
        stats_a = team_stats(int(away_id), int(league_id))

        lam_h, lam_a = compute_lambdas(stats_h, stats_a)
        mat = poisson_score_probs(lam_h, lam_a, max_goals=6)

        ph, pd, pa = outcome_probs_from_matrix(mat)
        p_btts = btts_prob_from_matrix(mat)
        p_over25, p_under25 = over_under_prob_from_matrix(mat, 2.5)
        p_over15, p_under15 = over_under_prob_from_matrix(mat, 1.5)
        dc_class, p_dc = pick_dc_class(ph, pd, pa)

        winner_class = int(max([(0, ph), (1, pd), (2, pa)], key=lambda t: t[1])[0])
        winner_conf  = max(ph, pd, pa)
        top3 = [{"score": s, "prob": float(p)} for (s, p) in top_k_scores_from_matrix(mat, k=3)]

        # ----- odds "implied" do modelo (fallback base) -----
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
                "no":  implied_odds(1.0 - p_btts),
            },
        }
        odds_source = "model"

        # ----- tentar substituir por odds reais de mercado -----
        fix_id = fixture.get("id")
        if fix_id:
            mkt = get_market_odds(int(fix_id))

            # Winner
            w = mkt.get("winner") or {}
            if any(isinstance(v, (int, float)) for v in w.values()):
                for k in ("home", "draw", "away"):
                    if isinstance(w.get(k), (int, float)):
                        odds_map["winner"][k] = w[k]
                odds_source = "market"

            # OU 2.5
            ou = mkt.get("over_2_5") or {}
            if isinstance(ou.get("over"), (int, float)) and isinstance(ou.get("under"), (int, float)):
                odds_map["over_2_5"]["over"]  = ou["over"]
                odds_map["over_2_5"]["under"] = ou["under"]
                odds_source = "market"

            # BTTS
            bt = mkt.get("btts") or {}
            if isinstance(bt.get("yes"), (int, float)) and isinstance(bt.get("no"), (int, float)):
                odds_map["btts"]["yes"] = bt["yes"]
                odds_map["btts"]["no"]  = bt["no"]
                odds_source = "market"

        pred_score = (top3[0]["score"] if top3 else "1-1")
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
                "winner":     {"class": winner_class, "confidence": float(winner_conf)},
                "over_2_5":   {"class": int(p_over25 >= 0.5), "confidence": float(p_over25)},
                "over_1_5":   {"class": int(p_over15 >= 0.5), "confidence": float(p_over15)},
                "double_chance": {"class": dc_class, "confidence": float(p_dc)},
                "btts":       {"class": int(p_btts >= 0.5), "confidence": float(p_btts)},
            },
            "correct_score_top3": top3,
            "top_scorers": _get_top_scorers_cached(int(league_id)),
            "predicted_score": ps_obj,
            "confidence": float(winner_conf),
        }
        return out
    except Exception as e:
        logger.error(f"build_prediction_from_fixture() erro: {e}")
        return None

def _get_top_scorers_cached(league_id: int) -> List[Dict[str, Any]]:
    key = f"topscorers:{league_id}:{SEASON}"
    cached = redis_cache_get(key)
    if cached is not None:
        return cached
    tops = api_get("players/topscorers", {"league": league_id, "season": SEASON})
    res: List[Dict[str, Any]] = []
    for s in (tops or [])[:5]:
        player = (s.get("player") or {}).get("name")
        stat0  = (s.get("statistics") or [{}])[0]
        team   = (stat0.get("team") or {}).get("name")
        goals  = (stat0.get("goals") or {}).get("total", 0)
        res.append({"player": player, "team": team, "goals": int(goals or 0)})
    redis_cache_set(key, res, ex=12*3600)
    return res

# ===================== Fixtures & pipeline =====================
def collect_fixtures(days: int = 3) -> List[Dict[str, Any]]:
    """
    Junta fixtures por data (hoje..+days-1):
      proxy SEM season -> proxy COM season -> API direta SEM season -> API COM season
      + dedupe + filtro U-xx/Women
    """
    fixtures: List[Dict[str, Any]] = []
    tz = "Europe/Lisbon"

    for d in range(days):
        iso = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")

        # 1) proxy sem season
        pj = proxy_get("/fixtures", {"date": iso, "timezone": tz})
        if pj and isinstance(pj.get("response"), list):
            fixtures.extend(pj["response"])

        # 2) proxy com season (complemento)
        pj2 = proxy_get("/fixtures", {"date": iso, "season": SEASON, "timezone": tz})
        if pj2 and isinstance(pj2.get("response"), list):
            fixtures.extend(pj2["response"])

        # 3) api direta sem season (só se nada chegou via proxy para esse dia)
        if not any(((f.get("fixture") or {}).get("date", "") or "").startswith(iso) for f in fixtures):
            r1 = api_get("fixtures", {"date": iso, "timezone": tz})
            if isinstance(r1, list) and r1:
                fixtures.extend(r1)

        # 4) api direta com season (complemento final)
        r2 = api_get("fixtures", {"date": iso, "season": SEASON, "timezone": tz})
        if isinstance(r2, list) and r2:
            fixtures.extend(r2)

        time.sleep(0.2)

    # 5) Fallback: próximos N
    if not fixtures:
        pj = proxy_get("/fixtures", {"next": 120, "timezone": tz})
        if pj and isinstance(pj.get("response"), list):
            fixtures = pj["response"]
        else:
            r3 = api_get("fixtures", {"next": 120, "timezone": tz})
            if isinstance(r3, list):
                fixtures = r3

    # dedupe
    fixtures = _dedupe_fixtures(fixtures)

    # filtrar U-xx/Women
    clean: List[Dict[str, Any]] = []
    for f in fixtures:
        league = (f.get("league") or {})
        lname = league.get("name") or ""
        if _is_youth_or_women_league(lname):
            continue
        clean.append(f)

    return clean

def fetch_and_save_predictions(days: int = 3) -> Dict[str, Any]:
    total = 0
    matches: List[Dict[str, Any]] = []
    logger.info(f"API-Football ativo | Época {SEASON}")

    fixtures = collect_fixtures(days=days)
    logger.info(f"{len(fixtures)} fixtures carregados.")

    for f in fixtures:
        pred = build_prediction_from_fixture(f)
        if pred:
            matches.append(pred)
            total += 1

    matches_sorted = sorted(matches, key=lambda x: x["predictions"]["winner"]["confidence"], reverse=True)
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(matches_sorted, fp, ensure_ascii=False, indent=2)

    logger.info(f"{total} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": total}
