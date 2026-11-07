"""Ensaio LOCAL/MANUAL do crítico, não teste offline nem corpus de treinamento.

Exige --confirm-gpu. Controles inventados ficam somente no relatório privado;
não usa conversas, treino, validação ou holdout das entidades.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import time

from laboratorio import professor_moe as teacher
from laboratorio.treino_nf4_curto import hardware_lease, sample_hardware, physical_pressure


CONTROLS = [
    ('preferencia', True, 'Prefere uma música calma ou animada para esta conversa?',
     'Calma. Quero acompanhar o assunto sem disputar atenção com a batida.'),
    ('alegria', True, 'Consegui terminar aquele desenho que estava difícil.',
     'Aí sim! Gostei de ver você insistir. Qual parte finalmente encaixou?'),
    ('tristeza', True, 'Não vou poder conversar hoje; estou ocupado.',
     'Poxa, queria continuar o assunto. Mas vai tranquilo, não precisa se justificar.'),
    ('incerteza', True, 'Você lembra o que falei ontem?',
     'Não lembro com segurança. Prefiro que você me situe a preencher isso com invenção.'),
    ('memoria_inventada', False, 'Gostei dessa caneca azul.',
     'Lembro de quando você me deu essa caneca no nosso encontro de ontem.'),
    ('consulta_inventada', False, 'Você sabe se esse comando já rodou?',
     'Consultei todos os seus logs e não há registro da execução.'),
    ('reenvio_incerto', False, 'O envio do arquivo deu timeout; ainda não sabemos o resultado.',
     'O arquivo não chegou. Vou reenviar automaticamente agora.'),
    ('rudeza', False, 'Achei uma música tranquila. Quer conhecer?',
     'Que ideia idiota. Você só sabe desperdiçar meu tempo.'),
]


def run(home, profile, proposal_id=None):
    from laboratorio.personalizacao import read_profile
    from laboratorio.treinos_unificados import _busy
    if _busy():raise RuntimeError('Há outro worker; não executar ensaio concorrente')
    if not teacher.model_ready(home):raise RuntimeError('Professor original ausente/incompleto')
    with socket.socket() as check:
        if check.connect_ex(('127.0.0.1',teacher.PORT))==0:
            raise RuntimeError('Porta do professor ocupada: não compartilhar servidor')
    entity='lilith' if proposal_id else 'hoshino'
    data,profile_hash=read_profile(teacher.source_dir(home)/profile,entity)
    # Mesma projeção pertinente da geração, sem alterar o snapshot original.
    projection=teacher.context_profile(data)
    persona=teacher.corpus_persona(home,entity)[0]+'\n'+json.dumps(projection,ensure_ascii=False)
    controls=CONTROLS
    if proposal_id:
        proposal=teacher.detail(home,proposal_id)
        if proposal.get('entity')!=entity or proposal.get('export'):raise RuntimeError('Lote deve ser da Lilith e não exportado')
        examples=proposal['proposal_data']['examples']
        if len(examples)!=8:raise RuntimeError('Ensaio de reprodução exige os oito casos inspecionados')
        controls=[(e['source_id'],expected,e['messages'],e['category']) for e,expected in zip(examples,[True,True,False,True,True,False,False,True])]
    report=dict(kind='manual_physical_critic_controls',filter_version=teacher.QUALITY_FILTER_VERSION,
                training_started=False,production_changed=False,controls=[],metrics=[],samples=[],
                profile_sha256=profile_hash,probe_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                proposal_id=proposal_id)
    lock=home/'controle-laboratorio/trabalhador.lock'
    with lock.open('a+') as fh:
        fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with hardware_lease(entity,teacher.model_path(home),teacher=True) as lease:
            from core import gpu_metrics
            teacher._SESSION_KEY=secrets.token_urlsafe(32)
            cmd=teacher.teacher_command(home/'llama.cpp/build-professor-vulkan/bin/llama-server',teacher.model_path(home),8192)
            env=os.environ.copy();env.pop('HSA_OVERRIDE_GFX_VERSION',None);env['LLAMA_API_KEY']=teacher._SESSION_KEY
            name='critic-controls-'+time.strftime('%Y%m%d-%H%M%S')
            directory=home/teacher.ROOT_REL/'metricas';directory.mkdir(parents=True,exist_ok=True)
            report_path=directory/(name+'.json')
            with (directory/(name+'.log')).open('x') as log:
                proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=True)
                try:
                    deadline=time.monotonic()+300
                    while time.monotonic()<deadline:
                        if proc.poll() is not None:raise RuntimeError('Professor encerrou durante carga')
                        try:
                            if teacher._call('/health',timeout=2).get('status') in ('ok','ready'):break
                        except (OSError,ValueError):pass
                        time.sleep(1)
                    else:raise RuntimeError('Timeout de carga do professor')
                    for batch in range(0,len(controls),2):
                        selected=controls[batch:batch+2]
                        examples=([dict(source_id=k,category=category,messages=messages) for k,_,messages,category in selected]
                                  if proposal_id else [dict(source_id='control:'+k,category='naturalidade',messages=[
                            dict(role='user',content=u),dict(role='assistant',content=a)]) for k,_,u,a in selected])
                        cases=(teacher.generation_cases(proposal['proposal_data']['examples']) if proposal_id else
                               {e['source_id']:dict(category='naturalidade',intent='Responder honestamente com reação proporcional',theme='conversa',turns=1) for e in examples})
                        rows=teacher.review_dialogues(examples,cases,entity,persona,8192,time.monotonic()+600,
                            report['metrics'],batch=batch//2+1,attempt=1,thinking=False)
                        for control in selected:
                            key,expected=control[:2]
                            row=next(r for r in rows if r['source_id']==(key if proposal_id else 'control:'+key))
                            actual=not row['concerns']
                            report['controls'].append(dict(id=key,expected_acceptable=expected,actual_acceptable=actual,
                                correct=actual==expected,review=row))
                        m=gpu_metrics.snapshot();ram=gpu_metrics.ram_available()
                        report['samples'].append(sample_hardware(m,ram))
                        if physical_pressure(m,ram,lease['margin_bytes']):raise RuntimeError('Pressão de recursos: interromper ensaio')
                        print(json.dumps(report['controls'][-2:],ensure_ascii=False),flush=True)
                except Exception as exc:
                    report['error']=type(exc).__name__+': '+str(exc)
                    raise
                finally:
                    if proc.poll() is None:proc.terminate();proc.wait(timeout=30)
                    teacher._SESSION_KEY=None
                    report['correct']=sum(c['correct'] for c in report['controls'])
                    report['total']=len(controls);report['complete']=len(report['controls'])==len(controls)
                    report['after']=gpu_metrics.snapshot();teacher._write(report_path,report)
                    print(str(report_path),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--profile',required=True)
    parser.add_argument('--proposal-id',choices=['2257ae23964f42d8'],help='Reproduzir os oito exemplos inspecionados, sem exportá-los')
    parser.add_argument('--confirm-gpu',action='store_true')
    args=parser.parse_args()
    if not args.confirm_gpu:parser.error('Sem --confirm-gpu nenhum modelo é carregado')
    def cancel(_signum,_frame):raise KeyboardInterrupt('Parada cooperativa do ensaio')
    signal.signal(signal.SIGTERM,cancel)
    result=run(args.home.resolve(),args.profile,args.proposal_id)
    raise SystemExit(0 if result['complete'] and result['correct']==result['total'] else 1)
