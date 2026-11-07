"""Regressões do reset total F6 e do reset de conversa F5."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import types
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.chdir(ROOT)

import config  # noqa: E402
from memory.sqlite import init_db  # noqa: E402
from tools import memory_admin  # noqa: E402

# Importa main sem depender de Textual instalado.
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


def build_app():
    app = object.__new__(main.InterfaceHoshino)
    app.sys_log = Log()
    app.chat_log = Log()
    app._fila_conversa = deque([1, 2])
    app._workers_por_chave = {}
    app._fila_chaves = {"tui::local::": []}
    app._travas_conversa = {}
    app._versao_fila_conversa = 0
    app._historicos_por_chave = {"x": [1]}
    app._revisoes_conversa = {"x": 1}
    app._saidas_por_conversa = {"x": [1]}
    app.messages = [{"role": "user", "content": "oi"}]
    app.ultima_entrada = "oi"
    app.saidas_recentes = deque([1])
    app._memory_generation = 0
    app._reset_em_andamento = False
    app.pessoa = {"id": "p"}
    app.pessoa_local = {"id": "p"}
    app.prompt_sistema = "old"
    app.entrada = type("Entrada", (), {"clear": lambda self: None})()
    return app


def test_f6_zerar_todas_tabelas_e_historico():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "h.db"
        hist = Path(td) / "history.sqlite3"
        config.DB_PATH = str(db)
        init_db.DB_PATH = str(db)
        memory_admin.DB_PATH = str(db)
        init_db._schema_done = False if hasattr(init_db, '_schema_done') else None
        init_db.init_database(verbose=False)

        con = sqlite3.connect(db)
        cur = con.cursor()
        tables = memory_admin._tabelas_dinamicas(cur)
        assert "messages" not in tables
        assert "events" not in tables
        for table in tables:
            cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')]
            if not cols:
                continue
            # Escreve uma linha genérica só nas tabelas que permitem um teste simples.
            # Em tabelas complexas, basta verificar que a função percorre a tabela.
        cur.close(); con.close()

        # Cria registros reais em duas tabelas e no histórico separado.
        con = sqlite3.connect(db)
        con.execute("INSERT INTO facts (id, content, confidence) VALUES ('x','memoria',1)")
        con.execute("INSERT INTO goals (id, description, status) VALUES ('g','objetivo','active')")
        con.commit(); con.close()

        from core import history
        history.DB = Path(hist)
        history._INITIALIZED_DB = None
        history.message("in", "user", "chat antigo")
        history.event("evento_antigo")

        runtime = Path(td) / "runtime"
        runtime.mkdir()
        mente = runtime / "estado_mente.json"
        reflexao = runtime / "reflexao_noturna.json"
        reflexao_pendente = runtime / "reflexao_noturna_pendente.json"
        mente.write_text("{}", encoding="utf-8")
        reflexao.write_text("{}", encoding="utf-8")
        reflexao_pendente.write_text("{}", encoding="utf-8")
        bus = runtime / "bus"
        (bus / "entrada").mkdir(parents=True)
        (bus / "saida").mkdir(parents=True)
        (bus / "discord_estado.json").write_text("{}", encoding="utf-8")
        (bus / "discord_usuarios.json").write_text("{}", encoding="utf-8")
        (bus / "discord_contatos.json").write_text("{}", encoding="utf-8")
        (bus / "entrada" / "msg.json").write_text("{}", encoding="utf-8")
        (bus / "saida" / "out.json").write_text("{}", encoding="utf-8")
        jobs = runtime / "jobs"
        jobs.mkdir()
        (jobs / "job.json").write_text("{}", encoding="utf-8")
        # Configurações/políticas não são memória e devem sobreviver ao F6.
        (runtime / "rede.json").write_text("{}", encoding="utf-8")
        (runtime / "modo_interacao.json").write_text("{}", encoding="utf-8")
        memory_admin._ESTADO_MENTE = mente
        memory_admin._REFLEXAO_NOTURNA = reflexao
        memory_admin._REFLEXAO_NOTURNA_PENDENTE = reflexao_pendente
        memory_admin._RUNTIME_DIR = runtime
        memory_admin._RUNTIME_JSON_DINAMICOS = (
            bus / "discord_estado.json", bus / "discord_usuarios.json", bus / "discord_contatos.json"
        )
        memory_admin._RUNTIME_GLOB_DINAMICOS = (bus / "entrada", bus / "saida", jobs)

        with patch.object(memory_admin, "COLECOES_VETORIAIS", ()):
            resultado = memory_admin.wipe_persistent_memory()
        assert "Todos os registros persistentes foram zerados" in resultado
        assert memory_admin.memoria_restante() == ""
        assert not mente.exists()
        assert not reflexao.exists()
        assert not reflexao_pendente.exists()
        assert not (bus / "discord_estado.json").exists()
        assert not (bus / "discord_usuarios.json").exists()
        assert not (bus / "discord_contatos.json").exists()
        assert not (bus / "entrada" / "msg.json").exists()
        assert not (bus / "saida" / "out.json").exists()
        assert not (jobs / "job.json").exists()
        assert (runtime / "rede.json").exists()
        assert (runtime / "modo_interacao.json").exists()
        assert history.search("chat antigo", 10) == []
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0
        con.close()


def test_f5_limpa_chat_e_pede_unload():
    app = build_app()
    async def run():
        with patch.object(main.history, "clear_messages", return_value=3) as clear_hist, \
             patch.object(main.task_state, "limpar_chave", return_value=1) as clear_task, \
             patch.object(main.ollama_lifecycle, "descarregar_modelo", return_value=(True, "unload")) as unload, \
             patch.object(main.people, "identificar", return_value={"id": "local"}), \
             patch.object(main, "registrar_evento"), \
             patch.object(app, "_aguardar_llm_livre", new=AsyncMock(return_value=True)):
            await app._reset_context_async()
        assert clear_hist.call_args.args == ("tui", "local")
        clear_task.assert_called_once_with(("tui", "local", ""))
        unload.assert_called_once()
        assert app.messages == []
        assert app.chat_log.cleared >= 1
        assert app._fila_conversa == deque()
        assert not app._reset_em_andamento

    asyncio.run(run())


if __name__ == "__main__":
    test_f6_zerar_todas_tabelas_e_historico()
    test_f5_limpa_chat_e_pede_unload()
    print("ok - reset total e reset de conversa")
