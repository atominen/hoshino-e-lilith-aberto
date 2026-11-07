"""Recuperação local pelo worker/registro existentes; não é outro scheduler.

Wake reconstrói apenas originais pinados/última estável. Candidatos e checkpoints
exigem escolha experimental explícita; consultas não carregam/convertem pesos.
"""
from __future__ import annotations

import ast
import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import datetime,timezone

from . import treinos_unificados as lab, versionamento_lora as versions

GIB=1024**3
SUPPORTED={'qwen35-9b':('qwen3_5','qwen35','principal'),
           'qwen35-4b':('qwen3_5','qwen35','light'),
           'qwen25-7b':('qwen2','qwen2','light'),
           'yi-6b':('llama','llama','companion'),
           'alistair-4b':('qwen3_5','qwen35','principal')}
FAMILY={'qwen35-9b':'qwen3.5-9b','qwen35-4b':'qwen3.5-4b','qwen25-7b':'qwen2.5-7b',
        'yi-6b':'yi-6b','alistair-4b':'qwen3.5-4b'}
ENTITIES=('hoshino','lilith','alistair')
CONVERSION_POLICY='ollama-main-no-mtp-v1'


def _json(path):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>4*1024**2:raise RuntimeError('Metadado ausente/inseguro')
    return json.loads(path.read_text())


def _wire(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def _enable_neural_mode(project,entity):
    from core import neural9b_modes,central_control
    revision=neural9b_modes.revision(project)
    document=neural9b_modes.read_document(project)
    document[entity]='neural9b'
    central_control.atomic_save(neural9b_modes.path(project),json.dumps(document,indent=2)+'\n',revision)


def alias(entity,model):
    if entity not in ENTITIES or model not in SUPPORTED or (entity=='alistair')!=(model=='alistair-4b'):
        raise ValueError('Entidade/base não autorizada para recuperação local')
    if entity=='hoshino' and model=='qwen35-9b':
        return 'hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M'
    return entity+'-'+FAMILY[model]+':latest'


def desired_alias(project,entity,model):
    from core.neural9b_modes import runtime_alias
    selected=runtime_alias(project,entity,model)
    if selected:return selected
    if model=='qwen35-9b':
        from core.neural9b_modes import read_modes,ALIASES
        if read_modes(project)[entity]=='neural9b':return ALIASES[entity]
    return alias(entity,model)


def store(project,entity):
    if entity not in ENTITIES:raise ValueError('Entidade desconhecida')
    return Path(project)/'compartilhado/modelos'/('ollama' if entity=='hoshino' else 'ollama-'+entity)


def store_writable(project,entity):
    storage=store(project,entity)
    for candidate in (storage,storage/'blobs',storage/'manifests'):
        path=candidate
        while not path.exists():path=path.parent
        if path.is_symlink() or not os.access(path,os.W_OK|os.X_OK):
            return False,'Armazenamento sem permissão de escrita: '+str(path)
    return True,None


def manifest_path(storage,name):
    from scripts.preparar_executores_leves import manifest_path as existing_path
    return existing_path(storage,name)


def installed(project,entity,name):
    from core.resource_manager import local_model_installed
    return local_model_installed(name,store(project,entity))


def receipt_path(home,entity,model):
    alias(entity,model)
    return lab._registry(home)/'recovery'/entity/(model+'.json')


def active_receipt(home,project,entity,model):
    path=receipt_path(home,entity,model)
    if not path.exists():return None
    row=_json(path)
    if (row.get('entity')!=entity or row.get('model_id')!=model or
        row.get('state')!='verified' or not row.get('alias')):return None
    target=manifest_path(store(project,entity),row['alias'])
    if not installed(project,entity,row['alias']) or versions.sha(target)!=row.get('manifest_sha256'):return None
    return row


def _base_info(home,model):
    base=Path(home)/lab.MODELS[model][0]
    if base.is_symlink() or not base.is_dir():raise RuntimeError('Base local ausente; recuperação não baixa modelos')
    cfg=_json(base/'config.json')
    if cfg.get('model_type')!=SUPPORTED[model][0]:raise RuntimeError('Arquitetura da base divergente')
    files=sorted(base.glob('*.safetensors'))
    if not files or any(p.is_symlink() or p.stat().st_size<4096 for p in files):
        raise RuntimeError('Pesos originais ausentes/incompletos; não reinstalar candidato removido')
    index=base/'model.safetensors.index.json'
    if index.exists() and set(_json(index).get('weight_map',{}).values())!={p.name for p in files}:
        raise RuntimeError('Índice de shards divergente/incompleto')
    config_hash=versions.sha(base/'config.json');expected={};receipt={}
    if (base/'lab_revision.json').exists():
        receipt=_json(base/'lab_revision.json')
        expected=receipt.get('weights_sha256',{}) or {k:v['sha256'] for k,v in receipt.get('shards',{}).items()}
        if receipt.get('config_sha256') and receipt['config_sha256']!=config_hash:
            raise RuntimeError('Config da base mudou')
    if not expected:
        for reference in (lab._registry(home)/'reports/v18-20261012/base-integrity.json',
                          lab._registry(home)/'reports/consolidacao-20261012/base-integrity.json'):
            if reference.exists():
                row=_json(reference).get(model,{})
                if row.get('config_sha256')==config_hash:
                    expected={p['name']:p['sha256'] for p in row['files']};break
    if set(expected)!={p.name for p in files} or any(not re.fullmatch('[a-f0-9]{64}',v) for v in expected.values()):
        raise RuntimeError('Originais sem hashes pinados; não usar candidato para fabricar base')
    tokenizer={p.name:versions.sha(p) for p in base.iterdir() if p.is_file() and
               (p.name.startswith('tokenizer') or p.name in ('chat_template.jinja','vocab.json','merges.txt','generation_config.json'))}
    if 'tokenizer_config.json' not in tokenizer or not ({'tokenizer.json','vocab.json','tokenizer.model'} & set(tokenizer)):
        raise RuntimeError('Tokenizer/template originais incompletos')
    result=dict(base=str(base.resolve()),config_sha256=config_hash,weights_sha256=expected,
                tokenizer_sha256=tokenizer,bytes=sum(p.stat().st_size for p in files),
                hf_origin=receipt.get('repo') or 'checkpoint_local_hash_pinado',
                vision=bool(cfg.get('vision_config')),architecture=SUPPORTED[model][1])
    return result


def verify_source(source):
    base=Path(source['base'])
    if base.is_symlink() or versions.sha(base/'config.json')!=source['config_sha256']:
        raise RuntimeError('Base mudou desde o planejamento')
    for name,digest in {**source['weights_sha256'],**source['tokenizer_sha256']}.items():
        path=base/name
        if Path(name).name!=name or path.is_symlink() or versions.sha(path)!=digest:
            raise RuntimeError('Integridade da base/tokenizer não confirmada: '+name)
    adapter=source.get('adapter') or source.get('stable')
    if adapter:
        snap=Path(adapter['snapshot'])
        if snap.is_symlink():raise RuntimeError('Adaptador simbólico recusado')
        for name,digest in adapter['files_sha256'].items():
            if Path(name).name!=name or (snap/name).is_symlink() or versions.sha(snap/name)!=digest:
                raise RuntimeError('Estável mudou durante recuperação')
    return True


def version_receipt_path(home,entity,model,fingerprint):
    alias(entity,model)
    if not re.fullmatch('[a-f0-9]{64}',fingerprint):raise ValueError('Referência de versão inválida')
    return lab._registry(home)/'recovery'/entity/'versions'/model/(fingerprint+'.json')


def version_receipt(home,project,entity,model,fingerprint):
    path=version_receipt_path(home,entity,model,fingerprint)
    if not path.exists():return None
    row=_json(path);probe=row.get('probe',{})
    if (row.get('entity')!=entity or row.get('model_id')!=model or row.get('state')!='verified' or
            row.get('source_sha256')!=fingerprint or probe.get('done') is not True or
            probe.get('unload_confirmed') is not True or probe.get('pressure')):return None
    manifest=manifest_path(store(project,entity),row.get('alias',''))
    if (not installed(project,entity,row.get('alias','')) or manifest.is_symlink() or
            versions.sha(manifest)!=row.get('manifest_sha256')):return None
    return row


def _version_entry(home,project,entity,model,kind,ref,snapshot=None,provenance=None,step=None,evaluation=None):
    descriptor=dict(entity=entity,model_id=model,kind=kind,ref=ref)
    if snapshot:
        snapshot=Path(snapshot)
        if snapshot.is_symlink() or not snapshot.resolve().is_relative_to(lab._registry(home).resolve()):
            raise RuntimeError('Snapshot fora do laboratório')
        prov=_json(provenance);base=Path(home)/lab.MODELS[model][0]
        if (prov.get('entity')!=entity or Path(prov.get('base_path','')).resolve()!=base.resolve() or
                prov.get('base_config_sha256')!=versions.sha(base/'config.json') or
                prov.get('base_weights_signature')!=versions.base_signature(base)):
            raise RuntimeError('Snapshot de outra identidade/base ou originais alterados')
        digest=step['adapter_sha256'] if step else prov['final_adapter_sha256']
        if not re.fullmatch('[a-f0-9]{64}',digest):raise RuntimeError('Hash de adaptador inválido')
        descriptor.update(adapter_sha256=digest,provenance_sha256=versions.sha(provenance),
            adapter_config_sha256=versions.sha(snapshot/'adapter_config.json'),
            step_sha256=versions.sha(snapshot/'step.json') if step else None)
    else:
        descriptor['base_config_sha256']=versions.sha(Path(home)/lab.MODELS[model][0]/'config.json')
    fingerprint=hashlib.sha256(_wire(descriptor).encode()).hexdigest()
    name=entity+'-'+FAMILY[model]+'-'+kind+'-'+fingerprint[:16]+':latest'
    receipt=None
    if kind=='original':
        old=active_receipt(home,project,entity,model)
        original=(old or {}).get('original',{})
        name=original.get('alias') or alias(entity,model)
        if not installed(project,entity,name):
            local=entity+'-'+FAMILY[model]+'-original-'+conversion_digest(_base_info(home,model))[:12]+':latest'
            if installed(project,entity,local):name=local
        ready=installed(project,entity,name)
    else:
        receipt=version_receipt(home,project,entity,model,fingerprint)
        ready=bool(receipt and receipt['alias']==name)
    checks=(evaluation or {}).get('behavioral_audit',{}).get('checks',[])
    return dict(descriptor,source_sha256=fingerprint,alias=name,ready=ready,
        snapshot=str(snapshot) if snapshot else None,
        quality_approved=kind in ('original','stable'),experimental=kind in ('checkpoint','trained'),
        evaluation_available=evaluation is not None,evaluation_passed=(evaluation or {}).get('passed'),
        behavioral_passed=sum(bool(v.get('passed')) for v in checks),behavioral_total=len(checks),
        steps=step.get('step') if step else (_json(snapshot/'micro_result.json').get('steps') if snapshot and kind=='trained' else None),
        manifest_sha256=(receipt or {}).get('manifest_sha256') if kind!='original' else
            versions.sha(manifest_path(store(project,entity),name)) if ready else None)


def versions_catalog(home,project,entity):
    """Inventário read-only. Não carrega modelos nem promove candidatos reprovados."""
    from core import neural9b_modes
    if entity not in ENTITIES:raise ValueError('Entidade desconhecida')
    home=Path(home).resolve();project=Path(project).resolve();root=lab._registry(home)
    jobs=[]
    for path in sorted((root/'jobs').glob('*.json')):
        row=_json(path)
        if row.get('entity')==entity and row.get('state')=='completed':jobs.append(row)
    families=[]
    for model in SUPPORTED:
        if model not in neural9b_modes.enabled_families(project,entity):continue
        rows=[];error=None
        try:
            rows.append(_version_entry(home,project,entity,model,'original','original'))
            trains=[j for j in jobs if j.get('model')==model and j.get('action')=='train' and j.get('artifact')]
            latest=max(trains,key=lambda j:(j.get('finished',j.get('created','')),j['id']),default=None)
            if latest:
                candidate=Path(latest['artifact']);result=_json(candidate/'micro_result.json')
                if result.get('cancelled') or result.get('entity')!=entity:raise RuntimeError('Último treino incompleto/estrangeiro')
                report=None
                for job in reversed(jobs):
                    if job.get('action')=='evaluate' and job.get('plan',{}).get('candidate')==str(candidate):
                        report=_json(job['artifact']);break
                rows.append(_version_entry(home,project,entity,model,'trained',latest['id'],candidate,candidate/'provenance.json',evaluation=report))
                checkpoints=sorted((candidate/'checkpoints').glob('passo-*'))
                if checkpoints:
                    ck=checkpoints[-1];step=_json(ck/'step.json')
                    matching=report if report and report.get('adapter_sha256')==step.get('adapter_sha256') else None
                    rows.append(_version_entry(home,project,entity,model,'checkpoint',latest['id']+':'+str(step['step']),ck,candidate/'provenance.json',step,matching))
            stable=versions.stable_status(home,entity,model)
            if stable.get('available') and stable.get('snapshot'):
                snap=Path(stable['snapshot']);report=_json(snap/'independent_evaluation.json')
                if report.get('passed') is not True:raise RuntimeError('Registro estável sem aprovação')
                rows.append(_version_entry(home,project,entity,model,'stable',stable['adapter_sha256'],snap,snap/'provenance.json',evaluation=report))
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            error=str(exc)
        families.append(dict(model_id=model,label=lab.MODELS[model][1].removesuffix(' original'),tier=SUPPORTED[model][2],entries=rows,error=error))
    selection=neural9b_modes.read_document(project).get('executor_versions',{}).get(entity,{})
    result=dict(entity=entity,families=families,selection=selection,selection_revision=neural9b_modes.revision(project),
                note='Candidatos experimentais não são estáveis. Troca somente dormindo; preparar não acorda nem altera memória.')
    result['revision']=hashlib.sha256(_wire(result).encode()).hexdigest()
    return result


def find_version(home,project,entity,model,kind,ref,revision=None):
    catalog=versions_catalog(home,project,entity)
    if revision is not None and catalog['revision']!=revision:raise ValueError('Catálogo mudou; atualize antes de selecionar')
    for family in catalog['families']:
        if family['model_id']==model:
            for entry in family['entries']:
                if entry['kind']==kind and entry['ref']==ref:return entry
    raise ValueError('Versão ausente, estrangeira ou não concluída')


def plan_version(home,project,entity,model,options):
    if (not isinstance(options,dict) or set(options)!={'version_kind','version_ref','source_sha256','experimental_consent'} or
            type(options['experimental_consent']) is not bool):raise ValueError('Seleção de versão inválida')
    entry=find_version(home,project,entity,model,options['version_kind'],options['version_ref'])
    if entry['source_sha256']!=options['source_sha256']:raise RuntimeError('Versão mudou; não preparar outra implicitamente')
    if entry['experimental'] and not options['experimental_consent']:raise ValueError('Uso experimental exige consentimento explícito')
    base=_base_info(home,model);base.update(kind=entry['kind'],stable=None)
    if entry['snapshot']:
        snap=Path(entry['snapshot']);parent=snap.parent.parent if entry['kind']=='checkpoint' else snap
        versions.verify(parent,base['base']) if entry['kind']!='stable' else versions.stable_status(home,entity,model)
        if entry['kind']=='checkpoint':
            prov=_json(parent/'provenance.json')
            versions.validate_resume(snap,base['base'],prov['train_path'],prov['validation_path'],entity=entity)
        names=['adapter_model.safetensors','adapter_config.json']
        pinned={name:versions.sha(snap/name) for name in names}
        if pinned['adapter_model.safetensors']!=entry['adapter_sha256']:raise RuntimeError('Adaptador mudou desde o catálogo')
        base['adapter']=dict(snapshot=str(snap),adapter_sha256=entry['adapter_sha256'],files_sha256=pinned)
    # Se a base já está convertida, apenas o pequeno adaptador é preparado.
    cached=lab._registry(home)/'conversions'/model/conversion_digest(base)/'converted.json'
    required=2*GIB if cached.is_file() else int(base['bytes']*1.4)+12*GIB
    writable,reason=store_writable(project,entity)
    return dict(action='recover',model_id=model,entity=entity,tier=SUPPORTED[model][2],
        alias=entry['alias'],canonical_alias=alias(entity,model),needed=not entry['ready'],missing_alias=entry['alias'],
        source=base,source_sha256=entry['source_sha256'],version_kind=entry['kind'],version_ref=entry['ref'],
        receipt_path=str(version_receipt_path(home,entity,model,entry['source_sha256'])),
        context_max=4096 if model=='yi-6b' else 8192 if model!='qwen35-9b' else 16384,
        required_bytes=required,allowed=writable and shutil.disk_usage(home).free>=required,blocker=reason,
        project=str(Path(project).resolve()),home=str(Path(home).resolve()),activate=False,download=False,
        training_started=False,experimental=entry['experimental'],quality_approved=entry['quality_approved'])


def plan(home,project,entity,model):
    home=Path(home).resolve();project=Path(project).resolve();target=alias(entity,model)
    row=dict(action='recover',model_id=model,entity=entity,tier=SUPPORTED[model][2],
             canonical_alias=target,alias=target,project=str(project),home=str(home),
             download=False,training_started=False,missing_alias=desired_alias(project,entity,model),
             needed=not installed(project,entity,desired_alias(project,entity,model)))
    if not row['needed']:return dict(row,allowed=True,activate=False)
    base=_base_info(home,model);stable=versions.stable_status(home,entity,model)
    if stable.get('available'):
        if stable.get('entity')!=entity or stable.get('model')!=model or not stable.get('snapshot'):
            raise RuntimeError('Estável estrangeira/legada; não converter implicitamente')
        snap=Path(stable['snapshot'])
        if snap.is_symlink() or not snap.resolve().is_relative_to((home/'controle-laboratorio/stable'/entity/model).resolve()):
            raise RuntimeError('Estável fora do registro da entidade')
        prov=_json(snap/'provenance.json');evaluation=_json(snap/'independent_evaluation.json')
        if (prov.get('entity')!=entity or prov.get('base_config_sha256')!=base['config_sha256'] or
            prov.get('base_path')!=base['base'] or evaluation.get('entity')!=entity or
            evaluation.get('passed') is not True or evaluation.get('physical_reload_verified') is not True or
            evaluation.get('adapter_sha256')!=stable.get('adapter_sha256')):
            raise RuntimeError('Estável não corresponde à base/avaliação aprovada')
        pinned=prov.get('base_weights_sha256')
        if pinned and pinned!=base['weights_sha256']:raise RuntimeError('Estável treinada em outros pesos')
        if not pinned and prov.get('base_weights_signature')!=versions.base_signature(base['base']):
            raise RuntimeError('Assinatura original da estável mudou')
        base.update(kind='stable',stable=stable)
        row['alias']=entity+'-neural9b:latest' if model=='qwen35-9b' else target
    else:
        if row['missing_alias']!=target:raise RuntimeError('Neural selecionado ausente e não há estável aprovada; não mascarar com original')
        base.update(kind='original',stable=None)
    fingerprint=hashlib.sha256(_wire(base).encode()).hexdigest()
    required=int(base['bytes']*1.4)+12*GIB  # F16/Q4/projector + import/staging + reserva existentes
    available=shutil.disk_usage(home).free
    writable,permission_error=store_writable(project,entity)
    return dict(row,source=base,source_sha256=fingerprint,required_bytes=required,
                free_bytes=available,allowed=available>=required and writable,blocker=permission_error,
                activate=model!='yi-6b' or (bool(base['stable']) and model in configured_targets(project,entity)),
                context_max=4096 if model=='yi-6b' else 8192 if entity=='alistair' else 16384 if model=='qwen35-9b' else 8192)


def configured_targets(project,entity):
    from core.central_control import MODEL_DEFAULTS
    alias(entity,'alistair-4b' if entity=='alistair' else 'qwen35-9b')
    envpath=Path(project)/'entidades'/entity/'config'/(entity+'.env')
    if entity=='hoshino' and not envpath.exists():envpath=envpath.with_name('hoshino_v32.env')
    primary=MODEL_DEFAULTS[entity]
    if envpath.exists():
        for line in envpath.read_text().splitlines():
            match=re.match(r'\s*(?:export\s+)?HOSHINO_MODEL\s*=\s*(.*)',line)
            if match:
                try:primary=ast.literal_eval(match[1])
                except (ValueError,SyntaxError):primary=match[1].strip()
    known={alias(entity,m):m for m in SUPPORTED if (entity=='alistair')==(m=='alistair-4b')}
    if entity!='alistair':known[entity+'-neural9b:latest']='qwen35-9b'
    if primary not in known:raise ValueError('Executor selecionado sem origem local autorizada; nenhum pull automático')
    from core.neural9b_modes import primary_family
    targets=[primary_family(project,entity) or known[primary]]
    path=envpath.parent/'executores.json'
    if path.exists():
        catalog=_json(path)
        for kind in ('light','companion'):
            candidate=catalog.get(kind)
            if not candidate or (kind=='companion' and not (candidate.get('enabled') and candidate.get('conversation_validated') is True)):continue
            if candidate.get('model') not in known:raise ValueError('Executor adicional removido/não autorizado')
            targets.append(known[candidate['model']])
    return list(dict.fromkeys(targets))


def ensure(home,project,entity,*,retry=False):
    """Wake explicito prepara o MESMO worker; falha anterior nunca some no restart."""
    home=Path(home)
    if not home.is_dir():return {'state':'not_configured','needed':False}
    targets=configured_targets(project,entity)
    folder=lab._registry(home)/'jobs'
    previous={}
    for file in folder.glob('*.json'):
        row=_json(file)
        model=row.get('plan',{}).get('model_id')
        if row.get('entity')==entity and row.get('plan',{}).get('version_kind') and row.get('state') in ('started','running','cancel_requested'):
            current=lab.details(home,row['id'])
            if current['state'] in ('started','running','cancel_requested'):
                return {'state':'recovering','needed':True,'id':row['id']}
        if row.get('plan',{}).get('version_kind'):
            from core.neural9b_modes import selected_version
            selected=selected_version(project,entity,model)
            if not selected or selected['source_sha256']!=row['plan'].get('source_sha256'):continue
        if row.get('action')=='recover' and row.get('entity')==entity and model in targets:
            if model not in previous or file.stat().st_mtime>previous[model][0]:previous[model]=(file.stat().st_mtime,row)
    # Uma cópia de alias pode sobreviver a crash ANTES do recibo final. Presença
    # de arquivo não apaga um resultado incerto nem autoriza inferência/replay.
    for _,row in previous.values():
        if row['state']=='completed' and lab._owned_alive(row,row['id']):
            return {'state':'recovering','needed':True,'id':row['id'],'detail':'Worker finalizando/liberando locks'}
        if row['state'] in ('started','running','cancel_requested'):
            row=lab.details(home,row['id'])
        if row['state'] in ('started','running','cancel_requested'):
            return {'state':'recovering','needed':True,'id':row['id']}
        if row['state']!='completed' and not retry:
            return {'state':'blocked','needed':True,'id':row['id'],'detail':'Recuperação anterior não confirmada; repetir somente com confirmação explícita'}
    for model in targets:
        path=receipt_path(home,entity,model)
        if path.exists() and _json(path).get('state')=='publishing':
            return {'state':'blocked','needed':True,'detail':'Publicação interrompida: conferir recibo/alias antes de ativar, sem replay'}
    missing=[m for m in targets if not installed(project,entity,desired_alias(project,entity,m))]
    if not missing:return {'state':'ready','needed':False}
    result=lab.start(home,project,missing[0],entity,90,'recover','EXECUTAR_RECUPERACAO_LOCAL')
    return dict(result,state='recovering',needed=True)


def effective_primary(home,project,entity):
    model='alistair-4b' if entity=='alistair' else 'qwen35-9b'
    row=active_receipt(home,project,entity,model)
    return row['alias'] if row and row.get('activated') else None


def cli():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preview','recover','ensure','verify-publication'))
    parser.add_argument('--home',type=Path,required=True);parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--entity',choices=ENTITIES,required=True);parser.add_argument('--model',choices=SUPPORTED)
    parser.add_argument('--confirm',action='store_true');parser.add_argument('--wait',action='store_true')
    parser.add_argument('--job')
    args=parser.parse_args();home=args.home.resolve();project=args.project.resolve()
    if args.action=='preview':
        targets=[args.model] if args.model else configured_targets(project,args.entity)
        print(json.dumps([plan(home,project,args.entity,m) for m in targets],ensure_ascii=False,indent=2));return
    if not args.confirm:parser.error('Nenhuma conversão sem confirmação')
    if args.action=='verify-publication':
        if not args.job:parser.error('Job anterior obrigatório')
        print(json.dumps(verify_publication(home,project,args.entity,args.job),ensure_ascii=False));return
    if args.action=='recover':
        if not args.model:parser.error('Selecione o modelo local')
        result=lab.start(home,project,args.model,args.entity,90,'recover','EXECUTAR_RECUPERACAO_LOCAL')
    else:result=ensure(home,project,args.entity)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if not args.wait:return
    deadline=time.monotonic()+10800
    while result.get('id') and time.monotonic()<deadline:
        item=lab.details(home,result['id'])
        if item['state'] in ('started','running','cancel_requested'):time.sleep(1);continue
        if item['state']=='completed' and lab._owned_alive(item,item['id']):time.sleep(.2);continue
        print(json.dumps({'id':item['id'],'state':item['state'],'error':item.get('error'),'artifact':item.get('artifact')},ensure_ascii=False),flush=True)
        if item['state']!='completed':raise SystemExit(1)
        if args.action=='recover':return
        result=ensure(home,project,args.entity)
        if result.get('state')=='blocked':raise SystemExit(result['detail'])
    if result.get('id'):raise SystemExit('Espera excedida; job preservado, sem replay')


def inspect_gguf(home,path,architecture=None):
    """Lê estrutura/tensores inteiros, não só magic bytes; sem carregar LLM."""
    sys.path.insert(0,str(Path(home)/'llama.cpp/gguf-py'))
    from gguf import GGUFReader
    path=Path(path)
    if path.is_symlink() or path.stat().st_size<=4096:raise RuntimeError('GGUF incompleto/simbólico')
    reader=GGUFReader(str(path))
    field=reader.fields.get('general.architecture');arch=field.contents() if field else None
    if architecture and arch!=architecture:raise RuntimeError('Arquitetura GGUF divergente: '+str(arch))
    if not reader.tensors or any(t.data_offset+t.n_bytes>path.stat().st_size for t in reader.tensors):
        raise RuntimeError('Tensores GGUF incompletos')
    names=[t.name for t in reader.tensors]
    if len(names)!=len(set(names)):raise RuntimeError('Tensores GGUF duplicados')
    template=reader.fields.get('tokenizer.chat_template')
    count=reader.fields.get(str(arch)+'.block_count')
    blocks=sorted({int(n.split('.')[1]) for n in names if re.match(r'^blk\.\d+\.',n)})
    result={'path':str(path),'bytes':path.stat().st_size,'sha256':versions.sha(path),
            'architecture':arch,'tensors':len(names),'template_present':bool(template and template.contents()),
            'block_count':count.contents() if count else None,'block_indices':blocks}
    del reader
    return result


def validate_main_layout(source,record):
    cfg=_json(Path(source['base'])/'config.json');text=cfg.get('text_config',cfg)
    layers=text.get('num_hidden_layers')
    if type(layers)!=int or layers<1 or record.get('block_count')!=layers or record.get('block_indices')!=list(range(layers)):
        raise RuntimeError('GGUF anuncia camadas divergentes/incompletas; não importar. MTP não é executor principal.')


def conversion_digest(source):
    identity={k:v for k,v in source.items() if k not in ('stable','kind','adapter')}
    identity['conversion_policy']=CONVERSION_POLICY
    return hashlib.sha256(_wire(identity).encode()).hexdigest()


def adopt_completed_conversion(home,jid,partial):
    """Retomada EXPLÍCITA de saída íntegra de um job falho, nunca no wake.

    Não aceita fragmentos, artefatos estrangeiros ou uma base diferente. O job
    e seu log originais continuam intactos; importação/probe ainda são obrigatórios.
    """
    row=lab.details(home,jid)
    if row.get('action')!='recover' or row.get('state')!='failed':raise RuntimeError('Job não é recuperação falha encerrada')
    spec=row['plan'];source=spec['source'];verify_source(source)
    digest=conversion_digest(source)
    target=lab._registry(home)/'conversions'/spec['model_id']/digest
    partial=Path(partial)
    if (partial.is_symlink() or partial.resolve().parent!=target.parent.resolve() or
            not partial.name.startswith(digest+'.partial-') or target.exists()):
        raise RuntimeError('Staging estrangeiro ou destino existente')
    log=lab._job_file(home,jid).with_suffix('.log')
    # Saída do worker precisa apontar exatamente para este staging; não adotar
    # qualquer arquivo com magic GGUF encontrado no disco.
    if not log.is_file() or str(partial) not in log.read_text(errors='replace'):
        raise RuntimeError('Staging sem vínculo com o log do job')
    output={'base':partial/'base-q4_k_m.gguf'}
    if source['vision']:
        projector=partial/'mmproj-model-f16.gguf'
        if not projector.exists():projector=partial/'model-f16.gguf'
        output['projector']=projector
    records=[]
    for kind,path in output.items():
        item=inspect_gguf(home,path,source['architecture'] if kind=='base' else 'clip')
        if kind=='base' and not item['template_present']:raise RuntimeError('Template ausente')
        if kind=='base':validate_main_layout(source,item)
        records.append(dict(item,path=str(target/path.name),name=path.name,kind=kind))
    verify_source(source)
    lab._write_json(partial/'converted.json',dict(base_source_sha256=digest,files=records,
        conversion_policy=CONVERSION_POLICY,
        state='converted_not_installed',recovered_from_failed_job=jid,
        corrective_action='Verificação integral após corrigir contrato do nome do projetor'))
    os.rename(partial,target)
    return {'state':'converted_not_installed','path':str(target),'files':records,'previous_job':jid}


def convert_source(home,spec):
    """Cache de artefato existente no registro; não é cache mental ou de inferência."""
    from .trabalhador import convert_local
    source=spec['source'];verify_source(source)
    digest=conversion_digest(source)
    root=lab._registry(home)/'conversions'/spec['model_id']/digest
    record=root/'converted.json'
    if record.exists():
        cached=_json(record)
        if cached.get('base_source_sha256')!=digest:raise RuntimeError('Conversão de outra base')
        if cached.get('conversion_policy')!=CONVERSION_POLICY:raise RuntimeError('Conversão usa contrato anterior')
        for entry in cached['files']:
            path=root/entry['name']
            if path.is_symlink() or versions.sha(path)!=entry['sha256']:
                raise RuntimeError('Conversão armazenada corrompida; não repetir automaticamente')
            if entry['kind']=='base':validate_main_layout(source,entry)
    else:
        if root.exists():raise RuntimeError('Conversão parcial anterior; recuperar com confirmação explícita')
        root.parent.mkdir(parents=True,exist_ok=True)
        staging=root.with_name(root.name+'.partial-'+os.urandom(4).hex());staging.mkdir(mode=0o700)
        output=convert_local(home,source['base'],staging,vision=source['vision'],guard=lambda:conversion_pressure(home))
        records=[]
        for kind,path in output.items():
            if path:
                item=inspect_gguf(home,path,source['architecture'] if kind=='base' else None)
                if kind=='base' and not item['template_present']:raise RuntimeError('Template ausente: protocolo de diálogo não confirmado')
                if kind=='base':validate_main_layout(source,item)
                records.append(dict(item,path=str(root/Path(path).name),name=Path(path).name,kind=kind))
        verify_source(source)
        cached={'base_source_sha256':digest,'files':records,'state':'converted_not_installed','conversion_policy':CONVERSION_POLICY}
        lab._write_json(staging/'converted.json',cached);os.rename(staging,root)
    files=[dict(entry,path=str(root/entry['name'])) for entry in cached['files']]
    adapter=source.get('adapter') or source.get('stable')
    if adapter:
        snap=Path(adapter['snapshot']);adigest=adapter['adapter_sha256']
        adir=root/spec['entity']/adigest
        if not adir.exists():
            staging=adir.with_name(adir.name+'.partial-'+os.urandom(4).hex());staging.mkdir(parents=True,mode=0o700)
            cpp=Path(home)/'llama.cpp'
            from .trabalhador import run
            run([Path(home)/'.venv-rocm/bin/python',cpp/'convert_lora_to_gguf.py',snap,
                 '--base',source['base'],'--outtype','f16','--outfile',staging/'stable-lora.gguf'],timeout=3600,guard=lambda:conversion_pressure(home))
            item=inspect_gguf(home,staging/'stable-lora.gguf',source['architecture'])
            verify_source(source);lab._write_json(staging/'converted.json',dict(item,source_adapter_sha256=adigest))
            os.rename(staging,adir)
        item=_json(adir/'converted.json')
        if item.get('source_adapter_sha256')!=adigest or versions.sha(adir/'stable-lora.gguf')!=item['sha256']:
            raise RuntimeError('LoRA GGUF armazenado divergente')
        files.append(dict(item,path=str(adir/'stable-lora.gguf'),name='stable-lora.gguf',kind='adapter'))
    return files


def conversion_pressure(home):
    from core import gpu_metrics
    available=gpu_metrics.ram_available()
    if available is None or available<4*GIB:return 'RAM física incerta/sob pressão; conversão interrompida'
    if shutil.disk_usage(home).free<10*GIB:return 'Reserva de disco atingida; conversão interrompida sem apagar originais'
    return None


@contextlib.contextmanager
def owned_daemon(home,project,entity):
    """Endpoint dedicado; reusa só daemon com host/store próprios comprovados."""
    import requests
    port={'hoshino':11435,'lilith':11436,'alistair':11437}[entity]
    host=f'127.0.0.1:{port}';base='http://'+host;storage=store(project,entity).resolve()
    with socket.socket() as check:occupied=check.connect_ex(('127.0.0.1',port))==0
    proc=None;owned_pid=None;owned_stamp=None
    if occupied:
        matched=False
        for item in Path('/proc').iterdir():
            if not item.name.isdigit():continue
            try:
                if (item/'comm').read_text().strip()!='ollama' or item.stat().st_uid!=os.getuid():continue
                environment=dict(v.split(b'=',1) for v in (item/'environ').read_bytes().split(b'\0') if b'=' in v)
                if environment.get(b'OLLAMA_HOST')==host.encode() and environment.get(b'OLLAMA_MODELS')==str(storage).encode():
                    matched=True;owned_pid=int(item.name);owned_stamp=lab._stamp(owned_pid)
            except (OSError,ValueError):continue
        if not matched:raise RuntimeError('Porta ocupada por daemon não owned; não importar/reiniciar')
    else:
        from core import resource_manager
        writable,reason=store_writable(project,entity)
        if not writable:raise RuntimeError(reason)
        env=dict(os.environ,OLLAMA_HOST=host,OLLAMA_MODELS=str(storage),OLLAMA_VULKAN='1',OLLAMA_NO_CLOUD='1',OLLAMA_NOPRUNE='1')
        env.pop('HSA_OVERRIDE_GFX_VERSION',None)
        env.update(resource_manager.ram_prompt_cache_environment(entity,env))
        storage.mkdir(parents=True,exist_ok=True)
        log=lab._registry(home)/'recovery'/entity/'daemon.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('ab') as output:
            proc=subprocess.Popen([shutil.which('ollama') or 'ollama','serve'],env=env,stdin=subprocess.DEVNULL,
                stdout=output,stderr=output,start_new_session=True)
        owned_pid=proc.pid;owned_stamp=lab._stamp(proc.pid)
    class Endpoint(str):pass
    endpoint=Endpoint(base);stop_lock=threading.RLock()
    def stop_owned():
        # entity.lock está preso e o daemon era idle ao entrar. Nunca sinalizar
        # por nome/porta; identidade de processo precisa continuar a mesma.
        with stop_lock:
            if lab._stamp(owned_pid)!=owned_stamp:return
            os.kill(owned_pid,15)
            until=time.monotonic()+30
            while time.monotonic()<until:
                if proc:
                    try:proc.wait(timeout=.2);return
                    except subprocess.TimeoutExpired:pass
                elif lab._stamp(owned_pid)!=owned_stamp:return
                else:time.sleep(.2)
            raise RuntimeError('Daemon owned não encerrou cooperativamente; recurso incerto')
    endpoint.stop_owned=stop_owned
    try:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if proc and proc.poll() is not None:raise RuntimeError('Daemon owned encerrou na inicialização')
            try:
                response=requests.get(base+'/api/version',timeout=(1,2));response.raise_for_status();break
            except requests.RequestException:time.sleep(.2)
        else:raise TimeoutError('Daemon local não respondeu')
        resident=requests.get(base+'/api/ps',timeout=(1,3));resident.raise_for_status()
        if resident.json().get('models'):raise RuntimeError('Modelo residente: adiar importação, sem unload automático')
        yield endpoint
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Sem apagar pesos nem sinalizar processos de terceiros.
                proc.kill();proc.wait(timeout=10)


def _verify_installed(project,entity,name):
    from scripts.preparar_executores_leves import verify
    blobs=verify(store(project,entity),name)
    if not installed(project,entity,name):raise RuntimeError('Alias não confirmado no store próprio')
    return {'alias':name,'manifest_sha256':versions.sha(manifest_path(store(project,entity),name)),'blobs':blobs}


def import_alias(home,project,entity,base,name,files,context_max):
    """Nenhum pull; recibo success + hash de TODOS os blobs + protocolo show."""
    import requests
    from scripts.preparar_executores_leves import stream,NEUTRAL_SYSTEM
    if installed(project,entity,name):raise RuntimeError('Alias existente preservado; importação recusada')
    target=manifest_path(store(project,entity),name)
    if target.exists():raise RuntimeError('Manifesto parcial/corrompido existente; reparar explicitamente sem sobrescrever')
    mapped={};adapters={}
    for entry in files:
        path=Path(entry['path']);digest='sha256:'+entry['sha256']
        if path.is_symlink() or versions.sha(path)!=entry['sha256']:raise RuntimeError('GGUF mudou antes do upload')
        with path.open('rb') as content:
            reply=requests.post(base+'/api/blobs/'+digest,data=content,timeout=(5,900));reply.raise_for_status()
        (adapters if entry['kind']=='adapter' else mapped)[path.name]=digest
    params={'num_ctx':context_max,'num_predict':768 if entity=='alistair' else 2048,
            'num_gpu':0 if entity=='alistair' else 20}
    payload={'model':name,'files':mapped,'parameters':params,'system':NEUTRAL_SYSTEM}
    if adapters:payload['adapters']=adapters
    stream(base,'/api/create',payload,project)
    receipt=_verify_installed(project,entity,name)
    show=requests.post(base+'/api/show',json={'model':name},timeout=(1,10));show.raise_for_status()
    actual=show.json()
    if actual.get('system')!=NEUTRAL_SYSTEM or not actual.get('template'):
        raise RuntimeError('Template/system do executor não confirmado')
    receipt['capabilities']=actual.get('capabilities',[])
    if any(f['kind']=='projector' for f in files) and 'vision' not in receipt['capabilities']:
        raise RuntimeError('Importação perdeu visão; não ativar silenciosamente')
    return receipt


def publish_alias(project,entity,endpoint,source,destination):
    import requests
    if installed(project,entity,destination):raise RuntimeError('Alias apareceu durante recuperação; preservar')
    if manifest_path(store(project,entity),destination).exists():
        raise RuntimeError('Manifesto anterior incompleto: não sobrescrever automaticamente')
    # /api/copy confirma por status HTTP e retorna corpo VAZIO. Não permitir
    # JSON vazio em /chat; apenas este contrato aceita resposta sem JSON.
    response=requests.post(endpoint+'/api/copy',json={'source':source,'destination':destination},timeout=(2,30))
    response.raise_for_status()
    receipt=_verify_installed(project,entity,destination)
    if receipt['manifest_sha256']!=versions.sha(manifest_path(store(project,entity),source)):
        raise RuntimeError('Cópia não corresponde ao staging verificado')
    return receipt


def verify_publication(home,project,entity,jid):
    """Confirma uma cópia que já aconteceu; NUNCA repete copy/inferência/treino."""
    home=Path(home);project=Path(project)
    row=lab.details(home,jid)
    if row.get('action')!='recover' or row.get('entity')!=entity or row['state'] not in ('failed','interrupted_unverified'):
        raise RuntimeError('Job anterior não é recuperação incerta desta entidade')
    if lab._busy() or lab._owned_alive(row,jid):raise RuntimeError('Worker ainda ativo; aguardar liberação')
    spec=row['plan'];model=spec['model_id'];path=receipt_path(home,entity,model)
    record=_json(path);probe=record.get('probe',{})
    if (record.get('state')!='publishing' or record.get('job_id')!=jid or record.get('entity')!=entity or
        record.get('alias')!=spec['alias'] or record.get('stage_alias')!=entity+'-recovery-'+jid+':latest' or probe.get('done') is not True or
        probe.get('unload_confirmed') is not True or probe.get('pressure')):
        raise RuntimeError('Probe/unload/publicação anteriores não confirmados; não repetir automaticamente')
    runtime=project/'entidades'/entity/'runtime'
    with (lab._registry(home)/'start.lock').open('a+') as start_lock,\
         (home/'controle-laboratorio/trabalhador.lock').open('a+') as worker_lock,\
         (runtime/'entity.lock').open('a+') as entity_lock:
        for lock in (start_lock,worker_lock,entity_lock):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify_source(spec['source'])
        if spec['source']['kind']=='stable':
            current=versions.stable_status(home,entity,model)
            if current.get('adapter_sha256')!=spec['source']['stable']['adapter_sha256']:
                raise RuntimeError('Última estável mudou; não ativar versão anterior')
        stage=record['stage_alias'];selected=_verify_installed(project,entity,spec['alias'])
        if selected['manifest_sha256']!=versions.sha(manifest_path(store(project,entity),stage)):
            raise RuntimeError('Alias não corresponde à publicação/probe anteriores')
        original=entity+'-'+FAMILY[model]+'-original-'+conversion_digest(spec['source'])[:12]+':latest'
        original_receipt=_verify_installed(project,entity,original)
        from .trabalhador import api
        with owned_daemon(home,project,entity) as endpoint:
            shown=api(endpoint,'/api/show',{'model':spec['alias']})
            selected['capabilities']=shown.get('capabilities',[])
            if spec['source']['vision'] and 'vision' not in selected['capabilities']:raise RuntimeError('Visão ausente')
        if spec['activate'] and spec['source']['kind']=='stable' and model=='qwen35-9b':
            _enable_neural_mode(project,entity)
        selected.update(entity=entity,model_id=model,state='verified',job_id=jid,
            source_sha256=spec['source_sha256'],source_kind=spec['source']['kind'],original=original_receipt,
            activated=spec['activate'],probe=probe,created=time.time(),download=False,training_started=False,
            publication_verified_without_replay=True)
        lab._write_json(path,selected)
        row.update(previous_error=row.get('error'),error=None,state='completed',recovery=selected,
                   artifact=str(path),operator_verification='Hashes/capabilities/unload anteriores, sem repetir ações',
                   finished=datetime.now(timezone.utc).isoformat())
        lab._save_job(home,jid,row)
        return selected


def probe_idle(endpoint,stage,spec):
    """Inferência mínima real e unload confirmado DENTRO do compute lease."""
    from core import resource_manager,gpu_metrics
    from .trabalhador import api
    from .treino_nf4_curto import sample_hardware,physical_pressure,thermal_pressure
    entity=spec['entity'];model=spec['model_id']
    layers=20 if model=='qwen35-9b' else -1
    budget=int((4 if model in ('alistair-4b','qwen35-4b') else 4.25 if model=='qwen35-9b' else 5)*GIB)
    samples=[];pressure=[];stop=threading.Event();start=time.monotonic()
    with resource_manager.compute_lease('llm',entity=entity,model_key=endpoint+'|'+stage,priority=5 if entity=='alistair' else 1,
            vram_bytes=budget,workspace_bytes=512*1024**2,cpu_fallback=entity=='alistair',
            opportunistic=entity=='alistair',wait=30) as lease:
        before=gpu_metrics.snapshot()
        def monitor():
            while not stop.wait(1):
                metrics=gpu_metrics.snapshot();row=sample_hardware(metrics,gpu_metrics.ram_available());samples.append(row)
                memory_pressure=(physical_pressure(metrics,row['ram_available'],resource_manager.gpu_policy()['margin_bytes'])
                    if lease['backend']=='gpu' else 'RAM física insuficiente/incerta para CPU'
                    if row['ram_available'] is None or row['ram_available']<2*GIB else None)
                reason=thermal_pressure(row) or memory_pressure
                if reason and not pressure:
                    pressure.append(reason)
                    try:endpoint.stop_owned()
                    except Exception as exc:pressure.append('Parada owned não confirmada: '+str(exc))
        observer=threading.Thread(target=monitor,daemon=True);observer.start()
        try:
            value=api(endpoint,'/api/chat',{'model':stage,'messages':[{'role':'user','content':'Responda somente: Olá.'}],
                'think':False,'stream':False,'keep_alive':30,'options':{'num_ctx':spec['context_max'],
                'num_predict':64,'num_gpu':0 if lease['backend']=='cpu' else layers}},timeout=300)
            if value.get('done') is not True or value.get('done_reason')=='length' or not value.get('message',{}).get('content'):
                raise RuntimeError('Probe sem resposta completa; importado não é executor validado')
            own=next((m for m in api(endpoint,'/api/ps',timeout=3).get('models',[])
                     if (m.get('name') or m.get('model'))==stage),None)
            if own is None or (lease['backend']=='gpu' and not own.get('size_vram')):
                raise RuntimeError('Residência GPU não confirmada')
            observed=gpu_metrics.snapshot()
            if pressure or (lease['backend']=='gpu' and (not observed.get('known') or
                    observed['used_bytes']>observed['total_bytes']-resource_manager.gpu_policy()['margin_bytes'])):
                raise RuntimeError('Probe excedeu margem/pressão ou métricas ficaram incertas')
            result={'done':True,'backend':lease['backend'],'context':spec['context_max'],
                'layers':0 if lease['backend']=='cpu' else layers,'vram_budget_bytes':budget,
                'resident_vram_bytes':own.get('size_vram'),'metrics':observed,'before':before,
                'load_seconds':value.get('load_duration',0)/1e9,'infer_seconds':value.get('eval_duration',0)/1e9,
                'total_seconds':value.get('total_duration',0)/1e9,'quality_approved':False}
        finally:
            stop.set();observer.join(timeout=35)
            # EOF/erro/timeout não libera lease enquanto o backend pode gerar.
            try:
                api(endpoint,'/api/generate',{'model':stage,'keep_alive':0,'stream':False},timeout=30)
                until=time.monotonic()+10
                while time.monotonic()<until:
                    if not api(endpoint,'/api/ps',timeout=3).get('models'):break
                    time.sleep(.2)
                else:raise RuntimeError('Unload não confirmado')
            except BaseException:
                endpoint.stop_owned()
                raise
        result.update(samples=samples,pressure=pressure,after=gpu_metrics.snapshot(),unload_confirmed=True,
                      lease_seconds=round(time.monotonic()-start,3))
        return result


def execute(home,project,spec,jid):
    entity=spec['entity'];runtime=Path(project)/'entidades'/entity/'runtime'
    runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/'entity.lock').open('a+') as lock:
        # A chamada da Central ainda pode estar liberando seu lock de revisão.
        # Handoff curto e limitado; entidade realmente ativa continua recusada.
        until=time.monotonic()+2
        while True:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=until:raise RuntimeError('Entidade ativa: conversão/importação adiada sem suspensão') from None
                time.sleep(.02)
        return _execute_idle(home,project,spec,jid)


def _execute_idle(home,project,spec,jid):
    """Chamado apenas pelo worker unificado, com os seus locks já adquiridos."""
    from core import resource_manager,gpu_metrics,diagnostics
    home=Path(home);project=Path(project);entity=spec['entity'];model=spec['model_id']
    versioned=bool(spec.get('version_kind'))
    receipt=Path(spec['receipt_path']) if versioned else receipt_path(home,entity,model)
    if not spec['needed']:return {'state':'already_installed','production_changed':False}
    if installed(project,entity,spec['missing_alias']):raise RuntimeError('Executor apareceu; não sobrescrever')
    if shutil.disk_usage(home).free<spec['required_bytes']:raise RuntimeError('Espaço insuficiente; nenhum modelo apagado')
    if gpu_metrics.ram_available() is None or gpu_metrics.ram_available()<spec['source']['bytes']+2*GIB:
        raise RuntimeError('RAM física insuficiente para conversão; swap não entra no orçamento')
    # Reservas kernel existentes; nenhum banco/fila de recursos paralelo.
    with resource_manager.lease('cpu_llm','model_conversion',entity=entity,wait=30):
        diagnostics.emit('model.recovery_started',entity=entity,job_id=jid,model=model,source=spec['source']['kind'])
        print('RECUPERACAO_FASE verificação SHA completa e conversão/cache local',entity,model,flush=True)
        files=convert_source(home,spec)
    print('RECUPERACAO_FASE revalidar fonte antes de importar',entity,model,flush=True)
    verify_source(spec['source'])
    basefiles=[f for f in files if f['kind']!='adapter']
    # Uma conversão rejeitada permanece como evidência, sem ser confundida com
    # o original conversível desta revisão do contrato.
    original=entity+'-'+FAMILY[model]+'-original-'+conversion_digest(spec['source'])[:12]+':latest'
    with owned_daemon(home,project,entity) as endpoint:
        print('RECUPERACAO_FASE importação local sem download',entity,model,flush=True)
        original_receipt=(_verify_installed(project,entity,original) if installed(project,entity,original) else
                          import_alias(home,project,entity,endpoint,original,basefiles,spec['context_max']))
        # Nunca publicar o alias selecionado antes da inferência/unload. Um
        # crash no probe deixa só staging visível, não um falso executor pronto.
        stage=entity+'-recovery-'+jid+':latest'
        staged=import_alias(home,project,entity,endpoint,stage,files,spec['context_max'])
        print('RECUPERACAO_FASE probe real e unload confirmado',entity,model,flush=True)
        probe=probe_idle(endpoint,stage,spec)
        # O recibo intermediário bloqueia wake/replay mesmo se /api/copy
        # concluir e o worker morrer antes do commit final de verificação.
        lab._write_json(receipt,dict(state='publishing',entity=entity,
            model_id=model,job_id=jid,alias=spec['alias'],stage_alias=stage,probe=probe,
            original=original_receipt,staged=staged,source_sha256=spec['source_sha256']))
        selected=publish_alias(project,entity,endpoint,stage,spec['alias'])
        if not versioned and spec['alias']!=spec['canonical_alias'] and not installed(project,entity,spec['canonical_alias']):
            publish_alias(project,entity,endpoint,original,spec['canonical_alias'])
        selected['capabilities']=staged['capabilities']
    selected.update(entity=entity,model_id=model,state='verified',job_id=jid,
        source_sha256=spec['source_sha256'],source_kind=spec['source']['kind'],original=original_receipt,
        activated=False,probe=probe,
        created=time.time(),download=False,training_started=False)
    # Ativação só após saída da carga/unload. Não toca identidade ou banco mental.
    if spec['activate'] and spec['source']['kind']=='stable' and model=='qwen35-9b':
        _enable_neural_mode(project,entity)
    selected['activated']=spec['activate']
    if versioned:
        selected.update(version_kind=spec['version_kind'],version_ref=spec['version_ref'],
            experimental=spec['experimental'],quality_approved=spec['quality_approved'])
    lab._write_json(receipt,selected)
    diagnostics.emit('model.recovery_verified',entity=entity,job_id=jid,model=model,alias=selected['alias'],
                     manifest_sha256=selected['manifest_sha256'],source_kind=selected['source_kind'],activated=selected['activated'])
    print('RECUPERACAO_VERIFICADA',entity,model,selected['alias'],flush=True)
    return selected


if __name__=='__main__':cli()
