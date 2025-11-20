"""
Ferramentas utilitárias para manutenção do cache Redis relacionado a plantéis e marcadores.
Permite forçar atualização de squads e stats de um time específico.
"""
from typing import Optional
from src import config

# Chaves típicas usadas no cache para squads e stats
SQUAD_KEY = "scorers:players/squads:{team_id}"
PLAYERS_STATS_KEY = "scorers:players:{team_id}:{season}"


def clear_team_cache(team_id: int, season: Optional[int] = None) -> None:
    """
    Remove do Redis as chaves de squad e stats de um time específico.
    """
    if not config.redis_client:
        print("[redis_tools] Redis não configurado.")
        return
    squad_key = SQUAD_KEY.format(team_id=team_id)
    config.redis_client.delete(squad_key)
    print(f"[redis_tools] Removido cache do squad: {squad_key}")
    if season:
        stats_key = PLAYERS_STATS_KEY.format(team_id=team_id, season=season)
        config.redis_client.delete(stats_key)
        print(f"[redis_tools] Removido cache de stats: {stats_key}")


def clear_all_squads_cache() -> None:
    """
    Remove todas as chaves de squads do Redis (padrão scorers:players/squads:*).
    """
    if not config.redis_client:
        print("[redis_tools] Redis não configurado.")
        return
    for key in config.redis_client.scan_iter("scorers:players/squads:*"):
        config.redis_client.delete(key)
        print(f"[redis_tools] Removido: {key}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", type=int, help="ID do time para limpar cache")
    ap.add_argument("--season", type=int, help="Época (opcional)")
    ap.add_argument("--all", action="store_true", help="Limpa cache de todos os squads")
    args = ap.parse_args()
    if args.all:
        clear_all_squads_cache()
    elif args.team:
        clear_team_cache(args.team, args.season)
    else:
        print("Use --team <id> ou --all")
