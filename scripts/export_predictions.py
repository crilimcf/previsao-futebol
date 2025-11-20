#!/usr/bin/env python3
import os
import json
import sys
from datetime import datetime, timedelta
import urllib.request

API_BASE = os.environ.get("API_BASE_URL", "https://previsao-futebol.onrender.com")
API_TOKEN = os.environ.get("API_TOKEN", "")
HEADERS_JSON = {"Accept":"application/json"}
HEADERS_AUTH = {"Accept":"application/json","Authorization":f"Bearer {API_TOKEN}"} if API_TOKEN else HEADERS_JSON

def http(method, path, headers=None, data=None, timeout=60):
    req = urllib.request.Request(API_BASE + path, method=method, headers=headers or {})
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type","application/json")
    else:
        body = None
    with urllib.request.urlopen(req, body, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "null")

def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def safe_write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def main():
    # 1) força atualização no backend
    try:
        upd = http("POST", "/meta/update", headers=HEADERS_AUTH)
        print("Update:", upd)
    except Exception as e:
        print("WARN: update failed:", e, file=sys.stderr)

    # 2) lê ligas conhecidas
    try:
        leagues = http("GET", "/meta/leagues", headers=HEADERS_JSON)
        league_ids = [str(x["id"]) for x in leagues] if isinstance(leagues, list) else []
    except Exception as e:
        print("WARN: leagues failed:", e, file=sys.stderr)
        league_ids = []

    # 3) agrega previsões para hoje+1+2 (todas as ligas)
    today = datetime.utcnow()
    days = [iso(today + timedelta(days=i)) for i in (0,1,2)]
    all_preds = []
    for d in days:
        # sem filtro (para apanhar ligas novas)
        try:
            ps = http("GET", f"/predictions?date={d}", headers=HEADERS_JSON) or []
            if isinstance(ps, list):
                all_preds.extend(ps)
        except Exception as e:
            print(f"WARN: /predictions?date={d} failed:", e, file=sys.stderr)
        # com filtro por liga (alguns backends só devolvem completo por liga)
        for lid in league_ids:
            try:
                ps = http("GET", f"/predictions?date={d}&league_id={lid}", headers=HEADERS_JSON) or []
                if isinstance(ps, list):
                    all_preds.extend(ps)
            except Exception:
                pass

    # de-dupe por match_id+date
    seen = set()
    dedup = []
    for p in all_preds:
        key = (str(p.get("match_id") or p.get("fixture_id") or ""), p.get("date",""))
        if key not in seen:
            dedup.append(p)
            seen.add(key)

    # 4) stats
    try:
        stats = http("GET", "/stats", headers=HEADERS_JSON) or {}
    except Exception as e:
        print("WARN: stats failed:", e, file=sys.stderr)
        stats = {}

    # 5) escreve ficheiros
    safe_write("data/predict/predictions.json", dedup)
    safe_write("data/stats/prediction_stats.json", stats)

    # 6) (opcional) apende histórico ligeiro
    hist_path = "data/predict/predictions_history.json"
    try:
        if os.path.exists(hist_path):
            with open(hist_path, "r", encoding="utf-8") as f:
                hist = json.load(f)
            if not isinstance(hist, list):
                hist = []
        else:
            hist = []
        hist.append({
            "ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": len(dedup)
        })
        safe_write(hist_path, hist)
    except Exception as e:
        print("WARN: history write failed:", e, file=sys.stderr)

    print(f"Saved {len(dedup)} predictions; stats keys: {list(stats.keys())}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
