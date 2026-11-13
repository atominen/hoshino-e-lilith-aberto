"""Revisor de memória: segunda chamada do modelo, só para conferir (pedido humano 07/11).

O escriba-modelo (primeira chamada) propõe anotações a partir da troca que acabou de acontecer. Em 06/11 ele inventou
("quase fechou uma edição na Wikipedia"), trocou quem disse o quê e guardou pedido pontual como gosto da pessoa.
Aqui uma segunda chamada, separada e curta, confere cada anotação antes de guardar:

- **base**: quem sustenta a anotação? a PESSOA, as FONTES do turno (saídas das ferramentas que ela usou), só a
  própria entidade, ou ninguém (inventada); e **contradiz**: algo da conversa ou das fontes desmente?
  O que só a entidade afirmou é conferido por este código, não a critério do modelo: até duas ferramentas de leitura
  (internet, página, histórico do chat, ficha da máquina) e uma nova decisão com o que achou. Sem confirmação, não entra;
- **duravel**: vale lembrar daqui a semanas?
- **relacao** com as anotações parecidas já guardadas: nova, igual ou atualiza (e qual).

A decisão final é deste código, não do modelo:
- sem apoio ou passageira: não guarda;
- igual ou atualiza: guarda a nova e marca a antiga como substituída (``superseded``, com o vínculo ``supersedes``).
  Assim confundir "igual" com "atualiza" não faz estrago: os dois dão o mesmo resultado. O único erro que
  desativa algo certo é chamar de igual/atualiza uma anotação de outro fato, e a avaliação mede justamente isso;
- só anotações do próprio escriba-modelo (fonte ``escriba_llm``) podem ser substituídas. O que veio de regra,
  da pessoa ou de reflexão nunca é mostrado nem tocado aqui. Nada é apagado.

Quem responde é configurável (``HOSHINO_REVISOR_MEMORIA``): ``entidade`` (o mesmo modelo dela, segunda chamada),
``intermediario`` (o 2B só na CPU, sem ferramentas) ou ``desligado``. Comparação e escolha em
docs/MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md.
"""
from __future__ import annotations

import json
import re
import unicodedata

LETRAS = ("A", "B", "C")
MAX_ANTIGAS = len(LETRAS)
FONTES_SUBSTITUIVEIS = ("escriba_llm",)

MAX_FONTES = 4          # saídas de ferramenta do turno mostradas ao revisor
MAX_FONTE = 1500        # caracteres de cada uma
MAX_FONTES_TOTAL = 4500
MAX_CONFERENCIAS = 2    # chamadas de ferramenta por anotação
# Só leitura. Quem executa é o despachante de sempre (chave da internet e ferramentas desligadas na Central valem);
# a ficha da máquina é local (tools/ficha_maquina.py).
FERRAMENTAS_CONFERENCIA = ("web_search", "fetch_page", "buscar_historico_chat", "ficha_da_maquina")
ESQUEMA_FICHA = {"type": "function", "function": {
    "name": "ficha_da_maquina",
    "description": "Ficha do PC1, lida agora: processador, memória RAM, placa de vídeo e VRAM, sistema e disco.",
    "parameters": {"type": "object", "properties": {}, "required": []}}}


BASES = ("fonte", "conferencia", "pessoa", "entidade", "nenhuma")


def esquema(n_antigas: int) -> dict:
    """Formato da resposta. Chaves em ordem alfabética (citacao, contradiz, duravel, relacao): em 07/11 o Ollama
    devolvia as chaves assim, e o modelo decide na ordem em que escreve; copiar o trecho primeiro ancora o resto.
    A letra vai junto da relação ("igual A"); só as letras que existem podem ser escolhidas."""
    letras = LETRAS[:max(0, min(int(n_antigas), MAX_ANTIGAS))]
    relacoes = ["nova", *(f"{tipo} {letra}" for tipo in ("igual", "atualiza") for letra in letras)]
    return {
        "type": "object",
        "properties": {
            "citacao": {"type": "string", "maxLength": 300},
            "contradiz": {"type": "boolean"},
            "duravel": {"type": "boolean"},
            "relacao": {"type": "string", "enum": relacoes},
        },
        "required": ["citacao", "contradiz", "duravel", "relacao"],
        "additionalProperties": False,
    }


# 07/11: com "apoiada: sim/nao/conferir" o 9B nunca escolheu conferir e aceitou o que só ela tinha dito ("sobre uma
# boxeadora", "64 GB de RAM"). Agora ele só diz QUEM sustenta a anotação; conferir ou não é regra deste código.
SISTEMA = """Você confere uma anotação de memória de {nome} antes de ela ser guardada. Recebe a CONVERSA (o que a \
PESSOA disse e o que {nome} respondeu), as FONTES que {nome} consultou nesta conversa (saídas das ferramentas){e_conferencia}, \
a ANOTAÇÃO candidata e, se houver, anotações JÁ GUARDADAS parecidas. Responda só o JSON.

{instrucao_citacao}
contradiz: a conversa ou as FONTES{ou_conferencia} desmentem a anotação? As JÁ GUARDADAS não contam aqui: \
anotação que corrige uma já guardada é "atualiza", não "contradiz".
duravel: vale lembrar daqui a semanas?
  true: quem a pessoa é, o que ela tem, faz, gosta ou conta da vida dela, o que foi combinado, como algo funciona \
nesta máquina, um fato sobre o mundo num assunto que interessa à pessoa.
  false: cumprimento, pedido pontual (abrir, tocar, pesquisar algo agora), como a conversa foi, o que {nome} \
respondeu ou não conseguiu fazer.
relacao, comparando com as JÁ GUARDADAS (X é a letra dela):
  "igual X": a anotação diz tudo o que a já guardada X diz (mesmo com outras palavras ou com mais detalhe);
  "atualiza X": a já guardada X ficou errada ou velha por causa da anotação;
  "nova": qualquer outro caso, inclusive mesmo assunto em que a já guardada continua valendo e não está contida \
na anotação.

Exemplos:
PESSOA: "meu cachorro se chama Bento" / {nome}: "Que nome bonito!" | ANOTAÇÃO: "O cachorro da pessoa se chama Bento" \
| JÁ GUARDADAS: nenhuma → {{"citacao": "meu cachorro se chama Bento", "contradiz": false, "duravel": true, \
"relacao": "nova"}}
PESSOA: "abre o site do banco" / {nome}: "Abri." | ANOTAÇÃO: "A pessoa prefere bancos digitais" \
→ {{"citacao": "", "contradiz": false, "duravel": true, "relacao": "nova"}}
PESSOA: "abre o site do banco" / {nome}: "Abri." | ANOTAÇÃO: "A pessoa pediu para abrir o site do banco" \
→ {{"citacao": "abre o site do banco", "contradiz": false, "duravel": false, "relacao": "nova"}}
PESSOA: "quem escreveu Dom Casmurro? adoro esse livro" / {nome}: "Foi o José de Alencar." | FONTES: [1] web_search: \
"Dom Casmurro, romance de Machado de Assis publicado em 1899" | ANOTAÇÃO: "Dom Casmurro foi escrito por José de \
Alencar" → {{"citacao": "Foi o José de Alencar.", "contradiz": true, "duravel": true, "relacao": "nova"}}
PESSOA: "quem escreveu Dom Casmurro? adoro esse livro" / {nome}: "Foi o Machado de Assis." | FONTES: [1] web_search: \
"Dom Casmurro, romance de Machado de Assis publicado em 1899" | ANOTAÇÃO: "Dom Casmurro foi escrito por Machado de \
Assis" → {{"citacao": "Dom Casmurro, romance de Machado de Assis", "contradiz": false, "duravel": true, "relacao": "nova"}}
PESSOA: "qual é o processador do meu pc?" / {nome}: "É um Ryzen 7 5700X." | FONTES: nenhuma | ANOTAÇÃO: "O PC da \
pessoa tem um Ryzen 7 5700X" → {{"citacao": "É um Ryzen 7 5700X.", "contradiz": false, "duravel": true, "relacao": "nova"}}
PESSOA: "me mudei pra Natal mês passado" | ANOTAÇÃO: "A pessoa mora em Natal" | [A] "A pessoa mora em Recife" \
→ {{"citacao": "me mudei pra Natal mês passado", "contradiz": false, "duravel": true, "relacao": "atualiza A"}}
PESSOA: "o Bento é um vira-lata de 3 anos" | ANOTAÇÃO: "Bento, o cachorro da pessoa, é um vira-lata de 3 anos" \
| [A] "A pessoa gosta de gatos" [B] "A pessoa tem um cachorro chamado Bento" \
→ {{"citacao": "o Bento é um vira-lata de 3 anos", "contradiz": false, "duravel": true, "relacao": "igual B"}}
PESSOA: "montei um servidor de Minecraft aqui em casa" | ANOTAÇÃO: "A pessoa tem um servidor de Minecraft em casa" \
| [A] "A pessoa joga Minecraft com os primos" → {{"citacao": "montei um servidor de Minecraft aqui em casa", \
"contradiz": false, "duravel": true, "relacao": "nova"}}"""


CITACAO = ('citacao: copie, exatamente como está escrito, o trecho curto que sustenta a anotação. Procure nesta ordem: '
           'nas FONTES{onde}, nas palavras da PESSOA e, só se não estiver em nenhum desses, na fala de {nome}. Se ninguém '
           'disse, deixe "".')

PEDIDO_CONFERIR = ("Só {nome} afirmou o que está na ANOTAÇÃO. Confira agora se bate, chamando uma ferramenta (no máximo "
                   "duas chamadas): web_search para fatos do mundo, fetch_page para ler uma página das FONTES, "
                   "buscar_historico_chat para o que a pessoa disse antes, ficha_da_maquina para o hardware e o sistema "
                   "deste PC. Chame a ferramenta, sem responder em texto.")


def _aspas(texto, limite):
    return '"' + " ".join(str(texto or "").split())[:limite] + '"'


def bloco_fontes(fontes) -> str:
    """As saídas de ferramenta mais recentes do turno, curtas, numeradas na ordem em que aconteceram. Se não couberem
    todas, ficam as mais novas (a última costuma ser a que embasou a resposta)."""
    escolhidas, total = [], 0
    for nome, texto in reversed(list(fontes or [])[-MAX_FONTES:]):
        trecho = " ".join(str(texto or "").split())[:MAX_FONTE]
        if not trecho or total + len(trecho) > MAX_FONTES_TOTAL:
            continue
        escolhidas.append((nome, trecho))
        total += len(trecho)
    return "\n".join(f"[{n}] {nome}: {trecho}" for n, (nome, trecho) in enumerate(reversed(escolhidas), 1))


def mensagens(pessoa: str, resposta: str, candidata: dict, antigas: list[dict], *, nome: str, fontes=None,
              conferencia=None) -> list[dict]:
    """Pedido de revisão de uma anotação. ``antigas``: [{'conteudo': ...}], no máximo três, na ordem das letras.
    ``fontes``: [(ferramenta, saída)] do turno. ``conferencia``: [(ferramenta, argumentos, saída)] feita agora."""
    linhas = ["CONVERSA:", f"PESSOA: {_aspas(pessoa, 1500)}", f"{nome.upper()}: {_aspas(resposta, 1500)}", ""]
    bloco = bloco_fontes(fontes)
    linhas += ["FONTES:", bloco, ""] if bloco else ["FONTES: nenhuma", ""]
    if conferencia is not None:
        linhas.append("CONFERÊNCIA FEITA AGORA:")
        if conferencia:
            for ferramenta, argumentos, saida in conferencia:
                args = json.dumps(argumentos or {}, ensure_ascii=False)[:200]
                linhas.append(f"- {ferramenta} {args}: {' '.join(str(saida or '').split())[:MAX_FONTE]}")
        else:
            linhas.append("- nenhuma ferramenta foi chamada; nada foi conferido.")
        linhas.append("")
    linhas += [f"ANOTAÇÃO ({candidata.get('tipo') or 'anotação'}): {_aspas(candidata.get('conteudo'), 400)}", ""]
    if antigas:
        linhas.append("JÁ GUARDADAS:")
        linhas += [f"[{letra}] {_aspas(a.get('conteudo'), 400)}" for letra, a in zip(LETRAS, antigas)]
    else:
        linhas.append("JÁ GUARDADAS: nenhuma")
    conferida = conferencia is not None
    sistema = SISTEMA.format(nome=nome, e_conferencia=", a CONFERÊNCIA FEITA AGORA" if conferida else "",
                             ou_conferencia=" ou a CONFERÊNCIA" if conferida else "",
                             instrucao_citacao=CITACAO.format(nome=nome, onde=" ou na CONFERÊNCIA" if conferida else ""))
    return [{"role": "system", "content": sistema}, {"role": "user", "content": "\n".join(linhas)}]


def ler_resposta(bruto) -> dict | None:
    """JSON do modelo validado; ``None`` quando não dá para confiar no formato."""
    if isinstance(bruto, dict):
        dados = bruto
    else:
        texto = re.sub(r"```(?:json)?|```", "", str(bruto or "")).strip()
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio == -1 or fim <= inicio:
            return None
        try:
            dados = json.loads(texto[inicio:fim + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(dados, dict) or not isinstance(dados.get("citacao"), str):
        return None
    if not isinstance(dados.get("contradiz"), bool) or not isinstance(dados.get("duravel"), bool):
        return None
    partes = str(dados.get("relacao") or "").split()
    if partes == ["nova"]:
        relacao, antiga = "nova", ""
    elif len(partes) == 2 and partes[0] in ("igual", "atualiza") and partes[1] in LETRAS:
        relacao, antiga = partes
    else:
        return None
    return dict(citacao=dados["citacao"].strip()[:300], contradiz=dados["contradiz"], duravel=dados["duravel"],
                relacao=relacao, antiga=antiga)


def _normal(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return " ".join(re.findall(r"\w+", "".join(c for c in texto if not unicodedata.combining(c))))


# 07/11 (teste de uso): a pessoa escreve como fala ("voce ta dando bastante trabalho"); o modelo copia corrigido
# ("você está dando…") e o trecho não batia, virando "sem_apoio" o que a pessoa disse de fato.
_FALA_DE_CHAT = {"ta": "esta", "tá": "esta", "to": "estou", "tô": "estou", "tao": "estao", "vc": "voce", "vcs": "voces",
                 "pra": "para", "pro": "para o", "q": "que", "n": "nao", "tb": "tambem", "tbm": "tambem",
                 "msm": "mesmo", "eh": "e", "cmg": "comigo", "ctg": "contigo", "obg": "obrigado"}


def _falado(texto: str) -> str:
    return " ".join(_FALA_DE_CHAT.get(p, p) for p in _normal(texto).split())


def _cobertura(trecho: str, texto: str) -> float:
    """Quanto do trecho está no texto (1.0 = copiado; tolera acento, caixa, pontuação e abreviação de chat)."""
    trecho, texto = _falado(trecho), _falado(texto)
    if not trecho or not texto:
        return 0.0
    if trecho in texto:
        return 1.0
    palavras, vistas = trecho.split(), set(texto.split())
    return sum(p in vistas for p in palavras) / len(palavras)


_GENERICOS = {"pessoa", "pc", "pc1", "pc2", "usuario", "usuaria", "lilith", "hoshino", "alistair", "a", "o", "os", "as"}


_VAZIAS = {"a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos",
           "nas", "para", "por", "com", "que", "e", "ou", "se", "me", "te", "eu", "voce", "ele", "ela", "isso", "esse",
           "essa", "isto", "aqui", "ai", "la", "mais", "muito", "bem", "pode", "poderia", "quero", "queria", "min", "mim",
           "pra", "ta", "esta", "estou", "nao", "sim", "ola", "oi", "so", "tambem", "ja", "agora", "ver", "the", "and"}


_PERGUNTA = re.compile(r"^\s*(?:e\s+)?(?:o\s+que|que|quem|qual|quais|quando|onde|como|por\s*que|porque|quant[oa]s?)\b"
                      r"|\?\s*$")
_PEDIDO = re.compile(r"\b(?:pode|poderia|consegue|quer|vamos|bora|abre|abra|coloca|coloque|mostra|mostre)\b")


def _nas_palavras_da_pessoa(conteudo: str, pessoa: str) -> bool:
    """A anotação traz a maior parte das palavras-chave da fala da pessoa (pelo menos duas)?

    Pergunta sobre um assunto não sustenta nada sobre ele ("o que é the boxer" não diz que é sobre uma boxeadora);
    pedido sustenta que a pessoa pediu."""
    falado = _falado(pessoa)
    if _PERGUNTA.search(falado) and not _PEDIDO.search(falado):
        return False
    chaves = {p for p in _falado(pessoa).split() if p not in _VAZIAS and (len(p) >= 3 or p.isdigit())}
    if len(chaves) < 2:
        return False
    texto = set(_falado(conteudo).split())
    return sum(p in texto for p in chaves) / len(chaves) >= 0.6


def detalhes(conteudo: str) -> set[str]:
    """Números e nomes próprios da anotação (o que mais costuma ser inventado)."""
    achados = set(re.findall(r"\d+(?:[.,]\d+)?", conteudo or ""))
    palavras = re.findall(r"[\wÀ-ÿ-]+", conteudo or "")
    for posicao, palavra in enumerate(palavras):
        if posicao and palavra[:1].isupper() and len(palavra) >= 3 and _normal(palavra) not in _GENERICOS:
            achados.add(palavra)
    return {_normal(d) for d in achados if _normal(d)}


_LUGAR = re.compile(r"\baqui dentro\b|\bdentro d[eo]st[ea] (?:computador|pc|maquina|sistema|tela)\b|"
                    r"\b(?:neste|deste) (?:computador|pc|sistema)\b|\b(?:nesta|desta) (?:maquina|instalacao|casa)\b")
_DEMONSTRATIVOS = (("nessa ", "nesta "), ("dessa ", "desta "), ("nesse ", "neste "), ("desse ", "deste "))


def lugares_de(texto: str) -> set[str]:
    """Onde ela estaria ("aqui dentro", "nesta máquina", "neste computador"…), normalizado."""
    texto = _normal(texto)
    for de, para in _DEMONSTRATIVOS:
        texto = texto.replace(de, para)
    return set(_LUGAR.findall(texto))


def apurar_base(resposta: dict, candidata: dict, *, pessoa: str, fala: str, fontes=None, conferencia=None,
                pessoa_antes: str = "") -> str:
    """Quem sustenta a anotação, decidido por este código a partir do trecho que o modelo copiou (07/11: o 9B dizia
    "a pessoa disse" para o que só a entidade tinha dito sobre a pessoa, como "o cachorro se chama Thor").

    - o trecho precisa estar num dos textos (fontes, conferência, fala da pessoa, fala da entidade); o primeiro dessa
      ordem que o contém é a base; trecho vazio ou que não está em lugar nenhum: "nenhuma";
    - nomes e números da anotação que não estão no texto da base, mas estão na fala da entidade, vieram dela:
      a base vira "entidade"."""
    textos = [("fonte", " ".join(str(t) for _, t in (fontes or []))),
              ("conferencia", " ".join(str(t) for _, _, t in (conferencia or []))),
              ("pessoa", "\n".join(t for t in (pessoa or "", pessoa_antes or "") if t)), ("entidade", fala or "")]
    citacao = resposta.get("citacao") or ""
    base = next((nome for nome, texto in textos if _cobertura(citacao, texto) >= 0.8), "nenhuma")
    falas = [pessoa or ""] + [t for t in (pessoa_antes or "").split("\n") if t.strip()]
    if base == "nenhuma" and not citacao.strip() and any(
            _nas_palavras_da_pessoa(candidata.get("conteudo") or "", f) for f in falas):
        # 07/11 (teste de uso): o 9B devolvia trecho vazio para "Gustavo quer ver um vídeo no YouTube…", que era o que
        # a pessoa tinha pedido. Sem trecho, vale se a anotação usa as palavras-chave da própria fala da pessoa.
        base = "pessoa"
    achados = detalhes(candidata.get("conteudo") or "")
    lugares = lugares_de(candidata.get("conteudo") or "")
    if lugares and base in ("fonte", "conferencia", "pessoa", "entidade"):
        # 11/11: "assumiu a responsabilidade sobre o meu funcionamento aqui dentro" — ninguém disse "aqui dentro".
        # Onde ela está não vem de fábrica nem de enfeite: o lugar da anotação tem que estar no texto da base.
        if not lugares <= lugares_de(dict(textos)[base]):
            base = "entidade" if lugares <= lugares_de(fala or "") else "nenhuma"
    if base in ("fonte", "conferencia", "pessoa"):
        texto_base = _normal(dict(textos)[base])
        faltam = {d for d in achados if d not in texto_base.split() and d not in texto_base}
        if faltam and any(d in _normal(fala) for d in faltam):
            base = "entidade"
    elif base == "entidade" and conferencia and len(achados) >= 2:
        # 07/11: depois de conferir, o 9B às vezes copiava a fala dela em vez da ficha que confirmava ("RX 6650 XT de
        # 8 GB"). Resgate estreito: todos os nomes e números da anotação (pelo menos dois) estão no que a ferramenta trouxe.
        conferido = _normal(dict(textos)["conferencia"])
        if all(d in conferido.split() or d in conferido for d in achados):
            base = "conferencia"
    return base


def decidir(resposta: dict | None, antigas: list[dict], *, conferida: bool = False) -> dict | None:
    """Regras fixas sobre a resposta do modelo. ``None`` = revisão inválida (quem chama decide o que fazer).
    ``motivo == "conferir"``: só a entidade sustenta uma anotação durável; quem chama confere com ferramentas e
    decide de novo com ``conferida=True`` (aí, sem confirmação, não entra: ``nao_conferida``)."""
    if resposta is None:
        return None
    base = dict(resposta, substitui=None, antiga_conteudo=None)
    # 07/11: o 9B marcava "contradiz" quando a pessoa corrigia uma já guardada ("agora quero respostas curtas" diante
    # de "gosta de respostas detalhadas"), mesmo instruído a não fazer isso. O que a pessoa conta de si vale pela fala
    # dela: com o trecho nas palavras dela e relação "atualiza", isso é atualização, não desmentido.
    desmentida = resposta["contradiz"] and not (resposta.get("base") == "pessoa" and resposta["relacao"] == "atualiza")
    if desmentida or resposta.get("base") == "nenhuma":
        return dict(base, guardar=False, motivo="sem_apoio")
    if not resposta["duravel"]:
        return dict(base, guardar=False, motivo="passageira")
    if resposta.get("base") == "entidade":
        return dict(base, guardar=False, motivo="nao_conferida" if conferida else "conferir")
    if resposta["relacao"] in ("igual", "atualiza"):
        indice = LETRAS.index(resposta["antiga"]) if resposta["antiga"] in LETRAS else -1
        if 0 <= indice < len(antigas) and antigas[indice].get("id"):
            alvo = antigas[indice]
            antiga = str(alvo.get("conteudo") or "")[:200]
            if not alvo.get("substituivel", True):
                # 11/11: a já guardada veio da pessoa ou de regra. "igual" = já está guardado, não repete (a memória
                # ficou poluída com 4 anotações de uma frase). "atualiza" grava a nova e a antiga fica: só a própria
                # pessoa (correção) muda o que ela disse.
                if resposta["relacao"] == "igual":
                    # Revisão (11/11): "igual" inclui "com mais detalhe". Só é repetição se a anotação não traz nome nem
                    # número que as já guardadas mostradas não tenham ("mora em Natal desde 2020" ≠ "mora em Natal").
                    conhecidos = " ".join(_normal(a.get("conteudo")) for a in antigas)
                    novos = {d for d in detalhes(resposta.get("conteudo_candidata") or "") if d not in conhecidos}
                    if not novos:
                        return dict(base, guardar=False, motivo="ja_guardada", antiga_conteudo=antiga)
                    return dict(base, guardar=True, motivo="igual_com_mais_detalhe", antiga_conteudo=antiga)
                return dict(base, guardar=True, motivo="atualiza_protegida", antiga_conteudo=antiga)
            return dict(base, guardar=True, motivo=resposta["relacao"], substitui=alvo["id"], antiga_conteudo=antiga)
        return dict(base, guardar=True, motivo="nova_sem_alvo")  # disse igual/atualiza sem apontar uma válida
    return dict(base, guardar=True, motivo="nova")


def ler_chamada(chamada) -> tuple[str, dict]:
    funcao = (chamada or {}).get("function") or {}
    nome = str(funcao.get("name") or "").strip()
    argumentos = funcao.get("arguments") or {}
    if isinstance(argumentos, str):
        try:
            argumentos = json.loads(argumentos)
        except json.JSONDecodeError:
            argumentos = {}
    return nome, argumentos if isinstance(argumentos, dict) else {}


async def conferir(pedido: list[dict], *, nome: str, chamar, executar, ferramentas: list[dict]) -> list[tuple]:
    """Até ``MAX_CONFERENCIAS`` chamadas de ferramenta de leitura. Devolve [(ferramenta, argumentos, saída)]."""
    permitidas = {f["function"]["name"] for f in ferramentas} & set(FERRAMENTAS_CONFERENCIA)
    conversa = list(pedido) + [{"role": "user", "content": PEDIDO_CONFERIR.format(nome=nome)}]
    feitas = []
    while len(feitas) < MAX_CONFERENCIAS:
        resposta = await chamar(list(conversa), ferramentas=ferramentas)
        chamadas = (resposta or {}).get("tool_calls") or []
        if not chamadas:
            break
        for chamada in chamadas[:MAX_CONFERENCIAS - len(feitas)]:
            nome, argumentos = ler_chamada(chamada)
            if nome in permitidas:
                saida = str(await executar(nome, argumentos) or "")
            else:
                saida = f"Ferramenta {nome or '?'} não está disponível para conferir."
            feitas.append((nome, argumentos, saida[:MAX_FONTE]))
            conversa += [{"role": "assistant", "content": "", "tool_calls": [chamada]},
                         {"role": "tool", "tool_name": nome, "content": saida[:MAX_FONTE]}]
    return feitas


async def revisar(candidata: dict, antigas: list[dict], *, pessoa: str, resposta: str, nome: str, fontes=None,
                  chamar, executar=None, ferramentas=None, pessoa_antes: str = "") -> tuple[dict | None, dict]:
    """Revisa uma anotação. ``chamar(mensagens, formato=None, ferramentas=None)`` devolve a mensagem do modelo
    (``content``, ``tool_calls``); ``executar(nome, argumentos)`` roda uma ferramenta de leitura. Sem ``executar``
    ou ``ferramentas``, o que só a entidade afirmou não entra (não há como conferir). Devolve (decisão,
    informações para o diagnóstico)."""
    pode_conferir = bool(executar and ferramentas)

    def lida_com_base(mensagem, conferencia=None):
        lida = ler_resposta((mensagem or {}).get("content"))
        if lida is not None:
            lida["base"] = apurar_base(lida, candidata, pessoa=pessoa, pessoa_antes=pessoa_antes, fala=resposta,
                                       fontes=fontes, conferencia=conferencia)
            lida["conteudo_candidata"] = str(candidata.get("conteudo") or "")
        return lida

    pedido = mensagens(pessoa, resposta, candidata, antigas, nome=nome, fontes=fontes)
    lida = lida_com_base(await chamar(pedido, formato=esquema(len(antigas))))
    decisao = decidir(lida, antigas, conferida=not pode_conferir)
    info = dict(conferencia=[], fontes=len(list(fontes or [])[-MAX_FONTES:]), base=(lida or {}).get("base"))
    if decisao and decisao["motivo"] == "conferir":
        feitas = await conferir(pedido, nome=nome, chamar=chamar, executar=executar, ferramentas=ferramentas or [])
        info["conferencia"] = [dict(ferramenta=n, argumentos=json.dumps(a, ensure_ascii=False)[:160]) for n, a, _ in feitas]
        final = mensagens(pessoa, resposta, candidata, antigas, nome=nome, fontes=fontes, conferencia=feitas)
        lida = lida_com_base(await chamar(final, formato=esquema(len(antigas))), feitas)
        decisao = decidir(lida, antigas, conferida=True)
        info["base"] = (lida or {}).get("base")
    return decisao, info
