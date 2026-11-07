"""Versões de executor por entidade, com compatibilidade Original/Neural 9B.

Não altera identidade/memória/.env. Ausência de configuração implica Original.
Checkpoints e treinos são pinados a recibos do Ollama isolado, não a 'últimos' flutuantes.
"""
import hashlib
import json
import re
from pathlib import Path

ENTITIES = ('hoshino', 'lilith')
ALIASES = {'hoshino':'hoshino-neural9b:latest', 'lilith':'lilith-neural9b:latest'}
STORES = {'hoshino':'ollama', 'lilith':'ollama-lilith'}
MODEL_FAMILIES = {'qwen35-9b', 'qwen35-4b', 'qwen25-7b', 'yi-6b', 'alistair-4b'}

def path(root):
    return Path(root) / 'compartilhado/config/neural9b_modes.json'

def revision(root):
    p=path(root)
    return hashlib.sha256(p.read_bytes() if p.is_file() else b'').hexdigest()

def read_document(root):
    p=path(root)
    if p.is_symlink(): raise ValueError('Configuração neural não pode ser link simbólico')
    if not p.exists(): return {'hoshino':'original','lilith':'original'}
    if p.stat().st_size>65536:raise ValueError('Configuração neural muito grande')
    obj=json.loads(p.read_text(encoding='utf8'))
    if (not isinstance(obj,dict) or set(obj)-set(ENTITIES)-{'executor_versions','hl_families'} or
            any(obj.get(e,'original') not in ('original','neural9b') for e in ENTITIES)):
        raise ValueError('Configuração neural inválida')
    families=obj.get('hl_families',['qwen35-9b','qwen25-7b','yi-6b'])
    if (not isinstance(families,list) or not families or len(families)!=len(set(families)) or
            any(f not in MODEL_FAMILIES-{'alistair-4b'} for f in families)):
        raise ValueError('Famílias autorizadas inválidas')
    versions=obj.get('executor_versions',{})
    if not isinstance(versions,dict) or set(versions)-{'hoshino','lilith','alistair'}:
        raise ValueError('Seleção de versões inválida')
    for entity,selection in versions.items():
        allowed={'alistair-4b'} if entity=='alistair' else set(families)
        if (not isinstance(selection,dict) or set(selection)-{'primary','models'} or
                selection.get('primary') not in allowed or not isinstance(selection.get('models'),dict) or
                set(selection['models'])-allowed):
            raise ValueError('Família/entidade inválida na seleção')
        for model,row in selection['models'].items():
            if (not isinstance(row,dict) or row.get('entity')!=entity or row.get('model_id')!=model or
                    row.get('kind') not in {'original','checkpoint','trained','stable'} or
                    not re.fullmatch(r'[a-f0-9]{64}',str(row.get('source_sha256',''))) or
                    not re.fullmatch(r'[a-f0-9]{64}',str(row.get('manifest_sha256',''))) or
                    not isinstance(row.get('alias'),str) or len(row['alias'])>200):
                raise ValueError('Origem de executor inválida')
    return obj

def read_modes(root):
    obj=read_document(root)
    return {e:obj.get(e,'original') for e in ENTITIES}

def enabled_families(root,entity):
    if entity=='alistair':return {'alistair-4b'}
    if entity not in ENTITIES:raise ValueError('Entidade desconhecida')
    return set(read_document(root).get('hl_families',['qwen35-9b','qwen25-7b','yi-6b']))

def primary_family(root,entity):
    return read_document(root).get('executor_versions',{}).get(entity,{}).get('primary')

def selected_version(root,entity,model):
    return read_document(root).get('executor_versions',{}).get(entity,{}).get('models',{}).get(model)

def context_limit(root,entity):
    # 9B: até 32K medido na placa em 28/10 (perfil do RM governa o que cabe); o .env escolhe.
    return {'yi-6b':4096,'qwen25-7b':8192,'qwen35-4b':8192,'qwen35-9b':32768,'alistair-4b':8192}.get(primary_family(root,entity),8192 if entity=='alistair' else 16384)

def runtime_alias(root,entity,model):
    """Seleção pinada, jamais o 'último' flutuante após outro treinamento."""
    row=selected_version(root,entity,model)
    if not row:return None
    from laboratorio import recuperacao_modelos as recovery
    storage=recovery.store(root,entity)
    manifest=recovery.manifest_path(storage,row['alias'])
    if (manifest.is_symlink() or not manifest.is_file() or not recovery.installed(root,entity,row['alias']) or
            hashlib.sha256(manifest.read_bytes()).hexdigest()!=row['manifest_sha256']):
        raise ValueError('Versão selecionada ausente/divergente; selecione Original. Não houve fallback silencioso.')
    if row['kind']!='original':
        home=Path(root)/'laboratorio-local'
        receipt=recovery.version_receipt(home,root,entity,model,row['source_sha256'])
        if not receipt or receipt['alias']!=row['alias']:
            raise ValueError('Recibo da versão selecionada não confirmado')
    return row['alias']

def model_ready(root,entity):
    if entity not in ENTITIES:raise ValueError('Neural 9B apenas para Hoshino e Lilith')
    storage=Path(root)/'compartilhado/modelos'/STORES[entity]
    manifest=storage/'manifests/registry.ollama.ai/library'/ALIASES[entity].replace(':','/')
    if not manifest.is_file() or manifest.is_symlink(): return False
    try:
        if manifest.stat().st_size>1_000_000:return False
        data=json.loads(manifest.read_text(encoding='utf8'))
        blobs=[data['config'],*data['layers']]
        if not blobs:return False
        for info in blobs:
            digest=info['digest'];size=info['size']
            if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest) or type(size)!=int or size<0:return False
            blob=storage/'blobs'/digest.replace(':','-')
            if not blob.is_file() or blob.is_symlink() or blob.stat().st_size!=size:return False
        # Ollama manifests may refer to many small blobs; ensure at least one large weight layer.
        return any(info['size']>=1024*1024 for info in data['layers'])
    except (ValueError,OSError,KeyError,TypeError,IndexError):return False

def status(root,entity):
    if entity not in ENTITIES:raise ValueError('Neural 9B apenas para Hoshino e Lilith')
    return {'entity':entity,'mode':read_modes(root)[entity], 'neural_alias':ALIASES[entity],
            'neural_ready':model_ready(root,entity),'revision':revision(root),
            'note':'Troca somente dormindo. Original preserva .env, identidade, memória, modelos e processos anteriores.'}

def startup_override(root,entity):
    family=primary_family(root,entity)
    if family:
        selected=runtime_alias(root,entity,family)
        if not selected:raise ValueError('Família principal sem versão selecionada')
        return selected
    if entity not in ENTITIES:return None
    if read_modes(root)[entity]=='original':return None
    if not model_ready(root,entity):
        raise ValueError(f'Neural 9B de {entity} não está instalado no armazenamento Ollama desta entidade. Troque para Original ou instale o adaptador convertido.')
    return ALIASES[entity]
