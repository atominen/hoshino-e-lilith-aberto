"""Shared boundary for files/commands; not confidentiality against the operator.

Unrestricted desktop control is administrative access, not a security sandbox.
"""
from pathlib import Path
import shutil
import config


def foreign_roots():
    root=Path(config.RAIZ).resolve()/'entidades'
    if not root.is_dir():return []
    return [p.resolve() for p in root.iterdir() if p.is_dir() and p.name!=config.ENTIDADE_ID]


def permitted(path):
    target=Path(path).expanduser().resolve()
    return not any(target==p or target.is_relative_to(p) for p in foreign_roots())


def require(path):
    if not permitted(path):raise PermissionError('ACESSO_BLOQUEADO: armazenamento de outra entidade; peça compartilhamento.')
    return Path(path).expanduser().resolve()


def command(argv):
    protected=foreign_roots()
    if not protected:return argv
    binary=shutil.which('bwrap')
    if not binary:raise PermissionError('Isolamento indisponível: comando recusado, sem fallback sem proteção.')
    args=[binary,'--bind','/','/','--unshare-pid','--proc','/proc','--dev','/dev','--die-with-parent']
    for root in protected:args+=['--tmpfs',str(root)]
    return args+['--']+argv
