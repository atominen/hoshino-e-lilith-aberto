#!/usr/bin/env python3
"""Instala o ensaio Qwen TTS em ambiente CPU isolado, preservando o legado.

Fontes: pacote oficial qwen-tts, wheels CPU oficiais PyTorch e checkpoint
Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice. Não executa inferência nem toca áudio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "compartilhado/ambientes/tts-qwen"
PYTHON = ENV / "bin/python"
MODEL_ROOT = ROOT / "compartilhado/modelos/voz/qwen3-tts"
MODEL = MODEL_ROOT / "Qwen3-TTS-12Hz-0.6B-CustomVoice"
REPOSITORY = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
REVISION = "85e237c12c027371202489a0ec509ded67b5e4b5"
GIB = 1024 ** 3
RESERVE = 12 * GIB


def check_space(additional: int = 0) -> None:
    free = shutil.disk_usage(ROOT).free
    if free < RESERVE + additional:
        raise RuntimeError(
            f"Espaço insuficiente: {free / GIB:.2f} GiB livres; "
            f"reserva {RESERVE / GIB:.0f} GiB + previsão {additional / GIB:.1f} GiB. "
            "Nenhum componente legado será apagado para abrir espaço."
        )
    print(f"Disco: {free / GIB:.2f} GiB livres; reserva protegida de 12 GiB.", flush=True)


def run(args: list[str], *, env: dict | None = None) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def prepare() -> None:
    check_space(6 * GIB)
    if not PYTHON.is_file():
        python312 = shutil.which("python3.12")
        if not python312:
            raise RuntimeError("Python 3.12 não encontrado; o ambiente legado não será modificado.")
        print("Criando ambiente TTS Qwen isolado.", flush=True)
        run([python312, "-m", "venv", str(ENV)])
    print("Preparando dependências oficiais em CPU, sem CUDA/ROCm.", flush=True)
    run([str(PYTHON), "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
         "torch==2.6.0+cpu", "torchaudio==2.6.0+cpu", "--index-url", "https://download.pytorch.org/whl/cpu"])
    run([str(PYTHON), "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
         "qwen-tts==0.1.1", "--index-url", "https://pypi.org/simple"])
    run([str(PYTHON), "-m", "pip", "check"])
    run([str(PYTHON), str(Path(__file__).resolve()), "--download"])
    check_space()
    run([str(PYTHON), str(Path(__file__).resolve()), "--verify"])


def download() -> None:
    from huggingface_hub import HfApi, snapshot_download
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    info = HfApi().model_info(REPOSITORY, revision=REVISION, files_metadata=True)
    if info.sha != REVISION:
        raise RuntimeError("A revisão retornada não coincide com o checkpoint auditado.")
    for file in info.siblings:
        if not (MODEL / file.rfilename).resolve().is_relative_to(MODEL.resolve()):
            raise RuntimeError("Nome de arquivo remoto fora do diretório do modelo.")
    required_bytes = sum(int(file.size or 0) for file in info.siblings
                         if not (MODEL / file.rfilename).is_file())
    check_space(required_bytes + GIB)
    print(f"Modelo oficial: {REPOSITORY}; revisão {info.sha}; faltam ~{required_bytes / GIB:.2f} GiB.", flush=True)
    snapshot_download(repo_id=REPOSITORY, revision=info.sha, local_dir=MODEL, max_workers=2)
    verified_files = []
    for file in info.siblings:
        path = MODEL / file.rfilename
        if not path.is_file() or (file.size is not None and path.stat().st_size != file.size):
            raise RuntimeError(f"Checkpoint incompleto: {file.rfilename}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        actual = digest.hexdigest()
        lfs = file.lfs
        expected = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
        if expected and actual != expected:
            raise RuntimeError(f"SHA-256 divergente: {file.rfilename}")
        verified_files.append({"name": file.rfilename, "bytes": file.size, "sha256": actual,
                               "official_lfs_sha256": expected})
    (MODEL_ROOT / "origem_verificada.json").write_text(json.dumps({
        "repo_id": REPOSITORY, "revision": info.sha, "total_bytes": sum(int(x.size or 0) for x in info.siblings),
        "files": verified_files,
        "source": "https://huggingface.co/" + REPOSITORY,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Checkpoint completo em: {MODEL}", flush=True)


def verify() -> None:
    from importlib.metadata import distributions, version
    import torch
    import torchaudio
    from qwen_tts import Qwen3TTSModel
    assert torch.version.cuda is None, "A instalação não é CPU-only"
    assert not any(x.metadata.get("Name", "").startswith("nvidia-") for x in distributions()), "Há pacote NVIDIA inesperado"
    for required in ("config.json", "model.safetensors", "speech_tokenizer/config.json", "speech_tokenizer/model.safetensors"):
        if not (MODEL / required).is_file():
            raise RuntimeError(f"Arquivo necessário ausente: {required}")
    print(json.dumps({"ready_for_benchmark": True, "torch": torch.__version__, "torchaudio": torchaudio.__version__,
                      "qwen-tts": version("qwen-tts"), "transformers": version("transformers"),
                      "device": "cpu", "cuda_libraries": False, "model": str(MODEL)}, indent=2), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--download", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    os.environ["HF_HOME"] = str(MODEL_ROOT / "cache")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    if args.download:
        download()
    elif args.verify:
        verify()
    else:
        prepare()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
