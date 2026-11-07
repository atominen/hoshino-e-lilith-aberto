"""Um motor CPU compartilhado, Kokoro ou Qwen TTS, com RPC identificado.

Não captura dispositivos nem reproduz áudio. Logs vão para stderr. Cada texto
é dividido sem descarte; resultados só são publicados depois da WAV completa.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write("RESULT " + json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def text_chunks(text, limit=220):
    """Chunks limitados, sem cortar palavras ou descartar conteúdo."""
    if any(len(word) > limit for word in text.split()):
        raise ValueError("Palavra isolada acima do limite da fala; reformule. Nada foi cortado.")
    remaining = text.strip()
    while remaining:
        if len(remaining) <= limit:
            yield remaining
            return
        prefix = remaining[:limit + 1]
        boundaries = [m.end() for m in re.finditer(r"[.!?;:]\s+", prefix) if m.end() >= limit // 3]
        cut = boundaries[-1] if boundaries else prefix.rfind(" ", 1, limit + 1)
        if cut <= 0:
            raise ValueError("Não foi possível dividir o texto sem cortar palavras.")
        yield remaining[:cut].strip()
        remaining = remaining[cut:].strip()


def load_engine():
    with contextlib.redirect_stdout(sys.stderr):
        import soundfile as sf
        import numpy as np
        import torch
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        backend = os.environ.get("HOSHINO_AUDIO_TTS_BACKEND", "kokoro")
        if backend == "qwen3_tts":
            from qwen_tts import Qwen3TTSModel
            model_path = Path(os.environ["HOSHINO_AUDIO_TTS_MODEL"])
            if not model_path.is_dir():
                raise RuntimeError("Modelo Qwen TTS local ausente.")
            device=os.environ.get('HOSHINO_AUDIO_TTS_DEVICE','cpu')
            if device not in {'cpu','hip'}:raise RuntimeError('Dispositivo TTS inválido.')
            if device=='hip' and (not torch.version.hip or not torch.cuda.is_available()):raise RuntimeError('PyTorch AMD/HIP indisponível; GPU não foi usada.')
            # No PyTorch ROCm, a API se chama cuda mesmo sendo hardware AMD.
            pipe = Qwen3TTSModel.from_pretrained(str(model_path), device_map="cuda:0" if device=='hip' else 'cpu', dtype=torch.float32,
                                               attn_implementation="eager", local_files_only=True)
            if "portuguese" not in [str(x).casefold() for x in pipe.get_supported_languages()]:
                raise RuntimeError("Motor não oferece português.")
        elif backend == "kokoro":
            from kokoro import KPipeline
            pipe = KPipeline(lang_code="p", repo_id="hexgrad/Kokoro-82M", device="cpu")
        else:
            raise ValueError("Backend de voz desconhecido.")
    return backend, pipe, np, sf, torch


def main() -> int:
    engine = None
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        request_id = None
        output = None
        try:
            req = json.loads(raw)
            request_id = req.get("id")
            if req.get("op") == "stop":
                emit({"id": request_id, "ok": True, "stopped": True})
                return 0
            if req.get("op") != "synthesize":
                raise ValueError("operação desconhecida")

            texto = str(req.get("text") or "").strip()
            voice = str(req.get("voice") or "pf_dora")
            speed = float(req.get("speed", 1.0))
            output = Path(str(req["output"])).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            if not texto or len(texto) > 2400:
                raise ValueError("texto vazio ou acima de 2400 caracteres; nada foi cortado")
            if not 0.5 <= speed <= 2.0:
                raise ValueError("velocidade fora do contrato")
            chunks = list(text_chunks(texto))
            if engine is None:
                engine = load_engine()
            backend, pipe, np, sf, torch = engine

            partes = []
            with contextlib.redirect_stdout(sys.stderr):
                for chunk in chunks:
                    if backend == "qwen3_tts":
                        if voice.casefold() not in [str(x).casefold() for x in pipe.get_supported_speakers()]:
                            raise ValueError("Timbre não suportado pelo Qwen TTS.")
                        if speed != 1.0:
                            raise ValueError("Qwen TTS não oferece controle de velocidade neste adaptador.")
                        with torch.inference_mode():
                            waves, rate = pipe.generate_custom_voice(text=chunk, language="Portuguese", speaker=voice,
                                                                     max_new_tokens=512, do_sample=False)
                        audio = np.asarray(waves[0])
                        # 12 Hz: atingir o teto indica possível truncamento, nunca sucesso.
                        if len(audio) / rate >= 512 / 12 - 1:
                            raise RuntimeError("A fala atingiu o limite de geração; texto não foi confirmado completo.")
                        partes.append(audio)
                    else:
                        rate = 24000
                        for _, _, audio in pipe(chunk, voice=voice, speed=speed, split_pattern=r"\n+"):
                            partes.append(audio.cpu().numpy() if hasattr(audio, "cpu") else np.asarray(audio))

            if not partes:
                raise RuntimeError("Motor não retornou áudio")
            audio = np.concatenate(partes)
            if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all() or not np.max(np.abs(audio)):
                raise RuntimeError("Motor produziu áudio vazio, silencioso ou inválido")

            sf.write(output, audio, rate, subtype="PCM_16")
            result = {"output": str(output), "sample_rate": rate, "backend": backend,
                      "voice": voice, "duration_seconds": len(audio) / rate,
                      "device":os.environ.get('HOSHINO_AUDIO_TTS_DEVICE','cpu') if backend=='qwen3_tts' else 'cpu'}
            emit({"id": request_id, "ok": True, "result": result, **result})
        except Exception as exc:
            if output:
                output.unlink(missing_ok=True)
            emit({
                "id": request_id, "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return 0


if __name__ == "__main__":
    if '--probe-device' in sys.argv:
        import torch
        print(json.dumps({'amd_hip_available':bool(torch.version.hip and torch.cuda.is_available())}));raise SystemExit(0)
    raise SystemExit(main())
