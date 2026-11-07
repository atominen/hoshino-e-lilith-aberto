#!/usr/bin/env python3
"""Ensaio do pacote no PC principal, isolado das mentes; não aprova o Athlon."""
import json
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pacotes/alistair_pc2"
sys.path.insert(0, str(PACKAGE))
from verificar_pc2 import preflight
from pc2_node import Engine, Node, make_server
from core.alistair_backend import Client
from pc2_protocol import MODEL


def main():
    before = preflight(PACKAGE)
    engine = Engine(PACKAGE, {"ollama_port": 11438})
    node = server = None
    try:
        engine.start()
        secret = secrets.token_bytes(32)
        node = Node(engine, secret)
        server = make_server(node, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        client = Client(f"http://127.0.0.1:{server.server_port}", secret, timeout=120)
        started = time.monotonic()
        answer = client.infer("isolated-package-probe", {"model": MODEL,
            "messages": [{"role": "user", "content": "Calcule 14 + 7. Responda somente o número."}],
            "stream": False, "think": False,
            "options": {"num_ctx": 1024, "num_predict": 32, "num_gpu": 0, "temperature": 0}})
        seconds = round(time.monotonic() - started, 3)
        content = answer["message"]["content"].strip()
        if content != "21":
            raise RuntimeError("Resposta isolada diferente de 21: " + content)
        state = client.health()
        result = {"test_host": "pc_principal_not_athlon", "preflight": before,
                  "answer": content, "wall_seconds_including_queue_load": seconds,
                  "eval_count": answer.get("eval_count"), "cpu_residency_confirmed": state["engine"]["warm"],
                  "threads": state["threads"], "parallelism": state["parallelism"],
                  "mind_messages_created": 0, "real_lan_or_pc2_tested": False,
                  "cgroup_limits_on_pc2_tested": False}
    finally:
        if server: server.shutdown()
        if node: node.close()
        else: engine.close()
        if server: server.server_close()
    with socket.socket() as connection:
        result["owned_engine_port_released"] = connection.connect_ex(("127.0.0.1", 11438)) != 0
    result["owned_daemon_exit_confirmed"] = engine.process.poll() is not None
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
