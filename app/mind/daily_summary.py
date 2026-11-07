"""Lotes incrementais do histórico existente; cobertura no SQLite mental atual.

Não é outro histórico ou memória: context_summaries contém sínteses derivadas,
e faixa guarda referências/coverage. Cada fonte continua nos registros originais.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

import config
from core import bd, history, diagnostics

KIND = 'daily_summary_batch'
FRAGMENT_CHARS = 500


def _wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _prefix(day):
    date.fromisoformat(day)
    return f'daily-{config.ENTIDADE_ID}-{day}-'


def _compact_reference(origin):
    # Full metadata is still in the source fragments. Repeating a huge context
    # on every reference would make every fragment permanently exceed budget.
    return {key:(value if len(_wire(value))<=200 else
                 dict(full_source_field=key,chars=len(_wire(value)),
                      sha256=hashlib.sha256(_wire(value).encode()).hexdigest()))
            for key,value in origin.items()}


def batches(day):
    rows = bd.consultar('SELECT * FROM context_summaries WHERE id LIKE ? ORDER BY rowid',
                        (_prefix(day)+'%',), strict=True)
    out = []
    for row in rows:
        meta = json.loads(row['faixa'])  # corrupt coverage is an error, not an empty day
        if meta.get('kind') != KIND or meta.get('entity') != config.ENTIDADE_ID or meta.get('day') != day:
            raise ValueError('Escopo do resumo diário não corresponde à entidade/dia.')
        out.append(dict(row, coverage=meta))
    return out


def _sources(day, now):
    start = history.local_datetime(day+'T00:00:00')
    bounds = (start.timestamp(), (start+timedelta(days=1)).timestamp(), now.timestamp())
    # A ordem local é estável. ROWID não é uma alegação de ordem causal global.
    stores = [(Path(config.RUNTIME_DIR)/'history.sqlite3', 'messages', 'ts'),
              (Path(config.RUNTIME_DIR)/'history.sqlite3', 'events', 'ts'),
              (Path(bd.caminho()), 'episodes', 'created_at'),
              (Path(bd.caminho()), 'emotion_log', 'created_at')]
    for path, table, clock in stores:
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            history.register_sql_clock(conn)
            if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                continue  # historical schema lacking this optional source
            cursor = conn.execute(f'SELECT * FROM {table} WHERE project_epoch({clock})>=? '
                                  f'AND project_epoch({clock})<? AND project_epoch({clock})<=? ORDER BY rowid', bounds)
            for raw in cursor:
                row = dict(raw)
                # No compression of private diaries or diagnostic secrets into summaries.
                if table == 'episodes' and row.get('source') in {'initiative_checkpoint','initiative_observation'}:
                    continue  # Memória de trabalho, não novos episódios para consolidar em duplicata.
                if table == 'events':
                    if row['kind'] not in {'tool.receipt', 'tool.end', 'tool.failed', 'input.received', 'turn.cancelled'}:
                        continue
                    from core.central_control import redact
                    row = redact(row)
                evidence = dict(store='history' if table in {'messages','events'} else 'mental',
                                table=table, id=row['id'], timestamp=row[clock], observer=config.ENTIDADE_ID)
                if table == 'messages':
                    meta = json.loads(row.get('metadata') or '{}')
                    evidence.update(author_id=meta.get('author_id'), author_name=meta.get('author_name'),
                                    channel=row.get('channel'), channel_target=row.get('channel_target'),
                                    turn_id=row.get('turn_id'), message_id=row['id'], source_id=meta.get('source_id'),
                                    type='declared_message', confidence=None)
                elif table == 'episodes':
                    evidence.update(source=row.get('source'), context=row.get('context'), type='episodio')
                yield row, evidence


def prepare(day=None, *, agora=None, max_chars=9000):
    """Never acknowledge unseen characters; huge records continue in later lots."""
    now = history.local_datetime(agora)
    day = day or now.date().isoformat()
    budget = int(max_chars)
    if not 2000 <= budget <= 30000:
        raise ValueError('Orçamento diário deve ficar entre 2000 e 30000 caracteres.')
    committed = batches(day)
    covered = {s['part_key'] for b in committed for s in b['coverage']['sources']}
    ranges = {}
    for batch in committed:
        for source in batch['coverage']['sources']:
            identity=(source['store'],source['table'],source['id'],source['record_sha256'])
            ranges.setdefault(identity,[]).append((source['start'],source['end']))
    selected, parts, remaining = [], [], 0
    for row, origin in _sources(day, now):
        wire = _wire(row)
        digest = hashlib.sha256(wire.encode()).hexdigest()
        # Fixed fragments give stable idempotence under changing budgets.
        for offset in range(0, len(wire), FRAGMENT_CHARS):
            key = f"{origin['store']}:{origin['table']}:{row['id']}:{digest}:{offset}"
            end=min(offset+FRAGMENT_CHARS,len(wire))
            identity=(origin['store'],origin['table'],row['id'],digest)
            if key in covered or any(a<=offset and b>=end for a,b in ranges.get(identity,[])):
                continue
            ref = dict(_compact_reference(origin), record_sha256=digest, part_key=key, start=offset,
                       end=min(offset+FRAGMENT_CHARS,len(wire)), total_chars=len(wire))
            text = _wire(dict(reference=ref, fragment=wire[offset:offset+FRAGMENT_CHARS]))
            if len(text)+1 <= budget:
                selected.append(ref); parts.append(text); budget -= len(text)+1
            else:
                remaining += 1
    manifest = dict(kind=KIND, entity=config.ENTIDADE_ID, day=day, fragment_chars=FRAGMENT_CHARS,
                    timezone=str(history.local_timezone()), as_of=history.utc_timestamp(now),
                    sources=selected, pending_parts=remaining, global_causal_order=False)
    material = '\n'.join(parts)
    manifest['material_sha256'] = hashlib.sha256(material.encode()).hexdigest()
    identifier = _prefix(day)+hashlib.sha256(_wire(selected).encode()).hexdigest()[:24]
    prompt = ("Reviso somente estes fragmentos do meu dia; não invento o resto. "
              "Preservo quem falou, o sujeito, condições, contradições, resultados e pendências. "
              "Declaração não é verificação externa; resumo é interpretação revisável. "
              "Referencio IDs de origem. Não escrevo raciocínio interno. "
              "Faço uma síntese curta (até 1800 caracteres) para consultar depois.\n"+material) if parts else ''
    return dict(id=identifier, prompt=prompt, coverage=manifest)


def commit(prepared, summary):
    text = str(summary or '').strip()
    if not text or len(text)>2400:
        raise ValueError('Síntese vazia/longa: cobertura não avançou.')
    meta = prepared['coverage']
    if meta.get('entity') != config.ENTIDADE_ID or not meta.get('sources'):
        raise ValueError('Lote vazio ou estrangeiro.')
    # Revalidate source fragments; a modified/deleted source cannot be silently acknowledged.
    # Full source inventory, not just this prepare's budgeted prefix.
    available = set()
    for row, origin in _sources(meta['day'], history.local_datetime(meta['as_of'])):
        wire = _wire(row); digest = hashlib.sha256(wire.encode()).hexdigest()
        available.update(f"{origin['store']}:{origin['table']}:{row['id']}:{digest}:{o}"
                         for o in range(0,len(wire),meta.get('fragment_chars',1000)))
    if any(s['part_key'] not in available for s in meta['sources']):
        raise ValueError('Fonte mudou durante a síntese; histórico intacto e lote não confirmado.')
    with bd.conexao(escrita=True) as conn:
        old = conn.execute('SELECT faixa,resumo FROM context_summaries WHERE id=?', (prepared['id'],)).fetchone()
        if old:
            return dict(id=prepared['id'], committed=True, reused=True)
        # Concurrent, different batches may overlap: do not reinterpret the same lot twice.
        seen = set()
        for row in conn.execute('SELECT faixa FROM context_summaries WHERE id LIKE ?', (_prefix(meta['day'])+'%',)):
            seen.update(s['part_key'] for s in json.loads(row['faixa'])['sources'])
        if seen.intersection(s['part_key'] for s in meta['sources']):
            raise ValueError('Outro lote já consumiu parte destas fontes; preparar novamente.')
        conn.execute('INSERT INTO context_summaries VALUES(?,?,?,?,?,?,?)',
                     (prepared['id'], history.utc_timestamp(), _wire(meta), len(meta['sources']),
                      len(prepared['prompt'])//3, text, 0))
    diagnostics.emit('daily_summary.committed', entity=config.ENTIDADE_ID, summary_id=prepared['id'],
                     sources=meta['sources'], pending_parts=meta['pending_parts'], verified=True)
    return dict(id=prepared['id'], committed=True, reused=False)


def recall(day, limit=5):
    rows = batches(day)
    return {'day':day, 'entity':config.ENTIDADE_ID, 'type':'interpretacao',
            'items':[dict(id=r['id'],summary=r['resumo'],evidence=r['coverage']) for r in rows[-limit:]],
            'omitted_batches':max(0,len(rows)-limit), 'source':'context_summaries'}


def next_batch(*, agora=None, max_chars=9000):
    """Oldest unfinished day first; no arbitrary maximum date/lookback window."""
    now = history.local_datetime(agora)
    days = set()
    for path, table, clock in ((Path(config.RUNTIME_DIR)/'history.sqlite3','messages','ts'),
                               (Path(config.RUNTIME_DIR)/'history.sqlite3','events','ts'),
                               (Path(bd.caminho()),'episodes','created_at'),
                               (Path(bd.caminho()),'emotion_log','created_at')):
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
            if not conn.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
                continue
            conn.create_function('local_day',1,lambda ts:history.timestamp_details(ts).get('local_date'))
            days.update(r[0] for r in conn.execute(f'SELECT DISTINCT local_day({clock}) FROM {table}')
                        if r[0] and r[0]<=now.date().isoformat())
    for day in sorted(days):
        prepared = prepare(day, agora=now, max_chars=max_chars)
        if prepared['prompt']:
            return prepared
    return None
