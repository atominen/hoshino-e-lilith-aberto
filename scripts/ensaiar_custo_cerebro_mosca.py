"""Quanto custa simular em CPU uma rede LIF do tamanho do conectoma da mosca (FlyWire)?

Mede só o cálculo, com uma rede sintética de mesmo tamanho: ~139 mil neurônios
e de 3 a 15 milhões de ligações entre pares (o FlyWire tem ~50-54 milhões de
sinapses agrupadas em pares; a contagem exata de pares depende do corte usado).
O conteúdo das ligações não muda o custo; o que muda é tamanho, passo de tempo
e quantos neurônios disparam. Não baixa dados, não usa GPU nem modelo; grava
apenas o JSON de saída.

Uso:
  python3 -B scripts/ensaiar_custo_cerebro_mosca.py [--saida arquivo.json]
"""
import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
N = 139_255
PESTINHA_N = 470


def rede(n, ligacoes, rng):
    """CSR por neurônio pré-sináptico: indptr, alvos e pesos (float32)."""
    grau = rng.poisson(ligacoes / n, n).astype(np.int64)
    indptr = np.concatenate([[0], np.cumsum(grau)])
    alvos = rng.integers(0, n, indptr[-1], dtype=np.int32)
    pesos = (rng.standard_normal(indptr[-1]) * 0.05).astype(np.float32)
    return indptr, alvos, pesos


def medir(indptr, alvos, pesos, taxa_hz, dt_ms, passos, rng):
    n = len(indptr) - 1
    v = np.zeros(n, np.float32)
    decai = np.float32(np.exp(-dt_ms / 20.0))
    ruido = np.float32(0.02)
    p_disparo = taxa_hz * dt_ms / 1000
    t0 = time.perf_counter()
    disparos = 0
    for _ in range(passos):
        v *= decai
        v += ruido * rng.standard_normal(n, dtype=np.float32)
        # a atividade é imposta na taxa pedida para medir a propagação nessa taxa
        fired = np.flatnonzero(rng.random(n, dtype=np.float32) < p_disparo)
        disparos += len(fired)
        if len(fired):
            ini, fim = indptr[fired], indptr[fired + 1]
            tam = fim - ini
            idx = np.repeat(ini - np.cumsum(np.concatenate([[0], tam[:-1]])), tam) + np.arange(tam.sum())
            v += np.bincount(alvos[idx], weights=pesos[idx], minlength=n).astype(np.float32)
        v[fired] = 0.0
    dur = time.perf_counter() - t0
    por_passo = dur / passos
    passos_por_s = 1000 / dt_ms
    return dict(taxa_hz=taxa_hz, dt_ms=dt_ms, ms_por_passo=round(por_passo * 1000, 3),
                segundos_cpu_por_segundo_simulado=round(por_passo * passos_por_s, 2),
                disparos_por_passo=round(disparos / passos, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--saida', type=Path,
                        default=ROOT / 'compartilhado/runtime/ensaios/corpo-orbe-20261105/custo-cerebro-mosca.json')
    args = parser.parse_args()
    rng = np.random.default_rng(0)
    resultado = dict(cpu=platform.processor() or platform.machine(), neuronios=N, medidas=[],
                     observacao='um núcleo; numpy; atividade imposta; sem dinâmica sináptica com condutância')
    resultado['matriz_densa_estilo_pestinha_gb'] = round(N * N * 4 / 1e9, 1)
    for ligacoes in (3_000_000, 15_000_000):
        t = time.perf_counter()
        indptr, alvos, pesos = rede(N, ligacoes, rng)
        montagem = time.perf_counter() - t
        mem = (indptr.nbytes + alvos.nbytes + pesos.nbytes) / 1e6
        for taxa, dt, passos in ((2, 1.0, 300), (20, 1.0, 300), (2, 0.1, 300), (20, 0.1, 300)):
            m = medir(indptr, alvos, pesos, taxa, dt, passos, rng)
            m.update(ligacoes=ligacoes, memoria_mb=round(mem), montagem_s=round(montagem, 1))
            resultado['medidas'].append(m)
            print(json.dumps(m, ensure_ascii=False))
        del indptr, alvos, pesos
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
