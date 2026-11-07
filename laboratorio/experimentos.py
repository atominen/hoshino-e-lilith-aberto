"""Planos locais: entradas explícitas, validação e agendamento não destrutivo.
Sem downloads/treinos automáticos ao abrir o painel ou escolher um modelo.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import signal
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .catalogo import BY_ID, MODELS

ID = re.compile(r'^[a-z0-9]{12}$')
OPERATIONS = ('train','convert','ollama_test','cycle_30m')


def allowed_data(home: Path):
    from .corpus_atual import CORPUS
    roots = (home/CORPUS,)
    result=[]
    for root in roots:
        if not root.is_dir() or root.is_symlink(): continue
        for file in sorted(root.glob('*_train.jsonl')):
            if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root.resolve()):continue
            stem=file.name[:-len('_train.jsonl')]
            val=root/(stem+'_validation.jsonl')
            if not val.is_file() or val.is_symlink():continue
            try:
                with file.open(encoding='utf-8') as stream:
                    first=next((line for line in stream if line.strip()),None)
                obj=json.loads(first) if first else {}
                if not isinstance(obj.get('messages'),list):continue
            except (OSError,ValueError):continue
            result.append(dict(id=f'{root.name}:{stem}', label=f'{root.name} / {stem}',
                               train=str(file), validation=str(val)))
    seed=home/'datasets-alistair-seed'
    if seed.is_dir() and not seed.is_symlink():
        train=seed/'alistair_train.jsonl';val=seed/'alistair_validation.jsonl'
        if all(p.is_file() and not p.is_symlink() for p in (train,val)):
            result.append(dict(id='datasets-alistair-seed:alistair',label='Alistair / corpus sintetico piloto',train=str(train),validation=str(val)))
    uploads=home/'datasets-importados'
    if uploads.is_dir() and not uploads.is_symlink():
        for folder in sorted(uploads.iterdir()):
            if not folder.is_dir() or folder.is_symlink() or not ID.fullmatch(folder.name):continue
            train=folder/'train.jsonl';val=folder/'validation.jsonl'
            if all(p.is_file() and not p.is_symlink() for p in (train,val)):
                result.append(dict(id='importados:'+folder.name,label='Importado / '+folder.name,
                                   train=str(train),validation=str(val)))
    return result


def import_dataset(home:Path,train_text:str,validation_text:str):
    if not isinstance(train_text,str) or not isinstance(validation_text,str):raise ValueError('Arquivos devem ser UTF-8 JSONL')
    if len(train_text.encode())>2*1024*1024 or len(validation_text.encode())>2*1024*1024:
        raise ValueError('Limite de 2 MiB por arquivo')
    def check(content):
        count=0
        for line in content.splitlines():
            if not line.strip():continue
            try: x=json.loads(line)
            except ValueError:raise ValueError('Linha inválida, exige JSONL')
            msgs=x.get('messages') if isinstance(x,dict) else None
            if not isinstance(msgs,list) or len(msgs)<2 or not isinstance(msgs[-1],dict) or msgs[-1].get('role')!='assistant':
                raise ValueError('Cada exemplo precisa de messages, terminando em assistant')
            if any(not isinstance(m,dict) or m.get('role') not in ('user','assistant','system') or not isinstance(m.get('content'),str) or not m.get('content').strip() for m in msgs):
                raise ValueError('Somente mensagens textuais válidas de user/system/assistant')
            count+=1
            if count>5000:raise ValueError('Limite de 5000 registros')
        if count<2:raise ValueError('Mínimo dois exemplos')
        return count
    a=check(train_text);b=check(validation_text)
    # prevent obvious leakage between train and validation
    tr={hashlib.sha256(line.strip().encode()).digest() for line in train_text.splitlines() if line.strip()}
    vl={hashlib.sha256(line.strip().encode()).digest() for line in validation_text.splitlines() if line.strip()}
    if tr&vl:raise ValueError('Treino e validação contêm registros iguais; separar antes de importar')
    identifier=uuid.uuid4().hex[:12]
    directory=home/'datasets-importados'/identifier
    directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name,body in [('train.jsonl',train_text),('validation.jsonl',validation_text)]:
        f=directory/name;f.write_text(body,encoding='utf-8');f.chmod(0o600)
    return {'id':'importados:'+identifier,'train_rows':a,'validation_rows':b}


def clean_params(value: dict,home: Path):
    if not isinstance(value,dict):raise ValueError('Plano deve ser objeto JSON.')
    model=BY_ID.get(value.get('model'))
    if not model:raise ValueError('Modelo fora do catálogo experimental autorizado.')
    from .candidatos import validate_local,model_root
    if not validate_local(model_root(home,model['id']),model['repo']):
        raise ValueError('Modelo não baixado/verificado. Painel aceita somente checkpoints HF completos.')
    operation=value.get('operation')
    if operation not in OPERATIONS:raise ValueError('Operação desconhecida.')
    dataset=value.get('dataset','')
    datasets={x['id']:x for x in allowed_data(home)}
    if operation in ('train','cycle_30m') and dataset not in datasets:
        raise ValueError('Escolha um corpus local train/validation validado.')
    if operation in ('train','cycle_30m') and model['training']!='texto_qlora':
        raise ValueError('Este VLM não tem treinador multimodal homologado nesta versão. Não converter em texto silenciosamente.')
    if operation in ('convert','ollama_test') and model['kind']!='texto':
        raise ValueError('A exportação do painel Ollama v0.2 é apenas textual. Visão exige mmproj e teste separado.')
    duration=int(value.get('minutes',30))
    if operation=='cycle_30m' and duration != 30:raise ValueError('Ciclo comparativo exige exatamente 30 minutos de treino.')
    if not 1<=duration<=90:raise ValueError('Treino limitado a 1–90 minutos por experimento.')
    entity=value.get('entity','hoshino')
    if entity not in ('hoshino','lilith','alistair'):raise ValueError('Entidade de treino deve ser Hoshino, Lilith ou Alistair.')
    from .corpus_atual import entidade_do_corpus
    owner=entidade_do_corpus(dataset)
    if operation in ('train','cycle_30m') and owner and owner!=entity:
        raise ValueError('Corpus da entidade não combina com a personalidade selecionada.')
    if operation in ('train','cycle_30m') and dataset.startswith('importados:'):
        directory = home/'datasets-importados'/dataset.split(':',1)[1]
        origin = directory/'origem_professor.json'
        if origin.is_file() and not origin.is_symlink():
            metadata=json.loads(origin.read_text(encoding='utf-8'))
            if metadata.get('entity')!=entity:
                raise ValueError('Corpus derivado de professor pertence a outra entidade.')
    adapter=value.get('adapter','')
    if adapter not in ('','hoshino','lilith','alistair'):
        raise ValueError('Adaptador deve ser Hoshino, Lilith, Alistair ou nenhum.')
    return dict(model=model['id'], operation=operation, dataset=dataset if operation in ('train','cycle_30m') else '',
                minutes=duration, entity=entity if operation in ('train','cycle_30m') else '', adapter=adapter if operation in ('convert','ollama_test') else '',
                repo=model['repo'], training=model['training'])


def model_path(home,model_id):return home/'modelos-extras'/model_id/'hf'
def output_path(home,model_id):return home/'modelos-extras'/model_id/'gguf'
def adapter_path(home,model_id,name):return home/'modelos-extras'/model_id/'adapters'/name

def gate_9b(home:Path,op):
    """Não disputar recurso: pai 9B rodando impede treino/conversão/teste; download ativo impede outro HF."""
    from .core import Laboratory
    lab=Laboratory(home,home) # _process é estático, projeto não consultado
    pidfile=home/'experimentos/orquestrador-9b-vision-v1-4/pid'
    try: pid=int(pidfile.read_text())
    except (ValueError,OSError):pid=0
    alive, stopped=lab._process(pid)
    if alive and op in ('train','cycle_30m','convert','ollama_test'):
        raise RuntimeError('Orquestrador 9B ainda existe (inclusive pausado): preserve a janela de 21h e finalize o 9B antes de usar GPU.')
    if op in ('train','cycle_30m','convert','ollama_test'):
        agendamento=home/'controle-laboratorio/agendamento.json'
        if agendamento.is_file():
            try:
                item=json.loads(agendamento.read_text())
                dt=datetime.fromisoformat(item.get('at','1970-01-01 00:00:00'))
                now=datetime.now()
                if dt-timedelta(hours=3) < now < dt+timedelta(hours=11):
                    raise RuntimeError('Janela do 9B reservada (3h antes a 11h depois); não disputar GPU/CPU.')
            except (OSError,ValueError):pass

    if op in ('download','train','cycle_30m','convert','ollama_test'):
        try:
            out=subprocess.run(['pgrep','-af','automacao_9b_vision_v1_4/baixar_9b.py'],capture_output=True,text=True,timeout=5)
            if out.returncode==0 and any('python' in x and 'baixar_9b.py' in x for x in out.stdout.splitlines()):
                raise RuntimeError('Download do 9B em andamento: não concorrer com os recursos/armazenamento do 9B.')
        except FileNotFoundError:pass


def inspect_plan(params,home:Path):
    p=clean_params(params,home)
    model=model_path(home,p['model']);out=output_path(home,p['model'])
    free=shutil.disk_usage(home).free//(1024**3)
    files=[x for x in model.glob('*.safetensors')] if model.exists() else []
    base=out/'base-q4_k_m.gguf'
    notes=[]
    if p['operation']=='cycle_30m':notes.append('Teste thinking OFF/ON quando suportado (6B Yi apenas OFF); 30 min LoRA; GGUF e comparacao textual. Interrompe em qualquer falha. Tempo total sera maior que 30 min.')
    if p['operation'] in ('train','cycle_30m'):
        notes.append('QLoRA NF4 textual experimental na RX 6650 XT de 8 GiB; OOM pode interromper.')
        if not files:notes.append('Checkpoint HF não encontrado; baixe antes do treino.')
    if p['operation']=='convert':
        notes.append('Exportação GGUF F16 -> Q4_K_M exige armazenamento temporário; saída é textual.')
        if not files:notes.append('Checkpoint Safetensors não encontrado.')
    if p['operation']=='ollama_test':
        notes.append('Importa somente em Ollama isolado na porta 11557; não instala na Central.')
        if not base.is_file():notes.append('GGUF Q4_K_M não encontrado; converter antes.')
    if p['adapter'] and p['operation'] in ('convert','ollama_test'):
        if not adapter_path(home,p['model'],p['adapter']).is_dir():notes.append('Adaptador selecionado não encontrado; exportação/importação poderá falhar.')
    return {'plan':p,'model_local':str(model),'gguf_local':str(base), 'files_safetensors':len(files),
            'disk_free_gib':free,'notes':notes,'requires_explicit_confirmation':True,
            'does_not_modify_existing_9b':True}


def jobs_dir(home):return home/'controle-laboratorio'/'jobs'

def read_jobs(home):
    root=jobs_dir(home)
    results=[]
    for f in sorted(root.glob('*.json'), key=lambda x:x.stat().st_mtime,reverse=True)[:24] if root.is_dir() else []:
        try:
            if ID.fullmatch(f.stem):results.append(json.loads(f.read_text()))
        except (OSError,ValueError):pass
    return results


def job_info(home,job_id):
    if not isinstance(job_id,str) or not ID.fullmatch(job_id):raise ValueError('ID inválido')
    p=jobs_dir(home)/(job_id+'.json')
    obj=json.loads(p.read_text())
    log=jobs_dir(home)/(job_id+'.log')
    if log.is_file():
        with log.open('rb') as f:
            f.seek(max(0,f.seek(0,2)-12000));obj['log_tail']=f.read().decode(errors='replace')[-7000:]
    return obj


def _write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    os.replace(temp,path)


def create_job(home:Path,raw,at=None):
    preview=inspect_plan(raw,home)
    p=preview['plan']
    if p['operation'] in ('train','cycle_30m'):
        raise RuntimeError('Treinamento legado aposentado. Use treinos_unificados na Central; previews e evidências antigas permanecem legíveis.')
    if at:
        if not isinstance(at,str):raise ValueError('Horário inválido')
        dt=datetime.fromisoformat(at.replace('T',' '))
        if dt.tzinfo:raise ValueError('Usar horário local sem timezone')
        if not datetime.now()<dt<datetime.now()+timedelta(days=7):raise ValueError('Horário futuro máximo 7 dias.')
        # Orquestrador 9B programado às 21h; não reservar automaticamente a mesma janela.
        schedule=home/'controle-laboratorio/agendamento.json'
        if schedule.is_file():
            old=json.loads(schedule.read_text())
            previous=datetime.fromisoformat(old.get('at','1970-01-01 00:00:00'))
            if abs((previous-dt).total_seconds())<12*3600:
                raise RuntimeError('Conflito com janela reservada do 9B (±12h); selecione outro horário.')
    else:
        gate_9b(home,p['operation'])
    root=jobs_dir(home);root.mkdir(parents=True,exist_ok=True)
    job_id=uuid.uuid4().hex[:12]
    record={'id':job_id,'created':datetime.now().astimezone().isoformat(), 'state':'scheduled' if at else 'queued',
            'at':at or '', 'plan':p,'error':''}
    _write_json(root/(job_id+'.json'),record)
    cli=Path(__file__).parent/'labctl.py'
    if at:
        unit='lab-experimento-'+job_id
        when=datetime.fromisoformat(at.replace('T',' ')).strftime('%Y-%m-%d %H:%M:%S')
        cmd=['systemd-run','--user','--unit',unit,'--on-calendar',when,sys.executable,str(cli),'launch-job','--id',job_id]
        try:
            r=subprocess.run(cmd,text=True,capture_output=True,timeout=20)
            if r.returncode:raise RuntimeError(r.stderr or r.stdout)
        except Exception as e:
            record['state']='failed';record['error']='Agendamento não realizado: '+str(e);_write_json(root/(job_id+'.json'),record)
            raise
        record['timer']=unit+'.timer';_write_json(root/(job_id+'.json'),record)
    else: launch_job(home,job_id)
    return job_info(home,job_id)


def launch_job(home:Path,job_id):
    entry=job_info(home,job_id)
    if entry['state'] not in ('queued','scheduled'):
        raise RuntimeError('Job já iniciado/concluído; não executar duas vezes.')
    if entry['plan']['operation'] in ('train','cycle_30m'):
        entry.update(state='blocked_legacy',error='Migração manual para treino unificado; não repetir agenda antiga')
        entry.pop('log_tail',None);_write_json(jobs_dir(home)/(job_id+'.json'),entry)
        raise RuntimeError(entry['error'])
    p=entry['plan'];gate_9b(home,p['operation'])
    # Deixar ao worker o bloqueio interprocessos flock e todas as validações restantes.
    from subprocess import DEVNULL,Popen
    root=jobs_dir(home)
    python=home/'.venv-rocm/bin/python'
    if not python.is_file():raise RuntimeError('Python ROCm do laboratório não encontrado.')
    entry['state']='started';entry.pop('log_tail',None);_write_json(root/(job_id+'.json'),entry)
    try:
        with (root/(job_id+'.log')).open('ab') as f:
            proc=Popen([str(python),'-u','-m','laboratorio.trabalhador','--home',str(home),'--job',job_id],
                       stdin=DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,
                       cwd=str(Path(__file__).resolve().parent.parent))
        entry['pid']=proc.pid
        _write_json(root/(job_id+'.json'),entry)
    except Exception as e:
        entry['state']='failed';entry['error']=str(e);_write_json(root/(job_id+'.json'),entry);raise
    return entry


def cancel_job(home:Path,job_id):
    info=job_info(home,job_id)
    if info['state'] not in ('running','started'):
        raise RuntimeError('Job não está ativo para interrupção')
    pid=info.get('pid')
    if not isinstance(pid,int) or pid<2:raise RuntimeError('PID não encontrado')
    proc=Path('/proc')/str(pid)
    try:
        if proc.stat().st_uid!=os.getuid():raise PermissionError('Processo não pertence ao usuário')
        cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        if 'laboratorio.trabalhador' not in cmd or ('--job '+job_id) not in cmd:
            raise RuntimeError('PID foi reutilizado ou comando diferente; cancelamento recusado')
        os.kill(pid,signal.SIGTERM)
    except FileNotFoundError:raise RuntimeError('Processo já terminou; atualize o painel')
    return {'requested':True,'id':job_id,'pid':pid}
