#!/usr/bin/env python3
"""Instala os dois modelos adicionais em catálogos exclusivos e verifica hashes."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M"


def ensure_daemon(entity, port):
    if {'hoshino':11435, 'lilith':11436, 'alistair':11437}.get(entity) != port:
        raise ValueError('O ensaio só pode iniciar o endpoint dedicado da entidade correspondente.')
    base = f"http://127.0.0.1:{port}"
    try:
        r = requests.get(base + "/api/tags", timeout=2)
        r.raise_for_status()
        return base
    except requests.ConnectionError:
        pass
    directory = ROOT / "compartilhado/runtime/ollama" / entity
    directory.mkdir(parents=True, exist_ok=True)
    storage = ROOT / "compartilhado/modelos" / ("ollama" if entity == "hoshino" else f"ollama-{entity}")
    storage.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "OLLAMA_HOST": f"127.0.0.1:{port}", "OLLAMA_MODELS": str(storage), "OLLAMA_VULKAN": "1"}
    # Mesmo contrato do boot normal; só se aplica a um daemon novo. Não
    # reconfigura/reinicia o endpoint vivo nem imprime o ambiente herdado.
    app_path = str(ROOT / 'app')
    if app_path not in sys.path:
        sys.path.insert(0, app_path)
    from core import resource_manager
    env.update(resource_manager.ram_prompt_cache_environment(entity, env))
    with (directory / "server.log").open("a") as log:
        proc = subprocess.Popen([shutil.which("ollama") or "ollama", "serve"], env=env,
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
    for _ in range(40):
        if proc.poll() is not None:
            raise RuntimeError(f"daemon {entity} encerrou: {proc.returncode}")
        try:
            r = requests.get(base + "/api/tags", timeout=1)
            r.raise_for_status()
            return base
        except requests.ConnectionError:
            time.sleep(0.25)
    raise RuntimeError(f"daemon {entity} não respondeu")


def materialize(source, target, digest):
    """Troca um link por arquivo independente, sem escrever no destino do link."""
    if target.exists() and not target.is_symlink():
        source = target
    target.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    temp = None
    try:
        if source == target:
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    h.update(block)
        else:
            with source.open("rb") as original, tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
                temp = Path(out.name)
                for block in iter(lambda: original.read(8 * 1024 * 1024), b""):
                    h.update(block)
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
        if h.hexdigest() != digest.removeprefix("sha256:"):
            raise RuntimeError(f"hash incorreto: {target.name}")
        if temp:
            os.replace(temp, target)
            temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def stream_api(base, endpoint, payload):
    last = ""
    reported = 0
    with requests.post(base + endpoint, json=payload, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        for raw in response.iter_lines():
            if not raw:
                continue
            item = json.loads(raw)
            if item.get("error"):
                raise RuntimeError(item["error"])
            last = item.get("status", "")
            if time.monotonic() - reported > 15 or last == "success":
                total = item.get("total", 0)
                progress = f" {100 * item.get('completed', 0) / total:.0f}%" if total else ""
                print(last + progress, flush=True)
                reported = time.monotonic()
    if last != "success":
        raise RuntimeError("instalação não confirmou sucesso")


def main():
    source = ROOT / "compartilhado/modelos/ollama"
    target = ROOT / "compartilhado/modelos/ollama-lilith"
    manifest_path = Path("manifests/hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF/Q4_K_M")
    manifest = json.loads((source / manifest_path).read_text())
    blobs = [manifest["config"], *manifest["layers"]]
    required = sum(b["size"] for b in blobs if not (target / "blobs" / b["digest"].replace(":", "-")).is_file()
                   or (target / "blobs" / b["digest"].replace(":", "-")).is_symlink())
    if shutil.disk_usage(ROOT).free < required + 4 * 1024 ** 3:
        raise RuntimeError("espaço insuficiente para a cópia da Lilith e o Alistair")
    print("Instalando cópia independente do modelo da Lilith...", flush=True)
    for blob in blobs:
        name = blob["digest"].replace(":", "-")
        materialize(source / "blobs" / name, target / "blobs" / name, blob["digest"])
    (target / manifest_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / manifest_path, target / manifest_path)
    lilith = ensure_daemon("lilith", 11436)
    stream_api(lilith, "/api/create", {
        "model": "lilith-qwen3.5-9b:latest", "from": BASE,
        "system": "Você é o modelo local da Lilith. A aplicação fornece sua identidade, memória e estado próprios. Responda em português do Brasil.",
        "parameters": {"num_ctx": 16384, "num_predict": 4096, "temperature": 0.75}})
    alistair = ensure_daemon("alistair", 11437)
    from preparar_executores_leves import install_selected
    print("Importando Qwen3.5 4B verificado para Alistair; sem pull implícito...", flush=True)
    install_selected(entity='alistair',candidate='qwen3.5-4b')
    for base, model in [(lilith, "lilith-qwen3.5-9b:latest"), (alistair, "alistair-qwen3.5-4b:latest")]:
        r = requests.post(base + "/api/show", json={"model": model}, timeout=10)
        r.raise_for_status()
        body = r.json()
        print(f"Verificado: {model} / {body.get('details', {}).get('parameter_size')}", flush=True)
    print("Instalação concluída. Os três modelos de conversa têm configuração e catálogo próprios.", flush=True)


if __name__ == "__main__":
    main()
