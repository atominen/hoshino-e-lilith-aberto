"""Arquivo integral de conversa e trilha operacional da Hoshino.

A memória semântica continua sendo seletiva; este módulo é diferente: ele é o
registro bruto e pesquisável do que aconteceu. Cada mensagem recebida/enviada
é persistida, junto com canal, pessoa, anexos e correlação. Eventos técnicos
podem ser associados à conversa pelo turn_id/session_id.
"""
from __future__ import annotations
from contextlib import closing
from functools import lru_cache
import json, math, sqlite3, threading, uuid
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import config

DB = Path(config.RUNTIME_DIR) / "history.sqlite3"
DB.parent.mkdir(parents=True, exist_ok=True)
_INIT_LOCK = threading.Lock()
_INITIALIZED_DB = None


def local_timezone():
    name = getattr(config, "LOCAL_TIMEZONE", "America/Sao_Paulo")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError(f"Fuso horário inválido: {name}") from exc


def local_now():
    return datetime.now(local_timezone())


def local_datetime(value=None):
    """Compatibilidade de cálculo: legado sem offset assume o fuso configurado.

    Isso não confirma o fuso histórico (timestamp_details continua marcando-o
    como desconhecido), nem reescreve registros. Nunca usa o fuso do host.
    """
    parsed = local_now() if value is None else (value if isinstance(value, datetime)
                                               else datetime.fromisoformat(str(value)))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_timezone())
    return parsed.astimezone(local_timezone())


def utc_timestamp(value=None):
    parsed = datetime.now(timezone.utc) if value is None else local_datetime(value).astimezone(timezone.utc)
    return parsed.isoformat(timespec="milliseconds")


@lru_cache(maxsize=64)
def _clock_warning(operation, reason):
    # Uma indicação por operação/motivo/processo; não encher a timeline a cada
    # tick nem registrar conteúdo de um timestamp inválido possivelmente secreto.
    from core import diagnostics
    diagnostics.emit('clock.unreliable', level='WARN', operation=operation,
                     entity=config.ENTIDADE_ID, reason=reason, elapsed_confirmed=False)


def elapsed_seconds(start, end=None, *, operation=''):
    """Tempo persistente entre instantes; None significa duração não confiável.

    Para intervalos dentro da mesma execução, o consumidor deve preferir relógio
    monotônico. Não inventa passagem do tempo se o relógio recuou ou é inválido.
    """
    try:
        if start is None:
            raise ValueError('Instante inicial desconhecido.')
        a = local_datetime(start).astimezone(timezone.utc)
        b = local_datetime(end).astimezone(timezone.utc)
        seconds = (b - a).total_seconds()
    except (ValueError, TypeError, OverflowError):
        if operation:
            _clock_warning(operation, 'invalid_timestamp')
        return None
    if seconds < 0:
        if operation:
            _clock_warning(operation, 'clock_regression')
        return None
    return seconds


def runtime_elapsed(start, end=None, *, start_monotonic=None, end_monotonic=None, operation=''):
    """Cooldown na mesma execução: monotônico vence alterações do relógio civil.

    Valores monotônicos não são persistidos nem comparados entre processos.
    O fallback civil mantém compatibilidade com consumidores/fixtures antigos.
    """
    if start_monotonic is None and end_monotonic is None:
        return elapsed_seconds(start, end, operation=operation)
    if start_monotonic is None or end_monotonic is None:
        # Uma chamada antiga pode não fornecer o instante monotônico inicial.
        # Um início disponível sem fim não confirma duração alguma.
        if start_monotonic is None:
            return elapsed_seconds(start, end, operation=operation)
        if operation:
            _clock_warning(operation, 'incomplete_monotonic_pair')
        return None
    try:
        a, b = float(start_monotonic), float(end_monotonic)
        if not math.isfinite(a) or not math.isfinite(b) or min(a, b) < 0:
            raise ValueError('Relógio monotônico inválido.')
    except (TypeError, ValueError, OverflowError):
        if operation:
            _clock_warning(operation, 'invalid_monotonic')
        return None
    if b < a:
        if operation:
            _clock_warning(operation, 'monotonic_regression')
        return None
    return b - a


def timestamp_epoch(value):
    """Instante para comparação; legado assume fuso local apenas no cálculo.

    Inválido é None/NULL, nunca 'muito antigo'. Não altera dados ou diagnostica
    dentro de consultas SQLite (o diagnóstico poderia abrir outra transação).
    """
    if value is None:
        return None
    try:
        return local_datetime(value).timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def register_sql_clock(conn):
    """Comparações compatíveis nos bancos existentes, sem migração/esquema novo."""
    conn.create_function('project_epoch', 1, timestamp_epoch)


def timestamp_details(value):
    """Interpreta sem reescrever legado nem inventar seu fuso original."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return dict(timezone_known=False, utc=None, local=None, local_date=None, kind="invalid")
    if parsed.tzinfo is None:
        return dict(timezone_known=False, utc=None, local=parsed.isoformat(),
                    local_date=parsed.date().isoformat(), kind="legacy_local")
    local = parsed.astimezone(local_timezone())
    return dict(timezone_known=True, utc=parsed.astimezone(timezone.utc).isoformat(),
                local=local.isoformat(), local_date=local.date().isoformat(), kind="aware")


def timestamp_order(value):
    """Ordem visual; legado sem offset assume o fuso configurado SOMENTE aqui.

    Essa aproximação não é uma prova de ordem causal ou UTC histórico.
    """
    instant = timestamp_epoch(value)
    return instant if instant is not None else float('-inf')


def author_label(direction, role, person_name="", *, entity=None):
    # Em saída, person_name é DESTINATÁRIO no contrato antigo de main.py.
    if direction == "out" and role == "assistant":
        return str(entity).capitalize() if entity else config.ENTIDADE_NOME
    return str(person_name).strip() if person_name else "Autor não registrado"


def format_message(row, *, entity=None):
    ts, direction, role, channel, person, content, turn = row
    return f"[{ts}] [{channel}] {author_label(direction, role, person, entity=entity)}: {content}"


def _conn():
    c = sqlite3.connect(str(DB), timeout=15)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=10000")
    return c


def init():
    global _INITIALIZED_DB
    chave = str(DB)
    if _INITIALIZED_DB == chave and DB.exists():
        return
    with _INIT_LOCK:
        if _INITIALIZED_DB == chave and DB.exists():
            return
        c = _conn()
        c.executescript("""
    CREATE TABLE IF NOT EXISTS messages (
      id TEXT PRIMARY KEY, ts TEXT NOT NULL, direction TEXT NOT NULL,
      role TEXT NOT NULL, channel TEXT, channel_target TEXT, person_id TEXT,
      person_name TEXT, content TEXT NOT NULL, metadata TEXT, turn_id TEXT,
      session_id TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
    CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel, channel_target);
    CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(id UNINDEXED, content, person_name, channel);
    CREATE TABLE IF NOT EXISTS events (
      id TEXT PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL,
      severity TEXT NOT NULL, component TEXT, message TEXT, data TEXT,
      turn_id TEXT, session_id TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
    CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
    CREATE INDEX IF NOT EXISTS idx_events_turn ON events(turn_id);
    """)
        c.commit(); c.close()
        _INITIALIZED_DB = chave


def message(direction, role, content, channel="tui", channel_target="", person=None,
            metadata=None, turn_id="", session_id=""):
    init()
    mid = f"msg-{uuid.uuid4().hex}"
    p = person or {}
    ts = utc_timestamp()
    meta = dict(metadata or {})
    meta["observer_entity"] = config.ENTIDADE_ID
    if direction == "out" and role == "assistant":
        meta.update(author_id=config.ENTIDADE_ID, author_name=config.ENTIDADE_NOME,
                    recipient_id=p.get("id"), recipient_name=p.get("nome"))
    else:
        meta["author_id"] = p.get("id")
        meta["author_name"] = p.get("nome")
    data = json.dumps(meta, ensure_ascii=False, default=str)
    c = _conn()
    c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (mid, ts, direction, role, channel, channel_target,
               str(p.get("id", "")), str(p.get("nome", "")), str(content or ""),
               data, turn_id, session_id))
    try:
        c.execute("INSERT INTO messages_fts VALUES (?,?,?,?)",
                  (mid, str(content or ""), str(p.get("nome", "")), channel))
    except sqlite3.OperationalError:
        pass
    c.commit(); c.close()
    return mid


def event(kind, message_text="", severity="INFO", component="", data=None,
          turn_id="", session_id="", timestamp=None):
    init()
    ts = utc_timestamp() if timestamp is None else str(timestamp)
    if timestamp is not None and not timestamp_details(ts)["timezone_known"]:
        raise ValueError("Eventos novos exigem timestamp com fuso explícito.")
    if timestamp is not None:
        ts = datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat(timespec="milliseconds")
    eid = f"evt-{uuid.uuid4().hex}"
    c = _conn()
    c.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
              (eid, ts, kind,
               severity, component, str(message_text or ""),
               json.dumps(data or {}, ensure_ascii=False, default=str), turn_id, session_id))
    c.commit(); c.close()
    return eid


def clear_messages(channel: str | None = None, channel_target: str | None = None) -> int:
    """Apaga mensagens persistidas e o índice FTS; eventos técnicos ficam intactos."""
    init(); c = _conn()
    try:
        if channel is None:
            ids = [r[0] for r in c.execute("SELECT id FROM messages").fetchall()]
            if ids:
                c.executemany("DELETE FROM messages_fts WHERE id=?", [(i,) for i in ids])
                c.execute("DELETE FROM messages")
        elif channel_target is None:
            ids = [r[0] for r in c.execute("SELECT id FROM messages WHERE channel=?", (channel,)).fetchall()]
            if ids:
                c.executemany("DELETE FROM messages_fts WHERE id=?", [(i,) for i in ids])
                c.execute("DELETE FROM messages WHERE channel=?", (channel,))
        else:
            ids = [r[0] for r in c.execute("SELECT id FROM messages WHERE channel=? AND channel_target=?", (channel, channel_target)).fetchall()]
            if ids:
                c.executemany("DELETE FROM messages_fts WHERE id=?", [(i,) for i in ids])
                c.execute("DELETE FROM messages WHERE channel=? AND channel_target=?", (channel, channel_target))
        c.commit()
        return len(ids)
    finally:
        c.close()


def clear_all() -> dict:
    """Apaga todo o histórico persistente de conversa e eventos técnicos."""
    init(); c = _conn()
    try:
        n_messages = int(c.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
        n_events = int(c.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        c.execute("DELETE FROM messages_fts")
        c.execute("DELETE FROM messages")
        c.execute("DELETE FROM events")
        c.commit()
        return {"mensagens": n_messages, "eventos": n_events}
    finally:
        c.close()


def search(query, limit=20):
    init(); c = _conn()
    q = (query or "").strip()
    if not q:
        rows = c.execute("SELECT ts,direction,role,channel,person_name,content,turn_id FROM messages ORDER BY rowid DESC LIMIT ?", (int(limit),)).fetchall()
    else:
        try:
            rows = c.execute("SELECT m.ts,m.direction,m.role,m.channel,m.person_name,m.content,m.turn_id FROM messages_fts f JOIN messages m ON m.id=f.id WHERE messages_fts MATCH ? ORDER BY m.rowid DESC LIMIT ?", (q, int(limit))).fetchall()
        except sqlite3.OperationalError:
            like=f"%{q}%"
            rows=c.execute("SELECT ts,direction,role,channel,person_name,content,turn_id FROM messages WHERE content LIKE ? ORDER BY rowid DESC LIMIT ?", (like,int(limit))).fetchall()
    c.close(); return rows


def conversation(limit=50, channel=""):
    init(); c=_conn()
    if channel:
        rows=c.execute("SELECT ts,direction,role,channel,person_name,content,turn_id FROM messages WHERE channel=? ORDER BY rowid DESC LIMIT ?",(channel,int(limit))).fetchall()
    else:
        rows=c.execute("SELECT ts,direction,role,channel,person_name,content,turn_id FROM messages ORDER BY rowid DESC LIMIT ?",(int(limit),)).fetchall()
    c.close(); return list(reversed(rows))


def stats():
    init(); c=_conn()
    a=c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    e=c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    c.create_function("history_order", 1, timestamp_order)
    first_row=c.execute("SELECT ts FROM messages ORDER BY history_order(ts),rowid LIMIT 1").fetchone()
    last_row=c.execute("SELECT ts FROM messages ORDER BY history_order(ts) DESC,rowid DESC LIMIT 1").fetchone()
    first=first_row[0] if first_row else None
    last=last_row[0] if last_row else None
    c.close(); return {"database":str(DB),"mensagens":a,"eventos":e,"primeira":first,"ultima":last}


def export_txt(path=None):
    from pathlib import Path
    p=Path(path) if path else Path(config.ENTREGA_SAIDA)/f"historico_{config.ENTIDADE_ID}.txt"
    p.parent.mkdir(parents=True,exist_ok=True)
    rows=conversation(10**9)
    with p.open("w",encoding="utf-8") as f:
        for ts,direction,role,channel,person,content,turn in rows:
            who = author_label(direction, role, person)
            f.write(f"[{ts}] [{channel}] {who}:\n{content}\n\n")
    return str(p)


def _json_object(value):
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


# 06/11 (pedido humano): checagens internas repetidas escondidas por padrão na aba Atividade. Eram ~30% do
# histórico da Lilith (665 decisões "nada" a cada 8 s e 693 avisos de que nenhum app liberava VRAM).
ROUTINE_SQL = ("NOT ((kind='cognition.autonomy_decision' AND COALESCE(json_extract(data,'$.tipo'),'')='nada') "
               "OR kind='gpu.app_close_skipped')")


def evento_rotineiro(kind, data) -> bool:
    data = data if isinstance(data, dict) else {}
    return kind == 'gpu.app_close_skipped' or (kind == 'cognition.autonomy_decision' and data.get('tipo') == 'nada')


def daily_records(day, limit=100, offset=0, *, channel="", channel_target="",
                  person_id="", query="", include_events=True, include_messages=True,
                  severity="", newest_first=False, search_linked_text=None, db_path=None, entity=None,
                  hide_routine=False):
    """Consulta paginada do SQLite existente. Não cria sessão ou memória nova.

    Registros aware são agrupados no dia do fuso configurado; legado sem fuso
    conserva a data literal. A consulta de compatibilidade pode percorrer o
    histórico para interpretar offsets antigos; somente a página é carregada.
    A Central pode passar dia None para consultar todos os dias.
    db_path/entity são adaptadores internos da Central, não argumentos de tools.
    """
    try:
        if day is not None and (not isinstance(day, str) or date.fromisoformat(day).isoformat() != day):
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise ValueError("Data deve ser YYYY-MM-DD e existir no calendário.") from exc
    if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
        raise ValueError("Limite deve ser 1–500 e offset não negativo.")
    zone = str(local_timezone())
    selected = entity or config.ENTIDADE_ID
    path = Path(db_path) if db_path is not None else DB
    result = dict(entity=selected, local_date=day, timezone=zone, items=[], has_more=False,
                  next_offset=None, read_only=True, global_causal_order=False,
                  legacy_timezone_unknown=False, missing=not path.is_file())
    if result["missing"]:
        return result
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True, timeout=15)) as db:
        db.row_factory = sqlite3.Row
        db.create_function("history_day", 1, lambda ts: timestamp_details(ts)["local_date"])
        db.create_function("history_order", 1, timestamp_order)
        def contains(text, term):
            source = str(text or "")
            folded = str(term).casefold()
            return folded in source.casefold() or (
                search_linked_text is not None and search_linked_text(source, folded)
            )
        db.create_function("history_contains", 2, contains)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        selects, params = [], []
        for table, record_kind in (("messages", "message"), ("events", "event")):
            if table not in tables:
                continue
            if record_kind == "message" and not include_messages:
                continue
            if record_kind == "event" and not include_events:
                continue
            if record_kind == "message":
                fields = "direction,role,channel,channel_target,person_id,person_name,content,metadata AS payload,NULL AS kind,NULL AS severity,NULL AS component"
                filters = {"channel": channel, "channel_target": channel_target, "person_id": person_id}
                searchable = "content"
            else:
                # Não misturar eventos sem canal/autor registrado com conversa filtrada.
                if channel or channel_target or person_id:
                    continue
                fields = "NULL AS direction,NULL AS role,NULL AS channel,NULL AS channel_target,NULL AS person_id,NULL AS person_name,message AS content,data AS payload,kind,severity,component"
                filters = {"severity": severity}
                searchable = "COALESCE(message,'')||COALESCE(data,'')||kind"
            conditions = []
            if day is not None:
                conditions.append("history_day(ts)=?")
                params.append(day)
            for field, value in filters.items():
                if value:
                    conditions.append(field+"=?")
                    params.append(value)
            if query:
                conditions.append(f"history_contains({searchable},?)")
                params.append(str(query))
            if record_kind == "event" and hide_routine:
                conditions.append(ROUTINE_SQL)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            selects.append(f"SELECT '{record_kind}' AS record_kind,rowid AS sequence,id,ts,turn_id,session_id,{fields} FROM {table}{where}")
        if not selects:
            result["unsupported_schema"] = True
            return result
        order = "DESC" if newest_first else "ASC"
        sql = ("SELECT * FROM (" + " UNION ALL ".join(selects) +
               f") ORDER BY history_order(ts) {order},record_kind {order},sequence {order} LIMIT ? OFFSET ?")
        rows = db.execute(sql, (*params, limit+1, offset)).fetchall()
    result["has_more"] = len(rows) > limit
    result["next_offset"] = offset+limit if result["has_more"] else None
    for raw in rows[:limit]:
        row = dict(raw)
        payload = _json_object(row.pop("payload"))
        row["observer_entity"] = selected
        row["entity"] = selected if row["record_kind"] == "message" else payload.get("entity", selected)
        row["timestamp"] = timestamp_details(row["ts"])
        if row["record_kind"] == "message":
            row["metadata"] = payload
            row["author"] = author_label(row["direction"], row["role"], row["person_name"], entity=selected)
        else:
            row["data"] = payload
        result["items"].append(row)
        result["legacy_timezone_unknown"] |= not row["timestamp"]["timezone_known"]
    return result
