"""Políticas/adaptadores da sessão existente. Sem loop, scheduler ou banco novos."""
from __future__ import annotations
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid

from . import treinos_unificados as lab, professor_moe as teacher

DEFAULTS = dict(enabled=False, start_time='00:30', timezone='America/Sao_Paulo',
    idle_minutes=30, allow_idle=True, window_minutes=600, start_window_minutes=120,
    train_minutes=10, examples=8, entities=['hoshino','lilith','alistair'],
    shutdown_after=True, automatic_data_approval=False)


def root(home):
    return lab._registry(home)/'nights'


def save(home,name,obj):
    directory=root(home);directory.mkdir(parents=True,exist_ok=True)
    if directory.is_symlink():raise ValueError('Registro noturno por link recusado')
    path=directory/name
    if path.is_symlink():raise ValueError('Registro noturno por link recusado')
    lab._write_json(path,obj);path.chmod(0o600)


def config(home):
    file=root(home)/'policy.json'
    if file.is_symlink():raise ValueError('Configuração por link recusada')
    saved=json.loads(file.read_text()) if file.is_file() else {}
    if not isinstance(saved,dict) or set(saved)-set(DEFAULTS):raise ValueError('Configuração noturna inválida')
    return validate_policy({**copy.deepcopy(DEFAULTS),**saved})


def configure(home,data):
    if data.get('confirm') is not True:raise ValueError('Confirme a política automática/desligamento')
    changes=data.get('settings')
    if not isinstance(changes,dict) or set(changes)-set(DEFAULTS):raise ValueError('Configuração noturna inválida')
    obj=validate_policy({**config(home),**changes})
    file=root(home)/'policy.json'
    if file.is_file():save(home,'policy-backup-'+uuid.uuid4().hex+'.json',json.loads(file.read_text()))
    save(home,'policy.json',obj);return obj


def validate_policy(obj):
    for k in ('enabled','allow_idle','shutdown_after','automatic_data_approval'):
        if type(obj[k]) is not bool:raise ValueError('Opção booleana inválida: '+k)
    limits={'idle_minutes':(1,1440),'window_minutes':(30,1080),'start_window_minutes':(1,180),
            'train_minutes':(1,90),'examples':(8,12)}
    for key,(low,high) in limits.items():
        if type(obj[key]) is not int or not low<=obj[key]<=high:raise ValueError('Limite noturno inválido: '+key)
    if not isinstance(obj['start_time'],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',obj['start_time']):
        raise ValueError('Horário deve ser HH:MM')
    if not isinstance(obj['timezone'],str):raise ValueError('Fuso horário inválido')
    ZoneInfo(obj['timezone'])
    if (not isinstance(obj['entities'],list) or not obj['entities'] or len(set(obj['entities']))!=len(obj['entities'])
            or set(obj['entities'])-set(DEFAULTS['entities'])):raise ValueError('Entidades noturnas inválidas')
    return obj


def note_sleep(home,text,source_id,*,now=None):
    """Somente fala explícita do usuário no endpoint humano; não interpretar LLM."""
    if not isinstance(text,str) or not re.fullmatch(r'\s*(?:boa noite[,!. ]*)?(?:eu )?(?:vou dormir(?: agora)?|estou indo dormir)[.! ]*',text,re.I):return False
    now=time.time() if now is None else now
    save(home,'sleep-permission.json',dict(at=now,source_id=source_id,expires=now+12*3600))
    return True


def read_permission(home):
    file=root(home)/'sleep-permission.json'
    if file.is_symlink():raise ValueError('Permissão por link recusada')
    return json.loads(file.read_text()) if file.is_file() else {}


def schedule_key(policy,now):
    """Janela civil local, incluindo horários que atravessam meia-noite."""
    from datetime import timedelta
    local=datetime.fromtimestamp(now,ZoneInfo(policy['timezone']))
    hour,minute=map(int,policy['start_time'].split(':'))
    start=local.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if local<start:start-=timedelta(days=1)
    return start.date().isoformat() if 0<=now-start.timestamp()<policy['start_window_minutes']*60 else None


def agenda(project,*,now=None):
    """Nunca inicializa/migra bancos; horário ilegível impede desligamento."""
    from app.entity_paths import carregar_entidade
    from core.history import local_datetime
    now=time.time() if now is None else now
    result=[]
    for entity in DEFAULTS['entities']:
        file=carregar_entidade(Path(project),entity).memory/'sqlite'/(entity+'.db')
        if not file.is_file() or file.is_symlink():raise RuntimeError('Agenda indisponível: '+entity)
        with closing(sqlite3.connect(file.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table,status in (('goals','active'),('reminders','pending')):
                if table not in tables:
                    # Alistair não possui pipeline de goals; ausência legítima.
                    if entity=='alistair':continue
                    raise RuntimeError('Tabela de agenda ausente: '+entity+'/'+table)
                for row in db.execute(f'SELECT id,due_at FROM {table} WHERE status=?',(status,)):
                    due=None if not row['due_at'] else local_datetime(row['due_at']).timestamp()
                    result.append(dict(entity=entity,table=table,id=row['id'],due=due,due_now=due is not None and due<=now+120))
    return result


def guard(supervisor,policy,*,now=None,finish=False,collector_stopped=False):
    """Todas as sondas devem ser atuais; swap não é considerado RAM disponível."""
    from core import world_state,resource_manager,job_bus,interentity,gpu_metrics
    now=time.time() if now is None else now
    values=world_state.fresh_values(world_state.snapshot(now=now))
    health=values.get('collector.health') or {}
    if not health.get('running') and not collector_stopped:raise RuntimeError('Sondas de presença não disponíveis')
    idle=values.get('desktop.idle_seconds')
    if type(idle) not in (int,float) or idle<60:raise RuntimeError('Usuário ativo ou ociosidade desconhecida')
    if finish and idle<policy['idle_minutes']*60:raise RuntimeError('Usuário voltou: desligamento cancelado')
    load=values.get('system.load1');cpus=values.get('system.cpu_count')
    if type(load) not in (int,float) or not cpus or load>max(1,cpus*.25):raise RuntimeError('PC ocupado/CPU desconhecida')
    media=values.get('desktop.media')
    if media and (not isinstance(media,dict) or str(media.get('estado','')).casefold() not in ('paused','stopped','pausado','parado')):
        raise RuntimeError('Reprodução externa ativa ou estado desconhecido')
    metrics=gpu_metrics.snapshot()
    if not metrics.get('known') or not metrics.get('stable') or metrics.get('utilization') is None or metrics['utilization']>10:
        raise RuntimeError('GPU ocupada ou medição incerta')
    awake=any((interentity.presence(e) or {}).get('status') in ('awake','starting','stopping') for e in DEFAULTS['entities'])
    if finish and awake:raise RuntimeError('Ainda existe entidade/processo acordado')
    if not awake and metrics['used_bytes']>metrics['total_bytes']-resource_manager.gpu_policy()['margin_bytes']-4*1024**3:
        raise RuntimeError('Sem VRAM segura para manutenção')
    if gpu_metrics.ram_available()<16*1024**3:raise RuntimeError('RAM disponível insuficiente; swap não conta')
    if shutil.disk_usage(supervisor.laboratory_home).free<10*1024**3:raise RuntimeError('Disco sem reserva segura')
    if lab._busy() or resource_manager.status() or job_bus.status(active_only=True):raise RuntimeError('Trabalho/lease ainda ativo ou incerto')
    if resource_manager.gpu_state().get('queue'):raise RuntimeError('Há tarefas esperando GPU')
    if interentity.pending_wake_requests():raise RuntimeError('Pedido de acordar pendente')
    for entity in DEFAULTS['entities']:
        if interentity.inbox(entity,limit=1,mark_delivered=False,include_held=True):
            raise RuntimeError('Mensagem pendente/incerta: '+entity)
    tasks=agenda(supervisor_project(supervisor),now=now)
    if not finish and any(t['due'] is None or t['due_now'] for t in tasks):
        raise RuntimeError('Entidade possui obrigação na janela noturna')
    return dict(idle=idle,agenda=tasks,gpu=metrics)


def supervisor_project(supervisor):
    # Testes têm root próprio. Produção recebe ROOT explícito no Supervisor.
    return Path(supervisor.project)


def auto_tick(supervisor,*,now=None):
    now=time.time() if now is None else now
    policy=config(supervisor.laboratory_home)
    if not policy['enabled']:
        supervisor.night_readiness={'state':'disabled'};return
    if not policy['automatic_data_approval']:
        supervisor.night_readiness={'state':'ai_training_disabled'};return
    if supervisor.closing or supervisor.laboratory_maintenance:return
    key=schedule_key(policy,now)
    if not key or getattr(supervisor,'night_next_probe',0)>now:return
    supervisor.night_next_probe=now+30
    old=lab.night_status(supervisor.laboratory_home)
    if old.get('schedule_key')==key:
        supervisor.night_readiness={'state':'already_processed','night_id':old['id'],'night_state':old['state']}
        return  # uma noite por data, inclusive falha/crash
    try:
        permission=read_permission(supervisor.laboratory_home)
        state=guard(supervisor,policy,now=now)
        if not (permission.get('at',0)<=now<permission.get('expires',0)) and not (policy['allow_idle'] and state['idle']>=policy['idle_minutes']*60):
            raise RuntimeError('Sem declaração de sono/ociosidade autorizada suficiente')
        tasks=[];skipped=[]
        future=[t['due'] for t in state['agenda'] if t['due'] is not None]
        window=policy['window_minutes'] if not future else min(policy['window_minutes'],int((min(future)-now-300)/60))
        # Quem não coube na última janela vem primeiro. Sem outra fila/scheduler.
        deferred={s['entity'] for s in old.get('skipped',[])}
        ordered=sorted(policy['entities'],key=lambda e:e not in deferred)
        for entity in ordered:
            model='alistair-4b' if entity=='alistair' else 'qwen35-9b'
            spec=lab.plan(supervisor.laboratory_home,model,entity,policy['train_minutes'],'train')
            if not spec['allowed'] or not spec['model'].get('benchmarks',{}).get(entity):
                skipped.append(dict(entity=entity,reason=spec.get('blocker','Preset físico ausente')));continue
            if (len(tasks)+1)*2*(60+policy['train_minutes']+20)+10>window:
                skipped.append(dict(entity=entity,reason='Janela/agenda não comporta o orçamento seguro'));continue
            tasks.append(dict(action='learn',entity=entity,model=model,minutes=policy['train_minutes'],examples=policy['examples']))
        if not tasks:raise RuntimeError('Nenhum treino possui preset físico seguro')
        obj=supervisor.authorize_night(dict(confirm='VOU_DORMIR_AUTORIZO_LABORATORIO',window_minutes=window,tasks=tasks))
        obj.update(automatic_cycle=True,schedule_key=key,policy=policy,skipped=skipped,learning={},
                   authorization_source='explicit_sleep' if permission.get('at',0)<=now<permission.get('expires',0) else 'idle_policy')
        lab.night_save(supervisor.laboratory_home,obj)
        supervisor.night_readiness={'state':'authorized','night_id':obj['id'],'source':obj['authorization_source']}
    except (OSError,ValueError,RuntimeError,sqlite3.Error) as exc:
        supervisor.night_readiness={'state':'waiting','reason':str(exc),'at':now}


def history_snapshot(home,project,entity,limit=12):
    """Retém todos os IDs usados; backlog fica para a próxima noite, não some."""
    from app.entity_paths import carregar_entidade
    from core.central_control import redact
    from core import interentity
    paths=carregar_entidade(Path(project),entity)
    path=paths.runtime/'history.sqlite3' if entity!='alistair' else paths.memory/'sqlite'/'alistair.db'
    if path.is_symlink():raise ValueError('Histórico por link recusado')
    previous=root(home)/('history-'+entity+'.json')
    cursor=json.loads(previous.read_text()).get('cursor',0) if previous.is_file() else 0
    rows=[];links=[];last=cursor;skipped=[]
    if path.is_file():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            if entity=='alistair':
                names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                outputs=db.execute('SELECT rowid AS seq,* FROM alistair_turns WHERE rowid>? ORDER BY rowid LIMIT ?',(cursor,limit)).fetchall() if 'alistair_turns' in names else []
                for out in outputs:
                    last=out['seq'];a,b=redact(out['input']),redact(out['output'])
                    if not a or not b or max(len(a),len(b))>2400:
                        skipped.append(dict(id=out['source_id'],reason='Conteúdo excessivo/incompleto'));continue
                    sid=f'hist:alistair:{out["seq"]}:{hashlib.sha256(out["source_id"].encode()).hexdigest()[:12]}'
                    record=dict(entity=entity,source_id=sid,messages=[dict(role='user',content='['+out['sender']+'] '+a),dict(role='assistant',content=b)])
                    turn_id='turn-alistair-'+hashlib.sha256(out['source_id'].encode()).hexdigest()[:16]
                    feedback=interentity.human_feedback_for_turn(entity,turn_id,out['output'])
                    if feedback:record['human_feedback']=redact(feedback)
                    rows.append(record)
                    links.append(dict(source_id=sid,message_id=out['source_id'],sender=out['sender'],timestamp=out['created_at'],observer=entity))
            else:
                outputs=db.execute("SELECT rowid AS seq,* FROM messages WHERE rowid>? AND direction='out' AND role='assistant' ORDER BY rowid LIMIT ?",(cursor,limit)).fetchall()
            for out in ([] if entity=='alistair' else outputs):
                last=out['seq'];meta=json.loads(out['metadata'] or '{}')
                inputs=db.execute("SELECT * FROM messages WHERE direction='in' AND turn_id=? AND turn_id<>'' ORDER BY rowid",(out['turn_id'],)).fetchall()
                if not inputs:
                    refs=meta.get('input_sources',[])
                    if not refs and out['turn_id']:
                        # Legado: correlação já existente nos eventos, sem adivinhar
                        # mensagens vizinhas ou alterar registros antigos.
                        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        if 'events' in tables:
                            for event in db.execute('SELECT data FROM events WHERE turn_id=? ORDER BY rowid LIMIT 30',(out['turn_id'],)):
                                refs=json.loads(event['data'] or '{}').get('input_sources',[])
                                if refs:break
                    for ref in refs:
                        if ref.get('ouvinte_id')!=entity or not ref.get('history_id'):continue
                        item=db.execute("SELECT * FROM messages WHERE id=? AND direction='in'",(ref['history_id'],)).fetchone()
                        if item is not None and all(m['id']!=item['id'] for m in inputs):inputs.append(item)
                if not inputs or meta.get('observer_entity')!=entity or meta.get('private') or meta.get('kind')=='diary':
                    skipped.append(dict(id=out['id'],reason='Sem autoria/turno público verificável'));continue
                msgs=[];refs=[]
                for message in [*inputs,out]:
                    source=json.loads(message['metadata'] or '{}')
                    if source.get('observer_entity')!=entity or source.get('private') or source.get('kind')=='diary':break
                    text=redact(message['content'])
                    # Não truncar contexto e inventar um exemplo aprovado.
                    if not text or len(text)>2500:break
                    role='assistant' if message['direction']=='out' else 'user'
                    if role=='user':text='['+(message['person_name'] or message['role'])+'] '+text
                    if len(text)>2500:break
                    msgs.append(dict(role=role,content=text))
                    refs.append({k:message[k] for k in ('id','ts','direction','role','person_id','person_name','turn_id','session_id','channel')})
                else:
                    if 2<=len(msgs)<=12:
                        sid=f'hist:{entity}:{out["seq"]}:{hashlib.sha256(out["id"].encode()).hexdigest()[:12]}'
                        record=dict(entity=entity,source_id=sid,messages=msgs)
                        feedback=interentity.human_feedback_for_turn(entity,out['turn_id'],out['content'])
                        if feedback:record['human_feedback']=redact(feedback)
                        rows.append(record);links.append(dict(source_id=sid,messages=refs));continue
                skipped.append(dict(id=out['id'],reason='Conteúdo privado/excessivo/incompleto'))
    report=dict(entity=entity,cursor=last,previous_cursor=cursor,included=len(rows),links=links,skipped=skipped,read_only=True,database=str(path))
    name=f'{entity}-night-history-{uuid.uuid4().hex}.jsonl'
    if len(rows)>=2:
        directory=teacher.source_dir(Path(home));directory.mkdir(parents=True,exist_ok=True)
        fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n');stream.flush();os.fsync(stream.fileno())
        report['snapshot']=name
    save(home,'history-scan-'+entity+'-'+uuid.uuid4().hex+'.json',report)
    return report


def approve_data(home,jid,dataset):
    """Automação explicitamente habilitada; desativar não impede curadoria manual."""
    if not config(home)['automatic_data_approval']:
        raise RuntimeError('Treinamento automático por IA desativado; usar curadoria manual')
    obj=teacher.detail(Path(home),jid);proposal=obj.get('proposal_data',{});audit=proposal.get('quality_audit',{})
    examples=proposal.get('examples',[])
    if any(teacher.human_decision(proposal,e)=='rejected' for e in examples):
        raise RuntimeError('Currículo contém reprovação humana; automação não pode sobrescrevê-la')
    human_required=proposal.get('requires_human_curation') is True or proposal.get('generation_version')=='v1.12'
    if human_required and any(teacher.human_decision(proposal,e)!='approved' for e in examples):
        raise RuntimeError('Curadoria humana por exemplo pendente; notas do professor não a substituem')
    if (obj.get('state')!='proposed' or obj.get('purpose')=='candidate_review' or
        audit.get('passed') is not True or audit.get('complete_batches') is not True or
        audit.get('filter_version')!=teacher.QUALITY_FILTER_VERSION or not 8<=len(examples)<=12 or len(audit.get('categories',[]))<4):
        raise RuntimeError('Currículo incompleto/legado/sem diversidade: não treinar')
    reviews=[r for batch in audit.get('teacher_semantic_reviews',[]) for r in batch.get('reviews',[])]
    ids={e['source_id'] for e in examples}
    if not ids.issubset({r.get('source_id') for r in reviews if not r.get('concerns') and teacher.review_consistent(r)}):
        raise RuntimeError('Currículo sem crítica semântica completa')
    hardware=Path(home)/teacher.ROOT_REL/'metricas'/(jid+'.json')
    measured=json.loads(hardware.read_text()) if hardware.is_file() and not hardware.is_symlink() else {}
    if (measured.get('pressure')!=[] or not measured.get('samples') or
            measured.get('margin_bytes',0)<768*1024**2 or not measured.get('after',{}).get('known')):
        raise RuntimeError('Currículo sem telemetria física íntegra')
    # Mesmo tokenizador/template/limite do runner. JSON completo não significa
    # que um diálogo de quatro falas cabe no treino de 256 tokens.
    token_stats=token_budget(home,obj,examples)
    result=teacher.approved_export(Path(home),jid,sorted(ids),dataset,require_decisions=human_required)
    file=Path(home)/'datasets-importados'/result['dataset'].split(':')[1]/'origem_professor.json'
    marker=json.loads(file.read_text());marker.update(approval=(
        'assisted_curated_night_quality_gates_v1' if marker.get('assisted_approved_count',0)>0 else
        'human_curated_night_quality_gates_v1') if human_required else 'automatic_night_quality_gates_v1',
        human_approved=marker.get('human_approved',human_required),requires_manual_training=False,token_budget=token_stats)
    teacher._write(file,marker)
    return result


def token_budget(home,obj,examples):
    from transformers import AutoTokenizer
    from .treino_nf4_curto import tokenize
    from .personalizacao import profile_for_job,training_identity
    model='alistair-4b' if obj['entity']=='alistair' else 'qwen35-9b'
    path=Path(home)/lab.MODELS[model][0]
    tokenizer=AutoTokenizer.from_pretrained(str(path),local_files_only=True,trust_remote_code=False)
    profile,_=profile_for_job(home,obj)
    identity=training_identity(obj['entity'],profile)
    lengths=[]
    for example in examples:
        result=tokenize(tokenizer,example['messages'],identity)
        if result is None:raise RuntimeError('Diálogo excede template/256 tokens do runner; refazer concisamente, sem truncar')
        lengths.append(len(result[0]))
    return dict(model=model,context_limit=256,max_tokens=max(lengths),examples=len(lengths),truncated=0)


def cumulative_dataset(home,entity,stable):
    """A base HF é intacta; reutilizar o corpus da estável, não candidato reprovado."""
    from .corpus_atual import dataset_id
    canonical=dataset_id(entity)
    if not stable.get('available'):return canonical
    from .versionamento_lora import sha
    folder=stable.get('snapshot') or stable.get('candidate')
    if not folder:raise RuntimeError('Versão estável sem origem de currículo')
    manifest=Path(folder)/'provenance.json'
    if manifest.is_symlink():raise RuntimeError('Proveniência estável por link recusada')
    prov=json.loads(manifest.read_text())
    if prov.get('entity')!=entity:raise RuntimeError('Currículo estável de outra entidade')
    train=Path(prov['train_path'])
    if not train.is_file() or train.is_symlink() or sha(train)!=prov.get('train_sha256'):
        raise RuntimeError('Corpus da última estável mudou/está ausente; não esquecer silenciosamente')
    found=next((d for d in lab.training_datasets(home,entity) if Path(d['train']).resolve()==train.resolve()),None)
    if not found:raise RuntimeError('Corpus da estável não está entre os dados aprovados desta entidade')
    validation=Path(found['validation'])
    if validation.is_symlink() or sha(validation)!=prov.get('validation_sha256'):
        raise RuntimeError('Validação da estável mudou; treino recusado')
    return found['id']


def learn_tick(supervisor,task,now):
    """Uma transição por tick. Worker terminal + GPU liberada antes do seguinte."""
    home=supervisor.laboratory_home;night=supervisor.night;entity=task['entity']
    if not config(home)['automatic_data_approval']:
        night.update(state='stopping',error='Treinamento automático por IA desativado')
        return  # supervisor existente pede checkpoint/encerra o job owned
    state=night.setdefault('learning',{}).setdefault(entity,dict(phase='prepare',attempt=1,failures=[]))
    if lab._busy() and not night.get('job'):return
    phase=state['phase'];jid=night.get('job')
    if jid:
        record=teacher.detail(home,jid) if night['job_kind']=='teacher' else lab.details(home,jid)
        if record['state'] in ('started','running','cancel_requested'):return
        if lab._busy():return
        night['history'].append(dict(id=jid,kind=night['job_kind'],entity=entity,state=record['state'],phase=phase,artifact=record.get('artifact')))
        night['job']=None
        if phase=='curate' and record['state']=='proposed':
            state['teacher_job']=jid;state['phase']='approve';return
        if phase=='train' and record['state']=='completed':
            state['candidate']=record['artifact'];state['phase']='evaluate';return
        if phase=='evaluate' and record['state']=='completed' and record.get('automatic_promotion',{}).get('promoted') is True:
            state.update(phase='done',stable=record['automatic_promotion']);night['index']+=1
            if state.get('history_scan'):save(home,'history-'+entity+'.json',state['history_scan'])
            return
        reason=record.get('automatic_promotion',{}).get('reasons') or record.get('failed_batches') or record.get('error') or record['state']
        state['failures'].append(dict(job=jid,phase=phase,reason=reason))
        # Nunca repetir crash/cancelamento/estado incerto, hardware OOM ou timeout.
        quality_failure=record['state']=='needs_revision' or bool(record.get('failed_batches')) or bool(record.get('automatic_promotion',{}).get('reasons'))
        retry=(quality_failure and record['state'] in ('needs_revision','failed','completed') and phase in ('curate','evaluate') and
               state['attempt']==1 and 'interrupted' not in str(reason) and not re.search(r'oom|timeout|cancel|memória|memory',str(reason),re.I) and
               now+(60+task['minutes']+20)*60<night['deadline'])
        if retry:
            state.update(phase='prepare',attempt=2,feedback={'previous_failure':reason,'correction':'Novo currículo, contextos mais concretos, limites e exceções explícitos; não repetir respostas reprovadas.'})
        else:
            from .versionamento_lora import stable_status
            current=stable_status(home,entity,task['model'])
            # Promoção reprovada não publica; não executar rollback cego da estável saudável.
            if current!=state.get('stable_before'):raise RuntimeError('Registro estável mudou inesperadamente; recuperar manualmente')
            state.update(phase='failed',stable_retained=bool(current.get('available')),original_retained=not current.get('available'))
            night.setdefault('failures',[]).append(dict(entity=entity,reasons=state['failures'],retry_next_night=True))
            night['index']+=1
        return
    if phase=='prepare':
        from .personalizacao import capture_profile
        from .versionamento_lora import stable_status
        if state['attempt']==1:state['stable_before']=stable_status(home,entity,task['model'])
        profile=capture_profile(home,supervisor_project(supervisor),entity,confirm=True)
        scan=history_snapshot(home,supervisor_project(supervisor),entity,limit=task['examples'])
        dataset=cumulative_dataset(home,entity,state['stable_before'])
        # O histórico orienta lacunas, não respostas-alvo nem fatos a memorizar.
        prepared=teacher.prepare_from_dataset(home,entity,dataset,task['examples'],profile=profile['name'])['prepared']
        prepared.update(improvement_feedback=state.get('feedback'),case_offset=4 if state['attempt']==2 else 0,
                        history_analysis=scan,night_id=night['id'])
        if scan.get('snapshot'):
            prepared['history_snapshot']=scan['snapshot']
            prepared['history_snapshot_sha256']=hashlib.sha256((teacher.source_dir(home)/scan['snapshot']).read_bytes()).hexdigest()
        teacher._write(teacher.job_file(home,prepared['id']),prepared)
        state.update(phase='curate',dataset=dataset,history_scan=scan)
        result=teacher.start(home,prepared['id'],confirm=True);night.update(job=result['id'],job_kind='teacher')
    elif phase=='approve':
        try:out=approve_data(home,state['teacher_job'],state['dataset'])
        except RuntimeError as exc:
            from .versionamento_lora import stable_status
            state['failures'].append(dict(phase='approve',reason=str(exc)))
            current=stable_status(home,entity,task['model'])
            if current!=state['stable_before']:raise RuntimeError('Registro estável alterado durante reprovação')
            state.update(phase='failed',original_retained=not current.get('available'),stable_retained=bool(current.get('available')))
            night.setdefault('failures',[]).append(dict(entity=entity,reasons=state['failures'],retry_next_night=True));night['index']+=1;return
        state.update(dataset=out['dataset'],phase='train')
    elif phase=='train':
        result=lab.start(home,supervisor_project(supervisor),task['model'],entity,task['minutes'],'train',
                         'EXECUTAR_TREINO_UNIFICADO',dataset=state['dataset'])
        night.update(job=result['id'],job_kind='training')
    elif phase=='evaluate':
        result=lab.start(home,supervisor_project(supervisor),task['model'],entity,20,'evaluate',
                         'EXECUTAR_TREINO_UNIFICADO',candidate=state['candidate'],dataset=state['dataset'])
        night.update(job=result['id'],job_kind='training')


def finish(supervisor,now):
    """Decide restauração/desligamento; não desliga dentro do tick nem do teste."""
    night=supervisor.night;policy=night['policy']
    try:scheduled=agenda(supervisor_project(supervisor),now=now)
    except (OSError,ValueError,RuntimeError,sqlite3.Error) as exc:
        night['shutdown_blocked']='Agenda não verificável: '+type(exc).__name__;return False
    if scheduled:
        night['shutdown_blocked']='Agenda pendente';night['scheduled_tasks']=scheduled
        night['restore_entities']=sorted(set(night['restore_entities'])|{t['entity'] for t in scheduled})
        return False
    if not policy['shutdown_after'] or supervisor.closing:return False
    try:guard(supervisor,policy,now=now,finish=True)
    except (RuntimeError,OSError,ValueError) as exc:
        night['shutdown_blocked']=str(exc);return False
    night.update(poweroff_state='awaiting_cooperative_shutdown',finished=now)
    supervisor.night_poweroff_requested=True
    return True


def poweroff(supervisor):
    """Após shutdown completo da Central. Comando fixo; sem sudo/senha/retry."""
    import subprocess
    night=supervisor.night
    if night.get('poweroff_state')!='awaiting_cooperative_shutdown':
        return dict(accepted=False,verified=False,error='Desligamento não autorizado ou já tentado; sem replay')
    try:
        state=guard(supervisor,night['policy'],finish=True,collector_stopped=True)
        if state['agenda']:raise RuntimeError('Agenda apareceu antes do desligamento')
        night['poweroff_state']='requested_unverified';lab.night_save(supervisor.laboratory_home,night)
        result=subprocess.run(['/usr/bin/systemctl','poweroff','--no-block','--no-ask-password'],stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,check=False)
        if result.returncode:raise RuntimeError('Sistema recusou desligamento: '+str(result.returncode))
        return dict(accepted=True,verified=False)
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        night.update(poweroff_state='unconfirmed_no_retry',poweroff_error=str(exc))
        lab.night_save(supervisor.laboratory_home,night)
        return dict(accepted=False,verified=False,error=str(exc))
