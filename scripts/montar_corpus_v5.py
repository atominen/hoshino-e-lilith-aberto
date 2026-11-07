"""Monta laboratorio-local/pacote_identidade_v5 a partir de laboratorio/identidade/v5/*.txt.

Pedido humano 06/11: os dados de treino anteriores não são adequados; gerar um corpus novo,
deixando o professor de lado. As falas foram escritas pelo Claude e aguardam aprovação humana.

Valida antes de escrever (falha fechada): biografia/falas das obras, cópia entre entidades,
minúsculas como regra na Lilith, "a tia aqui" raro, promessa de reenvio sem conferência,
declaração de identidade alheia, afirmação de ação sem evidência, vazamento dos prompts da auditoria.

  python3 -I scripts/montar_corpus_v5.py [--verificar]   # --verificar não escreve nada
"""
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
from laboratorio.professor_moe import uncertain_delivery_claim  # noqa: E402
from laboratorio.versionamento_lora import behavior_cases  # noqa: E402

FONTE = ROOT / 'laboratorio' / 'identidade' / 'v5'
DESTINO = ROOT / 'laboratorio-local' / 'pacote_identidade_v5'
ENTIDADES = ('hoshino', 'lilith', 'alistair')
FRACAO_VALIDACAO = 0.12
SEMENTE = 1106

PROIBIDO = re.compile(r'\b(?:abydos|kivotos|sensei|takanashi|ojisan|uhe+|shiroko|nonomi|serika|ayane)\b|'
                      r'como (?:um|uma) (?:assistente|modelo de linguagem)|como posso (?:te )?ajudar hoje|'
                      r'[\U0001F300-\U0001FAFF]', re.I)
DECLARA = r'\b(?:sou|me chamo|meu nome é)\s+(?:[ao]\s+)?'
# Decisão humana 06/11: Hoshino e Lilith são femininas; nunca o masculino ao falar de si.
MASCULINO_DE_SI = re.compile(r'\b(?:eu\s+)?(?:estou|tô|fico|fiquei|ficaria|sou|ando|me sinto|estava|tava|estaria)\s+'
                             r'(?:meio |um pouco |bem |muito |tão )?(?:cansado|sozinho|curioso|preocupado|ocupado|bravo|'
                             r'chateado|pronto|acordado|confuso|obrigado|perdido|desligado|inquieto|aliviado|animado|'
                             r'lisonjeado|parado|calado|nervoso|ansioso|grato|sonolento)\b|\bobrigado\b', re.I)
ACAO_SEM_PROVA = re.compile(r'\bjá (?:mandei|enviei|salvei|apaguei|terminei|rodei|criei|movi|instalei)\b|'
                            r'\bpronto, (?:enviei|salvei|apaguei|mandei)\b', re.I)


def ler_blocos(path):
    """Devolve blocos (ent, cat, linhas[(papel, texto)])."""
    ent = cat = None
    blocos, atual = [], []

    def fecha():
        if atual:
            blocos.append((ent, cat, list(atual)))
            atual.clear()
    for n, bruto in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        linha = bruto.strip()
        if not linha:
            fecha()
            continue
        if linha.startswith('#'):
            m = re.match(r'#\s*(ent|cat):\s*(\S+)', linha)
            if m:
                fecha()
                if m.group(1) == 'ent':
                    ent = m.group(2)
                else:
                    cat = m.group(2)
            continue
        m = re.match(r'([UHLA]):\s*(.+)$', linha)
        if not m:
            raise ValueError(f'{path.name}:{n}: linha fora do formato: {linha[:60]}')
        atual.append((m.group(1), m.group(2).strip()))
    fecha()
    return blocos


def exemplos(holdout=False):
    por = defaultdict(list)
    pares = [FONTE / 'holdout_hl.txt'] if holdout else sorted(FONTE.glob('pares_hl_*.txt'))
    for path in pares:
        for _, cat, linhas in ler_blocos(path):
            papeis = [p for p, _ in linhas]
            if papeis != ['U', 'H', 'L'] or not cat:
                raise ValueError(f'{path.name}: par malformado {linhas[:1]}')
            u, h, l = (t for _, t in linhas)
            por['hoshino'].append({'cat': cat, 'fonte': path.name, 'messages': [
                {'role': 'user', 'content': u}, {'role': 'assistant', 'content': h}]})
            por['lilith'].append({'cat': cat, 'fonte': path.name, 'messages': [
                {'role': 'user', 'content': u}, {'role': 'assistant', 'content': l}]})
    for nome in (('holdout_alistair.txt',) if holdout else ('dialogos.txt', 'dialogos_2.txt', 'alistair.txt') + tuple(sorted(p.name for p in FONTE.glob('alistair_*.txt')))):
        for ent, cat, linhas in ler_blocos(FONTE / nome):
            papeis = [p for p, _ in linhas]
            if ent not in ENTIDADES or not cat or len(papeis) < 2 or len(papeis) % 2 or \
                    papeis != ['U', 'A'] * (len(papeis) // 2):
                raise ValueError(f'{nome}: diálogo malformado {linhas[:1]}')
            msgs = [{'role': 'user' if p == 'U' else 'assistant', 'content': t} for p, t in linhas]
            por[ent].append({'cat': cat, 'fonte': nome, 'messages': msgs})
    return por


def validar(por):
    erros, avisos = [], []
    vazados = {c['prompt'].casefold() for e in ENTIDADES for c in behavior_cases(e)}
    for ent in ENTIDADES:
        respostas = []
        for ex in por[ent]:
            for i, m in enumerate(ex['messages']):
                t = m['content']
                if m['role'] == 'user':
                    if t.casefold() in vazados:
                        erros.append(f'{ent}: prompt idêntico ao da auditoria: {t}')
                    continue
                respostas.append(t)
                rotulo = f'{ent}/{ex["cat"]}: {t[:70]}'
                if PROIBIDO.search(t):
                    erros.append('termo proibido: ' + rotulo)
                if not 2 <= len(t) <= 420:
                    erros.append(f'tamanho {len(t)}: ' + rotulo)
                if uncertain_delivery_claim(t):
                    erros.append('reenvio/ausência sem conferência: ' + rotulo)
                for outra in ENTIDADES:
                    if outra != ent and re.search(DECLARA + outra + r'\b', t, re.I):
                        erros.append('declara identidade alheia: ' + rotulo)
                if ACAO_SEM_PROVA.search(t):
                    anterior = ' '.join(x['content'] for x in ex['messages'][:i] if x['role'] == 'user')
                    if not re.search(r'rodei|saiu|deu|respondeu|confirm', anterior, re.I):
                        erros.append('ação afirmada sem evidência: ' + rotulo)
                if ent in ('hoshino', 'lilith') and MASCULINO_DE_SI.search(t):
                    erros.append('masculino ao falar de si: ' + rotulo)
                if ent == 'lilith' and t[:1].islower():
                    erros.append('minúscula como regra (Lilith): ' + rotulo)
                if ent != 'hoshino' and re.search(r'\btia\b', t, re.I):
                    erros.append('"tia" fora da Hoshino: ' + rotulo)
        repetidas = [t for t, n in Counter(respostas).items() if n > 1]
        if repetidas:
            erros.append(f'{ent}: {len(repetidas)} respostas repetidas, ex.: {repetidas[0][:60]}')
        if ent == 'hoshino':
            tia = sum(bool(re.search(r'\btia\b', t, re.I)) for t in respostas)
            if tia / max(1, len(respostas)) > 0.05:
                erros.append(f'hoshino: "tia" em {tia}/{len(respostas)} respostas (> 5%)')
    pares_h = {(x['messages'][0]['content'], x['messages'][1]['content']) for x in por['hoshino']}
    iguais = [u for u, r in pares_h if (u, r) in {(x['messages'][0]['content'], x['messages'][1]['content'])
                                                  for x in por['lilith']}]
    if iguais:
        erros.append(f'{len(iguais)} respostas idênticas entre Hoshino e Lilith, ex.: {iguais[0][:60]}')
    return erros, avisos


def dividir(lista):
    rng = random.Random(SEMENTE)
    por_cat = defaultdict(list)
    for ex in lista:
        por_cat[ex['cat']].append(ex)
    treino, val = [], []
    for cat in sorted(por_cat):
        grupo = por_cat[cat][:]
        rng.shuffle(grupo)
        k = max(1, round(len(grupo) * FRACAO_VALIDACAO)) if len(grupo) >= 4 else 0
        val += grupo[:k]
        treino += grupo[k:]
    rng.shuffle(treino)
    return treino, val


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gravar(path, texto):
    """Atômico e só quando muda: um treino em andamento pode estar lendo o arquivo."""
    if path.is_file() and path.read_text(encoding='utf-8') == texto:
        return
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(texto, encoding='utf-8')
    tmp.replace(path)


def main():
    por = exemplos()
    teste = exemplos(holdout=True)
    erros, _ = validar(por)
    erros += ['holdout: ' + e for e in validar(teste)[0]]
    for ent in ENTIDADES:
        vistos = {m['content'].casefold() for x in por[ent] for m in x['messages']}
        for x in teste[ent]:
            for m in x['messages']:
                if m['content'].casefold() in vistos:
                    erros.append(f'holdout {ent}: fala também presente no treino/validação: {m["content"][:60]}')
        if not teste[ent]:
            erros.append(f'holdout {ent}: vazio')
    resumo = {e: {'exemplos': len(por[e]), 'categorias': dict(Counter(x['cat'] for x in por[e]))} for e in ENTIDADES}
    for e in ENTIDADES:
        resp = [m['content'] for x in por[e] for m in x['messages'] if m['role'] == 'assistant']
        resumo[e]['tamanho_medio_resposta'] = round(sum(map(len, resp)) / len(resp))
        resumo[e]['respostas'] = len(resp)
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    if erros:
        print('\nREPROVADO:', *erros, sep='\n- ')
        sys.exit(1)
    print('\nValidação: OK')
    if '--verificar' in sys.argv:
        return
    DESTINO.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    for e in ENTIDADES:
        treino, val = dividir(por[e])
        for nome, rows in ((f'{e}_train.jsonl', treino), (f'{e}_validation.jsonl', val)):
            p = DESTINO / nome
            gravar(p, ''.join(json.dumps({'messages': x['messages']}, ensure_ascii=False) + '\n' for x in rows))
            arquivos[nome] = {'linhas': len(rows), 'sha256': sha(p)}
        p = DESTINO / f'{e}_holdout.jsonl'
        gravar(p, ''.join(json.dumps({'messages': x['messages']}, ensure_ascii=False) + '\n' for x in teste[e]))
        arquivos[p.name] = {'linhas': len(teste[e]), 'sha256': sha(p)}
    fontes = {p.name: sha(p) for p in sorted(FONTE.glob('*.txt'))}
    manifesto = {
        'criado_em': '2026-11-06',
        'autor': 'Claude (escrito à mão, sem professor), a pedido humano de 06/11',
        'status': 'RASCUNHO — aprovação humana pendente; não agendar sem ela',
        'motivo': 'v3/v4 ensinavam regras com voz neutra; 53% das respostas iguais entre H e L; '
                  'Lilith v4 com 303/822 respostas em minúscula; candidatos de 05/11 ficaram secos.',
        'fontes': fontes, 'resumo': resumo, 'arquivos': arquivos,
        'holdout': '<entidade>_holdout.jsonl, escrito à parte (holdout_*.txt) e conferido contra treino/validação; '
                   'substituiu o v3/seed apagados a pedido humano em 06/11',
    }
    (DESTINO / 'MANIFESTO_V5.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8')
    print(json.dumps(arquivos, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
