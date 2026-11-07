"""Download sob comando explícito. A interface operacional mostra só pesos completos.

Uso: python -m laboratorio.candidatos list|download qwen3-8b
"""
from __future__ import annotations
import argparse,fcntl,json,os,shutil,sys
from pathlib import Path
from .catalogo import MODELS,BY_ID


def model_root(home:Path,model_id):
    return home/'modelos-extras'/model_id/'hf'


def validate_local(root:Path,expected_repo:str|None=None):
    """Verifica arquivos locais e finalização; nunca marca .incomplete como instalado."""
    if not root.is_dir() or root.is_symlink():return False
    manifest=root/'lab_revision.json'
    if not manifest.is_file() or manifest.is_symlink():return False
    try:
        info=json.loads(manifest.read_text(encoding='utf-8'))
        if expected_repo and info.get('repo')!=expected_repo:return False
        if not (root/'config.json').is_file():return False
        weight_files=sorted(root.glob('*.safetensors'))
        if not weight_files or any(x.is_symlink() or x.stat().st_size<4096 for x in weight_files):return False
        index=root/'model.safetensors.index.json'
        if index.is_file():
            obj=json.loads(index.read_text())
            required=set(obj['weight_map'].values())
            if not required:return False
            if any('/' in n or '\\' in n or not (root/n).is_file() for n in required):return False
        else:
            if not (root/'model.safetensors').is_file() and len(weight_files)!=1:return False
        return bool(info.get('revision'))
    except (OSError,ValueError,KeyError,TypeError):return False


def installed_models(home:Path):
    """Descoberta por RECIBOS locais, não pela lista de planos candidatos."""
    result=[]
    directory=home/'modelos-extras'
    if not directory.is_dir() or directory.is_symlink():return result
    for root in sorted(directory.iterdir()):
        if not root.is_dir() or root.is_symlink():continue
        folder=root/'hf'
        if not validate_local(folder):continue
        try:
            meta=json.loads((folder/'lab_revision.json').read_text())
            repo=meta['repo']
            if not isinstance(repo,str) or '/' not in repo:continue
            known=BY_ID.get(root.name)
            if known and repo!=known['repo']:continue
            if known:entry=dict(known)
            else:
                # Modelos locais desconhecidos ficam inventariados, mas nunca
                # treináveis automaticamente sem revisão do modelo e arquitetura.
                entry=dict(id=root.name,name=repo,size='não avaliado',kind='desconhecido',
                           repo=repo,vision=False,thinking=False,training='pesquisa',
                           score='Pesos presentes; arquitetura e thinking sem homologação.',
                           source='https://huggingface.co/'+repo)
            result.append(dict(entry,local_path=str(folder),installed=True))
        except (KeyError,OSError,ValueError,TypeError):continue
    return result


def download(home:Path,model_id:str):
    if model_id not in BY_ID:raise ValueError('Candidato nao autorizado para laboratorio.')
    if BY_ID[model_id].get('retired'):
        raise ValueError('Modelo retirado pelo proprietário; download recusado, sem reinstalação automática.')
    from .experimentos import gate_9b
    gate_9b(home,'download')
    free=shutil.disk_usage(home).free
    minimum=35 if model_id=='yi15-6b' else 50
    if free<minimum*1024**3:raise RuntimeError(f'Exige {minimum} GiB livres antes de baixar: preservar 9B, GGUF e dados.')
    repo=BY_ID[model_id]['repo']
    root=model_root(home,model_id)
    root.mkdir(parents=True,exist_ok=True)
    lock=home/'controle-laboratorio'/'trabalhador.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as lockfile:
        try:fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Outro experimento ou download já utiliza o laboratório')
        spec=BY_ID[model_id]
        _perform_download(root,repo,revision=spec.get('revision'),source_files=spec.get('source_files'))

def _perform_download(root:Path,repo:str,*,revision=None,source_files=None):
    # Antes de importar huggingface_hub, definir fallback de rede lenta.
    os.environ.setdefault('HF_HUB_DISABLE_XET','1')
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','120')
    os.environ.setdefault('HF_HUB_ETAG_TIMEOUT','60')
    from huggingface_hub import model_info,snapshot_download
    revision=revision or model_info(repo).sha
    if not isinstance(revision,str) or len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):
        raise RuntimeError('Revisão imutável HF não identificada')
    source_files=source_files or {}
    if any(Path(name).name!=name or len(digest)!=64 for name,digest in source_files.items()):
        raise ValueError('Arquivos pinados inválidos')
    print('Baixando',repo,revision,flush=True)
    snapshot_download(repo_id=repo,revision=revision,local_dir=str(root),max_workers=1,
       allow_patterns=['*.safetensors','*.json','*.jinja','*.model','*.txt','*.tiktoken','tokenizer.*','merges.txt','vocab.json',*source_files],
       ignore_patterns=['*.bin','*.pt','*.pth','*.gguf'])
    if source_files:
        import hashlib
        for name,digest in source_files.items():
            path=root/name
            if not path.is_file() or path.is_symlink():raise RuntimeError('Arquivo pinado ausente/divergente')
            actual=hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda:source.read(8*1024**2),b''):actual.update(block)
            if actual.hexdigest()!=digest:raise RuntimeError('SHA256 divergente; não marcar instalação completa')
    marker=root/'lab_revision.json'
    marker.write_text(json.dumps({'repo':repo,'revision':revision},ensure_ascii=False))
    if not validate_local(root,repo):
        marker.unlink(missing_ok=True)
        raise RuntimeError('Download incompleto: modelo não será mostrado como instalado')
    print('DOWNLOAD VERIFICADO:',root,flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('list','installed','download'))
    p.add_argument('model',nargs='?');p.add_argument('--home',type=Path,default=Path.home()/'laboratorio-lora')
    args=p.parse_args();home=args.home.resolve()
    if args.action=='list':
        for m in MODELS:print(f"{m['id']}: {m['name']} [{m['size']}] — {m['repo']} (ainda NÃO baixado até verificação local)")
    elif args.action=='installed':
        for m in installed_models(home):print(m['name'],m['local_path'])
    else:
        if not args.model:p.error('Informe ID de candidato (consulte list)')
        download(home,args.model)
if __name__=='__main__':main()
