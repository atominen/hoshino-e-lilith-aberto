"""Disse que ia conferir (ou que conferiu) sem chamar ferramenta nenhuma? (07/11, pedido humano)

Medido nas perguntas de fato: o 9B escrevia "Vou verificar a ficha do PC e te respondo" e parava, ou pior, "O que
aparece na ficha é: Intel Core Ultra 5…" sem ter chamado a ficha. O ciclo de ferramentas usa isto para uma única
recuperação dirigida no turno: pede a chamada de verdade, ou que ela diga que não conferiu.
"""
from __future__ import annotations

import re
import unicodedata

_VERBO = r"(?:verificar|conferir|checar|olhar|ver|pesquisar|procurar|consultar|buscar|confirmar|ler)"
_ANUNCIA = re.compile(
    rf"\b(?:vou|deixa eu|deixe eu|irei|j[aá] vou|agora vou|vou te)\s+(?:\w+\s+)?{_VERBO}\b"
    r"|\b(?:pesquisando|verificando|conferindo|consultando|checando|procurando)\b"
    r"|\b(?:aparece|mostra|diz|indica|consta)\s+(?:na|no|a|o|nas|nos)\s+(?:ficha|pesquisa|busca|sistema|resultado|"
    r"internet|historico|registro|arquivo)\b"
    r"|\bsegundo (?:a|o) (?:ficha|pesquisa|busca|sistema|historico)\b"
    # "não conferi nada" é honestidade, não alegação de conferência
    r"|(?<!nao )(?<!nem )\b(?:pesquisei|conferi|verifiquei|consultei|chequei|olhei na|vi na ficha)\b")

PEDIDO = ("CONFERÊNCIA PENDENTE: na resposta acima você disse que ia conferir, ou que viu algo numa ferramenta, mas "
          "não chamou nenhuma ferramenta neste turno. Chame agora a ferramenta certa (ficha_da_maquina, pesquisa, "
          "histórico ou memória). Se não houver como conferir, responda dizendo que não conferiu e não sabe.")

# Teste de uso 07/11: "Vou abrir o Firefox para você. Apareceu uma aba vazia." sem ferramenta nenhuma. Ação no
# computador anunciada, alegada ou com resultado inventado, sem chamada, é o mesmo erro com outro verbo.
_ACAO = (r"(?:abrir|fechar|criar|apagar|excluir|deletar|mover|renomear|salvar|enviar|mandar|instalar|desinstalar|"
         r"executar|rodar|iniciar|ligar|desligar|focar|minimizar|maximizar|copiar|colar|baixar|tocar|pausar|chamar)")
# "Vou abrir" só conta quando a pessoa pediu uma ação ("vou mandar um abraço" é conversa); "abri", "apareceu",
# "está aberto" sem chamada é alegação falsa sempre.
_VAI_FAZER = re.compile(
    rf"(?<!nao )\b(?:vou|deixa eu|deixe eu|irei|j[aá] vou|agora vou|vou te)\s+(?:\w+\s+)?{_ACAO}\b"
    r"|\b(?:abrindo|fechando|criando|apagando|enviando|mandando|instalando|executando|rodando|iniciando|baixando)\b")
_DIZ_QUE_FEZ = re.compile(
    r"(?<!nao )(?<!nem )(?<!nao consegui )\b(?:abri|fechei|criei|apaguei|exclui|deletei|movi|renomeei|salvei|enviei|"
    r"mandei|instalei|desinstalei|executei|rodei|iniciei|liguei|desliguei|foquei|minimizei|maximizei|copiei|colei|"
    r"baixei)\b"
    r"|\b(?:apareceu|ja abriu|ficou aberto|ficou aberta)\b"
    # 07/11: "O vídeo já estava aberto e tocando" (nada estava): estado afirmado sem ter olhado
    r"|(?<!nao )(?<!nem )\b(?:ja )?(?:esta|estava|ja ta)\s+(?:aberto|aberta|tocando|rodando|passando|funcionando|na tela|pronto|pronta)\b"
    r"|\b(?:ja esta|ja estava) (?:la|ai|aberto|aberta)\b")
_PEDE_ACAO = re.compile(  # formas exatas: "um abraço" e "colega" não são pedido de abrir/colar
    r"\b(?:abr(?:e|es|a|am|ir|indo|iu)|fech(?:e|a|ar|ando|ou)|cri(?:e|a|ar|ando|ou)|apag(?:ue|a|ar|ando|ou)|"
    r"exclu(?:a|i|ir|indo)|delet(?:e|a|ar)|mov(?:a|e|er)|renome(?:ie|ia|ar)|salv(?:e|a|ar|ando)|envi(?:e|a|ar|ando)|"
    r"mand(?:e|a|ar|ando)|instal(?:e|a|ar|ando)|execut(?:e|a|ar|ando)|rod(?:e|a|ar|ando)|inici(?:e|a|ar|ando)|"
    r"lig(?:ue|a|ar|ando)|deslig(?:ue|a|ar)|foc(?:a|ar)|foque|minimiz(?:e|a|ar)|maximiz(?:e|a|ar)|copi(?:e|a|ar)|"
    r"col(?:e|a|ar)|baix(?:e|a|ar|ando)|toc(?:a|ar)|toque|paus(?:e|a|ar)|cham(?:e|a|ar))\b")

# 12/11: pedidos de ação fora da lista de verbos de computador ("conecte no servidor", "entra lá", "joga sozinha").
_PEDE_ACAO_GERAL = re.compile(r"\b(?:conect(?:e|a|ar|ando)|entr(?:e|a|ar) (?:no|na|la|em)|jog(?:ue|a|ar)\b|"
                              r"desconect(?:e|a|ar))")

PEDIDO_ACAO = ("AÇÃO PENDENTE: na resposta acima você disse que fez, ou que ia fazer, algo no computador (abrir, "
               "criar, enviar, fechar…), mas não chamou nenhuma ferramenta neste turno, então nada aconteceu de "
               "verdade. Chame agora a ferramenta certa. Se não houver ferramenta para isso, diga com honestidade que "
               "não fez e por quê.")


# 11/11 (teste de uso): cobrada uma vez, ela anunciou de novo ("Vou conferir as janelas do PC2.") e isso foi enviado.
# Segunda e última chance, sem ferramentas: dizer com as próprias palavras que não fez. Se nem assim, vai o FALLBACK.
PEDIDO_HONESTO = ("Você foi cobrada e mesmo assim não chamou nenhuma ferramenta: nada foi conferido nem feito. Não "
                  "escreva \"vou conferir\", \"vou olhar\" nem nada que prometa ou alegue a ação. Diga à pessoa, em "
                  "uma ou duas frases do seu jeito, que não conseguiu fazer isso agora, e pergunte se ela quer que você "
                  "tente de novo.")
FALLBACK_HONESTO = "Não consegui fazer isso agora. Quer que eu tente de novo?"


# 07/11 (teste de uso): "encontre o manga the boxer e me manda o link" → "Já deixei o link aberto" (no PC1, sem link na
# conversa). Pediu link, a ferramenta trouxe endereço e a resposta não tem nenhum: falta mandar.
_PEDE_LINK = re.compile(r"\b(?:link|links|endere[cç]o|url)\b", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<>\]\)\"']+")
PEDIDO_LINK = ("LINK PENDENTE: a pessoa pediu o link e a sua resposta não tem nenhum endereço. Responda de novo, curto, "
               "com o endereço completo (https://…) que a ferramenta trouxe.")


def faltou_link(resposta: str, *, pedido: str, saidas_ferramentas) -> bool:
    """A pessoa pediu link, alguma ferramenta trouxe um e a resposta não mandou nenhum?"""
    if not _PEDE_LINK.search(pedido or "") or _URL.search(resposta or ""):
        return False
    return any(_URL.search(str(s or "")) for s in (saidas_ferramentas or []))


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in texto if not unicodedata.combining(c))


def anunciou_sem_conferir(resposta: str, *, ferramentas_usadas, ferramentas_oferecidas) -> bool:
    """A resposta anuncia ou alega uma conferência que não aconteceu, havendo ferramenta para fazê-la?"""
    if ferramentas_usadas or not ferramentas_oferecidas or not (resposta or "").strip():
        return False
    return bool(_ANUNCIA.search(_normal(resposta)))


# 12/11 (Minecraft, medição em runtime/ensaios/acao-minecraft-20261112): com os pesos treinados (v5 e v6) a Lilith
# escreveu "Vou conectar agora", "Vou chamar minecraft_estado" e "Conectando ao seu servidor..." por 10 passos sem
# chamar nada. "conectar" não está na lista de verbos de computador acima, e nem precisa estar: a âncora passa a ser a
# própria ferramenta oferecida. Vale o nome dela escrito no texto, ou o verbo do nome anunciado ("vou conectar" ↔
# minecraft_conectar) quando a pessoa pediu essa ação ("conecte…"). Com a cobrança dirigida abaixo e o raciocínio
# ligado, o v6 foi de 0/5 para 5/5; o 9B original continuou em 5/5.
MAX_COBRANCAS = 3  # cobranças dirigidas por turno antes do pedido de honestidade (medido: até duas bastaram)
_PREFIXO_ANUNCIO = r"\b(?:vou|irei|deixa eu|deixe eu|ja vou|agora vou|vou te)\b"
_VERBO_DE_FERRAMENTA = re.compile(r"[a-z]{3,}(?:ar|er|ir)")


def _nomes(ferramentas_oferecidas) -> list[str]:
    nomes = []
    for f in ferramentas_oferecidas or []:
        nome = f if isinstance(f, str) else ((f or {}).get("function") or {}).get("name")
        if nome:
            nomes.append(str(nome))
    return nomes


def ferramentas_anunciadas(resposta: str, ferramentas_oferecidas, pedido: str = "", usadas=()) -> list[str]:
    """Ferramentas oferecidas (e não chamadas neste turno) que a resposta cita pelo nome ou anuncia pelo verbo."""
    texto, falado = _normal(resposta), _normal(pedido)
    if not texto.strip():
        return []
    feitas, citadas, anunciadas = set(usadas or ()), [], []
    for nome in _nomes(ferramentas_oferecidas):
        if nome in feitas:
            continue
        if "_" in nome and re.search(rf"(?<![a-z0-9_]){re.escape(nome)}(?![a-z0-9_])", texto):
            citadas.append(nome)  # nome de ferramenta em prosa nunca é conversa
            continue
        for parte in nome.split("_"):
            if len(parte) < 5 or not _VERBO_DE_FERRAMENTA.fullmatch(parte):
                continue
            raiz = re.escape(parte[:-2])
            if not re.search(rf"\b{raiz}\w*", falado):  # só quando a pessoa pediu essa ação
                continue
            if (re.search(rf"(?<!nao ){_PREFIXO_ANUNCIO}[^.!?\n]{{0,80}}\b{re.escape(parte)}\b", texto)
                    or re.search(rf"\b{raiz}(?:ando|endo|indo)\b", texto)):
                anunciadas.append(nome)
                break
    return (citadas + anunciadas)[:4]


def anunciou_sem_fazer(resposta: str, *, ferramentas_usadas, ferramentas_oferecidas, pedido: str = "") -> str | None:
    """'conferir' ou 'acao' quando a resposta anuncia/alega o que não aconteceu (havendo ferramenta); senão None.

    ``pedido`` é a fala da pessoa: "vou abrir" só é cobrado quando ela pediu uma ação."""
    if anunciou_sem_conferir(resposta, ferramentas_usadas=ferramentas_usadas,
                             ferramentas_oferecidas=ferramentas_oferecidas):
        return "conferir"
    if not ferramentas_oferecidas or not (resposta or "").strip():
        return None
    # Anúncio de uma ferramenta que ainda não foi chamada vale mesmo depois de outras ("iniciei a ponte, vou conectar").
    if ferramentas_anunciadas(resposta, ferramentas_oferecidas, pedido, usadas=ferramentas_usadas):
        return "acao"
    if ferramentas_usadas:
        return None
    texto = _normal(resposta)
    if _DIZ_QUE_FEZ.search(texto) or (_VAI_FAZER.search(texto) and _PEDE_ACAO.search(_normal(pedido))):
        return "acao"
    return None


def cobranca(resposta: str, falta: str, *, ferramentas_oferecidas, pedido: str = "", ferramentas_usadas=()) -> str:
    """Texto da cobrança. Quando dá para dizer QUAL ferramenta ela anunciou, diz pelo nome (medido em 12/11)."""
    alvo = ferramentas_anunciadas(resposta, ferramentas_oferecidas, pedido, usadas=ferramentas_usadas)
    if not alvo:
        return PEDIDO if falta == "conferir" else PEDIDO_ACAO
    return ("NADA ACONTECEU: a resposta acima foi só texto e nenhuma ferramenta foi chamada. Escrever \"vou chamar\" "
            "ou \"conectei\" não executa nada. Ferramentas que você citou: " + ", ".join(alvo) + ". Emita agora a "
            "chamada da ferramenta (tool call), com os argumentos, em vez de descrever o que vai fazer. Se não houver "
            "o que executar, diga com honestidade que não fez.")


def pede_acao(pedido: str) -> bool:
    """A fala da pessoa pede uma ação no computador? (liga o raciocínio do turno: sem ele o modelo treinado anuncia)"""
    return bool(_PEDE_ACAO.search(_normal(pedido)) or _PEDE_ACAO_GERAL.search(_normal(pedido)))
