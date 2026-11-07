#!/usr/bin/env python3
"""Configura somente o executor instalado; não abre serviços nem imprime chaves."""
import argparse
import json
import os
import secrets
from pathlib import Path
import pc2_protocol as protocol


def save(path, value):
    # Arquivo novo e exclusivo; configuração existente nunca é sobrescrita.
    with path.open("x", encoding="utf-8") as output:
        os.chmod(path, 0o600)
        output.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def configure(root, bind, main_ip):
    root = Path(root)
    bind, main_ip = protocol.lan_ip(bind), protocol.lan_ip(main_ip)
    if bind.startswith("127.") or main_ip.startswith("127.") or bind == main_ip:
        raise ValueError("Informe dois IPs LAN diferentes: PC2 e PC principal.")
    if (root / "worker.json").exists() or (root / "lan.key").exists() or (root / "pareamento").exists():
        raise ValueError("Já existe configuração; preserve a chave e reveja-a antes de mudar os IPs.")
    secret = secrets.token_hex(32)
    with (root / "lan.key").open("x") as output:
        os.chmod(root / "lan.key", 0o600)
        output.write(secret + "\n")
    pair = root / "pareamento"
    pair.mkdir(mode=0o700)
    with (pair / "lan.key").open("x") as output:
        os.chmod(pair / "lan.key", 0o600)
        output.write(secret + "\n")
    save(pair / "conexao.json", {"url": f"http://{bind}:8770", "key_file": "lan.key"})
    save(root / "worker.json", {"configured": True, "bind": bind, "port": 8770,
         "ollama_port": 11438, "allowed_clients": [main_ip], "token_file": "lan.key"})
    return pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pc2-ip")
    parser.add_argument("--principal-ip")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    pair = configure(root, args.pc2_ip or input("IP LAN deste segundo PC: ").strip(),
                     args.principal_ip or input("IP LAN do PC principal: ").strip())
    print("Configurado. Copie somente a pasta pareamento para o PC principal.")
    print("A chave não foi exibida. Nenhum servidor foi iniciado.")


if __name__ == "__main__":
    main()
