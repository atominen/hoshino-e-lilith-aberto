"""Mede, nos diagnósticos reais (só leitura), onde o 9B gasta tempo e se raciocinar mais rendeu.

Uso: python3 -I scripts/medir_orcamento_raciocinio.py [arquivos .jsonl...]
Sem argumentos lê entidades/*/runtime/diagnostics/hoshino_2026-1*.jsonl.
Não abre bancos nem escreve nada.
"""
import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARACTERES_POR_TOKEN = 3.5
TETO_ROTINA = 1536


def eventos(caminho):
    with open(caminho, errors='replace') as f:
        for linha in f:
            if '"llm.' not in linha and '"activity.action_outcome"' not in linha and 'thinking_budget"' not in linha:
                continue
            try:
                yield json.loads(linha)
            except ValueError:
                continue


def decisao(cabecalho):
    return ('objetivo geral permanece' in cabecalho or 'meta intermediária' in cabecalho
            or cabecalho.startswith('DECISÃO OPERACIONAL'))


def main(arquivos):
    tempo: dict = collections.defaultdict(float)
    faixas = collections.defaultdict(collections.Counter)
    total_dec = cortado = acima = n_dec = 0
    for caminho in arquivos:
        inicio, fim, ultimo = {}, {}, None
        for e in eventos(caminho):
            d, ev = e.get('data') or {}, e.get('event')
            rid = d.get('request_id')
            if ev == 'llm.start':
                inicio[rid] = ((d.get('system_blocks') or [{}])[0].get('header') or '')
            elif ev == 'llm.end':
                fim[rid] = d
                if decisao(inicio.get(rid, '')):
                    t = d.get('thinking_chars') or 0
                    c = (d.get('content') or {}).get('len') or 0
                    n_dec += 1
                    total_dec += t + c
                    if t > TETO_ROTINA * CARACTERES_POR_TOKEN:
                        acima += 1
                        cortado += t - TETO_ROTINA * CARACTERES_POR_TOKEN
                    if 'objetivo geral' in inicio.get(rid, '') or inicio.get(rid, '').startswith('DECISÃO'):
                        ultimo = t
            elif ev == 'llm.backend_timing':
                carga = (d.get('load_ns') or 0) / 1e9
                geracao = (d.get('generation_ns') or 0) / 1e9
                total = (d.get('total_ns') or 0) / 1e9
                tempo['carga'] += carga
                tempo['geracao'] += geracao
                tempo['prompt_e_resto'] += max(0.0, total - carga - geracao)
            elif ev == 'minecraft.decision_thinking_budget':
                ultimo = 'estourou'
            elif ev == 'activity.action_outcome' and ultimo is not None:
                if d.get('mutates'):
                    faixa = (ultimo if ultimo == 'estourou' else '0' if ultimo == 0 else '<1k' if ultimo < 1000
                             else '1-3k' if ultimo < 3000 else '3-6k' if ultimo < 6000 else '6k+')
                    faixas[faixa][d.get('status')] += 1
                ultimo = None
    soma = sum(tempo.values()) or 1
    print('Tempo do backend:', {k: f'{v / 3600:.1f} h ({v / soma:.0%})' for k, v in tempo.items()})
    print('Raciocínio da decisão (caracteres) -> resultado da ação com efeito:')
    for faixa in ('0', '<1k', '1-3k', '3-6k', '6k+', 'estourou'):
        c = faixas[faixa]
        n = sum(c.values())
        if n:
            print(f'  {faixa:9} n={n:4} sucesso={c["success"] / n:.0%} incerto={c["uncertain"] / n:.0%}')
    if n_dec:
        print(f'Decisões/metas: {n_dec}; acima de {TETO_ROTINA} tokens: {acima} ({acima / n_dec:.0%}); '
              f'fração do texto acima do teto: {cortado / max(1, total_dec):.0%}')


if __name__ == '__main__':
    main(sys.argv[1:] or sorted(glob.glob(str(ROOT / 'entidades/*/runtime/diagnostics/hoshino_2026-1*.jsonl'))))
