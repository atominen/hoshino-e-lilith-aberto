"""Protótipo offline do corpo expressivo dos orbes com o núcleo original do Pestinha.

A rede fica depois do estado emocional: lê o que o overlay já recebe da Central
(estado da presença e `expression_profile`) e as interações com o próprio orbe
(cutucar, arrastar) e devolve só a expressão do corpo. Não alimenta decisões,
emoções, humor nem prompt. Este ensaio não importa `app.*`, não chama modelo,
lê os bancos em modo imutável e grava apenas num diretório temporário e no JSON
de saída.

Uso:
  python3 -B scripts/ensaiar_corpo_orbe_pestinha.py <checkout-do-pestinha> [--saida arquivo.json]

Critérios definidos antes da rodada (05/11/2026):
  1. coerência: com uma emoção real estável, o rótulo do corpo não contradiz
     a valência da emoção em pelo menos 95% das amostras;
  2. habituação: a resposta à décima cutucada seguida é menor que à primeira e
     volta a pelo menos 80% da inicial após pausa de 10 min;
  3. individualidade: Hoshino e Lilith diferem mais entre si do que a mesma
     entidade entre sementes de ruído;
  4. persistência: o estado salvo volta com recuperação pelo tempo decorrido e
     é recusado para outra entidade, outra revisão ou arquivo adulterado;
  5. custo: mediana abaixo de 5 ms por passo de 100 ms (5% de um núcleo);
  6. isolamento: nenhum banco ou estado_mente das entidades muda durante o ensaio.
"""
import argparse
import hashlib
import json
import math
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/ui'))
from corpo_pulsado import (  # noqa: E402  o ensaio mede o módulo implantado
    DT, STEP_MS, EXPRESSAO, TONUS, TEMPERAMENTOS, UPSTREAM_COMMIT, CorpoPulsado,
    carregar_nucleo, perfil_de, semente)

ENTIDADES = {e: TEMPERAMENTOS[e] for e in ('lilith', 'hoshino')}
VALENCIA_REAL = {'alegria': 1, 'orgulho': 1, 'afeto': 1, 'amor': 1,
                 'curiosidade': 0, 'desejo': 0, 'tedio': 0,
                 'raiva': -1, 'tristeza': -1, 'vergonha': -1, 'medo': -1, 'apreensao': -1}
VALENCIA_CORPO = {'feliz': 1, 'contente': 1, 'bravo': -1, 'triste': -1}
ESPERADO = {
    'alegria': {'feliz', 'contente'}, 'orgulho': {'feliz', 'contente'},
    'afeto': {'contente', 'feliz'}, 'amor': {'contente', 'feliz'},
    'curiosidade': {'curioso'}, 'desejo': {'curioso'},
    'raiva': {'bravo'}, 'tristeza': {'triste'}, 'vergonha': {'triste'},
    'tedio': {'observando'}, 'medo': {'observando', 'assustado'},
    'apreensao': {'observando', 'assustado'}, None: {'observando'},
}


def meias_vidas():
    """Lê as meias-vidas de app/mind/emotions.py sem importar o módulo."""
    texto = (ROOT / 'app/mind/emotions.py').read_text(encoding='utf-8')
    out, atual = {}, None
    for linha in texto.splitlines():
        chave = re.match(r"""\s{4}["'](\w+)["']\s*:\s*(\{|dict\()""", linha)
        if chave:
            atual = chave.group(1)
        valor = re.search(r"""["']?meia_vida_min["']?\s*[:=]\s*(\d+)""", linha)
        if valor and atual:
            out[atual] = int(valor.group(1))
    return out


def rodar(corpo, status, perfil, segundos, reduzido=False):
    return [corpo.passo(status, perfil, reduzido) for _ in range(int(round(segundos / DT)))]


def contradiz(emocao, rotulo):
    real = VALENCIA_REAL.get(emocao, 0)
    corpo = VALENCIA_CORPO.get(rotulo, 0)
    return (real != 0 and corpo == -real) or (real == 0 and corpo == -1)


def ensaio_coerencia(nucleo, revisao, sementes):
    linhas = []
    for entidade in ENTIDADES:
        for emocao in [None, *TONUS]:
            rotulos = Counter()
            for s in sementes:
                corpo = CorpoPulsado(nucleo, entidade, revisao, ruido=s)
                perfil = perfil_de({emocao: 0.6} if emocao else {})
                rodar(corpo, 'awake', perfil, 10)                       # aquecimento
                rotulos.update(r['rotulo'] for r in rodar(corpo, 'awake', perfil, 15))
            n = sum(rotulos.values())
            linhas.append(dict(
                entidade=entidade, emocao=emocao or 'nenhuma',
                expressa=round(sum(c for r, c in rotulos.items() if r in ESPERADO[emocao]) / n, 3),
                contradiz=round(sum(c for r, c in rotulos.items() if emocao and contradiz(emocao, r)) / n, 3),
                rotulos=dict(rotulos.most_common())))
    return linhas


def linha_do_tempo_real(db, meias):
    con = sqlite3.connect(f'file:{db}?mode=ro&immutable=1', uri=True)
    rows = con.execute('select created_at, emocao, intensidade from emotion_log '
                       'order by created_at').fetchall()
    con.close()
    return [(datetime.fromisoformat(t), e, float(i)) for t, e, i in rows if e in meias]


def forcas_em(instante, eventos, meias):
    ultimo = {}
    for t, e, i in eventos:
        if t > instante:
            break
        ultimo[e] = (t, i)
    return {e: i * 0.5 ** (((instante - t).total_seconds() / 60) / meias[e])
            for e, (t, i) in ultimo.items()}


def ensaio_replay(nucleo, revisao, db, meias, amostras, sementes):
    eventos = linha_do_tempo_real(db, meias)
    if not eventos:
        return dict(amostras=0)
    inicio, fim = eventos[0][0], eventos[-1][0] + timedelta(hours=2)
    passo = (fim - inicio) / amostras
    instantes = [inicio + passo * (k + 0.5) for k in range(amostras)]
    total, expressa, contra, por_dominante = 0, 0, 0, Counter()
    exemplos = []
    for k, instante in enumerate(instantes):
        perfil = perfil_de(forcas_em(instante, eventos, meias))
        dom = perfil['dominant']
        corpo = CorpoPulsado(nucleo, 'lilith', revisao, ruido=sementes[k % len(sementes)])
        rodar(corpo, 'awake', perfil, 10)
        rot = Counter(r['rotulo'] for r in rodar(corpo, 'awake', perfil, 10))
        n = sum(rot.values())
        total += n
        expressa += sum(c for r, c in rot.items() if r in ESPERADO.get(dom, set()))
        contra += sum(c for r, c in rot.items() if dom and contradiz(dom, r))
        por_dominante[dom or 'nenhuma'] += 1
        if len(exemplos) < 8:
            exemplos.append(dict(instante=instante.isoformat(timespec='seconds'), dominante=dom,
                                 emocoes={e: round(v, 2) for e, v in perfil['emotions'].items()},
                                 corpo=dict(rot.most_common(3))))
    return dict(amostras=len(instantes), periodo=[inicio.isoformat(), fim.isoformat()],
                dominantes=dict(por_dominante), expressa=round(expressa / total, 3),
                contradiz=round(contra / total, 3), exemplos=exemplos)


def resposta_cutucada(corpo, perfil):
    """Pico da soma dos motores de expressão nos 3 s após uma cutucada, acima do repouso."""
    base = sum(corpo.brain.motor_activity()[m] for m in EXPRESSAO)
    corpo.cutucar()
    pico, rotulos = 0.0, Counter()
    for r in rodar(corpo, 'awake', perfil, 3):
        pico = max(pico, sum(r['motores'].values()) - base)
        rotulos[r['rotulo']] += 1
    return pico, rotulos


def ensaio_habituacao(nucleo, revisao, sementes):
    perfil = perfil_de({})
    out = {}
    for entidade in ENTIDADES:
        series, depois, eficacia = [], [], []
        for s in sementes:
            corpo = CorpoPulsado(nucleo, entidade, revisao, ruido=s)
            rodar(corpo, 'awake', perfil, 5)
            serie = []
            for _ in range(10):
                pico, _ = resposta_cutucada(corpo, perfil)
                serie.append(pico)
                rodar(corpo, 'awake', perfil, 1)                        # uma cutucada a cada 4 s
            eficacia.append(corpo.brain.efficacy()['POKE'])
            rodar(corpo, 'awake', perfil, 600)                          # pausa de 10 min
            depois.append(resposta_cutucada(corpo, perfil)[0])
            series.append(serie)
        media = [statistics.mean(c) for c in zip(*series)]
        out[entidade] = dict(
            resposta_hz=[round(x, 1) for x in media],
            decima_sobre_primeira=round(media[-1] / media[0], 3),
            eficacia_poke_apos_10=round(statistics.mean(eficacia), 3),
            apos_pausa_sobre_primeira=round(statistics.mean(depois) / media[0], 3))
    return out


def roteiro_individual(corpo):
    perfil = perfil_de({})
    rotulos = Counter()
    for status, segundos, acao in [('awake', 5, None), ('awake', 4, 'arrastar'),
                                   ('awake', 6, 'soltar'), ('awake', 3, 'cutucar'),
                                   ('working', 15, None), ('awake', 5, 'cutucar'),
                                   ('sleeping', 3, None)]:
        if acao == 'arrastar':
            corpo.arrastar(True)
        elif acao == 'soltar':
            corpo.arrastar(False)
        elif acao == 'cutucar':
            corpo.cutucar()
        rotulos.update(r['rotulo'] for r in rodar(corpo, status, perfil, segundos))
    return rotulos


def distancia(a, b):
    na, nb = sum(a.values()), sum(b.values())
    return 0.5 * sum(abs(a[k] / na - b[k] / nb) for k in set(a) | set(b))


def ensaio_individualidade(nucleo, revisao, sementes):
    dist = {e: [roteiro_individual(CorpoPulsado(nucleo, e, revisao, ruido=s)) for s in sementes]
            for e in ENTIDADES}
    dentro = [distancia(x, y) for e in dist for i, x in enumerate(dist[e]) for y in dist[e][i + 1:]]
    entre = [distancia(x, y) for x in dist['hoshino'] for y in dist['lilith']]
    return dict(dentro_da_entidade=round(statistics.mean(dentro), 3) if dentro else None,
                entre_entidades=round(statistics.mean(entre), 3),
                rotulos={e: dict(sum(v, Counter()).most_common()) for e, v in dist.items()})


def ensaio_persistencia(nucleo, revisao, pasta):
    perfil = perfil_de({})
    corpo = CorpoPulsado(nucleo, 'lilith', revisao, ruido=1)
    for _ in range(8):
        corpo.cutucar()
        rodar(corpo, 'awake', perfil, 4)
    antes = corpo.brain.efficacy()['POKE']
    arquivo = pasta / 'corpo_lilith.json'
    corpo.salvar(arquivo)
    tau = float(corpo.brain.s_tau_rec[corpo.brain.pool('POKE')['start']])

    mesma = CorpoPulsado(nucleo, 'lilith', revisao, ruido=2)
    ok_mesma, _ = mesma.carregar(arquivo)
    imediato = mesma.brain.efficacy()['POKE']

    dados = json.loads(arquivo.read_text())
    dados['saved_at'] -= 600
    envelhecido = pasta / 'corpo_lilith_10min.json'
    envelhecido.write_text(json.dumps(dados))
    pausa = CorpoPulsado(nucleo, 'lilith', revisao, ruido=3)
    ok_pausa, _ = pausa.carregar(envelhecido)
    recuperado = pausa.brain.efficacy()['POKE']
    esperado = 1 - (1 - antes) * math.exp(-600 / tau)

    outra = CorpoPulsado(nucleo, 'hoshino', revisao, ruido=4)
    eficacia_outra = outra.brain.efficacy()['POKE']
    ok_outra, motivo_outra = outra.carregar(arquivo)
    revisao_nova = CorpoPulsado(nucleo, 'lilith', revisao + '-x', ruido=5)
    ok_rev, motivo_rev = revisao_nova.carregar(arquivo)

    adulterado = dict(dados, efficacy=dict(dados['efficacy'], POKE=[1.5] * len(dados['efficacy']['POKE'])))
    ruim = pasta / 'corpo_lilith_adulterado.json'
    ruim.write_text(json.dumps(adulterado))
    vitima = CorpoPulsado(nucleo, 'lilith', revisao, ruido=6)
    ok_ruim, motivo_ruim = vitima.carregar(ruim)

    # semente trocada dentro de um arquivo com a identidade certa
    trocada = pasta / 'corpo_lilith_semente.json'
    trocada.write_text(json.dumps(dict(dados, seed=semente('hoshino'))))
    ok_semente, motivo_semente = CorpoPulsado(nucleo, 'lilith', revisao, ruido=7).carregar(trocada)
    return dict(
        eficacia_poke_salva=round(antes, 4),
        recarga_imediata=dict(aceita=ok_mesma, eficacia=round(imediato, 4)),
        recarga_apos_10min=dict(aceita=ok_pausa, eficacia=round(recuperado, 4),
                                esperado_pela_formula=round(esperado, 4)),
        outra_entidade=dict(aceita=ok_outra, motivo=motivo_outra,
                            estado_intacto=outra.brain.efficacy()['POKE'] == eficacia_outra),
        outra_revisao=dict(aceita=ok_rev, motivo=motivo_rev),
        valores_fora_do_dominio=dict(aceita=ok_ruim, motivo=motivo_ruim,
                                     estado_intacto=vitima.brain.efficacy()['POKE'] == 1.0),
        semente_trocada=dict(aceita=ok_semente, motivo=motivo_semente))


def ensaio_reduzido(nucleo, revisao):
    corpo = CorpoPulsado(nucleo, 'lilith', revisao, ruido=1)
    perfil = perfil_de({'alegria': 0.7})
    corpo.cutucar()
    amostra = rodar(corpo, 'awake', perfil, 6, reduzido=True)
    return dict(amplitude_max=max(r['animacao']['amplitude_px'] for r in amostra),
                sobressaltos=sum(r['animacao']['sobressalto'] for r in amostra),
                rotulos=dict(Counter(r['rotulo'] for r in amostra)))


def custo(nucleo, revisao, passos=600):
    corpo = CorpoPulsado(nucleo, 'lilith', revisao, ruido=1)
    perfil = perfil_de({'curiosidade': 0.6})
    tempos = []
    for k in range(passos):
        if k % 50 == 0:
            corpo.cutucar()
        t = time.perf_counter()
        corpo.passo('working', perfil)
        tempos.append((time.perf_counter() - t) * 1000)
    mediana = statistics.median(tempos)
    return dict(passos=passos, mediana_ms=round(mediana, 2),
                p95_ms=round(sorted(tempos)[int(0.95 * passos)], 2),
                fracao_de_um_nucleo_a_10hz=round(mediana / STEP_MS, 3))


def marcas_protegidas():
    alvos = []
    for entidade in ('hoshino', 'lilith', 'alistair'):
        base = ROOT / 'entidades' / entidade
        alvos += list((base / 'memory/sqlite').glob('*.db')) + list((base / 'runtime').glob('estado_mente.json'))
        alvos += list((base / 'runtime').glob('history.sqlite3'))
    return {str(p.relative_to(ROOT)): (p.stat().st_mtime_ns, p.stat().st_size) for p in alvos if p.exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--saida', type=Path,
                        default=ROOT / 'compartilhado/runtime/ensaios/corpo-orbe-20261105/resultado.json')
    parser.add_argument('--sementes', type=int, default=3)
    parser.add_argument('--amostras-replay', type=int, default=30)
    args = parser.parse_args()

    commit = subprocess.run(['git', '-C', str(args.upstream), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True).stdout.strip()
    if commit != UPSTREAM_COMMIT:
        sys.exit(f'checkout do Pestinha em {commit or "?"}; esperado {UPSTREAM_COMMIT}')
    nucleo, revisao = carregar_nucleo(args.upstream)

    marcas = marcas_protegidas()
    sementes = list(range(1, args.sementes + 1))
    inicio = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='corpo-orbe-') as pasta:
        resultado = dict(
            upstream=commit, revisao_corpo=revisao,
            sementes_topologia={e: semente(e) for e in ENTIDADES}, temperamentos=ENTIDADES,
            tonus=TONUS,
            coerencia=ensaio_coerencia(nucleo, revisao, sementes),
            replay_lilith=ensaio_replay(nucleo, revisao, ROOT / 'entidades/lilith/memory/sqlite/lilith.db',
                                        meias_vidas(), args.amostras_replay, sementes),
            habituacao_cutucada=ensaio_habituacao(nucleo, revisao, sementes),
            individualidade=ensaio_individualidade(nucleo, revisao, sementes),
            persistencia=ensaio_persistencia(nucleo, revisao, Path(pasta)),
            movimento_reduzido=ensaio_reduzido(nucleo, revisao),
            custo=custo(nucleo, revisao),
        )
    depois = marcas_protegidas()
    resultado['isolamento'] = dict(arquivos_conferidos=len(marcas),
                                   alterados=sorted(k for k in marcas if depois.get(k) != marcas[k]))
    resultado['duracao_s'] = round(time.monotonic() - inicio, 1)

    c = resultado['coerencia']
    h = resultado['habituacao_cutucada']
    p = resultado['persistencia']
    i = resultado['individualidade']
    resultado['criterios'] = {
        '1_coerencia': all(x['contradiz'] <= 0.05 for x in c) and resultado['replay_lilith'].get('contradiz', 1) <= 0.05,
        '2_habituacao': all(v['decima_sobre_primeira'] < 1 and v['apos_pausa_sobre_primeira'] >= 0.8 for v in h.values()),
        '3_individualidade': i['dentro_da_entidade'] is not None and i['entre_entidades'] > i['dentro_da_entidade'],
        '4_persistencia': (p['recarga_imediata']['aceita'] and p['recarga_apos_10min']['aceita']
                           and abs(p['recarga_apos_10min']['eficacia'] - p['recarga_apos_10min']['esperado_pela_formula']) < 0.01
                           and not any(p[k]['aceita'] for k in ('outra_entidade', 'outra_revisao',
                                                                'valores_fora_do_dominio', 'semente_trocada'))),
        '5_custo': resultado['custo']['mediana_ms'] < 5,
        '6_isolamento': not resultado['isolamento']['alterados'],
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(criterios=resultado['criterios'], saida=str(args.saida),
                          duracao_s=resultado['duracao_s']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
