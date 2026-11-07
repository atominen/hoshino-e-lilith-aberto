#!/usr/bin/env python3
"""Audita o worker legado offline, sem abrir microfone ou tocar áudio.

Usa somente pesos já locais. WAVs e logs ficam em um diretório temporário
removido no final; a evidência JSON é emitida em stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import select
import shutil
import struct
import subprocess
import tempfile
import time
import wave


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "compartilhado/ambientes/voz/bin/python"
WORKER = ROOT / "app/tools/voice_worker.py"
CACHES = {
    "principal": ROOT / "compartilhado/modelos/huggingface",
    "legado": ROOT / "compartilhado/modelos/voz/huggingface",
}


def rss_kib(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def wav_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        frames = wav.getnframes()
        width = wav.getsampwidth()
        data = wav.readframes(frames)
    if width != 2 or not frames or not rate:
        raise ValueError("WAV vazio ou formato inesperado")
    samples = struct.unpack(f"<{len(data) // 2}h", data)
    peak = max(abs(x) for x in samples) / 32768
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768
    if peak == 0:
        raise ValueError("áudio completamente silencioso")
    return {
        "channels": channels, "sample_rate": rate, "seconds": round(frames / rate, 3),
        "peak": round(peak, 6), "rms": round(rms, 6), "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def response(process: subprocess.Popen, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if not select.select([process.stdout], [], [], remaining)[0]:
            raise TimeoutError("worker excedeu o prazo")
        line = process.stdout.readline()
        if not line:
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
            raise RuntimeError(f"worker encerrou sem RESULT; código {process.poll()}")
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    raise TimeoutError("worker excedeu o prazo")


def audit_cache(name: str, cache: Path, timeout: float, voices: list[str], keep_output: Path | None = None) -> dict:
    evidence = {"cache": name, "path": str(cache), "offline": True, "playback": False, "turns": []}
    env = os.environ.copy()
    env.update({
        "HF_HOME": str(cache), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4",
        "TOKENIZERS_PARALLELISM": "false",
    })
    with tempfile.TemporaryDirectory(prefix="hoshino-tts-audit-") as directory:
        log_path = Path(directory) / "worker.log"
        with log_path.open("w+") as log:
            process = subprocess.Popen(
                [str(PYTHON), str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=log, text=True, bufsize=1, env=env,
            )
            try:
                for index, voice in enumerate(voices):
                    output = Path(directory) / f"turn-{index}.wav"
                    text = "Olá, Gustavo. Estou verificando a síntese local em português brasileiro, sem reproduzir áudio."
                    started = time.monotonic()
                    process.stdin.write(json.dumps({
                        "op": "synthesize", "text": text, "voice": voice,
                        "speed": 1.0, "output": str(output),
                    }, ensure_ascii=False) + "\n")
                    process.stdin.flush()
                    result = response(process, timeout)
                    turn = {"voice": voice, "elapsed_seconds": round(time.monotonic() - started, 3),
                            "ok": bool(result.get("ok")), "worker_rss_kib": rss_kib(process.pid)}
                    if result.get("ok"):
                        turn.update(wav_info(output))
                        if keep_output is not None:
                            keep_output.mkdir(parents=True, exist_ok=True)
                            retained = keep_output / f"kokoro-{name}-{voice}-{index}.wav"
                            shutil.copyfile(output, retained)
                            turn["retained_file"] = str(retained)
                    else:
                        turn["error"] = result.get("error", "falha sem motivo")
                    evidence["turns"].append(turn)
                evidence["ok"] = all(turn["ok"] for turn in evidence["turns"])
            except Exception as exc:
                evidence.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                try:
                    if process.poll() is None:
                        process.stdin.write('{"op":"stop"}\n')
                        process.stdin.flush()
                        process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                for stream in (process.stdin, process.stdout):
                    try:
                        stream.close()
                    except OSError:
                        pass
                log.flush()
                evidence["worker_log_tail"] = log_path.read_text(errors="replace").splitlines()[-10:]
    evidence["temporary_outputs_removed"] = True
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", choices=["principal", "legado", "ambos"], default="ambos")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--voices", nargs="+", default=["pf_dora", "pf_dora"])
    parser.add_argument("--output", type=Path, help="preservar cópias de WAVs para ensaio independente")
    args = parser.parse_args()
    selected = CACHES.items() if args.cache == "ambos" else [(args.cache, CACHES[args.cache])]
    evidence = {"tested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "worker": str(WORKER), "python": str(PYTHON),
                "results": [audit_cache(name, cache, args.timeout, args.voices, args.output) for name, cache in selected]}
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if all(result.get("ok") for result in evidence["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
