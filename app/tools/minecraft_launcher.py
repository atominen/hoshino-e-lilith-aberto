"""Gerenciador local do laboratório Minecraft da Hoshino.

Responsabilidade: iniciar/parar o servidor local e a ponte Mineflayer a partir
 da interface principal, para que o teste não dependa de abrir terminais extras.
O bot Mineflayer continua separado do processo principal Python.
"""
from __future__ import annotations

import os
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests
from core import diagnostics
import config

RAIZ = Path(config.RAIZ)
MC_DIR = Path(config.MINECRAFT_DIR)
SERVER_DIR = MC_DIR / "server_1.16.5"
BRIDGE_URL = config.MINECRAFT_BRIDGE_URL
MC_HOST = os.environ.get("HOSHINO_MINECRAFT_HOST", "127.0.0.1")
MC_PORT = int(os.environ.get("HOSHINO_MINECRAFT_PORT", "25565"))
BRIDGE_PROTOCOL_REQUIRED = 3

_server_proc: Optional[subprocess.Popen] = None
_bridge_proc: Optional[subprocess.Popen] = None
_log_handle = None


def _porta_aberta(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _saude_ponte() -> dict | None:
    """Retorna a saúde da ponte, sem confundir resposta HTTP com compatibilidade."""
    try:
        r = requests.get(f"{BRIDGE_URL}/health", timeout=0.7)
        if not r.ok:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except (requests.RequestException, ValueError):
        return None


def ponte_online() -> bool:
    return _saude_ponte() is not None


def ponte_compativel(saude: dict | None = None) -> bool:
    saude = _saude_ponte() if saude is None else saude
    return bool(isinstance(saude, dict) and isinstance(saude.get("protocol"), int)
                and saude["protocol"] >= BRIDGE_PROTOCOL_REQUIRED)


def _descricao_ponte_incompativel(saude: dict | None) -> str:
    protocolo = saude.get("protocol") if isinstance(saude, dict) else None
    recebido = str(protocolo) if protocolo is not None else "não informado"
    return ("ponte Mineflayer ativa, porém incompatível "
            f"(protocolo {recebido}; necessário {BRIDGE_PROTOCOL_REQUIRED}). "
            "Ela não foi encerrada automaticamente porque não foi iniciada por esta sessão. "
            f"Reinicie a ponte existente com {MC_DIR / 'start_bridge.sh'} e tente novamente.")


def estado() -> dict:
    diagnostics.emit("minecraft.launcher.state_check")
    server = _server_proc is not None and _server_proc.poll() is None
    bridge_proprio = _bridge_proc is not None and _bridge_proc.poll() is None
    port = _porta_aberta(MC_HOST, MC_PORT)
    health = _saude_ponte()
    state = health.get("state") if isinstance(health, dict) else {}
    state = state if isinstance(state, dict) else {}
    compativel = ponte_compativel(health)
    conectado = bool(state.get("connected") is True and
                     (state.get("verified") is True or state.get("connectionState") == "ready"))
    return {
        "servidor_processo_da_hoshino": server,
        "servidor_porta": port,
        "ponte_processo_da_hoshino": bridge_proprio,
        "ponte_online": bool(health),
        "ponte_protocolo": health.get("protocol") if health else None,
        "ponte_compativel": compativel,
        "bot_conectado": conectado,
        "server_dir": str(SERVER_DIR),
    }


def _abrir_log():
    global _log_handle
    MC_DIR.mkdir(parents=True, exist_ok=True)
    log = Path(config.RUNTIME_DIR) / "minecraft" / "laboratorio.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    _log_handle = open(log, "a", encoding="utf-8", buffering=1)
    return _log_handle


def _preparado() -> tuple[bool, str]:
    if not (MC_DIR / "node_modules" / "mineflayer").exists():
        return False, f"Mineflayer não está instalado. Execute: npm --prefix {shlex.quote(str(MC_DIR))} install"
    if not (SERVER_DIR / "server.jar").exists():
        return False, "Servidor 1.16.5 ainda não foi baixado. Use o botão/atalho de preparar o laboratório."
    eula = SERVER_DIR / "eula.txt"
    if not eula.exists() or "eula=true" not in eula.read_text(encoding="utf-8", errors="ignore"):
        return False, f"O servidor está preparado, mas o EULA ainda não foi aceito em {eula}."
    if not (SERVER_DIR / "start_server.sh").exists():
        return False, "start_server.sh não existe. Prepare o servidor novamente."
    return True, "ok"


def preparar() -> str:
    diagnostics.emit("minecraft.server.prepare.start")
    """Baixa/prepara o servidor oficial local. A aceitação do EULA continua manual."""
    script = MC_DIR / "prepare_local_server.sh"
    if not script.exists():
        return "Script de preparação do servidor não encontrado."
    try:
        r = subprocess.run(["bash", str(script)], cwd=str(MC_DIR), capture_output=True,
                           text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Falha ao preparar o servidor: {exc}"
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        return saida[-2500:] or f"preparação terminou com código {r.returncode}"
    if "eula=true" not in (SERVER_DIR / "eula.txt").read_text(encoding="utf-8", errors="ignore"):
        return (saida[-1800:] + "\n\nServidor preparado. Aceite o EULA uma vez e depois F11 poderá iniciar tudo automaticamente.").strip()
    return "Servidor Minecraft 1.16.5 preparado."


def iniciar_ponte() -> str:
    """Inicia somente a ponte Mineflayer.

    A ponte também é necessária para entrar em mundo LAN ou servidor remoto;
    portanto não deve depender do servidor local de laboratório estar baixado
    nem de um EULA do servidor que não será usado.
    """
    global _bridge_proc
    from core import ui_policy
    if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'minecraft'):
        return 'ACESSO_BLOQUEADO: Minecraft foi desativado na Central.'
    health = _saude_ponte()
    if health is not None:
        if ponte_compativel(health):
            return "ponte Mineflayer já estava rodando"
        diagnostics.emit("minecraft.bridge.start.incompatible", level="ERROR", health=health)
        return _descricao_ponte_incompativel(health)
    if _bridge_proc is not None and _bridge_proc.poll() is None:
        return 'Ponte própria ainda iniciando ou sem saúde confirmada; nenhuma duplicata foi criada.'
    if not (MC_DIR / "node_modules" / "mineflayer").exists():
        return f"Mineflayer não está instalado. Execute: npm --prefix {shlex.quote(str(MC_DIR))} install"
    log = _abrir_log()
    try:
        _bridge_proc = subprocess.Popen(
            ["bash", str(MC_DIR / "start_bridge.sh")], cwd=str(MC_DIR),
            env={**os.environ, "HOSHINO_RUNTIME_DIR": str(config.RUNTIME_DIR),
                 "HOSHINO_ENTIDADE": config.ENTIDADE_ID,
                 "HOSHINO_MC_BRIDGE_PORT": str(config.MINECRAFT_BRIDGE_PORT)},
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, text=True)
    except OSError as exc:
        return f"falha ao iniciar ponte: {exc}"
    for _ in range(80):
        health = _saude_ponte()
        if ponte_compativel(health):
            diagnostics.emit("minecraft.bridge.start.ready", health=health)
            return "ponte Mineflayer iniciada"
        if _bridge_proc.poll() is not None:
            return f"ponte encerrou. Veja {Path(config.RUNTIME_DIR) / 'minecraft' / 'laboratorio.log'}."
        time.sleep(0.25)
    if health is not None:
        return _descricao_ponte_incompativel(health)
    return f"ponte não respondeu em 20s. Veja {Path(config.RUNTIME_DIR) / 'minecraft' / 'laboratorio.log'}."


def iniciar() -> str:
    global _server_proc, _bridge_proc
    ok, motivo = _preparado()
    if not ok:
        # Primeira execução: tentar preparar automaticamente. A única etapa que
        # continua exigindo ação humana é a aceitação do EULA da Mojang.
        if "Servidor 1.16.5 ainda não foi baixado" in motivo or "start_server.sh" in motivo:
            preparacao = preparar()
            ok, motivo = _preparado()
            if not ok:
                return f"{preparacao}\n{motivo}"
        else:
            return motivo

    diagnostics.emit("minecraft.lab.start")
    mensagens = []
    if not _porta_aberta(MC_HOST, MC_PORT):
        log = _abrir_log()
        try:
            _server_proc = subprocess.Popen(
                ["bash", str(SERVER_DIR / "start_server.sh")],
                cwd=str(SERVER_DIR),
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        except OSError as exc:
            return f"Não consegui iniciar o servidor Minecraft: {exc}"
        for _ in range(120):
            if _porta_aberta(MC_HOST, MC_PORT, 0.2):
                break
            if _server_proc.poll() is not None:
                return f"O servidor Minecraft encerrou antes de abrir a porta. Veja {Path(config.RUNTIME_DIR) / 'minecraft' / 'laboratorio.log'}."
            time.sleep(0.25)
        else:
            return f"O servidor Minecraft não abriu a porta {MC_PORT} a tempo. Veja {Path(config.RUNTIME_DIR) / 'minecraft' / 'laboratorio.log'}."
        mensagens.append("servidor iniciado")
    else:
        mensagens.append("servidor já estava rodando")

    resultado_ponte = iniciar_ponte()
    if resultado_ponte.startswith("ponte Mineflayer"):
        mensagens.append(resultado_ponte)
    else:
        return " + ".join(mensagens + [resultado_ponte])

    resultado = " + ".join(mensagens)
    diagnostics.emit("minecraft.lab.start.end", result=resultado, state=estado())
    return resultado


def parar_ponte_propria() -> bool:
    """Só o Popen criado nesta entidade; nunca encontra processo por porta/nome."""
    global _bridge_proc
    if _bridge_proc is not None and _bridge_proc.poll() is None:
        _bridge_proc.terminate()
        try:
            _bridge_proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            _bridge_proc.kill()
            _bridge_proc.wait(timeout=4)
        diagnostics.emit('minecraft.bridge.owned_stopped', pid=getattr(_bridge_proc, 'pid', None), entity=config.ENTIDADE_ID)
        _bridge_proc = None
        return True
    _bridge_proc = None
    return False


def parar() -> str:
    diagnostics.emit("minecraft.lab.stop.start")
    global _server_proc, _log_handle
    mensagens = ['ponte parada'] if parar_ponte_propria() else []

    if _server_proc is not None and _server_proc.poll() is None:
        try:
            if _server_proc.stdin:
                _server_proc.stdin.write("stop\n")
                _server_proc.stdin.flush()
            _server_proc.wait(timeout=12)
        except Exception:
            _server_proc.terminate()
            try:
                _server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _server_proc.kill()
        mensagens.append("servidor parado")
    _server_proc = None

    if _log_handle is not None:
        try:
            _log_handle.close()
        except OSError:
            pass
        _log_handle = None
    resultado = ", ".join(mensagens) if mensagens else "nenhum processo iniciado pela Hoshino estava rodando"
    diagnostics.emit("minecraft.lab.stop.end", result=resultado)
    return resultado


def abrir_sklauncher() -> str:
    """Tenta abrir uma instalação local do SKLauncher sem exigir caminho fixo."""
    comando = os.environ.get("HOSHINO_SKLAUNCHER_CMD", "").strip()
    candidatos = []
    if comando:
        candidatos.append(comando)
    candidatos += [
        os.path.expanduser("~/Downloads/SKlauncher*.AppImage"),
        os.path.expanduser("~/Applications/SKlauncher*.AppImage"),
        os.path.expanduser("~/.local/bin/sklauncher"),
        os.path.expanduser("~/SKlauncher*.AppImage"),
    ]
    import glob
    for item in candidatos:
        if "*" in item:
            encontrados = sorted(glob.glob(item))
            if encontrados:
                item = encontrados[0]
            else:
                continue
        if os.path.isfile(item) and os.access(item, os.X_OK):
            subprocess.Popen([item], start_new_session=True)
            return f"SKLauncher aberto: {item}"
        if item and os.path.sep not in item:
            from shutil import which
            if which(item):
                subprocess.Popen([item], start_new_session=True)
                return f"SKLauncher aberto: {item}"
    return "Não encontrei o SKLauncher automaticamente. Defina HOSHINO_SKLAUNCHER_CMD no ambiente com o comando/caminho do launcher."
