"""Progresso persistente de trabalhos; Alistair usa os estados reais no standby."""
import json
import os
import sqlite3
import time
from pathlib import Path
import config
from core.sqlite_runtime import open_initialized

DB_PATH = Path(config.SHARED_RUNTIME_DIR) / "jobs_compartilhados.sqlite3"
ACTIVE = {"queued", "running"}
TERMINAL = {"done", "error", "interrupted"}


def _process_stamp(pid):
    """Identifica a execução, não somente o PID que pode ser reutilizado."""
    try:
        # O campo comm pode conter espaços e parênteses; os campos seguintes
        # começam após o último ')'. starttime é o campo 22 de /proc/PID/stat.
        fields = Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] in {"Z", "X"} else fields[19]
    except (OSError, IndexError, ValueError):
        return None


def _conn():
    db = open_initialized(DB_PATH, "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, entity TEXT NOT NULL, "
                          "kind TEXT NOT NULL, status TEXT NOT NULL, pid INTEGER NOT NULL, created_at REAL NOT NULL, "
                          "updated_at REAL NOT NULL, details TEXT NOT NULL);", timeout=10)
    db.row_factory = sqlite3.Row
    if "process_stamp" not in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}:
        try:
            db.execute("ALTER TABLE jobs ADD COLUMN process_stamp TEXT")
        except sqlite3.OperationalError:
            if "process_stamp" not in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}:
                raise
    db.commit()
    return db


def publish(job_id, entity, status, kind="image", **details):
    if status not in {"queued", "running", "done", "error", "interrupted"}:
        raise ValueError("estado de trabalho inválido")
    db = _conn()
    try:
        now = time.time()
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if old and old["entity"] != entity:
            raise ValueError("trabalho pertence a outra entidade")
        if old and old["status"] in TERMINAL and status != old["status"]:
            raise ValueError("trabalho encerrado não pode voltar a executar; crie outro job")
        if old and old["status"] == "running" and status == "queued":
            raise ValueError("trabalho em execução não pode retornar à fila")
        merged = json.loads(old["details"]) if old else {}
        merged.update(details)
        if merged.get('tool') == 'diario':
            # This database is shared. A durable receipt is not a diary copy.
            merged = {k:v for k,v in merged.items() if k in {
                'tool','signature','signature_version','mutates','outcome','auto_retry',
                'verified','requires_verification','resolved'}}
            merged['private'] = True
        db.execute("INSERT INTO jobs(id,entity,kind,status,pid,created_at,updated_at,details,process_stamp) "
                   "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE "
                   "SET status=excluded.status,updated_at=excluded.updated_at,details=excluded.details",
                   (job_id, entity, kind, status, os.getpid(), now, now, json.dumps(merged, ensure_ascii=False),
                    _process_stamp(os.getpid())))
        db.commit()
    finally:
        db.close()


def status(active_only=False, limit=50, *, kind=None):
    db = _conn()
    try:
        for row in db.execute("SELECT id,pid,process_stamp FROM jobs WHERE status IN ('queued','running')").fetchall():
            dead = bool(row["process_stamp"] and row["process_stamp"] != _process_stamp(row["pid"]))
            try:
                os.kill(row["pid"], 0)
            except ProcessLookupError:
                dead = True
            except PermissionError:
                pass
            if dead:
                db.execute("UPDATE jobs SET status='interrupted',updated_at=? "
                           "WHERE id=? AND status IN ('queued','running')", (time.time(), row["id"]))
        db.commit()
        predicates = ["status IN ('queued','running')"] if active_only else []
        params = []
        if kind is not None:
            if not isinstance(kind, str) or not 1 <= len(kind) <= 100:
                raise ValueError('tipo de trabalho inválido')
            predicates.append('kind=?'); params.append(kind)
        where = 'WHERE ' + ' AND '.join(predicates) if predicates else ''
        rows = db.execute(f"SELECT * FROM jobs {where} ORDER BY updated_at DESC LIMIT ?",
                          (*params, min(200, max(1, int(limit))))).fetchall()
        result = []
        for row in rows:
            details = json.loads(row['details'])
            if row['kind'] == 'llm_text' and kind != 'llm_text':
                # Consultas genéricas (painéis, mundo e standby) não escolhem
                # destinatário/sala. O texto só sai pela projeção específica.
                details = {key: details[key] for key in ('revision', 'final') if key in details}
                details['phase'] = 'gerando resposta' if row['status'] in ACTIVE else 'prévia encerrada'
            result.append({**dict(row), 'details': details})
        return result
    finally:
        db.close()


def annotate(job_id, entity, **details):
    """Atualiza observações do job sem correr contra seu desfecho.

    Reprodução UI pode chegar ao mesmo tempo que síntese vira done. Nunca
    restaura running nem adota PID de outro processo ao anexar telemetria.
    """
    db=_conn()
    try:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT entity,details FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not old or old['entity']!=entity:raise ValueError('Trabalho não pertence à entidade.')
        merged=json.loads(old['details']);merged.update(details)
        if merged.get('tool')=='diario':
            merged={k:v for k,v in merged.items() if k in {
                'tool','signature','signature_version','mutates','outcome','auto_retry',
                'verified','requires_verification','resolved','private'}}
        db.execute('UPDATE jobs SET details=?,updated_at=? WHERE id=?',
                   (json.dumps(merged,ensure_ascii=False),time.time(),job_id))
        db.commit()
    finally:db.close()


def resolve_reviewed(job_id, entity, *, reviewer, resolution, evidence):
    """Aplica uma revisão atribuída a um recibo incerto, sem reescrever seu desfecho.

    Só libera a assinatura para nova decisão; não repete nada. Revisão parcial
    (só no checkpoint) deixava a mesma ação bloqueada indefinidamente.
    """
    if not (str(reviewer).strip() and str(resolution).strip() and str(evidence).strip()):
        raise ValueError('Revisão exige revisor, resolução e evidência.')
    db=_conn()
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT entity,details FROM jobs WHERE id=? AND kind='tool'",(job_id,)).fetchone()
        if not row or row['entity']!=entity:raise ValueError('Recibo não encontrado para a entidade.')
        details=json.loads(row['details'])
        if details.get('resolved'):raise ValueError('Recibo já revisado; nada alterado.')
        details.update(resolved=True,resolution=str(resolution),reviewer=str(reviewer),evidence=evidence,
                       reviewed_at=time.time(),auto_retry=False)
        db.execute('UPDATE jobs SET details=?,updated_at=? WHERE id=?',(json.dumps(details,ensure_ascii=False),time.time(),job_id))
        db.commit()
        return details
    finally:db.close()


def get(job_id, entity=None):
    # Primeiro reconcilia execuções interrompidas. A consulta por ID não se
    # limita à janela dos 50 jobs recentes.
    status(limit=1)
    db = _conn()
    try:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (str(job_id),)).fetchone()
        if row is None or (entity is not None and row["entity"] != entity):
            return None
        return {**dict(row), "details": json.loads(row["details"])}
    finally:
        db.close()


def unresolved_action(entity, signature):
    """Recibos existentes: um efeito incerto nunca vira convite para repetição."""
    status(limit=1)  # reconcilia dono morto, sem reexecutar trabalhos
    db = _conn()
    try:
        for row in db.execute("SELECT * FROM jobs WHERE entity=? AND kind='tool' "
                              "AND status IN ('running','interrupted')", (entity,)):
            details = json.loads(row['details'])
            if details.get('signature') == signature and not details.get('resolved'):
                return {**dict(row), 'details': details}
    finally:
        db.close()


def unresolved_maintenance(entity, scope):
    """Limpeza interrompida não desaparece da guarda após os 200 jobs da UI."""
    status(limit=1)  # Reconcilia dono morto; nunca reexecuta efeitos.
    db=_conn()
    try:
        for row in db.execute("SELECT * FROM jobs WHERE entity=? AND kind='memory_maintenance' "
                              "AND status IN ('running','interrupted') ORDER BY updated_at DESC",(entity,)):
            details=json.loads(row['details'])
            if details.get('scope')==scope and not details.get('resolved'):
                return {**dict(row),'details':details}
    finally:db.close()
    return None


def reserve_action(identifier, entity, signature, tool):
    """Reserva atômica no diário existente, inclusive entre processos/threads."""
    status(limit=1)
    db = _conn()
    try:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute("SELECT id,details FROM jobs WHERE entity=? AND kind='tool' AND status IN ('running','interrupted')", (entity,)):
            details = json.loads(row['details'])
            legacy_unknown=(tool=='execute_command' and details.get('tool')==tool
                            and details.get('signature_version',1)<3)
            if (details.get('signature') == signature or legacy_unknown) and not details.get('resolved'):
                return row['id']
        now = time.time()
        details = dict(tool=tool, signature=signature, signature_version=3, mutates=True, outcome='pending', auto_retry=False)
        db.execute("INSERT INTO jobs(id,entity,kind,status,pid,created_at,updated_at,details,process_stamp) VALUES(?,?,'tool','running',?,?,?,?,?)",
                   (identifier, entity, os.getpid(), now, now, json.dumps(details), _process_stamp(os.getpid())))
        db.commit()
        return None
    finally:
        db.close()
