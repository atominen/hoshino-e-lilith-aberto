"""Fechamento controlado do Laboratorio: 3 SFT de ate 10 min, depois curadoria.

Nenhum treino ou exclusao em GET. Bases escolhidas explicitamente pelo operador;
9B nao treinavel nesta versao. Trabalhos separados, sem deploy na Central.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

ENTITIES = ('alistair', 'lilith', 'hoshino')
MODELS = ('4b', '0.8b')
ID = re.compile(r'^[a-f0-9]{16}$')
from .corpus_atual import dataset_id as _dataset_id
ORIGINAL = {e: _dataset_id(e) for e in ('alistair', 'lilith', 'hoshino')}
BUSY_TOKENS = ('laboratorio.professor_moe worker', 'treino_micro.py',
               'treino_qwen35_entidade.py', 'laboratorio.probes_arquiteturas smoke',
               'llama-server --model', 'laboratorio.trabalhador --home',
               'laboratorio.finalizacao_10min worker')


def root(home): return Path(home) / 'controle-laboratorio' / 'fechamento-10min'


def now(): return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex[:8])
    try:
        with tmp.open('x', encoding='utf8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def plan(home, picks):
    from .experimentos import allowed_data
    if not isinstance(picks, dict) or set(picks) != set(ENTITIES):
        raise ValueError('Escolha explicitamente as tres entidades')
    if picks['alistair'] != '4b' or any(picks[x] not in MODELS for x in ENTITIES):
        raise ValueError('Alistair exige 4B. 9B esta bloqueado; nao substituir sem escolher.')
    available = {x['id']: x for x in allowed_data(home)}
    if any(ORIGINAL[e] not in available for e in ENTITIES):
        raise RuntimeError('Corpus original de uma entidade ausente; nenhum treino iniciado')
    choices = []
    for entity in ENTITIES:
        name = picks[entity]
        if name == '4b':
            model = Path(home)/'modelos-extras/alistair-qwen35-4b/hf'
        else:
            model = Path(home)/'modelos/qwen3.5-0.8b'
        if not (model/'config.json').is_file() or not list(model.glob('*.safetensors')):
            raise RuntimeError(f'Pesos HF locais incompletos para {entity}: {model}')
        d=available[ORIGINAL[entity]]
        choices.append({'entity':entity,'base':name,'base_path':str(model),
                        'dataset_id':ORIGINAL[entity], 'train':d['train'],
                        'validation':d['validation'], 'minutes_limit':10,
                        'mode':'QLoRA_4B_NF4' if name=='4b' else 'LoRA_08B_BF16'})
    return {'order':choices,'sequential':True,'time_limit_each_minutes':10,
            'model_9b_enabled':False, 'no_deploy':True,
            'note':'4B compartilhado usa LoRAs SEPARADAS; nao substitui os 9B originais. Alistair usa seed sintetico piloto.'}


def busy_process(exclude=()):
    exclude = set(exclude) | {os.getpid(), os.getppid()}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) in exclude: continue
        try:
            cmd=(proc/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ')
        except (OSError, PermissionError):continue
        # Do not trust simple python search terms in a shell command; match actual binary or module execution.
        if ('python' in cmd and any(x in cmd for x in BUSY_TOKENS[:-1])) or ('llama-server' in cmd and '--model' in cmd):
            return f'{proc.name}: {cmd[:200]}'
    return None


def job_file(home, id):
    if not isinstance(id,str) or not ID.fullmatch(id):raise ValueError('ID de job inválido')
    return root(home)/'jobs'/(id+'.json')


def read_job(home, id):
    f=job_file(home,id)
    if not f.is_file():raise ValueError('Trabalho inexistente')
    obj=json.loads(f.read_text(encoding='utf8'))
    return obj


def recent(home):
    directory=root(home)/'jobs'
    if not directory.is_dir():return []
    ret=[]
    for f in sorted(directory.glob('*.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:12]:
        try:
            o=json.loads(f.read_text(encoding='utf8'))
            if o.get('state') in ('started','running'):
                pid=o.get('pid',0)
                if not isinstance(pid,int) or not (Path('/proc')/str(pid)).exists():
                    o['state']='interrupted_unverified'
            ret.append(o)
        except (ValueError,OSError):continue
    return ret


def status(home):
    jobs=recent(home)
    teacher=[]
    try:
        from .professor_moe import jobs as teacher_jobs
        teacher=teacher_jobs(home)
    except (OSError,ValueError,TypeError):pass
    return {'jobs':jobs,'teacher_jobs':teacher if isinstance(teacher,list) else [],
            'blocked_9b':True,'models':list(MODELS),
            'cleaning':'ONLY_DRY_RUN', 'training_and_teacher_do_not_run_in_parallel':True}


def launch(home, project, picks, confirm):
    raise RuntimeError('Fechamento v1.3 aposentado. Use sessão noturna cooperativa do supervisor e treino unificado.')


def run_command(cmd, log, project, timeout=1450):
    env=os.environ.copy();env.pop('HSA_OVERRIDE_GFX_VERSION',None)
    print('EXECUTANDO:',repr(cmd),flush=True)
    try:
        result=subprocess.run(cmd,env=env,cwd=str(project),timeout=timeout,check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'Limite de execucao atingido: {timeout}s; sem retry automatico') from exc
    if result.returncode:
        raise RuntimeError(f'Etapa encerrou com codigo {result.returncode}; veja {log}')


def _confirm_artifact(path):
    if not path.is_dir() or path.is_symlink():return False
    return all((path/n).is_file() for n in ('adapter_model.safetensors','adapter_config.json'))


def worker(home, project, jid):
    raise RuntimeError('Worker histórico aposentado; não retomar automaticamente. Evidências permanecem legíveis.')


def cancel(home, jid, confirm):
    if confirm!='PARAR_LOTE_10_MIN':raise ValueError('Confirmacao de parada obrigatoria')
    obj=read_job(home,jid)
    if obj.get('state') not in ('started','running'):
        raise RuntimeError('Lote nao esta ativo')
    pid=obj.get('pid')
    if not isinstance(pid,int) or pid<2:raise RuntimeError('PID nao validado')
    proc=Path('/proc')/str(pid)
    if not proc.is_dir():raise RuntimeError('Processo ja terminou; atualize estado')
    if proc.stat().st_uid!=os.getuid():raise PermissionError('PID pertence a outro usuario')
    cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
    if 'laboratorio.finalizacao_10min' not in cmd or 'worker' not in cmd or ('--id '+jid) not in cmd:
        raise RuntimeError('PID reutilizado ou nao corresponde ao job')
    if os.getpgid(pid)!=pid:raise RuntimeError('Grupo nao isolado; parada recusada')
    os.killpg(pid,signal.SIGTERM)
    obj['state']='cancel_requested'
    obj['error']='SIGTERM solicitado; confirmar pela ausência de subprocessos e revisar checkpoints'
    write_json(job_file(home,jid),obj)
    return {'stop_requested':True,'id':jid}


def prepare_teacher(home, jid, confirm):
    if confirm!='PREPARAR_3_CURADORIAS':raise ValueError('Confirmacao de curadoria necessaria')
    obj=read_job(home,jid)
    if obj.get('state')!='trained_pending_teacher' or len(obj.get('results',[]))!=3:
        raise RuntimeError('Tres treinos com checkpoints precisam concluir antes da curadoria')
    if busy_process():raise RuntimeError('GPU ocupada, revisar antes de iniciar professor')
    from .professor_moe import prepare_from_dataset
    result={}
    obj.setdefault('teacher_ids',{})
    for ent in ENTITIES:
        if ent in obj['teacher_ids']:
            result[ent]={'id':obj['teacher_ids'][ent],'already_prepared':True}
            continue
        prepared=prepare_from_dataset(home,ent,ORIGINAL[ent],limit=12,mode='standard')['prepared']
        result[ent]=prepared
        obj['teacher_ids'][ent]=prepared['id']
        write_json(job_file(home,jid),obj)
    obj['state']='teacher_prepared'
    write_json(job_file(home,jid),obj)
    return {'teacher':result,'requires_manual_run':True,'requires_quality_and_human_approval':True}


def closure(home, jid):
    obj=read_job(home,jid)
    teacher_ids=obj.get('teacher_ids') or {}
    quality={}
    from .professor_moe import detail
    for e in ENTITIES:
        tid=teacher_ids.get(e)
        if not tid:quality[e]='NAO_PREPARADO';continue
        try:
            t=detail(home,tid)
            quality[e]={'state':t.get('state'),'passed':t.get('quality_passed') is True,
                        'manual_export':bool(t.get('export'))}
        except (ValueError,OSError):quality[e]='STATUS_INDISPONIVEL'
    passed=(len(obj.get('results',[]))==3 and all(isinstance(quality[e],dict)
       and quality[e]['passed'] and quality[e]['manual_export'] for e in ENTITIES))
    return {'completed':passed,'training_state':obj.get('state'),
            'teacher':quality,'identity_and_memory_modified':False,
            'message':('QUALIDADE E REVISAO APROVADAS: laboratorio pode ser arquivado'
                       if passed else 'PENDENTE: treinos e propostas exigem aprovacao; nao apagar ou implantar automaticamente')}



def audit_environment(home, project):
    """Read-only post-migration sanity check. NO deleting/renaming here."""
    home=Path(home).expanduser().resolve()
    project=Path(project).expanduser().resolve()
    old=Path.home()/'laboratorio-lora'
    import subprocess
    try:
        ignored=subprocess.run(['git','-C',str(project),'check-ignore','-q','laboratorio-local/'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0
    except (OSError,subprocess.TimeoutExpired):ignored=False
    candidates=[]
    from .limpeza_segura import get_cleanup_candidates
    try:
        candidates=[{'path':str(p),'bytes':p.stat().st_size} for p in get_cleanup_candidates(home)]
    except OSError as exc:candidates=[{'error':str(exc)}]
    out={'project':str(project),'storage_path':str(home),
         'storage_in_project':home==project/'laboratorio-local',
         'old_compatibility_symlink':old.is_symlink() and old.resolve()==home,
         'git_ignores_storage':ignored,
         'entities':{e:{k:(project/'entidades'/e/k).is_dir() for k in ('identity','memory')}
                     for e in ('hoshino','lilith')},
         'essential_code':{str(n):(project/n).is_file() for n in
             ('laboratorio/painel.py','laboratorio/finalizacao_10min.py',
              'laboratorio/professor_moe.py','laboratorio/treino_micro.py')},
         'safe_partial_candidates':candidates,
         'deletion_performed':False,'models_removed':False,
         'note':'Nenhum modelo confirmado como dispensavel: nao executar limpezas generalizadas.'}
    out['structure_ok']=out['storage_in_project'] and out['old_compatibility_symlink'] and \
           out['git_ignores_storage'] and all(all(v.values()) for v in out['entities'].values()) and \
           all(out['essential_code'].values())
    return out


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('action', choices=('status','worker','closure'))
    p.add_argument('--home',type=Path,default=Path.home()/'laboratorio-lora')
    p.add_argument('--project',type=Path,default=Path.home()/'hoshino e lilith')
    p.add_argument('--id')
    a=p.parse_args(argv)
    if a.action=='worker':worker(a.home,a.project,a.id)
    elif a.action=='closure':print(json.dumps(closure(a.home,a.id),ensure_ascii=False,indent=2))
    else:print(json.dumps(status(a.home),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
