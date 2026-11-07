#!/usr/bin/env python3
"""Teste isolado do executor: não envia mensagens para nenhuma mente."""
import json
import time
import uuid
from pathlib import Path
from core.alistair_backend import Client
from pc2_protocol import MODEL


def main():
    root = Path(__file__).resolve().parent
    config = json.loads((root / "worker.json").read_text())
    # Execute no PC principal usando o pareamento; o worker só aceita seu IP.
    pair = root / "pareamento"
    client = Client(f"http://{config['bind']}:8770", bytes.fromhex((pair / "lan.key").read_text().strip()))
    return benchmark(client)


def benchmark(client):
    start = time.monotonic()
    answer = client.infer("benchmark-" + uuid.uuid4().hex, {"model": MODEL,
        "messages": [{"role": "user", "content": "Calcule 14 + 7 e responda apenas o número, sem comentários."}],
        "stream": False, "think": False, "options": {"num_ctx": 1024, "num_predict": 32, "num_gpu": 0}})
    elapsed = round(time.monotonic() - start, 3)
    value = {"wall_seconds_including_queue_load": elapsed, "answer": answer["message"].get("content"),
             "engine_eval_count": answer.get("eval_count"), "health": client.health(),
             "isolated_context": True, "no_mind_messages": True}
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return value


if __name__ == "__main__":
    main()
