"""Ficha fixa do PC1, só leitura (07/11, para o revisor de memória conferir afirmações sobre a máquina).

Processador, memória RAM, placa de vídeo e VRAM, sistema e disco. Lê /proc, /sys e ``lspci``; não muda nada.
Não descreve o PC2: dele só existem os sentidos que o painel manda (apps abertos, atividade).
"""
from __future__ import annotations

import math
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def _ler(caminho) -> str:
    try:
        return Path(caminho).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _gib(bytes_):
    return f"{bytes_ / 1024 ** 3:.1f} GiB"


def _placas_de_video() -> list[str]:
    nomes = []
    if shutil.which("lspci"):
        try:
            saida = subprocess.run(["lspci"], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            saida = ""
        for linha in saida.splitlines():
            if re.search(r"VGA compatible|3D controller|Display controller", linha):
                nomes.append(linha.split(": ", 1)[-1].strip())
    vram = []
    for total in sorted(Path("/sys/class/drm").glob("card*/device/mem_info_vram_total")):
        try:
            vram.append(_gib(int(_ler(total).strip())))
        except ValueError:
            continue
    if vram:
        nomes = [f"{n} (VRAM {v})" for n, v in zip(nomes, vram)] + nomes[len(vram):] if nomes else [f"VRAM {v}" for v in vram]
    return nomes


def ficha() -> str:
    linhas = ["Ficha do PC1 (onde roda o cérebro das entidades), lida agora:"]
    cpu = re.search(r"^model name\s*:\s*(.+)$", _ler("/proc/cpuinfo"), re.M)
    linhas.append(f"- Processador: {cpu.group(1).strip() if cpu else platform.processor() or 'desconhecido'}, "
                  f"{os.cpu_count() or '?'} threads")
    mem = re.search(r"^MemTotal:\s*(\d+)\s*kB", _ler("/proc/meminfo"), re.M)
    if mem:
        total = int(mem.group(1)) * 1024
        # O sistema reserva um pouco: 31,2 GiB utilizáveis são 32 GB instalados. 07/11: "pentes de ~32 GB" foi lido
        # pelo 9B como "dois pentes de 32 GB, 64 no total"; a frase agora diz o total.
        nominal = math.ceil(total / 1024 ** 3 / 2) * 2
        linhas.append(f"- Memória RAM: {_gib(total)} utilizáveis, cerca de {nominal} GB instalados no total")
    for placa in _placas_de_video() or ["desconhecida"]:
        linhas.append(f"- Placa de vídeo: {placa}")
    sistema = re.search(r'^PRETTY_NAME="?([^"\n]+)', _ler("/etc/os-release"), re.M)
    linhas.append(f"- Sistema: {sistema.group(1) if sistema else platform.system()}, kernel {platform.release()}")
    try:
        disco = os.statvfs("/")
        linhas.append(f"- Disco do sistema: {_gib(disco.f_blocks * disco.f_frsize)}, livre {_gib(disco.f_bavail * disco.f_frsize)}")
    except OSError:
        pass
    linhas.append(f"- Nome na rede: {platform.node()}")
    return "\n".join(linhas)
