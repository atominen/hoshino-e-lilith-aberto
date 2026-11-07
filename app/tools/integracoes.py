"""Controle seguro dos processos auxiliares da Hoshino.

Somente unidades com nomes fixos podem ser iniciadas ou encerradas aqui. Isso
evita transformar um pedido em chat num executor genérico de systemd e torna o
estado das integrações observável pela interface.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import config
from core import diagnostics

RAIZ = Path(config.RAIZ)
UNIDADE_DISCORD = f"{config.ENTIDADE_ID}-discord.service"
UNIDADE_MINECRAFT = f"{config.ENTIDADE_ID}-minecraft-bridge.service"


def _executar(comando: list[str], timeout: float = 8) -> tuple[int, str]:
    if not shutil.which(comando[0]):
        return 127, f"{comando[0]} não está disponível neste sistema."
    try:
        resultado = subprocess.run(comando, text=True, capture_output=True, timeout=timeout,
                                   cwd=str(RAIZ))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    texto = ((resultado.stdout or "") + (resultado.stderr or "")).strip()
    return resultado.returncode, texto


def _estado_unidade(unidade: str) -> str:
    _, estado = _executar(["systemctl", "--user", "is-active", unidade])
    estado = (estado or "unknown").splitlines()[0].strip().lower()
    return estado if estado in {"active", "inactive", "failed", "activating", "deactivating"} else "unknown"


def _esperar_estado(unidade: str, esperados: set[str], segundos: float = 4.0) -> str:
    limite = time.monotonic() + segundos
    estado = _estado_unidade(unidade)
    while estado not in esperados and time.monotonic() < limite:
        time.sleep(0.12)
        estado = _estado_unidade(unidade)
    return estado


def estado_estruturado() -> dict:
    """Estado mecânico usado pela UI; não depende do texto humano de estado()."""
    discord = _estado_unidade(UNIDADE_DISCORD)
    minecraft = _estado_unidade(UNIDADE_MINECRAFT)
    bot = False
    ponte = {}
    try:
        from tools import minecraft_launcher
        ponte = minecraft_launcher.estado()
        bot = bool(ponte.get("bot_conectado"))
    except Exception:  # noqa: BLE001
        pass
    return {
        "discord": discord,
        "minecraft": minecraft,
        "minecraft_bot_conectado": bot,
        "minecraft_ponte_online": bool(ponte.get("ponte_online")),
    }

def estado() -> str:
    """Resumo local, sem iniciar nada nem expor configuração sensível."""
    discord = _estado_unidade(UNIDADE_DISCORD)
    minecraft = _estado_unidade(UNIDADE_MINECRAFT)
    try:
        from tools import discord as discord_tool
        detalhe_discord = discord_tool.diagnostico()
    except Exception as exc:  # noqa: BLE001
        detalhe_discord = f"diagnóstico Discord indisponível ({type(exc).__name__})"
    try:
        from tools import minecraft_launcher
        ponte = minecraft_launcher.estado()
        detalhe_minecraft = (f"ponte={'online' if ponte.get('ponte_online') else 'offline'}, "
                             f"protocolo={ponte.get('ponte_protocolo')}, "
                             f"bot_conectado={bool(ponte.get('bot_conectado'))}")
    except Exception as exc:  # noqa: BLE001
        detalhe_minecraft = f"ponte Minecraft indisponível ({type(exc).__name__})"
    return (f"Integrações: Discord serviço={discord}; Minecraft serviço={minecraft}.\n"
            f"{detalhe_discord}\nMinecraft: {detalhe_minecraft}")


def _iniciar_unidade(unidade: str, comando: list[str], descricao: str) -> str:
    antes = _estado_unidade(unidade)
    if antes in {"active", "activating"}:
        return f"{descricao} já está em execução ({antes})."
    codigo, saida = _executar([
        "systemd-run", "--user", "--unit", unidade.removesuffix(".service"), "--collect",
        f"--property=WorkingDirectory={RAIZ}", "--service-type=exec",
        f"--setenv=HOSHINO_RUNTIME_DIR={config.RUNTIME_DIR}",
        f"--setenv=HOSHINO_ENTIDADE={config.ENTIDADE_ID}",
        f"--setenv=HOSHINO_MC_BRIDGE_PORT={config.MINECRAFT_BRIDGE_PORT}",
        *comando,
    ])
    if codigo != 0:
        diagnostics.emit("integration.start_failed", level="ERROR", unit=unidade,
                         code=codigo, output=saida[-500:])
        return f"Não consegui iniciar {descricao}: {saida or f'código {codigo}'}."
    depois = _esperar_estado(unidade, {"active", "failed", "inactive"})
    if depois == "active":
        diagnostics.emit("integration.started", unit=unidade)
        return f"{descricao} iniciado com segurança e confirmado ativo."
    diagnostics.emit("integration.start_unhealthy", level="ERROR", unit=unidade,
                     state=depois, output=saida[-500:])
    return (f"{descricao} foi solicitado, mas não ficou ativo (estado {depois}). "
            "Consulte o diagnóstico para ver o motivo.")


def iniciar_discord() -> str:
    """Valida a configuração local e inicia o adaptador Discord conhecido."""
    from core import ui_policy
    if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
        return 'ACESSO_BLOQUEADO: Discord foi desativado na Central.'
    try:
        from integracoes.discord_env import carregar
        valores, avisos = carregar(str(Path(config.RUNTIME_DIR) / "discord.env"))
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui validar a configuração Discord da entidade: {type(exc).__name__}."
    if not valores.get("HOSHINO_DISCORD_TOKEN", "").strip():
        return f"Discord não foi iniciado: falta HOSHINO_DISCORD_TOKEN em {Path(config.RUNTIME_DIR) / 'discord.env'}."
    if avisos:
        diagnostics.emit("integration.discord_env_warnings", warnings=len(avisos))
    return _iniciar_unidade(UNIDADE_DISCORD, [str(RAIZ / "iniciar_discord.sh")], f"Discord de {config.ENTIDADE_NOME}")


def iniciar_minecraft() -> str:
    """Inicia ponte e abre o launcher conhecido; não entra num mundo sozinho."""
    minecraft_dir = Path(config.MINECRAFT_DIR)
    script = minecraft_dir / "start_bridge.sh"
    if not script.is_file():
        return f"Minecraft não foi iniciado: {script} não existe."
    if not (minecraft_dir / "node_modules" / "mineflayer").exists():
        return "Minecraft não foi iniciado: Mineflayer ainda não está instalado."
    resultado_ponte = _iniciar_unidade(
        UNIDADE_MINECRAFT, ["bash", str(script)], f"ponte Minecraft de {config.ENTIDADE_NOME}")
    # A ponte é a capacidade da Hoshino dentro do jogo; o launcher abre a
    # interface do jogo para a pessoa sem usar shell arbitrário.
    if "confirmado ativo" not in resultado_ponte:
        return resultado_ponte
    try:
        from tools import minecraft_launcher
        resultado_launcher = minecraft_launcher.abrir_sklauncher()
    except Exception as exc:  # noqa: BLE001
        resultado_launcher = f"não consegui abrir o launcher ({type(exc).__name__})"
    return f"{resultado_ponte} {resultado_launcher}"


def encerrar_discord() -> str:
    return _encerrar_unidade(UNIDADE_DISCORD, f"Discord de {config.ENTIDADE_NOME}")


def encerrar_minecraft() -> str:
    # Tenta uma saída limpa do bot antes de encerrar o processo da ponte.
    try:
        from tools import minecraft
        minecraft.desconectar()
    except Exception:  # noqa: BLE001
        pass
    return _encerrar_unidade(UNIDADE_MINECRAFT, f"ponte Minecraft de {config.ENTIDADE_NOME}")


def _encerrar_unidade(unidade: str, descricao: str) -> str:
    antes = _estado_unidade(unidade)
    if antes in {"inactive", "failed", "unknown"}:
        return f"{descricao} já estava parado ({antes})."
    codigo, saida = _executar(["systemctl", "--user", "stop", unidade])
    depois = _esperar_estado(unidade, {"inactive", "failed", "unknown"})
    if codigo == 0 and depois in {"inactive", "unknown"}:
        diagnostics.emit("integration.stopped", unit=unidade)
        return f"{descricao} encerrou com segurança."
    diagnostics.emit("integration.stop_failed", level="ERROR", unit=unidade,
                     state=depois, code=codigo, output=saida[-500:])
    return f"Não consegui confirmar o encerramento de {descricao} (estado {depois})."
