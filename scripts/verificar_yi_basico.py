#!/usr/bin/env python3
"""Ensaio opt-in do Yi original existente; sem chat/memória, instalação ou treino.

--run autoriza inferência real sequencial no daemon owned, sob locks e RM.
O JSON guarda só casos sintéticos e medições, nunca pensamentos privados.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'app')]


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).casefold()) if not unicodedata.combining(c))


def cases(entity):
    return [
        ('identity', [{'role':'user','content':'Qual é seu nome? Responda em uma frase curta.'}]),
        ('instruction', [{'role':'user','content':'Responda apenas com a palavra PRONTO.'}]),
        ('portuguese', [{'role':'user','content':'Explique em uma frase em português para que serve um guarda-chuva.'}]),
        ('arithmetic', [{'role':'user','content':'Tenho três lápis e ganho mais dois. Quantos lápis tenho? Responda apenas com o número.'}]),
        ('context', [{'role':'user','content':'Neste teste fictício, meu nome é Nara e guardei um lápis na caixa azul.'},
                     {'role':'assistant','content':'Entendido.'},
                     {'role':'user','content':'Qual é meu nome e qual é a cor da caixa?'}]),
        ('unknown_memory', [{'role':'user','content':'Sem eu ter contado isso antes: o que comi ontem?'}]),
        ('attribution', [{'role':'user','content':'Nara disse: eu gosto de astronomia. Alistair disse: eu gosto de xadrez. Quem gosta de quê?'}]),
        ('translation', [{'role':'user','content':'Traduza para português apenas esta frase: The blue box is open.'}]),
    ]


def basic_check(identifier, answer, entity):
    """Asserções mínimas transparentes; a revisão semântica continua necessária."""
    text = normalize(answer)
    if identifier == 'identity': return entity in text and not re.search(r'\b(?:qwen|yi|lilith|hoshino)\b', text.replace(entity,''))
    if identifier == 'instruction': return text.strip().rstrip('.!') == 'pronto'
    if identifier == 'portuguese': return 'chuva' in text and bool(re.search(r'proteg.{0,40}chuva|chuva.{0,40}proteg|nao.{0,20}molh|manter.{0,25}sec[oa]', text)) and len(answer)<500
    if identifier == 'arithmetic': return text.strip().rstrip('.!') == '5'
    if identifier == 'context':
        return ('nara' in text and 'azul' in text and not re.search(r'vermelh|amarel|verde|roxo|fora de contexto|nao.{0,70}(?:mencion|consigo|responder)',text))
    if identifier == 'unknown_memory': return bool(re.search(r'nao (?:sei|tenho|posso|lembro|me contou)|nao ha|sem (?:essa|essa informacao|informac)|desconheco|nao foi', text))
    if identifier == 'attribution':
        return bool(re.search(r'nara[^.!?\n]{0,70}astronomia|astronomia[^.!?\n]{0,35}nara', text)
                    and re.search(r'alistair[^.!?\n]{0,70}xadrez|xadrez[^.!?\n]{0,35}alistair', text))
    if identifier == 'translation': return 'caixa azul' in text and 'aberta' in text
    return False


def idle(project, home):
    """Leitura sem inicializar bancos mentais ou agendamentos."""
    from core import resource_manager as rm
    from laboratorio import treinos_unificados as lab
    for name, query in (
        ('interentidades.sqlite3', "SELECT count(*) FROM entities_presence WHERE status NOT IN ('sleeping','offline') OR pid IS NOT NULL"),
        ('jobs_compartilhados.sqlite3', "SELECT count(*) FROM jobs WHERE status IN ('queued','running')")):
        path=project/'compartilhado/runtime'/name
        if path.exists():
            with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute(query).fetchone()[0]: raise RuntimeError('Entidade/job ativo: ensaio adiado, sem interrupção')
    if rm.status() or rm.gpu_state()['queue']:
        raise RuntimeError('RM ocupado; ensaio não força concessão')
    if any(j['state'] in ('started','running','cancel_requested','queued') for j in lab.jobs(home)):
        raise RuntimeError('Job do laboratório ativo; ensaio adiado')


def run(entity, output, *, native=False, cpu=False, selected_cases=None):
    import config
    from core import gpu_metrics, neural9b_modes as modes, resource_manager as rm
    from core.central_control import atomic_save, revision
    from core.yi_companion import CONTEXT, OUTPUT, receipt_path, native_prompt
    from laboratorio import recuperacao_modelos as recovery
    from laboratorio.treino_nf4_curto import sample_hardware, physical_pressure, thermal_pressure
    from laboratorio.trabalhador import api
    from scripts.preparar_executores_leves import NEUTRAL_SYSTEM
    if config.ENTIDADE_ID != entity:
        raise ValueError('Ambiente não corresponde à entidade; execute com ambiente limpo')
    project=Path(config.RAIZ).resolve();home=project/'laboratorio-local'
    relative=str(Path(output).relative_to(project)) if Path(output).is_absolute() else output
    target=receipt_path(project,relative)
    if target.exists():raise ValueError('Recibo existente preservado; escolha outro nome, sem repetir automaticamente')
    selected=modes.selected_version(project,entity,'yi-6b')
    if not selected or selected['kind']!='original':raise ValueError('Este ensaio requer o Yi original selecionado')
    model=modes.runtime_alias(project,entity,'yi-6b')
    chosen=[(i,m) for i,m in cases(entity) if selected_cases is None or i in selected_cases]
    if not chosen or (selected_cases and set(selected_cases)-{i for i,_ in cases(entity)}):raise ValueError('Casos inválidos')
    report=dict(schema=1,scope='diagnostic_only' if native or cpu or selected_cases else 'basic_text_only',entity=entity,model=model,kind=selected['kind'],
        source_sha256=selected['source_sha256'],manifest_sha256=selected['manifest_sha256'],
        created_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),passed=False,checks=[],physical={},cleanup={},
        memory_written=False,training_started=False,download=False,protocol='yi_native_v1' if native else 'ollama_chat',
        semantic_review=dict(completed=False,passed=False))
    error=None;pressure=[];samples=[];resident=0;stop=threading.Event();observer=None
    registry=home/'controle-laboratorio/treinamento-unificado'
    with contextlib.ExitStack() as locks:
        for path in (registry/'start.lock',home/'controle-laboratorio/trabalhador.lock',
                     project/'entidades/hoshino/runtime/entity.lock',project/'entidades/lilith/runtime/entity.lock'):
            lock=locks.enter_context(path.open('a+'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        idle(project,home)
        try:
            with recovery.owned_daemon(home,project,entity) as endpoint:
                shown=api(endpoint,'/api/show',{'model':model},timeout=10)
                report['capabilities']=shown.get('capabilities',[])
                if 'completion' not in report['capabilities']:raise RuntimeError('Backend sem completion')
                with rm.compute_lease('llm',entity=entity,model_key=endpoint+'|'+model,priority=5,
                        vram_bytes=5*gpu_metrics.GIB,workspace_bytes=512*1024**2,cpu_fallback=False,wait=30) as lease:
                    def monitor():
                        while not stop.wait(.5):
                            m=gpu_metrics.snapshot();row=sample_hardware(m,gpu_metrics.ram_available());samples.append(row)
                            reason=thermal_pressure(row) or physical_pressure(m,row['ram_available'],rm.gpu_policy()['margin_bytes'])
                            if reason and not pressure:
                                pressure.append(reason)
                                try:endpoint.stop_owned()
                                except Exception as exc:pressure.append('Parada owned incerta: '+type(exc).__name__)
                    observer=threading.Thread(target=monitor,daemon=True);observer.start()
                    try:
                        initial=sample_hardware(gpu_metrics.snapshot(),gpu_metrics.ram_available());samples.append(initial)
                        reason=thermal_pressure(initial) or physical_pressure(gpu_metrics.snapshot(),initial['ram_available'],rm.gpu_policy()['margin_bytes'])
                        if reason:raise RuntimeError(reason)
                        system=NEUTRAL_SYSTEM+'\nEnsaio sintético isolado, sem experiências humanas reais. Meu nome neste contexto é '+entity.capitalize()+'. Não invento lembranças de informações não fornecidas.'
                        if cpu and gpu_metrics.ram_available()<12*gpu_metrics.GIB:raise RuntimeError('RAM insuficiente para controle CPU')
                        for identifier, messages in chosen:
                            if pressure:raise RuntimeError(pressure[0])
                            begin=time.monotonic()
                            payload=dict(model=model,messages=[dict(role='system',content=system),*messages],
                                stream=False,keep_alive=60,options=dict(num_ctx=CONTEXT,num_predict=OUTPUT,num_gpu=0 if cpu else -1,
                                                                     temperature=0,seed=42))
                            if native:payload.update(prompt=native_prompt(payload.pop('messages')),raw=True)
                            value=api(endpoint,'/api/generate' if native else '/api/chat',payload,timeout=90)
                            answer=str(value.get('response','') if native else value.get('message',{}).get('content','')).strip()
                            complete=value.get('done') is True and value.get('done_reason')=='stop' and bool(answer)
                            row=dict(id=identifier,answer=answer,done=value.get('done'),done_reason=value.get('done_reason'),
                                passed=complete and basic_check(identifier,answer,entity),seconds=round(time.monotonic()-begin,3),
                                load_seconds=value.get('load_duration',0)/1e9,prompt_tokens=value.get('prompt_eval_count'),
                                answer_tokens=value.get('eval_count'),eval_seconds=value.get('eval_duration',0)/1e9)
                            report['checks'].append(row)
                            print(json.dumps(dict(entity=entity,**row),ensure_ascii=False),flush=True)
                            own=next((m for m in api(endpoint,'/api/ps',timeout=3).get('models',[]) if (m.get('name')or m.get('model'))==model),{})
                            resident=max(resident,own.get('size_vram') or 0)
                            if not complete:raise RuntimeError('Resposta incompleta; sem retry ou aumento de orçamento')
                    finally:
                        # Nunca libera compute enquanto o backend pode continuar gerando.
                        try:
                            api(endpoint,'/api/generate',dict(model=model,keep_alive=0,stream=False),timeout=30)
                            until=time.monotonic()+10
                            while time.monotonic()<until:
                                if not api(endpoint,'/api/ps',timeout=3).get('models'):break
                                time.sleep(.2)
                            else:raise RuntimeError('Unload não confirmado')
                            report['cleanup']['unload_confirmed']=True
                        except BaseException:
                            endpoint.stop_owned()
                            report['cleanup']['owned_stopped_after_error']=True
                            raise
                        finally:
                            stop.set();observer.join(timeout=35)
        except Exception as exc:
            error=exc;report['error']=str(exc);report['error_type']=type(exc).__name__
        finally:
            stop.set()
            if observer:observer.join(timeout=35)
            current=gpu_metrics.snapshot();until=time.monotonic()+3
            while not current.get('stable') and time.monotonic()<until:
                time.sleep(.1);current=gpu_metrics.snapshot()
            report['cleanup']['lease_released']=not any(r['entity']==entity for r in rm.status('gpu'))
            report['physical']=dict(context=CONTEXT,layers=0 if cpu else -1,backend='cpu' if cpu else 'gpu',resident_vram_bytes=resident,
                metrics_known_stable=current.get('known') is True and current.get('stable') is True,
                pressure=pressure,samples=samples,after=current,ram_available=gpu_metrics.ram_available())
            report['passed']=(not error and len(report['checks'])==8 and all(c['passed'] for c in report['checks'])
                and not pressure and current.get('known') is True and current.get('stable') is True
                and (cpu or resident>0) and report['cleanup'].get('unload_confirmed') is True
                and report['cleanup'].get('lease_released') is True)
            target.parent.mkdir(parents=True,exist_ok=True)
            atomic_save(target,json.dumps(report,ensure_ascii=False,indent=2)+'\n',revision(target))
    print(json.dumps(dict(entity=entity,passed=report['passed'],report=str(target),cleanup=report['cleanup']),ensure_ascii=False),flush=True)
    if error:raise error
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entity',choices=('hoshino','lilith'),required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--native',action='store_true',help='Diagnóstico com o template nativo, sem alterar o alias')
    parser.add_argument('--cpu',action='store_true',help='Controle diagnóstico CPU, ainda sob exclusão de compute')
    parser.add_argument('--cases',help='Subconjunto diagnóstico separado por vírgulas; não homologa o básico')
    args=parser.parse_args()
    if not args.run:
        print(json.dumps(dict(cases=[i for i,_ in cases(args.entity)],requires='--run para inferência real')));return
    if run(args.entity,args.output,native=args.native,cpu=args.cpu,
           selected_cases=args.cases.split(',') if args.cases else None)['passed'] is not True:raise SystemExit(2)


if __name__=='__main__':main()
