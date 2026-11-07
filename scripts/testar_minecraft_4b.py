#!/usr/bin/env python3
"""Opt-in real Lilith/4B Minecraft trial, using the existing authorial decider.

No services or application modules are imported without --execute. --check-offline
only compiles source text. A real run creates a fresh test database, leaves the
existing kit/task databases untouched, and keeps the canonical bridge and RM.

Run with the project's Python environment:
    python3 -B scripts/testar_minecraft_4b.py --check-offline
    python3 -B scripts/testar_minecraft_4b.py --execute

There are at most 12 selected iterations and a cooperative 600-second budget.
An already-started operation is drained rather than killed to meet a deadline.
Consequently final observation/cleanup may finish after that budget.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from contextlib import ExitStack, contextmanager
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time
from types import SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / 'compartilhado/runtime/ensaios/minecraft-4b-20261028'
ENTITY = 'lilith'
APP_CHANNEL = 'tui'
CONTEXT_TOKENS = 16000
TARGET = {'host': '10.0.0.200', 'port': 25565, 'username': 'LilithMC', 'version': '1.16.5'}
GOAL = ('Minecraft: host 10.0.0.200 porta 25565 versao 1.16.5. '
        'Fabrique uma picareta de pedra em sobrevivência.')
HOSTILE = {'zombie', 'husk', 'drowned', 'skeleton', 'stray', 'creeper', 'spider',
           'cave_spider', 'enderman', 'witch', 'slime', 'phantom', 'pillager',
           'vindicator', 'zombie_villager', 'silverfish', 'blaze', 'ghast', 'ravager', 'wither'}
SNAPSHOT_KEYS = ('connected', 'verified', 'connectionState', 'sessionId', 'host', 'port',
                 'username', 'version', 'dimension', 'gameMode', 'position', 'health',
                 'food', 'oxygen', 'skyLight', 'inventory', 'equipment', 'heldItem',
                 'nearbyEntities', 'furnaceRuns', 'pathfinding', 'lastError')
READS = {'minecraft_estado', 'minecraft_inventario', 'minecraft_receitas',
         'minecraft_procurar_bloco', 'minecraft_manual', 'minecraft_descobrir_lan'}
SETUP = {'minecraft_iniciar_ponte', 'minecraft_conectar'}


def public_only(value):
    """Reports accept public decisions and tool facts, never private channels."""
    if isinstance(value, dict):
        if any(str(value.get(key, '')).casefold() == 'diario'
               for key in ('name', 'tool', 'tool_name', 'nome')):
            return {'private_record_omitted': True}
        return {str(key): public_only(item) for key, item in value.items()
                if not any(word in str(key).casefold() for word in ('thinking', 'diario', 'private_reason'))}
    if isinstance(value, (list, tuple)):
        return [public_only(item) for item in value]
    if isinstance(value, str):
        text = re.sub(r'<think>.*?(?:</think>|$)', '', value, flags=re.DOTALL)
        return re.sub(r'(?im)^\s*DIARIO:.*$', '[private record omitted]', text)
    return value


def backend_metrics(event):
    keys = ('model', 'done', 'done_reason', 'total_duration', 'load_duration',
            'prompt_eval_count', 'prompt_eval_duration', 'eval_count', 'eval_duration')
    result = {key: event[key] for key in keys if key in event and not isinstance(event[key], (dict, list))}
    count, duration = result.get('eval_count'), result.get('eval_duration')
    if type(count) is int and type(duration) is int and duration > 0:
        result['tokens_per_second'] = round(count * 1e9 / duration, 3)
    return result


def permission_reason(result):
    output = str(result.get('output') or '')
    if result.get('status') == 'permission' or output.startswith('ACESSO_BLOQUEADO:'):
        return public_only(output)[:600] or 'Permissão recusada sem motivo informado.'
    return None


def state_stop_reason(state):
    """Disconnected setup is allowed; connected danger/missing facts stop work."""
    if state.get('connected') is not True:
        return None
    if state.get('verified') is not True or state.get('gameMode') != 'survival':
        return 'Estado conectado sem sobrevivência verificada.'
    health, food = state.get('health'), state.get('food')
    if type(health) not in (int, float) or not math.isfinite(health):
        return 'Vida atual desconhecida.'
    if type(food) not in (int, float) or not math.isfinite(food):
        return 'Fome atual desconhecida.'
    if health <= 10 or food <= 6:
        return 'Perigo observado: vida baixa ou fome.'
    for entity in state.get('nearbyEntities') or []:
        if (isinstance(entity, dict) and entity.get('name') in HOSTILE
                and type(entity.get('distance')) in (int, float)
                and entity['distance'] <= 16 and entity.get('lineOfSight') is not False):
            return 'Perigo observado: hostil próximo.'
    return None


def cleanup_allowed(state, checkpoint, *, uncertain):
    """Disconnect/owned-process cleanup needs a positively observed idle state."""
    if uncertain or checkpoint.get('pending') or 'pathfinding' not in state or state['pathfinding'] is not None:
        return False
    if state.get('connected') is False:
        return True
    return (state.get('connected') is True and state.get('verified') is True
            and all(state.get(key) == TARGET[key] for key in ('host', 'port', 'username')))


def observed_state(result):
    if result.get('ok') is not True:
        return {}
    try:
        state = json.loads(result.get('output') or '')
    except (ValueError, TypeError):
        return {}
    return state if isinstance(state, dict) else {}


class Recorder:
    def __init__(self, folder, seconds):
        self.folder = folder
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.state = {}
        self.checkpoint = {}
        self.uncertain = False
        self.report = {'run_id': folder.name, 'entity': ENTITY, 'goal': GOAL,
                       'channel': APP_CHANNEL, 'origin': 'authorized_minecraft_4b_trial',
                       'target': TARGET, 'live_trial_executed': True,
                       'started_at_utc': datetime.now(timezone.utc).isoformat(),
                       'decisions': [], 'llm_calls': [], 'backend': [], 'tools': [],
                       'resource_events': [], 'cleanup': {}, 'limits': {'seconds': seconds}}

    def save(self):
        with self.lock:
            rendered = json.dumps(public_only(self.report), ensure_ascii=False, indent=2) + '\n'
            temporary = self.folder / 'report.json.tmp'
            temporary.write_text(rendered)
            temporary.replace(self.folder / 'report.json')

    def append(self, key, value):
        with self.lock:
            self.report[key].append(public_only(value))

    def cancel(self, reason):
        with self.lock:
            self.report.setdefault('stop_reason', str(reason))
            self.stop.set()

    def cancelled(self):
        if time.monotonic() >= self.deadline:
            self.cancel('Orçamento cooperativo de tempo atingido; nenhuma nova ação.')
        return self.stop.is_set()

    def observe(self, state):
        with self.lock:
            self.state = copy.deepcopy(state)
            snapshot = {key: copy.deepcopy(state[key]) for key in SNAPSHOT_KEYS if key in state}
            self.report.setdefault('snapshot_before', snapshot)
            if state.get('connected') is True:
                if not all(state.get(key) == TARGET[key] for key in ('host', 'port', 'username')):
                    self.cancel('Destino ou jogador diferente do ensaio autorizado.')
                self.report.setdefault('snapshot_first_connected', snapshot)
            elif 'snapshot_first_connected' in self.report:
                self.cancel('Conexão caiu após entrar; sessão preservada para conferência.')
            reason = state_stop_reason(state)
            if reason:
                self.cancel(reason)
            return snapshot


@contextmanager
def replaced(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield original
    finally:
        setattr(obj, name, original)


def load_runtime(folder, iterations):
    """Called only after explicit opt-in; bind isolated paths before app imports."""
    if any(name in sys.modules for name in ('config', 'main', 'core.resource_manager')):
        raise RuntimeError('Execute em processo Python novo; módulos da aplicação já foram importados.')
    os.environ.update(HOSHINO_ENTIDADE=ENTITY, HOSHINO_MAX_PASSOS_TAREFA_LONGA=str(iterations),
                      HOSHINO_DIAGNOSTICS_TRACE='0', HOSHINO_STREAM_LLM='1',
                      HOSHINO_OLLAMA_URL='http://127.0.0.1:11436/api/chat',
                      HOSHINO_OLLAMA_HOST='127.0.0.1:11436',
                      HOSHINO_MINECRAFT_BRIDGE='http://127.0.0.1:8766',
                      HOSHINO_MC_BRIDGE_PORT='8766', HOSHINO_MINECRAFT_USERNAME='LilithMC')
    sys.path[:0] = [str(ROOT / 'app'), str(ROOT)]
    import config
    canonical_runtime = config.RUNTIME_DIR
    runtime = folder / 'runtime'
    runtime.mkdir()
    config.DB_PATH = str(folder / 'test-task.sqlite3')
    config.RUNTIME_DIR = str(runtime)
    config.ESTADO_MENTE = str(runtime / 'estado_mente.json')
    config.EVENT_LOG_DIR = str(runtime / 'event_log')
    config.JOBS_DIR = str(runtime / 'jobs')
    config.BUS_DIR = str(runtime / 'bus')
    config.VECTOR_DIR = str(folder / 'vector-unused')
    config.MAX_PASSOS_TAREFA_LONGA = iterations
    config.MIC_ATIVO = False
    config.VOZ_ATIVA = False
    from core import entity_admission, interentity
    return SimpleNamespace(config=config, canonical_runtime=canonical_runtime,
                           entity_admission=entity_admission, interentity=interentity)


def load_application(runtime):
    from memory.sqlite import init_db
    init_db.init_database(verbose=False)
    import main as application
    from core import minecraft_agent, resource_manager, gpu_resource, gpu_metrics, diagnostics, task_state, dispatch, job_bus, ollama_lifecycle
    from tools import minecraft_launcher
    return SimpleNamespace(**vars(runtime), application=application, agent=minecraft_agent,
                           rm=resource_manager, gpu=gpu_resource, gpu_metrics=gpu_metrics,
                           diagnostics=diagnostics, task_state=task_state, dispatch=dispatch,
                           job_bus=job_bus, lifecycle=ollama_lifecycle, launcher=minecraft_launcher)


class MetricsResponse:
    """Pass frames through unchanged; retain only the final numeric metadata."""
    def __init__(self, response, recorder):
        self.response, self.recorder = response, recorder

    def __getattr__(self, name):
        return getattr(self.response, name)

    def iter_lines(self, *args, **kwargs):
        for line in self.response.iter_lines(*args, **kwargs):
            if line:
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    event = None
                if isinstance(event, dict) and event.get('done') is True:
                    self.recorder.append('backend', backend_metrics(event))
            yield line


async def trial(apps, recorder, iterations):
    config, agent, rm = apps.config, apps.agent, apps.rm
    app = object.__new__(apps.application.InterfaceHoshino)
    app._draining = False
    app._saidas_por_conversa = {}
    app._locks_saida = {}
    app._fila_chaves = {}
    app.canal_atual = APP_CHANNEL
    app.sys_log = SimpleNamespace(write=lambda _: None)
    # No prompt_sistema: completion returns its receipt without another summary inference.
    key = (APP_CHANNEL, recorder.folder.name, 'ensaio4b')
    task = apps.task_state.iniciar_ou_continuar(key, GOAL)
    criteria = agent.targets(task.objetivo)
    if criteria != {'inventory': {'stone_pickaxe': 1}, 'equipped': {}, 'placed': {}, 'crafted': {'stone_pickaxe': 1}}:
        raise RuntimeError('Contrato do objetivo não corresponde à única picareta de pedra.')
    cp = agent.initial(task.objetivo, criteria)
    cp.update(target=copy.deepcopy(TARGET), username=TARGET['username'])
    agent.save(task, cp)
    recorder.checkpoint = cp
    recorder.report['task_id'] = task.id
    catalog = rm.executor_catalog()
    light = next((row for row in catalog if row['tier'] == 'light'
                  and row.get('gpu_layers') == -1 and 'qwen3.5-4b' in row['model']), None)
    if light is None or not rm.local_model_installed(light['model']):
        raise RuntimeError('Executor 4B leve aprovado/instalado não encontrado; sem substituição ou download.')
    choice = rm.ExecutorChoice(model=light['model'], tier='light', reason='authorized_minecraft_4b_trial',
                              num_ctx=CONTEXT_TOKENS, vram_bytes=light['vram_bytes'],
                              expected_latency=light['expected_latency'], fallback_latency=light['fallback_latency'],
                              output_max=1024, supports_tools=True, supports_thinking=True, supports_format=True,
                              fixed_window=True)
    recorder.report['executor'] = {'model': choice.model, 'tier': choice.tier, 'num_ctx': CONTEXT_TOKENS,
                                   'output_max': 1024, 'gpu_layers': -1, 'reason': choice.reason,
                                   'fixed_window': True, 'context_scope': 'Human-authorized trial only; catalog unchanged.'}
    real_dispatch = apps.dispatch.executar_resultado
    real_run = agent.run
    real_model = app.chamar_modelo
    real_post = apps.application.requests.post
    real_emit = apps.diagnostics.emit
    real_start_bridge = apps.launcher.iniciar_ponte
    cleanup_phase = {'active': False}

    def start_bridge():
        # Persisted furnace ownership belongs to the canonical bridge runtime.
        # Trial notes/DB remain isolated before and after this serialized setup.
        if recorder.cancelled():
            raise RuntimeError('Ensaio cancelado antes de iniciar a ponte.')
        original_runtime = config.RUNTIME_DIR
        config.RUNTIME_DIR = apps.canonical_runtime
        try:
            return real_start_bridge()
        finally:
            config.RUNTIME_DIR = original_runtime

    def refusal(reason):
        recorder.cancel(reason)
        return {'ok': False, 'status': 'error', 'output': 'ERRO_CONTROLADOR: ' + reason,
                'precondition_failed': True, 'effect_started': False}

    def dispatch(tool, arguments, *args, **kwargs):
        arguments = arguments or {}
        is_read = tool in READS or (tool == 'minecraft_forno' and arguments.get('acao', 'estado') == 'estado')
        # Opening a furnace is a serialized client-window operation even when
        # it does not change world items. Do not open a new window after stop.
        if not cleanup_phase['active'] and tool == 'minecraft_forno' and recorder.cancelled():
            return refusal(recorder.report['stop_reason'])
        if not cleanup_phase['active'] and not is_read:
            if recorder.cancelled():
                return refusal(recorder.report['stop_reason'])
            if tool in {'minecraft_conectar_lan', 'minecraft_desconectar', 'minecraft_parar'}:
                return refusal('Operação de sessão fora do escopo durante o ensaio.')
            if tool == 'minecraft_conectar' and any(arguments.get(k) != TARGET[k] for k in TARGET):
                return refusal('Conexão diferente do destino/jogador autorizado.')
            if tool not in SETUP and tool.startswith('minecraft_'):
                if recorder.state.get('connected') is not True:
                    return refusal('Estado conectado não confirmado antes do efeito.')
                if recorder.state.get('pathfinding') is not None:
                    return refusal('Já há ação em andamento; nenhuma nova ação iniciada.')
        began = time.monotonic()
        result = real_dispatch(tool, arguments, *args, **kwargs)
        denied = permission_reason(result)
        recorder.append('tools', {'tool': tool, 'arguments': arguments,
                                 'seconds': round(time.monotonic() - began, 3),
                                 'status': result.get('status'), 'ok': result.get('ok'),
                                 'receipt_id': result.get('receipt_id'), 'cleanup': cleanup_phase['active'],
                                 **({'permission_reason': denied} if denied else {})})
        if denied:
            recorder.report['permission_refusal'] = {'tool': tool, 'channel': APP_CHANNEL, 'reason': denied}
            recorder.cancel(denied)
        if result.get('outcome_uncertain') or result.get('status') == 'uncertain':
            recorder.uncertain = True
            recorder.cancel('Efeito incerto: nenhuma nova ação ou desconexão automática.')
        if tool == 'minecraft_estado':
            state = observed_state(result)
            if state:
                if cleanup_phase['active']:
                    recorder.state = copy.deepcopy(state)
                else:
                    recorder.observe(state)
            elif not cleanup_phase['active']:
                recorder.cancel('Observação de estado inválida; nenhuma nova ação ou reconexão automática.')
        return result

    async def tracked_run(criteria, checkpoint, **callbacks):
        recorder.checkpoint = checkpoint
        ask, persist = callbacks['ask'], callbacks['persist']

        async def tracked_ask(state, current):
            began = time.monotonic()
            row = {'iteration': len(recorder.report['decisions']) + 1, 'step_before': current['steps']}
            try:
                decision = await ask(state, current)
                row.update({key: copy.deepcopy(decision.get(key)) for key in ('tool', 'arguments', 'comment')})
                return decision
            except BaseException as exc:
                row['error_type'] = type(exc).__name__
                raise
            finally:
                row['seconds'] = round(time.monotonic() - began, 3)
                recorder.append('decisions', row)

        def tracked_persist(current):
            persist(current)
            recorder.report['checkpoint'] = {key: copy.deepcopy(current.get(key)) for key in
                                             ('steps', 'no_progress', 'pending', 'crafted', 'subgoal', 'plan_steps',
                                              'plan_feedback', 'events', 'trajectory', 'goal_monitor')}
            recorder.save()

        callbacks.update(ask=tracked_ask, persist=tracked_persist, limit=min(iterations, callbacks.get('limit', iterations)))
        outcome = await real_run(criteria, checkpoint, **callbacks)
        recorder.report['outcome'] = {key: copy.deepcopy(outcome.get(key)) for key in ('status', 'reason', 'used')}
        return outcome

    async def model(messages, tools=None, **kwargs):
        if recorder.cancelled():
            raise apps.application.TurnoCancelado()
        began = time.monotonic()
        row = {'model': choice.model, 'structured': kwargs.get('formato') is not None,
               'tool_count': len(tools or []), 'requested_output_limit': kwargs.get('limite_saida')}
        try:
            response = await real_model(messages, tools, **kwargs)
            row.update(ok=True, public_content_chars=len(str(response.get('content') or '')))
            return response
        except BaseException as exc:
            row.update(ok=False, error_type=type(exc).__name__)
            raise
        finally:
            row['seconds'] = round(time.monotonic() - began, 3)
            recorder.append('llm_calls', row)

    def post(url, *args, **kwargs):
        body = kwargs.get('json') or {}
        endpoint = config.OLLAMA_URL.rsplit('/api/', 1)[0]
        if str(url).startswith(endpoint + '/api/') and isinstance(body, dict) and body.get('model'):
            if body['model'] != choice.model:
                raise RuntimeError('Inferência/recuperação fora do 4B autorizado foi recusada.')
            if str(url) == config.OLLAMA_URL:
                options = body.get('options') or {}
                if options.get('num_ctx', CONTEXT_TOKENS) > CONTEXT_TOKENS or options.get('num_predict', 1024) > 1024:
                    raise RuntimeError('Pedido excedeu os limites do executor leve.')
                response = real_post(url, *args, **kwargs)
                if kwargs.get('stream') or body.get('stream'):
                    return MetricsResponse(response, recorder)
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        recorder.append('backend', backend_metrics(data))
                except (ValueError, TypeError):
                    pass
                return response
        return real_post(url, *args, **kwargs)

    def emit(event, *args, **kwargs):
        if event in {'gpu.compute_acquired', 'gpu.compute_released', 'executor.context_selected',
                     'executor.context_overflow', 'llm.backend_timing', 'gpu.offload_selected'}:
            recorder.append('resource_events', {'event': event, **kwargs})
        return real_emit(event, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(replaced(apps.dispatch, 'executar_resultado', dispatch))
        stack.enter_context(replaced(agent, 'run', tracked_run))
        stack.enter_context(replaced(app, 'chamar_modelo', model))
        stack.enter_context(replaced(apps.application.requests, 'post', post))
        stack.enter_context(replaced(apps.diagnostics, 'emit', emit))
        stack.enter_context(replaced(apps.launcher, 'iniciar_ponte', start_bridge))
        try:
            # Check the existing daemon without generating or invoking model recovery.
            tags = await asyncio.to_thread(apps.application.requests.get,
                                           config.OLLAMA_URL.rsplit('/api/', 1)[0] + '/api/tags', timeout=3)
            tags.raise_for_status()
            if choice.model not in {row.get('name') for row in tags.json().get('models', [])}:
                raise RuntimeError('O daemon canônico não possui o alias 4B aprovado.')
            health = await asyncio.to_thread(apps.launcher._saude_ponte)
            recorder.report['bridge_existed_before'] = health is not None
            recorder.report['bridge_health_before'] = ({
                'protocol': health.get('protocol'),
                'state': {key: copy.deepcopy((health.get('state') or {}).get(key))
                          for key in SNAPSHOT_KEYS if key in (health.get('state') or {})},
                'owned_by_this_run': apps.launcher._bridge_proc is not None,
            } if isinstance(health, dict) else None)
            if health is None:
                if await asyncio.to_thread(apps.launcher._porta_aberta, '127.0.0.1', config.MINECRAFT_BRIDGE_PORT):
                    raise RuntimeError('Porta da ponte ocupada sem health válido; processo existente preservado.')
                recorder.report['bridge_start'] = await asyncio.to_thread(start_bridge)
            state_result = await asyncio.to_thread(dispatch, 'minecraft_estado', {}, False, APP_CHANNEL, None)
            if state_result.get('ok') is not True:
                denied = permission_reason(state_result)
                if denied:
                    raise PermissionError(denied)
                raise RuntimeError('Estado inicial da ponte não confirmado.')
            recorder.report['gpu_before'] = apps.gpu_metrics.snapshot()

            @rm.inference_cycle('task', inherit=False)
            async def decide_and_act():
                cycle = rm._inference_cycle.get()
                cycle['choice'] = choice
                cycle['task'] = True
                cycle['input'] = GOAL
                return await app._ciclo_minecraft_observado(task, criteria, cancelar=recorder.cancelled,
                                                           chave_conversa=key, canal=APP_CHANNEL, retomar=False)

            summary, used = await decide_and_act()
            recorder.report.update(summary=summary, used=used)
        finally:
            cleanup_phase['active'] = True
            await cleanup(apps, app, recorder, dispatch, choice.model)


async def cleanup(apps, app, recorder, dispatch, model):
    """Observe and drain; never force-stop uncertain effects or unknown owners."""
    try:
        result = await asyncio.to_thread(dispatch, 'minecraft_estado', {}, False, APP_CHANNEL, None)
        state = observed_state(result)
        recorder.report['snapshot_after'] = {key: copy.deepcopy(state[key]) for key in SNAPSHOT_KEYS if key in state}
        safe = cleanup_allowed(state, recorder.checkpoint, uncertain=recorder.uncertain)
        recorder.report['cleanup']['safe_idle_confirmed'] = safe
        if safe and state.get('connected') is True:
            disconnected = await asyncio.to_thread(dispatch, 'minecraft_desconectar', {}, False, APP_CHANNEL, None)
            recorder.report['cleanup']['disconnect'] = {key: disconnected.get(key) for key in ('ok', 'status', 'receipt_id')}
            observed = await asyncio.to_thread(dispatch, 'minecraft_estado', {}, False, APP_CHANNEL, None)
            state = observed_state(observed)
            safe = (disconnected.get('ok') is True and state.get('connected') is False
                    and cleanup_allowed(state, recorder.checkpoint, uncertain=recorder.uncertain))
        owned = apps.launcher._bridge_proc
        recorder.report['cleanup']['owned_bridge_pid'] = getattr(owned, 'pid', None)
        if safe and owned is not None and owned.poll() is None:
            owned.terminate()
            try:
                await asyncio.to_thread(owned.wait, timeout=4)
                apps.launcher._bridge_proc = None
                recorder.report['cleanup']['owned_bridge_stopped'] = True
            except Exception as exc:
                recorder.report['cleanup'].update(owned_bridge_stopped=False, bridge_stop_error=type(exc).__name__)
                # Deliberately no kill(): retain the process for operator review.
        if recorder.report['llm_calls'] and all(row.get('ok') for row in recorder.report['llm_calls']) and not getattr(app, '_llm_http_ativos', 0):
            def unload():
                with apps.gpu.lease('unload', wait=5):
                    return apps.lifecycle._descarregar_modelo_sem_lease(timeout=15, model=model)
            try:
                ok, _ = await asyncio.to_thread(unload)
                recorder.report['cleanup']['4b_unload_confirmed'] = bool(ok)
            except Exception as exc:
                recorder.report['cleanup']['4b_unload_error'] = type(exc).__name__
        recorder.report['gpu_after'] = apps.gpu_metrics.snapshot()
    except Exception as exc:
        recorder.report['cleanup']['error_type'] = type(exc).__name__


async def execute_trial(options, folder):
    recorder = Recorder(folder, options.seconds)
    recorder.report['limits']['iterations'] = options.iterations
    heartbeat_stop = threading.Event()
    presence = {'status': 'starting'}
    previous_signals = {}
    apps = None
    try:
        runtime = load_runtime(folder, options.iterations)
        with runtime.entity_admission.instance(ROOT, ENTITY):
            runtime.interentity.register(ENTITY, 'starting', pid=os.getpid(), detail='Ensaio Minecraft 4B opt-in; banco isolado.')

            def heartbeat():
                while not heartbeat_stop.wait(8):
                    try:
                        runtime.interentity.heartbeat(ENTITY, presence['status'], 'Ensaio Minecraft 4B opt-in.')
                    except Exception:
                        recorder.cancel('Falha no heartbeat da presença; nenhuma nova ação.')

            worker = threading.Thread(target=heartbeat, daemon=True, name='minecraft-4b-presence')
            worker.start()
            try:
                for name in (signal.SIGINT, signal.SIGTERM):
                    previous_signals[name] = signal.getsignal(name)
                    signal.signal(name, lambda *_: recorder.cancel('Interrupção solicitada; drenagem cooperativa.'))
                apps = load_application(runtime)
                apps.job_bus.publish(folder.name, ENTITY, 'running', kind='minecraft_4b_trial', goal=GOAL)
                presence['status'] = 'awake'
                runtime.interentity.register(ENTITY, 'awake', pid=os.getpid(), detail='Ensaio curto 4B; tarefa independente do kit.')
                await trial(apps, recorder, options.iterations)
            except BaseException as exc:
                recorder.report['error_type'] = type(exc).__name__
                # Do not stringify exceptions carrying partial model output.
                recorder.cancel('Ensaio interrompido por erro; consultar recibos públicos e checkpoint isolado.')
            finally:
                heartbeat_stop.set()
                worker.join(timeout=2)
                try:
                    if apps is not None:
                        status = 'done' if recorder.report.get('outcome', {}).get('status') == 'completed' else 'interrupted'
                        apps.job_bus.publish(folder.name, ENTITY, status, kind='minecraft_4b_trial',
                                             report=str(folder / 'report.json'))
                finally:
                    runtime.interentity.register(ENTITY, 'sleeping', pid=os.getpid(),
                                                 detail='Ensaio 4B terminou; efeitos incertos/ponte preservados quando necessário.')
    except Exception as exc:
        recorder.report.setdefault('error_type', type(exc).__name__)
        recorder.report.setdefault('stop_reason', 'Admissão ou preparação não concluída.')
    finally:
        for name, handler in previous_signals.items():
            signal.signal(name, handler)
        recorder.report['elapsed_seconds'] = round(time.monotonic() - recorder.started, 3)
        recorder.report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        recorder.save()
    return 0 if recorder.report.get('outcome', {}).get('status') == 'completed' else 2


def run_live(options):
    folder = EVIDENCE_ROOT / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    code = asyncio.run(execute_trial(options, folder))
    print(json.dumps({'exit_code': code, 'report': str(folder / 'report.json')}, ensure_ascii=False))
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true', help='Autoriza o ensaio real curto no mundo atual.')
    mode.add_argument('--check-offline', action='store_true', help='Somente sintaxe/estrutura; não importa a aplicação.')
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--iterations', type=int, default=12)
    options = parser.parse_args(argv)
    if not 1 <= options.seconds <= 600 or not 1 <= options.iterations <= 12:
        parser.error('Use até 600 segundos e até 12 iterações.')
    if options.check_offline:
        for relative in ('scripts/testar_minecraft_4b.py', 'app/main.py', 'app/core/minecraft_agent.py',
                         'app/core/minecraft_cognition.py', 'app/core/entity_admission.py'):
            source = (ROOT / relative).read_text()
            compile(ast.parse(source), str(ROOT / relative), 'exec')
        print(json.dumps({'offline_check': 'passed', 'live_trial_executed': False}))
        return 0
    if not options.execute:
        print(json.dumps({'live_trial_executed': False, 'reason': 'Execução real exige --execute.'}, ensure_ascii=False))
        return 2
    return run_live(options)


if __name__ == '__main__':
    raise SystemExit(main())
