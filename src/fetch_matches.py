# src/fetch_matches.py
import os
import json
import time
import math
import random
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from src import config

logger = logging.getLogger("football_api")

# =========================
# ENV & CONSTANTES
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# Bookmaker preferencial (se existir na resposta). Se não, escolhe o 1º disponível.
PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

# Limites
REQUEST_TIMEOUT = 3
MAX_GOALS = 6  # para matriz de Poisson 0..6
DAYS_AHEAD = 3  # hoje + 2 dias


# =========================
# Redis helper (via config)
# =========================
redis = config.redis_client

def _rget(key: str) -> Optional[str]:
    try:
        return redis.get(key) if redis else None
    except Exception:
        return None

def _rset(key: str, value: str, ex: Optional[int] = 3600):
    try:
        if redis:
            redis.set(key, value, ex=ex)
    except Exception:
        pass


# =========================
# HTTP + CACHE
# =========================
def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    p = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return f"cache:{url}:{p}"

def safe_request(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """GET com cache Redis e timeout curto. Devolve r.json().get('response', []) ou {}."""
    key = _cache_key(url, params)
    cached = _rget(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            data = body.get("response", body)
            # guarda 1h
            _rset(key, json.dumps(data), ex=3600)
            logger.info(f"✅ {url} OK")
            return data
        else:
            logger.warning(f"⚠️ {url} -> HTTP {r.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ {url} erro: {e}")
        return []


# =========================
# CARREGAR LIGAS
# =========================
def _load_target_league_ids() -> List[int]:
    """Se existir config/leagues.json usa-o; caso contrário lê da API e cacheia 12h."""
    path = "config/leagues.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                leagues = json.load(f)
            ids = [int(l["id"]) for l in leagues if "id" in l]
            if ids:
                return ids
        except Exception as e:
            logger.warning(f"⚠️ leagues.json inválido: {e}")

    # Fallback: pedir à API
    ck = "cache:all_leagues_ids"
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    data = safe_request(f"{BASE_URL}leagues", {"season": SEASON})
    ids = []
    try:
        for item in data:
            lg = item.get("league", {})
            if lg.get("id"):
                ids.append(int(lg["id"]))
        # únicos
        ids = sorted(list(set(ids)))
        _rset(ck, json.dumps(ids), ex=43200)  # 12h
    except Exception as e:
        logger.warning(f"⚠️ a obter ligas: {e}")
        # fallback mínimo
        ids = [39, 140, 135, 78, 61, 94, 88, 2]
    return ids


# =========================
# FIXTURES + ODDS + STATS
# =========================
def _fixtures_by_date(yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    params = {"date": yyyy_mm_dd, "season": SEASON}
    return safe_request(f"{BASE_URL}fixtures", params) or []

def _odds_by_fixture(fixture_id: int) -> Dict[str, Any]:
    """Devolve odds já agregadas por mercado: 1x2, double_chance, over_under, btts."""
    raw = safe_request(f"{BASE_URL}odds", {"fixture": fixture_id}) or []
    if not raw:
        return {}

    # Estrutura esperada: [{bookmakers:[{name, bets:[{name, values:[{value, odd},...]}, ...]}]}]
    # Escolher bookmaker preferido, senão 1º.
    best_bm = None
    try:
        for row in raw:
            bms = row.get("bookmakers") or []
            # preferidos
            pref = [b for b in bms if b.get("name") in PREFERRED_BOOKMAKERS]
            candidates = pref or bms
            if not candidates:
                continue
            best_bm = candidates[0]
            break
    except Exception:
        pass

    if not best_bm:
        return {}

    bets = best_bm.get("bets") or []
    out = {"1x2": {}, "double_chance": {}, "over_under": {}, "btts": {}}

    def _push_ou(line_name: str, value: str, odd: str):
        # line_name típico: "Over/Under 2.5" | "Over/Under"
        # value: "Over 2.5" | "Under 2.5"
        try:
            parts = value.split()
            if len(parts) >= 2 and parts[0] in {"Over", "Under"}:
                line = parts[1]  # 2.5
                d = out["over_under"].setdefault(line, {})
                d[parts[0].lower()] = float(odd)
        except Exception:
            pass

    for b in bets:
        name = (b.get("name") or "").lower()
        values = b.get("values") or []

        if "match winner" in name or name in {"winner", "1x2"}:
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                if val in {"home", "1"}:
                    out["1x2"]["home"] = odd
                elif val in {"draw", "x"}:
                    out["1x2"]["draw"] = odd
                elif val in {"away", "2"}:
                    out["1x2"]["away"] = odd

        elif "double chance" in name or name == "double chance (1x2)":
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                key = val.replace(" ", "")  # "1X", "X2", "12"
                out["double_chance"][key] = odd

        elif "over/under" in name:
            for v in values:
                try:
                    _push_ou(b.get("name") or "", v.get("value") or "", v.get("odd"))
                except Exception:
                    continue

        elif "both teams to score" in name or "btts" in name:
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                if val in {"yes", "sim"}:
                    out["btts"]["yes"] = odd
                elif val in {"no", "não", "nao"}:
                    out["btts"]["no"] = odd

    return out


def _team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    """/teams/statistics (cache 6h)."""
    url = f"{BASE_URL}teams/statistics"
    params = {"team": team_id, "league": league_id, "season": SEASON}
    ck = _cache_key(url, params)
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    data = safe_request(url, params)
    # guardar um dict simples (em alguns casos o endpoint devolve diretamente um dict)
    try:
        if isinstance(data, list) and data:
            data = data[0]
    except Exception:
        pass
    _rset(ck, json.dumps(data), ex=21600)
    return data or {}


def _top_scorers(league_id: int) -> List[Dict[str, Any]]:
    """players/topscorers (cache 6h)."""
    url = f"{BASE_URL}players/topscorers"
    params = {"league": league_id, "season": SEASON}
    data = safe_request(url, params) or []
    out = []
    try:
        for s in data[:5]:
            player = (s.get("player") or {}).get("name")
            stats = (s.get("statistics") or [{}])[0]
            team = (stats.get("team") or {}).get("name")
            goals = ((stats.get("goals") or {}).get("total")) or 0
            out.append(
                {
                    "player": player,
                    "team": team,
                    "goals": goals,
                    # prob heurística: só para ranking na UI
                    "probability": round(0.40 + goals * 0.05 + random.uniform(0.03, 0.08), 2),
                }
            )
    except Exception:
        pass
    return out


# =========================
# POISSON
# =========================
def _poisson_pmf(lmbda: float, k: int) -> float:
    try:
        return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)
    except OverflowError:
        return 0.0

def _poisson_matrix(lh: float, la: float, max_goals: int = MAX_GOALS) -> List[List[float]]:
    mat = []
    for i in range(max_goals + 1):
        row = []
        ph = _poisson_pmf(lh, i)
        for j in range(max_goals + 1):
            pa = _poisson_pmf(la, j)
            row.append(ph * pa)
        mat.append(row)
    # normalizar para somar ~1 (bordas cortadas)
    s = sum(sum(r) for r in mat)
    if s > 0:
        for i in range(len(mat)):
            for j in range(len(mat[0])):
                mat[i][j] /= s
    return mat

def _params_from_stats(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    """
    Estima λ_home e λ_away a partir de médias 'for/against' home/away.
    Mistura simples e robusta a dados faltantes.
    """
    def _flt(v, dv=1.1):
        try:
            if v is None:
                return dv
            return float(v)
        except Exception:
            return dv

    gh_home = _flt(((stats_home.get("goals") or {}).get("for") or {}).get("average", {}).get("home"), 1.2)
    ga_home = _flt(((stats_home.get("goals") or {}).get("against") or {}).get("average", {}).get("home"), 1.0)
    gh_away = _flt(((stats_away.get("goals") or {}).get("for") or {}).get("average", {}).get("away"), 1.1)
    ga_away = _flt(((stats_away.get("goals") or {}).get("against") or {}).get("average", {}).get("away"), 1.0)

    # mistura e bounding
    lam_h = max(0.2, min(3.5, 0.6 * gh_home + 0.4 * ga_away))
    lam_a = max(0.2, min(3.5, 0.6 * gh_away + 0.4 * ga_home))
    return lam_h, lam_a

def _probs_from_matrix(mat: List[List[float]]) -> Dict[str, Any]:
    # Winner
    p_home = sum(mat[i][j] for i in range(len(mat)) for j in range(len(mat)) if i > j)
    p_draw = sum(mat[i][i] for i in range(len(mat)))
    p_away = 1.0 - p_home - p_draw

    # Overs
    def _psum(cond) -> float:
        s = 0.0
        for i in range(len(mat)):
            for j in range(len(mat)):
                if cond(i, j):
                    s += mat[i][j]
        return s

    p_over15 = _psum(lambda i, j: (i + j) >= 2)
    p_over25 = _psum(lambda i, j: (i + j) >= 3)
    p_btts = _psum(lambda i, j: (i >= 1 and j >= 1))

    # Double chance
    p_1x = p_home + p_draw
    p_12 = p_home + p_away
    p_x2 = p_draw + p_away

    # Correct score top3
    flat = []
    for i in range(len(mat)):
        for j in range(len(mat[0])):
            flat.append(((i, j), mat[i][j]))
    flat.sort(key=lambda x: x[1], reverse=True)
    top3 = [{"score": f"{a}-{b}", "prob": round(p, 4)} for (a, b), p in flat[:3]]

    return {
        "winner": {"home": p_home, "draw": p_draw, "away": p_away},
        "over_1_5": p_over15,
        "over_2_5": p_over25,
        "btts": p_btts,
        "double_chance": {"1X": p_1x, "12": p_12, "X2": p_x2},
        "correct_score_top3": top3,
    }


# =========================
# BUILD REGISTO FINAL
# =========================
def _pick_max(d: Dict[str, float]) -> Tuple[str, float]:
    if not d:
        return "N/A", 0.0
    k = max(d.keys(), key=lambda x: d[x])
    return k, float(d[k])

def _predicted_score_from_top(top3: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    if not top3:
        return {"home": None, "away": None}
    s = top3[0]["score"]
    try:
        h, a = s.split("-")
        return {"home": int(h), "away": int(a)}
    except Exception:
        return {"home": None, "away": None}


def _build_match_record(fix: Dict[str, Any], odds: Dict[str, Any],
                        probs: Dict[str, Any], scorers: List[Dict[str, Any]]) -> Dict[str, Any]:
    fixture = fix.get("fixture", {})
    league = fix.get("league", {})
    teams = fix.get("teams", {})

    fid = fixture.get("id")
    lg_id = league.get("id")
    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}

    # vencedor
    w_label, w_prob = _pick_max(probs["winner"])
    winner_class = {"home": 0, "draw": 1, "away": 2}.get(w_label, None)

    # DC
    dc_label, dc_prob = _pick_max(probs["double_chance"])
    # overs/btts
    over25 = 1 if probs["over_2_5"] >= 0.5 else 0
    over15 = 1 if probs["over_1_5"] >= 0.5 else 0
    btts    = 1 if probs["btts"]     >= 0.5 else 0

    top3 = probs["correct_score_top3"]
    pred_score = _predicted_score_from_top(top3)

    # odds achatadas úteis na UI anterior
    odds_1x2 = odds.get("1x2") or {}
    home_odd = odds_1x2.get("home")
    draw_odd = odds_1x2.get("draw")
    away_odd = odds_1x2.get("away")

    return {
        # meta
        "fixture_id": fid,
        "match_id": fid,
        "league_id": lg_id,
        "league_name": league.get("name"),
        "country": league.get("country"),
        "date": fixture.get("date"),
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "home_logo": home.get("logo"),
        "away_logo": away.get("logo"),

        # odds consolidadas
        "odds": {
            "1x2": odds_1x2,
            "double_chance": odds.get("double_chance", {}),
            "over_under": odds.get("over_under", {}),
            "btts": odds.get("btts", {}),
        },

        # legado para UI antiga
        "predicted_score": pred_score,
        "confidence": round(float(w_prob), 4),

        # bloco detalhado
        "predictions": {
            "winner": {"class": winner_class, "prob": round(float(w_prob), 4)},
            "double_chance": {"class": dc_label, "prob": round(float(dc_prob), 4)},
            "over_2_5": {"class": over25, "prob": round(float(probs["over_2_5"]), 4)},
            "over_1_5": {"class": over15, "prob": round(float(probs["over_1_5"]), 4)},
            "btts": {"class": btts, "prob": round(float(probs["btts"]), 4)},
            "correct_score": {"best": f"{pred_score['home']}-{pred_score['away']}", "top3": top3},
        },

        # topscorers da liga (opcional, dá jeito na UI)
        "top_scorers": scorers,
    }


# =========================
# PIPELINE PRINCIPAL
# =========================
def fetch_today_matches() -> Dict[str, Any]:
    """
    Busca fixtures (hoje + 2 dias), agrega odds e stats, calcula previsões
    e grava em data/predict/predictions.json (sem BOM).
    Retorna {"status": "ok", "total": N}
    """
    if not API_KEY:
        msg = "❌ API_FOOTBALL_KEY não definida."
        logger.error(msg)
        return {"status": "error", "detail": "API key missing", "total": 0}

    # 1) fixtures de hoje e próximos 2 dias (todas as ligas ou ligas de config/leagues.json)
    target_leagues = set(_load_target_league_ids())
    all_fixtures: List[Dict[str, Any]] = []

    for d in range(DAYS_AHEAD):
        dt = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        fixtures = _fixtures_by_date(dt) or []
        for f in fixtures:
            lg = (f.get("league") or {})
            if not lg.get("id"):
                continue
            if target_leagues and int(lg["id"]) not in target_leagues:
                continue
            all_fixtures.append(f)

    # 2) por liga, pré-carregar top scorers (cache)
    league_ids = sorted(list({(f.get("league") or {}).get("id") for f in all_fixtures if (f.get("league") or {}).get("id")}))
    scorers_by_league = {int(lid): _top_scorers(int(lid)) for lid in league_ids if lid}

    # 3) loop fixtures -> odds, stats equipas, Poisson, registo final
    out: List[Dict[str, Any]] = []

    for f in all_fixtures:
        fixture = f.get("fixture") or {}
        league  = f.get("league") or {}
        teams   = f.get("teams") or {}
        fid = fixture.get("id")
        lg_id = league.get("id")
        if not fid or not lg_id:
            continue

        home_id = (teams.get("home") or {}).get("id")
        away_id = (teams.get("away") or {}).get("id")
        if not home_id or not away_id:
            continue

        # odds
        odds = _odds_by_fixture(int(fid)) or {}

        # stats -> params Poisson
        st_home = _team_stats(int(home_id), int(lg_id)) or {}
        st_away = _team_stats(int(away_id), int(lg_id)) or {}

        lam_h, lam_a = _params_from_stats(st_home, st_away)
        mat = _poisson_matrix(lam_h, lam_a, MAX_GOALS)
        probs = _probs_from_matrix(mat)

        # scorers liga
        top_scorers = scorers_by_league.get(int(lg_id), [])

        out.append(_build_match_record(f, odds, probs, top_scorers))

    # 4) escrever ficheiro (sem BOM) e atualizar Redis
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    try:
        config.update_last_update()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao atualizar Redis: {e}")

    logger.info(f"✅ {len(out)} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": len(out)}


# Execução direta local
if __name__ == "__main__":
    print(fetch_today_matches())
# src/fetch_matches.py
import os
import json
import time
import math
import random
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from src import config

logger = logging.getLogger("football_api")

# =========================
# ENV & CONSTANTES
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
PRED_PATH = "data/predict/predictions.json"

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

# Bookmaker preferencial (se existir na resposta). Se não, escolhe o 1º disponível.
PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "1xBet", "1XBET"}

# Limites
REQUEST_TIMEOUT = 3
MAX_GOALS = 6  # para matriz de Poisson 0..6
DAYS_AHEAD = 3  # hoje + 2 dias


# =========================
# Redis helper (via config)
# =========================
redis = config.redis_client

def _rget(key: str) -> Optional[str]:
    try:
        return redis.get(key) if redis else None
    except Exception:
        return None

def _rset(key: str, value: str, ex: Optional[int] = 3600):
    try:
        if redis:
            redis.set(key, value, ex=ex)
    except Exception:
        pass


# =========================
# HTTP + CACHE
# =========================
def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    p = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return f"cache:{url}:{p}"

def safe_request(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """GET com cache Redis e timeout curto. Devolve r.json().get('response', []) ou {}."""
    key = _cache_key(url, params)
    cached = _rget(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            data = body.get("response", body)
            # guarda 1h
            _rset(key, json.dumps(data), ex=3600)
            logger.info(f"✅ {url} OK")
            return data
        else:
            logger.warning(f"⚠️ {url} -> HTTP {r.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ {url} erro: {e}")
        return []


# =========================
# CARREGAR LIGAS
# =========================
def _load_target_league_ids() -> List[int]:
    """Se existir config/leagues.json usa-o; caso contrário lê da API e cacheia 12h."""
    path = "config/leagues.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                leagues = json.load(f)
            ids = [int(l["id"]) for l in leagues if "id" in l]
            if ids:
                return ids
        except Exception as e:
            logger.warning(f"⚠️ leagues.json inválido: {e}")

    # Fallback: pedir à API
    ck = "cache:all_leagues_ids"
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    data = safe_request(f"{BASE_URL}leagues", {"season": SEASON})
    ids = []
    try:
        for item in data:
            lg = item.get("league", {})
            if lg.get("id"):
                ids.append(int(lg["id"]))
        # únicos
        ids = sorted(list(set(ids)))
        _rset(ck, json.dumps(ids), ex=43200)  # 12h
    except Exception as e:
        logger.warning(f"⚠️ a obter ligas: {e}")
        # fallback mínimo
        ids = [39, 140, 135, 78, 61, 94, 88, 2]
    return ids


# =========================
# FIXTURES + ODDS + STATS
# =========================
def _fixtures_by_date(yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    params = {"date": yyyy_mm_dd, "season": SEASON}
    return safe_request(f"{BASE_URL}fixtures", params) or []

def _odds_by_fixture(fixture_id: int) -> Dict[str, Any]:
    """Devolve odds já agregadas por mercado: 1x2, double_chance, over_under, btts."""
    raw = safe_request(f"{BASE_URL}odds", {"fixture": fixture_id}) or []
    if not raw:
        return {}

    # Estrutura esperada: [{bookmakers:[{name, bets:[{name, values:[{value, odd},...]}, ...]}]}]
    # Escolher bookmaker preferido, senão 1º.
    best_bm = None
    try:
        for row in raw:
            bms = row.get("bookmakers") or []
            # preferidos
            pref = [b for b in bms if b.get("name") in PREFERRED_BOOKMAKERS]
            candidates = pref or bms
            if not candidates:
                continue
            best_bm = candidates[0]
            break
    except Exception:
        pass

    if not best_bm:
        return {}

    bets = best_bm.get("bets") or []
    out = {"1x2": {}, "double_chance": {}, "over_under": {}, "btts": {}}

    def _push_ou(line_name: str, value: str, odd: str):
        # line_name típico: "Over/Under 2.5" | "Over/Under"
        # value: "Over 2.5" | "Under 2.5"
        try:
            parts = value.split()
            if len(parts) >= 2 and parts[0] in {"Over", "Under"}:
                line = parts[1]  # 2.5
                d = out["over_under"].setdefault(line, {})
                d[parts[0].lower()] = float(odd)
        except Exception:
            pass

    for b in bets:
        name = (b.get("name") or "").lower()
        values = b.get("values") or []

        if "match winner" in name or name in {"winner", "1x2"}:
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                if val in {"home", "1"}:
                    out["1x2"]["home"] = odd
                elif val in {"draw", "x"}:
                    out["1x2"]["draw"] = odd
                elif val in {"away", "2"}:
                    out["1x2"]["away"] = odd

        elif "double chance" in name or name == "double chance (1x2)":
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                key = val.replace(" ", "")  # "1X", "X2", "12"
                out["double_chance"][key] = odd

        elif "over/under" in name:
            for v in values:
                try:
                    _push_ou(b.get("name") or "", v.get("value") or "", v.get("odd"))
                except Exception:
                    continue

        elif "both teams to score" in name or "btts" in name:
            for v in values:
                val = (v.get("value") or "").lower()
                try:
                    odd = float(v.get("odd"))
                except Exception:
                    continue
                if val in {"yes", "sim"}:
                    out["btts"]["yes"] = odd
                elif val in {"no", "não", "nao"}:
                    out["btts"]["no"] = odd

    return out


def _team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    """/teams/statistics (cache 6h)."""
    url = f"{BASE_URL}teams/statistics"
    params = {"team": team_id, "league": league_id, "season": SEASON}
    ck = _cache_key(url, params)
    cached = _rget(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    data = safe_request(url, params)
    # guardar um dict simples (em alguns casos o endpoint devolve diretamente um dict)
    try:
        if isinstance(data, list) and data:
            data = data[0]
    except Exception:
        pass
    _rset(ck, json.dumps(data), ex=21600)
    return data or {}


def _top_scorers(league_id: int) -> List[Dict[str, Any]]:
    """players/topscorers (cache 6h)."""
    url = f"{BASE_URL}players/topscorers"
    params = {"league": league_id, "season": SEASON}
    data = safe_request(url, params) or []
    out = []
    try:
        for s in data[:5]:
            player = (s.get("player") or {}).get("name")
            stats = (s.get("statistics") or [{}])[0]
            team = (stats.get("team") or {}).get("name")
            goals = ((stats.get("goals") or {}).get("total")) or 0
            out.append(
                {
                    "player": player,
                    "team": team,
                    "goals": goals,
                    # prob heurística: só para ranking na UI
                    "probability": round(0.40 + goals * 0.05 + random.uniform(0.03, 0.08), 2),
                }
            )
    except Exception:
        pass
    return out


# =========================
# POISSON
# =========================
def _poisson_pmf(lmbda: float, k: int) -> float:
    try:
        return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)
    except OverflowError:
        return 0.0

def _poisson_matrix(lh: float, la: float, max_goals: int = MAX_GOALS) -> List[List[float]]:
    mat = []
    for i in range(max_goals + 1):
        row = []
        ph = _poisson_pmf(lh, i)
        for j in range(max_goals + 1):
            pa = _poisson_pmf(la, j)
            row.append(ph * pa)
        mat.append(row)
    # normalizar para somar ~1 (bordas cortadas)
    s = sum(sum(r) for r in mat)
    if s > 0:
        for i in range(len(mat)):
            for j in range(len(mat[0])):
                mat[i][j] /= s
    return mat

def _params_from_stats(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    """
    Estima λ_home e λ_away a partir de médias 'for/against' home/away.
    Mistura simples e robusta a dados faltantes.
    """
    def _flt(v, dv=1.1):
        try:
            if v is None:
                return dv
            return float(v)
        except Exception:
            return dv

    gh_home = _flt(((stats_home.get("goals") or {}).get("for") or {}).get("average", {}).get("home"), 1.2)
    ga_home = _flt(((stats_home.get("goals") or {}).get("against") or {}).get("average", {}).get("home"), 1.0)
    gh_away = _flt(((stats_away.get("goals") or {}).get("for") or {}).get("average", {}).get("away"), 1.1)
    ga_away = _flt(((stats_away.get("goals") or {}).get("against") or {}).get("average", {}).get("away"), 1.0)

    # mistura e bounding
    lam_h = max(0.2, min(3.5, 0.6 * gh_home + 0.4 * ga_away))
    lam_a = max(0.2, min(3.5, 0.6 * gh_away + 0.4 * ga_home))
    return lam_h, lam_a

def _probs_from_matrix(mat: List[List[float]]) -> Dict[str, Any]:
    # Winner
    p_home = sum(mat[i][j] for i in range(len(mat)) for j in range(len(mat)) if i > j)
    p_draw = sum(mat[i][i] for i in range(len(mat)))
    p_away = 1.0 - p_home - p_draw

    # Overs
    def _psum(cond) -> float:
        s = 0.0
        for i in range(len(mat)):
            for j in range(len(mat)):
                if cond(i, j):
                    s += mat[i][j]
        return s

    p_over15 = _psum(lambda i, j: (i + j) >= 2)
    p_over25 = _psum(lambda i, j: (i + j) >= 3)
    p_btts = _psum(lambda i, j: (i >= 1 and j >= 1))

    # Double chance
    p_1x = p_home + p_draw
    p_12 = p_home + p_away
    p_x2 = p_draw + p_away

    # Correct score top3
    flat = []
    for i in range(len(mat)):
        for j in range(len(mat[0])):
            flat.append(((i, j), mat[i][j]))
    flat.sort(key=lambda x: x[1], reverse=True)
    top3 = [{"score": f"{a}-{b}", "prob": round(p, 4)} for (a, b), p in flat[:3]]

    return {
        "winner": {"home": p_home, "draw": p_draw, "away": p_away},
        "over_1_5": p_over15,
        "over_2_5": p_over25,
        "btts": p_btts,
        "double_chance": {"1X": p_1x, "12": p_12, "X2": p_x2},
        "correct_score_top3": top3,
    }


# =========================
# BUILD REGISTO FINAL
# =========================
def _pick_max(d: Dict[str, float]) -> Tuple[str, float]:
    if not d:
        return "N/A", 0.0
    k = max(d.keys(), key=lambda x: d[x])
    return k, float(d[k])

def _predicted_score_from_top(top3: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    if not top3:
        return {"home": None, "away": None}
    s = top3[0]["score"]
    try:
        h, a = s.split("-")
        return {"home": int(h), "away": int(a)}
    except Exception:
        return {"home": None, "away": None}


def _build_match_record(fix: Dict[str, Any], odds: Dict[str, Any],
                        probs: Dict[str, Any], scorers: List[Dict[str, Any]]) -> Dict[str, Any]:
    fixture = fix.get("fixture", {})
    league = fix.get("league", {})
    teams = fix.get("teams", {})

    fid = fixture.get("id")
    lg_id = league.get("id")
    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}

    # vencedor
    w_label, w_prob = _pick_max(probs["winner"])
    winner_class = {"home": 0, "draw": 1, "away": 2}.get(w_label, None)

    # DC
    dc_label, dc_prob = _pick_max(probs["double_chance"])
    # overs/btts
    over25 = 1 if probs["over_2_5"] >= 0.5 else 0
    over15 = 1 if probs["over_1_5"] >= 0.5 else 0
    btts    = 1 if probs["btts"]     >= 0.5 else 0

    top3 = probs["correct_score_top3"]
    pred_score = _predicted_score_from_top(top3)

    # odds achatadas úteis na UI anterior
    odds_1x2 = odds.get("1x2") or {}
    home_odd = odds_1x2.get("home")
    draw_odd = odds_1x2.get("draw")
    away_odd = odds_1x2.get("away")

    return {
        # meta
        "fixture_id": fid,
        "match_id": fid,
        "league_id": lg_id,
        "league_name": league.get("name"),
        "country": league.get("country"),
        "date": fixture.get("date"),
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "home_logo": home.get("logo"),
        "away_logo": away.get("logo"),

        # odds consolidadas
        "odds": {
            "1x2": odds_1x2,
            "double_chance": odds.get("double_chance", {}),
            "over_under": odds.get("over_under", {}),
            "btts": odds.get("btts", {}),
        },

        # legado para UI antiga
        "predicted_score": pred_score,
        "confidence": round(float(w_prob), 4),

        # bloco detalhado
        "predictions": {
            "winner": {"class": winner_class, "prob": round(float(w_prob), 4)},
            "double_chance": {"class": dc_label, "prob": round(float(dc_prob), 4)},
            "over_2_5": {"class": over25, "prob": round(float(probs["over_2_5"]), 4)},
            "over_1_5": {"class": over15, "prob": round(float(probs["over_1_5"]), 4)},
            "btts": {"class": btts, "prob": round(float(probs["btts"]), 4)},
            "correct_score": {"best": f"{pred_score['home']}-{pred_score['away']}", "top3": top3},
        },

        # topscorers da liga (opcional, dá jeito na UI)
        "top_scorers": scorers,
    }


# =========================
# PIPELINE PRINCIPAL
# =========================
def fetch_today_matches() -> Dict[str, Any]:
    """
    Busca fixtures (hoje + 2 dias), agrega odds e stats, calcula previsões
    e grava em data/predict/predictions.json (sem BOM).
    Retorna {"status": "ok", "total": N}
    """
    if not API_KEY:
        msg = "❌ API_FOOTBALL_KEY não definida."
        logger.error(msg)
        return {"status": "error", "detail": "API key missing", "total": 0}

    # 1) fixtures de hoje e próximos 2 dias (todas as ligas ou ligas de config/leagues.json)
    target_leagues = set(_load_target_league_ids())
    all_fixtures: List[Dict[str, Any]] = []

    for d in range(DAYS_AHEAD):
        dt = (date.today() + timedelta(days=d)).strftime("%Y-%m-%d")
        fixtures = _fixtures_by_date(dt) or []
        for f in fixtures:
            lg = (f.get("league") or {})
            if not lg.get("id"):
                continue
            if target_leagues and int(lg["id"]) not in target_leagues:
                continue
            all_fixtures.append(f)

    # 2) por liga, pré-carregar top scorers (cache)
    league_ids = sorted(list({(f.get("league") or {}).get("id") for f in all_fixtures if (f.get("league") or {}).get("id")}))
    scorers_by_league = {int(lid): _top_scorers(int(lid)) for lid in league_ids if lid}

    # 3) loop fixtures -> odds, stats equipas, Poisson, registo final
    out: List[Dict[str, Any]] = []

    for f in all_fixtures:
        fixture = f.get("fixture") or {}
        league  = f.get("league") or {}
        teams   = f.get("teams") or {}
        fid = fixture.get("id")
        lg_id = league.get("id")
        if not fid or not lg_id:
            continue

        home_id = (teams.get("home") or {}).get("id")
        away_id = (teams.get("away") or {}).get("id")
        if not home_id or not away_id:
            continue

        # odds
        odds = _odds_by_fixture(int(fid)) or {}

        # stats -> params Poisson
        st_home = _team_stats(int(home_id), int(lg_id)) or {}
        st_away = _team_stats(int(away_id), int(lg_id)) or {}

        lam_h, lam_a = _params_from_stats(st_home, st_away)
        mat = _poisson_matrix(lam_h, lam_a, MAX_GOALS)
        probs = _probs_from_matrix(mat)

        # scorers liga
        top_scorers = scorers_by_league.get(int(lg_id), [])

        out.append(_build_match_record(f, odds, probs, top_scorers))

    # 4) escrever ficheiro (sem BOM) e atualizar Redis
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)

    try:
        config.update_last_update()
    except Exception as e:
        logger.warning(f"⚠️ Falha ao atualizar Redis: {e}")

    logger.info(f"✅ {len(out)} previsões salvas em {PRED_PATH}")
    return {"status": "ok", "total": len(out)}


# Execução direta local
if __name__ == "__main__":
    print(fetch_today_matches())
