# src/predict.py
import os
import sys
import json
import joblib
import pandas as pd
import logging
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.features import (
    add_rank_diff_feature,
    add_h2h_feature,
    add_odds_features,
    add_recent_form_to_upcoming,
)

# Preferir upcoming; cair para today se necessário
try:
    from src.api_fetch import fetch_upcoming_matches
except Exception:
    fetch_upcoming_matches = None  # type: ignore
try:
    from src.api_fetch import fetch_today_matches
except Exception:
    fetch_today_matches = None  # type: ignore

logger = logging.getLogger("predict")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


# ---------------------- normalização ----------------------
def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def _normalize_game(g: Dict[str, Any]) -> Dict[str, Any]:
    league_id = g.get("league_id") or g.get("league", {}).get("id") or g.get("LeagueID")
    home_name = (
        g.get("home_name")
        or g.get("home_team")
        or g.get("home")
        or g.get("teams", {}).get("home", {}).get("name")
    )
    away_name = (
        g.get("away_name")
        or g.get("away_team")
        or g.get("away")
        or g.get("teams", {}).get("away", {}).get("name")
    )

    date_val = g.get("date")
    time_val = g.get("time")
    if date_val and "T" in str(date_val) and not time_val:
        try:
            date_part, time_part = str(date_val).split("T", 1)
            time_val = time_part.split("+")[0].split("Z")[0][:5]
            date_val = date_part
        except Exception:
            pass

    odds = g.get("odds") or {}
    if not isinstance(odds, dict):
        odds = {}
    home_odds = odds.get("home")
    draw_odds = odds.get("draw")
    away_odds = odds.get("away")
    if home_odds is None and "home_win" in g:
        home_odds = g.get("home_win")
    if draw_odds is None and "x" in g:
        draw_odds = g.get("x")
    if away_odds is None and "away_win" in g:
        away_odds = g.get("away_win")

    match_id = (
        g.get("match_id")
        or g.get("fixture_id")
        or g.get("fixture", {}).get("id")
        or g.get("id")
    )

    return {
        "league_id": league_id,
        "home_name": home_name,
        "away_name": away_name,
        "date": date_val,
        "time": time_val,
        "odds": {
            "home": _safe_float(home_odds),
            "draw": _safe_float(draw_odds),
            "away": _safe_float(away_odds),
        },
        "match_id": match_id,
        "league_logo": g.get("league_logo") or g.get("league", {}).get("logo"),
        "home_logo": g.get("home_logo") or g.get("teams", {}).get("home", {}).get("logo"),
        "away_logo": g.get("away_logo") or g.get("teams", {}).get("away", {}).get("logo"),
    }

def _normalize_games(raw: Any) -> List[Dict[str, Any]]:
    games: List[Dict[str, Any]] = []
    if isinstance(raw, dict):
        for key in ("matches", "games", "response", "data"):
            arr = raw.get(key)
            if isinstance(arr, list):
                for g in arr:
                    games.append(_normalize_game(g))
                break
    elif isinstance(raw, list):
        for g in raw:
            games.append(_normalize_game(g))
    return [g for g in games if g.get("home_name") and g.get("away_name")]


# ---------------------- features ----------------------
def prepare_features(
    games: List[Dict[str, Any]],
    feature_columns: List[str],
    scaler=None,
    encoders: Optional[Dict[str, Any]] = None,
):
    df = pd.DataFrame(games)

    # leagues.json tolerante a BOM
    id_to_name = {}
    try:
        with open("config/leagues.json", encoding="utf-8-sig") as f:
            leagues = json.load(f)
        id_to_name = {str(lg["id"]): lg["name"] for lg in leagues}
    except Exception:
        logger.warning("⚠️ Não foi possível ler config/leagues.json.")
        id_to_name = {}

    df["League"] = df["league_id"].astype(str).map(id_to_name).fillna(df["league_id"].astype(str))

    df = add_rank_diff_feature(df)
    df = add_h2h_feature(df)
    df = add_odds_features(df)

    for col, key in zip(["home_win", "draw", "away_win"], ["home", "draw", "away"]):
        df[col] = df["odds"].apply(lambda x: x.get(key) if isinstance(x, dict) else None)

    if encoders and "le_league" in encoders and encoders["le_league"] is not None:
        le = encoders["le_league"]
        known = set(le.classes_)
        placeholder = next(iter(known)) if len(known) else None
        safe_leagues = df["League"].where(df["League"].isin(known), placeholder)
        try:
            df["League_Encoded"] = le.transform(safe_leagues)
        except Exception as e:
            logger.warning(f"⚠️ Falhou encoder de ligas: {e}")
            df["League_Encoded"] = 0
    else:
        logger.warning("⚠️ Encoder de ligas ausente — League_Encoded=0")
        df["League_Encoded"] = 0

    try:
        with open("data/raw/matches_raw.json", encoding="utf-8-sig") as f:
            historical = pd.DataFrame(json.load(f))
    except Exception:
        logger.warning("⚠️ data/raw/matches_raw.json não encontrado.")
        historical = pd.DataFrame(columns=["League", "Team1Goals", "Team2Goals"])

    if "League" not in historical.columns and "league" in historical.columns:
        historical["League"] = historical["league"]
    if "Team1Goals" not in historical.columns and "team1_goals" in historical.columns:
        historical["Team1Goals"] = historical["team1_goals"]
    if "Team2Goals" not in historical.columns and "team2_goals" in historical.columns:
        historical["Team2Goals"] = historical["team2_goals"]

    df = add_recent_form_to_upcoming(df, historical, n_games=5)

    for i, game in enumerate(games):
        for odd_col in ["home_win", "draw", "away_win"]:
            if odd_col in df.columns:
                game[odd_col] = df.loc[i, odd_col]

    missing = [c for c in feature_columns if c not in df.columns]
    for c in missing:
        df[c] = 0

    X = df[feature_columns].copy()
    if scaler:
        try:
            X = pd.DataFrame(scaler.transform(X), columns=feature_columns)
        except Exception as e:
            logger.warning(f"⚠️ scaler.transform falhou: {e}")
    return X


# ---------------------- fallback simples ----------------------
def _predict_fallback_winner(g: Dict[str, Any]) -> (Optional[int], float):
    odds = g.get("odds") or {}
    try:
        oh, od, oa = odds.get("home"), odds.get("draw"), odds.get("away")
        candidates = [("home", oh, 0), ("draw", od, 1), ("away", oa, 2)]
        candidates = [c for c in candidates if c[1] is not None]
        if not candidates:
            return None, 0.0
        best = min(candidates, key=lambda t: t[1])
        others = [x for x in candidates if x[2] != best[2]]
        conf_gap = (min([o[1] for o in others]) - best[1]) if others else 0.0
        conf = max(0.55, min(0.9, 0.65 + conf_gap * 0.05))
        return best[2], float(conf)
    except Exception:
        return None, 0.0


# ---------------------- MAIN ----------------------
def main():
    targets = ["Winner", "Over_2_5", "Over_1_5", "Double_Chance", "BTTS"]
    bundles = {}
    for t in targets:
        path = f"models/bundle_{t}.pkl"
        try:
            bundles[t] = joblib.load(path)
            logger.info(f"✅ Bundle carregado: {path}")
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível carregar {path}: {e}")

    raw_games = []
    if fetch_upcoming_matches:
        logger.info("🔎 A obter jogos via fetch_upcoming_matches()")
        try:
            raw_games = fetch_upcoming_matches()
        except Exception as e:
            logger.error(f"❌ Erro no fetch_upcoming_matches: {e}")
    elif fetch_today_matches:
        logger.info("🔎 A obter jogos via fetch_today_matches() (fallback)")
        try:
            raw_games = fetch_today_matches()
        except Exception as e:
            logger.error(f"❌ Erro no fetch_today_matches: {e}")

    games = _normalize_games(raw_games)
    if not games:
        logger.warning("[WARNING] Sem jogos por prever.")
        return

    for name, bundle in bundles.items():
        try:
            model = bundle["model"]
            feature_columns = bundle.get("feature_columns", [])
            scaler = bundle.get("scaler", None)
            le_league = bundle.get("le_league", None)

            X = prepare_features(
                games, feature_columns, scaler=scaler, encoders={"le_league": le_league}
            )

            preds = None
            confs = None
            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(X)
                preds = model.classes_[probs.argmax(axis=1)]
                confs = probs.max(axis=1)
            else:
                preds = model.predict(X)
                confs = [0.65] * len(games)

        except Exception as e:
            logger.error(f"[ERROR] Erro a prever {name}: {e}")
            preds = [None] * len(games)
            confs = [0.0] * len(games)

        for i, g in enumerate(games):
            g[f"prediction_{name}"] = (
                int(preds[i]) if preds is not None and preds[i] is not None else None
            )
            g[f"confidence_{name}"] = float(confs[i]) if confs is not None else 0.0

    if "Winner" not in bundles:
        for g in games:
            cls, conf = _predict_fallback_winner(g)
            g["prediction_Winner"] = cls
            g["confidence_Winner"] = conf

    # map id->nome (para UI)
    try:
        with open("config/leagues.json", encoding="utf-8-sig") as f:
            leagues = json.load(f)
        id_to_name = {str(lg["id"]): lg["name"] for lg in leagues}
    except Exception:
        id_to_name = {}

    results: List[Dict[str, Any]] = []
    for g in games:
        winner_cls = g.get("prediction_Winner")
        # palpite simples de resultado para compatibilidade com o teu UI
        if winner_cls == 0:
            ps = {"home": 1, "away": 0}
        elif winner_cls == 1:
            ps = {"home": 1, "away": 1}
        elif winner_cls == 2:
            ps = {"home": 0, "away": 1}
        else:
            ps = {"home": None, "away": None}

        results.append({
            "match_id": g.get("match_id"),
            "league_id": g.get("league_id"),
            "league": id_to_name.get(str(g.get("league_id")), str(g.get("league_id"))),
            "date": g.get("date"),
            "time": g.get("time"),
            "home_team": g.get("home_name"),
            "away_team": g.get("away_name"),
            "home_logo": g.get("home_logo"),
            "away_logo": g.get("away_logo"),
            "predicted_score": ps,                     # <— legado para o teu UI
            "confidence": float(g.get("confidence_Winner", 0.0)),  # <— legado
            "predictions": {  # detalhado (se precisares no futuro)
                "winner":   {"class": winner_cls, "confidence": float(g.get("confidence_Winner", 0.0))},
                "over_2_5": {"class": g.get("prediction_Over_2_5"), "confidence": float(g.get("confidence_Over_2_5", 0.0))},
                "over_1_5": {"class": g.get("prediction_Over_1_5"), "confidence": float(g.get("confidence_Over_1_5", 0.0))},
                "double_chance": {"class": g.get("prediction_Double_Chance"), "confidence": float(g.get("confidence_Double_Chance", 0.0))},
                "btts":     {"class": g.get("prediction_BTTS"), "confidence": float(g.get("confidence_BTTS", 0.0))},
            },
        })

    results_sorted = sorted(results, key=lambda x: x["confidence"] or 0.0, reverse=True)
    top_results = results_sorted[:7]

    out_dir = os.path.join("data", "predict")
    os.makedirs(out_dir, exist_ok=True)

    # >>> sem BOM <<<
    predictions_path = os.path.join(out_dir, "predictions.json")
    with open(predictions_path, "w", encoding="utf-8") as f:
        json.dump(top_results, f, ensure_ascii=False, indent=2)
    logger.info(f"[INFO] Predictions saved to {predictions_path} (top 7)")

    history_path = os.path.join(out_dir, "predictions_history.json")
    try:
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8-sig") as f:
                existing = json.load(f)
        else:
            existing = []
        existing.extend(top_results)
        with open(history_path, "w", encoding="utf-8") as f:  # <<< sem BOM
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info(f"[INFO] Appended top 7 predictions to {history_path}")
    except Exception as e:
        logger.error(f"[ERROR] Error saving predictions history: {e}")


if __name__ == "__main__":
    main()
