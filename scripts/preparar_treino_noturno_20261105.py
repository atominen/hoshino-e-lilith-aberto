"""Prepara a sessão única de 05→06/11: medições físicas dos 9B, prévia e agendamento.

Pedido humano 05/11: treinar os três originais (4B Alistair, 9B Hoshino, 9B Lilith) das
23:00 às 12:00 com os materiais default avaliados. Usa somente o laboratório e a Central
existentes; não acorda entidades nem promove candidatos.

  python3 -I scripts/preparar_treino_noturno_20261105.py medir hoshino|lilith
  python3 -I scripts/preparar_treino_noturno_20261105.py previa
  python3 -I scripts/preparar_treino_noturno_20261105.py agendar
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
from laboratorio import treinos_unificados as lab  # noqa: E402
from laboratorio import sessao_personalizada as custom  # noqa: E402

HOME = (ROOT / 'laboratorio-local').resolve()
JANELA = dict(starts_at='2026-11-05T23:00', ends_at='2026-11-06T12:00', evaluation_minutes=30)


def medir(entidade):
    job = lab.start(HOME, ROOT, 'qwen35-9b', entidade, 15, 'smoke', 'EXECUTAR_TREINO_UNIFICADO',
                    options={'rank': 4, 'head_cpu': 1})
    print('medição iniciada', job, flush=True)
    while True:
        row = lab.details(HOME, job['id'])
        if row['state'] not in ('started', 'running', 'cancel_requested'):
            break
        time.sleep(10)
    print(json.dumps({k: row.get(k) for k in ('id', 'state', 'error', 'artifact')}, ensure_ascii=False))
    print('preset medido:', lab.measured_preset(HOME, 'qwen35-9b', entidade))


def esperar(job):
    while True:
        row = lab.details(HOME, job['id'])
        if row['state'] not in ('started', 'running', 'cancel_requested'):
            return row
        time.sleep(10)


def treino_curto(modelo, entidade, head_cpu):
    """Mede throughput e tamanho de checkpoint exigidos pelo plano (não é candidato)."""
    job = lab.start(HOME, ROOT, modelo, entidade, 5, 'train', 'EXECUTAR_TREINO_UNIFICADO',
                    options={'rank': 4, 'head_cpu': head_cpu, 'max_steps': 24, 'checkpoint_steps': 8,
                             'validation_steps': 8})
    print('treino curto iniciado', job, flush=True)
    row = esperar(job)
    print(json.dumps({k: row.get(k) for k in ('id', 'state', 'error', 'artifact')}, ensure_ascii=False))
    m = lab.measured_preset(HOME, modelo, entidade)
    b = lab.benchmark_result(m) if m else {}
    print('medição escolhida:', m and m['evidence'], {k: b.get(k) for k in ('updates_per_optimization_hour', 'checkpoint_bytes', 'peak_vram_gib')})


def previa():
    p = custom.preview(HOME, JANELA)
    resumo = {k: p.get(k) for k in ('allowed', 'blockers', 'train_minutes_per_model', 'evaluation_minutes_per_model',
                                     'reserve_minutes', 'projected_checkpoint_bytes', 'disk_free_bytes')}
    resumo['etapas'] = [(t['action'], t['model'], t['entity'], t['minutes']) for t in p['tasks']]
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    return p


def agendar():
    print(json.dumps(lab.supervisor_call(ROOT, '/schedule-once', dict(JANELA, confirm='AGENDAR_TRES_ORIGINAIS')),
                     ensure_ascii=False)[:1500])


if __name__ == '__main__':
    acao = sys.argv[1]
    if acao == 'medir':
        medir(sys.argv[2])
    elif acao == 'curto':
        treino_curto(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    elif acao == 'previa':
        previa()
    else:
        agendar()
