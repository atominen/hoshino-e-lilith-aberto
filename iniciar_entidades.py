#!/usr/bin/env python3
"""Central local: seleção, caixa postal e supervisão, sem dependências extras."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import webbrowser
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from entity_paths import carregar_entidade
from core import interentity, resource_manager, job_bus, world_state, capability_router, shutdown, diagnostics, entity_admission
from core import central_rede, pc2_remoto
# 11/11 (pedido humano): ponte de áudio PC1 ↔ PC2 pela própria Central, sem SonoBus nem outro app externo.
from ui import native_ponte
PONTE_AUDIO = native_ponte.Servidor()
import atexit
atexit.register(PONTE_AUDIO.encerrar)
from core.audio_service import AudioService, MAX_INPUT_BYTES
from core.central_control import Control, redact
ENTIDADES = interentity.ENTITIES


def validar_entidade(nome):
    if nome not in ENTIDADES:
        raise ValueError("Escolha Hoshino, Lilith ou Alistair.")
    carregar_entidade(ROOT, nome)
    return nome


class Supervisor:
    def __init__(self,laboratory_home=None):
        self.processes = {}
        self.failures = {}
        self.next_attempt = {}
        self.lock = threading.RLock()
        self.closing = False
        self.process_stamps = {}
        self.shutdown_result = None
        self.shutdown_origin = dict(requester='sistema', reason='Encerramento cooperativo da Central; solicitante não registrado.', source='central')
        self.sleep_watch = {}
        self.audio = None
        self.project = ROOT
        self.night_poweroff_requested = False
        self.night_readiness = {'state':'disabled'}
        self.laboratory_home = Path(laboratory_home or os.environ.get('HOSHINO_LAB_HOME') or ROOT/'laboratorio-local').resolve()
        self.night = None
        self.laboratory_maintenance = False
        self.model_recoveries = {}
        self.wake_origins = {}
        # Não repetir treino depois de crash nem restaurar entidades enquanto um
        # executor órfão ainda pode usar GPU. Recuperação exige confirmação local.
        if self.laboratory_home.is_dir():
            from laboratorio.treinos_unificados import night_status,NIGHT_ACTIVE,night_save
            prior=night_status(self.laboratory_home)
            if prior.get('state') in NIGHT_ACTIVE:
                prior.update(state='recovery_required',error='Supervisor reiniciou: confirmar recuperação; sem replay de treino')
                self.night=prior;self.laboratory_maintenance=True;night_save(self.laboratory_home,prior)

    def start(self, entity, *, requester='usuario', reason='Despertar solicitado no lançador local.',
              source='local', reference=''):
        entity = validar_entidade(entity)
        from core import wake_context
        wake_origin = wake_context.origin(requester, reason, source, reference)
        with self.lock, entity_admission.guard(self.project, entity, processes=self.processes):
            if self.closing:
                raise ValueError("Central encerrando; aguarde a drenagem.")
            if self.laboratory_maintenance:
                raise ValueError('Laboratório noturno em manutenção autorizada; acordar bloqueado até restaurar')
            if entity in self.model_recoveries:
                return {'entity':entity,'status':'starting','detail':'Recuperação de modelos locais em andamento',
                        'recovery':self.model_recoveries[entity]}
            proc = self.processes.get(entity)
            current = interentity.presence(entity) or {}
            if (proc and proc.poll() is None) or current.get("status") in {"awake", "starting", "stopping"}:
                return {"entity": entity, "status": current.get("status", "starting")}
            lock_path = ROOT / "entidades" / entity / "runtime/entity.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+") as process_lock:
                try:
                    fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {"entity": entity, "status": "busy", "detail": "processo existente ainda mantém a instância"}
                fcntl.flock(process_lock, fcntl.LOCK_UN)
            # Somente o pedido explícito de wake dispara recuperação; abrir a
            # Central/consultar dashboard nunca converte ou acorda ninguém.
            from laboratorio.recuperacao_modelos import ensure
            from core import alistair_execution
            remote_alistair = entity=='alistair' and alistair_execution.is_remote(ROOT)
            recovery={'state':'ready'} if remote_alistair else ensure(self.laboratory_home,ROOT,entity)
            if recovery['state']=='blocked':raise ValueError(recovery['detail'])
            if recovery['state']=='recovering':
                self.model_recoveries[entity]=recovery['id']
                self.wake_origins[entity]=wake_origin
                interentity.clear_sleep(entity)
                interentity.register(entity,'starting',recovery.get('pid'),os.getpid(),'recuperando executor local; inferência ainda não iniciada')
                return {'entity':entity,'status':'starting','detail':'Preparando executor ausente a partir de pesos locais',
                        'recovery':recovery['id']}
            # Não propagar a configuração carregada para outra identidade.
            env = {k: v for k, v in os.environ.items() if not k.startswith(("HOSHINO_", "OLLAMA_"))}
            env.update(HOSHINO_ENTIDADE=entity, HOSHINO_HEADLESS="1", HOSHINO_LAUNCHER_PID=str(os.getpid()))
            env['HOSHINO_CENTRAL_LISTENING']='1'
            env['HOSHINO_WAKE_CONTEXT'] = json.dumps(wake_origin, ensure_ascii=False)
            # Seletor independente: não altera .env nem identidade; recusa alias neural incompleto.
            from core import neural9b_modes
            neural_alias = neural9b_modes.startup_override(ROOT, entity)
            if neural_alias:
                env['HOSHINO_NEURAL9B_MODEL'] = neural_alias
            interentity.clear_sleep(entity)
            log_dir = ROOT / "compartilhado/runtime/launcher"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / f"{entity}.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(["bash", str(ROOT / "iniciar_hoshino.sh")], cwd=ROOT,
                                        env=env, stdin=subprocess.DEVNULL, stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=True)
            self.processes[entity] = proc
            self.process_stamps[entity] = job_bus._process_stamp(proc.pid)
            interentity.register(entity, "starting", proc.pid, os.getpid(), "inicialização solicitada")
            self.failures.pop(entity, None)
            return {"entity": entity, "status": "starting", "pid": proc.pid}

    def _start_automatic(self, entity, **origin):
        """Recusa de capacidade não encerra a vigia nem consome pedido pendente."""
        try:
            return self.start(entity, **origin)
        except ValueError as exc:
            self.failures[entity] = str(exc)
            self.next_attempt[entity] = time.monotonic() + 60
            return {'entity':entity, 'status':'blocked', 'detail':str(exc)}

    def tick(self):
        with self.lock:
            from laboratorio import treinos_unificados as recovery_lab
            for entity,jid in list(self.model_recoveries.items()):
                item=recovery_lab.details(self.laboratory_home,jid)
                if item['state']=='completed' and recovery_lab._owned_alive(item,jid):
                    interentity.heartbeat(entity,'starting','worker finalizando recuperação/liberando locks')
                    continue
                if item['state'] in ('started','running','cancel_requested'):
                    if (self.closing or interentity.sleep_requested(entity)) and item['state'] in ('started','running'):
                        recovery_lab.stop(self.laboratory_home,jid,'PARAR_TREINO_UNIFICADO')
                    interentity.heartbeat(entity,'starting','recuperando executor local; não é entidade acordada')
                    continue
                del self.model_recoveries[entity]
                interentity.register(entity,'sleeping' if interentity.sleep_requested(entity) else 'offline',detail='recuperação '+item['state'])
                if item['state']=='completed' and not self.closing and not interentity.sleep_requested(entity):
                    # Pode haver um leve também ausente: mesmo worker serial,
                    # só inicia a entidade quando todos os selecionados existirem.
                    try:self.start(entity, **self.wake_origins.pop(entity, {}))
                    except Exception as exc:self.failures[entity]=str(exc)
                else:self.failures[entity]='Recuperação não confirmada: '+str(item.get('error',item['state']))
            for entity, proc in list(self.processes.items()):
                code = proc.poll()
                if code is None:
                    if interentity.sleep_requested(entity):
                        watch = self.sleep_watch.setdefault(entity, {'start': time.monotonic(), 'warned': False, 'blocked': False})
                        if self.audio is not None and not watch.get('speech_cancelled'):
                            try:
                                self.audio.interrupt_entity(entity)
                                watch['speech_cancelled'] = True
                            except Exception as exc:
                                diagnostics.emit('shutdown.speech_cancel_failed', level='ERROR', entity=entity,
                                                 error_type=type(exc).__name__)
                        elapsed = time.monotonic() - watch['start']
                        if elapsed >= 10 and not watch['warned']:
                            watch['warned'] = True
                            diagnostics.emit('shutdown.entity_slow', level='WARN', entity=entity, pid=proc.pid, elapsed=elapsed)
                        if elapsed >= 45 and not watch['blocked']:
                            watch['blocked'] = True
                            self.failures[entity] = 'Sono excedeu 45s; processo mantido para proteger efeitos incertos. Consulte jobs/recursos e diagnóstico.'
                            diagnostics.emit('shutdown.entity_blocked', level='ERROR', entity=entity, pid=proc.pid,
                                             jobs=[j for j in job_bus.status(active_only=True) if j['entity']==entity],
                                             resources=[r for r in resource_manager.status() if r['entity']==entity], auto_retry=False)
                    else:
                        self.sleep_watch.pop(entity, None)
                    continue
                sleeping = code == 0 and interentity.sleep_requested(entity)
                detail = "encerrada após concluir trabalhos" if sleeping else f"processo encerrou: código {code}"
                recorded = (interentity.presence(entity) or {}).get('detail', '')
                detail += '; ' + recorded if 'unload=' in recorded else '; unload=unconfirmed'
                interentity.register(entity, "sleeping" if sleeping else "offline", detail=detail)
                if code != 0:
                    self.failures[entity] = detail + "; consulte o log do iniciador"
                self.next_attempt[entity] = time.monotonic() + 60
                del self.processes[entity]
                self.sleep_watch.pop(entity, None)
            if self.night and self.night.get('automatic_cycle') and self.night.get('state') in ('draining','running'):
                from laboratorio.rotina_noturna import agenda
                try:
                    observed=world_state.fresh_values(world_state.snapshot())
                    idle=observed.get('desktop.idle_seconds')
                    if idle is None or idle<60:
                        self.night.update(state='stopping',error='Usuário retornou/sonda indisponível: checkpoint cooperativo')
                    due=[t for t in agenda(self.project) if t['due_now']]
                    if due:
                        self.night.update(state='stopping',error='Agenda exige entidade acordada',scheduled_tasks=due)
                        self.night['restore_entities']=sorted(set(self.night['restore_entities'])|{t['entity'] for t in due})
                except Exception as exc:
                    self.night.update(state='stopping',error='Agenda não verificável: '+type(exc).__name__)
            self.night_tick()
            from laboratorio.sessao_personalizada import tick as scheduled_once_tick
            try:scheduled_once_tick(self)
            except Exception as exc:
                self.night_readiness={'state':'blocked','reason':'Sessão única: '+type(exc).__name__}
            from laboratorio.rotina_noturna import auto_tick
            try:auto_tick(self)
            except Exception as exc:
                self.night_readiness={'state':'error','reason':type(exc).__name__}
            if self.closing or self.laboratory_maintenance:
                return
            if any(j["kind"] == "image" for j in job_bus.status(active_only=True)) and not interentity.sleep_requested("alistair"):
                if time.monotonic() >= self.next_attempt.get("alistair", 0):
                    self._start_automatic('alistair', requester='sistema', reason='Acompanhamento de trabalho de imagem na fila existente.',
                               source='trabalho')
            for request in interentity.pending_wake_requests():
                entity = request["target"]
                if entity not in ENTIDADES:
                    continue
                state = (interentity.presence(entity) or {}).get("status")
                if state == "awake" and not interentity.sleep_requested(entity):
                    interentity.consume_wake(request["id"])
                elif state not in {"awake", "starting", "stopping"}:
                    if interentity.sleep_requested(entity) and request["created_at"] <= interentity.sleep_time(entity):
                        continue
                    if time.monotonic() >= self.next_attempt.get(entity, 0):
                        self._start_automatic(entity, requester=request['requester'], reason=request['reason'],
                                   source='pedido', reference=request['id'])

    def authorize_night(self,data):
        from laboratorio.treinos_unificados import night_create,night_save
        with self.lock:
            if self.closing or self.laboratory_maintenance:raise ValueError('Supervisor ocupado/encerrando')
            awake=[e for e in ENTIDADES if (interentity.presence(e) or {}).get('status') in ('awake','starting')]
            self.night=night_create(self.laboratory_home,ROOT,data,awake)
            self.laboratory_maintenance=True
            for e in awake:interentity.request_sleep(e, requester='sistema',
                reason='Pausa para a sessão de laboratório autorizada.', source='laboratorio')
            night_save(self.laboratory_home,self.night)
            diagnostics.emit('laboratory.night_authorized',night_id=self.night['id'],restore=awake)
            return self.night

    def cancel_night(self,data):
        from laboratorio.treinos_unificados import night_save
        if data.get('confirm') is not True or not self.night:raise ValueError('Confirme a parada/recuperação da sessão')
        with self.lock:
            self.night_poweroff_requested=False
            self.night.update(state='stopping',cancel_requested=True)
            night_save(self.laboratory_home,self.night)
            return self.night

    def night_tick(self):
        from laboratorio import treinos_unificados as lab
        obj=self.night
        if not obj or obj['state'] not in lab.NIGHT_ACTIVE or obj['state']=='recovery_required':return
        before=json.dumps(obj,sort_keys=True)
        home=self.laboratory_home;now=time.time()
        if now>=obj['deadline'] and obj['state'] in ('draining','running'):
            obj.update(state='stopping',error='Janela autorizada terminou; pedir checkpoint e restaurar')
        try:
            from laboratorio import professor_moe as teacher
            if obj['state']=='draining':
                active=any((interentity.presence(e) or {}).get('status') in ('awake','starting','stopping') for e in ENTIDADES)
                if active or job_bus.status(active_only=True) or resource_manager.status():
                    if now>=obj['drain_deadline']:
                        obj.update(state='stopping',error='Drenagem excedeu prazo; nenhum treino iniciado')
                else:obj['state']='running'
            if obj['state']=='running' and obj['index']<len(obj['tasks']) and obj['tasks'][obj['index']]['action']=='learn':
                from laboratorio.rotina_noturna import learn_tick
                task=obj['tasks'][obj['index']]
                learn_tick(self,task,now)
                if obj['index']>=len(obj['tasks']):obj['state']='restoring'
                if json.dumps(obj,sort_keys=True)!=before:
                    lab.night_save(home,obj)
                    step=obj.get('learning',{}).get(task['entity'],{})
                    diagnostics.emit('laboratory.learning_transition',night_id=obj['id'],entity=task['entity'],
                                     phase=step.get('phase'),attempt=step.get('attempt'),job=obj.get('job'),
                                     worker_kind=obj.get('job_kind'))
                return
            if obj['state']=='running':
                jid=obj.get('job')
                if jid:
                    is_teacher=obj.get('job_kind')=='teacher'
                    record=teacher.detail(home,jid) if is_teacher else lab.details(home,jid)
                    if record['state'] in (('proposed',) if is_teacher else ('completed',)):
                        obj['history'].append({'id':jid,'state':record['state'],'artifact':record.get('artifact'),
                                               'result_summary':record.get('result_summary')})
                        obj['index']+=1;obj['job']=None
                    elif record['state'] not in ('started','running','cancel_requested'):
                        obj.update(state='stopping',error='Job não concluído: '+record['state'])
                if obj['state']=='running' and not obj.get('job'):
                    if obj['index']>=len(obj['tasks']):obj['state']='restoring'
                    else:
                        task=obj['tasks'][obj['index']]
                        if task['action']=='curate':
                            result=teacher.start(home,task['id'],confirm=True);obj['job_kind']='teacher'
                        else:
                            task=lab.resolve_night_task(home,obj,task)
                            result=lab.start(home,ROOT,task['model'],task['entity'],task['minutes'],task['action'],
                                         'EXECUTAR_TREINO_UNIFICADO',task.get('checkpoint'),task.get('candidate'),task.get('dataset'),task.get('options'))
                            obj['job_kind']='training'
                        obj['job']=result['id']
            if obj['state']=='stopping':
                if obj.get('job'):
                    is_teacher=obj.get('job_kind')=='teacher'
                    job=teacher.detail(home,obj['job']) if is_teacher else lab.details(home,obj['job'])
                    if job['state'] in ('started','running'):
                        if is_teacher:teacher.stop(home,obj['job'])
                        else:lab.stop(home,obj['job'],'PARAR_TREINO_UNIFICADO')
                    elif job['state']!='cancel_requested':
                        obj['stopped_job']=obj['job'];obj['job']=None
                if not obj.get('job') and not lab._busy():obj['state']='restoring'
            if obj['state']=='restoring':
                if lab._busy() or resource_manager.status():return
                # Só processos originalmente acordados; não acordar as outras.
                if any((interentity.presence(e) or {}).get('status') in ('starting','stopping') for e in ENTIDADES):return
                if obj.get('automatic_cycle') and not obj.get('cancel_requested') and not obj.get('error'):
                    from laboratorio.rotina_noturna import finish
                    if finish(self,now):
                        obj.update(state='completed_with_errors' if obj.get('failures') else 'completed',restored=[])
                        lab.night_save(home,obj);return
                self.laboratory_maintenance=False
                restored=[r for r in obj.get('restored',[]) if r['status'] in {'starting','awake'}]
                pending=[]
                remaining=obj.get('restore_pending',obj['restore_entities'])
                for e in ([] if self.closing else remaining):
                    attempted=time.monotonic()>=self.next_attempt.get(e,0)
                    if not attempted:
                        result={'status':'blocked'}
                    else:
                        result=self._start_automatic(e, requester='sistema', reason='Restauração após a sessão de laboratório autorizada.',
                                          source='laboratorio', reference=obj['id'])
                    restored.append({'entity':e,'status':result['status']})
                    if result['status'] not in {'starting','awake'}:
                        pending.append(e)
                        if attempted:self.next_attempt[e]=max(self.next_attempt.get(e,0),time.monotonic()+60)
                obj.update(state='restoring' if pending else 'completed_with_errors' if obj.get('error') or obj.get('failures') else 'completed',
                           restored=restored,restore_pending=pending,restoration_health_pending=bool(restored))
                if not pending:obj['finished']=now
                diagnostics.emit('laboratory.night_restored',night_id=obj['id'],restored=restored)
        except Exception as exc:
            obj.update(state='stopping',error=type(exc).__name__+': '+str(exc))
            diagnostics.exception('laboratory.night_failed',exc,night_id=obj['id'])
        if json.dumps(obj,sort_keys=True)!=before:lab.night_save(home,obj)

    def chat_streams(self, entity, session_id, chat_scope):
        from core import text_stream
        return text_stream.snapshot(entity, session_id, chat_scope)

    def state(self, entity="hoshino", *, daily=False, session_id='', day='', query='', before=0, upper=None, chat_scope='all'):
        validar_entidade(entity)
        conversation = (interentity.daily_conversation(entity, session_id=session_id, day=day, query=query,
                                                       before=before, upper=upper, scope=chat_scope) if daily else
                        {'conversation':interentity.user_conversation(entity, 100)})
        for message in conversation['conversation']:
            meta = interentity._metadata(message)
            if (message['sender'] in interentity.ENTITIES and message['recipient'] == 'usuario' and
                    message['kind'] not in ('deleted', 'diary') and not meta.get('private') and meta.get('kind') != 'diary'):
                review = meta.get('human_feedback') or {}
                message['feedback_target'] = dict(text_sha256=hashlib.sha256(message['text'].encode('utf8')).hexdigest(),
                    expected_revision=review.get('revision') if isinstance(review, dict) else None)
        from core import chat_identity
        labels={name:chat_identity.display_name(self.project/'entidades'/name/'memory/sqlite'/(name+'.db')) for name in interentity.ENTITIES}
        return {"human_display_names":labels, "presence": interentity.presence()["entities"], "resources": resource_manager.status(),
                "failures": dict(self.failures), **conversation,
                "private": interentity.private_history(100),
                "jobs": job_bus.status(), "standby_by": "alistair",
                "wake_requests": interentity.pending_wake_requests(),
                "world": world_state.snapshot(), "routing": capability_router.Router().status(entity),
                "shutdown": self.shutdown_result, "closing": self.closing, "gpu":resource_manager.gpu_state(),
                "model_recoveries":dict(self.model_recoveries)}

    def shutdown(self, audio=None, monitor=None, policy=None, ui=None):
        from laboratorio import treinos_unificados as recovery_lab
        self.closing = True
        # Serviços legados podem prender o close. O prazo global inclui esses
        # closes: threads daemon não autorizam matar workers ou sair escondido.
        cleanups = []
        errors = []
        def request_initial_sleep():
            try:
                for entity in self.processes:
                    interentity.request_sleep(entity, **self.shutdown_origin)
            except Exception as exc:
                errors.append('pedido de sono: ' + str(exc))
                diagnostics.exception('shutdown.sleep_request_failed', exc)
        request = threading.Thread(target=request_initial_sleep, daemon=True, name='closing-sleep-request')
        request.start()
        cleanups.append(request)
        def cleanup(name, service):
            try:
                if service.close() is False:
                    errors.append(name + ': encerramento não confirmado')
            except Exception as exc:
                errors.append(name + ': ' + str(exc))
                diagnostics.exception('shutdown.cleanup_failed', exc, service=name)
        for name, service in (('audio', audio), ('world_monitor', monitor), ('overlay',ui)):
            if service is not None:
                thread = threading.Thread(target=cleanup, args=(name, service), daemon=True, name='closing-' + name)
                thread.start()
                cleanups.append(thread)
        def snapshot():
            processes = [{'entity': e, 'pid': p.pid, 'owned_stamp': self.process_stamps.get(e)}
                         for e, p in self.processes.items() if p.poll() is None]
            try:
                jobs = job_bus.status(active_only=True, limit=200)
                resources = resource_manager.status()
                diagnostic_error = ''
            except Exception as exc:
                jobs, resources, diagnostic_error = [], [], str(exc)
            threads = [t.name for t in cleanups if t.is_alive()]
            terminal_jobs = []
            for entity in self.processes:
                for path in (ROOT / 'entidades' / entity / 'runtime/jobs').glob('job-*.json'):
                    try:
                        meta = json.loads(path.read_text())
                        if meta.get('status') == 'rodando' and (not meta.get('process_stamp') or
                                job_bus._process_stamp(meta.get('pid')) == meta['process_stamp']):
                            terminal_jobs.append({'entity': entity, 'path': str(path), 'pid': meta.get('pid'),
                                                  'outcome': 'uncertain', 'auto_retry': False})
                    except (OSError, ValueError, TypeError) as exc:
                        diagnostic_error = 'Job de terminal ilegível: ' + str(exc)
            lab_pending=bool(self.night and self.night.get('state') in {'draining','running','stopping','restoring','recovery_required'})
            recoveries=[{'entity':entity,'id':jid} for entity,jid in self.model_recoveries.items()
                        if recovery_lab.details(self.laboratory_home,jid)['state'] in ('started','running','cancel_requested')]
            return dict(pending=bool(processes or jobs or terminal_jobs or resources or threads or errors or diagnostic_error or lab_pending or recoveries),
                        processes=processes, jobs=jobs, resources=resources, cleanups=threads,
                        model_recoveries=recoveries,
                        laboratory_night=self.night if lab_pending else None,
                        terminal_jobs=terminal_jobs, errors=list(errors), diagnostic_error=diagnostic_error)
        def cooperate(state):
            if state.get('laboratory_night'):self.cancel_night({'confirm':True})
            for recovery in state.get('model_recoveries',[]):
                recovery_lab.stop(self.laboratory_home,recovery['id'],'PARAR_TREINO_UNIFICADO')
            for p in state['processes']:
                interentity.request_sleep(p['entity'], **self.shutdown_origin)
            if audio is not None:
                for job in state['jobs']:
                    if job['kind'] in {'audio_asr', 'audio_tts'}:
                        try:
                            audio.cancel(job['id'])
                        except ValueError:
                            pass  # cancel só aceita IDs possuídos por esta central
        # Não existe prova de que um thread arbitrário é seguro para SIGKILL.
        # Logo, não forçamos entidades bloqueadas: explicitamente recusamos sair.
        self.shutdown_result = shutdown.drain(snapshot, cooperate, lambda _: False, policy)
        if self.shutdown_result['status'] == 'complete':
            self.tick()
        return self.shutdown_result


# 07/11 (pedido humano): com a Central aberta no PC1 e o painel no PC2, só a última janela que recebeu foco comanda.
# Ficam livres o que é segurança (dormir, interromper, cancelar, encerrar) e os sentidos (cópias, tela, foco, PC2).
SO_JANELA_ATIVA = frozenset({
    '/api/send', '/api/start', '/api/audio/transcribe', '/api/audio/test', '/api/audio/listening',
    '/api/control/microphone', '/api/control/interface', '/api/control/audio', '/api/control/tools',
    '/api/control/models', '/api/control/model-versions', '/api/control/model-versions/prepare', '/api/control/vram',
    '/api/control/apis',
    '/api/control/rede', '/api/control/password', '/api/control/memory/delete', '/api/control/knowledge',
    '/api/control/knowledge/unlock', '/api/control/logic', '/api/control/chat/feedback', '/api/control/attachment',
    '/api/control/import', '/api/control/import/finish', '/api/control/export', '/api/control/overlay/start',
    '/api/control/alistair/execution', '/api/control/neural', '/api/control/native/open',
    '/api/control/laboratory/night/start', '/api/control/laboratory/night/schedule-once',
    '/api/control/laboratory/night/config'})


def audio_origin(audio, entity, data):
    """Origem registrada só após o usuário revisar e enviar a transcrição."""
    ids=data.get('audio_job_ids');extra={}
    if ids is not None:
        if (not isinstance(ids,list) or not 1<=len(ids)<=64 or any(not isinstance(i,str) or not i for i in ids) or
                (data.get('audio_job_id') and data['audio_job_id']!=ids[-1])):raise ValueError('IDs de transcrição inválidos.')
        jobs=[audio.get(i) for i in ids];job=jobs[-1]
    elif data.get('audio_job_id'):
        job=audio.get(data['audio_job_id']);jobs=[job]
    else:
        return {}
    if data.get("draft_origin") is not True or job["kind"] != "audio_asr" or job["status"] != "done" or job["entity"] != entity:
        raise ValueError("Transcrição não corresponde ao rascunho desta entidade.")
    result = job["result"] or {}
    capture_mode=job.get('capture_mode',job.get('details',{}).get('capture_mode','command'))
    if ids is not None or job.get('utterance'):
        from core.asr_provenance import compose
        result,capture_mode,utterance_id=compose(jobs,entity,data.get('conversation_session_id'),data.get('chat_scope','direct'))
        extra=dict(audio_job_ids=[j['id'] for j in jobs],utterance_id=utterance_id)
    if capture_mode=='detection':
        from core import ui_policy
        if not ui_policy.capability_allowed(audio.root,entity,'ambient'):
            raise ValueError('Ouvir o ambiente está desativado para esta entidade; transcrição não enviada.')
    words = lambda text: re.findall(r"\w+", str(text or "").casefold())
    original, edited = words(result.get("text")), words(data.get("text"))
    matches = sum(word in set(edited) for word in original)
    if not original or matches < (len(original) if len(original) < 4 else (len(original) + 1) // 2):
        raise ValueError("Texto não corresponde à transcrição; envie como texto digitado.")
    from core import speech_perception
    return {"audio_job_id": job["id"], "speech_perception":speech_perception.evidence(result),
            "capture_mode":capture_mode, "source": result.get("source", "browser_microphone"),
            "speaker": result.get("speaker", "usuario"), "speaker_basis": result.get("speaker_basis", "source_role"),
            "speaker_identification_performed": False, "draft_reviewed": not bool(data.get('automatic_asr')),
            "transcript_edited": original != edited,**extra}


def rede_state(handler):
    """Painel do PC2 (06/11): configuração, endereços e código. Só a janela local vê o código."""
    if getattr(handler.server, 'lan', False):
        raise PermissionError('O acesso pela rede só é configurado na Central do PC1.')
    cfg = central_rede.settings(ROOT)
    lan = getattr(handler.server, 'lan_server', None)
    return dict(cfg, addresses=central_rede.addresses(), active=lan is not None,
                active_port=lan.server_port if lan is not None else None,
                code=central_rede.token(ROOT) if cfg['enabled'] else None,
                apply='immediate', ponte_audio=PONTE_AUDIO.estado())


def rede_save(handler, data):
    if getattr(handler.server, 'lan', False):
        raise PermissionError('O acesso pela rede só é configurado na Central do PC1.')
    if set(data) - {'enabled', 'allowed', 'regenerate'}:
        raise ValueError('Campo inválido.')
    saved = central_rede.save(ROOT, enabled=data.get('enabled'), allowed=data.get('allowed'),
                              regenerate=data.get('regenerate') is True)
    diagnostics.emit('central.lan_saved', enabled=saved['enabled'], allowed=saved['allowed'],
                     regenerated=data.get('regenerate') is True)
    apply_lan(handler.server)
    return dict(rede_state(handler), saved=True)


def apply_lan(local_server):
    """Aplica na hora (06/11): salvar fecha a porta antiga e, se ligado, abre outra com o código e as redes atuais.
    Antes só valia ao reabrir a Central, e quem salvou logo depois de abrir ficou sem porta."""
    running = getattr(local_server, 'lan_server', None)
    if running is not None:
        running.shutdown()
        running.server_close()
        local_server.lan_server = None
    if not central_rede.settings(ROOT)['enabled']:
        return None
    try:
        lan = make_lan_server(local_server)
    except (OSError, ValueError) as exc:
        diagnostics.emit('central.lan_unavailable', level='WARNING', error=type(exc).__name__, detail=str(exc)[:200])
        return None
    local_server.lan_server = lan
    threading.Thread(target=lan.serve_forever, daemon=True).start()
    return lan


def pc2_route(handler, path, data):
    """Painel do PC2 (06/11): pede comandos, devolve resultados e manda os sentidos de lá.
    Só a porta da rede aceita: o painel do PC1 nunca se passa pelo PC2."""
    if not getattr(handler.server, 'lan', False):
        raise PermissionError('Só o painel do PC2, pela rede, usa esta rota.')
    if path == '/api/control/pc2/proximo':
        if set(data) - {'permitido', 'permitido_tela'}:
            raise ValueError('Campo inválido.')
        return dict(comando=pc2_remoto.proximo(ROOT, permitido=data.get('permitido') is True,
                                               permitido_tela=data.get('permitido_tela') is True))
    if path == '/api/control/pc2/resultado':
        if set(data) - {'id', 'codigo', 'saida', 'erro'}:
            raise ValueError('Campo inválido.')
        return pc2_remoto.concluir(ROOT, data.get('id'), data.get('codigo'), data.get('saida'), data.get('erro'))
    if set(data) - {'estado'}:
        raise ValueError('Campo inválido.')
    return pc2_remoto.guardar_sentidos(data.get('estado'))


def make_lan_server(local_server, settings=None, token=None):
    """Segunda porta (0.0.0.0) para o painel do PC2: mesmo backend, mesma Central, outra credencial.

    Aceita só IP de rede privada permitida, Host igual ao endereço local da conexão e o código de pareamento."""
    settings = settings or central_rede.settings(ROOT)
    token = token or central_rede.token(ROOT)
    allowed = settings['allowed']
    central_rede.networks(allowed)

    class LanHandler(local_server.RequestHandlerClass):
        def authorized(self):
            local = self.connection.getsockname()[0]
            host = f"{local}:{self.server.server_port}"
            return (central_rede.client_allowed(self.client_address[0], allowed)
                    and self.headers.get("Host") == host
                    and self.headers.get("Origin", "http://" + host) == "http://" + host
                    and secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token))

    server = ThreadingHTTPServer((settings.get('bind', '0.0.0.0'), settings['port']), LanHandler)
    server.lan = True
    server.audio = local_server.audio
    server.control = local_server.control
    server.world_monitor = None
    server.daemon_threads = True
    server.request_shutdown = lambda: local_server.request_shutdown() if local_server.request_shutdown else None
    local_server.lan_server = server
    return server


def make_server(supervisor, port=8769, audio=None):
    token = secrets.token_urlsafe(32)
    audio = audio or AudioService(ROOT)
    control = Control(ROOT, supervisor, audio)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, *args):
            pass

        def reply(self, status, data, html=False, image=False, sound=False, mime=None):
            body = data if html or image or sound or mime else json.dumps(redact(data), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime or ("audio/wav" if sound else "image/png" if image else "text/html; charset=utf-8" if html else "application/json; charset=utf-8"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            host = f"127.0.0.1:{self.server.server_port}"
            return (self.headers.get("Host") == host
                    and self.headers.get("Origin", "http://" + host) == "http://" + host
                    and secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token))

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/":
                self.reply(200, (ROOT / "app/ui/central.html").read_bytes(), html=True)
                return
            # Assets públicos não contêm estado nem credenciais. Sem resolução
            # de caminhos fornecidos pelo cliente ou navegação de diretórios.
            assets = {"/ui/central.css": "central.css", "/ui/control.js": "control.js"}
            if url.path in assets:
                self.reply(200, (ROOT / 'app/ui' / assets[url.path]).read_bytes(),
                           mime=mimetypes.guess_type(assets[url.path])[0] + '; charset=utf-8')
                return
            if not self.authorized():
                self.reply(403, {"error": "Abra a central pelo executável local."})
                return
            try:
                if url.path == '/api/control/pc2/som':
                    # 11/11: som do PC1 para o painel do PC2, contínuo (só a porta da rede).
                    if not getattr(self.server,'lan',False):raise PermissionError('Só o painel do PC2, pela rede, ouve o som do PC1.')
                    PONTE_AUDIO.servir_som(self)
                    return
                query = {k:v[0] for k,v in parse_qs(url.query).items()}
                if url.path == '/api/control/clipboard-attachment':
                    data, mime = control.clipboard_attachment(query.get('entity', 'hoshino'), query.get('name', ''))
                    self.reply(200, data, mime=mime)
                    return
                if (url.path in {'/api/control/knowledge','/api/control/logic'} or
                    url.path=='/api/control/memory' and query.get('scope')!='chat'):
                    control.require_memories(query.get('entity','hoshino'),self.headers.get('X-Memory-Access',''))
                views = {'/api/control/models': lambda: control.model_settings(query.get('entity','hoshino')),
                         '/api/control/model-versions': lambda: control.model_versions(query.get('entity','hoshino')),
                         '/api/control/neural9b': lambda: control.neural9b_status(query.get('entity','hoshino')),
                         '/api/control/audio': control.audio_settings,
                         '/api/control/memory': lambda: control.memory(query.get('entity','hoshino'),query),
                         '/api/control/knowledge': lambda: control.knowledge(query.get('entity','hoshino'),query),
                         '/api/control/logic':lambda:control.logic_models(query.get('entity','hoshino'),query),
                         '/api/control/activity': lambda: control.activity(query.get('entity') or None,query),
                         '/api/control/timeline': lambda: control.timeline(query.get('entity','hoshino'),query),
                         '/api/control/commands': lambda: control.commands(query.get('entity','hoshino')),
                         '/api/control/resources': control.system,
                         '/api/control/capabilities': lambda:control.capabilities(query.get('entity','hoshino')),
                         '/api/control/interface': control.ui_settings}
                views['/api/control/files'] = control.model_files
                views['/api/control/overlay'] = control.overlay_state
                views['/api/control/entities'] = control.entities
                views['/api/control/gpu-alerts'] = control.gpu_alerts
                views['/api/control/rede'] = lambda: rede_state(self)
                views['/api/control/vram'] = control.vram_settings
                views['/api/control/apis'] = control.api_settings  # 07/11: APIs de modelo e quem usa qual
                views['/api/control/clipboard'] = control.clipboard_capture_state
                views['/api/control/laboratory/night'] = lambda: supervisor.night or {'state':'idle'}
                from laboratorio.rotina_noturna import config as night_config
                views['/api/control/laboratory/night/config'] = lambda: dict(settings=night_config(supervisor.laboratory_home),readiness=supervisor.night_readiness)
                views['/api/control/microphone'] = control.microphone
                views['/api/control/password'] = control.password_state
                views['/api/control/alistair/execution'] = control.alistair_execution
                if url.path in views:
                    self.reply(200, views[url.path]())
                    return
                if url.path == '/api/chat/streams':
                    self.reply(200, supervisor.chat_streams(query.get('entity', 'hoshino'),
                               query.get('conversation_session_id', ''), query.get('chat_scope', 'direct')))
                    return
                if url.path == "/api/world":
                    self.reply(200, world_state.snapshot(since=parse_qs(url.query).get("since", [None])[0]))
                    return
                if url.path == "/api/routing":
                    query = parse_qs(url.query)
                    self.reply(200, capability_router.Router().plan(query.get("capability", ["llm"])[0],
                               query.get("entity", ["hoshino"])[0]))
                    return
                if url.path == "/api/audio/state":
                    self.reply(200, audio.state())
                    return
                if url.path=='/api/audio/listening':
                    entity=validar_entidade(query.get('entity','hoshino'))
                    if query.get('events')=='1':result=audio.listening.recent(entity,query.get('after',0))
                    else:
                        from core.audio_listening import inventory
                        sources=inventory()
                        result=dict(audio.listening.state(entity),sources=sources['sources']+sources['streams'])
                    self.reply(200,result);return
                if url.path == "/api/audio/job":
                    self.reply(200, audio.get(parse_qs(url.query).get("id", [""])[0]))
                    return
                if url.path == "/api/audio/file":
                    query = parse_qs(url.query)
                    self.reply(200, audio.file(query.get("id", [""])[0],query.get('chunk',[None])[0]).read_bytes(), sound=True)
                    return
                if url.path == "/api/control/anexo":
                    # 06/11: imagens que as entidades anexaram (pesquisa profunda); só IDs de 12 hex, só desta pasta.
                    ident = parse_qs(url.query).get("id", [""])[0]
                    if not re.fullmatch(r"[0-9a-f]{12}", ident):
                        raise ValueError("anexo inválido")
                    path = ROOT / "compartilhado/anexos_chat" / (ident + ".jpg")
                    self.reply(200, path.read_bytes(), mime="image/jpeg")
                    return
                if url.path == "/api/image":
                    job = job_bus.get(parse_qs(url.query).get("id", [""])[0])
                    if not job or job["kind"] != "image" or job["status"] != "done" or job["entity"] not in ENTIDADES:
                        raise ValueError("imagem não está concluída")
                    path = Path(job["details"].get("path", "")).resolve()
                    allowed = ROOT / "entidades" / job["entity"] / "runtime/imagens"
                    if not path.is_relative_to(allowed.resolve()) or path.suffix.lower() != ".png":
                        raise ValueError("arquivo fora das imagens da entidade")
                    if path.stat().st_size > 40 * 1024 ** 2:
                        raise ValueError("imagem grande demais para prévia")
                    self.reply(200, path.read_bytes(), image=True)
                    return
                if url.path != "/api/state":
                    self.reply(404, {"error": "não encontrado"})
                    return
                if query.get('daily', '0') not in {'0','1'}:
                    raise ValueError('Modo de conversa inválido.')
                self.reply(200, supervisor.state(query.get('entity', 'hoshino'), daily=query.get('daily')=='1',
                                                session_id=query.get('conversation_session_id',''),
                                                day=query.get('day',''),query=query.get('q',''),
                                                before=query.get('before',0),upper=query.get('upper'),chat_scope=query.get('chat_scope','all')))
            except PermissionError as exc:
                self.reply(403, {'error':str(exc)})
            except ValueError as exc:
                self.reply(400, {"error": str(exc)})
            except OSError:
                self.reply(404, {"error": "Arquivo indisponível."})
            except Exception:
                self.reply(500, {"error": "Falha na consulta; operação não confirmada."})

        def do_POST(self):
            if not self.authorized():
                self.reply(403, {"error": "acesso local inválido"})
                return
            try:
                url = urlsplit(self.path)
                if supervisor.closing and url.path not in ('/api/audio/cancel','/api/audio/perception/stop','/api/control/shutdown'):
                    self.reply(409, {'error': 'Central em encerramento; somente diagnóstico e cancelamento estão disponíveis.'})
                    return
                if url.path in SO_JANELA_ATIVA and not control.window_may_command(self.headers.get('X-Central-Client','')):
                    self.reply(409, {'error': 'Esta janela está em pausa: a outra janela da Central (a última que recebeu '
                                              'foco) está em uso. Clique nesta janela para usá-la.', 'inactive_window': True})
                    return
                size = int(self.headers.get("Content-Length", "0"))
                if url.path == '/api/control/attachment':
                    query=parse_qs(url.query)
                    if not 0<size<=8*1024**2 or self.headers.get('Content-Type')!='application/octet-stream':raise ValueError('Anexo inválido/acima de 8 MiB.')
                    self.reply(200,control.attachment(query.get('entity',[''])[0],query.get('name',[''])[0],self.rfile.read(size)))
                    return
                if url.path == '/api/control/pc2/tela':
                    # 06/11: print da tela do PC2 para um pedido 'tela' (só a porta da rede; PNG até 16 MiB).
                    if not getattr(self.server,'lan',False):raise PermissionError('Só o painel do PC2, pela rede, envia a tela.')
                    if not 0<size<=16*1024**2 or self.headers.get('Content-Type')!='application/octet-stream':raise ValueError('Print inválido/acima de 16 MiB.')
                    self.reply(200,pc2_remoto.guardar_tela(ROOT,parse_qs(url.query).get('id',[''])[0],self.rfile.read(size)))
                    return
                if url.path == '/api/control/pc2/microfone':
                    # 11/11: microfone do PC2 tocado em voz_do_pc2 (microfone padrão do PC1), contínuo e chunked.
                    if not getattr(self.server,'lan',False):raise PermissionError('Só o painel do PC2, pela rede, manda o microfone de lá.')
                    PONTE_AUDIO.receber_microfone(self)
                    return
                if url.path == '/api/control/clipboard':
                    # 06/11: cópia guardada sozinha (texto até 1 MiB, PNG até 8 MiB) na área compartilhada.
                    query=parse_qs(url.query)
                    if not 0<size<=8*1024**2 or self.headers.get('Content-Type')!='application/octet-stream':raise ValueError('Cópia inválida/acima de 8 MiB.')
                    self.reply(200,control.clipboard_capture(query.get('kind',[''])[0],self.rfile.read(size),
                                                             origem='pc2' if getattr(self.server,'lan',False) else 'pc1'))
                    return
                if url.path == '/api/control/upload':
                    query=parse_qs(url.query)
                    if not 0<size<=2*1024**2 or self.headers.get('Content-Type')!='application/octet-stream':
                        raise ValueError('Chunk binário acima do limite/inválido.')
                    self.reply(200,control.import_chunk(query.get('id',[''])[0],int(query.get('offset',['-1'])[0]),self.rfile.read(size)))
                    return
                if url.path == '/api/audio/perception':
                    if size!=31200 or self.headers.get('Content-Type')!='application/octet-stream':
                        raise ValueError('Envie uma janela PCM16 mono16kHz de15600 amostras.')
                    query={k:v[0] for k,v in parse_qs(url.query).items()}
                    overlap=query.get('playback_overlap','false')
                    if overlap not in ('true','false'):raise ValueError('Sobreposição inválida.')
                    self.reply(200,audio.submit_perception(validar_entidade(query.get('entity','')),self.rfile.read(size),
                        source=query.get('source',''),capture_id=query.get('capture_id',''),sequence=int(query.get('sequence','-1')),
                        playback_overlap=overlap=='true',scope=query.get('scope','global'),observed_at=query.get('observed_at')))
                    return
                if url.path == "/api/audio/transcribe":
                    if not 0 < size <= MAX_INPUT_BYTES:
                        raise ValueError("Áudio vazio ou acima de 8 MB.")
                    if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "audio/wav":
                        raise ValueError("Envie um arquivo WAV.")
                    entity = validar_entidade(parse_qs(url.query).get("entity", [""])[0])
                    query=parse_qs(url.query)
                    utterance=query.get('utterance',[None])[0]
                    if utterance is not None:
                        if len(utterance)>1024:raise ValueError('Origem de fala excessiva.')
                        utterance=json.loads(utterance)
                    self.reply(202, audio.submit_transcription(entity, self.rfile.read(size),query.get('source',['browser_microphone'])[0],
                                                               mode=query.get('mode',['command'])[0],utterance=utterance))
                    return
                if not 0 < size <= 65536:
                    raise ValueError("pedido vazio ou grande demais")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("pedido inválido")
                if url.path=='/api/audio/listening':
                    entity=validar_entidade(data.get('entity',''))
                    action=data.get('action')
                    if action=='open':result=audio.listening.open(entity,data.get('channel',''),data.get('source_id',''),data.get('attention','ativa'))
                    elif action=='stop':result=audio.listening.stop(entity,data.get('channel',''))
                    elif action=='attention':result=audio.listening.attention(entity,data.get('channel',''),data.get('attention',''))
                    else:raise ValueError('Ação de escuta inválida.')
                    self.reply(200,result);return
                if url.path=='/api/audio/perception/stop':
                    self.reply(200,audio.perception.cancel(data.get('capture_id','')));return
                if url.path=='/api/control/laboratory/night/config':
                    from laboratorio.rotina_noturna import configure
                    if supervisor.laboratory_maintenance:raise ValueError('Espere a sessão atual encerrar para alterar política')
                    self.reply(200,configure(supervisor.laboratory_home,data));return
                if url.path=='/api/control/laboratory/night/start':
                    self.reply(202,supervisor.authorize_night(data));return
                if url.path=='/api/control/laboratory/night/schedule-once':
                    from laboratorio.sessao_personalizada import schedule
                    self.reply(202,schedule(supervisor,data));return
                if url.path=='/api/control/laboratory/night/cancel-schedule':
                    from laboratorio.sessao_personalizada import cancel
                    self.reply(200,cancel(supervisor,data));return
                if url.path=='/api/control/laboratory/night/stop':
                    self.reply(202,supervisor.cancel_night(data));return
                if url.path == '/api/control/shutdown':
                    if data.get('confirm') is not True or not self.server.request_shutdown:
                        raise ValueError('Encerramento global indisponível ou não confirmado.')
                    supervisor.shutdown_origin = dict(requester='usuario',
                        reason='Encerramento completo confirmado na Central.', source='central')
                    self.server.request_shutdown()
                    self.reply(202,{'accepted':True,'verified':False,'note':'Encerramento cooperativo solicitado; trabalhos incertos não serão repetidos ou mortos à força.'})
                    return
                if url.path == "/api/audio/cancel":
                    self.reply(200, audio.cancel(data.get("id", "")))
                    return
                if url.path=='/api/control/knowledge/unlock':
                    # Única credencial efêmera que precisa chegar ao cliente que
                    # acabou de provar a senha. Nunca desabilitar a redação geral.
                    grant=control.unlock_memories(data)
                    public={k:grant[k] for k in ('unlocked','entity','expires_in')}
                    public['access_token']=grant['access_token']
                    self.reply(200,json.dumps(public).encode(),mime='application/json; charset=utf-8')
                    return
                settings = {'/api/control/model-versions':control.change_model_version,
                            '/api/control/model-versions/prepare':lambda data:control.change_model_version(data,prepare=True),
                            '/api/control/neural9b':control.save_neural9b_mode, '/api/control/models':control.save_model, '/api/control/audio':control.save_audio,
                            '/api/control/interface':control.save_ui}
                settings.update({'/api/control/microphone':control.save_microphone,'/api/control/tools':control.save_tools,
                                 '/api/control/logic':control.save_logic_model,
                                 '/api/control/password':control.set_password,'/api/control/memory/preview':control.memory_preview,
                                 '/api/control/memory/delete':control.delete_memory})
                settings['/api/control/native/open']=control.start_native
                settings['/api/control/chat/feedback']=control.save_chat_feedback
                settings['/api/control/knowledge']=control.save_knowledge
                settings['/api/control/knowledge/lock']=lambda data:control.lock_memories(data.get('entity'),self.headers.get('X-Memory-Access',''))
                settings['/api/control/alistair/execution']=control.save_alistair_execution
                settings['/api/control/alistair/execution/check']=control.check_alistair_execution
                settings['/api/control/rede']=lambda data:rede_save(self,data)
                settings['/api/control/vram']=control.save_vram
                settings['/api/control/apis']=control.save_api
                for route in ('/api/control/pc2/proximo','/api/control/pc2/resultado','/api/control/pc2/sentidos'):
                    settings[route]=lambda data,route=route:pc2_route(self,route,data)
                if url.path in settings:
                    if url.path in {'/api/control/knowledge','/api/control/logic'}:
                        control.require_memories(data.get('entity','hoshino'),self.headers.get('X-Memory-Access',''))
                    self.reply(200, settings[url.path](data))
                    return
                transfers = {'/api/control/import': lambda:control.begin_import(data),
                             '/api/control/import/finish':lambda:control.finish_import(data.get('id')),
                             '/api/control/transfer/cancel':lambda:control.cancel_transfer(data.get('id')),
                             '/api/control/export':lambda:control.export_file(data)}
                if url.path in transfers:
                    self.reply(200,transfers[url.path]())
                    return
                if url.path == '/api/control/overlay/start':
                    self.reply(200,control.start_overlay())
                    return
                if url.path == '/api/control/social':
                    self.reply(200,control.social(data))
                    return
                if url.path == '/api/control/focus':
                    self.reply(200,control.focus(data))
                    return
                if url.path == '/api/audio/interrupt':
                    entity=validar_entidade(data.get('entity'))
                    audio.interrupt_entity(entity)
                    self.reply(200,{'entity':entity,'cancel_requested':True})
                    return
                if url.path == '/api/audio/test':
                    if data.get('confirm') is not True:
                        raise ValueError('Teste de voz requer confirmação explícita; provider externo pode consumir quota.')
                    entity=validar_entidade(data.get('entity'))
                    if set(data)-{'entity','confirm','text','provider','model'}:raise ValueError('Campo de teste inválido.')
                    self.reply(202, audio.submit_speech(entity,text=data.get('text','Olá. Este é um teste de voz da '+entity.capitalize()+'.'),
                                                       test=True,provider=data.get('provider'),model=data.get('model')))
                    return
                entity = validar_entidade(data.get("entity"))
                if url.path == '/api/audio/job':
                    self.reply(200, audio.playback_event(entity, data.get('id',''),
                                                        data.get('playback_event'), data.get('chunk'), data.get('player','browser'),data.get('position_seconds'),data.get('sequence'),data.get('observed_at')))
                    return
                if url.path == "/api/audio/synthesize":
                    if not isinstance(data.get("message_id"), str) or not data["message_id"]:
                        raise ValueError("Selecione uma resposta da entidade para ouvir.")
                    self.reply(202, audio.submit_speech(entity, message_id=data["message_id"]))
                    return
                if url.path == '/api/audio/stream':
                    self.reply(202,audio.submit_stream(entity,str(data.get('stream_id',''))))
                    return
                if url.path == "/api/start":
                    result = supervisor.start(entity, requester='usuario',
                        reason='Despertar solicitado na Central.', source='central')
                elif url.path == "/api/sleep":
                    result = interentity.request_sleep(entity, requester='usuario',
                        reason='Pedido de dormir na Central.', source='central')
                    try:
                        audio.interrupt_entity(entity)
                    except Exception as exc:
                        diagnostics.emit('shutdown.speech_cancel_failed', level='ERROR', entity=entity,
                                         error_type=type(exc).__name__)
                elif url.path == "/api/send":
                    submission = str(data.get('submission_id') or '')
                    if submission and not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', submission):
                        raise ValueError('ID de envio inválido.')
                    session_id = data.get('conversation_session_id', '')
                    if not isinstance(session_id, str) or len(session_id) > 100:
                        raise ValueError('ID de sessão inválido.')
                    received_at = time.time()
                    scope=data.get('chat_scope','direct')
                    origin=dict(audio_origin(audio, entity, data), submission_id=submission,
                                origem_maquina='pc2' if getattr(self.server,'lan',False) else 'pc1')  # 06/11: de qual PC a pessoa escreveu
                    if scope=='global':
                        from core import ui_policy
                        eligible=([e for e in ENTIDADES if ui_policy.capability_allowed(ROOT,e,'ambient')]
                                  if origin.get('capture_mode')=='detection' else None)
                        result=interentity.send_global(data.get('text',''),submission_id=submission,entity=entity,
                                                      conversation_session_id=session_id,metadata=origin,eligible_targets=eligible)
                    else:
                        result = interentity.send("usuario", entity, data.get("text", ""), wake=data.get("wake") is True,
                                                  metadata=origin,conversation_session_id=session_id,chat_scope=scope,
                                                  dedupe_key='central:'+entity+':'+submission if submission else '')
                    if not result.get('deduplicated'):
                        from laboratorio.rotina_noturna import note_sleep
                        try:note_sleep(supervisor.laboratory_home,data.get('text',''),result['id'])
                        except Exception as exc:
                            diagnostics.emit('laboratory.sleep_permission_failed',level='ERROR',error_type=type(exc).__name__)
                        try:
                            from core.audio_playback import explicit_stop
                            if explicit_stop(data.get('text','')):
                                for target in result.get('deliveries',[entity]):audio.interrupt_entity(target, before=received_at)
                        except Exception as exc:
                            # A entrada já está persistida. Não devolver falha de
                            # envio e induzir a pessoa a duplicar uma intenção.
                            diagnostics.emit('audio.interruption_unconfirmed',level='WARN',entity=entity,
                                             error_type=type(exc).__name__,message_id=result['id'])
                else:
                    self.reply(404, {"error": "não encontrado"})
                    return
                self.reply(200, result)
            except PermissionError as exc:
                self.reply(403, {'error':str(exc)})
            except (ValueError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception:
                self.reply(500, {"error": "Falha na central; operação não confirmada."})

    class AudioServer(ThreadingHTTPServer):
        def server_close(self):
            super().server_close()
            if self.world_monitor is not None:
                self.world_monitor.close()
            audio.close()

    server = AudioServer(("127.0.0.1", port), Handler)
    server.audio = audio
    server.control = control
    supervisor.audio = audio
    server.world_monitor = None  # Apenas main inicia sondas; testes/consultas não coletam.
    server.daemon_threads = True
    server.request_shutdown = None
    return server, token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity", choices=[*ENTIDADES, "ambas", "todas"])
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--send", nargs=3, metavar=("DE", "PARA", "TEXTO"))
    parser.add_argument("--wake", nargs=2, metavar=("DE", "PARA"))
    parser.add_argument("--sleep", choices=ENTIDADES)
    parser.add_argument("--no-browser", "--no-terminal", action="store_true")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument('--browser',action='store_true',help='Interface HTML legada explícita; padrão é janela Qt nativa.')
    args = parser.parse_args()
    if args.verify:
        for entity in ENTIDADES:
            validar_entidade(entity)
        if not (ROOT / "app/ui/central.html").is_file():
            raise SystemExit("Interface local ausente.")
        print("Estrutura do iniciador verificada; nenhum modelo foi iniciado.")
        return 0
    if args.status:
        print(interentity.status_text() + "\n" + resource_manager.summary())
        return 0
    if args.send:
        print(interentity.send(*args.send))
        return 0
    if args.wake:
        print(interentity.wake(*args.wake))
        return 0
    if args.sleep:
        print(interentity.request_sleep(args.sleep, requester='usuario',
              reason='Pedido de dormir pelo lançador no terminal.', source='terminal'))
        return 0
    runtime = ROOT / "compartilhado/runtime/launcher"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "supervisor.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            link = runtime / "central.url"
            if link.is_file() and not args.no_browser:
                if args.browser:webbrowser.open(link.read_text().strip())
                else:Control(ROOT,Supervisor(),None).start_native({'entity':args.entity if args.entity in ENTIDADES else 'hoshino'})
            print("A central já está em execução.")
            return 0
        supervisor = Supervisor()
        server, token = make_server(supervisor, args.port)
        url = f"http://127.0.0.1:{server.server_port}/#{token}"
        fd = os.open(runtime / "central.url", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as link:
            os.fchmod(link.fileno(), 0o600)
            link.write(url)
        stopped = threading.Event()
        server.request_shutdown = stopped.set
        def signal_shutdown(signum, _frame):
            supervisor.shutdown_origin = dict(requester='sistema', source='sinal',
                reason=f'A Central recebeu {signal.Signals(signum).name}; emissor não identificado.')
            stopped.set()
        signal.signal(signal.SIGINT, signal_shutdown)
        signal.signal(signal.SIGTERM, signal_shutdown)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # 06/11: painel do PC2 pela rede local; falha aqui nunca impede a Central local.
        lan_server = apply_lan(server)
        if lan_server is not None:
            print(f"Painel pela rede: porta {lan_server.server_port} em {', '.join(central_rede.addresses()) or 'IP local'}.", flush=True)
        server.world_monitor = world_state.Monitor(server.audio)
        server.world_monitor.start()
        # Abrir a Central não acorda entidades; seleção e pedidos explícitos
        # continuam usando o mesmo Supervisor e a caixa postal durável.
        selected = ENTIDADES if args.entity in {"ambas", "todas"} else [args.entity] if args.entity else []
        for entity in selected:
            try:
                supervisor.start(entity, requester='usuario', reason='Seleção explícita no lançador pelo terminal.', source='terminal')
            except ValueError as exc:
                supervisor.failures[entity] = str(exc)
                print(f'{entity.title()}: {exc}', flush=True)
        if not args.no_browser:
            if args.browser:webbrowser.open(url)
            else:server.control.start_native({'entity':args.entity if args.entity in ENTIDADES else 'hoshino'})
        print("Central local aberta. Fechar a janela pede confirmação para encerrar o projeto.", flush=True)
        while True:
            if not stopped.wait(1):
                supervisor.tick()
                if supervisor.night_poweroff_requested:stopped.set()
                continue
            print('Encerrando com prazo global de 45s; acompanhe o diagnóstico na central.', flush=True)
            result = supervisor.shutdown(server.audio, server.world_monitor,ui=server.control)
            shutdown.record_result(ROOT,token,result)
            if result['status'] == 'complete':
                lan_now = getattr(server, 'lan_server', None)  # pode ter sido aberta/trocada depois, pela Central
                if lan_now is not None:
                    lan_now.shutdown()
                    lan_now.server_close()
                server.shutdown()
                server.server_close()
                if supervisor.night_poweroff_requested:
                    from laboratorio.rotina_noturna import poweroff
                    diagnostics.emit('laboratory.poweroff_result',**poweroff(supervisor))
                break
            print('Encerramento bloqueado: operação ainda ativa/incerta. Central mantida para diagnóstico; nenhum efeito foi repetido. Novo pedido de saída fará nova verificação.', flush=True)
            stopped.clear()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
