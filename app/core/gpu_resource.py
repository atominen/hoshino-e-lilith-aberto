"""Adaptador dos modelos locais para o Resource Manager cooperativo."""
from __future__ import annotations

import contextlib
import os
import sqlite3
import time
from contextvars import ContextVar
from pathlib import Path

import config
from core import resource_manager, gpu_metrics, diagnostics
import requests

_request = ContextVar('gpu_request', default=None)
_priority = ContextVar('gpu_priority', default=1)
_cancellation = ContextVar('gpu_cancellation',default=None)
# Último degrau de camadas por modelo: num_gpu diferente faz o Ollama recarregar.
_warm_offload = {}


def _proven(request, models):
    """Revisões Codex: a isenção do modelo inteiro na placa (resident_full) é só um pedido; cada avaliação aqui usa
    a prova feita agora (resource_manager.resident_whole), como a fila do compute_lease."""
    if not request.get('resident_full'):
        return request
    return dict(request, resident_full=resource_manager.resident_whole(models, request.get('model_key'), request.get('resident_ctx')))

# Degraus quentes admitidos sem medição confiável (base do catálogo ou último
# degrau): 27/10 19:16 o 9B ficou preso em 20 camadas com VRAM sobrando.
_uncertain_offload = set()


def current_priority():
    return _priority.get()


@contextlib.contextmanager
def priority(value, *, cancel=None):
    scope = _priority.set(int(value))
    cancellation = _cancellation.set(cancel) if cancel is not None else None
    try:
        yield
    finally:
        if cancellation is not None: _cancellation.reset(cancellation)
        _priority.reset(scope)


def routed_payload(payload, acquired):
    if acquired and acquired.get('backend')=='cpu':
        return dict(payload,options={**payload.get('options',{}),'num_gpu':0})
    if acquired and acquired.get('backend')=='gpu':
        return dict(payload, options={**payload.get('options',{}),
                    'num_gpu':acquired.get('gpu_layers', -1)})
    return payload


def prepare_residency(owner: str) -> list[str]:
    """Só libera pesos ociosos quando a pressão e o custo justificarem.

    Chamado pelo gerenciador sob manutenção exclusiva, sem compute ativo.
    Nunca toca no Ollama padrão, nunca mata daemon ou pausa imagem.
    """
    current = config.OLLAMA_URL.rsplit("/api/", 1)[0]
    endpoints = {"http://127.0.0.1:11435", "http://127.0.0.1:11436", "http://127.0.0.1:11437"}
    request = _request.get() or dict(owner=owner, model_key='' if owner=='image' else current+'|'+config.MODEL_NAME,
                                    vram_bytes=6*gpu_metrics.GIB, workspace_bytes=512*1024**2,
                                    priority=resource_manager.PRIORITIES.get(owner,5),
                                    expected_latency=15, fallback_latency=120)
    unloaded = []
    candidates = []
    own_cpu = None
    for base in sorted(endpoints):
        if resource_manager.higher_priority_waiting(request['priority']):
            raise resource_manager.GPUDeferred('Sondagem de residência adiada para trabalho prioritário.')
        try:
            response = requests.get(base + "/api/ps", timeout=(1, 2))
        except requests.ConnectionError:
            continue
        response.raise_for_status()
        for model in response.json().get("models", []):
            name = model.get("name") or model.get("model")
            if not name:
                continue
            size = model.get('size_vram')
            resource_manager.observe_model(base, name, size)
            reported = max(model.get('size') or 0,size or 0)
            if reported>0: resource_manager.record_memory_estimate(base,name,reported)
            if model.get('context_length'): resource_manager.record_model_context(base,name,model['context_length'])
            if size == 0:
                if base+'|'+name == request['model_key']:
                    own_cpu = name
                continue
            if base+'|'+name == request['model_key']:
                continue
            candidates.append((base,name))
        observed = {m.get('name') or m.get('model') for m in response.json().get('models', [])}
        for old in resource_manager.residency():
            if old['endpoint']==base and old['model'] not in observed:
                resource_manager.forget_model(base, old['model'])
    if request['model_key'] and current in endpoints and request.get('use_model_estimate', True):
        estimate = resource_manager.memory_estimate(request['model_key'])
        if estimate is None:
            catalog = requests.get(current+'/api/tags',timeout=(1,2))
            catalog.raise_for_status()
            selected_model = request['model_key'].split('|', 1)[1]
            for model in catalog.json().get('models',[]):
                if (model.get('name') or model.get('model'))==selected_model and model.get('size',0)>0:
                    resource_manager.record_memory_estimate(current,selected_model,model['size'])
            estimate = resource_manager.memory_estimate(request['model_key'])
        if estimate is not None: request['vram_bytes']=int(estimate)
    policy = resource_manager.gpu_policy()
    rows = {r['model_key']:r for r in resource_manager.residency()}
    candidates.sort(key=lambda item: rows[item[0]+'|'+item[1]]['last_used'])
    for base, name in candidates:
        metrics = gpu_metrics.snapshot()
        models = resource_manager.residency()
        decision = resource_manager.assess_gpu(_proven(request, models), metrics, models=models)
        if decision['allowed'] or decision['reason'] != 'vram_pressure':
            break
        row = rows[base+'|'+name]
        if resource_manager.higher_priority_waiting(request['priority']):
            raise resource_manager.GPUDeferred('Manutenção adiada para solicitação interativa.')
        # Sticky é economia de reload, não exclusão indefinida da outra
        # entidade. O RM só chama este ponto sob manutenção exclusiva, sem
        # compute ativo. Depois de espera limitada, um par H/L pode ceder pesos
        # ociosos; margem, benefício e verificação de unload continuam exigidos.
        peer_main = (owner == 'llm' and request['priority'] == 2 and
                     config.ENTIDADE_ID in {'hoshino','lilith'} and base != current and
                     base in {'http://127.0.0.1:11435','http://127.0.0.1:11436'})
        queued_at = request.get('queue_started_monotonic')
        fair_wait = (peer_main and isinstance(queued_at,(int,float)) and
                     time.monotonic()-queued_at >= min(policy['sticky_seconds'],
                         max(1,float(request.get('wait_budget_seconds',120)))/2))
        if request['priority'] > 1 and time.time()-row['last_used'] < policy['sticky_seconds'] and not fair_wait:
            continue
        benefit = request['fallback_latency']-request['expected_latency']
        hot_cost = 10 if time.time()-row['last_used'] < policy['sticky_seconds'] else 0
        if benefit <= row['reload_seconds']+hot_cost:
            continue
        if metrics.get('utilization') is None or metrics['utilization'] >= 90:
            continue  # não sabemos se um consumidor externo está gerando
        started = time.monotonic()
        diagnostics.emit('gpu.unload_requested', owner=owner, model=name, endpoint=base,
                         benefit_seconds=benefit, reload_cost_seconds=row['reload_seconds'], metrics=metrics)
        result = requests.post(base + "/api/generate", json={
            "model": name, "keep_alive": 0, "stream": False}, timeout=(1, 5))
        result.raise_for_status()
        check = requests.get(base + "/api/ps", timeout=(1, 2))
        check.raise_for_status()
        if any((m.get("name") or m.get("model")) == name for m in check.json().get("models", [])):
            raise RuntimeError(f"modelo concorrente não liberou a GPU: {name}")
        resource_manager.forget_model(base, name)
        unloaded.append(name)
        diagnostics.emit('gpu.unloaded', model=name, duration_seconds=time.monotonic()-started,
                         vram_after=gpu_metrics.snapshot())
    # Pedido humano 30/10: todos os pesos ociosos do projeto já saíram e ainda falta VRAM → fecha o app aberto por
    # último que, sozinho, libera o que falta (desligado por padrão; ver vram_guard).
    # Revisão Codex: com pesos preservados (sticky, custo de recarga) ou sem RAM para carregar, não fecha nada.
    metrics = gpu_metrics.snapshot()
    models = resource_manager.residency()
    decision = resource_manager.assess_gpu(_proven(request, models), metrics, models=models)
    own = next((r for r in models if r['model_key'] == request['model_key']), None)
    staging = (2*gpu_metrics.GIB if resource_manager.model_state(own) in {'gpu_resident','ram_resident'}
               else request['vram_bytes'])
    ram = gpu_metrics.ram_available()
    # Revisão Codex: a prova vem da residência que sobrou, não da lista desta sondagem (uma consulta que falhou
    # deixa a lista vazia): qualquer outro modelo ainda registrado com VRAM — preservado, em daemon sem resposta
    # ou com VRAM desconhecida — veta.
    # VRAM desconhecida (None, ex.: depois de um reload) também veta até uma sondagem conclusiva.
    others_on_gpu = [r for r in models if r['model_key'] != request['model_key'] and r.get('vram_bytes') != 0]
    if (decision['reason'] == 'vram_pressure' and not others_on_gpu
            and ram is not None and ram >= staging+policy['ram_margin_bytes']
            and not resource_manager.higher_priority_waiting(request['priority'])):
        from core import vram_guard
        vram_guard.reclaim(request, decision, metrics, policy,
                           interrupt=lambda: resource_manager.higher_priority_waiting(request['priority']))
    # O daemon pode reutilizar um runner CPU mesmo com num_gpu=-1. A troca
    # ocorre somente sob a manutenção exclusiva que chamou esta função.
    if own_cpu and resource_manager.assess_gpu(_proven(request, resource_manager.residency()), gpu_metrics.snapshot(),
            models=resource_manager.residency())['allowed']:
        from core import ollama_lifecycle
        started = time.monotonic()
        ok, detail = ollama_lifecycle._descarregar_modelo_sem_lease(timeout=10, model=own_cpu)
        diagnostics.emit('gpu.cpu_to_gpu_unload', model=own_cpu, confirmed=ok,
                         duration_seconds=time.monotonic()-started)
        if not ok:
            raise RuntimeError('Troca CPU/GPU bloqueada: unload próprio não confirmado: '+detail)
        resource_manager.forget_model(current, own_cpu)
        unloaded.append(own_cpu)
    return unloaded


def _lock_path() -> Path:
    # A GPU é da máquina; o lock não pode acompanhar a memória de uma entidade.
    p = Path(config.SHARED_RUNTIME_DIR) / "gpu_resource.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextlib.contextmanager
def lease(owner: str, *, priority=None, cpu_fallback=False, wait=120, cancel=None,
          vram_bytes=None, workspace_bytes=None, model=None, expected_latency=None,
          fallback_latency=None, opportunistic=False):
    """Compute termina na saída do contexto; os pesos não são descarregados."""
    _lock_path().touch(exist_ok=True)  # caminho legado de diagnóstico
    cancel = _cancellation.get() if cancel is None else cancel
    if callable(cancel):
        callback = cancel
        class Cancellation:
            def is_set(self): return bool(callback())
        cancel = Cancellation()
    if owner == 'unload':
        with resource_manager.lease('gpu', owner, entity=config.ENTIDADE_ID, wait=wait, cancel=cancel):
            yield dict(backend='gpu', priority=5)
        return
    current = config.OLLAMA_URL.rsplit('/api/', 1)[0]
    model_key = '' if owner=='image' else current+'|'+(model or config.MODEL_NAME)
    automatic_estimate = vram_bytes is None and owner!='image'
    executor = next((e for e in resource_manager.executor_catalog() if e['model']==model), None)
    if executor and executor.get('gpu_profile') and owner in {'llm','vision'}:
        automatic_estimate = False  # RAM total de runner CPU não é o offload medido
    if vram_bytes is None:
        vram_bytes = (int(config.IMAGE_MAX_VRAM_GIB*gpu_metrics.GIB) if owner=='image' else
                      executor['vram_bytes'] if executor else 6*gpu_metrics.GIB)
    if workspace_bytes is None:
        workspace_bytes = 0 if owner=='image' else gpu_metrics.GIB if executor and executor['tier']=='light' else 512*1024**2
    gpu_layers = executor.get('gpu_layers') if executor else None
    uncertain = False
    resident_full = False
    if owner in {'llm','vision'} and executor and executor.get('gpu_profile') and executor.get('gpu_layers') in {20,32}:
        # Perfis 20/32 do mesmo 9B: o degrau segue a VRAM livre (o Minecraft e o
        # desktop variam). Só antes da inferência; contexto e margem preservados.
        probe=dict(owner=owner,model_key=model_key,vram_bytes=vram_bytes,
                   workspace_bytes=workspace_bytes,overlap_safe=False)
        models=resource_manager.residency()
        on_gpu=any(r['model_key']==model_key and (r.get('vram_bytes') or 0)>0 for r in models)
        # Ainda nos mesmos pesos da GPU: manter o degrau, mesmo com observação antiga.
        # Métrica incerta (logo após carregar) também mantém o último degrau: cair para
        # o perfil base força recarga; o lease ainda recusa GPU sem VRAM confirmada.
        fixed=resource_manager.fixed_offload()
        # 30/10 (33 camadas): no degrau de todas as camadas a isenção é provada pelo /api/ps; uma leitura feita durante
        # a carga anterior (modelo ainda parcial na placa) fazia a 2ª chamada esperar 120 s. Relê sempre (local, só leitura).
        full_step=bool(fixed) and fixed[0]==max(n for n,_ in resource_manager.offload_ladder_9b())
        if fixed and (full_step or any(r['model_key']==model_key and time.time()-r['observed_at']>15 for r in models)):
            # O lease conta os pesos residentes só com observação recente; sem isso o degrau
            # fixo já carregado parecia memória nova e esperava 120 s (27/10 19:56).
            resource_manager.refresh_executor_state(current)  # só leitura do daemon, sem unload
            models=resource_manager.residency()  # revisão Codex: a decisão usa a residência relida
        chosen=fixed or (_warm_offload.get(model_key) if on_gpu else None)
        uncertain=not fixed and bool(chosen) and model_key in _uncertain_offload
        if uncertain:
            # Sobe uma vez só quando a medição agora confiável comporta um degrau maior,
            # com a mesma margem; decisão por pressão medida continua sem upgrade.
            better=resource_manager.select_offload(probe,gpu_metrics.snapshot(),models)
            if better is not None:
                uncertain=False
                if better and better[0]>chosen[0]:chosen=better
        if chosen and not fixed:
            live=gpu_metrics.snapshot()
            decision=resource_manager.assess_gpu(dict(probe,vram_bytes=chosen[1]),live,models=models)
            if decision['reason'] in {'vram_pressure','estimate_exceeds_hard_limit'}:
                if any(r['model_key']==model_key and time.time()-r['observed_at']>15 for r in models):
                    resource_manager.refresh_executor_state(current)  # só leitura do daemon, sem unload
                    models=resource_manager.residency()
                    decision=resource_manager.assess_gpu(dict(probe,vram_bytes=chosen[1]),live,models=models)
                if decision['reason'] in {'vram_pressure','estimate_exceeds_hard_limit'}:
                    lower=resource_manager.select_offload(probe,live,models)
                    if lower and lower[0]<chosen[0]:chosen=lower  # mesma qualidade, só offload menor quando necessário
        if not chosen:
            chosen=resource_manager.select_offload(probe,gpu_metrics.snapshot(),models)
            # Residência velha (>15 s) não conta os próprios pesos: tudo parece pressão (27/10 19:41).
            if chosen is False and any(r['model_key']==model_key and time.time()-r['observed_at']>15 for r in models):
                resource_manager.refresh_executor_state(current)  # só leitura do daemon, sem unload
                models=resource_manager.residency()
                chosen=resource_manager.select_offload(probe,gpu_metrics.snapshot(),models)
            uncertain=chosen is None
            if chosen is None:chosen=_warm_offload.get(model_key)
        # Base do catálogo sem degrau medido: fica marcada para subir quando couber.
        if not chosen:uncertain=True
        if chosen:
            gpu_layers,vram_bytes=chosen
            diagnostics.emit('gpu.offload_selected',model=model,layers=gpu_layers,vram_bytes=vram_bytes,
                             context_preserved=True,margin_preserved=True,fixed=bool(fixed))
            if fixed and chosen==fixed:
                # O degrau fixo foi medido na placa já com KV e buffers (24K/32 camadas: +5,68 GiB
                # contra 5,8 orçados, 28/10). Somar 512 MiB de trabalho na carga a frio recusava a
                # GPU com o desktop acima de ~0,9 GiB; a margem do RM continua valendo.
                workspace_bytes=0
                full=max(n for n,_ in resource_manager.offload_ladder_9b())
                # Só PEDE a isenção; a prova (inteiro na placa, mesmo contexto) é feita a cada avaliação na fila.
                resident_full=gpu_layers==full
    if executor:
        if expected_latency is None: expected_latency = executor['expected_latency']
        if fallback_latency is None: fallback_latency = executor['fallback_latency']
    request = dict(owner=owner, model_key=model_key, vram_bytes=vram_bytes, workspace_bytes=workspace_bytes,
                   resident_full=resident_full, resident_ctx=config.NUM_CTX,
                   priority=(_priority.get() if owner=='llm' else resource_manager.PRIORITIES.get(owner,5)) if priority is None else priority,
                   expected_latency=(120 if owner=='image' else 15) if expected_latency is None else expected_latency,
                   fallback_latency=(600 if owner=='image' else 120) if fallback_latency is None else fallback_latency,
                   use_model_estimate=automatic_estimate)
    request.update(queue_started_monotonic=time.monotonic(),wait_budget_seconds=wait)
    flexible_min = min(4*gpu_metrics.GIB,vram_bytes) if owner=='image' else None
    if flexible_min is not None: request['flexible_min_bytes']=flexible_min
    scope = _request.set(request)
    try:
        with resource_manager.compute_lease(owner, entity=config.ENTIDADE_ID, model_key=model_key,
                vram_bytes=vram_bytes, workspace_bytes=workspace_bytes, priority=request['priority'],
                expected_latency=request['expected_latency'], fallback_latency=request['fallback_latency'],
                overlap_safe=owner in {'llm','vision','audio','spontaneous','batch'},resident_full=resident_full,
                resident_ctx=config.NUM_CTX,
                cpu_fallback=cpu_fallback, cpu_ram_bytes=vram_bytes+4*gpu_metrics.GIB, wait=wait, cancel=cancel,
                prepare=lambda: prepare_residency(owner), cancel_supported=owner=='image',
                flexible_min_bytes=flexible_min,use_model_estimate=automatic_estimate,
                opportunistic=opportunistic) as acquired:
            if acquired['backend']=='gpu' and executor and executor.get('gpu_profile') and owner in {'llm','vision'}:
                # Só um perfil admitido pode ser reutilizado como quente. Um
                # candidato recusado não foi aplicado; o fallback base também
                # precisa ficar registrado quando a métrica inicial era incerta.
                _warm_offload[model_key]=(gpu_layers,vram_bytes)
                (_uncertain_offload.add if uncertain else _uncertain_offload.discard)(model_key)
                acquired = dict(acquired, gpu_layers=gpu_layers,
                                gpu_profile=executor['gpu_profile']+(f'_layers{gpu_layers}' if gpu_layers!=executor['gpu_layers'] else ''))
            yield acquired
        if model_key:
            try:
                with contextlib.closing(resource_manager._conn()) as conn, conn:
                    conn.execute('UPDATE gpu_residency SET last_used=? WHERE model_key=?', (time.time(),model_key))
            except (sqlite3.Error,OSError) as exc:
                diagnostics.persistence_failure('gpu.mark_model_used',resource_manager.DB_PATH,exc,retry_safe=True,model_key=model_key)
    finally:
        _request.reset(scope)
