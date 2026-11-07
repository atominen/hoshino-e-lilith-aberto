"""Auditoria somente leitura dos dados preservados na reorganização.

Após voltar a usar a Hoshino, diferenças de hash são esperadas: este comando
confere o snapshot da migração, não julga atualizações posteriores como corrupção.
"""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import config


def main():
    manifesto = json.loads((ROOT / "arquivo/migracao-20261005/dados-verificados.json").read_text())
    diferentes = []
    for item in manifesto.values():
        path = ROOT / item["destino"]
        if not path.is_file():
            diferentes.append(item["destino"])
            continue
        with path.open("rb") as arquivo:
            atual = hashlib.file_digest(arquivo, "sha256").hexdigest()
        if atual != item["sha256"]:
            diferentes.append(item["destino"])
    if diferentes:
        raise RuntimeError(f"{len(diferentes)} arquivo(s) diferem do snapshot: {diferentes}")
    print(f"Hashes preservados: {len(manifesto)} arquivos.")
    for path in (Path(config.DB_PATH), Path(config.VECTOR_DIR) / "chroma.sqlite3",
                 Path(config.RUNTIME_DIR) / "history.sqlite3"):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as banco:
            resultado = banco.execute("PRAGMA quick_check").fetchall()
        if resultado != [("ok",)]:
            raise RuntimeError(f"Banco não íntegro: {path.name}")
        print(f"Banco íntegro (somente leitura): {path.name}")
    quebrados = [str(p.relative_to(ROOT)) for p in (ROOT / "compat").rglob("*")
                 if p.is_symlink() and not p.exists()]
    if quebrados:
        raise RuntimeError(f"Links quebrados: {quebrados}")
    print("Links de compatibilidade válidos.")


if __name__ == "__main__":
    main()
