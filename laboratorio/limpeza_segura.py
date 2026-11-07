#!/usr/bin/env python3
"""Inventário conservador. Só apaga parcial exato após conferir SHA completo do 9B.
Nunca remove modelos distintos, identidade, memória, backups ou datasets.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
import shutil
from pathlib import Path
from datetime import datetime, timezone

SHA9 = '95117c3faed067c2a48dd3ddebf16209c4c6b60d1714ef5dd32cf784e2e053fc'
SIZE9 = 18_819_721_632
LAB_DEFAULT = Path.home() / 'laboratorio-lora'
EXTRAS = ('modelos-extras/yi15-6b','modelos-extras/hunyuan-7b','modelos-extras/alistair-qwen35-4b',
          'modelos/qwen2.5-7b-hf-local','modelos/qwen2.5-7b-local','modelos/qwen3.5-0.8b',
          'professor-27b','professor-moe-35b')


def project_caches(project,*,apply=False):
    """Só caches descartáveis de código; nunca modelos, datasets ou RAM/KV."""
    project=Path(project).resolve();names={'__pycache__','.pytest_cache','.ruff_cache','.mypy_cache'};found=[]
    for area in ('app','laboratorio','scripts','testes'):
        root=project/area
        if root.is_symlink():raise ValueError('Área do projeto por link recusada')
        if not root.is_dir():continue
        for base,dirs,_ in os.walk(root,followlinks=False):
            for name in list(dirs):
                path=Path(base)/name
                if path.is_symlink():dirs.remove(name);continue
                if name in names:
                    if not path.resolve().is_relative_to(root):raise ValueError('Cache fora da área permitida')
                    found.append(dict(path=str(path),bytes=allocated(path)));dirs.remove(name)
    if apply:
        for row in found:
            path=Path(row['path'])
            if path.is_symlink() or path.name not in names or not path.resolve().is_relative_to(project):
                raise RuntimeError('Destino de cache mudou; exclusão recusada')
            shutil.rmtree(path)
    return dict(applied=apply,caches=found,bytes=sum(r['bytes'] for r in found),
                recovery='Regeneráveis pelo Python/ferramentas; nenhum peso ou dado de treino removido')

def hash_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def active_download():
    # Deliberately overblock on any HF downloader/9B repair; never kill PIDs.
    for d in Path('/proc').iterdir():
        if not d.name.isdigit() or int(d.name)==os.getpid(): continue
        try:
            cmd=(d/'cmdline').read_bytes().decode('utf-8','replace').replace('\0',' ')
        except (OSError,PermissionError):continue
        if not cmd:continue
        if ('retomar_9b_parcial.py' in cmd or 'baixar_9b.py' in cmd or
             ('huggingface' in cmd.lower() and 'download' in cmd.lower())):
            return f'{d.name}: {cmd[:250]}'
    return None

def allocated(p):
    if p.is_symlink():return 0
    if p.is_file():return p.stat().st_blocks*512
    if not p.is_dir():return 0
    s=0
    for base, dirs, files in os.walk(p,followlinks=False):
        for name in files:
            q=Path(base)/name
            try:
                if not q.is_symlink():s+=q.stat().st_blocks*512
            except OSError: pass
        dirs[:]=[x for x in dirs if not (Path(base)/x).is_symlink()]
    return s

def get_cleanup_candidates(lab):
    cache=lab/'modelos/qwen3.5-9b-uncensored-hf/.cache/huggingface/download'
    if cache.is_symlink():raise RuntimeError('Cache com symlink: limpeza bloqueada')
    result=[]
    if cache.is_dir():
        for p in sorted(cache.glob('*.incomplete')):
            if p.is_symlink() or not p.is_file():continue
            if re.search(r'\.'+SHA9+r'\.[a-zA-Z0-9]+\.incomplete$',p.name):
                result.append(p)
    return result

def report(lab):
    base=lab/'modelos/qwen3.5-9b-uncensored-hf'
    full=base/'model.safetensors'
    candidates=get_cleanup_candidates(lab)
    mods={x:dict(exists=(lab/x).exists(),bytes_allocated=allocated(lab/x)) for x in EXTRAS}
    pairs=[]
    v2,v3=lab/'pacote_neural_v2',lab/'pacote_neural_v3'
    if v2.is_dir() and v3.is_dir():
        for p in sorted(v2.iterdir()):
            q=v3/p.name
            if p.is_file() and q.is_file() and not p.is_symlink() and not q.is_symlink() and p.stat().st_size==q.stat().st_size:
                if p.stat().st_size<=20*1024*1024 and hash_file(p)==hash_file(q):pairs.append(p.name)
    return dict(created=datetime.now(timezone.utc).isoformat(),read_only=True,
                final_9b_exists=full.is_file(),final_9b_bytes=full.stat().st_size if full.is_file() else 0,
                hash_verified=False, # NEVER claim hash without checking it at cleanup time.
                candidate_partials=[dict(path=str(p),bytes=p.stat().st_size) for p in candidates],
                active_download=active_download(),models_preserved=mods,
                identical_v2_v3_filenames=pairs,
                note='Arquivos idênticos entre v2/v3 NÃO serão apagados: dependências ainda desconhecidas. Todo modelo é preservado.')

def clean(lab, confirmation):
    # Defensive: no directory deletion. Exact paths only.
    if confirmation!='APAGAR_SOMENTE_PARCIAIS_9B':raise RuntimeError('Confirmação literal incorreta')
    if active_download():raise RuntimeError('Downloader ativo: limpeza bloqueada')
    base=lab/'modelos/qwen3.5-9b-uncensored-hf'
    full=base/'model.safetensors'
    if full.is_symlink() or not full.is_file() or full.stat().st_size!=SIZE9:
        raise RuntimeError('Modelo final inexistente ou tamanho divergente')
    print('Conferindo SHA-256 completo do 9B (18,8 GB)...',flush=True)
    if hash_file(full)!=SHA9:raise RuntimeError('Hash do 9B divergente; nenhum parcial removido')
    result=[]
    for p in get_cleanup_candidates(lab):
        if active_download():raise RuntimeError('Downloader surgiu durante a limpeza; interrompido')
        if p.is_symlink() or not p.is_file():raise RuntimeError('Parcial alterado; interrompido')
        size=p.stat().st_size
        p.unlink()
        result.append(dict(path=str(p),bytes=size))
    return result

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('audit','clean'))
    parser.add_argument('--lab',type=Path,default=LAB_DEFAULT)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--confirm',default='')
    a=parser.parse_args(argv)
    lab=a.lab.expanduser().resolve()
    if a.mode=='audit':
        print(json.dumps(report(lab),ensure_ascii=False,indent=2));return 0
    if not a.apply:
        print(json.dumps({'mode':'DRY_RUN','candidates':report(lab)['candidate_partials'],
            'message':'Nenhuma exclusão. Para executar somente os parciais 9B, --apply --confirm APAGAR_SOMENTE_PARCIAIS_9B'},ensure_ascii=False,indent=2));return 0
    try:
        result=clean(lab,a.confirm)
    except (RuntimeError,OSError) as exc:
        print(f'BLOQUEADO: {exc}',file=sys.stderr);return 1
    print(json.dumps({'removed':result,'total_bytes':sum(x['bytes'] for x in result)},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
