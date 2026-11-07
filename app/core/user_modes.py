"""Pequenos estados de interação controlados pela própria Hoshino."""
from __future__ import annotations
import json
from pathlib import Path
import config

def _path() -> Path:
    """Resolve o estado no runtime configurado, permitindo testes/instalações isoladas."""
    return Path(config.RUNTIME_DIR) / "modo_interacao.json"

def _ler():
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def silencioso() -> bool:
    return bool(_ler().get("silencioso", False))

def definir_silencioso(valor: bool) -> str:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"silencioso": bool(valor)}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return "modo silencioso ativado" if valor else "modo silencioso desativado"
