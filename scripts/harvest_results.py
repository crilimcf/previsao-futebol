#!/usr/bin/env python3
# scripts/harvest_results.py
import os
import json
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests

# ========= Config =========
API_KEY  = os.getenv("API_FOOTBALL_KEY", "").strip()
BASE_URL = os.getenv("API_FOOTBALL_BASE", "https://v3.football.api-sports.io/").strip()
SEASON   = os.getenv("API_FOOTBALL_SEASON", "2025").strip()

# Normalizar BASE_URL (evita 'Invalid URL "fixtures"')
if not BASE_URL:
    BASE_URL = "https://v3.football.api-sports.io/"
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL.lstrip("/")
BASE_URL = BASE_URL.rstrip("/") + "/"

HEADERS = {
    "Accept": "application/json",
    **({"x-apisports-key": API_KEY} if API_KEY else {}),
}
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))
MAX_GOALS = 6
RETRIES = 5

# ========= Helpers =========
def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def _url(path_or_url: str) -> str:
    """Permite passar 'fixtures' ou um URL completo."""
    return path_or_url if path_or_url.startswith("http") else urljoin(BASE_URL, path_or_url.lstrip("/"))

def _json_or_text(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return resp.text

def get(path_or_url: str, params: dict | None = None):
    """GET com retry exponencial e suporte básico a 429."""
    url = _url(path_or_url)
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params or {}, timeout=TIMEOUT)
            # 429: respeitar se houver cabeçalhos
            if r.status_code == 429:
                reset = r.headers.get("x-ratelimit-reset")
                wait_s = int(reset) if (reset and reset.isdigit()) else attempt * 3
                time.sleep(wait_s)
                continue
            r.raise_for_status()
            body = _json_or_text(r)
            if isinstance(body, dict) and "response" in body:
                return body["response"]
            return body
        except Exception as e:
            last_err = e
            time.sleep(attempt * 2)  # backoff
    raise SystemExit(f"GET failed {url}: {last_err}")

def poisson_pmf(lmbda: float, k: int) -> float:
    try:
        return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)
    except Exception:
        return 0.0

def poisson_matrix(lh: float, la: float, max_goals: int = MAX_GOALS):
    mat = []
    for i in range(max_goals + 1):
        row = []
        ph = poisson_pmf(lh, i)
        for j in range(max_goals + 1):
            pa = poisson_pmf(la, j)
            row.append(ph * pa)
        mat.append(row)
    s = sum(sum(r) for r in mat)
    if s > 0:
        for i in range(len(mat)):
            for j in range(len(mat[0])):
                mat[i][j] /= s
    return mat

def _as_float(x, default: float) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        # API-Football devolve strings tipo "1.42"
        return float(str(x).replace(",", "."))
    except Exception:
        return default

def stats_params(stats_home: dict, stats_away: dict):
    # goals.for.average.home  / goals.against.average.away (etc.)
    gh_home = _as_float((((stats_home.get("goals") or {}).get("for") or {}).get("average") or {}).get("home"), 1.2)
    ga_home = _as_float((((stats_home.get("goals") or {}).get("against") or {}).get("average") or {}).get("home"), 1.0)
    gh_away = _as_float((((stats_away.get("goals") or {}).get("for") or {}).get("average") or {}).get("away"), 1.1)
    ga_away = _as_float((((stats_away.get("goals") or {}).get("against") or {}).get("average") or {}).get("away"), 1.0)

    # mistura simples e limitada a [0.2, 3.5]
    lam_h = max(0.2, min(3.5, 0.6 * gh_home + 0.4 * ga_away))
    lam_a = max(0.2, min(3.5, 0.6 * gh_away + 0.4 * ga_home))
    return lam_h, lam_a

def probs_from_matrix(mat):
    n = len(mat)
    p_home = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(mat[i][i] for i in range(n))
    p_away = max(0.0, 1.0 - p_home - p_draw)

    def _sum(cond): 
        return sum(mat[i][j] for i in range(n) for j in range(n) if cond(i, j))

    p_over25 = _sum(lambda i, j: i + j >= 3)
    p_over15 = _sum(lambda i, j: i + j >= 2)
    p_btts   = _sum(lambda i, j: i >= 1 and j >= 1)
    p_1x = p_home + p_draw
    p_12 = p_home + p_away
    p_x2 = p_draw + p_away
    return {
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "p_over25": p_over25, "p_over15": p_over15, "p_btts": p_btts,
        "p_dc_1x": p_1x, "p_dc_12": p_12, "p_dc_x2": p_x2,
    }

def team_stats(team_id: int, league_id: int):
    d = get("teams/statistics", {"team": team_id, "league": league_id, "season": SEASON})
    if isinstance(d, list) and d:
        d = d[0]
    return d or {}

# ========= Main =========
def main():
    if not API_KEY:
        print("No API_FOOTBALL_KEY set; skipping.")
        return 0

    # Ontem (UTC) para resultados fechados
    y = datetime.now(timezone.utc) - timedelta(days=1)
    y_s = _iso(y)

    fixtures = get("fixtures", {"date": y_s, "season": SEASON}) or []
    # manter apenas jogos terminados
    fixtures = [
        f for f in fixtures
        if ((f.get("fixture") or {}).get("status") or {}).get("short") in {"FT", "AET", "PEN"}
    ]

    # Preparar pasta e dedupe
    hist_dir  = "data/training"
    hist_path = os.path.join(hist_dir, "history.jsonl")
    os.makedirs(hist_dir, exist_ok=True)

    seen: set[int] = set()
    if os.path.exists(hist_path):
        with open(hist_path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    j = json.loads(line)
                    fid = j.get("fixture_id")
                    if fid is not None:
                        seen.add(fid)
                except Exception:
                    pass

    out_lines: list[str] = []
    for f in fixtures:
        fx = f.get("fixture") or {}
        lg = f.get("league") or {}
        tm = f.get("teams") or {}
        goals = f.get("goals") or {}

        fid = fx.get("id")
        if not fid or fid in seen:
            continue

        lg_id   = lg.get("id")
        home_id = (tm.get("home") or {}).get("id")
        away_id = (tm.get("away") or {}).get("id")
        hg      = goals.get("home")
        ag      = goals.get("away")

        if None in (lg_id, home_id, away_id, hg, ag):
            continue

        # Stats -> Poisson
        try:
            st_h = team_stats(int(home_id), int(lg_id))
            st_a = team_stats(int(away_id), int(lg_id))
        except SystemExit as e:
            # se rebentar numa equipa, salta
            continue

        lam_h, lam_a = stats_params(st_h, st_a)
        mat   = poisson_matrix(lam_h, lam_a)
        probs = probs_from_matrix(mat)

        rec = {
            "fixture_id": fid,
            "date": (fx.get("date") or "")[:10],
            "league_id": lg_id,
            "home_id": home_id,
            "away_id": away_id,
            "home_goals": hg,
            "away_goals": ag,
            # probs base
            **probs,
            # labels
            "y_home": 1 if hg > ag else 0,
            "y_draw": 1 if hg == ag else 0,
            "y_away": 1 if ag > hg else 0,
            "y_over25": 1 if (hg + ag) >= 3 else 0,
            "y_btts": 1 if (hg >= 1 and ag >= 1) else 0,
        }
        out_lines.append(json.dumps(rec, ensure_ascii=False))

    if out_lines:
        with open(hist_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(out_lines) + "\n")

    print(f"Harvested {len(out_lines)} new samples for {y_s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
