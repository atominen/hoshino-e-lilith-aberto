#!/usr/bin/env python3
"""Instalador local simples. Planeja primeiro; nunca inicia entidade ou modelo.

PC2 usa o pacote CPU/modelo 4B existente, fora do Git. A instalação conserva
staging quando falha e recusa sobrescrever destino ou extrair caminhos estranhos.
"""
import argparse
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
GIB = 1024**3
DEPS = {'pc2': ('python3', 'libgomp1'),
        'principal': ('python3-venv', 'python3-pyqt5', 'libportaudio2', 'ffmpeg', 'pulseaudio-utils', 'xdotool', 'wmctrl', 'xclip')}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024**2), b''): h.update(chunk)
    return h.hexdigest()


def plan(profile, destination, package=None):
    destination = Path(destination).absolute()
    anchor = destination
    while not anchor.exists(): anchor = anchor.parent
    result = dict(profile=profile, destination=str(destination),
                  free_bytes=shutil.disk_usage(anchor).free, reserve_bytes=4*GIB,
                  system_packages=DEPS[profile], cloud=False, new_models=False, auto_start=False)
    if profile == 'pc2':
        if not hasattr(tarfile,'data_filter'):raise ValueError('Atualize o Python do Mint: filtro seguro de extração ausente; não extraio sem proteção.')
        if not package or not Path(package).is_file(): raise ValueError('Informe --pacote com alistair_pc2.tar, transferido do PC principal.')
        with tarfile.open(package) as archive:
            members = archive.getmembers()
            validate_members(members)
            size = sum(m.size for m in members if m.isfile())
        result.update(package=str(Path(package).absolute()), unpacked_bytes=size, required_bytes=size+4*GIB)
        if result['free_bytes'] < result['required_bytes']: raise OSError('Sem espaço para instalar mantendo 4 GiB de reserva.')
    else:
        result.update(existing_models_only=True, model_install='importe os pesos existentes pela central; nenhum download implícito',
                      fresh_install_complete=False)
    return result


def validate_members(members):
    seen = set()
    for member in members:
        p = PurePosixPath(member.name)
        if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != 'alistair_pc2' or member.name in seen:
            raise ValueError('Pacote contém caminho inválido/duplicado.')
        seen.add(member.name)
        if not (member.isfile() or member.isdir() or member.issym()):
            raise ValueError('Pacote contém dispositivo, hardlink ou entrada não suportada.')
        if member.issym():
            link = PurePosixPath(member.linkname)
            if link.is_absolute() or '..' in link.parts or len(p.parts) < 2:
                raise ValueError('Link simbólico fora do contrato CPU.')
    links = {m.name for m in members if m.issym()}
    if any(any(str(parent) in links for parent in PurePosixPath(m.name).parents) for m in members):
        raise ValueError('Extração através de link simbólico recusada.')


def move_without_replace(source, destination):
    """Publicação atômica Linux: nem uma corrida pode sobrescrever o destino."""
    if platform.system() != 'Linux':
        raise ValueError('Publicação segura deste instalador requer Linux.')
    rename = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
    if rename is None:
        raise ValueError('renameat2 indisponível; staging preservado, sem sobrescrever.')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST: raise ValueError('Destino já existe; não sobrescrevo.')
        raise OSError(code, os.strerror(code), str(destination))


def install_pc2(destination, package, sha256):
    destination, package = Path(destination).absolute(), Path(package).resolve()
    if destination.exists() or destination.is_symlink(): raise ValueError('Destino existente: não sobrescrevo uma instalação.')
    if not __import__('re').fullmatch('[a-f0-9]{64}', sha256 or ''): raise ValueError('Informe SHA-256 confiável do pacote, obtido no PC principal.')
    if digest(package) != sha256: raise ValueError('SHA-256 do pacote diverge; nada instalado.')
    report = plan('pc2', destination, package)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.alistair-install-', dir=destination.parent))
    try:
        with tarfile.open(package) as archive:
            validate_members(archive.getmembers())
            archive.extractall(stage, filter='data')
        package_root = stage/'alistair_pc2'
        # Verificador é o código do checkout, não código recebido no pacote.
        spec = importlib.util.spec_from_file_location('pc2_integrity', ROOT/'pc2/verificar_pc2.py')
        verify = importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
        manifest = verify.verify(package_root)
        if (manifest.get('package')!='alistair_pc2' or manifest.get('model')!='alistair-qwen3-4b:latest' or
                manifest.get('credentials_included') is not False or manifest.get('entity_minds_included') is not False):
            raise ValueError('Pacote fora do contrato: CPU 4B, sem mente/credenciais.')
        # rename não pode substituir destino criado por outra instalação.
        if destination.exists() or destination.is_symlink(): raise ValueError('Destino mudou durante a instalação.')
        # Um lock cooperativo resolve dois instaladores deste projeto.
        import fcntl
        with (destination.parent/('.'+destination.name+'.install.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if destination.exists() or destination.is_symlink(): raise ValueError('Destino já instalado.')
            move_without_replace(package_root, destination)
        report.update(installed=True, integrity_verified=True, staging=str(stage),
                      next_step='bash '+str(destination/'iniciar.sh'), hardware_validated=False)
        return report
    except BaseException:
        print('Instalação não concluída. Staging preservado para revisão: '+str(stage), file=sys.stderr)
        raise


def dependencies(profile):
    if platform.system()!='Linux' or not shutil.which('apt-get'): raise ValueError('Instalação automática de dependências requer Linux Mint/Debian apt-get.')
    # Lista fechada. Não lê senha; sudo interativo pertence ao terminal do usuário.
    subprocess.run(['sudo', 'apt-get', 'install', '--', *DEPS[profile]], check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--perfil', choices=DEPS);parser.add_argument('--destino', type=Path)
    parser.add_argument('--pacote', type=Path);parser.add_argument('--sha256')
    parser.add_argument('--aplicar', action='store_true');parser.add_argument('--dependencias', action='store_true')
    args=parser.parse_args()
    if not args.perfil:
        print('Hoshino / Lilith / Alistair — instalação privada\n1. PC2 (executor CPU)\n2. PC principal (dependências / diagnóstico)')
        args.perfil='pc2' if input('Escolha [1/2]: ').strip()=='1' else 'principal'
        if args.perfil=='pc2':
            args.pacote=Path(input('Caminho de alistair_pc2.tar: ').strip())
            args.sha256=input('SHA-256 recebido do PC principal: ').strip()
    destination=args.destino or (Path.home()/'alistair_pc2' if args.perfil=='pc2' else ROOT)
    print(json.dumps(plan(args.perfil,destination,args.pacote),ensure_ascii=False,indent=2))
    if not args.aplicar:
        print('Somente planejamento. Use --aplicar explicitamente; nenhum download ou serviço iniciou.')
        return
    if args.dependencias: dependencies(args.perfil)
    if args.perfil=='pc2': print(json.dumps(install_pc2(destination,args.pacote,args.sha256),ensure_ascii=False,indent=2))
    else:
        venv=ROOT/'compartilhado/ambientes/principal'
        if not (venv/'bin/python').is_file(): subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
        subprocess.run([str(venv/'bin/python'),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
        print('Dependências preparadas. Modelos/identidades existentes preservados; instalação nova completa exige importação e verificação separadas.')


if __name__=='__main__':
    try: main()
    except (ValueError,OSError,subprocess.SubprocessError,tarfile.TarError) as exc:
        print('Não instalado: '+str(exc),file=sys.stderr);sys.exit(1)
