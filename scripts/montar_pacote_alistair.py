#!/usr/bin/env python3
"""Exportação por lista permitida; nunca copia runtime, mente ou credenciais."""
import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path("manifests/registry.ollama.ai/library/alistair-qwen3.5-4b/latest")
ALLOWED = {
    "app/pc2_node.py": "pc2_node.py", "app/pc2_protocol.py": "pc2_protocol.py",
    "app/core/work_queue.py": "core/work_queue.py",
    "app/core/alistair_backend.py": "core/alistair_backend.py",
    "scripts/image_child.py": "child_guard.py",
    "pc2/configurar_pc2.py": "configurar_pc2.py", "pc2/verificar_pc2.py": "verificar_pc2.py",
    "pc2/benchmark_pc2.py": "benchmark_pc2.py", "pc2/iniciar.sh": "iniciar.sh",
    "pc2/parar.sh": "parar.sh", "pc2/LEIA-ME.md": "LEIA-ME.md",
    "third_party/ORIGENS.md": "ORIGENS.md",
    "third_party/licenses/AIRI.MIT": "licenses/AIRI.MIT",
    "third_party/licenses/OLLAMA.MIT": "licenses/OLLAMA.MIT",
    "third_party/licenses/LLAMA_CPP.MIT": "licenses/LLAMA_CPP.MIT",
    "third_party/licenses/NEURO_SDK.MIT": "licenses/NEURO_SDK.MIT",
}


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 ** 2), b""):
            result.update(chunk)
    return result.hexdigest()


def inputs(root, model_root, executable, libraries):
    files = [(Path(root) / source, target) for source, target in ALLOWED.items()]
    manifest_file = Path(model_root) / MODEL_PATH
    model = json.loads(manifest_file.read_text())
    files.append((manifest_file, str(Path("models") / MODEL_PATH)))
    for item in [model["config"], *model["layers"]]:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", item["digest"]):
            raise ValueError("Digest do modelo fora do contrato.")
        blob = Path(model_root) / "blobs" / item["digest"].replace(":", "-")
        if blob.is_symlink() or blob.stat().st_size != item["size"] or sha(blob) != item["digest"][7:]:
            raise ValueError("Blob do modelo com integridade incorreta.")
        files.append((blob, "models/blobs/" + blob.name))
        if item.get("mediaType") == "application/vnd.ollama.image.license":
            files.append((blob, "licenses/QWEN_MODEL.txt"))
    files.append((Path(executable), "engine/bin/ollama"))
    libraries = Path(libraries).resolve()
    for lib in sorted(libraries.iterdir()):
        # Só arquivos CPU da raiz; os diretórios GPU e libgomp de terceiros ficam fora.
        if lib.name.startswith("libgomp") or lib.is_dir():
            continue
        if not (lib.name.startswith(("libggml", "libllama", "libmtmd")) or lib.name in {"llama-server", "llama-quantize"}):
            continue
        if not lib.resolve().is_relative_to(libraries) or (lib.is_symlink() and Path(os.readlink(lib)).is_absolute()):
            raise ValueError("Biblioteca aponta para fora da árvore CPU.")
        files.append((lib, "engine/lib/ollama/" + lib.name))
    return files


def build(root, destination, *, model_root=None, executable="/usr/local/bin/ollama", libraries="/usr/local/lib/ollama", engine_version="0.32.6"):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    archive = destination.with_suffix(".tar")
    if destination.exists() or archive.exists():
        raise ValueError("Destino já existe; nenhuma entrega será sobrescrita.")
    sources = inputs(root, model_root or root / "compartilhado/modelos/ollama-alistair", executable, libraries)
    size = sum(source.stat().st_size for source, _ in sources if not source.is_symlink())
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < size * 2 + 4 * 1024 ** 3:
        raise RuntimeError("Sem espaço para pasta, tar e reserva de 4 GiB.")
    stage = Path(tempfile.mkdtemp(prefix=".alistair-build-", dir=destination.parent))
    records = {}
    try:
        for source, relative in sources:
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                target.symlink_to(os.readlink(source))
                records[relative] = {"symlink": os.readlink(source)}
            else:
                shutil.copy2(source, target)
                os.chmod(target, 0o755 if relative.endswith(".sh") or relative.startswith("engine/") else 0o644)
                records[relative] = {"sha256": sha(target), "bytes": target.stat().st_size}
        data = {"schema": 1, "package": "alistair_pc2", "engine_version": engine_version,
                "model": "alistair-qwen3.5-4b:latest", "entity_minds_included": False,
                "credentials_included": False, "gpu_libraries_included": False,
                "files": records}
        (stage / "manifesto.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        stage.rename(destination)
        with tarfile.open(archive, "x", format=tarfile.PAX_FORMAT) as output:
            output.add(destination, arcname="alistair_pc2", recursive=True)
        # Confere todos os arquivos do tar sem extrair, inclusive o peso completo.
        with tarfile.open(archive, "r") as bundle:
            for relative, record in records.items():
                member = bundle.getmember("alistair_pc2/" + relative)
                if "symlink" in record:
                    if not member.issym() or member.linkname != record["symlink"]:
                        raise ValueError("Link incorreto no tar.")
                else:
                    digest = hashlib.sha256()
                    with bundle.extractfile(member) as source:
                        for chunk in iter(lambda: source.read(4 * 1024 ** 2), b""):
                            digest.update(chunk)
                    if member.size != record["bytes"] or digest.hexdigest() != record["sha256"]:
                        raise ValueError("Integridade incorreta no tar.")
        return {"folder": str(destination), "archive": str(archive), "archive_bytes": archive.stat().st_size,
                "archive_sha256": sha(archive), "files": len(records), "model_blobs_verified": True,
                "archive_verified": True}
    except BaseException:
        # Preserva artefatos para diagnóstico; não apaga um destino talvez transferido.
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, default=ROOT / "pacotes/alistair_pc2")
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.destino), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
