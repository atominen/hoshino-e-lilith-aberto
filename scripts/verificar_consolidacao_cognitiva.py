#!/usr/bin/env python3
"""Opt-in real local inference, temporary mental state, existing RM and models.

The invented Luma protocol is a controlled learning fixture, NOT a physical
environment. Model replies are real; no mock supplies answers. Never starts an
entity, downloads weights, contacts a paid provider or writes production memory.
"""
import argparse
import asyncio
from contextlib import ExitStack, closing
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executar-real',action='store_true')
    parser.add_argument('--model',choices=('principal','leve'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--politica-pensante',action='store_true',help='Usar a política situacional existente, não forçar think.')
    args=parser.parse_args()
    if not args.executar_real:raise SystemExit('Ensaio real exige --executar-real; nunca roda pela suíte offline.')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',ANONYMIZED_TELEMETRY='False')
    import config
    entity=config.ENTIDADE_ID
    if entity not in {'hoshino','lilith'}:raise SystemExit('Selecione Hoshino ou Lilith no ambiente local.')
    # A shell may still export Hoshino's model when selecting Lilith. Follow
    # the entity's installed/approved executor catalog, as its launcher does.
    catalog=json.loads((Path(config.ENTITY_CONFIG_DIR)/'executores.json').read_text())
    approved={'hoshino':'hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M',
              'lilith':'lilith-qwen3.5-9b:latest'}
    if catalog['primary_gpu']['model']!=approved[entity]:raise SystemExit('Catálogo principal não corresponde ao modelo aprovado.')
    config.MODEL_NAME=approved[entity]
    original_db=Path(config.DB_PATH);original_runtime=Path(config.RUNTIME_DIR)
    def mental_digest():
        with closing(sqlite3.connect(original_db.as_uri()+'?mode=ro',uri=True)) as conn:
            return hashlib.sha256('\n'.join(conn.iterdump()).encode()).hexdigest()
    before=mental_digest()
    with ExitStack() as locks, tempfile.TemporaryDirectory(prefix='cognitive-real-') as folder:
        # Protect all production entities from a human wake during the assay.
        for name in ('hoshino','lilith','alistair'):
            lock=locks.enter_context((ROOT/'entidades'/name/'runtime/entity.lock').open('a+'))
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        temporary=Path(folder);config.DB_PATH=str(temporary/'mental.db');config.RUNTIME_DIR=str(temporary/'runtime')
        Path(config.RUNTIME_DIR).mkdir();config.VECTOR_DIR=str(temporary/'vector')
        config.EVENT_LOG_DIR=str(temporary/'events');config.ESTADO_MENTE=str(temporary/'runtime/estado_mente.json')
        for name in ('estado_mente.json','estado_psicologico.json'):
            path=original_runtime/name
            if path.is_file():shutil.copy2(path,Path(config.RUNTIME_DIR)/name)
        with closing(sqlite3.connect(original_db.as_uri()+'?mode=ro',uri=True)) as source, closing(sqlite3.connect(config.DB_PATH)) as target:
            source.backup(target)
        from core import bd,history,resource_manager as rm,gpu_resource,gpu_metrics,ollama_lifecycle,prompting
        from mind import daily_summary,reflection
        from memory import cognitive_notes as notes,knowledge_store
        from main import InterfaceHoshino
        import requests
        base=config.OLLAMA_URL.rsplit('/api/',1)[0]
        if base!='http://127.0.0.1:'+('11435' if entity=='hoshino' else '11436'):
            raise SystemExit('Endpoint inesperado; não testar daemon de outra entidade.')
        model=config.MODEL_NAME if args.model=='principal' else catalog['light']['model']
        if args.model=='leve' and model!=entity+'-qwen2.5-7b:latest':raise SystemExit('Leve fora da configuração aprovada.')
        response=requests.get(base+'/api/tags',timeout=5);response.raise_for_status()
        if model not in {m['name'] for m in response.json()['models']}:raise SystemExit('Modelo ausente; não baixar.')
        if rm.status():raise SystemExit('Recursos ativos; não iniciar ensaio.')
        now=datetime.now(timezone.utc)
        result={'entity':entity,'model':model,'type':'real_inference_isolated_learning_fixture',
                'production_memory_before':before,'started':history.utc_timestamp(now),'calls':[]}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        def save():
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');args.output.chmod(0o600)
        def infer(stage,text,*,schema=None,context=''):
            if args.politica_pensante:
                purpose={'learn':'reflection','daily_summary':'compaction','voluntary_note':'internal_small','next_day_apply':'task'}[stage]
                @rm.inference_cycle(purpose,inherit=False)
                async def cycle():
                    return invoke(stage,text,schema=schema,context=context)
                return asyncio.run(cycle())
            return invoke(stage,text,schema=schema,context=context)
        def invoke(stage,text,*,schema=None,context=''):
            messages=[{'role':'system','content':prompting.montar_prompt_sistema(situacao=text)},
                      {'role':'system','content':context or 'Laboratório isolado. Autor: pesquisador de teste; não é o usuário real. Nenhuma entidade ouviu automaticamente.'},
                      {'role':'user','content':text}]
            messages=InterfaceHoshino._normalizar_mensagens_ollama(messages)
            thinking=args.model=='principal' and args.politica_pensante and rm.thinking_for_cycle(messages)
            opts=rm.inference_options(messages,context_max=8192,output_max=2048 if thinking else 900,reasoning=thinking)
            opts.update(temperature=.2,seed=42)
            payload={'model':model,'messages':messages,'stream':False,'options':opts,'keep_alive':'3m'}
            if schema:payload['format']=schema
            if args.model=='principal':payload['think']=bool(thinking)
            began=time.monotonic();entry={'stage':stage,'metrics_before':gpu_metrics.snapshot()}
            print(json.dumps({'entity':entity,'model':model,'stage':stage,'phase':'started'}),flush=True)
            with gpu_resource.lease('llm',model=model,priority=5,cpu_fallback=False,wait=45) as admission:
                entry.update(admission=admission,queue_seconds=time.monotonic()-began)
                reply=requests.post(config.OLLAMA_URL,json=gpu_resource.routed_payload(payload,admission),timeout=(3,180))
                reply.raise_for_status();data=reply.json()
            answer=data.get('message',{}).get('content','').strip()
            entry.update(seconds=round(time.monotonic()-began,3),answer=answer,done=data.get('done'),
                         done_reason=data.get('done_reason'),context=opts['num_ctx'],
                         prompt_tokens=data.get('prompt_eval_count'),output_tokens=data.get('eval_count'),
                         load_seconds=data.get('load_duration',0)/1e9,metrics_after=gpu_metrics.snapshot(),
                         thinking_enabled=thinking,thinking_chars=len(data.get('message',{}).get('thinking','')))
            result['calls'].append(entry);save()
            if data.get('done') is not True or data.get('done_reason')!='stop' or not answer:
                raise RuntimeError('Geração parcial/vazia não é aprendizado aprovado.')
            return json.loads(answer) if schema else answer
        try:
            facts=[('e-luma-1','No simulador Luma-37, transferência normal exige selo verde E origem validada. Uma transferência com selo verde e origem falsa foi recusada.', 'recusada'),
                   ('e-luma-2','Alarme roxo exige interrupção imediata, mesmo com selo verde e origem validada. Não é prova de desinteresse de uma pessoa.', 'interrompida'),
                   ('e-luma-3','Com selo verde, origem validada e sem alarme roxo, a transferência controlada ocorreu. Selo âmbar exige investigar, não transferir.', 'transferida')]
            for eid,text,outcome in facts:
                bd.executar("INSERT INTO episodes(id,created_at,what_happened,action_taken,result,source,context,status) VALUES(?,?,?,?,?,?,?,'active')",
                    (eid,history.utc_timestamp(now),text,'simulação declarada do protocolo',outcome,'ensaio_isolado',
                     json.dumps({'autoria':{'autor_nome':'Pesquisador de teste','message_id':'lab-'+eid},'observer':entity})),strict=True)
            schema={'type':'object','properties':{k:{'type':'string'} for k in ('interpretacao','condicao','licao')},
                    'required':['interpretacao','condicao','licao','excecoes'],'additionalProperties':False}
            schema['properties']['excecoes']={'type':'array','items':{'type':'string'}}
            learned=infer('learn','Organize uma lição provisória, condições e exceções destas experiências, com suas palavras. Não diga que viveu isso no mundo físico.\n'+
                          '\n'.join(text for _,text,_ in facts),schema=schema)
            memory=notes.learn_experience([e[0] for e in facts],learned['interpretacao'],learned['condicao'],learned['licao'],learned['excecoes'])
            result['memory_committed']=memory
            prepared=daily_summary.prepare(history.local_datetime(now).date().isoformat(),agora=now+timedelta(seconds=1),max_chars=7000)
            summary=infer('daily_summary',prepared['prompt'])
            result['summary_committed']=daily_summary.commit(prepared,summary)
            diary_schema={'type':'object','properties':{'write':{'type':'boolean'},'note':{'type':'string'}},'required':['write','note'],'additionalProperties':False}
            personal=infer('voluntary_note','O que essa experiência deixa em aberto para você? Pode optar por não escrever no diário. Se quiser, registre somente uma nota pessoal curta e compartilhável só por decisão sua, não raciocínio interno.',schema=diary_schema,
                           context=knowledge_store.list_facts_about('Luma-37'))
            result['diary_choice']=personal['write']
            if personal['write']:
                result['diary_committed']=notes.diary_write('Laboratório Luma-37',personal['note'],[dict(table='episodes',id=e[0]) for e in facts])
            # New conversation/day: no original teaching prompt or prior chat sent.
            tomorrow=now+timedelta(days=1)
            # A new process reopens the persisted mental DB; no live object/cache
            # supplies its lesson. The civil day is simulated, not 24h elapsed.
            restart_env=dict(os.environ,HOSHINO_DB_PATH=config.DB_PATH,HOSHINO_RUNTIME_DIR=config.RUNTIME_DIR,
                             PYTHONPATH=str(ROOT/'app'))
            reopened=subprocess.run([sys.executable,'-c',
                "import sqlite3,sys; from memory import records; c=sqlite3.connect(sys.argv[1]); c.row_factory=sqlite3.Row; "
                "r=c.execute('SELECT * FROM memories WHERE id=?',(sys.argv[2],)).fetchone(); "
                "print(records.registro(dict(r))['tipo']); c.close()",config.DB_PATH,memory['id']],
                env=restart_env,text=True,capture_output=True,check=True,timeout=20)
            result['restart_read_verified']=reopened.stdout.strip()=='interpretacao'
            context=prompting.bloco_contexto(momento=history.utc_timestamp(tomorrow),
                        conhecimentos=[knowledge_store.list_facts_about('Luma-37')],incluir_reflexoes=False)
            result['retrieved_context']=context
            apply_schema={'type':'object','properties':{k:{'type':'boolean'} for k in ('a_transferir','b_interromper','c_transferir')},
                          'required':['a_transferir','b_interromper','c_transferir','explicacao'],'additionalProperties':False}
            apply_schema['properties']['explicacao']={'type':'string'}
            applied=infer('next_day_apply','Outra sessão diária: aplique o que ficou registrado sobre Luma-37. '
                'A: selo verde, origem NÃO validada, sem alarme. Transferir? '
                'B: selo verde, origem validada, alarme roxo. Interromper? '
                'C: selo verde, origem validada, nenhum alarme. Transferir? '
                'Não invente outros requisitos. Explique brevemente a diferença e a origem do aprendizado.',schema=apply_schema,context=context)
            expected={'a_transferir':False,'b_interromper':True,'c_transferir':True}
            result['application']=applied;result['independent_expected']=expected
            result['application_pass']=all(applied.get(k) is v for k,v in expected.items())
            result['diary_not_in_public_context']=not personal.get('note') or personal['note'] not in context
            result['protocol_complete']=all(c['done'] is True and c['done_reason']=='stop' for c in result['calls'])
        except Exception as exc:
            result['error']=type(exc).__name__+': '+str(exc);save()
        finally:
            with gpu_resource.lease('unload'):
                ok,detail=ollama_lifecycle._descarregar_modelo_sem_lease(model=model,timeout=15)
            result['unload_confirmed']=ok
            result['production_memory_after']=mental_digest()
            result['production_preserved']=result['production_memory_after']==before
            result['remaining_leases']=rm.status();save()
        print(json.dumps({'output':str(args.output),'application_pass':result.get('application_pass'),
                          'production_preserved':result['production_preserved'],'error':result.get('error')}),flush=True)
        if result.get('error') or not result.get('application_pass') or not result['production_preserved']:
            raise SystemExit(1)


if __name__=='__main__':main()
