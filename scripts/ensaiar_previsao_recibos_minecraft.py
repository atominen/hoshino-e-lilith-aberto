"""Os recibos do Minecraft da Lilith têm padrão aprendível além da taxa de falha por ação?

Leitura imutável de entidades/lilith/runtime/history.sqlite3; não importa `app.*`;
sem LLM; grava apenas o JSON de saída.

Alvo: uma ação (exceto state/connect/disconnect) termina sem efeito, ou seja,
`ok` falso ou `sem_ganho` verdadeiro no recibo `minecraft.rpc.end`.

Comparação, definida antes da rodada (05/11/2026):
  B0  taxa global de falha
  B1  taxa de falha por tipo de ação (suavizada)                  <- referência
  B2  B1 + "a mesma ação falhou na última tentativa da sessão"
  M1  regressão logística com tipo, histórico recente e estado do jogo
  M2  árvores com gradiente (pequenas), mesmas entradas
Avaliação: validação cruzada agrupada por sessão (cada sessão fica inteira fora
do treino) e divisão temporal 70/30. Critério de avanço: um modelo ganha de B1
em log loss nas duas avaliações e, na agrupada, o intervalo de 95% por
reamostragem de sessões da diferença fica inteiro abaixo de zero.

Uso:
  python3 -B scripts/ensaiar_previsao_recibos_minecraft.py [--saida arquivo.json]
"""
import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IGNORAR = {'state', 'connect', 'disconnect'}


def carregar(db):
    con = sqlite3.connect(f'file:{db}?mode=ro&immutable=1', uri=True)
    rows = con.execute("select ts, session_id, data from events where kind='minecraft.rpc.end' "
                       "order by ts").fetchall()
    con.close()
    acoes, ultimo_estado = [], {}
    for ts, sessao, data in rows:
        d = json.loads(data)
        r = d.get('result') if isinstance(d.get('result'), dict) else {}
        if d.get('action') == 'state':
            if r.get('health') is not None:
                ultimo_estado[sessao] = r
            continue
        if d.get('action') in IGNORAR:
            continue
        estado = ultimo_estado.get(sessao, {})
        inventario = estado.get('inventory') or []
        proximos = estado.get('nearbyEntities') or []
        acoes.append(dict(
            t=datetime.fromisoformat(ts).timestamp(), sessao=sessao or '?', acao=d.get('action'),
            falhou=int((not d.get('ok')) or bool(r.get('sem_ganho'))),
            vida=float(estado.get('health') or 20), fome=float(estado.get('food') or 20),
            itens=len(inventario), segurando=int(bool(estado.get('heldItem'))),
            proximos=len(proximos), tem_estado=int(bool(estado))))
    return acoes


def caracteristicas(acoes, tipos):
    X, ult_sessao, janela, ultima_por_tipo, t_ant, acao_ant = [], None, deque(maxlen=5), {}, None, None
    for a in acoes:
        if a['sessao'] != ult_sessao:
            janela.clear(); ultima_por_tipo.clear(); t_ant = acao_ant = None
            ult_sessao = a['sessao']
        tipo = [1.0 if a['acao'] == k else 0.0 for k in tipos]
        hist = [
            float(sum(janela)), float(len(janela)),
            float(ultima_por_tipo.get(a['acao'], -1) == 1), float(ultima_por_tipo.get(a['acao'], -1) == 0),
            float(acao_ant == a['acao']),
            math.log1p(a['t'] - t_ant) if t_ant else 0.0,
        ]
        jogo = [a['vida'] / 20, a['fome'] / 20, a['itens'] / 36, a['segurando'], a['proximos'] / 10, a['tem_estado']]
        X.append(tipo + hist + jogo)
        janela.append(a['falhou']); ultima_por_tipo[a['acao']] = a['falhou']
        t_ant, acao_ant = a['t'], a['acao']
    return np.array(X)


def logloss(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def auc(y, p):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None


def prever(treino, teste, X, y, acoes, ultima_falha):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    out = {}
    out['B0'] = np.full(len(teste), (y[treino].sum() + 1) / (len(treino) + 2))
    por_tipo = defaultdict(lambda: [0, 0])
    for i in treino:
        por_tipo[acoes[i]['acao']][0] += y[i]; por_tipo[acoes[i]['acao']][1] += 1
    glob = out['B0'][0]
    taxa = lambda k: (por_tipo[k][0] + 2 * glob) / (por_tipo[k][1] + 2)
    out['B1'] = np.array([taxa(acoes[i]['acao']) for i in teste])
    rep = [y[i] for i in treino if ultima_falha[i]]
    taxa_rep = (sum(rep) + 2 * glob) / (len(rep) + 2)
    out['B2'] = np.array([max(taxa(acoes[i]['acao']), taxa_rep) if ultima_falha[i] else taxa(acoes[i]['acao'])
                          for i in teste])
    if y[treino].sum() >= 3:
        esc = StandardScaler().fit(X[treino])
        m1 = LogisticRegression(C=0.3, max_iter=2000).fit(esc.transform(X[treino]), y[treino])
        out['M1'] = m1.predict_proba(esc.transform(X[teste]))[:, 1]
        m2 = HistGradientBoostingClassifier(max_depth=3, max_iter=80, learning_rate=0.05,
                                            min_samples_leaf=20, l2_regularization=1.0,
                                            random_state=0).fit(X[treino], y[treino])
        out['M2'] = m2.predict_proba(X[teste])[:, 1]
    else:
        out['M1'] = out['M2'] = out['B1']
    return out


def resumo(y, preds):
    return {k: dict(log_loss=round(float(logloss(y, p).mean()), 4),
                    brier=round(float(((p - y) ** 2).mean()), 4),
                    auc=None if auc(y, p) is None else round(auc(y, p), 3))
            for k, p in preds.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--db', type=Path, default=ROOT / 'entidades/lilith/runtime/history.sqlite3')
    parser.add_argument('--saida', type=Path,
                        default=ROOT / 'compartilhado/runtime/ensaios/corpo-orbe-20261105/previsao-recibos.json')
    args = parser.parse_args()
    marca = args.db.stat().st_mtime_ns
    acoes = carregar(args.db)
    tipos = sorted({a['acao'] for a in acoes})
    X = caracteristicas(acoes, tipos)
    y = np.array([a['falhou'] for a in acoes], dtype=float)
    ultima_falha = X[:, len(tipos) + 2] == 1.0
    sessoes = np.array([a['sessao'] for a in acoes])

    # validação agrupada por sessão
    unicas = sorted(set(sessoes), key=lambda s: min(a['t'] for a in acoes if a['sessao'] == s))
    dobras = [unicas[k::5] for k in range(5)]
    oof = {k: np.zeros(len(y)) for k in ('B0', 'B1', 'B2', 'M1', 'M2')}
    for dobra in dobras:
        teste = np.where(np.isin(sessoes, dobra))[0]
        treino = np.where(~np.isin(sessoes, dobra))[0]
        for k, p in prever(treino, teste, X, y, acoes, ultima_falha).items():
            oof[k][teste] = p
    rng = np.random.default_rng(0)
    por_sessao = {s: np.where(sessoes == s)[0] for s in unicas}
    ic = {}
    for k in ('B2', 'M1', 'M2'):
        diff = logloss(y, oof[k]) - logloss(y, oof['B1'])
        amostras = []
        for _ in range(2000):
            idx = np.concatenate([por_sessao[s] for s in rng.choice(unicas, len(unicas))])
            amostras.append(diff[idx].mean())
        ic[k] = [round(float(np.percentile(amostras, 2.5)), 4), round(float(np.percentile(amostras, 97.5)), 4)]

    corte = int(0.7 * len(y))
    treino, teste = np.arange(corte), np.arange(corte, len(y))
    temporal = prever(treino, teste, X, y, acoes, ultima_falha)

    agr, tmp = resumo(y, oof), resumo(y[teste], temporal)
    vence = {k: agr[k]['log_loss'] < agr['B1']['log_loss'] and tmp[k]['log_loss'] < tmp['B1']['log_loss']
             and ic[k][1] < 0 for k in ('B2', 'M1', 'M2')}
    falhas_por_tipo = Counter(a['acao'] for a in acoes if a['falhou'])
    resultado = dict(
        dados=dict(acoes=len(y), falhas=int(y.sum()), sessoes=len(unicas),
                   acoes_por_tipo=dict(Counter(a['acao'] for a in acoes).most_common()),
                   falhas_por_tipo=dict(falhas_por_tipo.most_common()),
                   periodo=[datetime.fromtimestamp(acoes[0]['t']).isoformat(timespec='seconds'),
                            datetime.fromtimestamp(acoes[-1]['t']).isoformat(timespec='seconds')],
                   falhas_no_teste_temporal=int(y[teste].sum())),
        agrupada_por_sessao=agr, ic95_diferenca_log_loss_vs_B1=ic, temporal_70_30=tmp,
        vence_referencia=vence, criterio_de_avanco=any(vence[k] for k in ('M1', 'M2')),
        banco_inalterado=args.db.stat().st_mtime_ns == marca)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
