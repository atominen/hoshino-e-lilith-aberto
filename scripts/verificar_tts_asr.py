#!/usr/bin/env python3
"""Ensaio local TTS → ASR, sem tocar captura, reprodução ou memórias.

Execute no ambiente principal. As duas candidatas passam pelo mesmo ASR CPU
persistente deste processo. WER mede fidelidade textual, não timbre, naturalidade
ou qualidade subjetiva da voz. O relatório JSON vai apenas para stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

DEFAULT_TEXT = "Olá, Gustavo. A imagem está pronta. Podemos conversar enquanto a outra tarefa continua."


def words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    # Mantém os acentos portugueses, ignora caixa e pontuação, sem reescrever
    # palavras parecidas para favorecer artificialmente o resultado.
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def compare(reference: str, hypothesis: str) -> dict:
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        raise ValueError("O texto esperado não pode ser vazio.")
    distance = list(range(len(hyp) + 1))
    for i, expected in enumerate(ref, start=1):
        row = [i]
        for j, received in enumerate(hyp, start=1):
            row.append(min(distance[j] + 1, row[-1] + 1,
                           distance[j - 1] + (expected != received)))
        distance = row
    errors = distance[-1]
    return {"normalized_reference": " ".join(ref), "normalized_hypothesis": " ".join(hyp),
            "reference_words": len(ref), "hypothesis_words": len(hyp),
            "word_errors": errors, "word_error_rate": errors / len(ref),
            "normalized_equal": ref == hyp}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--expected", default=DEFAULT_TEXT)
    args = parser.parse_args(argv)
    compare(args.expected, args.expected)  # Valida antes de carregar qualquer modelo.
    paths = args.paths or [ROOT / "compartilhado/runtime/audio/ensaios_tts_20261006" / name
                          for name in ("qwen_serena_ptbr.wav", "qwen_vivian_ptbr.wav")]
    from core import audio_transcription

    records = []
    try:
        for path in paths:
            record = {"path": str(path.resolve()), "expected_text": args.expected}
            try:
                if not path.is_file():
                    raise FileNotFoundError("A candidata ainda não está disponível.")
                record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                result = audio_transcription.transcribe(path, source="synthetic_tts_fixture")
                record.update({"ok": True, "transcript_literal": result["text"],
                               "comparison": compare(args.expected, result["text"]),
                               "transcription": result})
            except Exception as exc:
                record.update({"ok": False, "error_type": type(exc).__name__,
                               "error_code": getattr(exc, "code", "verification_failed"), "error": str(exc)})
            records.append(record)
    finally:
        audio_transcription.release_model()
    report = {"test": "local_tts_to_asr_text_fidelity", "source": "synthetic_tts_fixture",
              "asr": {"engine": "faster-whisper", "device": "cpu", "compute_type": "int8",
                      "downloads_allowed": False, "same_process_for_all_candidates": True},
              "limitations": ["Não mede timbre, naturalidade ou distinção subjetiva das vozes.",
                              "Texto produzido por ASR também pode conter erro; não prova qualidade absoluta.",
                              "Não captura/reproduz hardware nem publica mensagens ou memórias."],
              "records": records}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if records and all(r["ok"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
