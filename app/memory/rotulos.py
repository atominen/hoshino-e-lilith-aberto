"""Rótulos fixos de assunto das memórias (pedido humano 11/11).

"Adicione predefinições fixas de rótulo nas memórias: se o rótulo for igual/mesmo assunto, a segunda chamada deve
verificar." Cada anotação recebe um rótulo de uma lista fechada, decidido por este código (palavras-chave e a chave
das regras), não pelo modelo. O revisor de memória (``mind/revisor_memoria``) passa a comparar a anotação nova com
as já guardadas do mesmo rótulo, venham de onde vierem (regra, pessoa, escriba), além das parecidas por palavra.

Por que no código: o rótulo só escolhe QUEM o revisor vê; um rótulo largo demais só mostra uma anotação a mais, e
quem decide se é a mesma coisa continua sendo o revisor. Rótulos amplos ("mundo", "eu", "outro") não puxam
comparação sozinhos: duas notas sobre o mundo raramente são o mesmo assunto.
"""
from __future__ import annotations

import re
import unicodedata

ROTULOS = {
    "pessoa_nome": "nome, apelido ou como a pessoa quer ser chamada",
    "pessoa_papel": "quem a pessoa é para mim (quem me criou, responsável, dono)",
    "pessoa_familia": "família, amigos e animais da pessoa",
    "pessoa_lugar": "onde a pessoa mora, cidade, mudança",
    "pessoa_trabalho": "trabalho, estudo, ocupação",
    "pessoa_saude": "saúde, sono, corpo",
    "pessoa_rotina": "horários, hábitos, agenda",
    "pessoa_gosto": "gostos, preferências e o que a pessoa não gosta",
    "pessoa_projeto": "projetos, jogos e passatempos da pessoa",
    "maquina": "computador, aparelhos e programas",
    "combinado": "como a pessoa quer que eu aja, combinados",
    "eu": "sobre mim mesma",
    "mundo": "fato do mundo",
    "outro": "nenhum dos outros",
}

# Só estes puxam comparação pelo rótulo. Os amplos ficam com a semelhança de palavras.
COMPARAVEIS = frozenset(ROTULOS) - {"eu", "mundo", "outro"}

# Chave das regras do escriba → rótulo (exato, sem palavra-chave).
_POR_CHAVE = (("nome_do_usuario", "pessoa_nome"), ("origem_", "pessoa_papel"), ("ocupacao", "pessoa_trabalho"),
              ("gosto:", "pessoa_gosto"))


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


# Ordem importa: o primeiro que casa vence. Família antes de nome ("o cachorro dela se chama Bento"); papel antes de
# nome ("Gustavo, quem me criou, se chama…"); como chamar a pessoa é nome, não combinado.
_PADROES = [
    ("pessoa_papel", r"responsavel por (eu|minha|me)|\bme (criou|fez|montou|instalou)\b|\bcriador|\bcriadora|"
                     r"\b(meu|minha) (dono|dona)\b|\bquem me (criou|fez)"),
    ("pessoa_familia", r"\b(cachorr|gat[oa]s?\b|pet\b|bicho|animal|filh[oa]|mae\b|pai\b|irma|irmao|espos|marido|"
                       r"namorad|noiv|prim[oa]|avo|avos|tio\b|tia\b|sobrinh|amig[oa])"),
    ("pessoa_nome", r"se chama|\bchamad[oa]\b|\bnome\b|apelido|me cham[ae] de|chamar (ela|ele|a pessoa)? ?de"),
    ("combinado", r"\b(quer|prefere|pediu|pede) (que eu|pra eu|para eu|que a lilith|que a hoshino)|\bcombina(do|mos)\b|"
                  r"nao quer que eu|respostas? (curtas?|longas?|detalhadas?|diretas?)|\bme avis|sempre que eu"),
    ("pessoa_lugar", r"\bmor(a|ar|ou|ei|o)\b|\bmud(ou|ei|ar)\b (pra|para)|\bcidade\b|\bbairro\b|\bvive em\b|"
                     r"\bnasceu em\b|\bnatural de\b"),
    ("pessoa_trabalho", r"\btrabalh|\bemprego|profiss|\bestud|faculdade|\bescola\b|\bcurso\b|\bempresa\b|\bcargo\b|"
                        r"carreira|\bocupa"),
    ("pessoa_saude", r"\bsaude\b|\bdoen|remedio|medic|alergi|\bdor\b|\bsono\b|\bdorm[ie]|insonia|exercicio|academia"),
    ("pessoa_rotina", r"\bhorario|\bacorda\b|\brotina\b|todo dia|toda (manha|noite|tarde)|fim de semana|\bagenda\b|"
                      r"\bcostuma"),
    ("pessoa_gosto", r"\bgost[ao]\b|\bgosta de|\badora\b|\bodeia\b|\bprefere\b|favorit|\bcurte\b|\bdetesta\b|"
                     r"\bama\b|nao gosta"),
    ("maquina", r"\bpc\d?\b|computador|\bplaca\b|processador|ryzen|\bintel\b|nvidia|radeon|\brtx\b|\bgpu\b|\bram\b|"
                r"\bssd\b|monitor|teclado|\bmouse\b|headset|celular|notebook|\blinux\b|windows|\bmint\b|ubuntu"),
    ("pessoa_projeto", r"\bprojeto|\bjog(a|o|os|ar)\b|minecraft|servidor|hobby|passatempo|\bconstru|desenvolv"),
]
_REGRAS = [(rotulo, re.compile(padrao)) for rotulo, padrao in _PADROES]
_SOBRE_MIM = re.compile(r"^(eu|minha|meu|me|mim)\b")
_SOBRE_PESSOA = re.compile(r"\b(pessoa|usuari[oa]|ele|ela|participante)\b")


def rotular(conteudo: str, tipo: str = "", chave: str = "") -> str:
    """Rótulo fixo de uma anotação. Sempre devolve um dos ``ROTULOS``."""
    chave = str(chave or "")
    for prefixo, rotulo in _POR_CHAVE:
        if chave == prefixo or (prefixo.endswith(("_", ":")) and chave.startswith(prefixo)):
            return rotulo
    texto = _normal(conteudo)
    if not texto:
        return "outro"
    for rotulo, padrao in _REGRAS:
        if padrao.search(texto):
            return rotulo
    if _SOBRE_MIM.search(texto):
        return "eu"
    if str(tipo or "") == "fato" and not _SOBRE_PESSOA.search(texto):
        return "mundo"
    return "outro"


def valido(rotulo) -> bool:
    return rotulo in ROTULOS
