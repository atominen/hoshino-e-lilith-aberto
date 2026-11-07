#!/usr/bin/env python3
"""Verifica PC2 e habilita só o backend textual de Alistair, por escolha explícita."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from core.alistair_backend import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pareamento", type=Path)
    parser.add_argument("--habilitar", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    pair = args.pareamento.resolve()
    settings = json.loads((pair / "conexao.json").read_text())
    key = (pair / "lan.key").resolve()
    if not key.is_relative_to(pair) or key.stat().st_mode & 0o077:
        raise ValueError("Preserve a pasta de pareamento e a permissão 600 da chave.")
    client = Client(settings["url"], bytes.fromhex(key.read_text().strip()))
    if not client.ready():
        raise RuntimeError("PC2/modelo ainda não está disponível; configuração não alterada.")
    print("Executor LAN validado; modelo disponível, ferramentas continuam no PC principal.")
    if args.benchmark:
        sys.path.insert(0, str(ROOT / "pc2"))
        from benchmark_pc2 import benchmark
        benchmark(client)
    if args.habilitar:
        path = ROOT / "compartilhado/config/alistair_pc2.json"
        temporary = path.with_suffix(".json.pending")
        with temporary.open("x") as output:
            os.chmod(temporary, 0o600)
            json.dump({"enabled": True, "url": settings["url"], "key_file": str(key)}, output, indent=2)
        temporary.replace(path)
        print("Backend habilitado. Reinicie Alistair pela central para aplicar; Hoshino/Lilith não mudam.")
    else:
        print("Somente verificação; execução remota continua desativada.")


if __name__ == "__main__":
    main()
