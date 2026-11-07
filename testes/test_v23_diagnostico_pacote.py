import json, sqlite3, tempfile, zipfile
from pathlib import Path
import sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app")); os.chdir(ROOT)
import config
from core import diagnostics

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    old_runtime, old_out = config.RUNTIME_DIR, config.ENTREGA_SAIDA
    try:
        config.RUNTIME_DIR = str(td / 'runtime')
        config.ENTREGA_SAIDA = str(td / 'out')
        Path(config.RUNTIME_DIR).mkdir(parents=True)
        db = Path(config.RUNTIME_DIR) / 'history.sqlite3'
        c = sqlite3.connect(db)
        c.executescript('''
        CREATE TABLE messages (id TEXT PRIMARY KEY, ts TEXT NOT NULL, direction TEXT NOT NULL, role TEXT NOT NULL, channel TEXT, channel_target TEXT, person_id TEXT, person_name TEXT, content TEXT NOT NULL, metadata TEXT, turn_id TEXT, session_id TEXT);
        CREATE TABLE events (id TEXT PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL, severity TEXT NOT NULL, component TEXT, message TEXT, data TEXT, turn_id TEXT, session_id TEXT);
        ''')
        sid='v23pkg'
        c.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',('m','2026-09-20T10:00:00','in','user','tui','local','','G','abra o firefox','{}','turn-1',sid))
        c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',('e','2026-09-20T10:00:01','cognition.intent_interpreted','INFO','cognition','',json.dumps({'acao':'abrir_app'}),'turn-1',sid))
        c.commit(); c.close()
        diagnostics.SESSION_ID = sid
        out = diagnostics.package_diagnosis()
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
            for n in ('history/session_summary.json','history/session_messages.jsonl','history/session_events.jsonl','diagnostics/session_timeline.jsonl','snapshot.json'):
                assert n in names, n
            data = json.loads(z.read('history/session_summary.json'))
            assert data['messages'] == 1 and data['events'] >= 2
        print('V23 pacote diagnóstico: OK')
    finally:
        config.RUNTIME_DIR, config.ENTREGA_SAIDA = old_runtime, old_out
