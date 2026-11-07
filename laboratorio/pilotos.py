"""Fila opt-in: Alistair 4B e Yi 6B, sem concorrer com a automacao 9B.

NAO baixa automaticamente. O 6B pode receber corpus de Hoshino, Lilith
ou Alistair, mas requer escolha explicita do operador.
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from . import alistair
from .candidatos import model_root,validate_local
from .catalogo import BY_ID
from .experimentos import allowed_data,clean_params,gate_9b,create_job,job_info

SIX_ID='yi15-6b'


def choose_corpus(home:Path,entity:str)->str:
    from .corpus_atual import dataset_id
    if entity=='alistair':
        candidate=dataset_id('alistair')
    else:
        items=[x['id'] for x in allowed_data(home)
               if x['id'].startswith(dataset_id(entity))]
        preferred=dataset_id(entity)
        if preferred in items:
            candidate=preferred
        elif len(items)==1:
            candidate=items[0]
        else:
            raise RuntimeError(f'Nao foi possivel selecionar corpus v3 principal de {entity}: {items}.')
    if candidate not in {x['id'] for x in allowed_data(home)}:
        raise RuntimeError('Corpus nao instalado: '+candidate)
    return candidate


def plan(home:Path,entity:str):
    if entity not in ('hoshino','lilith','alistair'):
        raise ValueError('Informe aluno do 6B: hoshino, lilith ou alistair')
    model,output,dataset=alistair.paths(home)
    six=model_root(home,SIX_ID)
    try: corpus=choose_corpus(home,entity)
    except RuntimeError as e:corpus=None;failure=str(e)
    else:failure=''
    return dict(alistair_base_complete=alistair.complete(model),alistair_seed_present=(dataset/'recibo.json').exists(),
                alistair_probe_passed=(output/'.probe_passed.json').exists(),
                six_b_model=SIX_ID,six_b_repo=BY_ID[SIX_ID]['repo'],six_b_complete=validate_local(six,BY_ID[SIX_ID]['repo']),
                six_b_native_thinking=False,six_b_entity=entity,six_b_dataset=corpus,dataset_error=failure,
                requested_minutes_per_student=30,
                will_download=False,will_change_production=False,will_shutdown=False,
                ready_to_run=bool(alistair.complete(model) and (dataset/'recibo.json').is_file() and validate_local(six,BY_ID[SIX_ID]['repo']) and corpus))


def run(home:Path,entity:str):
    # Barreiras 9B: nao descarregar orquestrador alheio e nao suspender download.
    gate_9b(home,'cycle_30m')
    p=plan(home,entity)
    if not p['ready_to_run']:
        raise RuntimeError('Bases/datasets incompletos. Execute plan e baixe quando 9B estiver finalizado.')
    print('ETAPA 1: validar o Alistair 4B na GPU',flush=True)
    alistair.start_experiment(home,'probe',30)
    print('ETAPA 2: treinar Alistair 4B durante ate 30 minutos',flush=True)
    alistair.start_experiment(home,'train',30)
    print('ETAPA 3: Yi 6B sem thinking: testar, treinar 30min, converter, comparar.',flush=True)
    raw=dict(model=SIX_ID,operation='cycle_30m',minutes=30,dataset=p['six_b_dataset'],entity=entity,adapter='')
    clean_params(raw,home)
    job=create_job(home,raw)
    job_id=job['id']
    print('Job 6B:',job_id,flush=True)
    while True:
        state=job_info(home,job_id)
        if state['state'] in ('completed','failed','canceled'):
            if state['state']!='completed':
                raise RuntimeError(f'Piloto 6B {state["state"]}; consulte job log {job_id}. Motivo: {state.get("error","")}')
            print('Piloto 4B+6B concluido. NENHUM modelo foi instalado na Central.',flush=True)
            return {'alistair_pilot':'trained_unapproved','six_b_job':job_id,'state':state['state']}
        time.sleep(8)


def main(argv=None):
    ap=argparse.ArgumentParser(description='Pilotos sequenciais Alistair 4B + Yi 6B')
    ap.add_argument('action',choices=('plan','run'))
    ap.add_argument('--home',type=Path,default=Path.home()/'laboratorio-lora')
    ap.add_argument('--six-entity',choices=('hoshino','lilith','alistair'),required=True)
    ap.add_argument('--confirm',action='store_true')
    a=ap.parse_args(argv);home=a.home.expanduser().resolve()
    if a.action=='plan':
        print(json.dumps(plan(home,a.six_entity),indent=2,ensure_ascii=False))
    else:
        if not a.confirm:ap.error('run requer --confirm; consome GPU, nao faz download')
        print(json.dumps(run(home,a.six_entity),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
