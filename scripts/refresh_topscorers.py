# scripts/refresh_topscorers.py
# Gera data/stats/topscorers.json cruzando plantel actual (squads),
# estatísticas (players) e lesões (injuries) para evitar jogadores transferidos
# e identificar lesionados.

import os
import json
import time
import argparse
import sys

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set
import requests

# Importa utilitário para limpar cache Redis de squads
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/utils')))
try:
    from redis_tools import clear_team_cache
except ImportError:
    def clear_team_cache(team_id, season=None):
        pass

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
BASE = (os.getenv("API_FOOTBALL_BASE") or "https://v3.football.api-sports.io").rstrip("/")
HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}

def req(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """GET com tolerância a rate-limit e timeouts."""
    url = f"{BASE}/{path.lstrip('/')}"
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status()
            return r.json() or {}
        except requests.HTTPError:
            # 429/5xx -> retry leve
            if r is not None and r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.0 + i * 0.7)
                continue
            raise
        except Exception:
            time.sleep(0.8 + i * 0.5)
    return {}

def load_leagues(leagues_file: Path) -> List[int]:
    if leagues_file and leagues_file.exists():
        data = json.loads(leagues_file.read_text(encoding="utf-8"))
        items = data.get("leagues") or data.get("items") or data
        ids = []
        for x in items or []:
            try:
                ids.append(int(x["id"]))
            except Exception:
                pass
        return sorted(set(ids))
    # fallback: Premier, LaLiga, Serie A, Bundesliga, Ligue1, Primeira, Eredivisie, Super Lig, UCL, UEL
    return [39,140,135,78,61,94,88,203,2,3]

def list_teams_for_league(league_id: int, season: int) -> List[Dict[str, Any]]:
    """Usa /teams?league=&season= para obter equipas da liga."""
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = req("teams", {"league": league_id, "season": season, "page": page})
        resp = data.get("response") or []
        for item in resp:
            team = item.get("team") or {}
            tid = team.get("id")
            name = team.get("name")
            if tid and name:
                out.append({"team_id": int(tid), "name": name})
        paging = data.get("paging") or {}
        if int(paging.get("current", 1)) >= int(paging.get("total", 1)):
            break
        page += 1
        time.sleep(0.25)
    # fallback se vazio: standings
    if not out:
        std = req("standings", {"league": league_id, "season": season}).get("response") or []
        for table in std:
            for grp in (table.get("league") or {}).get("standings") or []:
                for row in grp or []:
                    t = (row.get("team") or {})
                    if t.get("id"):
                        out.append({"team_id": int(t["id"]), "name": t.get("name", "")})
    return out

def set_squad(team_id: int) -> Set[int]:
    data = req("players/squads", {"team": team_id})  # docs: /squads?team= — alguns proxies expõem como players/squads
    if not data.get("response"):
        data = req("squads", {"team": team_id})
    ids: Set[int] = set()
    for item in data.get("response") or []:
        for p in (item.get("players") or []):
            if p.get("id"):
                ids.add(int(p["id"]))
    return ids

def injuries_set(team_id: int, season: int) -> Set[int]:
    data = req("injuries", {"team": team_id, "season": season})
    ids: Set[int] = set()
    for it in data.get("response") or []:
        p = it.get("player") or {}
        if p.get("id"):
            ids.add(int(p["id"]))
    return ids

def goals_by_player(team_id: int, league_id: int, season: int) -> Dict[int, Dict[str, Any]]:
    """Varre /players (paginação) e soma golos por jogador para a equipa/época."""
    page = 1
    agg: Dict[int, Dict[str, Any]] = {}
    while True:
        data = req("players", {"team": team_id, "league": league_id, "season": season, "page": page})
        resp = data.get("response") or []
        for row in resp:
            player = row.get("player") or {}
            stats = row.get("statistics") or []
            pid = player.get("id")
            if not pid:
                continue
            pid = int(pid)
            name = player.get("name", "")
            goals_total = 0
            for st in stats:
                goals = ((st.get("goals") or {}).get("total") or 0) or 0
                goals_total += int(goals or 0)
            if pid not in agg:
                agg[pid] = {"id": pid, "name": name, "goals": 0}
            agg[pid]["goals"] += goals_total
        paging = data.get("paging") or {}
        if int(paging.get("current", 1)) >= int(paging.get("total", 1)):
            break
        page += 1
        time.sleep(0.25)
    return agg

def pick_season(raw: str) -> int:
    tokens = [int(t) for t in str(raw).replace(";", " ").replace(",", " ").split() if t.isdigit()]
    return max(tokens) if tokens else datetime.utcnow().year

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", required=False, help="Época(s) '2024' ou '2023,2024'. Usa a mais recente.")
    ap.add_argument("--league", type=int, action="append", help="ID(s) da liga (repetir flag).")
    ap.add_argument("--leagues-file", default="config/leagues_main.json")
    ap.add_argument("--topn", type=int, default=5, help="N topo por equipa.")
    ap.add_argument("--exclude-injured", action="store_true", help="Exclui lesionados do top.")
    ap.add_argument("--out", default="data/stats/topscorers.json")
    args = ap.parse_args()

    if not API_KEY:
        print("[topscorers] Falta API_FOOTBALL_KEY — a escrever ficheiro vazio.")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"updated_at": datetime.utcnow().isoformat(), "teams": []}), encoding="utf-8")
        return

    season = pick_season(args.season or os.getenv("SEASONS") or os.getenv("API_FOOTBALL_SEASON") or "2024")
    leagues = list(set(args.league or []) or set(load_leagues(Path(args.leagues_file))))

    result = {
        "updated_at": datetime.utcnow().isoformat(),
        "season": season,
        "leagues": {},
    }

    for lg in leagues:
        print(f"[topscorers] Liga {lg} {season}")
        teams = list_teams_for_league(lg, season)
        league_entry = {"league_id": lg, "season": season, "teams": []}


        for t in teams:
            tid = t["team_id"]
            tname = t["name"]
            try:
                # Limpa cache Redis do squad antes de atualizar
                clear_team_cache(tid, season)
                squad_ids = set_squad(tid)
                inj = injuries_set(tid, season)
                goals = goals_by_player(tid, lg, season)

                rows = []
                for pid, info in goals.items():
                    # filtra quem não está no plantel actual (transferido)
                    if squad_ids and pid not in squad_ids:
                        continue
                    rows.append({
                        "id": pid,
                        "name": info["name"],
                        "goals": int(info["goals"] or 0),
                        "injured": pid in inj
                    })

                rows.sort(key=lambda x: (-x["goals"], x["name"]))
                if args.exclude_injured:
                    rows = [r for r in rows if not r["injured"]]
                league_entry["teams"].append({
                    "team_id": tid,
                    "name": tname,
                    "topscorers": rows[: args.topn]
                })
            except Exception as e:
                print(f"[topscorers] Falha equipa {tid} ({tname}): {e}")

            time.sleep(0.2)

        result["leagues"][str(lg)] = league_entry

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[topscorers] Gravado: {args.out}")

if __name__ == "__main__":
    main()
