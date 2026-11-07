"""Primitivas determinísticas e baratas para operações objetivas."""
from __future__ import annotations

import ast
import math
import operator
import secrets
from fractions import Fraction

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _numero(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError("número inválido")
    if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
        raise ValueError("resultado não finito")
    return valor


def _avaliar_no(no, profundidade=0):
    if profundidade > 40:
        raise ValueError("expressão profunda demais")
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)) and not isinstance(no.value, bool):
        return _numero(no.value)
    if isinstance(no, ast.UnaryOp) and type(no.op) in _UN:
        return _numero(_UN[type(no.op)](_avaliar_no(no.operand, profundidade + 1)))
    if isinstance(no, ast.BinOp) and type(no.op) in _BIN:
        a = _avaliar_no(no.left, profundidade + 1)
        b = _avaliar_no(no.right, profundidade + 1)
        if type(no.op) is ast.Pow and abs(b) > 100:
            raise ValueError("expoente máximo excedido")
        try:
            out = _BIN[type(no.op)](a, b)
        except ZeroDivisionError as exc:
            raise ValueError("divisão por zero") from exc
        out = _numero(out)
        if abs(out) > 10**30:
            raise ValueError("resultado grande demais")
        return out
    raise ValueError("expressão contém operação não permitida")


def calcular(expressao: str) -> str:
    """Calcula apenas aritmética explícita; nunca executa código."""
    texto = str(expressao or "").strip().replace("^", "**")
    if not texto:
        return "ERRO_CALCULO: expressão vazia"
    try:
        arvore = ast.parse(texto, mode="eval")
        valor = _avaliar_no(arvore.body)
    except (SyntaxError, ValueError, TypeError) as exc:
        return f"ERRO_CALCULO: {exc}"
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return f"CALCULO={texto} RESULTADO={valor}"


def _inteiro(minimo: int, maximo: int) -> int:
    if minimo > maximo:
        raise ValueError("intervalo inválido")
    return minimo + secrets.randbelow(maximo - minimo + 1)


def sortear(tipo: str = "inteiro", quantidade: int = 1, lados: int = 6,
            minimo: int = 1, maximo: int = 100, opcoes: list[str] | None = None) -> str:
    """Sorteios determinísticos no formato, aleatórios no resultado, sem LLM."""
    tipo_n = str(tipo or "inteiro").strip().casefold()
    quantidade = max(1, min(int(quantidade or 1), 100))
    if tipo_n in {"moeda", "cara ou coroa", "cara_ou_coroa", "coin"}:
        valores = ["cara" if secrets.randbelow(2) == 0 else "coroa" for _ in range(quantidade)]
        return f"SORTEIO=moeda RESULTADOS={','.join(valores)}"
    if tipo_n in {"dado", "dados", "die", "dice"}:
        lados = max(2, min(int(lados or 6), 1000))
        valores = [_inteiro(1, lados) for _ in range(quantidade)]
        return f"SORTEIO=dados LADOS={lados} RESULTADOS={','.join(map(str, valores))} SOMA={sum(valores)}"
    if tipo_n in {"escolha", "opcao", "opções", "opcoes"}:
        opcoes = [str(x) for x in (opcoes or []) if str(x).strip()]
        if not opcoes:
            return "ERRO_SORTEIO: nenhuma opção"
        valores = [opcoes[secrets.randbelow(len(opcoes))] for _ in range(quantidade)]
        return f"SORTEIO=escolha RESULTADOS={','.join(valores)}"
    minimo = int(minimo)
    maximo = int(maximo)
    valores = [_inteiro(minimo, maximo) for _ in range(quantidade)]
    return f"SORTEIO=inteiro MIN={minimo} MAX={maximo} RESULTADOS={','.join(map(str, valores))}"
