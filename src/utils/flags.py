# src/utils/flags.py
import os
from typing import Optional
from src import config

# Flag por defeito (env): true/false
ENV_DEFAULT = os.getenv("V2_MODELS_ENABLED", "false").lower() == "true"

# Redis keys
FLAG_KEY = "flag:v2_enabled"
FAIL_KEY = "flag:v2_fail_count"

# Limites para auto-desativar v2 após falhas
FAIL_MAX = int(os.getenv("V2_FAIL_MAX", "5"))     # nº de falhas até desligar
FAIL_TTL = int(os.getenv("V2_FAIL_TTL", "900"))   # segundos (15 min) de cooldown

def is_v2_enabled() -> bool:
    """
    Se houver override no Redis usa-o; senão respeita o ENV_DEFAULT.
    Se não houver Redis, cai para ENV_DEFAULT.
    """
    rc = config.redis_client
    if not rc:
        return ENV_DEFAULT
    try:
        ov = rc.get(FLAG_KEY)
        if ov is None:
            return ENV_DEFAULT
        return str(ov).lower() == "true"
    except Exception:
        return ENV_DEFAULT

def set_v2_enabled(enabled: bool, ttl: Optional[int] = None) -> None:
    rc = config.redis_client
    if not rc:
        return
    try:
        rc.set(FLAG_KEY, "true" if enabled else "false", ex=ttl)
    except Exception:
        pass

def note_v2_failure() -> None:
    """
    Incrementa o contador de falhas; se atingir FAIL_MAX, desliga v2 por FAIL_TTL.
    """
    rc = config.redis_client
    if not rc:
        return
    try:
        raw = rc.get(FAIL_KEY)
        cnt = int(raw) if (raw is not None and str(raw).isdigit()) else 0
        cnt += 1
        rc.set(FAIL_KEY, str(cnt), ex=FAIL_TTL)
        if cnt >= FAIL_MAX:
            # Kill-switch temporário
            set_v2_enabled(False, ttl=FAIL_TTL)
    except Exception:
        pass

def reset_v2_failure() -> None:
    rc = config.redis_client
    if not rc:
        return
    try:
        rc.delete(FAIL_KEY)
    except Exception:
        pass
