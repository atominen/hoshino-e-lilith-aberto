"""Estado de conversa: memória de trabalho por canal/thread, não por processo.

A identidade da Hoshino é global; o *fio da conversa* não é. Cada canal/destino
mantém seu próprio histórico de curto prazo. Assim, uma DM do Discord não pode
contaminar uma conversa no TUI, e mensagens que chegaram enquanto o modelo pensava
não entram retroativamente no turno que já estava sendo calculado.
"""
from __future__ import annotations

import re
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_CORRECAO_RE = re.compile(
    r"^(?:espera|espere|pera|nada disso|esquece(?: isso)?|esquec[eê](?: isso)?|"
    r"corrigindo|correção|correcao|na verdade|melhor |troca|troque|"
    r"muda|mudando|deixa pra la|deixa pra lá|cancel[ae]|pare(?: de)?|"
    r"nao quero|não quero|nao faca|não faça)\b",
    re.IGNORECASE,
)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()


def parece_correcao(texto: str) -> bool:
    """Detecta marcadores de correção/cancelamento sem tentar interpretar o pedido inteiro."""
    t = normalizar(texto)
    if not t:
        return False
    if re.match(r"^para(?:[.!]+(?:\s|$)|\s*$)", t) or re.match(r"^nao\s*[,;:]\s*\S", t):
        return True
    if _CORRECAO_RE.search(t):
        return True
    # "não sei", "não entendi" etc. são fala normal, não correção.
    return bool(re.search(r"^(?:na verdade|espera|pera|esquece|cancel[ae]|pare(?: de)?|nao quero|não quero|nao faca|não faça)\b", t))


def extrair_ultima_pergunta(texto: str) -> str:
    partes = re.split(r"(?<=[?!])\s+", (texto or "").strip())
    perguntas = [p.strip() for p in partes if "?" in p]
    return perguntas[-1][:500] if perguntas else ""


@dataclass
class ConversationState:
    key: tuple[str, str]
    canal: str
    destino: str
    historico: list[dict[str, Any]] = field(default_factory=list)
    participantes: dict[str, dict[str, Any]] = field(default_factory=dict)
    pessoa_atual: dict[str, Any] | None = None
    mensagens_pendentes: deque = field(default_factory=deque)
    saidas_recentes: deque = field(default_factory=lambda: deque(maxlen=5))
    ultima_entrada: str = ""
    ultima_resposta: str = ""
    ultima_pergunta: str = ""
    turno: int = 0
    revisao: int = 0
    geracao_revisao: int = 0
    cancelar_geracao: bool = False
    ultima_atividade: datetime = field(default_factory=datetime.now)

    def receber(self, texto: str, pessoa: dict | None = None, **dados) -> dict:
        self.revisao += 1
        self.ultima_atividade = datetime.now()
        if pessoa:
            pid = str(pessoa.get("id") or pessoa.get("nome") or "")
            if pid:
                self.participantes[pid] = dict(pessoa)
            self.pessoa_atual = pessoa
        item = {
            "texto": texto,
            "pessoa": pessoa,
            "canal": dados.get("canal", self.canal),
            "responder_para": str(dados.get("responder_para", self.destino) or ""),
            "revisao": self.revisao,
        }
        self.mensagens_pendentes.append(item)
        if parece_correcao(texto) and self.geracao_revisao:
            self.cancelar_geracao = True
        return item

    def iniciar_turno(self, lote: list[dict]) -> tuple[list[dict], int]:
        self.turno += 1
        self.geracao_revisao = self.revisao
        self.cancelar_geracao = False
        entradas = []
        for item in lote:
            msg = {"role": "user", "content": item.get("texto", "")}
            if item.get("imagens_b64"):
                msg["images"] = item["imagens_b64"]
            self.historico.append(msg)
            entradas.append(msg)
        self.ultima_entrada = "\n".join(i.get("texto", "") for i in lote).strip()
        if lote and lote[-1].get("pessoa"):
            self.pessoa_atual = lote[-1]["pessoa"]
        return entradas, self.geracao_revisao

    def anexar_resposta(self, conteudo: str) -> None:
        self.historico.append({"role": "assistant", "content": conteudo})
        self.ultima_resposta = conteudo
        self.ultima_pergunta = extrair_ultima_pergunta(conteudo)
        self.ultima_atividade = datetime.now()

    def registrar_saida(self, nome: str, resultado: str) -> None:
        from core import diagnostics
        resultado=diagnostics._redact({'tool':nome,'output':resultado or ''},truncate=False)['output']
        self.saidas_recentes.append((nome, resultado or ""))

    def texto_estado(self) -> str:
        linhas = [f"[FIO DE CONVERSA] turno {self.turno}; canal={self.canal}; destino={self.destino or 'local'}"]
        if self.ultima_pergunta:
            linhas.append(f"[PERGUNTA MINHA AINDA NO FIO] {self.ultima_pergunta}")
        if self.participantes:
            nomes = [str(p.get("nome") or pid) for pid, p in list(self.participantes.items())[-4:]]
            linhas.append("[PESSOAS PRESENTES NESTE FIO] " + ", ".join(nomes))
        if self.ultima_resposta:
            linhas.append(f"[MINHA ÚLTIMA FALA] {self.ultima_resposta[:700]}")
        if self.saidas_recentes:
            linhas.append("[RESULTADOS RECENTES DE FERRAMENTAS NESTE FIO]\n" +
                          "\n".join(f"- {n}: {r[:700]}" for n, r in self.saidas_recentes))
        return "\n".join(linhas)

    def limpar(self) -> None:
        self.historico.clear()
        self.mensagens_pendentes.clear()
        self.saidas_recentes.clear()
        self.ultima_entrada = ""
        self.ultima_resposta = ""
        self.ultima_pergunta = ""
        self.turno = 0
        self.revisao += 1
        self.cancelar_geracao = False
