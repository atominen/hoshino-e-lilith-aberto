"""Migração pontual auditável da árvore de 05/10/2026. Não inicia a aplicação.

Move diretórios no mesmo filesystem (sem copiar os modelos), recusa colisões,
confere hashes dos dados pessoais e deixa aliases para caminhos históricos.
Não é um comando de limpeza nem um instalador para executar novamente.
"""
from pathlib import Path
import hashlib
import json
import os
import sys

ORIGEM = Path("/home/gustavo/hoshino")
DESTINO = Path("/home/gustavo/hoshino e lilith")
REGISTRO = Path("arquivo/migracao-20261005/movimentos.json")
movimentos = []


def assinatura(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def mover(src, dst):
    src, dst = ORIGEM / src, ORIGEM / dst
    if not src.exists():
        raise FileNotFoundError(src)
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    movimentos.append({"origem": str(src.relative_to(ORIGEM)),
                       "destino": str(dst.relative_to(ORIGEM))})
    registro = ORIGEM / REGISTRO
    registro.parent.mkdir(parents=True, exist_ok=True)
    registro.write_text(json.dumps(movimentos, indent=2, ensure_ascii=False) + "\n")


def link(alvo, nome):
    alvo, nome = ORIGEM / alvo, ORIGEM / nome
    nome.parent.mkdir(parents=True, exist_ok=True)
    nome.symlink_to(os.path.relpath(alvo, nome.parent), target_is_directory=alvo.is_dir())


def main():
    if ORIGEM.is_symlink() or DESTINO.exists():
        raise RuntimeError("Migração já aplicada ou destino ocupado; nenhuma ação realizada.")
    obrigatorios = ["main.py", "config.py", "entity_paths.py", "identity/self_model.json",
                    "memory/sqlite/hoshino.db", "runtime/history.sqlite3",
                    "venv/bin/python", "scripts/ambiente.sh"]
    for rel in obrigatorios:
        if not (ORIGEM / rel).exists():
            raise FileNotFoundError(rel)

    # Algum import diagnóstico durante a preparação pode ter criado o runtime
    # novo antes da migração. Preservá-lo separadamente evita sobrescrever o
    # histórico original ou confundir esses eventos com a continuidade anterior.
    for rel, nome in (("entidades/hoshino/runtime", "runtime-da-preparacao"),
                      ("compartilhado/runtime/gpu_resource.lock", "gpu-lock-da-preparacao")):
        if (ORIGEM / rel).exists():
            mover(rel, Path("arquivo/migracao-20261005") / nome)

    # Hashes antes de mover: identidade, memória e estado persistente, incluindo
    # credenciais. O relatório contém somente hashes, nunca conteúdo desses arquivos.
    hashes = {}
    for nome in ("identity", "memory/sqlite", "memory/vector/db", "runtime"):
        for pasta, dirs, files in os.walk(ORIGEM / nome):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", "models", "stable-diffusion.cpp"}]
            for arquivo in files:
                p = Path(pasta) / arquivo
                if p.is_symlink() or p.suffix in {".py", ".pyc"} or ".bak" in p.name:
                    continue
                if p.is_file():
                    hashes[str(p.relative_to(ORIGEM))] = assinatura(p)

    # Artefatos de versões anteriores saem do código ativo, mas são preservados.
    for base in ("core", "social", "memory/sqlite", "testes"):
        for p in sorted((ORIGEM / base).glob("*.bak*")):
            rel = p.relative_to(ORIGEM)
            mover(rel, Path("arquivo/legado-20261005") / rel)
    for nome in ("main.py.v17.bak", "mudancas.patch", "MANIFEST.sha256"):
        if (ORIGEM / nome).exists():
            mover(nome, Path("arquivo/legado-20261005") / nome)
    for nome in ("test_diagnostico.py", "test_v24_estabilidade.py"):
        if (ORIGEM / nome).exists():
            mover(nome, Path("arquivo/legado-20261005/testes-raiz") / nome)

    mover("models", "compartilhado/modelos")
    for p in sorted((ORIGEM / "runtime/models").iterdir()):
        mover(p.relative_to(ORIGEM), Path("compartilhado/modelos") / p.name)
    (ORIGEM / "runtime/models").rmdir()
    mover("runtime/stable-diffusion.cpp", "compartilhado/servicos/stable-diffusion.cpp")
    mover("minecraft", "compartilhado/servicos/minecraft")
    mover("venv", "compartilhado/ambientes/principal")
    mover("venv-voz", "compartilhado/ambientes/voz")
    for nome in ("ollama", "ollama.log", "ollama.pid", "gpu_resource.lock"):
        if (ORIGEM / "runtime" / nome).exists():
            mover(Path("runtime") / nome, Path("compartilhado/runtime") / nome)

    hoshino = Path("entidades/hoshino")
    for nome in ("identity", "runtime", "workspace", "config"):
        mover(nome, hoshino / nome)
    for nome in ("episodes", "procedures", "vector/db"):
        mover(Path("memory") / nome, hoshino / "memory" / nome)
    for p in sorted((ORIGEM / "memory/sqlite").iterdir()):
        if p.is_file() and p.suffix != ".py":
            mover(p.relative_to(ORIGEM), hoshino / "memory/sqlite" / p.name)

    for nome in ("main.py", "config.py", "entity_paths.py", "core", "mind", "tools",
                 "social", "play", "integracoes", "memory"):
        mover(nome, Path("app") / nome)
    if (ORIGEM / "__pycache__").exists():
        mover("__pycache__", "arquivo/legado-20261005/cache-raiz")

    for nome in ("identity", "memory", "runtime", "workspace", "config"):
        (ORIGEM / "entidades/lilith" / nome).mkdir(parents=True, exist_ok=True)

    # Compatibilidade fora da árvore canônica de dados. Preserva shebangs dos
    # venvs, referências persistidas e caminhos de build sem duplicar arquivos.
    compat = Path("compat/hoshino")
    for nome in ("main.py", "config.py", "entity_paths.py", "core", "mind", "tools",
                 "social", "play", "integracoes"):
        link(Path("app") / nome, compat / nome)
    for nome in ("identity", "workspace", "config"):
        link(hoshino / nome, compat / nome)
    for nome, alvo in {"models": "compartilhado/modelos", "venv": "compartilhado/ambientes/principal",
                       "venv-voz": "compartilhado/ambientes/voz", "minecraft": "compartilhado/servicos/minecraft"}.items():
        link(alvo, compat / nome)
    for nome in ("scripts", "desktop", "docs", "testes", "README.md", "requirements.txt",
                 "requirements-hoshino-v32-extra.txt", "iniciar_hoshino.sh", "iniciar_discord.sh",
                 "iniciar_minecraft_hoshino.sh", "rodar_testes.sh"):
        link(nome, compat / nome)
    for p in (ORIGEM / hoshino / "runtime").iterdir():
        link(p.relative_to(ORIGEM), compat / "runtime" / p.name)
    link("compartilhado/modelos", compat / "runtime/models")
    link("compartilhado/servicos/stable-diffusion.cpp", compat / "runtime/stable-diffusion.cpp")
    for p in (ORIGEM / "compartilhado/runtime").iterdir():
        link(p.relative_to(ORIGEM), compat / "runtime" / p.name)
    for base in ("memory", "memory/sqlite", "memory/vector"):
        for p in (ORIGEM / "app" / base).iterdir():
            if not p.is_dir() or p.name == "__pycache__":
                link(p.relative_to(ORIGEM), compat / base / p.name)
        for p in (ORIGEM / hoshino / base).iterdir():
            if p.name not in {"sqlite", "vector"}:
                link(p.relative_to(ORIGEM), compat / base / p.name)

    mapeamento = {}
    for rel, esperado in hashes.items():
        destino = Path(rel)
        for movimento in movimentos:
            origem = Path(movimento["origem"])
            if destino == origem or destino.is_relative_to(origem):
                destino = Path(movimento["destino"]) / destino.relative_to(origem)
        atual = assinatura(ORIGEM / destino)
        if atual != esperado:
            raise RuntimeError(f"Dados mudaram durante a migração: {rel}")
        mapeamento[rel] = {"destino": str(destino), "sha256": atual}
    (ORIGEM / "arquivo/migracao-20261005/dados-verificados.json").write_text(
        json.dumps(mapeamento, indent=2, ensure_ascii=False) + "\n")

    # Renomeia somente após validar os dados e construir os aliases relativos.
    ORIGEM.rename(DESTINO)
    ORIGEM.symlink_to(DESTINO / compat, target_is_directory=True)
    print(f"Migração concluída: {DESTINO}; {len(movimentos)} movimentos; {len(hashes)} arquivos de dados verificados.")


if __name__ == "__main__":
    main()
