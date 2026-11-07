#!/usr/bin/env python3
"""HTTP real → dois timbres → ASR/cancelamento, sem mentes ou dispositivos reais.

Os bancos do ensaio são temporários; WAVs de saída são artefatos nas pastas de
áudio. Não reproduz som, não captura microfone e não inicia modelos de conversa.
"""
from contextlib import ExitStack
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.request import Request, urlopen
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
import iniciar_entidades as launcher
from core import interentity as bus, job_bus, resource_manager as resources
from core.audio_service import AudioService

TEXT = "Olá, Gustavo. A imagem está pronta. Podemos conversar enquanto a outra tarefa continua."


def main():
    evidence = {"tested_at": datetime.now().astimezone().isoformat(), "scope": "real_workers_and_http",
                "capture": False, "playback": False, "mental_memories": "untouched",
                "message_and_job_databases": "temporary", "turns": [], "limitations": [
                "Áudio sintético não comprova microfone físico, ruído ou sotaque natural.",
                "Papel usuario atribuído pela rota de microfone não é identificação biométrica."]}
    with tempfile.TemporaryDirectory(prefix="central-audio-ensaio-") as directory, ExitStack() as stack:
        directory = Path(directory)
        for module, attr, value in [(bus, "DB_PATH", directory / "messages.sqlite"),
                                    (job_bus, "DB_PATH", directory / "jobs.sqlite"),
                                    (resources, "DB_PATH", directory / "resources.sqlite"),
                                    (resources, "LOCK_DIR", directory / "locks")]:
            stack.enter_context(patch.object(module, attr, value))
        service = AudioService(ROOT)
        server, token = launcher.make_server(launcher.Supervisor(), port=0, audio=service)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def call(route, data=None, binary=False):
            headers = {"Authorization": "Bearer " + token}
            if data is not None:
                headers["Content-Type"] = "audio/wav" if binary else "application/json"
            body = data if binary else json.dumps(data).encode() if data is not None else None
            with urlopen(Request(base + "/api/" + route, data=body, headers=headers), timeout=30) as response:
                raw = response.read()
                return raw if response.headers.get_content_type() == "audio/wav" else json.loads(raw)

        def wait(job):
            deadline = time.monotonic() + 650
            while time.monotonic() < deadline:
                state = call("audio/job?id=" + job["id"])
                if state["status"] in job_bus.TERMINAL:
                    return state
                time.sleep(.5)
            raise TimeoutError("Ensaio de áudio excedeu orçamento.")

        try:
            evidence["state_before"] = call("audio/state")
            tts_pid = None
            for entity in ("hoshino", "lilith"):
                message = bus.send(entity, "usuario", TEXT)
                began = time.monotonic()
                job = wait(call("audio/synthesize", {"entity": entity, "message_id": message["id"]}))
                if job["status"] != "done":
                    raise RuntimeError(str(job))
                data = call("audio/file?id=" + job["id"])
                with wave.open(io.BytesIO(data)) as wav:
                    if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not wav.getnframes():
                        raise RuntimeError("WAV inválida na resposta HTTP")
                    duration = wav.getnframes() / wav.getframerate()
                pid = service.tts.process.pid
                if tts_pid is not None and tts_pid != pid:
                    raise RuntimeError("O segundo timbre não reutilizou o motor compartilhado")
                tts_pid = pid
                evidence["turns"].append({"entity": entity, "id": job["id"], "result": job["result"],
                    "elapsed_seconds": round(time.monotonic() - began, 3), "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(), "duration_seconds": round(duration, 3), "worker_pid": pid})
                print(f"{entity}: fala concluída em {evidence['turns'][-1]['elapsed_seconds']} s", flush=True)
            began = time.monotonic()
            transcription = wait(call("audio/transcribe?entity=lilith", data, binary=True))
            if transcription["status"] != "done":
                raise RuntimeError(str(transcription))
            if bus.inbox("lilith"):
                raise RuntimeError("Transcrição foi enviada sem revisão")
            evidence["transcription"] = {**transcription, "elapsed_seconds": round(time.monotonic() - began, 3),
                "input_is_synthetic": True, "tts_released_before_asr": not service.tts.alive(),
                "message_not_auto_sent": True}
            print("ASR HTTP: " + transcription["result"]["text"], flush=True)
            cancelled = call("audio/transcribe?entity=hoshino", data, binary=True)
            call("audio/cancel", {"id": cancelled["id"]})
            cancelled = wait(cancelled)
            if cancelled["status"] != "interrupted":
                raise RuntimeError("Cancelamento não confirmado: " + str(cancelled))
            evidence["cancelled"] = cancelled
            evidence["state_after"] = call("audio/state")
            evidence["status"] = "passed"
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(5)
            evidence["workers_stopped"] = not service.tts.alive() and not service.asr.alive()
        destination = ROOT / "docs/verificacao_audio_central_20261006.json"
        destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(str(destination), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
