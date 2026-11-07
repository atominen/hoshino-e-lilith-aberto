#!/usr/bin/env python3
"""Geração real e resposta CPU concorrente; não grava conversas nas mentes reais."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import config
from alistair_runner import Alistair
from core import job_bus, resource_manager
from tools import image_gen


def main():
    result = {"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "standby": None,
              "acceptance_scope": "pipeline de imagem e concorrência CPU/GPU; não é o benchmark aa",
              "visual_review": {"reviewed": False, "note": "inspeção visual ainda necessária"}}
    queued = image_gen.gerar_imagem(
        "A clean friendly illustration of a cozy shared home office for three AI assistants. "
        "Two anime girls and a discreet butler represented as three small decorative portraits. "
        "A computer, a green plant, warm light, simple harmonious composition, no written text.",
        seed=61006, nome="integracao_qwen_standby", preset="medio")
    print(queued, flush=True)
    if "JOB_ID=" not in queued:
        raise RuntimeError(queued)
    job_id = queued.split("JOB_ID=", 1)[1].splitlines()[0]
    result["job_id"] = job_id
    began = time.monotonic()
    printed = 0
    while True:
        job = job_bus.get(job_id, config.ENTIDADE_ID)
        if job["status"] in job_bus.TERMINAL:
            result["job"] = job
            break
        gpu = resource_manager.status("gpu")
        if gpu and job["details"].get("phase") == "sampling" and result["standby"] is None:
            with tempfile.TemporaryDirectory(prefix="alistair-verificacao-") as temporary:
                settings = {"DB_PATH": str(Path(temporary) / "mind.db"),
                            "SELF_MODEL_PATH": str(ROOT / "entidades/alistair/identity/self_model.json"),
                            "MODEL_NAME": "alistair-qwen3.5-4b:latest", "OLLAMA_URL": "http://127.0.0.1:11437/api/chat",
                            "NUM_CTX": 4096, "NUM_PREDICT": 192}
                with patch.multiple(config, **settings):
                    alistair = Alistair()
                    original_tool = alistair.call_tool
                    def read_only(name, args):
                        if name != "central_estado":
                            return {"ok": False, "error": "ensaio somente de leitura"}
                        return original_tool(name, args)
                    alistair.call_tool = read_only
                    start = time.monotonic()
                    answer = alistair.chat({"id": "technical-standby-test", "sender": "usuario",
                        "text": "Teste técnico somente de leitura. Informe em uma frase se há uma imagem em execução e quem está usando a GPU. Não envie mensagens e não acorde ninguém."})
                    r = requests.get("http://127.0.0.1:11437/api/ps", timeout=10)
                    r.raise_for_status()
                    residency = r.json().get("models", [])
                    after = job_bus.get(job_id)
                    result["standby"] = {"answer": answer, "elapsed_seconds": round(time.monotonic() - start, 2),
                        "gpu_before": gpu, "gpu_after": resource_manager.status("gpu"),
                        "image_state_after": after["status"], "residency": residency,
                        "ok": bool(answer) and after["status"] == "running"
                              and bool(resource_manager.status("gpu"))
                              and any(m.get("name") == config.MODEL_NAME and m.get("size_vram") == 0 for m in residency)}
                    print("STANDBY " + json.dumps(result["standby"], ensure_ascii=False), flush=True)
        if time.monotonic() - printed > 15:
            print(json.dumps({"job": job_id, "state": job["status"], "progress": job["details"]}, ensure_ascii=False), flush=True)
            printed = time.monotonic()
        if time.monotonic() - began > config.IMAGE_TIMEOUT + 180:
            raise TimeoutError("monitor excedeu orçamento de tempo")
        time.sleep(2)
    result["ok"] = result["job"]["status"] == "done" and bool(result["standby"] and result["standby"]["ok"])
    path = ROOT / "docs/verificacao_imagem_standby_20261006.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Relatório: {path}; ok={result['ok']}", flush=True)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
