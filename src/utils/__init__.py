# src/utils/__init__.py
from __future__ import annotations

import json
import os
from typing import Any, Optional

__all__ = ["load_json", "save_json"]

def load_json(path: str, default: Optional[Any] = None, encoding: str = "utf-8") -> Any:
    """
    Carrega JSON de forma robusta.
    - Suporta ficheiros com BOM (utf-8-sig)
    - Se o ficheiro não existir ou estiver vazio/ inválido, devolve `default` (ou {}).
    """
    if default is None:
        default = {}

    # 1) caminho inexistente
    if not os.path.exists(path):
        return default

    # 2) tenta ler em utf-8 normal
    try:
        with open(path, "r", encoding=encoding) as f:
            return json.load(f)
    except json.JSONDecodeError:
        # 3) tenta novamente com utf-8-sig (BOM) ou ficheiro vazio
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read().strip()
                if not text:
                    return default
                return json.loads(text)
        except Exception:
            return default
    except Exception:
        return default


def save_json(
    path: str,
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
    encoding: str = "utf-8",
) -> bool:
    """
    Grava JSON de forma atómica (escreve para .tmp e faz replace).
    Garante criação do diretório.
    """
    try:
        dirn = os.path.dirname(path) or "."
        os.makedirs(dirn, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding=encoding) as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
        os.replace(tmp, path)
        return True
    except Exception:
        return False
