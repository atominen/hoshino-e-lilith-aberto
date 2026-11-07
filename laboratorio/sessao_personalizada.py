"""Sessão única no supervisor existente; nunca um segundo worker/scheduler.

Datas absolutas, evidências pinadas e intenção persistida antes da partida.
Falha ou reinício durante uma tentativa nunca autoriza replay.
"""
import hashlib
import json
import shutil
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from . import treinos_unificados as lab
from . import corpus_atual

ZONE=ZoneInfo('America/Sao_Paulo')

def bounds(data):
    values=[]
    for key in ('starts_at','ends_at'):
        value=datetime.fromisoformat(str(data.get(key,'')))
        if value.tzinfo is None:value=value.replace(tzinfo=ZONE)
        values.append(value.timestamp())
    start,end=values
    if end<=start or (end-start)%60:raise ValueError('Datas inválidas; use minutos inteiros')
    return start,end,int((end-start)//60)

def fingerprint(home,tasks):
    from .versionamento_lora import sha,base_signature
    from .personalizacao import training_context
    home=Path(home)
    sources={}
    for task in tasks:
        m,e=task['model'],task['entity']
        base=home/lab.MODELS[m][0]
        sources[m+'/'+e]=dict(base=base_signature(base),config=sha(base/'config.json'),
            train=sha(home/lab.DATASETS[e][0]),validation=sha(home/lab.DATASETS[e][1]),
            holdout=sha(home/corpus_atual.holdout(e)),
            context=training_context(e))
    sources['runner']={name:sha(Path(__file__).with_name(name)) for name in
        ('treino_nf4_curto.py','treinos_unificados.py','personalizacao.py')}
    return hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()

def physical_readiness(home,result):
    """Exige saída física limpa e dimensiona disco a partir de medições reais."""
    projected=0
    for task in result['tasks']:
        if task['action']!='train':continue
        key=task['model']+'/'+task['entity']
        try:
            measurement=lab.measured_preset(home,task['model'],task['entity'])
            evidence=Path(measurement['evidence'])
            physical=json.loads((evidence/'hardware_metrics.json' if evidence.is_dir() else evidence.with_suffix('.hardware.json')).read_text())
            row=lab.benchmark_result(measurement)
            if physical.get('child_exit_code')!=0 or physical.get('pressure')!=[] or row.get('cancelled'):
                raise ValueError('medição física não encerrou limpa')
            if task['model']=='yi-6b' and not measurement['preset'].get('head_cpu'):
                raise ValueError('Yi exige offload CPU medido')
            projected+=lab.checkpoint_storage_projection(row,task['minutes']*60,task['options']['checkpoint_steps'])
        except (OSError,KeyError,ValueError,TypeError,RuntimeError) as exc:
            result['blockers'].append(key+': '+str(exc))
    result['projected_checkpoint_bytes']=projected
    result['disk_reserve_bytes']=5*1024**3
    result['disk_free_bytes']=shutil.disk_usage(home).free
    if result['disk_free_bytes']<projected+result['disk_reserve_bytes']:
        result['blockers'].append('Disco insuficiente para checkpoints projetados + reserva5GiB')
    result['allowed']=not result['blockers'] and len(result['tasks'])==2*lab.CUSTOM_TRAININGS
    return result

def build_plan(home,data):
    _,_,minutes=bounds(data)
    return physical_readiness(home,lab.default_cycle_plan(home,nightly=True,window_minutes=minutes,custom=True,
        evaluation_minutes_custom=data.get('evaluation_minutes',30)))

def preview(home,data):
    start,end,minutes=bounds(data)
    result=build_plan(home,data)
    result.update(starts_at=start,ends_at=end,timezone=str(ZONE))
    if start<=time.time():result['blockers'].append('Horário inicial já passou; não iniciar atrasado')
    result['allowed']=not result['blockers'] and len(result['tasks'])==2*lab.CUSTOM_TRAININGS
    result['fingerprint']=fingerprint(home,result['tasks'])
    return result

def path(home):return lab._registry(home)/'nights'/'scheduled-once.json'

def cancel(supervisor,data):
    if data.get('confirm') is not True:raise ValueError('Confirme o cancelamento')
    with supervisor.lock:
        p=path(supervisor.laboratory_home)
        row=json.loads(p.read_text())
        if row['state']!='scheduled':raise ValueError('Não está pendente; consulte a sessão, sem cancelar worker implicitamente')
        row['state']='cancelled';lab._write_json(p,row)
        lab._write_json(p.with_name('schedule-'+row['id']+'.json'),row)
        return row

def schedule(supervisor,data):
    if data.get('confirm')!='AGENDAR_TRES_ORIGINAIS':raise ValueError('Confirme a sessão única')
    with supervisor.lock:
        if supervisor.closing or supervisor.laboratory_maintenance:raise ValueError('Supervisor ocupado')
        p=path(supervisor.laboratory_home)
        if p.exists() and json.loads(p.read_text()).get('state') in ('scheduled','attempting','started'):
            raise ValueError('Sessão já registrada; não duplicar')
        plan=preview(supervisor.laboratory_home,data)
        if not plan['allowed']:raise ValueError('; '.join(plan['blockers']))
        record=dict(id=uuid.uuid4().hex[:16],state='scheduled',request=data,plan=plan,session_id=None)
        lab._write_json(p,record)
        lab._write_json(p.with_name('schedule-'+record['id']+'.json'),record)
        return record

def tick(supervisor):
    p=path(supervisor.laboratory_home)
    if not p.exists():return
    row=json.loads(p.read_text())
    if row['state']=='started':
        session=lab.night_status(supervisor.laboratory_home)
        if session.get('id')==row.get('session_id') and session.get('state') not in lab.NIGHT_ACTIVE:
            row.update(state='finished',result=session.get('state'))
            lab._write_json(p,row);lab._write_json(p.with_name('schedule-'+row['id']+'.json'),row)
        return
    if row['state']!='scheduled':return
    now=time.time();plan=row['plan']
    if now<plan['starts_at']:return
    try:
        if now>plan['starts_at']+60:raise ValueError('Janela de partida perdida; sem reagendamento')
        if supervisor.closing or supervisor.laboratory_maintenance or lab._busy():raise ValueError('Supervisor/worker ocupado')
        from core import resource_manager,job_bus
        if resource_manager.status() or job_bus.status(active_only=True):raise ValueError('Jobs/leases ativos; sem sobreposição')
        # Preview não aceita passado: revalidar gates diretamente, sem mudar datas.
        fresh=build_plan(supervisor.laboratory_home,row['request'])
        if not fresh['allowed']:raise ValueError('; '.join(fresh['blockers']))
        if fingerprint(supervisor.laboratory_home,fresh['tasks'])!=plan['fingerprint']:raise ValueError('Corpus/base mudou')
        if fresh['tasks']!=plan['tasks']:raise ValueError('Presets/plano mudaram; necessária nova revisão')
        if lab.night_status(supervisor.laboratory_home).get('state') in lab.NIGHT_ACTIVE:raise ValueError('Sessão ativa/incerta')
        for job in (lab._registry(supervisor.laboratory_home)/'jobs').glob('*.json'):
            if json.loads(job.read_text()).get('state') in ('started','running','cancel_requested'):
                raise ValueError('Job durável não encerrado')
        row['state']='attempting';lab._write_json(p,row)
        session=supervisor.authorize_night(dict(confirm='VOU_DORMIR_AUTORIZO_LABORATORIO',
            tasks=fresh['tasks'],window_minutes=int((plan['ends_at']-now)//60),absolute_deadline=plan['ends_at']-600))
        row.update(state='started',session_id=session['id'])
    except Exception as exc:row.update(state='blocked',error=str(exc))
    lab._write_json(p,row);lab._write_json(p.with_name('schedule-'+row['id']+'.json'),row)
