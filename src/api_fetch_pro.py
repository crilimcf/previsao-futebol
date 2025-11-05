# src/api_fetch_pro.py
from __future__ import annotations

import os, json, time, logging, random
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from src import config
from src.utils.poisson import score_matrix, probs_from_matrix, top_correct_scores

logger = logging.getLogger("api_pro")

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/")
SEASON = os.getenv("API_FOOTBALL_SEASON", "2025")

HEADERS = {"x-apisports-key": API_KEY}
PRED_PATH = "data/predict/predictions.json"

# ---------------- Cache Redis simples ----------------
def _rget(key: str) -> Optional[Any]:
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

# --------------- HTTP com cache e timeout ------------
def _safe_get(path: str, params: Optional[Dict[str, Any]] = None, timeout: int = 6) -> Any:
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_KEY missing")

    url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    cache_key = f"af:{path}:{json.dumps(params, sort_keys=True)}"
    cached = _rget(cache_key)
    if cached is not None:
        return cached

    t0 = time.time()
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        if r.status_code == 200:
            resp = r.json()
            data = resp.get("response", [])
            _rset(cache_key, data, ex=900)  # 15 min
            logger.info(f"✅ {path} OK in {round(time.time()-t0,2)}s")
            return data
        logger.warning(f"⚠️ {path} -> HTTP {r.status_code}")
        return []
    except Exception as e:
        logger.error(f"❌ GET {path} failed: {e}")
        return []

# --------------------- Odds helpers -------------------
# API-Football /odds?fixture={id}
# Estrutura: response: [{bookmakers:[{bets:[{name, values:[{value, odd}]}]}]}]
PREFERRED_BOOKMAKERS = {"Pinnacle", "bet365", "Bet365", "Marathonbet", "1xBet"}

def _pick_bookmaker(block: Dict[str, Any]) -> Dict[str, Any]:
    bkm_list = block.get("bookmakers") or []
    if not bkm_list:
        return {}
    # preferidos
    for b in bkm_list:
        name = (b.get("name") or "").strip()
        if name in PREFERRED_BOOKMAKERS:
            return b
    return bkm_list[0]  # fallback

def _extract_market(odds_block: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """Devolve o bet dict com name==procura (case-insensitive contains)."""
    if not odds_block:
        return None
    bets = odds_block.get("bets") or []
    name_low = name.lower()
    for b in bets:
        bname = (b.get("name") or "").lower()
        if name_low in bname:
            return b
    return None

def _odds_to_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def parse_fixture_odds(odds_resp: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normaliza:
      odds = {
        "winner": {"home": 1.90, "draw": 3.40, "away": 4.20},
        "over_2_5": {"over": 2.00, "under": 1.75},
        "over_1_5": {"over": 1.40, "under": 2.90},
        "btts": {"yes": 1.95, "no": 1.85}
      }
    """
    if not odds_resp:
        return {}
    # odds_resp é por fixture, por liga — pick bookmaker preferido
    bkm = _pick_bookmaker(odds_resp[0])
    if not bkm:
        # pode vir diretamente no primeiro nível
        bkm = odds_resp[0] if odds_resp and odds_resp[0].get("bets") else {}

    winner, ou25, ou15, btts = {}, {}, {}, {}

    # 1X2
    bet = _extract_market(bkm, "match winner")
    if bet:
        vals = bet.get("values", [])
        for it in vals:
            label = (it.get("value") or "").lower()
            odd = _odds_to_float(it.get("odd"))
            if "home" in label or label == "1":
                winner["home"] = odd
            elif "draw" in label or label == "x":
                winner["draw"] = odd
            elif "away" in label or label == "2":
                winner["away"] = odd

    # Over/Under (procura linha 2.5 e 1.5)
    bet_ou = _extract_market(bkm, "over/under") or _extract_market(bkm, "goals over/under")
    if bet_ou:
        vals = bet_ou.get("values", [])
        for it in vals:
            val = (it.get("value") or "").lower().replace(" ", "")
            odd = _odds_to_float(it.get("odd"))
            if "over2.5" in val:
                ou25["over"] = odd
            elif "under2.5" in val:
                ou25["under"] = odd
            elif "over1.5" in val:
                ou15["over"] = odd
            elif "under1.5" in val:
                ou15["under"] = odd

    # BTTS
    bet_btts = _extract_market(bkm, "both teams to score")
    if bet_btts:
        vals = bet_btts.get("values", [])
        for it in vals:
            label = (it.get("value") or "").lower()
            odd = _odds_to_float(it.get("odd"))
            if label.startswith("yes"):
                btts["yes"] = odd
            elif label.startswith("no"):
                btts["no"] = odd

    odds: Dict[str, Any] = {}
    if winner: odds["winner"] = winner
    if ou25:   odds["over_2_5"] = ou25
    if ou15:   odds["over_1_5"] = ou15
    if btts:   odds["btts"] = btts
    return odds

# ----------------- Probabilities helpers -----------------
def implied_probs_from_1x2(odds: Dict[str, float]) -> Tuple[float, float, float]:
    """Normaliza prob. implícita removendo vigorish."""
    o1, ox, o2 = odds.get("home"), odds.get("draw"), odds.get("away")
    parts = []
    for o in (o1, ox, o2):
        parts.append(0.0 if (o is None or o <= 1.0) else 1.0 / o)
    s = sum(parts) or 1.0
    return (parts[0]/s, parts[1]/s, parts[2]/s)

def pick_double_chance(p_home: float, p_draw: float, p_away: float) -> Tuple[int, float]:
    p_1x = p_home + p_draw   # 0
    p_12 = p_home + p_away   # 1
    p_x2 = p_draw + p_away   # 2
    arr = [(0, p_1x), (1, p_12), (2, p_x2)]
    arr.sort(key=lambda x: x[1], reverse=True)
    return arr[0]

# --------------- Stats → expected goals (λ) --------------
def expected_goals(stats_home: Dict[str, Any], stats_away: Dict[str, Any]) -> Tuple[float, float]:
    """
    Estima λ_home, λ_away a partir de médias 'for' e 'against' (home/away).
    Home adv leve.
    """
    def safe(path: List[str], obj: Dict[str, Any], default: float) -> float:
        cur: Any = obj
        for k in path:
            cur = (cur or {}).get(k)
        try:
            return float(cur)
        except Exception:
            return default

    avg_for_home  = safe(["goals", "for", "average", "home"], stats_home, 1.3)
    avg_for_away  = safe(["goals", "for", "average", "away"], stats_away, 1.1)
    avg_conc_home = safe(["goals", "against", "average", "home"], stats_home, 1.0)
    avg_conc_away = safe(["goals", "against", "average", "away"], stats_away, 1.0)

    lam_home = max(0.05, (avg_for_home + avg_conc_away) / 2.0 * 1.08)  # ligeiro boost casa
    lam_away = max(0.05, (avg_for_away + avg_conc_home) / 2.0 * 0.98)
    return (lam_home, lam_away)

# ----------------- Enriquecimento por fixture ------------
def enrich_fixture_prediction(fix: Dict[str, Any], league_id: int) -> Optional[Dict[str, Any]]:
    fixture = fix.get("fixture", {})
    league  = fix.get("league", {}) or {}
    teams   = fix.get("teams", {}) or {}

    fid  = fixture.get("id")
    if not fid: 
        return None

    home = teams.get("home", {}) or {}
    away = teams.get("away", {}) or {}

    # odds reais
    odds_resp = _safe_get("odds", {"fixture": fid})
    odds = parse_fixture_odds(odds_resp)

    # stats
    if not (home.get("id") and away.get("id") and league_id):
        return None

    st_home = _safe_get("teams/statistics", {"team": home["id"], "league": league_id, "season": SEASON})
    st_away = _safe_get("teams/statistics", {"team": away["id"], "league": league_id, "season": SEASON})

    if isinstance(st_home, list) and st_home:
        st_home = st_home[0]
    if isinstance(st_away, list) and st_away:
        st_away = st_away[0]

    lam_h, lam_a = expected_goals(st_home or {}, st_away or {})
    mat = score_matrix(lam_h, lam_a, max_goals=6)
    p = probs_from_matrix(mat)

    # Winner probs Poisson
    pH_poi, pX_poi, pA_poi = p["home"], p["draw"], p["away"]

    # Winner probs Odds
    if "winner" in odds and odds["winner"]:
        pH_i, pX_i, pA_i = implied_probs_from_1x2(odds["winner"])
    else:
        pH_i, pX_i, pA_i = pH_poi, pX_poi, pA_poi

    # Ensemble simples
    w_poi = 0.45
    pH = w_poi * pH_poi + (1 - w_poi) * pH_i
    pX = w_poi * pX_poi + (1 - w_poi) * pX_i
    pA = w_poi * pA_poi + (1 - w_poi) * pA_i

    # Classes + confianças
    winner_arr = [("home", pH, 0), ("draw", pX, 1), ("away", pA, 2)]
    winner_arr.sort(key=lambda t: t[1], reverse=True)
    winner_class = winner_arr[0][2]
    winner_conf  = winner_arr[0][1]

    # Over/Under
    p_o25_poi = p["over_2_5"]
    p_o15_poi = p["over_1_5"]

    if odds.get("over_2_5", {}).get("over") and odds["over_2_5"].get("under"):
        o_over, o_under = odds["over_2_5"]["over"], odds["over_2_5"]["under"]
        p_over_imp = (1.0 / o_over) if o_over and o_over > 1 else 0.0
        p_under_imp = (1.0 / o_under) if o_under and o_under > 1 else 0.0
        s = (p_over_imp + p_under_imp) or 1.0
        p_over25 = 0.5 * p_o25_poi + 0.5 * (p_over_imp / s)
    else:
        p_over25 = p_o25_poi

    if odds.get("over_1_5", {}).get("over") and odds["over_1_5"].get("under"):
        o_over, o_under = odds["over_1_5"]["over"], odds["over_1_5"]["under"]
        p_over_imp = (1.0 / o_over) if o_over and o_over > 1 else 0.0
        p_under_imp = (1.0 / o_under) if o_under and o_under > 1 else 0.0
        s = (p_over_imp + p_under_imp) or 1.0
        p_over15 = 0.5 * p_o15_poi + 0.5 * (p_over_imp / s)
    else:
        p_over15 = p_o15_poi

    # BTTS
    p_btts_poi = p["btts_yes"]
    if odds.get("btts", {}).get("yes") and odds["btts"].get("no"):
        o_yes, o_no = odds["btts"]["yes"], odds["btts"]["no"]
        p_yes = (1.0 / o_yes) if o_yes and o_yes > 1 else 0.0
        p_no  = (1.0 / o_no) if o_no and o_no > 1 else 0.0
        s = (p_yes + p_no) or 1.0
        p_btts = 0.5 * p_btts_poi + 0.5 * (p_yes / s)
    else:
        p_btts = p_btts_poi

    # DC
    dc_class, dc_prob = pick_double_chance(pH, pX, pA)

    # Correct score (top-3)
    cs_top3 = [{"score": s, "prob": prob} for (s, prob) in top_correct_scores(mat, n=3)]

    # Top scorers da liga (5)
    top_scorers = []
    if league_id:
        try:
            sc = _safe_get("players/topscorers", {"league": league_id, "season": SEASON})
            for s in (sc or [])[:5]:
                player = ((s.get("player") or {}).get("name")) or "-"
                team = (((s.get("statistics") or [{}])[0]).get("team") or {}).get("name")
                goals = (((s.get("statistics") or [{}])[0]).get("goals") or {}).get("total", 0)
                top_scorers.append({"player": player, "team": team, "goals": goals})
        except Exception:
            pass

    # objeto final
    return {
        "match_id": fid,
        "league_id": league.get("id") or league_id,
        "league": league.get("name") or "",
        "country": league.get("country"),
        "date": fixture.get("date"),
        "home_team": home.get("name"),
        "away_team": away.get("name"),
        "home_logo": home.get("logo"),
        "away_logo": away.get("logo"),
        "odds": odds or None,
        "predictions": {
            "winner": {"class": int(winner_class), "confidence": float(pH if winner_class == 0 else pX if winner_class == 1 else pA)},
            "over_2_5": {"class": int(p_over25 >= 0.5), "confidence": float(p_over25)},
            "over_1_5": {"class": int(p_over15 >= 0.5), "confidence": float(p_over15)},
            "double_chance": {"class": int(dc_class), "confidence": float(dc_prob)},
            "btts": {"class": int(p_btts >= 0.5), "confidence": float(p_btts)},
        },
        "correct_score_top3": cs_top3,
        "top_scorers": top_scorers,
    }

# ----------------- Builder principal ---------------------
def build_for_date(target_date: str, only_league: Optional[int] = None) -> List[Dict[str, Any]]:
    params = {"date": target_date, "season": SEASON}
    if only_league:
        params["league"] = only_league

    fixtures = _safe_get("fixtures", params) or []
    out: List[Dict[str, Any]] = []

    for f in fixtures:
        lg_id = only_league or ((f.get("league") or {}).get("id"))
        try:
            enriched = enrich_fixture_prediction(f, league_id=int(lg_id) if lg_id else 0)
            if enriched:
                out.append(enriched)
        except Exception as e:
            logger.warning(f"Fixture skip: {e}")

    # ordenar por confiança do winner
    out.sort(key=lambda x: (x.get("predictions", {}).get("winner", {}).get("confidence") or 0.0), reverse=True)
    return out

def build_predictions_for_range(days: int = 1, start: Optional[date] = None, only_league: Optional[int] = None) -> Dict[str, Any]:
    """
    days=1 -> apenas hoje. days=3 -> hoje+2 dias.
    """
    if start is None:
        start = date.today()

    all_rows: List[Dict[str, Any]] = []
    for d in range(days):
        dt = (start + timedelta(days=d)).strftime("%Y-%m-%d")
        rows = build_for_date(dt, only_league=only_league)
        all_rows.extend(rows)

    # persistir
    os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
    with open(PRED_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    # meta: atualizar last_update
    try:
        config.update_last_update()
    except Exception:
        pass

    return {"status": "ok", "total": len(all_rows)}
