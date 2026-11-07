#!/usr/bin/env python3
"""Sintetiza candidatas Serena/Vivian em um único motor CPU, sem reprodução.

Execute com compartilhado/ambientes/tts-qwen/bin/python. Não altera identidade,
memória ou o motor TTS escolhido para a central. WAVs são evidências de ensaio.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import resource
import time


ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "compartilhado/modelos/voz/qwen3-tts"
MODEL = MODEL_ROOT / "Qwen3-TTS-12Hz-0.6B-CustomVoice"


def rss_kib() -> int | None:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--text", default="Olá, Gustavo. A imagem está pronta. Podemos conversar enquanto a outra tarefa continua.")
    parser.add_argument("--speakers", nargs="+", default=["Serena", "Vivian"])
    parser.add_argument("--output", type=Path, default=ROOT / "compartilhado/runtime/audio/ensaios_tts_20261006")
    args = parser.parse_args()
    if not 1 <= args.threads <= 8 or not 20 <= args.max_new_tokens <= 1024:
        parser.error("threads entre 1 e 8 e max-new-tokens entre 20 e 1024")
    os.environ.update({"HF_HOME": str(MODEL_ROOT / "cache"), "HF_HUB_OFFLINE": "1",
                       "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(77)
    print("Carregando UM motor Qwen TTS em CPU float32.", flush=True)
    started = time.monotonic()
    model = Qwen3TTSModel.from_pretrained(str(MODEL), device_map="cpu", dtype=torch.float32,
                                        attn_implementation="eager", local_files_only=True)
    loaded = time.monotonic() - started
    languages = model.get_supported_languages()
    speakers = model.get_supported_speakers()
    if "portuguese" not in [str(x).lower() for x in languages]:
        raise RuntimeError(f"Português não suportado: {languages}")
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {"tested_at": datetime.now().astimezone().isoformat(), "model": str(MODEL),
                "device": "cpu", "dtype": "float32", "threads": args.threads, "playback": False,
                "one_model_instance": True, "load_seconds": round(loaded, 3), "load_rss_kib": rss_kib(),
                "languages": languages, "speakers": speakers, "text": args.text, "turns": [],
                "versions": {name: version(name) for name in ("qwen-tts", "torch", "torchaudio", "transformers")},
                "limitations": ["Ensaio, não escolha final de voz.", "Não há speaker nativo PT-BR no catálogo CustomVoice.",
                                "Modelo 0.6B não aplica instruct; timbre escolhido por speaker ID.",
                                "Integridade de WAV não comprova sotaque/qualidade subjetiva."]}
    for speaker in args.speakers:
        if speaker.lower() not in [str(x).lower() for x in speakers]:
            raise RuntimeError(f"Speaker não suportado: {speaker}")
        print(f"Sintetizando candidata {speaker} em Portuguese.", flush=True)
        started = time.monotonic()
        with torch.inference_mode():
            waves, rate = model.generate_custom_voice(text=args.text, language="Portuguese", speaker=speaker,
                                                      max_new_tokens=args.max_new_tokens, do_sample=False)
        elapsed = time.monotonic() - started
        audio = np.asarray(waves[0])
        if audio.ndim != 1 or not len(audio) or not np.isfinite(audio).all() or not np.max(np.abs(audio)):
            raise RuntimeError("Áudio inválido, vazio, não finito ou silencioso")
        path = args.output / f"qwen_{speaker.casefold()}_ptbr.wav"
        sf.write(path, audio, rate, subtype="PCM_16")
        information = sf.info(path)
        turn = {"speaker": speaker, "file": str(path), "elapsed_seconds": round(elapsed, 3),
                "audio_seconds": round(len(audio) / rate, 3), "realtime_factor": round(elapsed / (len(audio) / rate), 3),
                "sample_rate": rate, "channels": information.channels, "bytes": path.stat().st_size,
                "rms": round(float(np.sqrt(np.mean(audio ** 2))), 6), "peak": round(float(np.max(np.abs(audio))), 6),
                "rss_kib": rss_kib(), "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        evidence["turns"].append(turn)
        (args.output / "verificacao_qwen_tts.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(turn, ensure_ascii=False), flush=True)
    print(f"Evidência: {args.output / 'verificacao_qwen_tts.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
