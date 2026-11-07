#!/usr/bin/env python3
"""Verifica integridade e compatibilidade sem carregar o LLM."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 ** 2), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifesto.json").read_text())
    for name, record in manifest["files"].items():
        file = root / name
        if not file.resolve().is_relative_to(root):
            raise ValueError("Arquivo fora da pasta do pacote.")
        if "symlink" in record:
            if not file.is_symlink() or os.readlink(file) != record["symlink"] or not file.is_file():
                raise ValueError("Link alterado/ausente: " + name)
        elif not file.is_file() or file.is_symlink() or file.stat().st_size != record["bytes"] or sha(file) != record["sha256"]:
            raise ValueError("Integridade incorreta: " + name)
    return manifest


def preflight(root):
    root = Path(root).resolve()
    if sys.version_info < (3, 10) or platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Precisa de Linux x86_64 e Python 3.10+ (Mint 21/22 recomendado; confirme sua versão).")
    manifest = verify(root)
    engine = root / "engine/bin/ollama"
    env = {**os.environ, "LD_LIBRARY_PATH": str(root / "engine/lib/ollama"), "OLLAMA_HOST": "127.0.0.1:11438"}
    for binary in [engine, root / "engine/lib/ollama/llama-server", *sorted((root / "engine/lib/ollama").glob("lib*.so*"))]:
        if binary.is_symlink():
            continue
        result = subprocess.run(["ldd", str(binary)], env=env, capture_output=True, text=True, timeout=10)
        if result.returncode or "not found" in result.stdout:
            raise RuntimeError("Biblioteca do sistema ausente/incompatível: " + binary.name + ". Consulte LEIA-ME.md; não instale CUDA.")
    check = subprocess.run([str(engine), "--version"], env=env, capture_output=True, text=True, timeout=10)
    if check.returncode:
        raise RuntimeError("Motor incompatível com este Linux; nada foi iniciado.")
    available = shutil.disk_usage(root).free
    if available < 4 * 1024 ** 3:
        raise RuntimeError("Mantenha pelo menos 4 GiB livres após extrair o pacote.")
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemTotal:", "MemAvailable:")):
            memory[line.split(":", 1)[0]] = int(line.split()[1]) * 1024
    if memory.get("MemTotal", 0) < 8 * 1024 ** 3 or memory.get("MemAvailable", 0) < 5 * 1024 ** 3:
        raise RuntimeError("RAM total/disponível insuficiente para iniciar com folga; feche programas pesados.")
    return {"integrity": "ok", "engine": manifest["engine_version"], "memory": memory,
            "free_disk_bytes": available, "cgroup_v2": Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
            "pc2_performance_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integridade", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    result = {"integrity": "ok"} if args.integridade and verify(root) else preflight(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
