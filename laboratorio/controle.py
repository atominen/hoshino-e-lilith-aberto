"""Pausa do orquestrador sem parar downloader filho; agenda retomada com PID anti-reuso."""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from .core import Laboratory

EXPECTED = 'automacao_9b_vision_v1_4/orquestrar_9b.py start'


def process_identity(pid: int):
    if not isinstance(pid, int) or pid <= 1:
        raise ValueError('PID inválido')
    proc = Path('/proc') / str(pid)
    command = (proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
    if EXPECTED not in command or proc.stat().st_uid != os.getuid():
        raise PermissionError('PID diferente do orquestrador v1.4 do usuário.')
    stat = (proc/'stat').read_text().rpartition(') ')[2].split()
    # after '(comm) ', stat[0]=field 3; Linux starttime=field 22 => index 19
    return {'pid':pid, 'starttime':str(stat[19]), 'state':stat[0], 'cmd':command[:240]}


def resume_if_same(pid: int, starttime: str):
    ident = process_identity(pid)
    if ident['starttime'] != str(starttime):
        raise RuntimeError('PID reutilizado; SIGCONT recusado.')
    os.kill(pid, signal.SIGCONT)
    return {'resumed':True,'pid':pid}


def schedule(lab: Laboratory, pid: int, at: str):
    """Contrato legado recusado: não manter outro dono do ciclo de vida."""
    raise RuntimeError('Agenda v1.4 aposentada. Use sessão noturna cooperativa do supervisor na Central; não reativar SIGSTOP/9B legado.')
