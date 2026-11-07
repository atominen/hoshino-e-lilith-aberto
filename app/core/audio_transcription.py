"""ASR de arquivos para a central, sem captura nem escrita em mentes.

Este módulo deve ser usado por um único worker persistente da central. O lock
protege a única instância lazy daquele processo; não é um compartilhamento de
memória entre processos. O motor, preparo do sinal e filtro de texto são os do
transcritor existente, sem iniciar suas threads de captura/diarização.
"""
from __future__ import annotations

import importlib.util
import math
import os
import threading
import time
import wave
from pathlib import Path

import config


SAMPLE_RATE = 16000
MAX_SECONDS = 120.0
MAX_BYTES = 25 * 1024 * 1024
PRIMARY_SOURCES = frozenset({"browser_microphone", "native_microphone", "microfone_principal", "microfone"})
_LOCK = threading.RLock()
_RECOGNIZER = None


class AudioTranscriptionError(RuntimeError):
    """Falha explícita: o chamador não deve publicar isto como fala do usuário."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _wave_metadata(path: Path) -> dict:
    """A central envia WAV PCM: valida duração antes de decodificar na RAM."""
    try:
        if not path.is_file():
            raise AudioTranscriptionError("missing_file", "O arquivo de áudio não existe.")
        if not 0 < path.stat().st_size <= MAX_BYTES:
            raise AudioTranscriptionError("file_size", "O áudio está vazio ou excede 25 MiB.")
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate()
            frames = audio.getnframes()
            channels = audio.getnchannels()
            width = audio.getsampwidth()
            duration = frames / rate if rate else 0.0
            if audio.getcomptype() != "NONE" or channels not in (1, 2) or width not in (1, 2, 3, 4):
                raise AudioTranscriptionError("unsupported_audio", "Envie áudio WAV PCM mono ou estéreo.")
            if not 8000 <= rate <= 192000:
                raise AudioTranscriptionError("sample_rate", "A taxa de amostragem do áudio não é suportada.")
            if not 0.2 <= duration <= MAX_SECONDS:
                raise AudioTranscriptionError("duration", "Grave entre 0,2 e 120 segundos de áudio.")
            # Evita aceitar um cabeçalho que promete mais PCM do que existe.
            data = audio.readframes(frames)
            if len(data) != frames * channels * width:
                raise AudioTranscriptionError("truncated_audio", "O arquivo de áudio está incompleto.")
            return {"duration_seconds": duration, "input_sample_rate": rate,
                    "input_channels": channels, "input_sample_width": width}
    except AudioTranscriptionError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioTranscriptionError("invalid_audio", "Não consegui ler o arquivo WAV PCM.") from exc


def _decode(path: Path):
    # PyAV, já usado pelo faster-whisper, reamostra 44,1/48 kHz e reduz estéreo.
    from faster_whisper.audio import decode_audio
    return decode_audio(str(path), sampling_rate=SAMPLE_RATE)


def _get_recognizer():
    """Reutiliza o Reconhecedor legado, fixando CPU/int8 e cache offline."""
    global _RECOGNIZER
    with _LOCK:
        if _RECOGNIZER is None:
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model
            from tools.transcricao import Reconhecedor

            requested = str(config.WHISPER_MODELO)
            if Path(requested).is_dir():
                model_path = requested
            else:
                model_path = download_model(requested, local_files_only=True,
                                            cache_dir=str(Path(config.HUGGINGFACE_CACHE_DIR) / "hub"))
            recognizer = Reconhecedor(preferido="faster")
            recognizer._modelo = WhisperModel(
                model_path, device="cpu", compute_type="int8",
                cpu_threads=max(1, min(4, os.cpu_count() or 1)), num_workers=1,
                local_files_only=True,
            )
            recognizer.nome = "faster"
            _RECOGNIZER = recognizer
        return _RECOGNIZER


def status() -> dict:
    """Inspeção sem importar/carregar modelo, abrir dispositivos ou buscar rede."""
    return {"engine": "faster-whisper", "model": str(config.WHISPER_MODELO),
            "available": importlib.util.find_spec("faster_whisper") is not None,
            "loaded": _RECOGNIZER is not None, "device": "cpu", "compute_type": "int8",
            "sample_rate": SAMPLE_RATE, "max_seconds": MAX_SECONDS,
            "diarization_available": importlib.util.find_spec("pyannote") is not None,
            "sharing": "single_persistent_worker", "downloads_allowed": False}


def release_model() -> None:
    """Permite ao worker liberar o ASR na parada, nunca durante outra inferência."""
    global _RECOGNIZER
    with _LOCK:
        _RECOGNIZER = None


def _finite(value, fallback=0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def transcribe(path: Path, source: str = "browser_microphone") -> dict:
    """Transcreve WAV; silêncio/erro levantam AudioTranscriptionError.

    ``usuario`` é o papel esperado da fonte primária, NÃO reconhecimento vocal.
    Outras fontes ficam desconhecidas. A diarização não é ativada por um simples
    upload do microfone e sua ausência nunca é disfarçada de identificação.
    """
    started = time.monotonic()
    path = Path(path)
    source = str(source or "").strip()
    if not source or len(source) > 100:
        raise AudioTranscriptionError("source", "Indique a origem do áudio.")
    metadata = _wave_metadata(path)
    try:
        from tools.transcricao import preparar, rms, texto_aproveitavel
        import numpy as np

        samples = _decode(path)
        if samples.ndim != 1 or not np.isfinite(samples).all():
            raise AudioTranscriptionError("invalid_samples", "O áudio contém amostras inválidas.")
        if len(samples) > int(MAX_SECONDS * SAMPLE_RATE) + SAMPLE_RATE:
            raise AudioTranscriptionError("duration", "O áudio excede 120 segundos.")
        energy = rms(samples - float(np.mean(samples))) if len(samples) else 0.0
        if not len(samples) or energy < 1e-5:
            raise AudioTranscriptionError("no_speech", "Não foi detectada fala no áudio.")
        samples = preparar(samples, SAMPLE_RATE)
        language = str(config.WHISPER_IDIOMA or "").strip() or None
        speaker = "usuario" if source in PRIMARY_SOURCES else "desconhecido"
        segments = []
        rejected = 0
        # Os segmentos são um generator: consumi-los faz parte da inferência e
        # precisa continuar dentro do lock, não apenas a chamada transcribe().
        with _LOCK:
            recognizer = _get_recognizer()
            decoded, info = recognizer._modelo.transcribe(
                samples, language=language, vad_filter=True,
                initial_prompt="Conversa em português brasileiro. Nomes: Hoshino, Lilith e Alistair.",
                beam_size=config.WHISPER_BEAM_SIZE, condition_on_previous_text=False,
                word_timestamps=False,
            )
            for segment in decoded:
                text = str(getattr(segment, "text", "") or "")
                accepted, text, _ = texto_aproveitavel(text, exigir_nome=False, min_palavras=1)
                no_speech = _finite(getattr(segment, "no_speech_prob", None), None)
                avg_log = _finite(getattr(segment, "avg_logprob", None), None)
                weak_speech = (no_speech is not None and avg_log is not None
                               and no_speech > 0.6 and avg_log < -1.0)
                if not accepted or not any(c.isalpha() for c in text) or weak_speech:
                    rejected += 1
                    continue
                start = _finite(getattr(segment, "start", 0.0))
                end = _finite(getattr(segment, "end", start), start)
                segments.append({"start": max(0.0, start), "end": max(start, end),
                                 "text": text, "speaker": speaker,
                                 "no_speech_probability": no_speech,
                                 "average_log_probability": avg_log})
        if not segments:
            raise AudioTranscriptionError("no_speech", "Não foi detectada fala aproveitável no áudio.")
        metadata.update({
            "engine": "faster-whisper", "model": str(config.WHISPER_MODELO),
            "device": "cpu", "compute_type": "int8", "sample_rate": SAMPLE_RATE,
            "vad_filter": True, "rms_before_normalization": round(energy, 7),
            "processing_seconds": round(time.monotonic() - started, 3),
            "filtered_segments": rejected, "language_basis": "configured" if language else "detected",
            # Uma língua forçada recebe probability=1 no motor; isto não é
            # confiança medida de identificação e não deve aparecer como tal.
            "language_probability": None if language else _finite(getattr(info, "language_probability", None), None),
            "speaker_basis": "source_role" if source in PRIMARY_SOURCES else "unknown",
            "speaker_identification_performed": False, "diarization_performed": False,
            "diarization_available": importlib.util.find_spec("pyannote") is not None,
            "diarization_reason": "primary_microphone_single_source" if source in PRIMARY_SOURCES else "not_requested",
            "application": None, "content": "speech",
        })
        return {"text": " ".join(segment["text"] for segment in segments),
                "language": str(getattr(info, "language", None) or language or "unknown"),
                "segments": segments, "source": source, "speaker": speaker,
                "speaker_basis": metadata["speaker_basis"], "metadata": metadata}
    except AudioTranscriptionError:
        raise
    except Exception as exc:
        raise AudioTranscriptionError("transcription_failed", "Não consegui transcrever o áudio; nenhuma mensagem foi enviada.") from exc
