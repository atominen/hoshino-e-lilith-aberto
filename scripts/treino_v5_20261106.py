"""Treino do corpus v5 nos três pesos originais até 12:00 de 06/11 (pedido humano 06/11).

Ordem: Hoshino 9B → Lilith 9B → Alistair 4B, cada um seguido da avaliação (perdas + auditoria).
O tempo de treino é recalculado antes de cada etapa a partir do que sobra até o prazo, reservando
as avaliações que faltam. Sem promoção: os candidatos ficam para teste humano.

O Alistair só começa com `pacote_identidade_v5/.alistair_pronto` (o corpus dele é escrito
enquanto a Hoshino treina); sem o sinal, espera enquanto ainda houver tempo útil.

  nohup python3 -I scripts/treino_v5_20261106.py > <log> 2>&1 &
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
from laboratorio import treinos_unificados as lab  # noqa: E402

HOME = (ROOT / 'laboratorio-local').resolve()
PRAZO = datetime(2026, 11, 6, 12, 0).timestamp()
FOLGA_S = 3 * 60
AVALIACAO_MIN = {'qwen35-9b': 11, 'alistair-4b': 8}
PESO = {'qwen35-9b': 1.0, 'alistair-4b': 0.6}
ETAPAS = [('qwen35-9b', 'hoshino', 1), ('qwen35-9b', 'lilith', 1), ('alistair-4b', 'alistair', 0)]
SINAL_ALISTAIR = HOME / 'pacote_identidade_v5' / '.alistair_pronto'
REGISTRO = HOME / 'controle-laboratorio' / 'treinamento-unificado' / 'treino-v5-20261106.json'


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def esperar(job_id):
    while True:
        row = lab.details(HOME, job_id)
        if row['state'] not in ('started', 'running', 'cancel_requested'):
            return row
        time.sleep(15)


def minutos_de_treino(restantes):
    livre = (PRAZO - time.time() - FOLGA_S) / 60 - sum(AVALIACAO_MIN[m] for m, _, _ in restantes)
    return int(livre * PESO[restantes[0][0]] / sum(PESO[m] for m, _, _ in restantes))


def main():
    resultado = []
    for i, (modelo, entidade, head_cpu) in enumerate(ETAPAS):
        if entidade == 'alistair':
            while not SINAL_ALISTAIR.exists() and minutos_de_treino(ETAPAS[i:]) > 15:
                log('aguardando corpus do Alistair')
                time.sleep(30)
        minutos = min(90, minutos_de_treino(ETAPAS[i:]))
        if minutos < 8:
            log('sem tempo para', entidade, minutos)
            resultado.append({'entidade': entidade, 'pulado': 'sem tempo'})
            continue
        # O laboratório só libera treino com medição (smoke) no mesmo corpus/base: ~1 min.
        smoke = lab.start(HOME, ROOT, modelo, entidade, 15, 'smoke', 'EXECUTAR_TREINO_UNIFICADO',
                          options={'rank': 4, 'head_cpu': head_cpu})
        log('medição', entidade, smoke['id'])
        medida = esperar(smoke['id'])
        if medida['state'] != 'completed' or not lab.measured_preset(HOME, modelo, entidade):
            log('medição falhou', entidade, medida['state'], medida.get('error'))
            resultado.append({'entidade': entidade, 'medicao': medida['id'], 'erro': medida.get('error') or medida['state']})
            REGISTRO.write_text(json.dumps(resultado, ensure_ascii=False, indent=1))
            continue
        minutos = min(90, minutos_de_treino(ETAPAS[i:]))
        opcoes = {'rank': 4, 'head_cpu': head_cpu, 'validation_steps': 50, 'checkpoint_steps': 100}
        job = lab.start(HOME, ROOT, modelo, entidade, minutos, 'train', 'EXECUTAR_TREINO_UNIFICADO', options=opcoes)
        log('treino', entidade, modelo, minutos, 'min', job['id'])
        treino = esperar(job['id'])
        etapa = {'entidade': entidade, 'modelo': modelo, 'minutos': minutos, 'treino': treino['id'],
                 'estado_treino': treino['state'], 'erro_treino': treino.get('error'), 'adaptador': treino.get('artifact')}
        log('treino terminou', entidade, treino['state'], treino.get('error'))
        if treino['state'] == 'completed' and treino.get('artifact'):
            av = lab.start(HOME, ROOT, modelo, entidade, 15, 'evaluate', 'EXECUTAR_TREINO_UNIFICADO',
                           candidate=treino['artifact'])
            log('avaliação', entidade, av['id'])
            row = esperar(av['id'])
            etapa.update(avaliacao=row['id'], estado_avaliacao=row['state'], erro_avaliacao=row.get('error'),
                         relatorio=row.get('artifact'))
            log('avaliação terminou', entidade, row['state'], row.get('error'))
        resultado.append(etapa)
        REGISTRO.write_text(json.dumps(resultado, ensure_ascii=False, indent=1))
    log('fim')


if __name__ == '__main__':
    main()
