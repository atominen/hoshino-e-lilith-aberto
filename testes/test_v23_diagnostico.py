import asyncio
from contextlib import closing
import json
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
import sys
from unittest.mock import Mock, patch
sys.path.insert(0, str(ROOT / "app"))

import config
from core import diagnostics


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def test_turn_context_correlates_events():
    seen = []

    async def inner():
        diagnostics.cognitive("v23.test_event", value="x")
        seen.append(diagnostics.current_turn_id())
        return diagnostics.current_turn_id()

    class Probe:
        @diagnostics.with_turn_context
        async def run(self):
            return await inner()

    tid = asyncio.run(Probe().run())
    ok(tid.startswith("turn-"), "turn_id não foi criado")
    ok(seen == [tid], "turn_id não permaneceu no contexto")


def test_content_preview_exists_without_trace():
    old = diagnostics._TRACE_RUNTIME
    try:
        diagnostics._TRACE_RUNTIME = False
        m = diagnostics.content_meta("resposta operacional para depuração")
        ok(m["len"] == 35, "len incorreto")
        ok(m["preview"].startswith("resposta operacional"), "preview ausente")
        ok("sample" not in m, "sample indevido sem trace")
    finally:
        diagnostics._TRACE_RUNTIME = old


def test_session_rows_are_exportable():
    with tempfile.TemporaryDirectory() as td:
        old_runtime = config.RUNTIME_DIR
        try:
            config.RUNTIME_DIR = td
            db = Path(td) / "history.sqlite3"
            c = sqlite3.connect(db)
            c.executescript("""
            CREATE TABLE messages (
              id TEXT PRIMARY KEY, ts TEXT NOT NULL, direction TEXT NOT NULL,
              role TEXT NOT NULL, channel TEXT, channel_target TEXT, person_id TEXT,
              person_name TEXT, content TEXT NOT NULL, metadata TEXT, turn_id TEXT,
              session_id TEXT
            );
            CREATE TABLE events (
              id TEXT PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL,
              severity TEXT NOT NULL, component TEXT, message TEXT, data TEXT,
              turn_id TEXT, session_id TEXT
            );
            """)
            sid = "sess-v23"
            c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      ("m1", "2026-09-20T12:00:00", "in", "user", "tui", "local", "", "Gustavo",
                       "teste de diagnóstico", "{}", "turn-1", sid))
            c.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                      ("e1", "2026-09-20T12:00:01", "cognition.context_built", "INFO", "cognition", "",
                       json.dumps({"task": {"stage": 1}}), "turn-1", sid))
            c.commit(); c.close()
            msgs, events = diagnostics._history_session_rows(sid)
            ok(len(msgs) == 1 and msgs[0]["turn_id"] == "turn-1", "mensagem não correlacionada")
            ok(len(events) == 1 and events[0]["turn_id"] == "turn-1", "evento não correlacionado")
        finally:
            config.RUNTIME_DIR = old_runtime


def test_numeric_token_counts_are_not_credentials():
    data={'estimated_tokens':0,'required_tokens':4117,'context_tokens':4096,
          'output_tokens':768,'prompt_tokens':2912,'api_token':'SECRET',
          'tokens':'SECRET','nested':{'required_tokens':'SECRET'}}
    out=diagnostics._redact(data)
    ok(out['estimated_tokens']==0 and out['required_tokens']==4117,'contagens redigidas como segredo')
    ok(out['context_tokens']==4096 and out['output_tokens']==768 and out['prompt_tokens']==2912,'métricas perdidas')
    ok(out['api_token']=='[REDACTED]' and out['tokens']=='[REDACTED]','credencial exposta')
    ok(out['nested']['required_tokens']=='[REDACTED]','string sensível disfarçada de contagem exposta')
    ok(diagnostics._redact(0,'api_token')=='[REDACTED]','credencial numérica exposta')
    ok(diagnostics._redact(True,'required_tokens')=='[REDACTED]','booleano disfarçado de contagem exposto')


def test_diagnostic_jsonl_and_history_mirror_share_one_utc_timestamp():
    from core import history
    with tempfile.TemporaryDirectory() as td, patch.object(config,'RUNTIME_DIR',td), \
         patch.object(history,'DB',Path(td)/'history.sqlite3'), patch.object(diagnostics,'_logger',return_value=Mock()), \
         patch.object(config,'LOCAL_TIMEZONE','America/Sao_Paulo',create=True), \
         patch.object(history,'utc_timestamp',return_value='2026-10-10T02:59:59.001+00:00'):
        record=diagnostics.emit('utc.probe',source_id='input-1')
        with closing(sqlite3.connect(history.DB)) as db:
            ts,data=db.execute("SELECT ts,data FROM events WHERE kind='utc.probe'").fetchone()
        ok(ts==record['ts'],'espelho perdeu o instante original')
        ok(json.loads(data)['_diagnostic_id']==record['diagnostic_id'],'correlação perdida')
        path=next((Path(td)/'diagnostics').glob('*.jsonl'))
        ok(json.loads(path.read_text().splitlines()[-1])['ts']==record['ts'],'JSONL divergiu')


if __name__ == "__main__":
    test_turn_context_correlates_events()
    test_content_preview_exists_without_trace()
    test_session_rows_are_exportable()
    test_numeric_token_counts_are_not_credentials()
    test_diagnostic_jsonl_and_history_mirror_share_one_utc_timestamp()
    print("V23 diagnóstico: 5/5 testes passaram.")
