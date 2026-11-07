import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.chdir(ROOT)

from core import diagnostics
from tools import diagnostico
import config


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


# JSON-serialização de objetos de tempo não pode derrubar o diagnóstico.
diagnostics.emit("test.datetime", when=datetime.now(), token="nao_deve_aparecer")
arquivos = sorted((Path(config.RUNTIME_DIR) / "diagnostics").glob("hoshino_*.jsonl"))
obj = None
for arquivo in reversed(arquivos):
    for raw in reversed(arquivo.read_text(encoding="utf-8").splitlines()):
        try:
            candidato = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if candidato.get("event") == "test.datetime":
            obj = candidato
            break
    if obj:
        break
ok(obj is not None, "evento de diagnóstico não foi encontrado")
ok(obj["data"]["token"] == "[REDACTED]", "redaction de token falhou")
ok("when" in obj["data"], "datetime não foi serializado")

estado = diagnostico.estado()
ok("diagnostics" in estado, "estado de diagnóstico não informa pasta")
print("Diagnóstico: tudo passou.")
