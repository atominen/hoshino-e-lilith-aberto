"""Painel no PC2 pela rede local (pedido humano 06/11).

O cérebro fica no PC1: entidades, modelos e memórias não saem daqui. O PC2 roda só a janela da Central e
fala com este backend por uma segunda porta, aberta apenas quando a pessoa liga "acesso pela rede" na
Central. A porta local (127.0.0.1) continua como sempre.

- Configuração: ``compartilhado/config/central_rede.json`` (ligado, porta, redes permitidas).
- Código de pareamento: ``compartilhado/runtime/launcher/central_rede.token`` (0600). É fixo entre
  aberturas da Central, ao contrário do token local, para o PC2 não precisar de um novo a cada vez.
  "Gerar novo código" invalida o anterior.
- Só aceita clientes de redes privadas (10/8, 172.16/12, 192.168/16), e só as listadas, se houver lista.
  HTTP simples dentro de uma LAN de confiança, como o executor do PC2 e o do Xbox; não expor à internet.
"""
from __future__ import annotations

import ipaddress
import json
import os
import secrets
import socket
from pathlib import Path

PORT = 8770
CONFIG = 'compartilhado/config/central_rede.json'
TOKEN = 'compartilhado/runtime/launcher/central_rede.token'
PRIVATE = tuple(ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def settings(root) -> dict:
    try:
        data = json.loads((Path(root) / CONFIG).read_text())
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    port = data.get('port', PORT)
    allowed = data.get('allowed', [])
    return dict(enabled=data.get('enabled') is True,
                port=port if type(port) is int and 1024 < port < 65536 else PORT,
                allowed=[str(a) for a in allowed] if isinstance(allowed, list) else [])


def networks(allowed) -> list:
    """Redes aceitas. Vazio = as três faixas privadas. Rede pública ou inválida é recusada."""
    if not allowed:
        return list(PRIVATE)
    out = []
    for item in allowed:
        net = ipaddress.ip_network(str(item).strip(), strict=False)
        if not isinstance(net, ipaddress.IPv4Network) or not any(net.subnet_of(p) for p in PRIVATE):
            raise ValueError(f'{item} não é uma rede local privada.')
        out.append(net)
    return out


def client_allowed(address: str, allowed) -> bool:
    try:
        ip = ipaddress.ip_address(address)
        nets = networks(allowed)
    except ValueError:
        return False
    return any(ip in n for n in nets)


def token(root, *, regenerate=False) -> str:
    path = Path(root) / TOKEN
    path.parent.mkdir(parents=True, exist_ok=True)
    if not regenerate:
        try:
            value = path.read_text().strip()
            if len(value) >= 24:
                return value
        except OSError:
            pass
    value = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        os.fchmod(out.fileno(), 0o600)
        out.write(value)
    return value


def save(root, *, enabled, allowed=None, regenerate=False) -> dict:
    if type(enabled) is not bool:
        raise ValueError('enabled deve ser booleano.')
    current = settings(root)
    allowed = current['allowed'] if allowed is None else allowed
    if not isinstance(allowed, list) or len(allowed) > 16:
        raise ValueError('Lista de redes inválida.')
    networks(allowed)  # valida antes de gravar
    path = Path(root) / CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(enabled=enabled, port=current['port'], allowed=[str(a).strip() for a in allowed])
    temp = path.with_name('.' + path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, path)
    if regenerate or enabled:
        token(root, regenerate=regenerate)
    return data


def addresses() -> list[str]:
    """IPv4 privados desta máquina, para mostrar ao PC2 onde se conectar (rota padrão primeiro)."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('10.255.255.255', 1))  # UDP: nada é enviado, só escolhe a interface
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    out = []
    for ip in found:
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if any(parsed in p for p in PRIVATE) and ip not in out and not ip.startswith('172.17.'):
            out.append(ip)
    return out
