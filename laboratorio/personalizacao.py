"""Personalização no laboratório existente; snapshots explícitos, nunca outra mente."""
from __future__ import annotations
import hashlib
import json
import math
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .experimentos import allowed_data, read_jobs
from .candidatos import installed_models
from .professor_schema import ENTITIES
from . import professor_moe

PROFILE_VERSION = 1
MAX_PROFILE_BYTES = 32768
IDENTITY_FIELDS = ('identity', 'personality', 'cognitive_framework')
CONSTITUTION_FIELDS = ('identidade','honestidade','continuidade','expressao','acao','silencio')


def _wire(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def read_profile(path, entity, digest=None):
    """Snapshot imutável e vinculado à entidade; conteúdo é dado, não instrução."""
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_PROFILE_BYTES:
        raise ValueError('Perfil ausente, simbólico ou acima de 32 KiB; não truncar')
    raw=path.read_bytes();actual=hashlib.sha256(raw).hexdigest()
    if digest and actual!=digest:raise RuntimeError('Perfil mudou; geração/treino recusados')
    obj=json.loads(raw)
    if obj.get('version')!=PROFILE_VERSION or obj.get('entity')!=entity:
        raise ValueError('Perfil de outra entidade ou versão incompatível')
    if obj.get('private_diaries_included') is not False:
        raise ValueError('Contrato de privacidade do perfil ausente')
    if not isinstance(obj.get('identity'),dict) or obj['identity'].get('identity',{}).get('name','').casefold()!=entity:
        raise ValueError('Identidade do perfil divergente')
    if not isinstance(obj.get('constitution'),dict):raise ValueError('Constituição inválida')
    for key in ('traits','preferences','experiences'):
        if not isinstance(obj.get(key),list):raise ValueError('Perfil sem coleção: '+key)
    for trait in obj['traits']:
        value=trait.get('valor')
        if (type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1 or
            type(trait.get('evidencias')) is not int or trait['evidencias']<8 or trait.get('consolidado')!=1):
            raise ValueError('Traço sem consolidação verificável')
    for exp in obj['experiences']:
        record=exp.get('record',{})
        if (exp.get('observer')!=entity or exp.get('table') not in ('episodes','memories','reflections') or
            record.get('id')!=exp.get('id') or record.get('tipo')=='diario' or record.get('type')=='diario'):
            raise ValueError('Experiência privada, sem origem ou de outra entidade')
        if exp.get('masked_record_sha256')!=hashlib.sha256(_wire(record).encode()).hexdigest():
            raise ValueError('Evidência do perfil alterada')
        confidence=record.get('confidence')
        if confidence is not None and (type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1):
            raise ValueError('Confiança inválida na evidência')
    if len(obj['experiences'])>30:raise ValueError('Excesso de experiências; não truncar')
    return obj,actual


def capture_profile(home,project,entity,refs=None,*,confirm=False):
    """Só exporta o necessário e referências escolhidas; SQLite read-only, sem migração."""
    if confirm is not True:raise ValueError('Captura exige autorização explícita')
    if entity not in ENTITIES:raise ValueError('Entidade inválida')
    if entity=='alistair' and refs:raise ValueError('Alistair exporta papel/identidade, não pipeline experiencial')
    from app.entity_paths import carregar_entidade
    paths=carregar_entidade(Path(project),entity)
    refs=[] if refs is None else refs
    if not isinstance(refs,list) or len(refs)>30:raise ValueError('Até 30 referências explícitas')
    profile={'version':PROFILE_VERSION,'entity':entity,'created':datetime.now(timezone.utc).isoformat(),
             'private_diaries_included':False,'transient_emotions_included':False,
             'identity':{},'constitution':{},'traits':[],'preferences':[],'experiences':[],
             'sources':{},'database_available':False}
    for name,fields,dest in (('self_model.json',IDENTITY_FIELDS,'identity'),
                             ('constitution.json',CONSTITUTION_FIELDS,'constitution')):
        path=paths.identity/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>131072:
            raise ValueError('Identidade/constituição ausente ou insegura: '+name)
        raw=path.read_bytes();obj=json.loads(raw)
        profile[dest]={k:obj[k] for k in fields if k in obj}
        profile['sources'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'path':str(path)}
    if profile['identity'].get('identity',{}).get('name','').casefold()!=entity:
        raise ValueError('Nome da identidade não corresponde à entidade')
    database=paths.memory/'sqlite'/(entity+'.db')
    if database.is_symlink():raise ValueError('Banco por link recusado')
    if database.exists():
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=10)) as conn:
            conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');conn.execute('BEGIN')
            tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            profile['database_available']=True
            if 'traits' in tables:
                profile['traits']=[dict(r) for r in conn.execute(
                    'SELECT * FROM traits WHERE consolidado=1 AND evidencias>=8 ORDER BY nome')]
            if 'tastes' in tables:
                profile['preferences']=[dict(r) for r in conn.execute(
                    "SELECT * FROM tastes WHERE status='active' AND evidencias>=8 AND confianca>=0.6 ORDER BY id")]
            seen=set()
            for ref in refs:
                if (not isinstance(ref,dict) or set(ref)!={'table','id'} or
                    ref['table'] not in {'episodes','memories','reflections'} or
                    not isinstance(ref['id'],str) or not 1<=len(ref['id'])<=160):
                    raise ValueError('Referência exige table/id do banco da própria entidade')
                key=(ref['table'],ref['id'])
                if key in seen:raise ValueError('Referência duplicada')
                seen.add(key)
                if ref['table'] not in tables:raise ValueError('Categoria de memória ausente')
                row=conn.execute(f"SELECT * FROM {ref['table']} WHERE id=?",(ref['id'],)).fetchone()
                if row is None or dict(row).get('status') not in (None,'active'):
                    raise ValueError('Experiência inexistente ou substituída')
                row=dict(row)
                if row.get('tipo')=='diario':raise PermissionError('Diário privado não entra em treinamento')
                profile['experiences'].append({'table':ref['table'],'id':ref['id'],'observer':entity,
                    'record':row,'record_sha256':hashlib.sha256(_wire(row).encode()).hexdigest()})
    elif refs:raise ValueError('Banco ausente; não inventar experiências')
    # Conteúdo textual passa pelo redactor existente; nomes privados não são
    # removidos automaticamente, portanto inclusão de episódios exige seleção.
    from core.central_control import redact
    profile=redact(profile)
    for exp in profile['experiences']:
        exp['masked_record_sha256']=hashlib.sha256(_wire(exp['record']).encode()).hexdigest()
    raw=_wire(profile).encode()
    if len(raw)>MAX_PROFILE_BYTES:raise ValueError('Perfil acima de 32 KiB; selecione menos evidências, sem descarte silencioso')
    directory=professor_moe.source_dir(Path(home));directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if directory.is_symlink():raise ValueError('Diretório de curadoria por link recusado')
    target=directory/f'perfil-{entity}-{uuid.uuid4().hex}.json'
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    read_profile(target,entity,hashlib.sha256(raw).hexdigest())
    return {'name':target.name,'entity':entity,'sha256':hashlib.sha256(raw).hexdigest(),
            'traits':len(profile['traits']),'experiences':len(profile['experiences']),
            'production_changed':False,'training_started':False}


def profiles(home,entity):
    if entity not in ENTITIES:return []
    result=[]
    for file in sorted(professor_moe.source_dir(Path(home)).glob(f'perfil-{entity}-*.json')):
        try:
            obj,digest=read_profile(file,entity)
            result.append({'name':file.name,'sha256':digest,'created':obj['created'],
                           'traits':len(obj['traits']),'experiences':len(obj['experiences']),'valid':True})
        except (ValueError,RuntimeError,KeyError) as exc:
            result.append({'name':file.name,'valid':False,'error':str(exc)})
    return result


def profile_for_job(home,job):
    name=job.get('cognitive_profile')
    if not name:return None,None
    if not isinstance(name,str) or Path(name).name!=name:raise ValueError('Perfil fora da curadoria')
    return read_profile(professor_moe.source_dir(Path(home))/name,job['entity'],job['cognitive_profile_sha256'])


def dataset_profile(train,entity):
    """Legado continua legível; só corpus derivado com sidecar explícito leva perfil."""
    path=Path(train).parent/'cognitive_profile.json'
    if not path.exists():return None,None
    marker=Path(train).parent/'origem_professor.json'
    if marker.is_symlink():raise ValueError('Proveniência simbólica recusada')
    origin=json.loads(marker.read_text())
    if origin.get('entity')!=entity or not origin.get('cognitive_profile_sha256'):
        raise ValueError('Corpus sem vínculo íntegro de perfil/entidade')
    return read_profile(path,entity,origin['cognitive_profile_sha256'])


TRAINING_CONTEXT_VERSION = 2


def training_identity(entity,profile=None,*,version=TRAINING_CONTEXT_VERSION):
    # Nome não é memória de usuário. O estilo é aprendido das respostas do
    # corpus; não reapresentamos toda a personalidade em cada exemplo.
    if entity not in ENTITIES:raise ValueError('Entidade inválida')
    if type(version) is not int or version not in (1,2):raise ValueError('Versão de contexto incompatível')
    if profile is not None and profile.get('entity')!=entity:raise ValueError('Perfil de outra entidade')
    if profile is None and version==1:return None  # leitura/retomada explícita do contrato legado
    return f'Sou {entity.capitalize()}. Respondo em primeira pessoa; não invento lembranças nem ações.'


def training_context(entity,profile=None,*,version=TRAINING_CONTEXT_VERSION):
    identity=training_identity(entity,profile,version=version)
    wire=_wire(dict(entity=entity,version=version,identity=identity))
    return dict(version=version,sha256=hashlib.sha256(wire.encode()).hexdigest())


def artifact_context(provenance,entity,profile=None):
    """Não reinterpretar um checkpoint antigo usando o novo enquadramento."""
    if provenance.get('entity') not in (None,entity):raise ValueError('Contexto de outra entidade')
    record=provenance.get('training_context')
    if record is None:return training_context(entity,profile,version=1)
    if not isinstance(record,dict) or set(record)!={'version','sha256'}:
        raise ValueError('Proveniência de contexto inválida')
    expected=training_context(entity,profile,version=record['version'])
    if record!=expected:raise RuntimeError('Contexto de treino mudou ou foi adulterado')
    return expected


def entity_status(home: Path):
    datasets = allowed_data(home)
    from .treinos_unificados import jobs
    training_jobs = jobs(home)
    models = installed_models(home)
    proposals = professor_moe.jobs(home)
    result = []
    for entity in ENTITIES:
        from .corpus_atual import entidade_do_corpus
        own = [d for d in datasets if entidade_do_corpus(d['id']) == entity]
        # Importados com metadados de entidade explícitos também são visíveis.
        for d in datasets:
            if not d['id'].startswith('importados:'):
                continue
            marker = home/'datasets-importados'/d['id'].split(':',1)[1]/'origem_professor.json'
            if not marker.is_file() or marker.is_symlink():
                continue
            try:
                import json
                if json.loads(marker.read_text()).get('entity')==entity:
                    own.append(d)
            except (OSError,ValueError):
                pass
        own_jobs = [j for j in training_jobs if j.get('entity')==entity]
        own_proposals = [p for p in proposals if p.get('entity')==entity]
        result.append({'id':entity, 'name':entity.capitalize(), 'datasets':own,
                       'training_jobs':len(own_jobs), 'last_training':own_jobs[0] if own_jobs else None,
                       'teacher_jobs':len(own_proposals),
                       'last_teacher':own_proposals[0] if own_proposals else None,
                       'cognitive_profiles':profiles(home,entity)})
    from .versionamento_lora import stable_status
    from .treinos_unificados import MODELS
    for row in result:
        row['stable_versions']=[]
        for model in MODELS:
            try:
                stable=stable_status(home,row['id'],model)
                if stable['available']:row['stable_versions'].append(stable)
            except (RuntimeError,OSError,ValueError) as exc:
                row['stable_versions'].append({'model':model,'available':False,'error':str(exc)})
    return {'entities':result, 'installed_training_models':models,
            'teacher':professor_moe.status(home),
            'note':'Nenhum peso, checkpoint ou memória é alterado por esta leitura.'}
