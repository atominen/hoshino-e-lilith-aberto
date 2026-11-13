"""Inventário compartilhado de recursos da máquina.

O lock continua sendo o mecanismo de exclusão; este módulo acrescenta uma
trilha consultável de quem possui cada recurso, expiração de leases abandonados
e limites explícitos para o launcher. Nenhum estado mental é gravado aqui.
"""
from __future__ import annotations

import contextlib
import asyncio
import json
import os
import sqlite3
import time
import threading
import uuid
import functools
import hashlib
import inspect
import re
import unicodedata
import math
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import config
from core.sqlite_runtime import open_initialized
from core import gpu_metrics, diagnostics
from core import resource_profiles


ROOT = Path(config.SHARED_RUNTIME_DIR)
DB_PATH = ROOT / "resource_manager.sqlite3"
LOCK_DIR = ROOT / "resource_locks"
DEFAULT_TTL = 90.0
_inference_cycle = ContextVar('resource_inference_cycle', default=None)
_profile_controller = resource_profiles.Controller()
HOSHINO_9B = 'hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M'
OFFLOAD_9B_MANIFEST = '31b81956cc3fb4be766ad25d6a86d097bb853a87047a68751042952b74817995'
LILITH_9B = 'lilith-qwen3.5-9b:latest'
LILITH_9B_MANIFEST = '0f598c655b9866074344bfdf04f2baefd491146fcb4dd175b40a681a5c483096'
HUNYUAN_SOURCE = 'bartowski/tencent_Hunyuan-7B-Instruct-GGUF'
HUNYUAN_REV = 'f904d96e244a51562e80925489bc393c319f231d'
HUNYUAN_SHA = '37361ed44b126de00a551260fd7c3de3c3a7a58d6060bce99b6b8fe0c0665d63'
JAN_SOURCE = 'mradermacher/Qwen3-Jan-v1-256k-ctx-6B-Brainstorm20x-GGUF'
JAN_REV = '8c4b5e5b13b179aa6219a2cd4ae8f08f8a6e0b7c'
JAN_SHA = 'de4a21839013515909959112d67a5cda31e99a5b3e89a6b4df95376907cc7c3f'
ESPER_SOURCE = 'mradermacher/Qwen3-Esper3-Reasoning-Instruct-6B-Brainstorm20x-Enhanced-E32-GGUF'
ESPER_REV = 'ccb09bc46f7b7df8d5794a622e258bd7140dd877'
ESPER_SHA = 'c6e8b85ffd17184ec44103c2ee2348203fd5f8ccb63fc87750173c71ca873d72'


@dataclass(frozen=True)
class ExecutorChoice:
    model: str
    tier: str
    reason: str
    num_ctx: int
    vram_bytes: int
    expected_latency: float
    fallback_latency: float
    output_max: int = 0
    supports_tools: bool = True
    supports_thinking: bool = True
    supports_format: bool = True
    fixed_window: bool = False  # perfil GPU medido já reserva a janela inteira


def executor_output_limit(executor, configured):
    """Mesmo limite na elegibilidade e no HTTP; Yi não reserva4k de saída."""
    tier = executor.get('tier') if isinstance(executor, dict) else executor.tier
    cap = executor.get('output_max', 0) if isinstance(executor, dict) else getattr(executor,'output_max',0)
    if tier == 'light': cap = min(cap or 1024, 1024)
    output = configured if configured > 0 else 4096
    return min(output, cap) if cap else output


def context_requirement(messages, tools=None, *, output_max):
    """Mesma estimativa para selecionar executor e dimensionar sua janela."""
    if type(output_max) is not int or output_max <= 0:
        raise ValueError('Saída deve possuir limite positivo')
    wire = json.dumps(messages, ensure_ascii=False, separators=(',', ':'))
    if tools:
        wire += json.dumps(tools, ensure_ascii=False, separators=(',', ':'))
    estimated = math.ceil(len(wire) / min(config.CHARS_POR_TOKEN, 3.0)) + 12 * len(messages)
    return estimated, estimated + max(256, math.ceil(estimated * .15)) + output_max


def inference_options(messages, tools=None, *, context_max, output_max, reasoning=False, fixed_window=False):
    """Dimensiona a janela antes do HTTP, sem cortar mensagens ou trocar executor.

    É uma estimativa conservadora, não um tokenizer exato. Inclui argumentos,
    schemas, autoria e folga de template; excesso falha antes da inferência.
    Limites fixos continuam disponíveis para instalações com adaptação desligada.
    """
    if type(context_max) is not int or context_max < 512:
        raise ValueError('Teto de contexto inválido')
    estimated, required = context_requirement(messages, tools, output_max=output_max)
    # Imagem não tem equivalência confiável em caracteres: mantém a janela cheia.
    has_images = any(m.get('images') for m in messages)
    output = output_max  # não diminui qualidade/saída para caber silenciosamente
    if required > context_max and not has_images:
        diagnostics.emit('executor.context_overflow', level='WARNING',
                         estimated_tokens=estimated, required_tokens=required,
                         context_max=context_max, messages_removed=0,
                         message_sizes=[{'role':m.get('role'), 'chars':len(str(m.get('content','')))}
                                        for m in messages], tool_count=len(tools or []),
                         tool_chars=len(json.dumps(tools or [],ensure_ascii=False)))
        raise ValueError('Contexto excede o teto seguro; compactação existente necessária. Nenhuma mensagem foi cortada.')
    # Janela variável faz o Ollama recarregar o modelo; o perfil GPU medido já a reserva.
    adaptive = bool(config.ADAPTIVE_CONTEXT) and not has_images and not fixed_window
    buckets = sorted({2048, 4096, 8192, 12288, 16384, 32768, context_max})
    chosen = next((n for n in buckets if required <= n <= context_max), context_max) if adaptive else context_max
    diagnostics.emit('executor.context_selected', context_max=context_max, context_tokens=chosen,
                     estimated_tokens=estimated, output_tokens=output, adaptive=adaptive,
                     messages_removed=0)
    return {'num_ctx': chosen, 'num_predict': output}


def local_model_installed(model, storage=None):
    """Consulta o catálogo local, sem rede, carga de pesos ou dados mentais."""
    try:
        name, tag = model.rsplit(':', 1) if ':' in model else (model, 'latest')
        parts = name.split('/')
        if len(parts) == 1:
            parts = ['registry.ollama.ai', 'library', *parts]
        elif len(parts) == 2:
            parts = ['registry.ollama.ai', *parts]
        if any(not re.fullmatch(r'[\w.-]+', p) or p in {'.', '..'} for p in [*parts, tag]):
            return False
        root = Path(storage or config.OLLAMA_MODELS_DIR)
        manifest = json.loads((root/'manifests'/Path(*parts)/tag).read_text())
        blobs = [manifest['config'], *manifest['layers']]
        return bool(blobs) and all(
            re.fullmatch(r'sha256:[a-f0-9]{64}', blob['digest']) and
            (root/'blobs'/blob['digest'].replace(':', '-')).stat().st_size == blob['size']
            for blob in blobs)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _validated_primary_gpu(data):
    """Perfil medido na RX 6650 XT; não altera pesos/contexto nem a margem.

    A validação se liga ao manifesto testado. Outras variantes/janelas precisam
    de seu próprio ensaio; configuração inválida conserva o fallback antigo.
    """
    row = data.get('primary_gpu')
    if row is None:
        return None
    if not isinstance(row, dict):
        raise ValueError('Perfil GPU deve ser um objeto')
    approved = {'hoshino':(HOSHINO_9B,OFFLOAD_9B_MANIFEST,
                           'manifests/hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF/Q4_K_M'),
                'lilith':(LILITH_9B,LILITH_9B_MANIFEST,
                          'manifests/registry.ollama.ai/library/lilith-qwen3.5-9b/latest')}
    model,digest,relative=approved.get(config.ENTIDADE_ID,('','',''))
    if (config.MODEL_NAME != model or row.get('model') != model or row.get('manifest_sha256') != digest or
            row.get('validated') is not True or type(row.get('num_gpu')) is not int or row['num_gpu'] not in {20,32} or
            type(row.get('context_max')) is not int or row['context_max'] not in PROFILE_9B_GIB or
            config.NUM_CTX > row['context_max'] or
            type(row.get('vram_bytes')) is not int or row['vram_bytes'] != int(PROFILE_9B_GIB[row['context_max']]*gpu_metrics.GIB)):
        raise ValueError('Perfil GPU não corresponde ao ensaio físico aprovado')
    path = Path(config.OLLAMA_MODELS_DIR)/relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Manifesto mudou; perfil GPU exige novo ensaio')
    return row


# Qwen3.5-9B Q4_K_M, 16K, RX 6650 XT (26/10/2026): VRAM medida por camadas na GPU,
# incluindo buffers. 32 coincide com o perfil 5,5 GiB e 20 com o de 4,25 GiB.
OFFLOAD_LADDER_9B=((33,6.75),(32,5.5),(31,5.35),(30,5.2),(28,4.9),(26,4.65),(20,4.25))
# Pedidos humanos 28/10: 32K, depois 24K. Medido na placa com 32 camadas: 16K→24K custa
# +0,26 GiB e 16K→32K +0,38 GiB (só 8 de 32 blocos têm atenção completa).
PROFILE_9B_GIB={16384:5.5,24576:5.8,32768:5.9}
CONTEXT_EXTRA_GIB={16384:0,24576:0.3,32768:0.4}
# 30/10: com as 33 camadas na placa o acréscimo de contexto medido é bem menor (medicao-9b-contexto.md, 28/10).
CONTEXT_EXTRA_33_GIB={16384:0,24576:0.08,32768:0.12}


def context_extra_gib(context=None):
    """Acréscimo do menor contexto medido que comporta NUM_CTX (ou o contexto dado); acima de 32K não há medida."""
    context=config.NUM_CTX if context is None else context
    return next((gib for ctx,gib in sorted(CONTEXT_EXTRA_GIB.items()) if context<=ctx),None)


def offload_ladder_9b(context=None):
    """Degraus medidos com o acréscimo do contexto; a Central passa o contexto de cada entidade."""
    context=config.NUM_CTX if context is None else context
    extra=context_extra_gib(context) or 0
    full=next((gib for ctx,gib in sorted(CONTEXT_EXTRA_33_GIB.items()) if context<=ctx),extra)
    return tuple((n,gib+(full if n==33 else extra)) for n,gib in OFFLOAD_LADDER_9B)
_MEMORY_REASONS={'vram_pressure','estimate_exceeds_hard_limit'}


def fixed_offload():
    """Degrau fixo escolhido pelo humano em executores.json (gpu_layers_fixed), se medido.

    27/10: pedido humano de camada fixa na GPU; a escada dinâmica caía para 20
    camadas sem necessidade. Só degraus da escada medida são aceitos.
    """
    try:data=json.loads((Path(config.ENTITY_CONFIG_DIR)/'executores.json').read_text())
    except (OSError,ValueError):return None
    layers=data.get('gpu_layers_fixed') if isinstance(data,dict) else None
    return next(((n,int(gib*gpu_metrics.GIB)) for n,gib in offload_ladder_9b() if type(layers) is int and n==layers),None)


def select_offload(probe, metrics, models=()):
    """Maior degrau medido que cabe na VRAM livre agora, com a mesma margem.

    Só a conta de memória decide o degrau; compute ocupado continua sendo
    decisão do lease. Pesos residentes já contam na VRAM usada, então o modelo
    carregado não sobe nem recarrega sem espaço real. None = métrica incerta;
    False = nenhum degrau cabe (pressão real de VRAM).
    """
    memory=dict(metrics,utilization=None)
    for layers,gib in offload_ladder_9b():
        budget=int(gib*gpu_metrics.GIB)
        decision=assess_gpu(dict(probe,vram_bytes=budget),memory,models=models)
        if decision['allowed']:return layers,budget
        if decision['reason'] not in _MEMORY_REASONS:return None
    return False


def executor_catalog():
    """Catálogo aprovado por entidade; terceiro conversacional é opt-in validado.

    Preserva instalações anteriores com apenas principal/leve. Nenhum download
    ou escolha de checkpoint arbitrário ao ler configuração.
    """
    principal = dict(model=config.MODEL_NAME, tier='principal', num_ctx=config.NUM_CTX,
                     vram_bytes=6*gpu_metrics.GIB, expected_latency=15, fallback_latency=120)
    result = [principal]
    try:
        measured=_recovered_gpu_profile()
        if measured:
            principal.update(vram_bytes=measured['vram_bytes'],gpu_layers=measured['num_gpu'],
                gpu_profile='rx6650xt_recovered_'+measured.get('model_id','9b'),
                supports_tools=measured.get('supports_tools',True))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        diagnostics.exception('executor.gpu_profile_invalid',exc)
    if config.ENTIDADE_ID not in {'hoshino', 'lilith'}:
        return result
    try:
        data = json.loads((Path(config.ENTITY_CONFIG_DIR)/'executores.json').read_text())
        if not isinstance(data, dict):
            raise ValueError('Catálogo deve ser um objeto')
        try:
            gpu = _recovered_gpu_profile() or _validated_primary_gpu(data)
            if gpu:
                principal.update(vram_bytes=gpu['vram_bytes'], gpu_layers=gpu['num_gpu'],
                                 gpu_profile=f"rx6650xt_{gpu.get('model_id','9b')}_ctx{gpu['context_max']}_layers{gpu['num_gpu']}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            diagnostics.exception('executor.gpu_profile_invalid', exc)
        light = data.get('light')
        if light is None:
            # 05/11 (pedido humano): Hoshino e Lilith sem executor leve; tudo vai para o principal.
            return result
        approved = config.ENTIDADE_ID+'-qwen2.5-7b:latest'
        hunyuan = (light.get('model') == config.ENTIDADE_ID+'-hunyuan-7b:latest' and
                   light.get('source') == HUNYUAN_SOURCE and light.get('revision') == HUNYUAN_REV and
                   light.get('source_sha256') == HUNYUAN_SHA and light.get('conversation_validated') is True)
        legacy = light.get('model') == approved and light.get('source') == 'qwen2.5:7b-instruct-q4_K_M'
        qwen4 = (light.get('model') == config.ENTIDADE_ID+'-qwen3.5-4b:latest' and
                 light.get('source') == 'Qwen3.5-4B-local-original')
        if (data.get('schema') != 1 or data.get('scope_frozen') is not True or not (legacy or hunyuan or qwen4)):
            raise ValueError('Catálogo fora do escopo congelado')
        # Parâmetros conhecidos, não estimativas arbitrárias de um arquivo editado.
        from core.neural9b_modes import runtime_alias
        selected_light=runtime_alias(config.RAIZ,config.ENTIDADE_ID,'qwen35-4b' if qwen4 else 'qwen25-7b') if legacy or qwen4 else None
        result.append(dict(model=selected_light or light['model'], tier='light', num_ctx=8192,
                           vram_bytes=(4 if qwen4 else 5)*gpu_metrics.GIB, expected_latency=10, fallback_latency=85,
                           supports_tools=light.get('supports_tools', True) if hunyuan else True))
        if qwen4:result[-1]['gpu_layers']=-1
        companion = data.get('companion')
        if companion is not None:
            if not isinstance(companion, dict):
                raise ValueError('Terceiro executor deve ser um objeto')
            if companion.get('model') == config.ENTIDADE_ID+'-yi-6b:latest':
                from core.yi_companion import candidate
                yi = candidate(config.RAIZ, config.ENTIDADE_ID, companion)
                if yi:
                    if yi['model'] == principal['model']:
                        principal.update({k:v for k,v in yi.items() if k not in {'tier','enabled'}})
                    else: result.append(yi)
                return result
            jan = (companion.get('model') == config.ENTIDADE_ID+'-qwenjan-6b:latest' and
                   companion.get('source') == JAN_SOURCE and companion.get('revision') == JAN_REV and
                   companion.get('source_sha256') == JAN_SHA)
            esper = (companion.get('model') == config.ENTIDADE_ID+'-esper3-6b:latest' and
                     companion.get('source') == ESPER_SOURCE and companion.get('revision') == ESPER_REV and
                     companion.get('source_sha256') == ESPER_SHA)
            alias = config.ENTIDADE_ID+('-esper3-6b:latest' if esper else
                                        '-qwenjan-6b:latest' if jan else '-qwen3.5-4b:latest')
            legacy_companion = (companion.get('model') == alias and
                    companion.get('source') == 'unsloth/Qwen3.5-4B-GGUF' and
                    companion.get('revision') == 'e87f176479d0855a907a41277aca2f8ee7a09523')
            if (not (jan or esper or legacy_companion) or
                    type(companion.get('enabled')) is not bool or
                    type(companion.get('conversation_validated')) is not bool):
                raise ValueError('Terceiro executor fora do contrato aprovado')
            result.append(dict(model=alias, tier='companion', num_ctx=16384,
                               vram_bytes=(6 if jan or esper else 4)*gpu_metrics.GIB, expected_latency=10, fallback_latency=85,
                               supports_tools=companion.get('supports_tools', True),
                               enabled=companion['enabled'] and companion['conversation_validated']))
    except FileNotFoundError:
        pass  # Instalação antiga continua executando o principal.
    except (OSError, ValueError, KeyError, TypeError) as exc:
        diagnostics.exception('executor.catalog_invalid', exc)
    return result


def _recovered_gpu_profile():
    """Nova importação exige recibo/probe próprios; nunca reutiliza hash antigo."""
    if config.ENTIDADE_ID not in {'hoshino','lilith','alistair'}:return None
    from laboratorio.recuperacao_modelos import active_receipt,version_receipt
    from core.neural9b_modes import selected_version,primary_family
    root=Path(config.RAIZ);home=Path(os.environ.get('HOSHINO_LAB_HOME') or root/'laboratorio-local')
    model=primary_family(root,config.ENTIDADE_ID) or ('alistair-4b' if config.ENTIDADE_ID=='alistair' else 'qwen35-9b')
    context,layers,minimum={'qwen35-9b':(16384,20,4.25),'qwen25-7b':(8192,-1,5),
                            'yi-6b':(4096,-1,5),'qwen35-4b':(8192,-1,4),'alistair-4b':(8192,-1,4)}[model]
    extra=0
    if model=='qwen35-9b' and context<config.NUM_CTX<=32768:
        extra=int(context_extra_gib()*gpu_metrics.GIB)  # 24K/32K medidos 28/10 sobre o mesmo recibo de 16K
    elif config.NUM_CTX>context:return None
    row=active_receipt(home,root,config.ENTIDADE_ID,model)
    selected=selected_version(root,config.ENTIDADE_ID,model)
    if selected and selected['alias']==config.MODEL_NAME and selected['kind']!='original':
        row=version_receipt(home,root,config.ENTIDADE_ID,model,selected['source_sha256'])
    elif (selected and selected['alias']==config.MODEL_NAME and row and row.get('source_kind')=='original' and
          row['manifest_sha256']==selected['manifest_sha256']):
        # Cópia imutável dos mesmos pesos/parametrização já ensaiados.
        row=dict(row,alias=selected['alias'])
    if not row or row['alias']!=config.MODEL_NAME:return None
    probe=row.get('probe',{});metrics=probe.get('metrics',{})
    if (probe.get('done') is not True or probe.get('backend')!='gpu' or probe.get('layers')!=layers or
        probe.get('context')!=context or probe.get('unload_confirmed') is not True or probe.get('pressure') or
        type(probe.get('vram_budget_bytes')) is not int or probe['vram_budget_bytes']<int(minimum*gpu_metrics.GIB) or
        not metrics.get('known') or not metrics.get('stable') or
        type(probe.get('resident_vram_bytes')) is not int or probe['resident_vram_bytes']<=0):return None
    quantum=256*1024**2
    budget=max(probe['vram_budget_bytes'],math.ceil(probe['resident_vram_bytes']/quantum)*quantum)+extra
    return {'num_gpu':layers,'vram_bytes':budget,'context_max':max(context,config.NUM_CTX),'model':row['alias'],'model_id':model,
            'supports_tools':'tools' in row['capabilities'] if 'capabilities' in row else True,
            'manifest_sha256':row['manifest_sha256'],'validated':True}


def model_state(row, *, now=None):
    """Estado observado, não promessa de que os pesos estão carregados."""
    now = time.time() if now is None else now
    if not row:
        return 'unloaded'
    if abs(now-row.get('observed_at', 0)) > 15 or row.get('vram_bytes') is None:
        return 'unknown'
    return 'gpu_resident' if row['vram_bytes'] > 0 else 'ram_resident'


def assess_executor(candidates, *, complexity, priority, state, ram, context_tokens=0, companion_allowed=False,
                    profile=None):
    """Seleção pura antes de gerar: qualidade é restrição, não só um custo."""
    primary = candidates[0]
    light = next((c for c in candidates if c['tier']=='light' and c.get('installed')), None)
    companion = next((c for c in candidates if c['tier']=='companion' and c.get('installed')
                      and c.get('enabled') and companion_allowed), None)
    # O terceiro não substitui 7B em triagem/código nem 9B em tarefas críticas.
    # Entram no custo somente executores cuja janela comporta o contexto inteiro.
    small = [c for c in (light, companion) if c and
             c.get('required_context_tokens', context_tokens+1024) <= c['num_ctx']]
    chosen, reason = primary, 'quality_required'
    scores = {}
    # None conserva exatamente o custo anterior, inclusive na reversão por env.
    preset = resource_profiles.PROFILES.get(profile)
    if complexity == 'simple' and small:
        metrics, policy = state['metrics'], state['policy']
        busy = bool(state.get('compute')) or (metrics.get('utilization') or 0) > policy['max_utilization']
        queue = len(state.get('queue', []))
        for candidate in [primary, *small]:
            key = candidate['model_key']
            row = next((r for r in state.get('residency', []) if r['model_key']==key), None)
            residence = model_state(row)
            request = dict(owner='llm', model_key=key, vram_bytes=candidate['vram_bytes'],
                           workspace_bytes=512*1024**2, overlap_safe=False)
            fits = assess_gpu(request, metrics, models=state.get('residency', []), policy=policy)['allowed']
            cpu_ok = ram is not None and ram >= candidate['vram_bytes']+4*gpu_metrics.GIB+policy['ram_margin_bytes']
            reload_cost = row['reload_seconds'] if row else 12
            cost = candidate['expected_latency'] if fits and not busy else candidate['fallback_latency']
            if residence != 'gpu_resident': cost += reload_cost * (preset.reload_weight if preset else 1)
            if not cpu_ok and (not fits or busy): cost += 10000
            if priority <= 1: cost += queue * candidate['expected_latency'] * (preset.queue_weight if preset else 1)
            if preset: cost += candidate['vram_bytes']/gpu_metrics.GIB * preset.reservation_weight
            if residence == 'gpu_resident' and row and time.time()-row['last_used'] < policy['sticky_seconds']:
                cost -= min(reload_cost, 10) * (preset.hot_bonus if preset else 1)  # jamais vence qualidade
            scores[candidate['tier']] = max(0, cost)
        chosen = min([primary, *small], key=lambda c: scores[c['tier']])
        reason = 'simple_resource_cost' if chosen is not primary else ('principal_resource_cost' if preset else 'hot_principal_cheaper')
    elif complexity == 'simple':
        reason = 'light_unavailable' if not light else 'light_context_limit'
    return ExecutorChoice(chosen['model'], chosen['tier'], reason, chosen['num_ctx'],
                          chosen['vram_bytes'], chosen['expected_latency'], chosen['fallback_latency'],
                          chosen.get('output_max', 0), chosen.get('supports_tools', True),
                          chosen.get('supports_thinking', True), chosen.get('supports_format', True),
                          bool(chosen.get('gpu_profile'))), scores


def inference_cycle(purpose='conversation', *, inherit=True):
    """Escopo por tarefa assíncrona; retries/ferramentas conservam o executor.

    Escolha é lazy no primeiro ciclo de inferência, já com o contexto real.
    Não altera config global, identidade, memória, relações ou estado.
    """
    def decorate(fn):
        signature = inspect.signature(fn)
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            parent = _inference_cycle.get()
            if inherit and parent is not None and parent.get('task_owner') is asyncio.current_task():
                return await fn(*args, **kwargs)
            bound = signature.bind(*args, **kwargs).arguments
            input_text = bound.get('ultima_entrada', bound.get('entrada'))
            if input_text is None and purpose == 'internal_small':
                input_text = getattr(bound.get('self'), 'ultima_entrada', None)
            cycle = dict(purpose=purpose, choice=None, task_owner=asyncio.current_task(),
                         task=bool(bound.get('tarefa_turno') or bound.get('modo_operacao') in {'tarefa', 'autonomo_objetivo'} or
                                   (bound.get('intencao') or {}).get('tipo') in {'retomar_objetivo','investigar','refletir'}),
                         spontaneous=bound.get('prompt_interno') is not None or bound.get('modo_operacao')=='autonomo',
                         input=input_text)
            token = _inference_cycle.set(cycle)
            try:
                return await fn(*args, **kwargs)
            finally:
                _inference_cycle.reset(token)
        return wrapper
    return decorate


def choose_executor(messages, *, priority=1, purpose=None, tools=None, structured=False):
    cycle = _inference_cycle.get()
    try: task = asyncio.current_task()
    except RuntimeError: task = None
    if cycle and cycle.get('task_owner') is not task:
        cycle = None  # Filho sem wrapper também não herda a escolha do pai.
    if cycle and cycle['choice'] is not None:
        if (tools and not cycle['choice'].supports_tools) or (structured and not cycle['choice'].supports_format):
            raise ValueError('Contrato mudou no meio da resposta: executor não suporta ferramentas/formato. Sem troca silenciosa.')
        return cycle['choice']
    purpose = purpose or (cycle['purpose'] if cycle else 'conversation')
    last = next((str(m.get('content', '')) for m in reversed(messages) if m.get('role')=='user'), '')
    text = str(cycle['input']) if cycle and cycle['input'] is not None else last
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    complex_terms = r'\b(decisao|decidir|importante|complexo|profund[oa]|suicid\w*|saude|medic\w*|jurid\w*|invest\w*|codigo|program\w*|planej\w*|analise|explique|compare|execute|apague|exclua)\b'
    routine = bool(re.fullmatch(r'\s*(oi|ola|bom dia|boa tarde|boa noite|obrigad[oa]|como (voce|vc) (esta|ta)|tudo bem|que horas sao|que dia e hoje|ate mais)[!?.\s]*', normalized))
    routine = routine or (len(text)<=600 and bool(re.match(
        r'^\s*(traduza|traduz|reformule|classifique|conte uma piada|imite|resuma este texto|corrija a gramatica)\b', normalized)))
    simple = (routine or purpose in {'triage', 'internal_small'} or (cycle and cycle['spontaneous']))
    if (purpose in {'reflection', 'deep_reflection', 'task', 'compaction'} or (cycle and cycle['task']) or
            re.search(complex_terms, normalized) or len(text)>1200 or any(m.get('images') for m in messages)):
        simple = False
    # Pedido operacional curto ainda exige qualidade; interpretador existente.
    from core import intent, capabilities
    parsed = intent.interpretar(text)
    if parsed.confianca >= .85 and parsed.ferramenta_principal:
        meta = capabilities.info(parsed.ferramenta_principal)
        if meta.mutates or meta.requires_verification:
            simple = False
    candidates = executor_catalog()
    endpoint = config.OLLAMA_URL.rsplit('/api/', 1)[0]
    refresh_executor_state(endpoint)
    for item in candidates:
        item['model_key'] = endpoint+'|'+item['model']
        item['installed'] = local_model_installed(item['model']) and (
            not tools or item.get('supports_tools', True)) and (
            not structured or item.get('supports_format', True)) and (
            item.get('supports_tools', True) or not any(m.get('role')=='tool' or m.get('tool_calls') for m in messages))
        output = executor_output_limit(item, config.NUM_PREDICT)
        _, item['required_context_tokens'] = context_requirement(messages, tools, output_max=output)
    tokens, _ = context_requirement(messages, tools, output_max=1)
    state, ram = gpu_state(), gpu_metrics.ram_available()
    profile = (_profile_controller.choose(complexity='simple' if simple else 'complex', priority=priority,
                   entity=config.ENTIDADE_ID, state=state, ram=ram)
               if config.DYNAMIC_RESOURCE_PROFILES else None)
    choice, scores = assess_executor(candidates, complexity='simple' if simple else 'complex',
                                    priority=priority, state=state, ram=ram, context_tokens=tokens,
                                    companion_allowed=purpose=='conversation' and not (cycle and cycle['task']),
                                    profile=profile['id'] if profile else None)
    diagnostics.emit('executor.selected', entity=config.ENTIDADE_ID, model=choice.model, tier=choice.tier,
                     reason=choice.reason, complexity='simple' if simple else 'complex', priority=priority,
                     predicted_cost_seconds=scores, cost_basis='heuristic_not_benchmark', context_tokens=int(tokens),
                     resource_profile={k:v for k,v in profile.items() if k!='since'} if profile else None)
    if cycle: cycle['choice'] = choice
    return choice


def amostragem(think: bool) -> dict:
    """Opções de sorteio das palavras para as respostas da entidade (``config.AMOSTRAGEM``)."""
    if getattr(config, 'AMOSTRAGEM', 'qwen') != 'qwen':
        return {}
    return ({'temperature': 0.6, 'top_p': 0.95, 'top_k': 20} if think
            else {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20})


# 07/11: pergunta de fato (o que é, quem, quanto, qual, quando, lembra...) com raciocínio, para conferir antes de afirmar.
_PERGUNTA_DE_FATO = re.compile(
    r'\b(?:o que (?:e|foi|significa)|quem (?:e|foi|criou|escreveu|fez|inventou)|quant[oa]s?|qual|quais|quando|onde|'
    r'lembra\w*|como (?:se chama|eu me chamo)|meu nome|minha placa|meu pc|meu computador|processador|memoria ram|\bram\b)\b')


def thinking_for_cycle(messages):
    """Política do executor, não pensamento/persona: conversa comum sem think.

    Usa a entrada real, não palavras presentes na identidade ou nos exemplos do
    system prompt. Fixa a decisão no ciclo atual; não muda o modelo escolhido.
    Chamadas internas ainda podem forçar think=False (planner/JSON/retry).
    """
    cycle = _inference_cycle.get()
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    if cycle and cycle.get('task_owner') is not task:
        cycle = None
    if cycle and 'thinking_choice' in cycle:
        return cycle['thinking_choice']
    purpose = cycle['purpose'] if cycle else 'conversation'
    last = next((str(m.get('content', '')) for m in reversed(messages) if m.get('role') == 'user'), '')
    text = str(cycle['input']) if cycle and cycle['input'] is not None else last
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    philosophical_question = bool(
        re.search(r'\b(?:quest(?:ao|oes)|perguntas?|dilemas?|reflex(?:ao|oes))\b.{0,80}'
                  r'\b(?:filosof\w*|existenc\w*)\b', normalized)
        or (re.search(r'\b(?:identidade|existencia|consciencia|sentimentos)\b', normalized)
            and re.search(r'\b(?:motivos|provar|continuar sendo)\b', normalized)
            and ('?' in text or re.search(r'\b(?:de onde|por que|como|o que)\b', normalized))))
    sobre_ela = bool(re.search(r'\b(?:seu|sua|seus|suas)\b', normalized)
                     and not re.search(r'\b(?:meu|minha|meus|minhas|eu)\b', normalized))  # "qual é seu nome?"
    # Só pergunta de pessoa: o texto interno do despertar/iniciativa tem "quando", "qual", "onde" (07/11, teste de uso).
    espontaneo = bool(cycle and cycle.get('spontaneous'))
    factual_question = bool(getattr(config, 'RACIOCINIO_EM_FATOS', False) and purpose == 'conversation'
                            and not espontaneo and len(text) <= 600 and not sobre_ela
                            and _PERGUNTA_DE_FATO.search(normalized))
    # 12/11 (medição em runtime/ensaios/acao-minecraft-20261112): em pedido de ação ("conecte", "abre", "cria") os
    # pesos treinados anunciavam "vou conectar" e não chamavam a ferramenta; com raciocínio, 4 de 5 já chamam no
    # primeiro passo (0 de 5 sem). Custa alguns segundos só nesses turnos.
    action_request = False
    if purpose == 'conversation' and not espontaneo and len(text) <= 600:
        from core import conferencia
        action_request = conferencia.pede_acao(text)
    needs_reasoning = (purpose in {'reflection', 'deep_reflection', 'task', 'compaction'}
                      or factual_question or action_request
                      or bool(cycle and cycle['task'])
                      or philosophical_question
                      or len(text) > 1200
                      or bool(re.search(
                          r'\b(?:analise|compare|calcule|demonstre|prove|investigue|depure|debug|'
                          r'decisao|decidir|planej\w*|complex\w*|codigo|program\w*|'
                          r'conflito|contradicao|reflita|refletir|riscos?|saude|medic\w*|suicid\w*|'
                          r'jurid\w*|financ\w*|apague|exclua|remova)\b', normalized)))
    enabled = bool(config.THINKING and needs_reasoning)
    reason = ('disabled_by_config' if not config.THINKING else 'factual_question' if enabled and factual_question
              else 'action_request' if enabled and action_request
              else 'reasoning_required' if enabled else 'routine_conversation')
    diagnostics.emit('executor.thinking_selected', entity=config.ENTIDADE_ID,
                     enabled=enabled, reason=reason, purpose=purpose)
    if cycle:
        cycle['thinking_choice'] = enabled
    return enabled


def refresh_executor_state(endpoint):
    """Atualiza apenas o daemon da entidade; nunca carrega ou descarrega pesos."""
    if endpoint not in {f'http://127.0.0.1:{p}' for p in (11435, 11436, 11437)}:
        return False
    import requests
    try:
        response = requests.get(endpoint+'/api/ps', timeout=(.3, 1))
        response.raise_for_status()
        models = response.json()['models']
        observed = set()
        for model in models:
            name = model.get('name') or model.get('model')
            if not name: continue
            observed.add(name)
            observe_model(endpoint, name, model.get('size_vram'))
            size = max(model.get('size') or 0, model.get('size_vram') or 0)
            if size: record_memory_estimate(endpoint, name, size)
            if model.get('context_length'): record_model_context(endpoint, name, model['context_length'])
        for old in residency():
            if old['endpoint']==endpoint and old['model'] not in observed:
                forget_model(endpoint, old['model'])
        return True
    except (requests.RequestException, OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        diagnostics.exception('executor.residency_unknown', exc)
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    conn = open_initialized(DB_PATH,
        "CREATE TABLE IF NOT EXISTS leases (token TEXT PRIMARY KEY, resource TEXT NOT NULL, "
        "owner TEXT NOT NULL, entity TEXT NOT NULL, pid INTEGER NOT NULL, acquired_at TEXT NOT NULL, "
        "heartbeat REAL NOT NULL, expires_at REAL NOT NULL);"
        "CREATE INDEX IF NOT EXISTS idx_leases_resource ON leases(resource);"
        "CREATE TABLE IF NOT EXISTS gpu_requests (token TEXT PRIMARY KEY, priority INTEGER NOT NULL, "
        "enqueued_at REAL NOT NULL, state TEXT NOT NULL, request TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS gpu_residency (model_key TEXT PRIMARY KEY, model TEXT NOT NULL, "
        "endpoint TEXT NOT NULL, vram_bytes INTEGER, observed_at REAL NOT NULL, last_used REAL NOT NULL, "
        "reload_seconds REAL NOT NULL);"
        "CREATE TABLE IF NOT EXISTS gpu_meta (name TEXT PRIMARY KEY, value REAL NOT NULL);", timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _limpar_stale(conn: sqlite3.Connection) -> None:
    # Tempo sozinho nunca libera um job longo. O kernel decide se o dono
    # ainda tem o lock; isso também lida com PID reaproveitado após um crash.
    import fcntl
    expirados = []
    for row in conn.execute("SELECT token,resource FROM leases").fetchall():
        managed = conn.execute('SELECT 1 FROM gpu_requests WHERE token=?', (row['token'],)).fetchone()
        path = _lock_path('token-' + row['token']) if managed else _lock_path(row['resource'])
        with path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            expirados.append(row["token"])
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if expirados:
        conn.executemany("DELETE FROM leases WHERE token=?", [(token,) for token in expirados])
        conn.executemany("DELETE FROM gpu_requests WHERE token=?", [(token,) for token in expirados])
        conn.commit()
    abandoned = []
    for row in conn.execute('SELECT token FROM gpu_requests').fetchall():
        with _lock_path('token-'+row['token']).open('a+') as handle:
            try:
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            abandoned.append(row['token'])
    if abandoned:
        conn.executemany('DELETE FROM gpu_requests WHERE token=?',[(t,) for t in abandoned])
        conn.commit()


def status(resource: str = "") -> list[dict]:
    conn = _conn()
    try:
        _limpar_stale(conn)
        if resource:
            rows = conn.execute("SELECT * FROM leases WHERE resource=? ORDER BY acquired_at", (resource,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM leases ORDER BY resource, acquired_at").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            request = conn.execute('SELECT request FROM gpu_requests WHERE token=?',(row['token'],)).fetchone()
            if request:
                meta = json.loads(request[0])
                item.update(priority=meta['priority'], vram_reserved_bytes=meta.get('additional_bytes'),
                            model_key=meta.get('model_key'), lease_seconds=max(0,time.time()-datetime.fromisoformat(row['acquired_at']).timestamp()))
            result.append(item)
        return result
    finally:
        conn.close()


def _lock_path(resource: str) -> Path:
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(resource))
    return LOCK_DIR / f"{seguro or 'recurso'}.lock"


@contextlib.contextmanager
def lease(resource: str, owner: str, entity: str | None = None,
          ttl: float = DEFAULT_TTL, wait: float | None = None, cancel=None):
    """Adquire um recurso exclusivo, registra o proprietário e libera no fim."""
    import fcntl

    recurso = str(resource).strip()
    if not recurso:
        raise ValueError("resource vazio")
    token = f"lease-{uuid.uuid4().hex}"
    started = time.monotonic()
    lock = _lock_path(recurso)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError('Espera de recurso cancelada antes da execução.')
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if wait is not None or cancel is not None else 0)
            try:
                fcntl.flock(handle.fileno(), flags)
                break
            except BlockingIOError:
                if wait is not None and time.monotonic() - started >= float(wait):
                    raise TimeoutError(f"recurso ocupado: {recurso}")
                time.sleep(0.1)
        conn = _conn()
        try:
            _limpar_stale(conn)
            conn.execute("DELETE FROM leases WHERE resource=?", (recurso,))
            now = time.time()
            conn.execute(
                "INSERT INTO leases(token,resource,owner,entity,pid,acquired_at,heartbeat,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (token, recurso, str(owner), str(entity or getattr(config, "ENTIDADE_ID", "")),
                 os.getpid(), _now(), now, now + max(5.0, float(ttl))),
            )
            conn.commit()
        finally:
            conn.close()
        finished = threading.Event()

        def renew():
            while not finished.wait(max(1.0, min(float(ttl) / 3, 20.0))):
                try:
                    db = _conn()
                    try:
                        now = time.time()
                        db.execute("UPDATE leases SET heartbeat=?,expires_at=? WHERE token=?",
                                   (now, now + max(5.0, float(ttl)), token))
                        db.commit()
                    finally:
                        db.close()
                except sqlite3.Error:
                    # O flock permanece válido mesmo se a telemetria falhar.
                    continue

        worker = threading.Thread(target=renew, daemon=True, name="resource-heartbeat")
        worker.start()
        try:
            handle.seek(0)
            handle.truncate(0)
            handle.write(json.dumps({"resource": recurso, "owner": owner,
                                    "entity": entity or getattr(config, "ENTIDADE_ID", ""),
                                    "pid": os.getpid(), "token": token}) + "\n")
            handle.flush()
            yield token
        finally:
            finished.set()
            worker.join(timeout=11)
            conn = _conn()
            try:
                conn.execute("DELETE FROM leases WHERE token=?", (token,))
                conn.commit()
            finally:
                conn.close()
            try:
                handle.seek(0)
                handle.truncate(0)
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def summary() -> str:
    itens = status()
    if not itens:
        return "nenhum recurso exclusivo em uso"
    return " | ".join(
        f"{item['resource']}={item['owner']}[{item['entity']},pid={item['pid']}]"
        for item in itens
    )


# A arbitragem GPU continua neste gerenciador e no mesmo SQLite. VRAM residente
# não é lease de compute e não impede o sono depois que a geração terminou.
PRIORITIES = {'audio': 0, 'llm': 1, 'spontaneous': 2, 'vision': 3, 'image': 4, 'batch': 5, 'unload': 5}


class GPUDeferred(RuntimeError):
    """Manutenção pode ser adiada; não é pausa/retomada de imagem executando."""


class GPUWaitTimeout(TimeoutError):
    """A fila não concedeu compute; nenhuma inferência começou por este lease."""


class GPUCancelledBeforeCompute(InterruptedError):
    """Pausa cooperativa na fila, comprovadamente antes de conceder compute."""


# 06/11 (pedido humano, já no desktop leve): margem de VRAM escolhida em Configurações. Piso 128 MiB (antes
# 512 fixo): no Xfce sem compositor a placa fica com ~99 MiB usados pelo sistema. Atenção: a escada estima o 9B
# em 33 camadas/32K uns 350 MiB abaixo do real (7.389 MiB medidos), e a margem é quem cobre esse erro.
MARGIN_MIN_BYTES = 128 * 1024 ** 2
MARGIN_OPTIONS_MIB = (128, 256, 384, 512, 768, 1024)


def gpu_policy():
    baseline = dict(margin_bytes=768 * 1024 ** 2, concurrency_validated=False,
                    max_compute=2, max_utilization=55, sticky_seconds=90,
                    interactive_grace_seconds=3, ram_margin_bytes=2 * gpu_metrics.GIB)
    defaults = dict(baseline)
    path = Path(config.RAIZ) / 'compartilhado/config/gpu.json'
    try:
        configured = json.loads(path.read_text())
        if not isinstance(configured, dict):
            raise ValueError('invalid_gpu_policy_document')
        defaults.update({k:v for k,v in configured.items() if k in defaults})
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError):
        defaults['concurrency_validated'] = False
    try:
        import math
        for name in baseline:
            if name == 'concurrency_validated':
                continue
            number = float(defaults[name])
            if not math.isfinite(number) or number < 0:
                raise ValueError('invalid_gpu_policy')
            defaults[name] = number
        defaults['margin_bytes'] = max(MARGIN_MIN_BYTES, min(int(defaults['margin_bytes']), 2 * gpu_metrics.GIB))
        defaults['max_compute'] = max(1, min(2, int(defaults['max_compute'])))
        defaults['max_utilization'] = min(70, defaults['max_utilization'])
        defaults['ram_margin_bytes'] = max(gpu_metrics.GIB, defaults['ram_margin_bytes'])
    except (ValueError, TypeError, OverflowError):
        return baseline  # Arquivo incerto nunca habilita concorrência.
    defaults['concurrency_validated'] = defaults['concurrency_validated'] is True
    return defaults


def ram_prompt_cache_plan(*, memory=None):
    """Teto para próximos boots, não medição/reserva de RAM nem cache de pesos.

    Uma cota fixa por entidade evita multiplicar o padrão de 8 GiB por runner.
    O lifecycle limita cada daemon próprio a um modelo/geração simultâneos.
    Daemons já vivos não são reconfigurados por esta projeção.
    """
    mib = 1024 ** 2
    entities = ('hoshino', 'lilith', 'alistair')
    allocation = dict(hoshino=3584, lilith=3584, alistair=1024)
    budget = 8192
    valid, reason = True, 'configured_budget'
    try:
        path = Path(config.RAIZ) / 'compartilhado/config/gpu.json'
        try:
            supplied = json.loads(path.read_text())
        except FileNotFoundError:
            supplied = {}
        if not isinstance(supplied, dict):
            raise ValueError('invalid_policy')
        if 'ram_prompt_cache' in supplied:
            cache = supplied['ram_prompt_cache']
            if not isinstance(cache, dict):
                raise ValueError('invalid_cache_policy')
            budget, allocation = cache.get('budget_mib'), cache.get('per_entity_mib')
            if (type(budget) is not int or not 0 <= budget <= 16384 or
                    not isinstance(allocation, dict) or set(allocation) != set(entities) or
                    any(type(n) is not int or not 0 <= n <= budget for n in allocation.values()) or
                    sum(allocation.values()) > budget):
                raise ValueError('invalid_cache_budget')
    except (OSError, ValueError, TypeError):
        budget, allocation = 0, dict.fromkeys(entities, 0)
        valid, reason = False, 'invalid_configuration_cache_disabled'

    if memory is None:
        memory = dict(total_bytes=gpu_metrics.ram_total(), available_bytes=gpu_metrics.ram_available())
    total = memory.get('total_bytes') if isinstance(memory, dict) else None
    available = memory.get('available_bytes') if isinstance(memory, dict) else None
    configured = dict(allocation)
    if type(total) is not int or type(available) is not int or not 0 <= available <= total or total <= 0:
        allocation = dict.fromkeys(entities, 0)
        if valid:
            reason = 'uncertain_ram_cache_disabled'
    else:
        # RAM disponível já inclui o uso observado. Não somamos swap ou
        # subtraímos um teto virtual como se fosse RSS efetivamente alocado.
        headroom = max(0, available - gpu_policy()['ram_margin_bytes'] - 4 * gpu_metrics.GIB)
        allocated = sum(allocation.values())
        capacity = min(allocated, total // (3 * mib), int(headroom // mib))
        if allocated and capacity < allocated:
            allocation = {entity: amount * capacity // allocated for entity, amount in allocation.items()}
            if valid:
                reason = 'ram_headroom_limited'
    return dict(budget_mib=budget, configured_per_entity_mib=configured, per_entity_mib=allocation,
                aggregate_mib=sum(allocation.values()), valid=valid, reason=reason,
                used_bytes=None, state='planned_not_verified', apply='next_managed_daemon_boot',
                scope='owned_local_daemons', swap_in_budget=False)


def ram_prompt_cache_environment(entity, environment, *, plan=None):
    """Só opções públicas permitidas; não retorna/copia credenciais do ambiente."""
    if entity not in ('hoshino', 'lilith', 'alistair'):
        raise ValueError('unknown_cache_entity')
    policy = ram_prompt_cache_plan() if plan is None else plan
    cap = policy['per_entity_mib'][entity]
    manual = environment.get('LLAMA_ARG_CACHE_RAM')
    if isinstance(manual, str) and re.fullmatch(r'[0-9]{1,9}', manual):
        cap = min(cap, int(manual))  # 0 explícito continua desligado.
    return dict(LLAMA_ARG_CACHE_RAM=str(cap), OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_NUM_PARALLEL='1')


def residency():
    with contextlib.closing(_conn()) as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM gpu_residency')]


def observe_model(endpoint, model, vram_bytes, *, used=False, reload_seconds=12):
    now = time.time()
    size = None if vram_bytes is None else max(0, int(vram_bytes))
    with contextlib.closing(_conn()) as conn, conn:
        conn.execute('INSERT INTO gpu_residency VALUES(?,?,?,?,?,?,?) ON CONFLICT(model_key) DO UPDATE SET '
                     'vram_bytes=excluded.vram_bytes,observed_at=excluded.observed_at,last_used=CASE WHEN ? '
                     'THEN excluded.last_used ELSE gpu_residency.last_used END',
                     (endpoint+'|'+model, model, endpoint, size, now, now, float(reload_seconds), bool(used)))


def forget_model(endpoint, model):
    with contextlib.closing(_conn()) as conn, conn:
        conn.execute('DELETE FROM gpu_residency WHERE model_key=?', (endpoint+'|'+model,))


def record_reload(endpoint, model, seconds):
    """Custo observado pelo backend, sem inventar tamanho/residência de VRAM."""
    if not 0 < seconds < 3600:
        return
    now = time.time()
    try:
        with contextlib.closing(_conn()) as conn, conn:
            conn.execute('INSERT INTO gpu_residency VALUES(?,?,?,?,?,?,?) ON CONFLICT(model_key) DO UPDATE SET '
                         'reload_seconds=excluded.reload_seconds,last_used=excluded.last_used',
                         (endpoint+'|'+model,model,endpoint,None,0,now,float(seconds)))
    except (sqlite3.Error,OSError) as exc:
        diagnostics.persistence_failure('gpu.record_reload',DB_PATH,exc,retry_safe=True,model=model)
        return False
    return True


def record_memory_estimate(endpoint, model, size):
    """Tamanho reportado por /ps ou catálogo local; não é reserva de compute."""
    import math
    size = float(size)
    if not math.isfinite(size) or size<=0:
        return
    key = endpoint+'|'+model
    with contextlib.closing(_conn()) as conn, conn:
        for name,value in (('model_estimate:'+key,size),('model_estimate_at:'+key,time.time())):
            conn.execute('INSERT INTO gpu_meta VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',(name,value))


def record_model_context(endpoint, model, context):
    """30/10: contexto do runner que o daemon reporta no /api/ps (ver gpu_resource.resident_on_gpu_whole)."""
    if type(context) is not int or context <= 0:
        return
    key = endpoint+'|'+model
    with contextlib.closing(_conn()) as conn, conn:
        for name,value in (('model_ctx:'+key,context),('model_ctx_at:'+key,time.time())):
            conn.execute('INSERT INTO gpu_meta VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',(name,value))


def model_context(model_key):
    with contextlib.closing(_conn()) as conn:
        values = dict(conn.execute('SELECT name,value FROM gpu_meta WHERE name IN (?,?)',
                                  ('model_ctx:'+model_key,'model_ctx_at:'+model_key)))
    if abs(time.time()-values.get('model_ctx_at:'+model_key,0))>15:
        return None
    value = values.get('model_ctx:'+model_key)
    return int(value) if value is not None else None


def _resident_whole(conn, models, model_key, context):
    """30/10 (33 camadas): o daemon diz, em leitura de ≤15 s, que o modelo está INTEIRO na placa (VRAM residente ≥
    tamanho total do /api/ps) com o mesmo contexto pedido. Só então o degrau de todas as camadas não conta de novo a
    memória que já está em used_bytes."""
    if type(context) is not int:
        return False
    rows = dict(conn.execute('SELECT name,value FROM gpu_meta WHERE name IN (?,?,?,?)',
                ('model_estimate:'+model_key,'model_estimate_at:'+model_key,'model_ctx:'+model_key,'model_ctx_at:'+model_key)))
    now = time.time()
    total, ctx = rows.get('model_estimate:'+model_key), rows.get('model_ctx:'+model_key)
    if (not total or ctx is None or int(ctx) != context or abs(now-rows.get('model_estimate_at:'+model_key,0)) > 15
            or abs(now-rows.get('model_ctx_at:'+model_key,0)) > 15):
        return False
    return any(r.get('model_key') == model_key and now-(r.get('observed_at') or 0) <= 15
               and (r.get('vram_bytes') or 0) >= total for r in models or ())


def resident_whole(models, model_key, context):
    with contextlib.closing(_conn()) as conn:
        return _resident_whole(conn, models, model_key, context)


def memory_estimate(model_key):
    with contextlib.closing(_conn()) as conn:
        values = dict(conn.execute('SELECT name,value FROM gpu_meta WHERE name IN (?,?)',
                                  ('model_estimate:'+model_key,'model_estimate_at:'+model_key)))
    if abs(time.time()-values.get('model_estimate_at:'+model_key,0))>15:
        return None
    return values.get('model_estimate:'+model_key)


def gpu_state():
    with contextlib.closing(_conn()) as conn:
        _limpar_stale(conn)
        queued = [dict(r, request=json.loads(r['request'])) for r in conn.execute(
            'SELECT * FROM gpu_requests ORDER BY priority,enqueued_at,token')]
    models = residency()
    return dict(metrics=gpu_metrics.snapshot(), hard_limit_bytes=gpu_metrics.HARD_LIMIT,
                policy=gpu_policy(), compute=status('gpu'), queue=queued,
                residency=[dict(r, state=model_state(r)) for r in models])


def assess_gpu(request, metrics, active=(), models=(), policy=None, now=None):
    """Decisão pura. Reservas não materializadas são contadas conservadoramente."""
    p = policy or gpu_policy()
    now = time.time() if now is None else now
    resident = next((r for r in models if r['model_key']==request.get('model_key') and
                     now-r['observed_at'] <= 15 and r['vram_bytes'] is not None), None)
    warm = resident['vram_bytes'] if resident else 0
    budget = request['vram_bytes']
    # 30/10: modelo comprovadamente inteiro na placa no degrau de todas as camadas — a memória dele (pesos, KV e
    # buffers) já está em used_bytes; não há o que somar (gpu_resource.resident_on_gpu_whole).
    if request.get('resident_full') and resident:
        warm = max(warm, budget)
    reserved = sum(r.get('additional_bytes', r['vram_bytes']+r['workspace_bytes']) for r in active)
    # sd-cli já suporta graph-cut/offload e limite de memória. Só esse backend
    # opta por um teto flexível; dimensões, passos e pesos não são modificados.
    if (request['owner']=='image' and request.get('flexible_min_bytes') is not None
            and metrics.get('known') and metrics.get('stable') and abs(now-metrics.get('observed_at',0))<=2):
        available = (min(gpu_metrics.HARD_LIMIT,metrics['total_bytes'])-metrics['used_bytes']-
                     p['margin_bytes']-reserved-request['workspace_bytes'])
        available = max(0,int(available)//(64*1024**2)*(64*1024**2))
        if request['flexible_min_bytes']<=available<budget:
            budget = available
    # Mesmos pesos já residentes no degrau pedido: KV e buffers foram alocados na carga;
    # somar o espaço de trabalho de novo travava 32 camadas com o Minecraft aberto (27/10).
    workspace = 0 if warm and warm >= 0.9*budget else request['workspace_bytes']
    additional = max(0,budget-warm)+workspace
    result = dict(allowed=False, reason='', additional_bytes=additional, resident_bytes=warm,vram_budget_bytes=budget)
    if budget+request['workspace_bytes']+p['margin_bytes'] > gpu_metrics.HARD_LIMIT:
        return dict(result, reason='estimate_exceeds_hard_limit')
    if not metrics.get('known') or not metrics.get('stable') or abs(now-metrics.get('observed_at', 0)) > 2:
        return dict(result, reason='uncertain_vram')
    limit = min(gpu_metrics.HARD_LIMIT, metrics['total_bytes'])
    if metrics['used_bytes']+additional+reserved+p['margin_bytes'] > limit:
        return dict(result, reason='vram_pressure')
    if active:
        if request['owner']=='image' or any(r['owner']=='image' for r in active):
            return dict(result, reason='image_non_preemptible')
        if any(r.get('model_key') and r['model_key']==request.get('model_key') for r in active):
            return dict(result, reason='same_model_busy')
        if (not p['concurrency_validated'] or not metrics.get('stable') or
            metrics.get('utilization') is None or metrics['utilization'] > p['max_utilization'] or
            len(active) >= p['max_compute'] or not request.get('overlap_safe') or
            any(not r.get('overlap_safe') for r in active)):
            return dict(result, reason='serialize_for_stability')
    elif metrics.get('utilization') is not None and metrics['utilization'] >= 90:
        return dict(result, reason='external_compute_busy')
    return dict(result, allowed=True, reason='fits')


def _gpu_rows(conn, states):
    placeholders = ','.join('?' for _ in states)
    return [dict(token=r['token'], **json.loads(r['request'])) for r in conn.execute(
        'SELECT * FROM gpu_requests WHERE state IN ('+placeholders+')', tuple(states))]


def interactive_audio_active():
    """O mesmo lock CPU de áudio sinaliza P0; não inventa compute GPU."""
    import fcntl
    LOCK_DIR.mkdir(parents=True,exist_ok=True)
    with _lock_path('cpu_audio').open('a+') as handle:
        try:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def higher_priority_waiting(priority, *, include_audio=False):
    if include_audio and priority>0 and interactive_audio_active():
        return True
    with contextlib.closing(_conn()) as conn:
        _limpar_stale(conn)
        return bool(conn.execute("SELECT 1 FROM gpu_requests WHERE state='waiting' AND priority<?", (priority,)).fetchone())


@contextlib.contextmanager
def compute_lease(owner, *, entity=None, model_key='', vram_bytes=6*gpu_metrics.GIB,
                  workspace_bytes=512*1024**2, priority=None, overlap_safe=False,
                  expected_latency=15, fallback_latency=120, cpu_fallback=False,
                  cpu_ram_bytes=8*gpu_metrics.GIB, wait=120, cancel=None, prepare=None,
                  cancel_supported=False,flexible_min_bytes=None,use_model_estimate=False,
                  opportunistic=False,resident_full=False,resident_ctx=None):
    """Fila cooperativa, reservas e compute no inventário existente.

    O kernel conserva a posse de cada token, inclusive após expiração/queda de
    telemetria. Compatibilidade com o flock GPU exclusivo legado é preservada.
    Nunca pausa, mata ou repete uma inferência/imagem em execução.
    """
    import fcntl
    entity = entity or config.ENTIDADE_ID
    priority = PRIORITIES.get(owner, 5) if priority is None else int(priority)
    if priority not in range(6) or vram_bytes < 0 or workspace_bytes < 0 or cpu_ram_bytes < 0:
        raise ValueError('Pedido de recurso inválido.')
    if flexible_min_bytes is not None and (owner!='image' or not 0<flexible_min_bytes<=vram_bytes):
        raise ValueError('Teto flexível permitido somente para o backend de imagem gerenciado.')
    token = 'compute-'+uuid.uuid4().hex
    request = dict(owner=owner, entity=entity, model_key=model_key, priority=priority,
                   vram_bytes=int(vram_bytes), workspace_bytes=int(workspace_bytes), resident_full=resident_full is True,
                   resident_ctx=resident_ctx if type(resident_ctx) is int else None,
                   overlap_safe=bool(overlap_safe), expected_latency=float(expected_latency),
                   fallback_latency=float(fallback_latency), cpu_ram_bytes=int(cpu_ram_bytes),
                   cancel_supported=cancel_supported is True, resume_supported=False,
                   opportunistic=opportunistic is True)
    if flexible_min_bytes is not None: request['flexible_min_bytes']=int(flexible_min_bytes)
    started = time.monotonic()
    acquired = None
    prepared_at = None
    gate = None
    cpu_gpu_guard = None
    metrics = gpu_metrics.snapshot()
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    with _lock_path('token-'+token).open('a+') as possession:
        fcntl.flock(possession.fileno(), fcntl.LOCK_EX)
        try:
            with contextlib.closing(_conn()) as conn, conn:
                conn.execute('INSERT INTO gpu_requests VALUES(?,?,?,\'waiting\',?)',
                             (token, priority, time.time(), json.dumps(request)))
                if priority <= 1:
                    conn.execute("INSERT INTO gpu_meta VALUES('interactive',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (time.time(),))
            diagnostics.emit('gpu.queued', token=token, **request, metrics=metrics)
            while acquired is None:
                if cancel is not None and cancel.is_set():
                    raise GPUCancelledBeforeCompute('Pedido de compute cancelado antes da execução.')
                metrics = gpu_metrics.snapshot()
                policy = gpu_policy()
                preparing = False
                with contextlib.closing(_conn()) as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    # Esperas abandonadas também são reconhecidas pelo token kernel.
                    for r in conn.execute("SELECT token FROM gpu_requests WHERE token<>?", (token,)).fetchall():
                        with _lock_path('token-'+r['token']).open('a+') as old:
                            try:
                                fcntl.flock(old.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except BlockingIOError:
                                continue
                            conn.execute('DELETE FROM leases WHERE token=?', (r['token'],))
                            conn.execute('DELETE FROM gpu_requests WHERE token=?', (r['token'],))
                    active = _gpu_rows(conn, ('running','preparing'))
                    cpu_active = _gpu_rows(conn, ('cpu',))
                    top = conn.execute("SELECT token FROM gpu_requests WHERE state='waiting' ORDER BY priority,enqueued_at,token LIMIT 1").fetchone()
                    models = [dict(r) for r in conn.execute('SELECT * FROM gpu_residency')]
                    if use_model_estimate and model_key:
                        estimate = conn.execute('SELECT value FROM gpu_meta WHERE name=?',('model_estimate:'+model_key,)).fetchone()
                        stamp = conn.execute('SELECT value FROM gpu_meta WHERE name=?',('model_estimate_at:'+model_key,)).fetchone()
                        if estimate and stamp and abs(time.time()-stamp[0])<=15:
                            request['vram_bytes']=int(estimate[0])
                            request['cpu_ram_bytes']=max(cpu_ram_bytes,int(estimate[0])+4*gpu_metrics.GIB)
                    # Revisão Codex: a isenção do modelo inteiro na placa é provada agora, não no momento do pedido.
                    effective = (dict(request, resident_full=_resident_whole(conn, models, model_key, request.get('resident_ctx')))
                                 if request.get('resident_full') else request)
                    decision = assess_gpu(effective, metrics, active, models, policy)
                    available_ram = gpu_metrics.ram_available()
                    if owner != 'image':
                        own_resident = next((r for r in models if r['model_key']==model_key), None)
                        # GPU também precisa de RAM para carregar/servir o modelo.
                        # Pesos já residentes não são cobrados duas vezes; mantém
                        # folga de runtime, sem contar swap como RAM disponível.
                        staging_ram = (2*gpu_metrics.GIB if model_state(own_resident) in {'gpu_resident','ram_resident'}
                                       else request['vram_bytes'])
                        if available_ram is None or available_ram < staging_ram+policy['ram_margin_bytes']:
                            decision = dict(decision,allowed=False,reason='ram_pressure_or_unknown')
                    if opportunistic:
                        # Alistair não expulsa pares, não concorre com interação e
                        # nunca precisa recuperar GPU interrompendo geração.
                        preferred = conn.execute("SELECT 1 FROM gpu_requests WHERE state='waiting' "
                            "AND token<>? AND (priority<? OR json_extract(request,'$.entity') IN ('hoshino','lilith'))",
                            (token, priority)).fetchone()
                        row = next((r for r in models if r['model_key']==model_key), None)
                        reload_cost = 0 if model_state(row)=='gpu_resident' else (row['reload_seconds'] if row else 12)
                        reason = None
                        if preferred or interactive_audio_active(): reason = 'interactive_priority'
                        elif active or cpu_active: reason = 'opportunistic_busy'
                        elif metrics.get('utilization') is None or metrics['utilization'] > policy['max_utilization']:
                            reason = 'opportunistic_compute_uncertain'
                        elif fallback_latency <= expected_latency+reload_cost+5: reason = 'reload_not_advantageous'
                        if reason: decision = dict(decision,allowed=False,reason=reason)
                    if any(r.get('model_key') and r['model_key']==model_key for r in cpu_active):
                        decision = dict(decision,allowed=False,reason='same_model_busy_cpu')
                    recent = conn.execute("SELECT value FROM gpu_meta WHERE name='interactive'").fetchone()
                    quiet = priority < 4 or not recent or time.time()-recent[0] >= policy['interactive_grace_seconds']
                    audio_priority = (owner=='image' or opportunistic) and interactive_audio_active()
                    if audio_priority: quiet=False
                    # Caber na VRAM não é concessão de compute: a janela de
                    # proteção interativa também pode mandar o job para CPU.
                    # Apenas torna o diagnóstico fiel; não muda prazo/prioridade.
                    if not quiet and decision['allowed']:
                        decision = dict(decision, allowed=False,
                                        reason='interactive_audio_priority' if audio_priority else 'interactive_grace')
                    first = top and top['token']==token and quiet
                    if first and not active and not cpu_active and prepare is not None and not opportunistic and (prepared_at is None or
                            (not decision['allowed'] and time.monotonic()-prepared_at >= 2)):
                        gate = _lock_path('gpu').open('a+')
                        try:
                            fcntl.flock(gate.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            preparing = True
                        except BlockingIOError:
                            gate.close(); gate = None
                        if preparing:
                            conn.execute("UPDATE gpu_requests SET state='preparing' WHERE token=?", (token,))
                    elif first and decision['allowed']:
                        gate = _lock_path('gpu').open('a+')
                        try:
                            fcntl.flock(gate.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                            acquired = dict(backend='gpu', token=token, priority=priority, **decision)
                        except BlockingIOError:
                            gate.close(); gate = None
                    # Uma imagem não preemptível não bloqueia uma conversa nova:
                    # ela ganha CPU quando há RAM comprovada, sem tocar na imagem.
                    wait_for_image = priority<=1 and fallback_latency>expected_latency+5 and any(
                        r['owner']=='image' and r.get('cancel_supported') for r in active)
                    same_runner_busy = bool(model_key) and any(
                        r.get('model_key') == model_key for r in (*active, *cpu_active))
                    if (not preparing and acquired is None and cpu_fallback and
                            (priority <= 3 or opportunistic) and not wait_for_image and not same_runner_busy):
                        available = available_ram
                        if available is not None and available >= request['cpu_ram_bytes']+policy['ram_margin_bytes']:
                            cpu = _lock_path('cpu_llm').open('a+')
                            guard = _lock_path('gpu').open('a+')
                            try:
                                # CPU pode coexistir com compute GPU, mas não
                                # com unload/reconfiguração exclusiva de pesos.
                                fcntl.flock(guard.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                                fcntl.flock(cpu.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                                gate = cpu
                                cpu_gpu_guard = guard
                                acquired = dict(backend='cpu', token=token, priority=priority, **decision)
                            except BlockingIOError:
                                cpu.close()
                                guard.close()
                    if acquired:
                        request['additional_bytes'] = decision['additional_bytes']
                        request['requested_vram_bytes'] = request['vram_bytes']
                        request['vram_bytes'] = decision['vram_budget_bytes']
                        state = 'running' if acquired['backend']=='gpu' else 'cpu'
                        conn.execute('UPDATE gpu_requests SET state=?,request=? WHERE token=?', (state,json.dumps(request),token))
                        now = time.time()
                        conn.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,?,?)',
                                     (token, 'gpu' if state=='running' else 'cpu_llm', owner, entity, os.getpid(), _now(), now, now+DEFAULT_TTL))
                    conn.commit()
                if preparing:
                    try:
                        prepare()
                    except GPUDeferred:
                        pass
                    finally:
                        prepared_at = time.monotonic()
                        with contextlib.closing(_conn()) as conn, conn:
                            conn.execute("UPDATE gpu_requests SET state='waiting' WHERE token=?", (token,))
                        gate.close(); gate = None
                    continue
                if acquired is None:
                    if time.monotonic()-started >= wait:
                        raise GPUWaitTimeout('GPU indisponível com margem segura: '+decision['reason'])
                    time.sleep(.05)
            began = time.monotonic()
            diagnostics.emit('gpu.compute_acquired', **request, **{k:v for k,v in acquired.items() if k not in request},
                             metrics=metrics, queued_seconds=began-started, fallback=acquired['backend'] if acquired['backend']!='gpu' else None)
            try:
                yield acquired
            finally:
                diagnostics.emit('gpu.compute_released', token=token, owner=owner, entity=entity,
                                 priority=priority, backend=acquired['backend'], duration_seconds=time.monotonic()-began,
                                 vram_before=metrics, vram_after=gpu_metrics.snapshot())
        finally:
            try:
                with contextlib.closing(_conn()) as conn, conn:
                    conn.execute('DELETE FROM leases WHERE token=?', (token,))
                    conn.execute('DELETE FROM gpu_requests WHERE token=?', (token,))
            finally:
                if gate is not None:
                    gate.close()
                if cpu_gpu_guard is not None:
                    cpu_gpu_guard.close()


__all__ = ["DB_PATH", "LOCK_DIR", "status", "lease", "summary", "compute_lease", "gpu_state"]
