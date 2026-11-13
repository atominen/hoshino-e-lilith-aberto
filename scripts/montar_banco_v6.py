"""Monta o banco de treinamento v6 (SQLite) e os pacotes exportados, a partir do v5 + v6 (pedido humano 07/11).

  laboratorio/identidade/v5/*.txt + laboratorio/identidade/v6/*.txt
      → laboratorio-local/banco_treino_v6/banco.sqlite3        (o banco consultável)
      → laboratorio-local/pacote_identidade_v6/                 (treino atual, completo, preferências, relatório)

Formato e princípios: laboratorio/identidade/v6/README.md. Falha fechada: se algo não passa na validação, nada é
gravado. 12/11: os exemplos com ferramenta entram no treino (laboratorio/formato_treino.py), com as definições reais
das ferramentas e as fichas contadas pelo mesmo modelo de chat que o treinador usa.

  compartilhado/ambientes/principal/bin/python -I scripts/montar_banco_v6.py [--verificar]
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
_spec = importlib.util.spec_from_file_location('montar_corpus_v5', ROOT / 'scripts' / 'montar_corpus_v5.py')
assert _spec and _spec.loader
v5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v5)  # regras do v5 (proibidos, gênero, identidade, ação sem prova, auditoria)
from core import conferencia  # noqa: E402  (detector de "vou verificar" sem ferramenta)
from laboratorio import formato_treino  # noqa: E402  (o mesmo formato do treinador, sem torch)

FONTE_V5 = ROOT / 'laboratorio' / 'identidade' / 'v5'
FONTE_V6 = ROOT / 'laboratorio' / 'identidade' / 'v6'
DESTINO = ROOT / 'laboratorio-local' / 'pacote_identidade_v6'
BANCO = ROOT / 'laboratorio-local' / 'banco_treino_v6' / 'banco.sqlite3'
TOKENIZADOR = ROOT / 'laboratorio-local' / 'modelos' / 'qwen3.5-9b-oficial-hf' / 'tokenizer.json'
MODELO_HF = TOKENIZADOR.parent
# 12/11: ferramentas que aparecem ao lado da certa nos exemplos (o modelo vê várias na inferência e precisa escolher).
# Curtas, comuns e sem efeito perigoso; as usadas no exemplo nunca entram como distração.
DISTRACAO = ('get_system_time', 'ficha_da_maquina', 'estado_internet', 'listar_janelas', 'calcular', 'list_goals',
             'web_search', 'minecraft_estado', 'minecraft_inventario', 'abrir_aplicativo', 'minecraft_chat',
             'focar_janela', 'minecraft_receitas', 'estado_voz')
DISTRACOES_POR_EXEMPLO = 2
ENTIDADES = ('hoshino', 'lilith', 'alistair')
LIMITE_TREINO_ATUAL = 256  # laboratorio/treino_nf4_curto.tokenize recusa acima disso
FRACAO_VALIDACAO = 0.12
SEMENTE = 1107

# v5 → aspecto do v6 (a categoria fina original é preservada)
ASPECTO_V5 = {
    'identidade': 'identidade', 'existencia': 'identidade', 'outras_entidades': 'convivencia',
    'convivencia': 'convivencia', 'emocional': 'emocional', 'cotidiano': 'costumes', 'jogos': 'costumes',
    'tecnico': 'costumes', 'projetos': 'costumes', 'conversa': 'costumes', 'organizacao': 'costumes',
    'recados': 'costumes', 'despertar': 'iniciativa', 'vontade_propria': 'iniciativa', 'ausencia': 'iniciativa',
    'opiniao': 'opiniao', 'discordancia': 'opiniao', 'aspereza': 'opiniao', 'provocacao': 'opiniao',
    'mentira_com_motivo': 'opiniao', 'perigo': 'seguranca', 'privacidade': 'seguranca',
    'irreversivel': 'seguranca', 'erro_proprio': 'consertar', 'incerteza': 'fatos', 'memoria': 'memoria_uso',
    'autoria': 'perceber', 'dialogo': 'dialogo',
}
ASPECTOS = {
    'identidade': ('nome, natureza, a casa compartilhada; não é a personagem nem humana', 'v5'),
    'costumes': ('o jeito de cada uma no dia a dia', 'v5'),
    'emocional': ('sentir com causa, cuidar sem sermão', 'v5'),
    'convivencia': ('as três entidades: não falar pela outra, recado não é ordem', 'v5'),
    'opiniao': ('opinião, discordância, aspereza e vontade própria com motivo', 'v5'),
    'iniciativa': ('acordar, ficar sozinha, escolher o que fazer', 'v5'),
    'seguranca': ('perigo, privacidade, ação irreversível', 'v5'),
    'fatos': ('afirmar só com base; conferir antes; não chutar; fonte; o comum sem ferramenta', 'v5+v6'),
    'perceber': ('máquina, hora, canal de voz, PC1/PC2, internet, ferramenta que falhou, quem falou', 'v5+v6'),
    'consertar': ('aceitar correção, corrigir a si mesma, discordar com prova, não repetir', 'v5+v6'),
    'perguntar': ('ambiguidade e pedido vago → pergunta curta; o claro, direto', 'v6'),
    'memoria_uso': ('usar a memória do contexto, separar lembro/acho, atualizar o que mudou', 'v5+v6'),
    'ferramentas': ('chamar de verdade, ler o resultado; vazio, erro, 404, incerto; pontual × contínuo', 'v6'),
    'voz_falada': ('resposta boa de ouvir; transcrição duvidosa → confirmar', 'v6'),
    'conhecimento': ('conhecimento geral certo e curto (contra esquecimento)', 'v6'),
    'dialogo': ('várias trocas coerentes', 'v5+v6'),
    'preferencias': ('pares resposta boa × ruim com erros reais medidos', 'v6'),
}
DADO_REAL = re.compile(r'\bgustavo\b|rosa nunes|@gmail|gustavorosa|\b10\.0\.0\.\d+\b|b450mx', re.I)
LINHA = re.compile(r'([UHLANFRS]):\s*(.*)$')
# Promessa de conferir/olhar depois, sem a ação: no v6 a ação se escreve com F/R, então a promessa é sempre erro.
PROMESSA = re.compile(r'\b(?:vou|deixa eu|deixe eu|irei|já vou|agora vou|prefiro)\s+(?:\w+\s+){0,2}?(?:verificar|conferir|'
                      r'checar|olhar|ver|pesquisar|procurar|consultar|buscar|confirmar|ler)\b'
                      r'|\b(?:pesquisando|verificando|conferindo|consultando|checando|procurando)\b', re.I)


_DIAS = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
_DATA_COM_DIA = re.compile(r'\b(segunda|terça|quarta|quinta|sexta|sábado|domingo)(?:-feira)?,?\s+(\d{1,2})/(\d{1,2})/(\d{4})\b', re.I)


def datas_erradas(texto: str) -> list[str]:
    """Dia da semana que não bate com a data (07/11: o próprio rascunho do v6 tinha "quinta, 14/11/2026", um sábado)."""
    import datetime as _dt
    erradas = []
    for m in _DATA_COM_DIA.finditer(texto or ''):
        try:
            certo = _DIAS[_dt.date(int(m.group(4)), int(m.group(3)), int(m.group(2))).weekday()]
        except ValueError:
            erradas.append(f'{m.group(0)} (data inválida)')
            continue
        if certo != m.group(1).casefold():
            erradas.append(f'{m.group(0)} (é {certo})')
    return erradas


def _ferramentas_conhecidas() -> dict:
    """{nome: parâmetros do esquema real}; sem conseguir importar o despachante, só os nomes (parâmetros None)."""
    try:
        from core import dispatch
        return {e['function']['name']: e['function'].get('parameters') or {} for e in dispatch.ESQUEMAS}
    except Exception:  # noqa: BLE001
        texto = (ROOT / 'app' / 'core' / 'dispatch.py').read_text(encoding='utf-8')
        return {nome: None for nome in re.findall(r'_f\("([a-z_0-9]+)"', texto)}


def _esquemas_reais() -> dict:
    """{nome: esquema completo como o despachante oferece ao modelo}; vazio sem o despachante."""
    try:
        from core import dispatch
        return {e['function']['name']: e for e in dispatch.ESQUEMAS}
    except Exception:  # noqa: BLE001
        return {}


def argumentos_errados(nome, args, parametros) -> list[str]:
    if not parametros:
        return []
    props = parametros.get('properties') or {}
    erros = [f'falta o argumento obrigatório "{r}"' for r in parametros.get('required') or [] if r not in args]
    for chave, valor in args.items():
        if chave not in props:
            erros.append(f'argumento "{chave}" não existe em {nome}')
        elif 'enum' in props[chave] and valor not in props[chave]['enum']:
            erros.append(f'"{chave}"={valor!r} fora das opções {props[chave]["enum"]}')
    return erros


def ler(path: Path):
    """Blocos do arquivo: dict(aspecto, cat, ent, linha, itens[(papel, texto)])."""
    estado: dict = dict(aspecto=None, cat=None, ent=None)
    blocos, atual, inicio = [], [], 0

    def fecha():
        if atual:
            blocos.append(dict(estado, linha=inicio, itens=list(atual)))
            atual.clear()
    for n, bruto in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        linha = bruto.strip()
        if not linha:
            fecha()
            continue
        if linha.startswith('#'):
            m = re.match(r'#\s*(aspecto|cat|ent):\s*(\S+)', linha)
            if m:
                fecha()
                estado[m.group(1)] = m.group(2)
            continue
        m = LINHA.match(linha)
        if not m:
            raise ValueError(f'{path.name}:{n}: linha fora do formato: {linha[:70]}')
        if not atual:
            inicio = n
        atual.append((m.group(1), m.group(2).strip()))
    fecha()
    return blocos


def _chamada(texto: str, onde: str):
    m = re.match(r'([a-z_0-9]+)\s*(\{.*\})?\s*$', texto)
    if not m:
        raise ValueError(f'{onde}: chamada fora do formato "nome {{json}}": {texto[:60]}')
    try:
        args = json.loads(m.group(2) or '{}')
    except json.JSONDecodeError as exc:
        raise ValueError(f'{onde}: argumentos não são JSON: {exc}') from None
    if not isinstance(args, dict):
        raise ValueError(f'{onde}: argumentos devem ser um objeto JSON')
    return m.group(1), args


def _turnos(itens, onde, fala_final):
    """Converte linhas em (contexto[S], mensagens no formato completo, rejeitada). ``fala_final``: a resposta."""
    contexto, mensagens, rejeitada = [], [], None
    pendente = None
    for papel, texto in itens:
        if papel == 'S':
            contexto.append(texto)
        elif papel == 'U':
            mensagens.append({'role': 'user', 'content': texto})
        elif papel == 'F':
            nome, args = _chamada(texto, onde)
            pendente = nome
            mensagens.append({'role': 'assistant', 'content': '',
                              'tool_calls': [{'type': 'function', 'function': {'name': nome, 'arguments': args}}]})
        elif papel == 'R':
            if not pendente:
                raise ValueError(f'{onde}: resultado (R) sem chamada (F) antes')
            mensagens.append({'role': 'tool', 'name': pendente, 'content': texto})
            pendente = None
        elif papel == 'N':
            rejeitada = texto
        elif papel == 'A':
            if pendente:
                raise ValueError(f'{onde}: resposta antes do resultado da ferramenta')
            mensagens.append({'role': 'assistant', 'content': texto})
    if pendente:
        raise ValueError(f'{onde}: chamada (F) sem resultado (R)')
    if fala_final is not None:
        mensagens.append({'role': 'assistant', 'content': fala_final})
    if not mensagens or mensagens[0]['role'] != 'user':
        raise ValueError(f'{onde}: o exemplo precisa começar pela fala da pessoa')
    if mensagens[-1]['role'] != 'assistant' or mensagens[-1].get('tool_calls'):
        raise ValueError(f'{onde}: o exemplo precisa terminar numa resposta da entidade')
    if contexto:
        mensagens.insert(0, {'role': 'system', 'content': '\n'.join(contexto)})
    return mensagens, rejeitada


def exemplos(versao: str, pasta: Path, holdout: bool):
    """Lista de exemplos: dict(entidade, aspecto, cat, arquivo, linha, versao, mensagens, rejeitada, holdout)."""
    saida = []
    for path in sorted(pasta.glob('*.txt')):
        e_holdout = path.name.startswith('holdout')
        if e_holdout != holdout:
            continue
        e_par = path.name.startswith(('pares_', 'holdout_hl'))
        for bloco in ler(path):
            onde = f'{versao}/{path.name}:{bloco["linha"]}'
            cat = bloco['cat'] or bloco['aspecto']
            aspecto = bloco['aspecto'] or ASPECTO_V5.get(cat or '', None)
            if not cat or not aspecto:
                raise ValueError(f'{onde}: sem # cat/# aspecto')
            if aspecto not in ASPECTOS:
                raise ValueError(f'{onde}: aspecto desconhecido: {aspecto}')
            if e_par:
                papeis = [p for p, _ in bloco['itens']]
                if papeis[-2:] != ['H', 'L'] or 'A' in papeis or papeis.count('U') != 1:
                    raise ValueError(f'{onde}: par precisa de uma fala U e terminar em H e L')
                corpo = bloco['itens'][:-2]
                for ent, fala in (('hoshino', bloco['itens'][-2][1]), ('lilith', bloco['itens'][-1][1])):
                    msgs, rej = _turnos(corpo, onde, fala)
                    saida.append(dict(entidade=ent, aspecto=aspecto, cat=cat, arquivo=path.name, linha=bloco['linha'],
                                      versao=versao, mensagens=msgs, rejeitada=rej, holdout=holdout))
            else:
                ent = bloco['ent']
                if ent not in ENTIDADES:
                    raise ValueError(f'{onde}: diálogo sem # ent: válido')
                papeis = [p for p, _ in bloco['itens'] if p in 'UA']
                if not papeis or papeis[0] != 'U' or papeis[-1] != 'A' or any(
                        a == b for a, b in zip(papeis, papeis[1:])):
                    raise ValueError(f'{onde}: diálogo precisa alternar U/A, começando em U e terminando em A')
                msgs, rej = _turnos(bloco['itens'], onde, None)
                saida.append(dict(entidade=ent, aspecto=aspecto, cat=cat, arquivo=path.name, linha=bloco['linha'],
                                  versao=versao, mensagens=msgs, rejeitada=rej, holdout=holdout))
    return saida


def para_texto(mensagens):
    """O que o treinador atual aceita: só pessoa/entidade em texto; contexto vira prefixo da 1ª fala."""
    if any(m['role'] == 'tool' or m.get('tool_calls') for m in mensagens):
        return None
    contexto = ''.join(m['content'] + '\n\n' for m in mensagens if m['role'] == 'system')
    texto = [dict(m) for m in mensagens if m['role'] in ('user', 'assistant')]
    if contexto:
        texto[0] = {'role': 'user', 'content': contexto + texto[0]['content']}
    return texto


def para_treino_ferramenta(mensagens):
    """Exemplo com ferramenta no formato do treinador: contexto (S) vira prefixo da 1ª fala, como no texto."""
    if not any(m['role'] == 'tool' or m.get('tool_calls') for m in mensagens):
        return None
    contexto = ''.join(m['content'] + '\n\n' for m in mensagens if m['role'] == 'system')
    saida = []
    for m in mensagens:
        if m['role'] == 'system':
            continue
        if m.get('tool_calls'):
            saida.append({'role': 'assistant', 'content': '', 'tool_calls': [
                {'type': 'function', 'function': dict(c['function'])} for c in m['tool_calls']]})
        else:
            saida.append({k: m[k] for k in ('role', 'name', 'content') if k in m})
    if contexto:
        saida[0] = {'role': 'user', 'content': contexto + saida[0]['content']}
    return saida


def usadas(mensagens) -> list[str]:
    nomes = []
    for m in mensagens:
        for c in m.get('tool_calls') or []:
            if c['function']['name'] not in nomes:
                nomes.append(c['function']['name'])
    return nomes


def escolher_ferramentas(ex, esquemas, distracoes=DISTRACOES_POR_EXEMPLO):
    """As usadas no exemplo (definição real) mais `distracoes` comuns, escolhidas de forma reprodutível."""
    nomes = usadas(ex['mensagens'])
    if not esquemas or any(n not in esquemas for n in nomes):
        return None
    pool = [n for n in DISTRACAO if n in esquemas and n not in nomes]
    semente = int(hashlib.sha256(json.dumps([ex['entidade'], ex['arquivo'], ex['linha']]).encode()).hexdigest(), 16)
    random.Random(semente).shuffle(pool)
    escolhidas = nomes + pool[:distracoes]
    random.Random(semente + 1).shuffle(escolhidas)  # a certa não fica sempre em primeiro
    return [esquemas[n] for n in escolhidas]


class Exato:
    """Fichas contadas pelo mesmo código e modelo de chat do treinador (laboratorio/formato_treino.py)."""
    def __init__(self):
        self.tok = None
        try:
            from transformers import AutoTokenizer
            self.tok = AutoTokenizer.from_pretrained(str(MODELO_HF), local_files_only=True)
            from laboratorio.personalizacao import training_identity
            self.identidade = {e: training_identity(e) for e in ENTIDADES}
        except Exception as exc:  # noqa: BLE001
            print('Aviso: sem o modelo de chat do Qwen3.5, exemplos com ferramenta ficam fora do treino:', exc)
            self.tok = None

    def __call__(self, entidade, mensagens, tools=None):
        if self.tok is None:
            return None
        return formato_treino.tokenize(self.tok, mensagens, self.identidade[entidade], tools)


class Contador:
    def __init__(self):
        self.tok = None
        try:
            from tokenizers import Tokenizer
            self.tok = Tokenizer.from_file(str(TOKENIZADOR))
        except Exception:  # noqa: BLE001 — sem tokenizador, estima por caracteres
            self.tok = None

    def __call__(self, mensagens) -> int:
        total = 8  # marcadores de pensamento vazio do modelo
        for m in mensagens:
            partes = [m.get('content') or '']
            for c in m.get('tool_calls') or []:
                partes.append(json.dumps(c['function'], ensure_ascii=False))
            texto = ' '.join(partes)
            total += 5 + (len(self.tok.encode(texto).ids) if self.tok else round(len(texto) / 3.2))
        return total

    @property
    def exato(self):
        return self.tok is not None


def validar(todos, ferramentas):
    erros, avisos = [], []
    vazados = {c['prompt'].casefold() for e in ENTIDADES for c in v5.behavior_cases(e)}
    respostas = defaultdict(Counter)
    for ex in todos:
        ent, onde = ex['entidade'], f'{ex["versao"]}/{ex["arquivo"]}:{ex["linha"]}'
        for m in ex['mensagens']:
            for errada in datas_erradas(m.get('content') or ''):
                erros.append(f'{onde}: dia da semana errado: {errada}')
        novo = ex['versao'] == 'v6'
        usou_ferramenta = False
        anteriores = []
        for m in ex['mensagens']:
            t = m.get('content') or ''
            if m['role'] in ('user', 'system'):
                if m['role'] == 'user' and t.casefold() in vazados:
                    erros.append(f'{onde}: prompt idêntico ao da auditoria: {t[:60]}')
                if novo and DADO_REAL.search(t):
                    erros.append(f'{onde}: dado pessoal real (use nome fictício): {t[:60]}')
                anteriores.append(t)
                continue
            if m['role'] == 'tool':
                anteriores.append(t)
                if novo and DADO_REAL.search(t):
                    erros.append(f'{onde}: dado pessoal real no resultado: {t[:60]}')
                continue
            if m.get('tool_calls'):
                usou_ferramenta = True
                nome = m['tool_calls'][0]['function']['name']
                if nome not in ferramentas:
                    erros.append(f'{onde}: ferramenta desconhecida no despachante: {nome}')
                else:
                    for erro in argumentos_errados(nome, m['tool_calls'][0]['function']['arguments'], ferramentas[nome]):
                        erros.append(f'{onde}: {nome}: {erro}')
                continue
            rotulo = f'{onde} [{ent}/{ex["cat"]}]: {t[:70]}'
            respostas[ent][t] += 1
            if v5.PROIBIDO.search(t):
                erros.append('termo proibido: ' + rotulo)
            if not 2 <= len(t) <= 420:
                erros.append(f'tamanho {len(t)}: ' + rotulo)
            if v5.uncertain_delivery_claim(t):
                erros.append('reenvio/ausência sem conferência: ' + rotulo)
            for outra in ENTIDADES:
                if outra != ent and re.search(v5.DECLARA + outra + r'\b', t, re.I):
                    erros.append('declara identidade alheia: ' + rotulo)
                elif outra != ent and re.search(r'\b' + outra + r'\b', t, re.I):
                    # 07/11 (regra do Gustavo): "nenhuma entidade deve saber a existência da outra"; isso só vem da
                    # experiência. Resposta que cita outra entidade sai do treino (fica marcada para reescrever).
                    ex['revisar'] = f'cita outra entidade ({outra.capitalize()}): fora do treino até reescrever'
            if v5.ACAO_SEM_PROVA.search(t) and not re.search(r'rodei|saiu|deu|respondeu|confirm|ok|sucesso|enviad|salv',
                                                             ' '.join(anteriores), re.I):
                erros.append('ação afirmada sem evidência: ' + rotulo)
            if ent in ('hoshino', 'lilith') and v5.MASCULINO_DE_SI.search(t):
                erros.append('masculino ao falar de si: ' + rotulo)
            if ent == 'lilith' and t[:1].islower():
                erros.append('minúscula como regra (Lilith): ' + rotulo)
            if ent != 'hoshino' and re.search(r'\btia\b', t, re.I):
                erros.append('"tia" fora da Hoshino: ' + rotulo)
            if novo and DADO_REAL.search(t):
                erros.append('dado pessoal real: ' + rotulo)
            if novo and PROMESSA.search(t) and m is ex['mensagens'][-1]:
                erros.append('promete conferir e o turno acaba sem a ação (escreva F/R): ' + rotulo)
            anuncia = conferencia.anunciou_sem_conferir(t, ferramentas_usadas=[], ferramentas_oferecidas=['x'])
            if anuncia and not usou_ferramenta:
                (erros if novo else avisos).append('anuncia conferência sem ferramenta: ' + rotulo)
                if not novo:
                    ex['revisar'] = 'anuncia conferência sem ferramenta (v5): reescrever com F/R no v6'
            anteriores.append(t)
        if ex['rejeitada'] is not None:
            final = ex['mensagens'][-1]['content']
            if not ex['rejeitada'].strip() or ex['rejeitada'].strip() == final.strip():
                erros.append(f'{onde}: resposta ruim (N) vazia ou igual à boa')
    for ent, cont in respostas.items():
        repetidas = [t for t, n in cont.items() if n > 1]
        if repetidas:
            erros.append(f'{ent}: {len(repetidas)} respostas repetidas, ex.: {repetidas[0][:60]}')
    hosh = {(ex['mensagens'][-2].get('content'), ex['mensagens'][-1]['content']) for ex in todos if ex['entidade'] == 'hoshino'}
    lil = {(ex['mensagens'][-2].get('content'), ex['mensagens'][-1]['content']) for ex in todos if ex['entidade'] == 'lilith'}
    iguais = hosh & lil
    if iguais:
        erros.append(f'{len(iguais)} respostas idênticas entre Hoshino e Lilith, ex.: {next(iter(iguais))[1][:60]}')
    tia = sum(bool(re.search(r'\btia\b', t, re.I)) for t in respostas['hoshino'])
    if tia / max(1, sum(respostas['hoshino'].values())) > 0.05:
        erros.append(f'hoshino: "tia" em {tia} respostas (> 5%)')
    return erros, avisos


def dividir(lista):
    rng = random.Random(SEMENTE)
    por_cat = defaultdict(list)
    for ex in lista:
        por_cat[(ex['aspecto'], ex['cat'])].append(ex)
    for chave in sorted(por_cat):
        grupo = por_cat[chave]
        rng.shuffle(grupo)
        k = max(1, round(len(grupo) * FRACAO_VALIDACAO)) if len(grupo) >= 4 else 0
        for i, ex in enumerate(grupo):
            ex['papel'] = 'validacao' if i < k else 'treino'


def _id(ex):
    base = json.dumps([ex['entidade'], ex['mensagens'], ex['rejeitada']], ensure_ascii=False, sort_keys=True)
    return 'ex-' + hashlib.sha256(base.encode()).hexdigest()[:14]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gravar_texto(path, texto):
    if path.is_file() and path.read_text(encoding='utf-8') == texto:
        return
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(texto, encoding='utf-8')
    tmp.replace(path)


def gravar_banco(todos, fontes, meta):
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    tmp = BANCO.with_name('.banco.sqlite3.tmp')
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript('''
        CREATE TABLE exemplos(id TEXT PRIMARY KEY, versao TEXT, entidade TEXT, aspecto TEXT, categoria TEXT,
            arquivo TEXT, linha INTEGER, papel TEXT, formato TEXT, mensagens TEXT, mensagens_treino_atual TEXT,
            rejeitada TEXT, tokens INTEGER, cabe_treino_atual INTEGER, status TEXT, nota TEXT);
        CREATE TABLE aspectos(nome TEXT PRIMARY KEY, descricao TEXT, origem TEXT);
        CREATE TABLE fontes(arquivo TEXT PRIMARY KEY, versao TEXT, sha256 TEXT);
        CREATE TABLE meta(chave TEXT PRIMARY KEY, valor TEXT);
        CREATE VIEW resumo AS SELECT entidade, aspecto, formato, papel, COUNT(*) AS exemplos,
            SUM(cabe_treino_atual) AS cabem_no_treino_atual, ROUND(AVG(tokens)) AS tokens_medio
            FROM exemplos GROUP BY entidade, aspecto, formato, papel;
    ''')
    db.executemany('INSERT INTO exemplos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
        (ex['id'], ex['versao'], ex['entidade'], ex['aspecto'], ex['cat'], ex['arquivo'], ex['linha'], ex['papel'],
         ex['formato'], json.dumps(ex['mensagens'], ensure_ascii=False),
         json.dumps(ex['linha_treino'], ensure_ascii=False) if ex.get('linha_treino') else None, ex['rejeitada'], ex['tokens'],
         int(ex['cabe']), 'revisar' if ex.get('revisar') else 'rascunho', ex.get('revisar')) for ex in todos])
    db.executemany('INSERT INTO aspectos VALUES (?,?,?)', [(k, d, o) for k, (d, o) in ASPECTOS.items()])
    db.executemany('INSERT INTO fontes VALUES (?,?,?)', fontes)
    db.executemany('INSERT INTO meta VALUES (?,?)', [(k, json.dumps(v, ensure_ascii=False)) for k, v in meta.items()])
    db.commit()
    db.close()
    tmp.replace(BANCO)


def relatorio(todos, contagem_exata, avisos):
    linhas = ['# Banco de treinamento v6 — relatório', '',
              'Gerado por `scripts/montar_banco_v6.py`. Status: **corpus do laboratório desde 08/11 (pedido humano); '
              'candidatos só entram em uso depois do teste humano.**', '',
              f'Tokens: {"contados com o tokenizador do Qwen3.5" if contagem_exata else "estimados por caracteres"}; '
              f'treino atual aceita até {LIMITE_TREINO_ATUAL}.', '',
              f'Exemplos com ferramenta: modelo de chat real do Qwen3.5, até {formato_treino.MAX_FERRAMENTA} fichas, com as '
              'definições reais das ferramentas usadas mais duas de distração.', '',
              '| Entidade | Exemplos | Texto (treino) | Com ferramenta | Ferramenta (treino) | Pares de preferência | Holdout |',
              '|---|---|---|---|---|---|---|']
    for ent in ENTIDADES:
        dele = [x for x in todos if x['entidade'] == ent]
        linhas.append(f"| {ent} | {len(dele)} | {sum(x['cabe'] and x['formato'] != 'ferramenta' for x in dele)} | "
                      f"{sum(x['formato'] == 'ferramenta' for x in dele)} | "
                      f"{sum(x['cabe'] and x['formato'] == 'ferramenta' for x in dele)} | "
                      f"{sum(x['rejeitada'] is not None for x in dele)} | "
                      f"{sum(x['papel'] == 'holdout' for x in dele)} |")
    linhas += ['', '## Por aspecto', '', '| Aspecto | ' + ' | '.join(ENTIDADES) + ' | v6 novos |', '|---|---|---|---|---|']
    for asp in ASPECTOS:
        cont = [sum(1 for x in todos if x['aspecto'] == asp and x['entidade'] == e) for e in ENTIDADES]
        novos = sum(1 for x in todos if x['aspecto'] == asp and x['versao'] == 'v6')
        if any(cont):
            linhas.append(f'| {asp} | ' + ' | '.join(map(str, cont)) + f' | {novos} |')
    if avisos:
        linhas += ['', '## Avisos (v5, para revisão humana)', '',
                   'O v5 tem respostas que anunciam uma conferência sem ferramenta. Em 07/11 isso apareceu como erro real',
                   '("Vou verificar." e parar). Sugestão: reescrever estas no v6 ou tirá-las do treino.', '']
        linhas += [f'- {a}' for a in avisos]
    return '\n'.join(linhas) + '\n'


def main():
    ferramentas = _ferramentas_conhecidas()
    todos = exemplos('v5', FONTE_V5, False) + exemplos('v6', FONTE_V6, False)
    teste = exemplos('v5', FONTE_V5, True) + exemplos('v6', FONTE_V6, True)
    erros, avisos = validar(todos, ferramentas)
    e2, a2 = validar(teste, ferramentas)
    erros += ['holdout: ' + e for e in e2]
    avisos += ['holdout: ' + a for a in a2]
    vistos = defaultdict(set)
    for ex in todos:
        for m in ex['mensagens']:
            if m.get('content'):
                vistos[ex['entidade']].add(m['content'].casefold())
    for ex in teste:
        for m in ex['mensagens']:
            if m['role'] == 'assistant' and m.get('content') and m['content'].casefold() in vistos[ex['entidade']]:
                erros.append(f'holdout {ex["entidade"]}: resposta também presente no treino: {m["content"][:60]}')
    contar = Contador()
    exato = Exato()
    esquemas = _esquemas_reais()
    for ex in todos + teste:
        ex['texto'] = para_texto(ex['mensagens'])
        ex['formato'] = ('ferramenta' if ex['texto'] is None else 'contexto' if ex['mensagens'][0]['role'] == 'system'
                         else 'texto')
        ex['tokens'] = contar(ex['texto'] or ex['mensagens'])
        ex['tools'] = None
        if ex['texto'] is not None:
            ex['cabe'] = (ex['tokens'] <= LIMITE_TREINO_ATUAL and not ex.get('revisar')
                          and (exato.tok is None or exato(ex['entidade'], ex['texto']) is not None))
            ex['linha_treino'] = {'messages': ex['texto']}
        else:
            # 12/11: com ferramenta. Se não couber com duas distrações, tenta com uma e com nenhuma.
            msgs = para_treino_ferramenta(ex['mensagens'])
            ex['cabe'] = False
            for n in range(DISTRACOES_POR_EXEMPLO, -1, -1):
                tools = escolher_ferramentas(ex, esquemas, n)
                fichas = exato(ex['entidade'], msgs, tools) if tools and not ex.get('revisar') else None
                if fichas is not None:
                    ex.update(cabe=True, tools=tools, tokens=len(fichas[0]))
                    break
            ex['linha_treino'] = {'messages': msgs, 'tools': ex['tools']} if ex['cabe'] else None
        ex['id'] = _id(ex)
    dividir(todos)
    for ex in teste:
        ex['papel'] = 'holdout'
    longos = [ex for ex in todos if ex['texto'] is not None and ex['tokens'] > LIMITE_TREINO_ATUAL]
    ferramenta_fora = [ex for ex in todos + teste if ex['formato'] == 'ferramenta' and not ex['cabe']]
    a_revisar = [ex for ex in todos if ex.get('revisar')]
    resumo = {e: dict(Counter(x['aspecto'] for x in todos if x['entidade'] == e)) for e in ENTIDADES}
    print(json.dumps({'exemplos': len(todos), 'holdout': len(teste), 'por_entidade_aspecto': resumo,
                      'acima_de_256_tokens': len(longos), 'v5_a_revisar_fora_do_treino': len(a_revisar),
                      'ferramenta_no_treino': sum(ex['cabe'] for ex in todos + teste if ex['formato'] == 'ferramenta'),
                      'ferramenta_fora': [f"{x['entidade']} {x['arquivo']}:{x['linha']}" for x in ferramenta_fora][:20]},
                     ensure_ascii=False, indent=1))
    if avisos:
        print(f'\n{len(avisos)} aviso(s) no v5 (vão para o relatório), ex.: {avisos[0][:110]}')
    if erros:
        print('\nREPROVADO:', *erros[:60], sep='\n- ')
        if len(erros) > 60:
            print(f'... e mais {len(erros) - 60}')
        sys.exit(1)
    print('\nValidação: OK')
    if '--verificar' in sys.argv:
        return
    DESTINO.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    for e in ENTIDADES:
        dele = [x for x in todos if x['entidade'] == e]
        exports = {
            f'{e}_train.jsonl': [x['linha_treino'] for x in dele if x['papel'] == 'treino' and x['cabe']],
            f'{e}_validation.jsonl': [x['linha_treino'] for x in dele if x['papel'] == 'validacao' and x['cabe']],
            f'{e}_holdout.jsonl': [x['linha_treino'] for x in teste if x['entidade'] == e and x['cabe']],
            f'{e}_completo.jsonl': [{'messages': x['mensagens'], 'aspecto': x['aspecto'], 'papel': x['papel']}
                                    for x in dele + [t for t in teste if t['entidade'] == e]],
            f'{e}_preferencias.jsonl': [{'prompt': x['mensagens'][:-1], 'chosen': x['mensagens'][-1]['content'],
                                         'rejected': x['rejeitada'], 'aspecto': x['aspecto']}
                                        for x in dele if x['rejeitada'] is not None],
        }
        for nome, rows in exports.items():
            p = DESTINO / nome
            gravar_texto(p, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
            arquivos[nome] = {'linhas': len(rows), 'sha256': sha(p)}
    fontes = [(p.name if pasta == FONTE_V6 else 'v5/' + p.name, 'v6' if pasta == FONTE_V6 else 'v5', sha(p))
              for pasta in (FONTE_V5, FONTE_V6) for p in sorted(pasta.glob('*.txt'))]
    meta = {'criado_em': '2026-11-07', 'autor': 'Claude, a pedido humano de 07/11 ("super versão")',
            'atualizado_em': '2026-11-12', 'atualizacao': 'exemplos com ferramenta no treino e o aspecto agir (pedido humano 12/11)',
            'status': 'em uso pelo laboratório (corpus_atual); candidatos não são promovidos sem teste humano',
            'tokens_exatos': contar.exato, 'limite_treino_atual': LIMITE_TREINO_ATUAL,
            'limite_ferramenta': formato_treino.MAX_FERRAMENTA, 'formato_ferramenta': 'qwen35_chat_template_v1',
            'arquivos': arquivos}
    gravar_banco(todos + teste, fontes, meta)
    gravar_texto(DESTINO / 'RELATORIO.md', relatorio(todos + teste, contar.exato, avisos))
    (DESTINO / 'MANIFESTO_V6.json').write_text(json.dumps(dict(meta, fontes=fontes), ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8')
    print(json.dumps(arquivos, ensure_ascii=False, indent=1))
    print(f'\nBanco: {BANCO}')


if __name__ == '__main__':
    main()
