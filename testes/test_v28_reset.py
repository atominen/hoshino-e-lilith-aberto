"""Verifica os resets funcionais sem depender da UI real nem do Ollama real."""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

# Import mínimo do main em ambientes sem Textual instalado.
for mod_name, attrs in [
    ("textual", {}),
    ("textual.app", {"App": object, "ComposeResult": object}),
    ("textual.binding", {"Binding": lambda *a, **k: None}),
    ("textual.containers", {"Horizontal": object, "Vertical": object}),
    ("textual.widgets", {"Footer": object, "Header": object, "RichLog": object, "TextArea": object, "Static": object}),
]:
    mod = types.ModuleType(mod_name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[mod_name] = mod

import main  # noqa: E402


class Log:
    def __init__(self):
        self.messages = []
        self.cleared = 0
    def write(self, msg, *a, **k):
        self.messages.append(str(msg))
    def clear(self):
        self.cleared += 1


import unittest


class TestResetV28(unittest.TestCase):
    def _app(self):
        app = object.__new__(main.InterfaceHoshino)
        app.sys_log = Log()
        app.chat_log = Log()
        app._fila_conversa = __import__("collections").deque([1, 2])
        app._workers_por_chave = {}
        app._fila_chaves = {"a": []}
        app._travas_conversa = {}
        app._versao_fila_conversa = 0
        app._historicos_por_chave = {"x": [1]}
        app._revisoes_conversa = {"x": 1}
        app._saidas_por_conversa = {"x": [1]}
        app.messages = [{"role": "user", "content": "oi"}]
        app.ultima_entrada = "oi"
        app.saidas_recentes = __import__("collections").deque([1])
        app._memory_generation = 0
        app._reset_em_andamento = True
        app.pessoa = {"id": "p"}
        app.pessoa_local = {"id": "p"}
        app.prompt_sistema = "old"
        return app

    def test_f5_limpa_ui_historico_tarefa_e_descarrega(self):
        app = self._app()
        async def no_wait(*a, **k): return True
        with patch.object(main.history, "clear_messages", return_value=7) as clear_hist, \
             patch.object(main.task_state, "limpar_chave", return_value=1) as clear_task, \
             patch.object(main.ollama_lifecycle, "descarregar_modelo", return_value=(True, "unload")) as unload, \
             patch.object(main.people, "identificar", return_value={"id": "local"}), \
             patch.object(main, "registrar_evento"):
            with patch.object(app, "_aguardar_llm_livre", new=AsyncMock(return_value=True)):
                asyncio.run(app._reset_context_async())
        assert clear_hist.call_args.args == ("tui", "local")
        clear_task.assert_called_once_with(("tui", "local", ""))
        unload.assert_called_once()
        assert app.messages == []
        assert app._historicos_por_chave == {}
        assert app.chat_log.cleared == 1
        assert app._fila_conversa == __import__("collections").deque()

    def test_f6_nao_resemeia_curiosidades(self):
        app = self._app()
        with patch("tools.memory_admin.wipe_persistent_memory", return_value="apagado") as wipe, \
             patch.object(main.task_state, "limpar_tudo", return_value=(1, 2)) as clear_all, \
             patch.object(main.ollama_lifecycle, "descarregar_modelo", return_value=(True, "unload")) as unload, \
             patch.object(main.people, "identificar", return_value={"id": "local"}), \
             patch.object(main, "registrar_evento"), \
             patch.object(app, "_aguardar_llm_livre", new=AsyncMock(return_value=True)):
            asyncio.run(app._reset_memory_async())
        wipe.assert_called_once()
        clear_all.assert_called_once()
        unload.assert_called_once()
        assert app.chat_log.cleared == 1
        assert not any("semear" in x.lower() for x in app.sys_log.messages)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
