"""
Acesso ao banco — um lugar só.

Os módulos antigos abriam conexão cada um do seu jeito, com caminho relativo e
sem timeout, e engoliam erro de disco em silêncio. Aqui: caminho absoluto vindo
do config, `row_factory` para ler por nome, timeout para não travar com dois
processos, e exceção de SQLite nunca sobe para o laço principal.
"""
import os
import sqlite3
import sys
import uuid
import contextvars
import functools
from contextlib import contextmanager
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
DB_PATH = config.DB_PATH
_TRANSACTION = contextvars.ContextVar('mind_sqlite_transaction', default=None)


def atomico(falha):
    """Agrupa leituras/escritas existentes; falha explícita sem derrubar o turno.

    Não repete nada automaticamente. O chamador deve testar o retorno antes de
    afirmar aprendizado. ContextVar não compartilha conexão entre threads.
    """
    def decorate(func):
        @functools.wraps(func)
        def run(*args, **kwargs):
            if _TRANSACTION.get() is not None:
                return func(*args, **kwargs)
            try:
                with conexao(escrita=True) as conn:
                    token = _TRANSACTION.set(conn)
                    try:
                        result = func(*args, **kwargs)
                    finally:
                        _TRANSACTION.reset(token)
                return result
            except sqlite3.Error as exc:
                from core import diagnostics
                diagnostics.persistence_failure(f'{func.__module__}.{func.__name__}', caminho(), exc)
                return falha() if callable(falha) else falha
        return run
    return decorate


def caminho() -> str:
    """Lido na hora da chamada: os testes trocam config.DB_PATH em tempo de execução."""
    try:
        return config.DB_PATH
    except (NameError, AttributeError):  # pragma: no cover
        return DB_PATH


@contextmanager
def conexao(escrita: bool = False, *, path=None):
    database=str(path) if path is not None else caminho()
    conn = None
    try:
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        from core import history
        history.register_sql_clock(conn)
        if escrita:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if escrita:
            conn.commit()
    except sqlite3.Error as exc:
        from core import diagnostics
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error as rollback_exc:
                diagnostics.persistence_failure('sqlite.rollback', caminho(), rollback_exc)
        diagnostics.persistence_failure("sqlite.transaction" if escrita else "sqlite.read", database, exc,
                                        retry_safe=not escrita)
        raise
    finally:
        if conn is not None:
            conn.close()


def consultar(sql: str, params=(), *, strict=False) -> list:
    if _TRANSACTION.get() is not None:
        return [dict(r) for r in _TRANSACTION.get().execute(sql, params)]
    try:
        with conexao() as c:
            return [dict(r) for r in c.execute(sql, params)]
    except sqlite3.Error:
        if strict:
            raise
        return []


def um(sql: str, params=(), *, strict=False):
    linhas = consultar(sql, params, strict=strict)
    return linhas[0] if linhas else None


def executar(sql: str, params=(), *, strict=False) -> bool:
    if _TRANSACTION.get() is not None:
        _TRANSACTION.get().execute(sql, params)
        return True
    try:
        with conexao(escrita=True) as c:
            c.execute(sql, params)
        return True
    except sqlite3.Error:
        if strict:
            raise
        return False


def novo_id(prefixo: str, tamanho: int = 8) -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:tamanho]}"


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def quando(texto):
    """ISO -> datetime, tolerante a formato e a None."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(str(texto))
    except (ValueError, TypeError):
        return None
