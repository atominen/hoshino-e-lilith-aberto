"""Inicialização concorrente dos bancos compartilhados, sem efeitos no import."""
import sqlite3
import time
from pathlib import Path


def open_initialized(path, schema, timeout=5):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        db = sqlite3.connect(path, timeout=.25)
        try:
            # A mudança para WAL pode devolver BUSY imediatamente durante o
            # primeiro acesso simultâneo, mesmo com connect(timeout=5).
            db.execute("PRAGMA journal_mode=WAL")
            if callable(schema):
                schema(db)
            else:
                db.executescript(schema)
            db.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
            return db
        except sqlite3.OperationalError as exc:
            db.close()
            code = getattr(exc, "sqlite_errorcode", 0) & 255
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                raise
            time.sleep(.025)
        except BaseException:
            db.close()
            raise
