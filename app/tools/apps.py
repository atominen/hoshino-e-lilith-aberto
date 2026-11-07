"""Descoberta, instalação e abertura de aplicativos Linux.

Instalações passam pelo terminal existente para reaproveitar suas regras de
confirmação. A preferência para aplicativos de usuário é Flatpak --user quando
há um ID conhecido; para ferramentas de IA da oficina, usa-se o venv isolado.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import shlex
from pathlib import Path

from core import bd
from tools import terminal, workspace

ALIAS = {
    "spotify": "com.spotify.Client",
    "discord": "com.discordapp.Discord",
    "steam": "com.valvesoftware.Steam",
    "vlc": "org.videolan.VLC",
    "obs": "com.obsproject.Studio",
    "gimp": "org.gimp.GIMP",
    "krita": "org.kde.krita",
}


def _registrar(app_id: str, nome: str, escopo: str) -> None:
    try:
        bd.executar(
            "CREATE TABLE IF NOT EXISTS app_registry (id TEXT PRIMARY KEY, nome TEXT, escopo TEXT, "
            "origem TEXT, criado_em TEXT, atualizado_em TEXT)"
        )
        agora = bd.agora()
        bd.executar(
            "INSERT OR REPLACE INTO app_registry(id,nome,escopo,origem,criado_em,atualizado_em) VALUES(?,?,?,?,COALESCE((SELECT criado_em FROM app_registry WHERE id=?),?),?)",
            (app_id, nome, escopo, "flatpak", app_id, agora, agora)
        )
    except Exception:
        pass


def procurar(nome: str) -> str:
    termo = (nome or "").strip()
    if not termo:
        return "Erro: informe o nome do aplicativo."
    partes = []
    if shutil.which("flatpak"):
        p = subprocess.run(["flatpak", "search", termo], capture_output=True, text=True)
        if p.stdout.strip():
            partes.append("Flatpak:\n" + "\n".join(p.stdout.strip().splitlines()[:25]))
    if shutil.which("apt-cache"):
        p = subprocess.run(["apt-cache", "search", termo], capture_output=True, text=True)
        if p.stdout.strip():
            partes.append("APT:\n" + "\n".join(p.stdout.strip().splitlines()[:20]))
    if not partes:
        return f"Não consegui pesquisar aplicativos para '{termo}'."
    return "\n\n".join(partes)


def instalar(nome: str, destino: str = "usuario", origem: str = "auto") -> str:
    termo = (nome or "").strip()
    destino = (destino or "usuario").lower()
    origem = (origem or "auto").lower()
    if not termo:
        return "Erro: informe o aplicativo."

    if destino == "hoshino":
        return workspace.instalar_pacote_ia(termo)
    if destino == "oficina":
        return workspace.instalar_pacote(termo)

    if origem in ("flatpak", "auto") and shutil.which("flatpak"):
        app_id = ALIAS.get(termo.lower(), termo if "." in termo else "")
        if app_id:
            comando = f"flatpak install --user -y flathub {app_id}"
        else:
            # O Flatpak CLI permite resolver nomes pesquisáveis; sem ID exato isso
            # pode apresentar escolha ao usuário. Deixamos o terminal fazer a
            # confirmação se o backend pedir uma ação privilegiada.
            comando = f"flatpak install --user {shlex.quote(termo)}"
        resultado = terminal.execute_command(comando, ambiente="sistema", confirmado=False)
        if "código" not in resultado.lower() and not resultado.startswith("CONFIRMACAO"):
            _registrar(app_id or termo, termo, destino)
        return resultado

    if shutil.which("apt-get"):
        # apt é usado só com o nome exato fornecido. A proteção de risco do terminal
        # exigirá aprovação por F8 antes do sudo.
        comando = f"sudo apt-get install -y {shlex.quote(termo)}"
        return terminal.execute_command(comando, ambiente="sistema", confirmado=False)

    return "Não encontrei um gerenciador de aplicativos disponível (flatpak/apt)."


def listar_instalados() -> str:
    partes = []
    if shutil.which("flatpak"):
        p = subprocess.run(["flatpak", "list", "--app"], capture_output=True, text=True)
        if p.stdout.strip():
            partes.append("Flatpak:\n" + p.stdout.strip())
    if shutil.which("dpkg-query"):
        p = subprocess.run(["dpkg-query", "-W", "-f=${binary:Package}\n"],
                           capture_output=True, text=True)
        if p.stdout.strip():
            partes.append("APT/DPKG (amostra):\n" + "\n".join(p.stdout.strip().splitlines()[:120]))
    return "\n\n".join(partes) if partes else "Não consegui listar aplicativos."


def abrir(nome: str, argumentos: str = "") -> str:
    from tools import desktop
    return desktop.abrir_aplicativo(nome, argumentos)
