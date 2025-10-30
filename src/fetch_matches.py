import requests
import json
import os
from datetime import date
from src import config

API_KEY = os.getenv("SOCCERDATA_API_KEY")
BASE_URL = os.getenv("SOCCERDATA_BASE_URL", "https://api.soccerdataapi.com")

PRED_PATH = "data/predict/predictions.json"


def fetch_today_matches():
    """Obtém os jogos de hoje da SoccerDataAPI"""
    today = date.today().strftime("%Y-%m-%d")
    url = f"{BASE_URL}/matches?date={today}"

    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        matches = []
        for m in data.get("data", []):
            matches.append({
                "match_id": m.get("id"),
                "league": m.get("league", {}).get("name"),
                "home_team": m.get("home_team", {}).get("name"),
                "away_team": m.get("away_team", {}).get("name"),
                "date": m.get("date"),
                "time": m.get("time"),
                "odds": m.get("odds", {}),
            })

        os.makedirs(os.path.dirname(PRED_PATH), exist_ok=True)
        with open(PRED_PATH, "w", encoding="utf-8") as f:
            json.dump(matches, f, ensure_ascii=False, indent=2)

        print(f"✅ {len(matches)} jogos guardados em {PRED_PATH}")

        # Atualiza o Redis
        config.update_last_update()
        return {"status": "ok", "total": len(matches)}

    except Exception as e:
        print(f"⚠️ Erro ao buscar jogos: {e}")
        return {"status": "error", "detail": str(e)}
