"""Catálogo único e orquestrador conservador de treinos; nunca muda a Central.

Read-only catalog/preview. start exige confirmação; smoke e treino ocorrem
no worker isolado e serializado, preservando checkpoints anteriores.
"""
from __future__ import annotations
import fcntl, json, math, os, re, signal, subprocess, sys, time, uuid
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from . import corpus_atual

MODELS = {
    'qwen35-4b': ('modelos-extras/alistair-qwen35-4b/hf', 'Qwen3.5-4B', None, 'inference_only', '4b'),
    'alistair-4b': ('modelos-extras/alistair-qwen35-4b/hf', 'Qwen3.5-4B', 'alistair', 'smoke_ok', '4b'),
    'yi-6b': ('modelos-extras/yi15-6b/hf', 'Yi-1.5-6B', None, 'smoke_ok', '6b'),
    'hunyuan-7b': ('modelos-extras/hunyuan-7b/hf', 'Hunyuan-7B', None, 'smoke_ok', '7b-hunyuan'),
    'qwen25-7b': ('modelos/qwen2.5-7b-hf-local', 'Qwen2.5-7B', None, 'oom', '7b-qwen25'),
    # 05/11 (decisão humana): treino dos 9B a partir do Qwen/Qwen3.5-9B oficial (rev. c2022362), não do sem censura.
    'qwen35-9b': ('modelos/qwen3.5-9b-oficial-hf', 'Qwen3.5-9B oficial', None, 'oom', '9b'),
    'qwen35-08b': ('modelos/qwen3.5-0.8b', 'Qwen3.5-0.8B', None, 'testing_only', None),
}
# 06/11 (pedido humano): corpus v5 escrito à mão; material antigo apagado. Ver corpus_atual.py.
DATASETS = {e: (corpus_atual.treino(e), corpus_atual.validacao(e)) for e in ('alistair','hoshino','lilith')}
CUSTOM_TRAININGS = 3
STATES = {'smoke_ok': 'Dois passos QLoRA aprovados; treino cronometrado ainda não homologado',
          'inference_only': '4B disponível para inferência; treino por entidade ainda não validado',
          'oom': 'Pesos instalados; treino atual interrompeu por VRAM (OOM)',
          'testing_only': 'Apenas ferramenta de teste 0.8B; não é base de Hoshino/Lilith'}
ID_RE = re.compile(r'^[0-9a-f]{16}$')

def measured_preset(home,model,entity):
    """Somente medidas do mesmo corpus/base/perfil; não extrapola o teste 0.8B."""
    from .versionamento_lora import sha,base_signature
    base=Path(home)/MODELS[model][0];data=[Path(home)/r for r in DATASETS[entity]]
    good=[]
    for result in _registry(home).joinpath('adapters',entity).glob('*/micro_result.json'):
        try:
            row=json.loads(result.read_text());prov=json.loads(result.with_name('provenance.json').read_text())
            if (row.get('model')!=str(base.resolve()) or row.get('cancelled') or row.get('steps',0)<2 or
                prov.get('base_config_sha256')!=sha(base/'config.json') or
                prov.get('base_weights_signature')!=base_signature(base) or
                prov.get('train_sha256')!=sha(data[0]) or prov.get('validation_sha256')!=sha(data[1]) or
                row.get('preset',{}).get('memory_profile') not in ('frozen_bf16_v17','frozen_bf16_v18_head_cpu')):continue
            good.append(dict(row,artifact=str(result.parent)))
        except (OSError,ValueError,KeyError,TypeError):continue
    # Smoke não salva adaptador, mas sua medição física pode habilitar um piloto.
    for result in _registry(home).joinpath('reports',entity).glob('*-'+model+'.json'):
        try:
            row=json.loads(result.read_text());physical=json.loads(result.with_suffix('.hardware.json').read_text())
            if (row.get('entity')!=entity or row.get('model')!=str(base.resolve()) or row.get('cancelled') or
                row.get('steps',0)<2 or physical.get('pressure')!=[] or physical.get('child_exit_code')!=0 or
                row.get('base_config_sha256')!=sha(base/'config.json') or
                row.get('base_weights_signature')!=base_signature(base) or
                row.get('train_sha256')!=sha(data[0]) or row.get('validation_sha256')!=sha(data[1])):continue
            good.append(dict(row,artifact=str(result)))
        except (OSError,ValueError,KeyError,TypeError):continue
    if not good:return None
    best=select_measured_profile(good)
    return {'preset':best['preset'],'evidence':best['artifact'],'steps':best['steps'],
            'peak_vram_gib':best['peak_vram_gib'],'duration_seconds':best['duration_seconds'],
            'after_val_loss':best['after_val_loss'],'torch':best['torch'],'rocm':best['rocm'],
            'gpu':best['gpu'],'quality_approved':False,'long_run_validated':False}

def select_measured_profile(rows):
    # A janela física mais longa é melhor evidência de estabilidade. Não usar
    # losses de populações 6/16 ou precisões diferentes como ranking de qualidade.
    duration=max(r.get('optimization_seconds_this_run',0) for r in rows)
    peers=[r for r in rows if r.get('optimization_seconds_this_run',0)==duration]
    updates=max(r.get('updates_this_run',0) for r in peers)
    peers=[r for r in peers if r.get('updates_this_run',0)==updates]
    return min(peers,key=lambda r:r['peak_vram_gib'])

def home_data(home):
    home=Path(home).resolve(); result=[]
    for mid,(rel,label,exclusive,state,smoke_id) in MODELS.items():
        root=home/rel
        files=[p for p in root.glob('*.safetensors') if p.is_file() and not p.is_symlink()] if root.is_dir() else []
        cfg=root/'config.json';present=bool(files and cfg.is_file() and not cfg.is_symlink())
        missing=[];arch=None
        if present:
            try:
                config=json.loads(cfg.read_text(encoding='utf8'))
                arch=config.get('model_type')
                for idx in root.glob('*.safetensors.index.json'):
                    indexes=json.loads(idx.read_text())
                    missing += [n for n in set(indexes.get('weight_map',{}).values()) if not (root/n).is_file()]
            except (ValueError,OSError,TypeError):present=False
        present=present and not missing
        measurements={e:measured_preset(home,mid,e) for e in DATASETS if not exclusive or e==exclusive} if present else {}
        measured=any(measurements.values())
        result.append({'id':mid,'label':label,'path':str(root),'installed':present,
                       'bytes':sum(p.stat().st_size for p in files),'shards':len(files),
                       'architecture':arch,'state':('measured_candidate' if measured else state) if present else 'missing',
                       'description':('Novo perfil passou em GPU; candidato experimental, não qualidade homologada.' if measured else STATES.get(state,'')) if present else 'Pesos/config ausentes ou incompletos',
                       'benchmarks':measurements,'exclusive_entity':exclusive,'smoke_id':smoke_id,
                       'train_enabled':bool(present and (measured or state=='smoke_ok'))})
    teacher=home/'professor-moe-35b/gguf/Qwen3.5-35B-A3B-Q3_K_M.gguf'
    result.append({'id':'professor-35b','label':'Professor MoE 35B-A3B (GGUF Vulkan)','path':str(teacher),
                   'installed':teacher.is_file(),'bytes':teacher.stat().st_size if teacher.is_file() else 0,
                   'shards':1 if teacher.is_file() else 0,'architecture':'GGUF','state':'inference_only',
                   'description':'Geração de exemplos, não treinamento LoRA neste painel','exclusive_entity':None,
                   'smoke_id':None,'train_enabled':False})
    alternative=home/'modelos/qwen2.5-7b-local'
    if alternative.is_dir() and not alternative.is_symlink():
        files=[p for p in alternative.rglob('*') if p.is_file() and not p.is_symlink()
               and any(p.name.endswith(x) for x in ('.gguf','.safetensors','.bin'))]
        if files:
            result.append({'id':'qwen25-7b-local','label':'Qwen2.5-7B — outra versão local',
                'path':str(alternative),'installed':True,'bytes':sum(x.stat().st_size for x in files),
                'shards':len(files),'architecture':'formato local','state':'inference_only',
                'description':'Formato local separado do HF; não duplicar/apagar automaticamente',
                'exclusive_entity':None,'smoke_id':None,'train_enabled':False})
    return result

def training_datasets(home,entity):
    if entity not in DATASETS:raise ValueError('Entidade inválida')
    from .experimentos import allowed_data
    from .professor_moe import detail
    canonical=corpus_atual.dataset_id(entity)
    result=[]
    for d in allowed_data(Path(home)):
        if d['id']==canonical:result.append(dict(d,approved=True,original=True));continue
        if not d['id'].startswith('importados:'):continue
        marker=Path(home)/'datasets-importados'/d['id'].split(':',1)[1]/'origem_professor.json'
        try:
            origin=json.loads(marker.read_text())
            job=detail(Path(home),origin['teacher_job'])
            if (origin.get('entity')==entity and job.get('entity')==entity and
                job.get('state')=='approved_dataset' and job.get('export')==d['id'] and
                origin.get('approved_source_ids')==job.get('approved_ids')):
                result.append(dict(d,approved=True,original=False))
        except (OSError,ValueError,KeyError):continue
    return result

def plan(home,model,entity,minutes,action,checkpoint=None,candidate=None,dataset=None,options=None):
    from .treino_nf4_curto import training_options
    options=training_options(options)
    if model not in MODELS:raise ValueError('Modelo não selecionável para treino')
    if entity not in DATASETS:raise ValueError('Entidade inválida')
    if type(minutes) is not int or not 1<=minutes<=(360 if options.get('optimization_seconds') else 90):raise ValueError('Duração inválida')
    if action not in ('smoke','train','evaluate'):raise ValueError('Ação desconhecida')
    if options and action!='train' and not (action=='smoke' and set(options)<={'rank','head_cpu'}):
        raise ValueError('Opções de otimização somente no treino; smoke aceita apenas rank/offload explícitos')
    if options.get('optimization_seconds',0)>minutes*60:raise ValueError('Otimização excede a duração solicitada')
    row=next(r for r in home_data(home) if r['id']==model)
    if not row['installed']:raise RuntimeError('Pesos completos não encontrados; treino recusado')
    owner=row['exclusive_entity']
    if owner and owner!=entity:raise ValueError('O 4B pertence somente ao Alistair')
    if row['state']=='inference_only':
        return {'allowed':False,'model':row,'entity':entity,'minutes':minutes,'action':action,
                'blocker':'4B habilitado somente para inferência; treino por entidade requer validação própria'}
    if row['state'] in ('oom','testing_only') and not (row['state']=='oom' and action=='smoke' and options.get('head_cpu')==1):
        return {'allowed':False,'model':row,'entity':entity,'minutes':minutes,'action':action,
                'blocker':('Treinamento bloqueado por OOM previamente documentado; requer novo método validado na GPU' if row['state']=='oom'
                           else '0.8B é somente modelo de teste e não participa do menu principal')}
    paths=[Path(home)/rel for rel in DATASETS[entity]]
    if dataset:
        chosen=next((d for d in training_datasets(home,entity) if d['id']==dataset),None)
        if not chosen:raise ValueError('Dataset não aprovado/vinculado a esta entidade')
        paths=[Path(chosen[k]) for k in ('train','validation')]
    if any(not p.is_file() or p.is_symlink() for p in paths):raise RuntimeError('Corpus original incompleto')
    from .personalizacao import dataset_profile,training_context,artifact_context
    profile,profile_hash=dataset_profile(paths[0],entity)
    extras={'training_context':training_context(entity,profile)}
    if checkpoint:
        if action!='train':raise ValueError('Retomada somente no treino')
        ck=Path(checkpoint).resolve(strict=True)
        if not ck.is_relative_to(_registry(home).resolve()):raise ValueError('Checkpoint fora do laboratório unificado')
        from .versionamento_lora import validate_resume
        validate_resume(ck,Path(row['path']),*paths,entity=entity)
        extras['checkpoint']=str(ck)
        extras['resume_preset']=json.loads((ck.parent.parent/'provenance.json').read_text())['preset']
        extras['training_context']=artifact_context(json.loads((ck.parent.parent/'provenance.json').read_text()),entity,profile)
        if extras['resume_preset'].get('sampling')=='epoch_shuffle_v18' and not options.get('optimization_seconds'):
            raise ValueError('Checkpoint de otimização efetiva exige objetivo cumulativo; use Preparar retomada interrompida ou opções explícitas')
        progress=json.loads((ck/'step.json').read_text()).get('progress',{})
        if options.get('optimization_seconds') and ('optimization_seconds' not in progress or
                progress['optimization_seconds']>=options['optimization_seconds']):
            raise ValueError('Relógio efetivo ausente ou objetivo já alcançado neste checkpoint')
    if action=='evaluate':
        if not candidate:raise ValueError('Selecione o candidato para recarregar')
        ck=Path(candidate).resolve(strict=True)
        if not ck.is_relative_to(_registry(home).resolve()):raise ValueError('Candidato fora do laboratório')
        prov=json.loads((ck/'provenance.json').read_text())
        if prov.get('entity')!=entity or prov.get('base_path')!=str(Path(row['path']).resolve()):
            raise ValueError('Candidato de outra entidade/base')
        holdout=Path(home)/corpus_atual.holdout(entity)
        if not holdout.is_file():raise RuntimeError('Holdout ausente')
        extras.update(candidate=str(ck),holdout=str(holdout),candidate_preset=prov['preset'])
        extras['training_context']=artifact_context(prov,entity,profile)
    measured=row.get('benchmarks',{}).get(entity)
    preset=extras.get('resume_preset') or extras.get('candidate_preset') or (measured['preset'] if measured else {'rank':4})
    if options.get('rank') and options['rank']!=preset['rank'] and checkpoint:
        raise ValueError('Rank mudou durante retomada')
    if options.get('rank'):preset=dict(preset,rank=options['rank'])
    if 'head_cpu' in options:
        if checkpoint and bool(options['head_cpu'])!=bool(preset.get('head_cpu')):raise ValueError('Offload mudou durante retomada')
        preset=dict(preset)
        if options['head_cpu']:preset.update(head_cpu=True,head_cpu_dtype='float32',memory_profile='frozen_bf16_v18_head_cpu')
        else:
            preset.pop('head_cpu',None);preset.pop('head_cpu_dtype',None);preset['memory_profile']='frozen_bf16_v17'
    return {'allowed':True,'model':row,'entity':entity,'minutes':minutes,'action':action,**extras,
            'train':str(paths[0]),'validation':str(paths[1]),
            'dataset':dataset or corpus_atual.dataset_id(entity),
            'preset':preset,'options':options,
            'cognitive_profile_sha256':profile_hash,
            'no_deploy':True,'validation_required':True,
            'warning':'Smoke anterior de 2 passos não comprova estabilidade por minutos; etapa para se ocorrer OOM.'}

def _registry(home):return Path(home)/'controle-laboratorio/treinamento-unificado'

def _job_file(home,jid):
    if not ID_RE.fullmatch(str(jid)):raise ValueError('ID inválido')
    return _registry(home)/'jobs'/(jid+'.json')

def _stamp(pid):
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    except (OSError,IndexError):return None

def _owned_alive(obj,jid):
    pid=obj.get('pid');proc=Path('/proc',str(pid))
    try:
        cmd=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
        return (type(pid) is int and proc.stat().st_uid==os.getuid() and
                obj.get('process_stamp')==_stamp(pid) and
                'laboratorio.treinos_unificados worker' in cmd and '--id '+jid in cmd)
    except (OSError,UnicodeError):return False

def _write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex[:6])
    try:
        with tmp.open('x',encoding='utf8') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:tmp.unlink(missing_ok=True)

def _save_job(home,jid,obj,*,active_only=False):
    """Mesmo registro, lock de transição evita cancelamento sobre job concluído."""
    path=_job_file(home,jid)
    with path.with_suffix('.state.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=json.loads(path.read_text())
        if active_only and current.get('state') not in ('started','running','cancel_requested'):
            return current
        for key in ('cancel_requested_at','operator_escalation'):
            if key in current and key not in obj:obj[key]=current[key]
        if current.get('state')=='cancel_requested' and obj.get('state') in ('started','running'):
            obj['state']='cancel_requested'
        _write_json(path,obj)
    return obj

def details(home,jid):
    f=_job_file(home,jid)
    # Releitura sob o mesmo lock de transição: o worker pode terminar enquanto
    # esta consulta verifica /proc. Nunca sobrescrever seu desfecho persistido.
    with f.with_suffix('.state.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        obj=json.loads(f.read_text())
        active=obj.get('state') in ('started','running','cancel_requested')
        try:age=time.time()-datetime.fromisoformat(obj['created']).timestamp()
        except (KeyError,TypeError,ValueError):age=float('inf')
        missing_owner=(not _owned_alive(obj,jid)) if obj.get('pid') else age>15
        if active and missing_owner:
            obj.update(state='interrupted_unverified',error='Dono ausente; não repetir automaticamente',auto_retry=False)
            _write_json(f,obj)
    log=f.with_suffix('.log')
    if log.is_file():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-6000))
            obj['log_tail']=stream.read().decode('utf8',errors='replace')
        observed=re.findall(r'PASSO (\d+) LOSS ([0-9.]+) SEGUNDOS (\d+)',obj['log_tail'])
        if observed:
            step,loss,seconds=observed[-1]
            obj['progress']={'updates_observed':int(step),'last_training_loss':float(loss),
                             'wall_seconds_observed':int(seconds),'source':'worker_log_not_checkpoint_ack'}
    return obj

def _begin_job(home,jid,*,path=None):
    path=path or _job_file(home,jid)
    with path.with_suffix('.state.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        obj=json.loads(path.read_text())
        if obj.get('state')=='cancel_requested':
            obj.update(state='cancelled',finished=datetime.now(timezone.utc).isoformat())
        elif obj.get('state')=='started':obj['state']='running'
        else:raise RuntimeError('Transição de início inválida; não executar novamente')
        _write_json(path,obj)
    return obj

def jobs(home):
    directory=_registry(home)/'jobs'
    if not directory.is_dir():return []
    result=[]
    for f in sorted(directory.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:15]:
        try:
            x=details(home,f.stem);x.pop('plan',None);x.pop('log_tail',None)
            result.append(x)
        except (ValueError,OSError):pass
    return result

def _is_gpu_worker(raw):
    needles=('laboratorio.professor_moe worker','laboratorio.trabalhador --home',
             'laboratorio.finalizacao_10min worker','treino_micro.py',
             'treino_qwen35_entidade.py','laboratorio.probes_arquiteturas smoke',
             'laboratorio.treinos_unificados worker', 'laboratorio.treino_nf4_curto')
    args=raw.split(b'\0');executable=Path(args[0].decode(errors='replace')).name
    cmd=raw.decode(errors='replace').replace('\0',' ')
    return ((executable.startswith('python') and any(n in cmd for n in needles)) or
            (executable=='llama-server' and '--model' in cmd))

def _busy():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) in (os.getpid(),os.getppid()):continue
        try:raw=(proc/'cmdline').read_bytes()
        except (OSError,PermissionError):continue
        if _is_gpu_worker(raw):
            return str(proc.name)+' '+raw.decode(errors='replace').replace('\0',' ')[:140]
    return None

def start(home,project,model,entity,minutes,action,confirm,checkpoint=None,candidate=None,dataset=None,options=None):
    expected='EXECUTAR_RECUPERACAO_LOCAL' if action=='recover' else 'EXECUTAR_TREINO_UNIFICADO'
    if confirm!=expected:raise ValueError('Confirmacao explícita exigida')
    py=Path(home)/'.venv-rocm/bin/python'
    if not py.is_file():raise RuntimeError('Python ROCm ausente')
    root=_registry(home);root.mkdir(parents=True,exist_ok=True)
    with (root/'start.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if action=='recover':
            from .recuperacao_modelos import plan as recovery_plan,plan_version
            spec=plan_version(home,project,entity,model,options) if options else recovery_plan(home,project,entity,model)
        else:spec=plan(home,model,entity,minutes,action,checkpoint,candidate,dataset,options)
        if not spec['allowed']:raise RuntimeError(spec.get('blocker','Espaço insuficiente para conversão/importação local'))
        if action=='recover' and not spec['needed']:return {'state':'ready','needed':False,'production_changed':False}
        if _busy() or any(j['state'] in ('started','running','cancel_requested') for j in jobs(home)):
            raise RuntimeError('Há outro processo utilizando o laboratório/GPU')
        jid=uuid.uuid4().hex[:16];path=_job_file(home,jid)
        record={'id':jid,'state':'started','created':datetime.now(timezone.utc).isoformat(),
                'model':model,'entity':entity,'action':action,'minutes':minutes,'pid':None,'plan':spec}
        if action=='recover':
            from .versionamento_lora import sha
            record['runtime_code_sha256']={name:sha(Path(project)/'laboratorio'/name)
                for name in ('recuperacao_modelos.py','trabalhador.py','treinos_unificados.py')}
        _write_json(path,record)
        with path.with_suffix('.log').open('xb') as log:
            try:
                proc=subprocess.Popen([str(py),'-u','-m','laboratorio.treinos_unificados','worker',
                     '--home',str(home),'--project',str(project),'--id',jid],cwd=str(project),
                    stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,
                    env={k:v for k,v in os.environ.items() if k!='HSA_OVERRIDE_GFX_VERSION'})
                record['pid']=proc.pid;record['process_stamp']=_stamp(proc.pid);_write_json(path,record)
            except BaseException:
                record['state']='failed';_write_json(path,record);raise
        return {'id':jid,'pid':proc.pid,'state':'started'}

def _review_candidate_after_release(home,jid,obj,spec,report):
    """Fase serial do mesmo job: professor existente, sem lease simultâneo do aluno.

    O job pai continua ativo no supervisor até a crítica terminar. Crash não
    promove nem repete crítica; o PID do professor fica no registro existente.
    """
    from . import professor_moe as teacher
    from .versionamento_lora import auto_promote
    prepared=teacher.prepare_candidate_review(home,spec['candidate'],report,spec['entity'],spec['model']['id'])
    identifier=prepared['id']
    obj.update(phase='behavioral_review',behavior_review_job=identifier)
    _save_job(home,jid,obj,active_only=True)
    cancelled=False
    def request_stop(_sig,_frame):
        nonlocal cancelled
        cancelled=True
    old=signal.signal(signal.SIGTERM,request_stop)
    try:
        # Não perder cancelamento que chegou entre término do aluno e esta fase.
        cancelled=cancelled or json.loads(_job_file(home,jid).read_text()).get('state')=='cancel_requested'
        if prepared['state']=='prepared' and not cancelled:teacher.start(home,identifier,confirm=True)
        deadline=time.monotonic()+900;stop_at=None;stop_error=None;timed_out=False
        while True:
            entry=teacher.detail(home,identifier)
            if entry['state'] not in ('started','running','cancel_requested'):break
            expired=time.monotonic()>=deadline
            timed_out=timed_out or expired
            if (cancelled or expired) and stop_at is None:
                stop_at=time.monotonic()
                try:teacher.stop(home,identifier)
                except (OSError,RuntimeError) as exc:stop_error=type(exc).__name__+': '+str(exc)
            if stop_at is not None and time.monotonic()-stop_at>=90:
                raise TimeoutError('Crítica não encerrou cooperativamente; verificar job '+identifier+
                    ('; '+stop_error if stop_error else '')+'; nenhuma promoção/repetição')
            time.sleep(.5)
        cancelled=cancelled or json.loads(_job_file(home,jid).read_text()).get('state')=='cancel_requested'
        if cancelled:return {'promoted':False,'reasons':['avaliação cancelada'],'production_changed':False},True
        if timed_out:return {'promoted':False,'reasons':['deadline da crítica excedido'],
                             'teacher_job':identifier,'production_changed':False},False
        if entry['state']!='candidate_review_passed':
            return {'promoted':False,'reasons':['crítica '+entry['state']],
                    'teacher_job':identifier,'production_changed':False},False
        return auto_promote(home,spec['candidate'],report,spec['entity'],spec['model']['id']),False
    finally:signal.signal(signal.SIGTERM,old)


def _finish_evaluation(home,jid,obj,spec,report,resources):
    from .rotina_noturna import config as night_policy
    if not night_policy(home)['automatic_data_approval']:
        return dict(promoted=False,reasons=['automacao_ia_desativada_revisao_manual'],production_changed=False),False
    from .versionamento_lora import auto_promote
    promotion=auto_promote(home,spec['candidate'],report,spec['entity'],spec['model']['id'])
    if promotion.get('reasons')==['independent_behavioral_review_missing']:
        # Aluno terminou antes desta chamada. Professor assume os locks/lease.
        resources.close()
        return _review_candidate_after_release(home,jid,obj,spec,report)
    return promotion,False


def worker(home,project,jid):
    home=Path(home).resolve();project=Path(project).resolve();f=_job_file(home,jid)
    obj=json.loads(f.read_text());idstr=str(jid)
    for _ in range(80):
        obj=json.loads(f.read_text())
        if obj.get('pid')==os.getpid():break
        time.sleep(0.1)
    else:raise RuntimeError('PID não confirmado pelo iniciador')
    lock=_registry(home)/'gpu.lock'
    shared=home/'controle-laboratorio/trabalhador.lock'
    shared.parent.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        for path in (shared,lock):
            lk=stack.enter_context(path.open('a+'))
            fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            obj=_begin_job(home,jid)
            if obj['state']=='cancelled':return
            s=obj['plan'];py=home/'.venv-rocm/bin/python'
            if s['action']=='recover':
                # 12/11: o worker é um processo novo, sem PYTHONPATH; a recuperação importa `core` (app/).
                # Sem isto o "Preparar" da Central falhava com "No module named 'core'".
                for extra in (str(project),str(project/'app')):
                    if extra not in sys.path:sys.path.insert(0,extra)
                from .recuperacao_modelos import execute,receipt_path
                def cancel_recovery(*_):raise KeyboardInterrupt('Recuperação cancelada; sem replay automático')
                handlers={sig:signal.signal(sig,cancel_recovery) for sig in (signal.SIGTERM,signal.SIGINT)}
                try:
                    result=execute(home,project,s,jid)
                    obj.update(state='completed',artifact=s.get('receipt_path') or str(receipt_path(home,s['entity'],s['model_id'])),
                        recovery=result,finished=datetime.now(timezone.utc).isoformat())
                    _save_job(home,jid,obj)
                finally:
                    for sig,handler in handlers.items():signal.signal(sig,handler)
                return
            from .personalizacao import dataset_profile,training_context,artifact_context
            profile,current_profile=dataset_profile(s['train'],s['entity'])
            if current_profile!=s.get('cognitive_profile_sha256'):
                raise RuntimeError('Perfil mudou desde o plano; não executar treino divergente')
            current_context=training_context(s['entity'],profile)
            selected=s.get('candidate') or s.get('checkpoint')
            if selected:
                provenance=Path(selected)/'provenance.json' if s.get('candidate') else Path(selected).parent.parent/'provenance.json'
                current_context=artifact_context(json.loads(provenance.read_text()),s['entity'],profile)
            if s.get('training_context') is not None and s['training_context']!=current_context:
                raise RuntimeError('Contexto mudou depois do plano; não executar entrada divergente')
            output=_registry(home)/('reports' if s['action'] in ('smoke','evaluate') else 'adapters')/s['entity']/(idstr+'-'+s['model']['id'])
            if s['action']=='evaluate':output=output.with_suffix('.json');output.parent.mkdir(parents=True,exist_ok=True)
            cmd=[str(py),'-u','-m','laboratorio.treino_nf4_curto', '--model',s['model']['path'],
                 '--train',s['train'],'--validation',s['validation'], '--entity',s['entity'],
                 '--minutes',str(s['minutes']), '--mode',s['action'],
                 '--rank',str(s['preset'].get('rank',4)), '--out',str(output)]
            if s.get('checkpoint'):cmd+=['--resume',s['checkpoint']]
            if s.get('candidate'):cmd+=['--adapter',s['candidate'],'--holdout',s['holdout']]
            for key,value in s.get('options',{}).items():
                if key!='rank':cmd+=['--'+key.replace('_','-'),str(value)]
            if s['preset'].get('head_cpu') and 'head_cpu' not in s.get('options',{}):cmd+=['--head-cpu','1']
            measurement=s['model'].get('benchmarks',{}).get(s['entity'])
            if measurement:cmd+=['--benchmark-signature',json.dumps({k:measurement[k] for k in ('torch','rocm','gpu')})]
            print('EXECUTANDO:',repr(cmd),flush=True)
            # Recarga + base de controle + duas séries de contratos precisam de
            # orçamento explícito. Não elevar a janela de treinamento efetivo.
            timeout=(s['minutes']*90+900) if s['action']=='train' else (s['minutes']*60+900)
            child=subprocess.Popen(cmd,cwd=str(project),start_new_session=True)
            cancelled=False;cancelled_at=None
            def cancel(_sig,_frame):
                nonlocal cancelled,cancelled_at
                cancelled=True
                if cancelled_at is None:cancelled_at=time.monotonic()
                if child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
            old=signal.signal(signal.SIGTERM,cancel)
            try:
                deadline=time.monotonic()+timeout
                while child.poll() is None and time.monotonic()<deadline and (cancelled_at is None or time.monotonic()-cancelled_at<90):
                    try:child.wait(timeout=1)
                    except subprocess.TimeoutExpired:pass
                if child.poll() is None:
                    cancel(signal.SIGTERM,None)
                    # Deadline normal concede graça; cancelamento já aguardou 90s.
                    try:child.wait(timeout=max(1,90-(time.monotonic()-cancelled_at)))
                    except subprocess.TimeoutExpired:
                        # Apenas grupo criado aqui; snapshots não promovidos e
                        # bases somente leitura. Nunca sinalizar terceiros por nome.
                        os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
                    raise TimeoutError('Deadline: executor parado; checkpoints parciais não homologados')
                code=child.returncode
            finally:signal.signal(signal.SIGTERM,old)
            if code:raise RuntimeError('Executor retornou código '+str(code))
            if s['action']=='train':
                if not all((output/file).is_file() for file in ('adapter_model.safetensors','adapter_config.json','micro_result.json')):
                    raise RuntimeError('Executor terminou sem salvar checkpoint completo')
            elif s['action']=='smoke':
                if not output.with_suffix('.json').is_file():
                    raise RuntimeError('Probe terminou sem relatório')
            else:
                if not output.is_file():raise RuntimeError('Avaliação sem relatório')
            obj['artifact']=str(output.with_suffix('.json') if s['action']=='smoke' else output)
            if s['action']=='evaluate' and not cancelled:
                obj['automatic_promotion'],cancelled=_finish_evaluation(home,jid,obj,s,output,stack)
            result_record=json.loads((output/'micro_result.json').read_text()) if s['action']=='train' else {}
            if s['action']=='train':
                obj['result_summary']={k:result_record.get(k) for k in ('steps','updates_this_run',
                    'optimization_seconds','optimization_target_seconds','optimization_target_reached',
                    'early_stopped','termination_reason','after_val_loss')}
            obj['state']='cancelled_checkpointed' if cancelled or result_record.get('cancelled') else 'completed'
            obj['finished']=datetime.now(timezone.utc).isoformat()
            _save_job(home,jid,obj)
        except BaseException as ex:
            obj['state']='failed';obj['error']=type(ex).__name__+': '+str(ex)
            _save_job(home,jid,obj)
            print('FALHA:',obj['error'],flush=True)

def stop(home,jid,confirm):
    if confirm!='PARAR_TREINO_UNIFICADO':raise ValueError('Confirmacao de parada ausente')
    obj=details(home,jid)
    if obj['state'] not in ('started','running'):raise RuntimeError('Job não está executando')
    pid=obj.get('pid');proc=Path('/proc')/str(pid)
    if not isinstance(pid,int) or not proc.is_dir():raise RuntimeError('PID ausente')
    if proc.stat().st_uid!=os.getuid():raise PermissionError('Processo de outro usuário')
    cmd=(proc/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ')
    if 'laboratorio.treinos_unificados worker' not in cmd or ('--id '+jid) not in cmd:
        raise RuntimeError('PID inesperado; recusar sinal')
    if obj.get('process_stamp')!=_stamp(pid):raise RuntimeError('PID reutilizado; recusar sinal')
    obj['state']='cancel_requested';obj['cancel_requested_at']=datetime.now(timezone.utc).isoformat()
    obj['error']='SIGTERM enviado; conferir logs/checkpoints'
    obj.pop('log_tail',None)
    saved=_save_job(home,jid,obj,active_only=True)
    if saved.get('state')!='cancel_requested':return {'id':jid,'signal_sent':False,'state':saved['state']}
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:return {'id':jid,'signal_sent':False,'state':details(home,jid)['state']}
    return {'id':jid,'signal_sent':True}

NIGHT_ACTIVE={'draining','running','stopping','restoring','recovery_required'}

def checkpoint_storage_projection(row,seconds,interval):
    speed=row.get('updates_per_optimization_hour');sizes=row.get('checkpoint_bytes')
    if not speed or not sizes:raise RuntimeError('Benchmark sem throughput/tamanho de checkpoint medidos')
    updates=speed*max(0,seconds)/3600
    return round((math.ceil(updates/interval)+2)*max(sizes)*1.1)

def benchmark_result(measurement):
    """Evidência medida pode ser pasta de adaptador OU arquivo de smoke.

    Ler o formato real sem promover smoke a checkpoint medido. O consumidor
    ainda exige throughput/tamanho de checkpoint antes de autorizar treino longo.
    """
    evidence=Path(measurement['evidence'])
    return json.loads((evidence/'micro_result.json' if evidence.is_dir() else evidence).read_text())

def night_create(home,project,data,awake,*,now=None):
    """Plano noturno durável do supervisor existente, não um segundo scheduler."""
    if data.get('confirm')!='VOU_DORMIR_AUTORIZO_LABORATORIO':
        raise ValueError('Informe explicitamente que vai dormir e autorize a janela')
    window=data.get('window_minutes')
    if type(window) is not int or not 15<=window<=1080:raise ValueError('Janela noturna: 15–1080 minutos')
    tasks=data.get('tasks')
    if not isinstance(tasks,list) or not 1<=len(tasks)<=16:raise ValueError('Selecione 1–16 trabalhos úteis')
    learners=[t for t in tasks if isinstance(t,dict) and t.get('action')=='learn']
    if learners:
        from .rotina_noturna import config as night_policy
        if not night_policy(home)['automatic_data_approval']:
            raise ValueError('Treinamento automático por IA desativado; treinos manuais continuam disponíveis')
    if learners and (len(learners)!=len(tasks) or len({t.get('entity') for t in learners})!=len(learners)):
        raise ValueError('Ciclo automático não pode misturar ações legadas nem duplicar entidade')
    specs=[];projected_storage=0
    for task in tasks:
        if isinstance(task,dict) and task.get('action')=='learn':
            if (set(task)-{'action','entity','model','minutes','examples'} or task.get('entity') not in DATASETS or
                    task.get('model')!=('alistair-4b' if task.get('entity')=='alistair' else 'qwen35-9b') or
                    type(task.get('examples')) is not int or not 8<=task['examples']<=12):
                raise ValueError('Ciclo cognitivo noturno inválido')
            spec=plan(home,task['model'],task['entity'],task.get('minutes'),'train')
            if not spec['allowed'] or not spec['model'].get('benchmarks',{}).get(task['entity']):
                raise RuntimeError('Ciclo exige preset físico medido nesta base/entidade')
            specs.append(dict(task));continue
        if isinstance(task,dict) and task.get('action')=='curate':
            if set(task)-{'action','id','entity','minutes'}:raise ValueError('Campos de curadoria noturna inválidos')
            from .professor_moe import detail
            record=detail(Path(home),task.get('id'))
            if (record['state']!='prepared' or record.get('purpose')=='candidate_review' or record['entity']!=task.get('entity') or
                type(task.get('minutes')) is not int or not 1<=task['minutes']<=60):
                raise ValueError('Professor exige tarefa preparada/autoria/janela válida')
            specs.append(dict(task));continue
        if not isinstance(task,dict) or set(task)-{'model','entity','minutes','action','checkpoint','candidate','dataset','options','candidate_from_task'}:
            raise ValueError('Trabalho noturno inválido')
        if 'candidate_from_task' in task:
            ref=task['candidate_from_task']
            if (type(ref) is not int or ref!=len(specs)-1 or ref<0 or task.get('action')!='evaluate' or
                task.get('candidate') or task.get('checkpoint') or task.get('options') or
                type(task.get('minutes')) is not int or not 1<=task['minutes']<=90 or
                any(specs[ref].get(k)!=task.get(k) for k in ('model','entity','dataset')) or
                specs[ref].get('action')!='train'):raise ValueError('Avaliação exige treino anterior da MESMA base/corpus/entidade')
            spec=plan(home,task.get('model'),task.get('entity'),1,'train',dataset=task.get('dataset'))
        else:
            spec=plan(home,task.get('model'),task.get('entity'),task.get('minutes'),task.get('action'),
                      task.get('checkpoint'),task.get('candidate'),task.get('dataset'),task.get('options'))
        if not spec['allowed']:raise RuntimeError(spec['blocker'])
        if task.get('action')=='smoke':
            if not spec['allowed']:raise RuntimeError(spec.get('blocker','Probe recusado'))
            specs.append(dict(task));continue
        if not spec['model'].get('benchmarks',{}).get(spec['entity']):
            raise RuntimeError('Sessão noturna exige preset medido nesta base/corpus')
        if spec.get('preset',{}).get('rank')!=spec['model']['benchmarks'][spec['entity']]['preset']['rank']:
            raise RuntimeError('Rank solicitado sem benchmark aprovado desta base/corpus; ensaiar primeiro')
        if bool(spec.get('preset',{}).get('head_cpu'))!=bool(spec['model']['benchmarks'][spec['entity']]['preset'].get('head_cpu')):
            raise RuntimeError('Offload solicitado sem benchmark aprovado; ensaiar primeiro')
        options=spec.get('options',{})
        if options.get('optimization_seconds'):
            row=benchmark_result(spec['model']['benchmarks'][spec['entity']])
            elapsed=0
            if task.get('checkpoint'):
                elapsed=json.loads((Path(task['checkpoint'])/'step.json').read_text()).get('progress',{}).get('optimization_seconds',0)
            projected_storage+=checkpoint_storage_projection(row,options['optimization_seconds']-elapsed,options.get('checkpoint_steps',25))
        specs.append(dict(task))
    if projected_storage:
        import shutil
        if shutil.disk_usage(home).free<projected_storage+5*1024**3:
            raise RuntimeError('Espaço insuficiente para checkpoints do plano + 5GiB de reserva; sessão não autorizada')
    if sum((2*(60+t['minutes']+20) if t['action']=='learn' else t['minutes']*(1.25 if t.get('options',{}).get('optimization_seconds') else 1)) for t in specs)+10>window:
        raise ValueError('Reserve dez minutos para drenagem/carga/restauração')
    root=_registry(home)/'nights';root.mkdir(parents=True,exist_ok=True)
    current=root/'current.json'
    if current.exists() and json.loads(current.read_text()).get('state') in NIGHT_ACTIVE:
        raise RuntimeError('Sessão noturna anterior ainda não encerrada')
    now=time.time() if now is None else now
    deadline=now+window*60
    if data.get('absolute_deadline') is not None:
        absolute=data['absolute_deadline']
        if type(absolute) not in (int,float) or not math.isfinite(absolute) or absolute<=now:
            raise ValueError('Prazo absoluto inválido')
        deadline=min(deadline,absolute)
    obj={'id':uuid.uuid4().hex[:16],'state':'draining','authorized_at':now,
         'deadline':deadline,'drain_deadline':now+180,'tasks':specs,'index':0,
         'restore_entities':list(awake),'home':str(Path(home).resolve()),
         'project':str(Path(project).resolve()),'job':None,'history':[],
         'production_weights_changed':False,'auto_retry':False}
    _write_json(current,obj);return obj

def resolve_night_task(home,night,task):
    """Histórico durável é a referência; não adivinhar 'último adaptador' global."""
    result=dict(task)
    if 'candidate_from_task' in result:
        index=result.pop('candidate_from_task')
        if type(index) is not int or index<0 or index!=len(night['history'])-1:
            raise RuntimeError('Treino predecessor exato ainda não concluiu')
        record=details(home,night['history'][index]['id'])
        if (record.get('state')!='completed' or record.get('action')!='train' or
                any(record.get(k)!=task.get(k) for k in ('entity','model')) or
                (task.get('dataset') and record.get('plan',{}).get('dataset')!=task['dataset'])):
            raise RuntimeError('Candidato noturno incorreto/incompleto')
        result['candidate']=record['artifact']
    return result

def long_plan(home):
    """Só prepara e mede previsões; jamais acorda, suspende ou inicia jobs."""
    tasks=[];estimates=[];blockers=[]
    for entity in ('hoshino','lilith'):
        measurement=measured_preset(home,'qwen35-9b',entity)
        if not measurement:blockers.append('Benchmark 9B ausente: '+entity);continue
        evidence=Path(measurement['evidence']);row=benchmark_result(measurement)
        speed=row.get('updates_per_optimization_hour')
        if not speed or not row.get('checkpoint_bytes'):
            blockers.append('Benchmark sem relógio efetivo/checkpoint medido: '+entity);continue
        train_count=row.get('train_examples',722);updates=speed*6
        checkpoint_interval=max(25,min(500,round(speed/3)))  # ~20 min efetivos, condicionado ao disco real.
        options={'optimization_seconds':21600,'checkpoint_steps':checkpoint_interval,'validation_steps':100,'patience':3,
                 'rank':measurement['preset']['rank'],'head_cpu':int(bool(measurement['preset'].get('head_cpu')))}
        before=len(tasks)
        tasks.extend([{'model':'qwen35-9b','entity':entity,'dataset':corpus_atual.dataset_id(entity),
                       'minutes':360,'action':'train','options':options},
                      {'model':'qwen35-9b','entity':entity,'dataset':corpus_atual.dataset_id(entity),
                       'minutes':15,'action':'evaluate','candidate_from_task':before}])
        checkpoints=max(1,len(row.get('checkpoint_bytes',[])))
        checkpoint_cost=row.get('checkpoint_seconds',0)/checkpoints
        # Histórico é cumulativo na retomada; custo é só desta execução.
        observed_checks=sum(h.get('step',0)>row.get('initial_steps',0) for h in row.get('validation_history',[]))
        checks=max(1,row.get('validation_checks_this_run',observed_checks))
        validation_cost=row.get('intermediate_validation_seconds',0)/checks
        if not validation_cost:validation_cost=row.get('validation_seconds',0)/max(2,checks+2)
        overhead=(updates/checkpoint_interval*checkpoint_cost+updates/options['validation_steps']*validation_cost+
                  row.get('load_seconds',0)+row.get('baseline_validation_seconds',validation_cost)+
                  row.get('final_validation_seconds',validation_cost)+row.get('final_adapter_save_seconds',0))
        estimates.append({'entity':entity,'evidence':str(evidence),'updates_6h_projection':round(updates),
            'epochs_6h_projection':round(updates/train_count,2),
            'effective_optimization_minutes':360,
            'training_wall_minutes_projection':round(360+overhead/60,1),
            'final_evaluation_budget_minutes':15,'checkpoint_interval_updates':checkpoint_interval,
            'checkpoint_interval_optimization_seconds':round(checkpoint_interval/speed*3600,1),
            'checkpoint_storage_bytes_projection':checkpoint_storage_projection(row,21600,checkpoint_interval),
            'validation_early_stop_enabled':True,'long_stability_proven':False})
    import shutil
    storage=shutil.disk_usage(home)
    expected=sum(e['checkpoint_storage_bytes_projection'] for e in estimates)
    if storage.free<expected+5*1024**3:blockers.append('Espaço insuficiente para checkpoints + 5GiB de reserva')
    obj={'version':'v1.8','state':'prepared_not_authorized','execution_started':False,
         'requires_explicit_sleep_authorization':True,'allowed':not blockers,'blockers':blockers,
         'tasks':tasks,'estimates':estimates,'window_minutes':1080,'confirm':None,
         'estimated_wall_minutes':round(sum(e['training_wall_minutes_projection']+15 for e in estimates)+10,1),
         'disk_free_bytes':storage.free,'checkpoint_bytes_projection':expected,
         'warning':'Projeção, não homologação de 6h. Early stop pode encerrar antes; qualidade não promovida automaticamente.'}
    if obj['estimated_wall_minutes']>obj['window_minutes']:
        obj['allowed']=False;blockers.append('Duração prevista excede a janela segura do supervisor')
    _write_json(_registry(home)/'plans/12h-prepared.json',obj)
    return obj


def default_cycle_plan(home,*,nightly=False,window_minutes=None,optimization_seconds=None,custom=False,evaluation_minutes_custom=30):
    """Sessão manual única; não liga professor, política diária ou outro scheduler.

    Compatibilidade: teto de 6h/12h de parede. A autorização explícita de seis
    horas efetivas usa optimization_seconds=21600; carga/avaliação são adicionais.
    Os sete adaptadores começam do original, nunca dos candidatos de20min.
    """
    from .versionamento_lora import sha,base_signature
    if window_minutes is None:window_minutes=720 if nightly else 150
    if custom and (not nightly or optimization_seconds is not None or type(window_minutes) is not int or not 120 <= window_minutes <= 1080
                   or type(evaluation_minutes_custom) is not int or not 15 <= evaluation_minutes_custom <= 90):
        raise ValueError('Personalizado: janela de120–1080min, avaliação de15–90min, três originais')
    if not custom and (type(window_minutes) is not int or window_minutes not in ((360,720) if nightly else (150,))):
        raise ValueError('Janela manual: 6h/12h para sete treinos ou150min para a rodada curta')
    effective=optimization_seconds is not None
    if effective and (not nightly or type(optimization_seconds) is not int or optimization_seconds!=21600 or window_minutes!=720):
        raise ValueError('Seis horas efetivas exigem sete treinos e janela adicional de12h de parede')
    # 6h incluem as sete recargas completas. Não fingir seis horas efetivas
    # de updates; reservar45min para carga/drenagem e30min por avaliação.
    train_minutes=15 if nightly and window_minutes==360 else 80 if nightly else 20
    evaluation_minutes=30 if nightly and window_minutes==360 else 15
    if effective:train_minutes=52;evaluation_minutes=30
    if custom:
        evaluation_minutes=evaluation_minutes_custom
        # 05/11: o personalizado treina só os três originais vigentes (9B Hoshino, 9B Lilith, 4B Alistair).
        train_minutes=min(90,(window_minutes-45)//CUSTOM_TRAININGS-evaluation_minutes)
        if train_minutes<1:raise ValueError('Janela insuficiente: reserve45min mais sete avaliações e treinos')
    home=Path(home).resolve();tasks=[];blockers=[]
    models=('yi-6b','qwen25-7b','qwen35-9b','alistair-4b') if nightly and not custom else ('qwen35-9b','alistair-4b')
    for model in models:
        for entity in (('alistair',) if model=='alistair-4b' else ('hoshino','lilith')):
            measurement=measured_preset(home,model,entity)
            if not measurement:
                blockers.append(model+'/'+entity+': falta probe físico do corpus atual');continue
            # O ciclo personalizado é um NOVO experimento dos originais. A
            # reprovação de um candidato descartado não aprova nem impede a
            # geração de outro; seus controles físicos continuam obrigatórios.
            # O plano legado homologado conserva integralmente seu gate.
            if nightly and not custom and model in ('yi-6b','qwen25-7b'):
                adequate=False
                candidates=set()
                for provenance in (_registry(home)/'adapters'/entity).glob('*/provenance.json'):
                    try:
                        prov=json.loads(provenance.read_text());candidate=provenance.parent
                        trained=json.loads((candidate/'micro_result.json').read_text())
                        if (prov.get('entity')==entity and prov.get('base_path')==str((home/MODELS[model][0]).resolve()) and
                            prov.get('base_weights_signature')==base_signature(home/MODELS[model][0]) and
                            prov.get('train_sha256')==sha(home/DATASETS[entity][0]) and
                            prov.get('validation_sha256')==sha(home/DATASETS[entity][1]) and
                            trained.get('steps',0)>=8 and not trained.get('cancelled')):
                            candidates.add(sha(candidate/'adapter_model.safetensors'))
                    except (OSError,ValueError,KeyError,TypeError):continue
                for report in (_registry(home)/'reports'/entity).glob('*-'+model+'.json'):
                    try:
                        row=json.loads(report.read_text());base=row.get('baseline',{})
                        physical=json.loads(report.with_suffix('.hardware.json').read_text())
                        if (row.get('entity')==entity and row.get('physical_reload_verified') is True and
                            row.get('adapter_sha256') in candidates and physical.get('child_exit_code')==0 and physical.get('pressure')==[] and
                            row.get('validation_sha256')==sha(home/DATASETS[entity][1]) and
                            row.get('holdout_sha256')==sha(home/corpus_atual.holdout(entity)) and
                            row.get('behavioral_audit',{}).get('passed') is True and
                            math.isfinite(row['validation_loss']) and math.isfinite(row['holdout_loss']) and
                            row['validation_loss']<=base.get('validation_loss',0)*1.02 and
                            row['holdout_loss']<=base.get('holdout_loss',0)*1.02):adequate=True
                    except (OSError,ValueError,KeyError,TypeError):continue
                if not adequate:blockers.append(model+'/'+entity+': piloto/recarga/comportamento ainda sem aprovação técnica');continue
            count=sum(bool(l.strip()) for l in (home/DATASETS[entity][0]).read_text().splitlines())
            options=dict(checkpoint_steps=50,validation_steps=50,patience=3,
                         rank=measurement['preset']['rank'],head_cpu=int(bool(measurement['preset'].get('head_cpu'))))
            if nightly:options['max_steps']=count*3
            if effective:
                # Divisão inteira exata de21600s; avaliações não gastam esse relógio.
                slot=len(tasks)//2
                options['optimization_seconds']=21600//7+int(slot<21600%7)
                measured=benchmark_result(measurement)
                if not measured.get('updates_per_optimization_hour') or not measured.get('checkpoint_bytes'):
                    blockers.append(model+'/'+entity+': falta benchmark salvo com throughput/checkpoint medidos');continue
            index=len(tasks)
            tasks += [dict(model=model,entity=entity,minutes=train_minutes,action='train',options=options),
                      dict(model=model,entity=entity,minutes=evaluation_minutes,action='evaluate',candidate_from_task=index)]
    result=dict(kind='manual_defaults_cycle',allowed=not blockers,blockers=blockers,tasks=tasks,
        starts_from_original=True,professor_enabled=False,execution_started=False,shutdown=False,
        window_minutes=window_minutes,early_stop=True,epoch_cap=3 if nightly else None,
        train_minutes_per_model=train_minutes,evaluation_minutes_per_model=evaluation_minutes,
        optimization_target_seconds=optimization_seconds,
        loading_and_evaluation_outside_optimization_budget=effective,
        warning='Janela máxima, não promessa de otimização contínua. Parar antes se validação piorar; nenhuma promoção pela IA.')
    result['reserve_minutes']=window_minutes-(CUSTOM_TRAININGS if custom else 7)*(train_minutes+evaluation_minutes) if nightly else None
    if custom:result.update(experimental=True,quality_approved=False,automatic_promotion=False)
    name='defaults-custom-preview.json' if custom else ('defaults-6h-effective-20261016.json' if effective else 'defaults-6h-20261016.json' if window_minutes==360 else 'defaults-night-20261016.json') if nightly else 'defaults-20min-20261015.json'
    _write_json(_registry(home)/'plans'/name,result)
    return result

def resume_night_tasks(home):
    """Preparação explícita após interrupção; nada é reexecutado nesta função."""
    old=night_status(home)
    if old.get('automatic_cycle'):
        raise RuntimeError('Ciclo automático interrompido exige revisar diagnóstico/artefatos; não replay de currículo/treino')
    if not old or old['state'] not in ('completed_with_errors','recovery_required') or _busy():
        raise RuntimeError('Restaurar/encerrar cooperativamente a sessão antes de preparar retomada')
    remaining=[dict(t) for t in old['tasks'][old['index']:]]
    if not remaining:raise RuntimeError('Nenhuma etapa pendente')
    task=remaining[0]
    previous_job=old.get('job') or old.get('stopped_job')
    if previous_job:
        if task.get('action')=='curate':raise RuntimeError('Professor interrompido exige preparar nova proposta, sem replay automático')
        record=details(home,previous_job)
        if any(record.get(k)!=task.get(k) for k in ('entity','model','action')):
            raise RuntimeError('Job interrompido não corresponde à etapa; não avançar nem repetir')
        if record['state']=='completed':
            # Conclusão durable ocorreu antes do supervisor persistir o avanço.
            if task['action']=='train' and len(remaining)>1 and 'candidate_from_task' in remaining[1]:
                remaining[1]['candidate']=record['artifact'];remaining[1].pop('candidate_from_task')
            remaining.pop(0)
        elif task['action']=='train':
            if record['state']!='cancelled_checkpointed':raise RuntimeError('Crash incerto: selecionar checkpoint íntegro manualmente')
            checkpoints=sorted(Path(record['artifact']).joinpath('checkpoints').glob('passo-*'))
            if not checkpoints:raise RuntimeError('Nenhum checkpoint confirmado')
            task['checkpoint']=str(checkpoints[-1])
    for i,t in enumerate(remaining):
        if 'candidate_from_task' in t:
            if i==0:
                ref=t.pop('candidate_from_task');t['candidate']=old['history'][ref]['artifact']
            else:t['candidate_from_task']=i-1
    return remaining

def night_save(home,obj):
    root=_registry(home)/'nights'
    _write_json(root/'current.json',obj)
    _write_json(root/(obj['id']+'.json'),obj)

def night_status(home):
    file=_registry(home)/'nights/current.json'
    return json.loads(file.read_text()) if file.exists() else {'state':'idle'}

def artifacts(home):
    """Inventário somente leitura; parciais identificados, não fingidos estáveis."""
    rows=[];root=_registry(home)/'adapters'
    for manifest in root.glob('*/*/provenance.json'):
        try:
            prov=json.loads(manifest.read_text());directory=manifest.parent
            if prov.get('entity') not in DATASETS:continue
            weights=(directory/'adapter_model.safetensors').is_file()
            rows.append({'path':str(directory),'entity':prov['entity'],'state':prov.get('state') if weights else 'weights_absent',
                         'base':prov.get('base_path'),'preset':prov.get('preset'),
                         'checkpoints':[str(p) for p in sorted((directory/'checkpoints').glob('passo-*')) if (p/'step.json').is_file() and (p/'adapter_model.safetensors').is_file()],
                         'final':weights and (directory/'micro_result.json').is_file()})
        except (OSError,ValueError):continue
    return rows

def supervisor_call(project,path,data=None):
    """Ponte loopback à Central existente. Token nunca vai para log/UI."""
    from urllib.parse import urlsplit
    from urllib.request import Request,urlopen
    parsed=urlsplit((Path(project)/'compartilhado/runtime/launcher/central.url').read_text().strip())
    if parsed.hostname!='127.0.0.1' or not parsed.port or not parsed.fragment:
        raise RuntimeError('Central local não autenticada/disponível')
    base=f'http://127.0.0.1:{parsed.port}'
    req=Request(base+'/api/control/laboratory/night'+path,
                data=json.dumps(data).encode() if data is not None else None,
                headers={'Authorization':'Bearer '+parsed.fragment,'Content-Type':'application/json','Origin':base})
    with urlopen(req,timeout=15) as response:return json.load(response)

def cli():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=('catalog','preview','worker'))
    p.add_argument('--home',type=Path,default=Path.home()/'laboratorio-lora')
    p.add_argument('--project',type=Path,default=Path.home()/'hoshino e lilith')
    p.add_argument('--id');p.add_argument('--model');p.add_argument('--entity');p.add_argument('--minutes',type=int,default=10)
    p.add_argument('--op',default='train')
    a=p.parse_args();home=a.home.resolve()
    if a.action=='catalog':print(json.dumps(home_data(home),ensure_ascii=False,indent=2))
    elif a.action=='preview':print(json.dumps(plan(home,a.model,a.entity,a.minutes,a.op),ensure_ascii=False,indent=2))
    else:worker(home,a.project,a.id)
if __name__=='__main__':cli()
