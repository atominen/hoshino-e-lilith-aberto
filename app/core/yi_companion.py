"""Yi6B opt-in: recibo básico e perfil físico pinados ao executor selecionado.

O recibo é um resultado de ensaio local, não uma aprovação de personalidade ou
treinamento. Nenhuma carga/download/inferência acontece ao consultar o catálogo.
"""
import hashlib
import json
import math
from pathlib import Path

GIB = 1024**3
CONTEXT = 4096
OUTPUT = 512
CASE_IDS = frozenset(('identity', 'instruction', 'portuguese', 'arithmetic',
                      'context', 'unknown_memory', 'attribution', 'translation'))


def native_prompt(messages):
    """Serialização do tokenizer Yi local: prefixo system, pares ChatML.

    Sem sobrescrever o template/modelo pinado; não descarta mensagens. Outros
    papéis/formatos precisam de um executor compatível, nunca de truncamento.
    """
    prefix=[];parts=[];started=False
    for message in messages:
        role=message.get('role');content=message.get('content')
        if not isinstance(content,str) or message.get('images') or message.get('tool_calls'):
            raise ValueError('Contexto Yi nativo requer apenas texto')
        if role=='system' and not started:prefix.append(content)
        elif role=='user':
            started=True;parts.append('<|im_start|>user\n'+content+'<|im_end|>\n<|im_start|>assistant\n')
        elif role=='assistant' and started:parts.append(content+'<|im_end|>\n')
        else:raise ValueError('Papel/ordem incompatível com template Yi; nenhuma mensagem foi descartada')
    if not messages or messages[-1].get('role')!='user':raise ValueError('Yi requer uma entrada de usuário final')
    return '\n\n'.join(prefix)+''.join(parts)


def receipt_path(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Recibo Yi deve ser relativo à área de ensaios')
    path = root/relative
    if not path.resolve().is_relative_to(root/'compartilhado/runtime/ensaios'):
        raise ValueError('Recibo Yi fora da área de ensaios')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Recibo Yi não pode atravessar links simbólicos')
    return path


def candidate(root, entity, settings):
    """Só habilita o MESMO alias/hash testado, na própria entidade."""
    from core.neural9b_modes import runtime_alias, selected_version
    if entity not in {'hoshino', 'lilith'} or settings.get('model') != entity+'-yi-6b:latest':
        raise ValueError('Yi adicional de outra entidade/família')
    if settings.get('enabled') is not True or settings.get('conversation_validated') is not True:
        return None
    selected = selected_version(root, entity, 'yi-6b')
    if not selected:
        raise ValueError('Yi sem seleção pinada')
    alias = runtime_alias(root, entity, 'yi-6b')
    path = receipt_path(root, settings.get('validation_receipt'))
    if path.stat().st_size > 256*1024:
        raise ValueError('Recibo Yi grande demais')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != settings.get('validation_sha256'):
        raise ValueError('Recibo Yi mudou')
    report = json.loads(raw)
    if (not isinstance(report, dict) or report.get('schema') != 1 or report.get('scope') != 'basic_text_only'
            or report.get('protocol') != 'ollama_chat'
            or report.get('entity') != entity or report.get('model') != alias
            or report.get('manifest_sha256') != selected['manifest_sha256']
            or report.get('source_sha256') != selected['source_sha256']
            or report.get('kind') != selected['kind'] or report.get('passed') is not True):
        raise ValueError('Recibo Yi não corresponde ao executor selecionado/aprovado no básico')
    review=report.get('semantic_review',{})
    if not isinstance(review,dict) or review.get('completed') is not True or review.get('passed') is not True:
        raise ValueError('Yi sem revisão semântica aprovada; palavras-chave não comprovam compreensão')
    checks = report.get('checks', [])
    if (not isinstance(checks, list) or not all(isinstance(c,dict) for c in checks)
            or len(checks) != len(CASE_IDS) or {c.get('id') for c in checks} != CASE_IDS
            or any(c.get('passed') is not True or c.get('done') is not True or c.get('done_reason') != 'stop' for c in checks)):
        raise ValueError('Yi não passou todos os casos básicos completos')
    probe, cleanup = report.get('physical', {}), report.get('cleanup', {})
    if not isinstance(probe,dict) or not isinstance(cleanup,dict):raise ValueError('Perfil/unload Yi inválido')
    resident = probe.get('resident_vram_bytes')
    if (probe.get('context') != CONTEXT or probe.get('layers') != -1 or probe.get('backend') != 'gpu'
            or probe.get('pressure') != [] or probe.get('metrics_known_stable') is not True
            or type(resident) is not int or resident <= 0
            or cleanup.get('unload_confirmed') is not True or cleanup.get('lease_released') is not True):
        raise ValueError('Perfil físico/unload Yi não confirmado')
    budget = max(5*GIB, math.ceil(resident/(256*1024**2))*(256*1024**2))
    if budget+512*1024**2+768*1024**2 > 8*GIB:
        raise ValueError('Yi fora do orçamento físico')
    return dict(model=alias, tier='companion', num_ctx=CONTEXT, output_max=OUTPUT,
                vram_bytes=budget, gpu_layers=-1, gpu_profile='yi6b_basic_ctx4096',
                expected_latency=8, fallback_latency=85, enabled=True,
                supports_tools=False, supports_thinking=False, supports_format=False,
                validation_scope='basic_text_only')
