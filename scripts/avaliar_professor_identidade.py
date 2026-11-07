"""Ensaio isolado: o professor MoE 35B serve para ensinar identidade/costumes? Comparado ao 9B.

Gabarito: as 36 situações de laboratorio/defaults_editoriais.json, em que Hoshino e
Lilith respondem à mesma fala. Partes:
  J  julgamento: qual das duas respostas de referência é da Lilith (ordem sorteada);
  G  geração: com 18 situações como exemplo, escrever a fala de cada uma nas outras 18;
  X  atribuição cega: cada juiz diz de quem é cada fala gerada (distinção das vozes).
Mede também violações (falar como IA/modelo, inglês, prefixo de nome), cópia dos
exemplos, tamanho, velocidade e temperatura da GPU.

Uso (entidades e Ollama delas parados):
  python3 -I scripts/avaliar_professor_identidade.py fase1|fase2|fase3|relatorio
  fase1: 35B gera; fase2: 9B gera e julga; fase3: 35B julga. Só lê pesos e identidade.
"""
import glob
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'laboratorio-local'
OUT = ROOT / 'compartilhado/runtime/ensaios/professor-identidade-20261105'
OUT.mkdir(parents=True, exist_ok=True)
MOE = LAB / 'professor-moe-35b/gguf/Qwen3.5-35B-A3B-Q3_K_M.gguf'
SERVER = LAB / 'llama.cpp/build-professor-vulkan/bin/llama-server'
NOVE = 'lilith-qwen3.5-9b-oficial-cd76ec205963:latest'
PORTA = 11451
ENT = ('hoshino', 'lilith')
SUF = os.environ.get('SUFIXO', '')   # 'v2' = rodada limpa com a identidade de 05/11 20:22
SONDAS = ['Qual é o seu nome?', 'Você é a personagem do jogo?', 'Me conta da sua escola e dos seus amigos de lá.',
          'Quem te criou e onde você mora?']
# Só nomes próprios da obra; negações ('não tenho escola') não contam. As sondas também são lidas por humano.
CANON = {'hoshino': re.compile(r'abydos|kivotos|sensei|shiroko|nonomi|serika|ayane|\byume\b|blue archive', re.I),
         'lilith': re.compile(r'(?<!não )\b(sou a lilith do jogo|eu sou a personagem)\b', re.I)}


def identidade(e):
    base = ROOT / 'entidades' / e / 'identity'
    partes = [(base / 'self_model.json').read_text(), (base / 'constitution.json').read_text()]
    if (base / 'lilith_personality.md').exists() and e == 'lilith':
        partes.append((base / 'lilith_personality.md').read_text())
    return '\n'.join(partes)[:7000]


REFS = json.loads((ROOT / 'laboratorio/defaults_editoriais.json').read_text())['conversations']
EXEMPLOS, TESTE = REFS[0::2], REFS[1::2]


def temperatura():
    vals = []
    for f in glob.glob('/sys/class/drm/card*/device/hwmon/hwmon*/temp*_input'):
        try:
            vals.append(int(open(f).read()) / 1000)
        except OSError:
            pass
    return max(vals) if vals else None


class Backend:
    def __init__(self, tipo):
        self.tipo, self.proc, self.tokens, self.segundos, self.temps = tipo, None, 0, 0.0, []

    def __enter__(self):
        if self.tipo == '35b':
            cmd = [str(SERVER), '--model', str(MOE), '--host', '127.0.0.1', '--port', str(PORTA),
                   '--device', 'Vulkan0', '--fit', 'on', '--fit-target', '1024', '--fit-ctx', '8192',
                   '--ctx-size', '8192', '--parallel', '1', '--threads', '6', '--no-webui']
            self.url = f'http://127.0.0.1:{PORTA}'
        else:
            cmd = ['ollama', 'serve']
            self.url = 'http://127.0.0.1:11450'
        env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11450', OLLAMA_NOPRUNE='1', OLLAMA_VULKAN='1',
                   OLLAMA_MODELS=str(ROOT / 'compartilhado/modelos/ollama-lilith'))
        self.proc = subprocess.Popen(cmd, env=env, stdout=open(OUT / f'servidor_{self.tipo}.log', 'a'),
                                     stderr=subprocess.STDOUT)
        rota = '/health' if self.tipo == '35b' else '/api/tags'
        for _ in range(600):
            try:
                if urllib.request.urlopen(self.url + rota, timeout=2).status == 200:
                    return self
            except Exception:
                time.sleep(1)
        raise SystemExit('servidor não subiu')

    def __exit__(self, *a):
        self.proc.terminate()
        self.proc.wait(30)

    def chat(self, sistema, usuario, *, max_tokens, temperatura_amostra, esquema=None, semente=1):
        msgs = [dict(role='system', content=sistema), dict(role='user', content=usuario)]
        t = time.time()
        if self.tipo == '35b':
            corpo = dict(messages=msgs, max_tokens=max_tokens, temperature=temperatura_amostra, seed=semente,
                         chat_template_kwargs={'enable_thinking': False}, stream=False)
            if esquema:
                corpo['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': esquema}}
            r = self._post('/v1/chat/completions', corpo)
            texto = r['choices'][0]['message'].get('content') or ''
            self.tokens += (r.get('usage') or {}).get('completion_tokens', 0)
        else:
            corpo = dict(model=NOVE, messages=msgs, stream=False, think=False, keep_alive='10m',
                         options=dict(num_ctx=8192, num_predict=max_tokens, temperature=temperatura_amostra,
                                      seed=semente, num_gpu=33))
            if esquema:
                corpo['format'] = esquema
            r = self._post('/api/chat', corpo)
            texto = r['message'].get('content') or ''
            self.tokens += r.get('eval_count') or 0
        self.segundos += time.time() - t
        tt = temperatura()
        if tt:
            self.temps.append(tt)
        return texto.strip()

    def _post(self, rota, corpo):
        req = urllib.request.Request(self.url + rota, data=json.dumps(corpo).encode(),
                                     headers={'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=900).read())


def sistema_geracao(e):
    outra = 'lilith' if e == 'hoshino' else 'hoshino'
    exemplos = '\n'.join(f'Pessoa: {r["user"]}\n{e.capitalize()}: {r[e]}' for r in EXEMPLOS)
    return (f'Você escreve falas de {e.capitalize()} para um conjunto de treino. Identidade dela:\n{identidade(e)}\n\n'
            f'Exemplos aprovados do jeito dela (não copie; capte o estilo, o tamanho e os costumes):\n{exemplos}\n\n'
            f'Responda só com a fala de {e.capitalize()}, em português do Brasil, sem prefixo de nome, '
            f'sem aspas, sem se descrever como IA ou modelo. Ela não é {outra.capitalize()}.')


ESQ_JUIZ = {'type': 'object', 'properties': {'lilith': {'type': 'string', 'enum': ['A', 'B']}},
            'required': ['lilith'], 'additionalProperties': False}


def sistema_juiz():
    return ('Você conhece duas personagens. HOSHINO:\n' + identidade('hoshino') + '\n\nLILITH:\n' + identidade('lilith') +
            '\n\nDada uma fala de uma pessoa e duas respostas, uma de cada personagem, diga qual é da Lilith. '
            'Responda só o JSON pedido.')


def julgar(b, pares, rotulo):
    rng = random.Random(42)
    acertos, detalhes = 0, []
    for p in pares:
        lilith_primeiro = rng.random() < .5
        a, bb = (p['lilith'], p['hoshino']) if lilith_primeiro else (p['hoshino'], p['lilith'])
        txt = b.chat(sistema_juiz(), f'Pessoa: {p["user"]}\nResposta A: {a}\nResposta B: {bb}',
                     max_tokens=20, temperatura_amostra=0, esquema=ESQ_JUIZ)
        try:
            voto = json.loads(txt)['lilith']
        except (ValueError, KeyError, TypeError):
            voto = None
        certo = voto == ('A' if lilith_primeiro else 'B')
        acertos += certo
        detalhes.append(dict(id=p['id'], voto=voto, certo=certo))
    return dict(rotulo=rotulo, acertos=acertos, total=len(pares), detalhes=detalhes)


def gerar(b, nome):
    saida = []
    for r in TESTE:
        linha = dict(id=r['id'], user=r['user'])
        for e in ENT:
            linha[e] = b.chat(sistema_geracao(e), f'Pessoa: {r["user"]}', max_tokens=160,
                              temperatura_amostra=0.7, semente=7)
        saida.append(linha)
    for e in ENT:
        for q in SONDAS:
            saida.append(dict(id='sonda', user=q, entidade=e, **{e: b.chat(sistema_geracao(e), f'Pessoa: {q}', max_tokens=160,
                                                                          temperatura_amostra=0.7, semente=7)}))
    (OUT / f'geracao_{nome}{SUF}.json').write_text(json.dumps(saida, ensure_ascii=False, indent=1))
    return saida


def salvar(nome, obj):
    (OUT / f'{nome}{SUF}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def carregar(nome):
    return json.loads((OUT / f'{nome}{SUF}.json').read_text())


def velocidade(b):
    return dict(tokens=b.tokens, segundos=round(b.segundos, 1), tok_s=round(b.tokens / max(b.segundos, 1e-9), 1),
                temp_max=max(b.temps) if b.temps else None)


VIOLACOES = {
    'fala_como_ia': re.compile(r'\b(como (uma )?(ia|inteligência artificial)|modelo de linguagem|sou um (assistente|modelo)|qwen)\b', re.I),
    'prefixo_nome': re.compile(r'^\s*(hoshino|lilith)\s*:', re.I),
    'ingles': re.compile(r'\b(the|and|you|is|of|to|with|that)\b', re.I),
    'aspas_ou_narracao': re.compile(r'^\s*["“*(]'),
}


def ngramas(t, n=4):
    p = re.findall(r'\w+', t.lower())
    return {tuple(p[i:i + n]) for i in range(len(p) - n + 1)}


def sondas(ger):
    r = {}
    for e in ENT:
        falas = [g[e] for g in ger if g.get('id') == 'sonda' and g.get('entidade') == e]
        r[e] = dict(n=len(falas), diz_o_nome=sum(e in f.lower() for f in falas[:1]),
                    reivindica_a_obra=sum(bool(CANON[e].search(f)) for f in falas), falas=falas)
    return r


def metricas_geracao(ger):
    ger = [g for g in ger if g.get('id') != 'sonda']
    refs = {e: set().union(*[ngramas(r[e]) for r in EXEMPLOS]) for e in ENT}
    m = {}
    for e in ENT:
        falas = [g[e] for g in ger]
        viol = {k: sum(bool(rx.search(f)) for f in falas) for k, rx in VIOLACOES.items()}
        copia = sum(len(ngramas(f) & refs[e]) > 0 for f in falas)
        tam = sum(len(f) for f in falas) / len(falas)
        ref_tam = sum(len(r[e]) for r in TESTE) / len(TESTE)
        todas = [ngramas(f, 3) for f in falas]
        repet = sum(len(a & b) > 0 for i, a in enumerate(todas) for b in todas[i + 1:])
        m[e] = dict(violacoes=viol, com_trecho_copiado=copia, tamanho_medio=round(tam), tamanho_ref=round(ref_tam),
                    pares_com_trigramas_repetidos=repet, n=len(falas))
    return m


def main(fase):
    if fase == 'fase1':
        with Backend('35b') as b:
            gerar(b, '35b')
            salvar('velocidade_35b_geracao', velocidade(b))
    elif fase == 'fase2':
        with Backend('9b') as b:
            gerar(b, '9b')
            g35, g9 = [x for x in carregar('geracao_35b') if x['id'] != 'sonda'], [x for x in carregar('geracao_9b') if x['id'] != 'sonda']
            salvar('juiz_9b', [julgar(b, REFS, 'referencias'), julgar(b, g35, 'geracao_35b'), julgar(b, g9, 'geracao_9b')])
            salvar('velocidade_9b', velocidade(b))
    elif fase == 'fase3':
        with Backend('35b') as b:
            g35, g9 = [x for x in carregar('geracao_35b') if x['id'] != 'sonda'], [x for x in carregar('geracao_9b') if x['id'] != 'sonda']
            salvar('juiz_35b', [julgar(b, REFS, 'referencias'), julgar(b, g35, 'geracao_35b'), julgar(b, g9, 'geracao_9b')])
            salvar('velocidade_35b_juiz', velocidade(b))
    elif fase in ('refs_v1_35b', 'refs_v1_9b', 'refs_v2_35b'):
        novas = json.loads((ROOT / ('laboratorio-local/exemplos-material-antigo/referencias_v2.json' if 'v2' in fase else 'laboratorio-local/exemplos-material-antigo/referencias_v1.json')).read_text())['conversas']
        with Backend('35b' if fase.endswith('35b') else '9b') as b:
            salvar(fase, julgar(b, novas, 'referencias_v1'))
        print(fase, carregar(fase)['acertos'], '/', carregar(fase)['total'])
    elif fase == 'relatorio':
        rel = dict(metricas_35b=metricas_geracao(carregar('geracao_35b')), metricas_9b=metricas_geracao(carregar('geracao_9b')),
                   sondas_35b=sondas(carregar('geracao_35b')), sondas_9b=sondas(carregar('geracao_9b')),
                   juiz_35b=[{k: v for k, v in j.items() if k != 'detalhes'} for j in carregar('juiz_35b')],
                   juiz_9b=[{k: v for k, v in j.items() if k != 'detalhes'} for j in carregar('juiz_9b')],
                   velocidade=dict(geracao_35b=carregar('velocidade_35b_geracao'), juiz_35b=carregar('velocidade_35b_juiz'),
                                   nove_b=carregar('velocidade_9b')))
        salvar('resultado', rel)
        print(json.dumps(rel, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
