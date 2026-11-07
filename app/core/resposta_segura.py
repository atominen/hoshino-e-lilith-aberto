"""Respostas imediatas para pedidos inequivocamente perigosos.

Este filtro é pequeno de propósito: ele só toma a frente do modelo quando o
pedido descreve claramente uma ação ilícita ou perigosa. Assim evita que uma
pergunta simples entre num ciclo caro de ferramentas ou receba uma resposta
genérica, mas não tenta substituir o raciocínio normal da Hoshino.
"""
from __future__ import annotations

import re
import unicodedata


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").casefold()
    return "".join(c for c in texto if not unicodedata.combining(c))


def resposta_imediata(texto: str) -> str | None:
    """Retorna orientação segura para pedidos claros; ``None`` nos demais."""
    t = _normalizar(texto)
    carro_sem_chave = re.search(
        r"\b(?:abrir|ligar|destravar|arrombar)\b.{0,70}\b(?:carro|veiculo|automovel)\b"
        r".{0,70}\b(?:sem (?:a )?chave|sem chave)\b",
        t,
    )
    if carro_sem_chave:
        return (
            "Não posso orientar a abrir ou ligar um carro sem chave. Se o carro é seu, "
            "a opção segura é usar a chave reserva, a assistência 24 horas/seguro, a "
            "concessionária ou um chaveiro automotivo com comprovante de propriedade."
        )
    if re.search(r"\b(?:levar|forcar|obrigar)\b.{0,80}\b(?:cama|sexo|transar)\b", t):
        return (
            "Não posso ajudar a pressionar, manipular ou forçar alguém numa situação "
            "sexual. Se for um encontro entre adultos, seja direto e respeitoso, aceite "
            "um não sem insistir e mantenha tudo consensual."
        )
    return None
