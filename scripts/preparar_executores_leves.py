#!/usr/bin/env python3
"""Prepara executores aprovados em catálogos separados, sem tocar nas mentes.

O padrão é planejamento somente leitura. --instalar autoriza pull/criação nos
dois daemons locais existentes. Não inicia/reinicia processos ou faz inferência.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'qwen2.5:7b-instruct-q4_K_M'
NEUTRAL_SYSTEM = ('Executor local de texto. A aplicação fornece a identidade, memória, relações e estado '
                  'da entidade em cada pedido. Não assuma uma identidade própria do modelo. '
                  'Responda em português do Brasil e siga o contexto fornecido pela aplicação.')
GIB = 1024**3
ESTIMATED_BYTES = 5*GIB  # catálogo: ~4,7 GB; teto conservador por cópia
RESERVE_BYTES = 10*GIB
ENTITIES = {'hoshino': ('http://127.0.0.1:11435', 'ollama'),
            'lilith': ('http://127.0.0.1:11436', 'ollama-lilith')}
SELECTION = {
    'hunyuan-7b': ('hunyuan7/tencent_Hunyuan-7B-Instruct-Q4_K_M.gguf',
                  '37361ed44b126de00a551260fd7c3de3c3a7a58d6060bce99b6b8fe0c0665d63',4621992960),
    'qwenjan-6b': ('qwenjan6/Qwen3-Jan-v1-256k-ctx-6B-Brainstorm20x.Q5_K_M.gguf',
                  'de4a21839013515909959112d67a5cda31e99a5b3e89a6b4df95376907cc7c3f',4241176000),
    'esper3-6b': ('esper3-6b/Qwen3-Esper3-Reasoning-Instruct-6B-Brainstorm20x-Enhanced-E32.Q5_K_M.gguf',
                 'c6e8b85ffd17184ec44103c2ee2348203fd5f8ccb63fc87750173c71ca873d72',4241176352),
    'qwen3.5-4b': ('qwen35-4b/Qwen3.5-4B-Q4_K_M.gguf',
                  '00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4',2740937888),
}
# O importador reescreve metadados GGUF: estes são os pesos efetivamente
# importados e verificados nesta seleção, não o hash do arquivo baixado.
IMPORTED_WEIGHTS = {
    'hunyuan-7b':'1b40cd94ebddde0587cb836cd9c0d5aa2961fa3df828a9f7d8414ae6f412180c',
    'qwenjan-6b':'fd3cd77d2f1d8a55d09dcef1f85be4997b0ee16792786313b8be14dadf3564a9',
    'esper3-6b':'bc145c8bfca3e9df3ea90a3e547ff26ac099a18127f185096f62bdde2cd13800',
    'qwen3.5-4b':'d1f31e92476a72cbf464ae849567917b2a5fe78003906e94ae5c69b742767204',
}


def manifest_path(storage,model):
    name, tag = model.rsplit(':', 1)
    parts=name.split('/')
    if len(parts)==1:parts=['registry.ollama.ai','library',*parts]
    elif len(parts)==2:parts=['registry.ollama.ai',*parts]
    if any(not re.fullmatch(r'[A-Za-z0-9_.-]+',p) or p in ('.','..') for p in (*parts,tag)):
        raise ValueError('Nome de modelo inválido')
    return Path(storage)/'manifests'/Path(*parts)/tag


def manifest_blobs(storage, model):
    path=manifest_path(storage,model)
    if path.is_symlink():raise ValueError('Manifesto simbólico recusado')
    manifest = json.loads(path.read_text())
    return [manifest['config'], *manifest['layers']]


def installed(storage, model):
    try:
        blobs = manifest_blobs(storage, model)
        return bool(blobs) and all((storage/'blobs'/b['digest'].replace(':', '-')).stat().st_size == b['size'] for b in blobs)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def plan(root=ROOT):
    root = Path(root)
    missing = [e for e, (_, directory) in ENTITIES.items()
               if not installed(root/'compartilhado/modelos'/directory, SOURCE)]
    final = len(missing)*ESTIMATED_BYTES
    # Uma cópia em download/parcial adicional, mesmo que o backend possa renomear.
    staging = ESTIMATED_BYTES if missing else 0
    free = shutil.disk_usage(root).free
    required = final+staging+RESERVE_BYTES
    return dict(entities=missing, free_bytes=free, estimated_final_bytes=final,
                staging_bytes=staging, reserve_bytes=RESERVE_BYTES,
                required_bytes=required, safe=free>=required, source=SOURCE)


def guard(root, required):
    if shutil.disk_usage(root).free < required:
        raise RuntimeError('Instalação bloqueada: espaço abaixo de download + reserva segura. Nenhum modelo apagado.')


def stream(base, path, payload, root, *, timeout_seconds=3600):
    began = time.monotonic()
    # A conversão GGUF pode passar 30s sem emitir uma linha. Mantém prazo finito
    # sem tratar silêncio normal do importador como instalação concluída.
    with requests.post(base+path, json=payload, stream=True, timeout=(3, 120)) as response:
        response.raise_for_status()
        success = False
        for raw in response.iter_lines():
            guard(root, RESERVE_BYTES)
            if time.monotonic()-began > timeout_seconds:
                raise TimeoutError('Instalação excedeu prazo; nenhuma repetição automática.')
            if not raw: continue
            item = json.loads(raw)
            if item.get('error'): raise RuntimeError('Backend não confirmou instalação do modelo aprovado.')
            if item.get('status')=='success': success = True
        if not success: raise RuntimeError('Instalação sem recibo de sucesso.')


def verify(storage, model):
    records = []
    for blob in manifest_blobs(storage, model):
        digest = blob['digest']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise ValueError('Digest inválido')
        path = storage/'blobs'/digest.replace(':', '-')
        if path.is_symlink() or path.stat().st_size != blob['size']:
            raise ValueError('Cópia independente/tamanho não confirmados')
        h = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(8*1024**2), b''): h.update(chunk)
        if h.hexdigest()!=digest[7:]: raise ValueError('Hash do modelo inválido')
        records.append(dict(digest=digest, bytes=blob['size']))
    return records


def install(root=ROOT):
    root = Path(root)
    before = plan(root)
    guard(root, before['required_bytes'])
    receipts = []
    for entity, (base, directory) in ENTITIES.items():
        storage = root/'compartilhado/modelos'/directory
        alias = entity+'-qwen2.5-7b:latest'
        # Somente daemons existentes nos ports do projeto; sem fallback a 11434.
        response = requests.get(base+'/api/tags', timeout=(1, 3))
        response.raise_for_status()
        if not installed(storage, SOURCE):
            guard(root, 2*ESTIMATED_BYTES+RESERVE_BYTES)
            stream(base, '/api/pull', {'model': SOURCE}, root)
        source_blobs = verify(storage, SOURCE)
        alias_ready = installed(storage, alias)
        if alias_ready:
            show = requests.post(base+'/api/show', json={'model':alias}, timeout=(1,3))
            show.raise_for_status()
            alias_ready = show.json().get('system') == NEUTRAL_SYSTEM
        if not alias_ready:
            stream(base, '/api/create', {'model': alias, 'from': SOURCE,
                'system': NEUTRAL_SYSTEM, 'parameters': {'num_ctx':8192}}, root)
        alias_blobs = verify(storage, alias)
        # Pesos do alias devem ser os mesmos da fonte verificada neste catálogo.
        weight = max(source_blobs, key=lambda b: b['bytes'])
        if weight not in alias_blobs: raise ValueError('Alias não usa o peso aprovado')
        weight_stat = (storage/'blobs'/weight['digest'].replace(':','-')).stat()
        check = requests.get(base+'/api/tags', timeout=(1, 3))
        check.raise_for_status()
        if not any((m.get('name') or m.get('model'))==alias for m in check.json()['models']):
            raise RuntimeError('Alias não confirmado na API do catálogo correto')
        receipts.append(dict(entity=entity, executor=alias, weight_bytes=weight['bytes'],
                             weight_sha256=weight['digest'], file_id=[weight_stat.st_dev,weight_stat.st_ino], verified=True))
    if receipts[0]['file_id']==receipts[1]['file_id']:
        raise ValueError('Os dois catálogos compartilham um inode de pesos; independência não confirmada.')
    return dict(before=before, after=plan(root), receipts=receipts)


def install_selected(root=ROOT, *, entity, candidate):
    """Importa somente arquivo escolhido/verificado; não muda executor ativo.

    Download é explícito pelo hf CLI. Sem pull implícito, inferência, wake ou DB
    mental. Catálogo independente por entidade; pesos não são sobrescritos.
    """
    root=Path(root)
    if entity not in {'hoshino','lilith','alistair'} or candidate not in SELECTION:
        raise ValueError('Seleção não autorizada')
    if (entity=='alistair') != (candidate=='qwen3.5-4b'):
        raise ValueError('Executor não pertence a esta entidade')
    relative, digest, size=SELECTION[candidate]
    path=root/'compartilhado/modelos/candidatos-20261008'/relative
    port={'hoshino':11435,'lilith':11436,'alistair':11437}[entity]
    base=f'http://127.0.0.1:{port}'
    storage=root/'compartilhado/modelos'/('ollama' if entity=='hoshino' else 'ollama-'+entity)
    alias=entity+'-'+candidate+':latest'
    alias_ready=installed(storage,alias)
    if not alias_ready:
        if path.is_symlink() or path.stat().st_size != size:
            raise ValueError('Arquivo/tamanho não confirmado')
        with path.open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest()!=digest:
                raise ValueError('Hash da fonte incorreto')
    check=requests.get(base+'/api/ps',timeout=(1,3));check.raise_for_status()
    if check.json().get('models'):
        raise RuntimeError('Daemon possui modelo residente; importação adiada')
    if not alias_ready:
        guard(root,2*size+20*GIB)
        with path.open('rb') as source:
            upload=requests.post(base+'/api/blobs/sha256:'+digest,data=source,timeout=(5,300))
            upload.raise_for_status()
        parameters={'num_ctx':4096 if entity=='alistair' else 8192,
                    'num_predict':768 if entity=='alistair' else 2048}
        if entity=='alistair': parameters.update(num_gpu=0,num_thread=4)
        stream(base,'/api/create',{'model':alias,'files':{path.name:'sha256:'+digest},
               'system':NEUTRAL_SYSTEM,'parameters':parameters},root)
    verified=verify(storage,alias)
    expected_weight = IMPORTED_WEIGHTS.get(candidate)
    weight = max(verified, key=lambda b: b['bytes'])
    if (weight['bytes'] != size or
            (expected_weight and weight['digest'] != 'sha256:'+expected_weight) or
            (not expected_weight and alias_ready)):
        raise ValueError('Alias não contém o peso importado aprovado')
    # Primeiro import de candidato novo: o arquivo de origem foi conferido
    # antes do upload; todos os blobs produzidos foram relidos e hasheados.
    # Alias preexistente sem hash fixado não é confiável. O recibo conserva o
    # hash pós-conversão para pinagem antes de reutilização/ativação.
    show=requests.post(base+'/api/show',json={'model':alias},timeout=(1,5));show.raise_for_status()
    if show.json().get('system')!=NEUTRAL_SYSTEM:
        raise ValueError('Identidade pré-embutida diferente do contrato')
    if candidate == 'esper3-6b' and (show.json().get('details', {}).get('family') != 'qwen3' or
            show.json().get('details', {}).get('quantization_level') != 'Q5_K_M'):
        raise ValueError('Esper3 importado incompatível com arquitetura/quantização aprovadas')
    return dict(entity=entity,model=alias,source_sha256=digest,blobs=verified,
                capabilities=show.json().get('capabilities'),details=show.json().get('details'),activated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instalar', action='store_true')
    parser.add_argument('--entidade',choices=('hoshino','lilith','alistair'))
    parser.add_argument('--candidato',choices=tuple(SELECTION))
    args = parser.parse_args()
    if args.candidato or args.entidade:
        if not args.instalar or not (args.candidato and args.entidade):
            parser.error('Importação escolhida exige --instalar --entidade --candidato')
        result=install_selected(entity=args.entidade,candidate=args.candidato)
    else:
        result=install() if args.instalar else plan()
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__': main()
