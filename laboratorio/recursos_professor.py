"""Planejamento conservador de recursos do professor 27B quantizado.

Estima RAM e contexto antes de carregar pesos. Nao infere que GTT equivale a VRAM.
Valores sao reservas aproximadas: a checagem real do backend continua obrigatoria.
"""
from __future__ import annotations
import math
import os
from pathlib import Path

GIB = 1024**3
# Modelo GGUF Q4_K_M tem ~16.5GB decimais; incluir overhead de mapeamento/cache.
MODEL_RESERVE = 17 * GIB
SYSTEM_RESERVE = 4 * GIB
CONTEXT_TIERS = (4096, 8192, 12288, 16384, 24576, 32768)


def memory_bytes(meminfo: str | None = None) -> tuple[int, int]:
    if meminfo is None:
        meminfo = Path('/proc/meminfo').read_text()
    parts={}
    for line in meminfo.splitlines():
        if ':' not in line:continue
        name, rest=line.split(':',1)
        if name in ('MemTotal','MemAvailable'):
            parts[name]=int(rest.strip().split()[0])*1024
    if not all(k in parts for k in ('MemTotal','MemAvailable')):
        raise RuntimeError('Nao foi possivel medir MemAvailable em /proc/meminfo')
    return parts['MemTotal'], parts['MemAvailable']


def available_vram_bytes(root=Path('/sys/class/drm')) -> int:
    """Usar memoria VRAM fisica observada, nunca GTT; falhar como desconhecida."""
    if not root.exists():return 0
    values=[]
    for card in root.glob('card[0-9]*'):
        dev=card/'device'
        try:
            total=int((dev/'mem_info_vram_total').read_text())
            used=int((dev/'mem_info_vram_used').read_text())
            if total>2*GIB:values.append(max(0,total-used))
        except (OSError,ValueError):continue
    return max(values,default=0)


def estimate_tokens(payload: str) -> int:
    """Orcamento alto para portugues/JSON, nunca substitui tokenizer real."""
    return math.ceil(len(payload.encode('utf-8'))/2.5)


def resource_plan(*, payload: str, total: int, available: int, cpu_count: int,
                  gpu_free: int=0, gpu_layers: str='auto', max_ctx: int=32768,
                  max_threads: int=0) -> dict:
    if gpu_layers!='auto':
        value=int(gpu_layers)
        if value < 0 or value > 32:raise ValueError('gpu_layers deve ser auto ou 0–32')
        layers=value
    else:
        # GPU experimental: apenas umas poucas camadas quando existe folga real.
        # Se nao ha medida fisica confiavel, nunca presumir VRAM livre.
        layers=4 if gpu_free>=6*GIB else 0
    if max_ctx not in CONTEXT_TIERS:raise ValueError('max_ctx fora dos niveis suportados')
    if not 0<=max_threads<=256:raise ValueError('max_threads invalido')
    if available<=0 or total<=0 or available>total:raise ValueError('Medicao RAM invalida')
    if cpu_count<1:raise ValueError('CPU invalida')
    # Manter 2 threads logicas para o sistema quando possivel; teto opcional.
    threads=max(1,cpu_count-2)
    if max_threads:threads=min(threads,max_threads)
    # A resposta JSON do professor pede ate ~1600 tokens, incluindo protocolo.
    required=estimate_tokens(payload)+2048+1024
    tiers=[c for c in CONTEXT_TIERS if c<=max_ctx and c>=required]
    if not tiers:raise RuntimeError(f'Material requer ~{required} tokens; dividir snapshot em lotes (max_ctx={max_ctx}).')
    # A logica abaixo reserva ~1.5 GiB para cada bloco de 4096 tokens de KV/overhead,
    # intencionalmente conservador; memoria real depende da arquitetura e cache.
    eligible=[c for c in tiers if available>=MODEL_RESERVE+SYSTEM_RESERVE+math.ceil(c/4096)*int(1.5*GIB)]
    if not eligible:
        raise RuntimeError(f'RAM disponivel insuficiente ({available/GIB:.1f} GiB) para professor 27B; nao usar swap como VRAM.')
    ctx=eligible[0]
    return dict(ctx=ctx,threads=threads,gpu_layers=layers,estimated_tokens=required,
                available_gib=round(available/GIB,2),total_gib=round(total/GIB,2),
                free_vram_gib=round(gpu_free/GIB,2),reserve_gib=round((MODEL_RESERVE+SYSTEM_RESERVE+math.ceil(ctx/4096)*1.5*GIB)/GIB,2),
                observation='HEURISTICA_DE_RAM_E_TOKENS_SEM_PROBE_REAL')
