"""Regressões do agendador de tool calls de uma única etapa do modelo."""
import asyncio
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import main
from core import cognition, dispatch


class _Log:
    def write(self, _texto):
        pass


def _app():
    # Não chamamos o construtor da UI: este teste só cobre o agendador puro.
    app = object.__new__(main.InterfaceHoshino)
    app.sys_log = _Log()
    return app


def _calls(*nomes):
    return [{"function": {"name": nome, "arguments": {}}} for nome in nomes]


def main_test():
    original = dispatch.executar
    ativos, pico = 0, 0
    lock = threading.Lock()

    def lento(nome, _args, _confirmado=False):
        nonlocal ativos, pico
        with lock:
            ativos += 1
            pico = max(pico, ativos)
        time.sleep(0.15)
        with lock:
            ativos -= 1
        return f"ok:{nome}"

    dispatch.executar = lento
    frame = cognition.criar_frame("consultar estados", [])
    try:
        resultados = asyncio.run(_app()._executar_chamadas_da_etapa(
            _calls("get_system_time", "estado_internet"), frame, 1, set()))
        assert [r[0] for r in resultados] == ["get_system_time", "estado_internet"]
        assert pico == 2, f"consultas deveriam coincidir; pico={pico}"

        ativos = pico = 0
        resultados = asyncio.run(_app()._executar_chamadas_da_etapa(
            _calls("write_file", "write_file"), frame, 1, set()))
        assert [r[0] for r in resultados] == ["workspace", "workspace"]
        assert all(r[1]["operacao"] == "salvar" for r in resultados)
        assert all(not r[2]["verified"] for r in resultados), "mock de agendamento não prova escrita"
        assert pico == 1, f"ações mutáveis devem permanecer seriais; pico={pico}"

        resultados = asyncio.run(_app()._executar_chamadas_da_etapa(
            [{"function": {"name": "get_system_time", "arguments": "{"}}],
            frame, 1, set()))
        assert resultados[0][2]["status"] == "error"
        assert "JSON válido" in resultados[0][2]["output"]

        try:
            asyncio.run(_app()._executar_chamadas_da_etapa(
                _calls("get_system_time"), frame, 1, set(), cancelar=lambda: True))
        except main.TurnoCancelado:
            pass
        else:
            raise AssertionError("correção deveria cancelar antes de chamar ferramenta")
    finally:
        dispatch.executar = original

    print("ok - consultas independentes paralelas; ações e chamadas inválidas seguras")


if __name__ == "__main__":
    main_test()
