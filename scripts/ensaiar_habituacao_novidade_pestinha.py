"""Replay offline dos eventos reais de 'novidade' da Lilith: regra atual x habituação.

Só leitura do banco (mode=ro&immutable=1); não importa `app.*`; grava apenas o JSON de saída.
Braços:
  A atual      : composição de emotions.disparar, base 0,5, meia-vida da curiosidade, sem habituação
  B LIF        : LIFBrain original; ganho = eficácia média de NOVELTY no início do evento,
                 pulso de 4 s simulado (NOVELTY 1,0 com decaimento de 3 s) e recuperação
                 analítica entre eventos (mesma fórmula do load() upstream)
  C analítico  : a mesma depressão sináptica sem spikes (disparos esperados por evento)
  D percepção  : regra atual, contando só rótulos de janela distintos sem o ícone giratório
  E nova regra : D + habituação de app/mind/habituation.py (REGRAS['novidade']), a versão implantada

Uso:
  python3 -B scripts/ensaiar_habituacao_novidade_pestinha.py <checkout-do-pestinha> [--saida arquivo.json]
"""
import argparse
import json
import math
import sqlite3
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = '984fb8677093cd868bf4f9712a43f19b44215f75'
BASE = 0.5                       # GATILHOS['novidade'] = [('curiosidade', 0.50)]
MEIA_VIDA_S = 240 * 60           # EMOCOES['curiosidade']['meia_vida_min']
GIRATORIOS = '◐◑◒◓✳⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ '


def compor(instantes, ganhos):
    out, valor, ultimo = [], 0.0, None
    for t, g in zip(instantes, ganhos):
        if ultimo is not None:
            valor *= 0.5 ** ((t - ultimo) / MEIA_VIDA_S)
        valor = valor + (1 - valor) * min(1.0, BASE * g)
        out.append(valor)
        ultimo = t
    return out


def resumo(nome, valores, ganhos=None):
    d = dict(braco=nome, media=round(statistics.mean(valores), 3),
             eventos_ge_0_9=sum(v >= 0.9 for v in valores), n=len(valores))
    if ganhos:
        d.update(ganho_min=round(min(ganhos), 3), ganho_mediano=round(statistics.median(ganhos), 3))
    return d


def normalizar(rotulo):
    return rotulo.replace('apareceu ', '', 1).lstrip(GIRATORIOS).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--db', type=Path, default=ROOT / 'entidades/lilith/memory/sqlite/lilith.db')
    parser.add_argument('--saida', type=Path,
                        default=ROOT / 'compartilhado/runtime/ensaios/corpo-orbe-20261105/replay-novidade.json')
    args = parser.parse_args()
    commit = subprocess.run(['git', '-C', str(args.upstream), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True).stdout.strip()
    if commit != UPSTREAM_COMMIT:
        sys.exit(f'checkout do Pestinha em {commit or "?"}; esperado {UPSTREAM_COMMIT}')
    sys.path.insert(0, str(args.upstream.resolve()))
    import numpy as np
    from pestinha.core.nervous_system import LIFBrain, SENSORY_SPEC

    marca = args.db.stat().st_mtime_ns
    con = sqlite3.connect(f'file:{args.db}?mode=ro&immutable=1', uri=True)
    rows = con.execute("select created_at, intensidade, motivo from emotion_log "
                       "where gatilho='novidade' order by created_at").fetchall()
    con.close()
    ts = [datetime.fromisoformat(r[0]).timestamp() for r in rows]
    registrado = [r[1] for r in rows]
    rotulos = [r[2] or '' for r in rows]

    a = compor(ts, [1.0] * len(ts))

    _, taxa, d, tau = SENSORY_SPEC['NOVELTY']
    brain = LIFBrain(seed=7)
    brain.rng = np.random.default_rng(7)
    pool = brain.pool('NOVELTY')
    sl = slice(pool['start'], pool['start'] + pool['n'])
    ganhos_b, ultimo, cpu = [], None, []
    for t in ts:
        if ultimo is not None and t - ultimo - 4.0 > 0:
            brain.p[sl] = 1 - (1 - brain.p[sl]) * math.exp(-(t - ultimo - 4.0) / tau)
        ganhos_b.append(float(brain.p[sl].mean()))
        inicio = time.perf_counter()
        for k in range(40):
            brain.stimulate({'NOVELTY': math.exp(-(k * 0.1) / 3.0)})
            brain.step(100)
        cpu.append(time.perf_counter() - inicio)
        ultimo = t
    b = compor(ts, ganhos_b)

    esperados = taxa * sum(math.exp(-(k * 0.1) / 3.0) * 0.1 for k in range(40))
    ganhos_c, p, ultimo = [], 1.0, None
    for t in ts:
        if ultimo is not None:
            p = 1 - (1 - p) * math.exp(-max(0.0, t - ultimo - 4.0) / tau)
        ganhos_c.append(p)
        p *= (1 - d) ** esperados
        ultimo = t
    c = compor(ts, ganhos_c)

    vistos, mantidos = set(), []
    for t, r in zip(ts, rotulos):
        if normalizar(r) not in vistos:
            vistos.add(normalizar(r))
            mantidos.append(t)
    dvals = compor(mantidos, [1.0] * len(mantidos))
    mesma_janela = janela_repetida(rotulos)

    fator, tau_min, piso = regra_novidade()
    ganhos_e, g, ultimo = [], 1.0, None
    for t in mantidos:
        if ultimo is not None:
            g = 1 - (1 - g) * math.exp(-(t - ultimo) / 60 / tau_min)
        ganhos_e.append(g)
        g = max(piso, g * fator)
        ultimo = t
    e = compor(mantidos, ganhos_e)

    resultado = dict(
        upstream=commit, eventos=len(ts), periodo=[rows[0][0], rows[-1][0]],
        sanidade_A_vs_log=dict(media_log=round(statistics.mean(registrado), 3),
                               erro_abs_medio=round(statistics.mean(abs(x - y) for x, y in zip(a, registrado)), 3)),
        A=resumo('atual', a), B=resumo('LIF Pestinha', b, ganhos_b), C=resumo('analítico', c, ganhos_c),
        D=dict(resumo('percepção corrigida', dvals), rotulos_distintos=len(mantidos)),
        E=dict(resumo('percepção + habituação (implantada)', e, ganhos_e),
               regra=dict(fator=fator, recuperacao_min=tau_min, piso=piso),
               primeiras_novidades=[round(x, 3) for x in e[:6]]),
        janela_mais_repetida=mesma_janela,
        disparos_esperados_por_neuronio_por_evento=round(esperados, 1),
        cpu_ms_por_evento_LIF=round(1000 * statistics.median(cpu), 1),
        banco_inalterado=args.db.stat().st_mtime_ns == marca,
    )
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


def regra_novidade():
    """Lê REGRAS['novidade'] de app/mind/habituation.py sem importar o app."""
    import re
    texto = (ROOT / 'app/mind/habituation.py').read_text(encoding='utf-8')
    m = re.search(r"'novidade':\s*\(([\d.]+),\s*(\d+),\s*([\d.]+)\)", texto)
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


def janela_repetida(rotulos):
    contagem = {}
    for r in rotulos:
        contagem[normalizar(r)] = contagem.get(normalizar(r), 0) + 1
    nome = max(contagem, key=contagem.get)
    return dict(rotulo=nome, eventos=contagem[nome],
                variantes_do_titulo=sorted({r for r in rotulos if normalizar(r) == nome})[:6])


if __name__ == '__main__':
    main()
