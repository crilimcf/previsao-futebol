# src/api_fetch.py
import os
import json
import time
import math
import random
import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple

import requests
from src import config

logger = logging.getLogger("api_fetch")

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")
HEADERS = {"x-apisports-key": API_KEY}
TIMEOUT = 6  # segundos

PRED_PATH = "data/predict/predictions.json"
os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)

# --------- Cache em Redis (opcional) ---------
def rget(key: str) -> Optional[Any]:
    try:
        if config.redis_client:
            raw = config.redis_client.get(key)
            return json.loads(raw) if raw else None
    except Exception:
        return None
    return None

def rset(key: str, val: Any, ex: int = 3600):
    try:
        if config.redis_client:
            config.redis_client.set(key, json.dumps(val), ex=ex)
    except Exception:
        pass

# --------- HTTP helper com cache ---------
def api_get(path: str, params: Dict[str, Any]) -> Any:
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_KEY não definida.")
    url = f"{BASE_URL}{path}"
    cache_key = f"af:{path}:{json.dumps(params, sort_keys=True)}"
    cached = rget(cache_key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json().get("response", [])
        rset(cache_key, data, ex=1800)
        return data
    except Exception as e:
        logger.warning(f"API error {path}: {e}")
        return []

# --------- Odds parsing ---------
def get_odds_for_fixture(fixture_id: int) -> Dict[str, Any]:
    """Extrai odds de mercados chave: 1X2, Over/Under 2.5/1.5, BTTS."""
    odds_resp = api_get("odds", {"fixture": fixture_id, "season": SEASON})
    result = {
        "1x2": {"home": None, "draw": None, "away": None},
        "ou_25": {"over": None, "under": None},
        "ou_15": {"over": None, "under": None},
        "btts": {"yes": None, "no": None},
    }
    try:
        # odds_resp: [{bookmakers:[{bets:[{name: 'Match Winner', values:[{value:'Home',odd:'1.70'},...]}, ...]}]}]
        for item in odds_resp:
            for bm in item.get("bookmakers", []):
                for bet in bm.get("bets", []):
                    name = (bet.get("name") or "").lower()
                    vals = bet.get("values", [])
                    # Match Winner
                    if "match winner" in name or name == "1x2":
                        # Home / Draw / Away
                        tmp = {"home": None, "draw": None, "away": None}
                        for v in vals:
                            label = (v.get("value") or "").lower()
                            odd = v.get("odd")
                            if not odd:
                                continue
                            try:
                                odd = float(odd)
                            except:
                                continue
                            if label in ("home", "1"):
                                tmp["home"] = odd
                            elif label in ("draw", "x"):
                                tmp["draw"] = odd
                            elif label in ("away", "2"):
                                tmp["away"] = odd
                        # escolhe as melhores/menores odds observadas
                        for k in tmp:
                            if tmp[k] is not None:
                                if result["1x2"][k] is None or tmp[k] < result["1x2"][k]:
                                    result["1x2"][k] = tmp[k]
                    # Over/Under 2.5
                    if "over/under" in name and any("2.5" in (v.get("value") or "") for v in vals):
                        tmp = {"over": None, "under": None}
                        for v in vals:
                            label = (v.get("value") or "").lower()
                            odd = v.get("odd")
                            if not odd:
                                continue
                            try:
                                odd = float(odd)
                            except:
                                continue
                            if "over 2.5" in label:
                                tmp["over"] = odd
                            elif "under 2.5" in label:
                                tmp["under"] = odd
                        for k in tmp:
                            if tmp[k] is not None:
                                if result["ou_25"][k] is None or tmp[k] < result["ou_25"][k]:
                                    result["ou_25"][k] = tmp[k]
                    # Over/Under 1.5
                    if "over/under" in name and any("1.5" in (v.get("value") or "") for v in vals):
                        tmp = {"over": None, "under": None}
                        for v in vals:
                            label = (v.get("value") or "").lower()
                            odd = v.get("odd")
                            if not odd:
                                continue
                            try:
                                odd = float(odd)
                            except:
                                continue
                            if "over 1.5" in label:
                                tmp["over"] = odd
                            elif "under 1.5" in label:
                                tmp["under"] = odd
                        for k in tmp:
                            if tmp[k] is not None:
                                if result["ou_15"][k] is None or tmp[k] < result["ou_15"][k]:
                                    result["ou_15"][k] = tmp[k]
                    # BTTS
                    if "both teams to score" in name or "btts" in name:
                        tmp = {"yes": None, "no": None}
                        for v in vals:
                            label = (v.get("value") or "").lower()
                            odd = v.get("odd")
                            if not odd:
                                continue
                            try:
                                odd = float(odd)
                            except:
                                continue
                            if "yes" in label:
                                tmp["yes"] = odd
                            elif "no" in label:
                                tmp["no"] = odd
                        for k in tmp:
                            if tmp[k] is not None:
                                if result["btts"][k] is None or tmp[k] < result["btts"][k]:
                                    result["btts"][k] = tmp[k]
    except Exception as e:
        logger.debug(f"odds parse fail {fixture_id}: {e}")
    return result

# --------- Team stats ---------
def team_stats(team_id: int, league_id: int) -> Dict[str, Any]:
    data = api_get("teams/statistics", {"team": team_id, "league": league_id, "season": SEASON})
    # a API devolve 1 objeto, mas pelo wrapper acima pode vir array; normaliza
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    return {}

# --------- Top scorers ---------
def get_top_scorers(league_id: int) -> List[Dict[str, Any]]:
    arr = api_get("players/topscorers", {"league": league_id, "season": SEASON})
    out: List[Dict[str, Any]] = []
    for s in arr[:5]:
        try:
            player = s.get("player", {}).get("name")
            stats = (s.get("statistics") or [{}])[0]
            team = stats.get("team", {}).get("name")
            goals = (stats.get("goals") or {}).get("total", 0)
            out.append({"player": player, "team": team, "goals": goals})
        except Exception:
            continue
    return out

# --------- Poisson helpers ---------
def poisson_pmf(k: int, lam: float) -> float:
    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except OverflowError:
        return 0.0

def score_matrix_probs(lh: float, la: float, max_goals: int = 7) -> List[Tuple[str, float]]:
    grid: List[Tuple[str, float]] = []
    for i in range(0, max_goals + 1):
        pi = poisson_pmf(i, lh)
        for j in range(0, max_goals + 1):
            pj = poisson_pmf(j, la)
            grid.append((f"{i}-{j}", pi * pj))
    grid.sort(key=lambda x: x[1], reverse=True)
    return grid

def derive_lambdas(home_stats: Dict[str, Any], away_stats: Dict[str, Any]) -> Tuple[float, float]:
    """
    Estima λ_home e λ_away a partir das médias Home/Away (for/against) e um HFA.
    É um modelo parsimonioso mas prático em produção (sem precisar solver numérico).
    """
    # Defaults de segurança
    hgf = float(((home_stats.get("goals") or {}).get("for") or {}).get("average", {}).get("home") or 1.3)
    hga = float(((home_stats.get("goals") or {}).get("against") or {}).get("average", {}).get("home") or 1.0)
    agf = float(((away_stats.get("goals") or {}).get("for") or {}).get("average", {}).get("away") or 1.2)
    aga = float(((away_stats.get("goals") or {}).get("against") or {}).get("average", {}).get("away") or 1.1)

    # heurística: usar a raiz do produto GF x GA cruzados (clássico de ratings simples)
    base_h = math.sqrt(max(0.05, hgf) * max(0.05, aga))
    base_a = math.sqrt(max(0.05, agf) * max(0.05, hga))

    # Home Field Advantage
    HFA = 1.10
    λh = max(0.1, base_h * HFA)
    λa = max(0.1, base_a)
    return λh, λa

def probs_from_matrix(grid: List[Tuple[str, float]]) -> Dict[str, float]:
    p_home = sum(p for s, p in grid if int(s.split("-")[0]) > int(s.split("-")[1]))
    p_draw = sum(p for s, p in grid if int(s.split("-")[0]) == int(s.split("-")[1]))
    p_away = 1.0 - p_home - p_draw
    p_over25 = 1.0 - sum(p for s, p in grid if (int(s.split("-")[0]) + int(s.split("-")[1])) <= 2)
    p_over15 = 1.0 - sum(p for s, p in grid if (int(s.split("-")[0]) + int(s.split("-")[1])) <= 1)
    # BTTS = 1 - P(home=0 or away=0)
    p_home0 = sum(p for s, p in grid if int(s.split("-")[0]) == 0)
    p_away0 = sum(p for s, p in grid if int(s.split("-")[1]) == 0)
    p_btts = 1.0 - (p_home0 + p_away0 - sum(p for s, p in grid if s == "0-0"))
    return {
        "ph": p_home, "pd": p_draw, "pa": p_away,
        "o25": p_over25, "o15": p_over15, "btts_yes": p_btts
    }

def double_chance_from_1x2(ph: float, pd: float, pa: float) -> Tuple[int, float, Dict[str, float]]:
    """Retorna (classe, confiança, detalhado) para DC: 0=1X, 1=12, 2=X2"""
    dc_1x = ph + pd
    dc_12 = ph + pa
    dc_x2 = pd + pa
    arr = [dc_1x, dc_12, dc_x2]
    idx = int(max(range(3), key=lambda i: arr[i]))
    return idx, arr[idx], {"1X": dc_1x, "12": dc_12, "X2": dc_x2}

# --------- Fixtures (3 dias: hoje, amanhã, depois) ---------
def get_fixtures_3days() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for day_offset in range(3):
        match_date = (date.today() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        fixtures = api_get("fixtures", {"season": SEASON, "date": match_date})
        for f in fixtures:
            try:
                out.append(f)
            except Exception:
                continue
    return out

# --------- Pipeline principal ---------
def fetch_today_matches() -> Dict[str, Any]:
    """
    Puxa fixtures reais, odds, stats, calcula previsões e guarda predictions.json
    """
    fixtures = get_fixtures_3days()
    results: List[Dict[str, Any]] = []
    total = 0

    for f in fixtures:
        try:
            fixture = f.get("fixture", {})
            league = f.get("league", {})
            teams = f.get("teams", {})

            fixture_id = fixture.get("id")
            league_id = league.get("id")
            home = teams.get("home", {}) or {}
            away = teams.get("away", {}) or {}

            home_id = home.get("id")
            away_id = away.get("id")
            if not all([fixture_id, league_id, home_id, away_id]):
                continue

            # Odds & Stats
            odds = get_odds_for_fixture(fixture_id)
            st_home = team_stats(home_id, league_id)
            st_away = team_stats(away_id, league_id)

            # Poisson lambdas
            λh, λa = derive_lambdas(st_home, st_away)
            matrix = score_matrix_probs(λh, λa, max_goals=7)
            probs = probs_from_matrix(matrix)

            # Winner
            winner_classes = [probs["ph"], probs["pd"], probs["pa"]]
            winner_cls = int(max(range(3), key=lambda i: winner_classes[i]))
            winner_conf = float(winner_classes[winner_cls])

            # Over/BTTS
            over25_conf = float(probs["o25"])
            over15_conf = float(probs["o15"])
            btts_conf = float(probs["btts_yes"])

            # Double Chance
            dc_cls, dc_conf, dc_map = double_chance_from_1x2(probs["ph"], probs["pd"], probs["pa"])

            # Top-3 correct score
            top3_cs = [{"score": s, "prob": round(p, 4)} for s, p in matrix[:3]]

            # Top scorers (liga)
            scorers = get_top_scorers(int(league_id))

            # Output compatível com o teu UI “novo”
            result = {
                "match_id": fixture_id,
                "league_id": league_id,
                "league": league.get("name"),
                "country": league.get("country"),
                "date": fixture.get("date"),
                "home_team": home.get("name"),
                "away_team": away.get("name"),
                "home_logo": home.get("logo"),
                "away_logo": away.get("logo"),
                "odds": {
                    "winner": odds.get("1x2"),
                    "over_2_5": odds.get("ou_25"),
                    "over_1_5": odds.get("ou_15"),
                    "btts": odds.get("btts"),
                },
                "predictions": {
                    "winner": {"class": winner_cls, "confidence": round(winner_conf, 4)},
                    "over_2_5": {"class": 1 if over25_conf >= 0.5 else 0, "confidence": round(over25_conf, 4)},
                    "over_1_5": {"class": 1 if over15_conf >= 0.5 else 0, "confidence": round(over15_conf, 4)},
                    "double_chance": {"class": dc_cls, "confidence": round(float(dc_conf), 4)},
                    "btts": {"class": 1 if btts_conf >= 0.5 else 0, "confidence": round(btts_conf, 4)},
                },
                "correct_score_top3": top3_cs,
                "top_scorers": scorers,
            }

            results.append(result)
            total += 1

        except Exception as e:
            logger.debug(f"fixture parse fail: {e}")
            continue

    # ordena pelo confidence do Winner
    results_sorted = sorted(results, key=lambda x: x["predictions"]["winner"]["confidence"], reverse=True)

    # grava sem BOM
    with open(PRED_PATH, "w", encoding="utf-8") as f:
        json.dump(results_sorted, f, ensure_ascii=False, indent=2)

    # update meta (TTL 7 dias em config)
    try:
        config.update_last_update()
    except Exception:
        pass

    logger.info(f"✅ {total} previsões guardadas em {PRED_PATH}")
    return {"status": "ok", "total": total}

# compat: alguns sítios chamam main()
def main():
    return fetch_today_matches()
