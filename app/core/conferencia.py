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


def _normal(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in texto if not unicodedata.combining(c))


def anunciou_sem_conferir(resposta: str, *, ferramentas_usadas, ferramentas_oferecidas) -> bool:
    """A resposta anuncia ou alega uma conferência que não aconteceu, havendo ferramenta para fazê-la?"""
    if ferramentas_usadas or not ferramentas_oferecidas or not (resposta or "").strip():
        return False
    return bool(_ANUNCIA.search(_normal(resposta)))
