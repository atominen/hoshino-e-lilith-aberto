#!/usr/bin/env python3
"""Remoção única autorizada do Yi reprovado; planejamento é o padrão.

Alvos exatos. Sem prune global, sem tocar outras famílias/dados mentais e sem
backup de pesos descartados. Metadados e relatórios antigos são preservados.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'app')]
DIGEST='abb85e1ac44d9503a94080fde0ff8fc3731bf1c555d6d9d967b501b484bc51de'
CONVERSION='efcc440c45b0123eaaca3b380b8daf545193150e40893fad3e67f5590ec4509b'
MANIFEST='3e9a9905779b5eb9639a4e2fdfff8513b1df2906369432408a539c33df2ea9d2'
ALIASES=(('ollama','hoshino-yi-6b'),('ollama','hoshino-yi-6b-original-efcc440c45b0'),
         ('ollama-lilith','lilith-yi-6b-original-efcc440c45b0'),
         ('ollama','hoshino-recovery-27207e019ef04a7a'))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for data in iter(lambda:source.read(8*1024**2),b''):h.update(data)
    return h.hexdigest()


def safe(path):
    if not path.is_relative_to(ROOT) or path==ROOT:
        raise RuntimeError('Alvo fora do escopo')
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise RuntimeError('Alvo com link simbólico recusado')
    return path


def inventory():
    home=ROOT/'laboratorio-local'
    hf=safe(home/'modelos-extras/yi15-6b/hf')
    if not hf.is_dir():raise RuntimeError('Fonte já ausente; não repetir remoção')
    for f in hf.rglob('*'):safe(f)
    if sum(f.stat().st_size for f in hf.glob('*.safetensors'))!=12122104808:
        raise RuntimeError('Fonte Yi mudou desde o diagnóstico')
    manifests=[]
    blobs=[]
    metadata=[]
    for store,alias in ALIASES:
        p=safe(ROOT/'compartilhado/modelos'/store/'manifests/registry.ollama.ai/library'/alias/'latest')
        if sha(p)!=MANIFEST:raise RuntimeError('Alias mudou; remoção recusada')
        data=json.loads(p.read_text())
        manifests.append(p)
        metadata.append(dict(path=str(p.relative_to(ROOT)),sha256=MANIFEST,manifest=data))
    keep={}
    for store in sorted((ROOT/'compartilhado/modelos').glob('ollama*')):
        if store.is_symlink():raise RuntimeError('Store simbólico recusado')
        if not store.is_dir():continue
        other=[]
        for p in (store/'manifests').rglob('*'):
            if not p.is_file():continue
            safe(p)
            if p in manifests:continue
            data=json.loads(p.read_text())
            refs={x['digest'] for x in [data['config'],*data['layers']]}
            if 'sha256:'+DIGEST in refs:raise RuntimeError('Outro alias ainda referencia o Yi: '+str(p))
            keep[str(p)]=sha(p)
            other.extend(refs)
        if store.name not in ('ollama','ollama-lilith'):continue
        candidate=safe(store/'blobs'/('sha256-'+DIGEST))
        if not candidate.is_file() or candidate.stat().st_size!=3673968736:
            raise RuntimeError('Blob Yi ausente/divergente')
        blobs.append(candidate)
    conversion=safe(home/'controle-laboratorio/treinamento-unificado/conversions/yi-6b'/CONVERSION/'base-q4_k_m.gguf')
    if not conversion.is_file() or conversion.stat().st_size!=3673968736:
        raise RuntimeError('Conversão Yi mudou')
    files=[*hf.rglob('*'),*manifests,*blobs,conversion]
    files=[p for p in files if p.is_file()]
    records=[dict(path=str(p.relative_to(ROOT)),size=p.stat().st_size,allocated=p.stat().st_blocks*512,
                  device=p.stat().st_dev,inode=p.stat().st_ino,nlink=p.stat().st_nlink) for p in files]
    return hf,manifests,blobs,conversion,keep,dict(manifests=metadata,files=records,
        apparent_bytes=sum(r['size'] for r in records),allocated_bytes=sum(r['allocated'] for r in records),
        hf_metadata={p.name:json.loads(p.read_text()) for p in hf.glob('*.json') if p.stat().st_size<65536 and p.name!='tokenizer.json'})


def busy_files(targets):
    """Não imprime comandos nem conteúdo privado: somente PID que usa alvo."""
    current=os.getpid()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==current:continue
        try:maps=(proc/'maps').read_text()
        except (OSError,PermissionError):maps=''
        if any(str(p) in maps for p in targets):raise RuntimeError('Alvo mapeado pelo PID '+proc.name)
        try:handles=list((proc/'fd').iterdir())
        except (OSError,PermissionError):continue
        for fd in handles:
            try:linked=os.readlink(fd)
            except OSError:continue
            if any(linked==str(p) for p in targets):raise RuntimeError('Alvo aberto pelo PID '+proc.name)


def run(apply=False):
    from scripts.verificar_yi_basico import idle
    from core import neural9b_modes as modes
    from core.central_control import atomic_save,revision
    home=ROOT/'laboratorio-local';registry=home/'controle-laboratorio/treinamento-unificado'
    receipt=registry/'reports/remocao-yi-20261024.json'
    with contextlib.ExitStack() as stack:
        for path in (registry/'start.lock',home/'controle-laboratorio/trabalhador.lock',
                     ROOT/'entidades/hoshino/runtime/entity.lock',ROOT/'entidades/lilith/runtime/entity.lock'):
            lock=stack.enter_context(path.open('a+'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(ROOT,home)
        selected=modes.read_document(ROOT)
        for entity in ('hoshino','lilith'):
            if modes.selected_version(ROOT,entity,'yi-6b'):raise RuntimeError('Remova primeiro a seleção Yi')
            cfg=json.loads((ROOT/f'entidades/{entity}/config/executores.json').read_text())
            if 'yi' in str(cfg.get('companion',{})).lower():raise RuntimeError('Catálogo Yi ainda ativo')
            if modes.primary_family(ROOT,entity)!='qwen35-9b':raise RuntimeError('Principal mudou; revisar antes de remover')
        hf,manifests,blobs,conversion,keep,report=inventory()
        targets=[ROOT/r['path'] for r in report['files']]
        busy_files(targets)
        print(json.dumps(dict(apply=apply,files=len(targets),allocated_bytes=report['allocated_bytes'],
            aliases=[str(p.relative_to(ROOT)) for p in manifests]),ensure_ascii=False),flush=True)
        if not apply:return report
        if receipt.exists():raise RuntimeError('Tentativa anterior registrada; reconciliar, não repetir')
        # Só o peso exato já identificado. Nunca coleta/pruna outros blobs.
        for p in [*blobs,conversion]:
            if sha(p)!=DIGEST:raise RuntimeError('Hash do peso mudou; nenhum peso removido')
        report.update(applied=False,phase='authorized_targets_verified',configuration=selected,
            other_manifests=keep,recovery='Redownload da revisão original ou reconversão; pesos não estão no GitHub',
            memory_touched=False,training_started=False)
        atomic_save(receipt,json.dumps(report,ensure_ascii=False,indent=2)+'\n',revision(receipt))
        for record in report['files']:
            p=ROOT/record['path'];s=p.stat()
            if (s.st_dev,s.st_ino,s.st_size)!=(record['device'],record['inode'],record['size']):
                raise RuntimeError('Alvo mudou após inventário; interrompido')
        busy_files(targets)
        for p in [*manifests,*blobs,conversion]:p.unlink()
        shutil.rmtree(hf)  # Diretório HF exato validado, sem links; nunca raiz/broad glob.
        if any(p.exists() for p in targets):raise RuntimeError('Remoção incompleta; reconciliar sem repetir')
        if any(sha(Path(p))!=digest for p,digest in keep.items()):raise RuntimeError('Outro manifesto mudou; investigar')
        idle(ROOT,home)
        report.update(applied=True,phase='removed',remaining_other_manifests_unchanged=True)
        atomic_save(receipt,json.dumps(report,ensure_ascii=False,indent=2)+'\n',revision(receipt))
        print(json.dumps(dict(applied=True,allocated_bytes_removed=report['allocated_bytes'],receipt=str(receipt)),ensure_ascii=False),flush=True)
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true')
    run(parser.parse_args().apply)
