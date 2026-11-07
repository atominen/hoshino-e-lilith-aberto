"""Comentários mecânicos nos episódios existentes; não inventa fala do LLM.

O comentário descreve o recibo de uma ação. Argumentos, respostas privadas e
segredos não são copiados. Falhar ao salvar nunca repete o efeito da ferramenta.
"""
import json
import sqlite3
import hashlib
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path


def record(tool,receipt,result,*,database=None):
    import config
    from core import diagnostics
    path=Path(database or config.DB_PATH)
    if not isinstance(result,dict) or not receipt or not path.is_file():return False
    status=result.get('status','unknown')
    if result.get('outcome_uncertain'):status='uncertain'
    elif status=='unknown' and result.get('ok') is False:status='error'
    elif status=='unknown' and result.get('ok') is True:status='success'
    verified=result.get('verified') is True
    descriptions={'success':'a ferramenta retornou um resultado',
        'error':'a tentativa falhou','pending':'o trabalho está pendente',
        'uncertain':'o efeito não foi confirmado; não repetir automaticamente',
        'permission':'a tentativa aguarda autorização','unknown':'o resultado está indefinido'}
    comment=f"Registro automático de ação: {tool}; {descriptions.get(status,descriptions['unknown'])}."
    comment+=' Efeito verificado.' if verified else ' Não há confirmação independente do efeito.'
    context=json.dumps(dict(kind='tool_receipt',entity=config.ENTIDADE_ID,receipt_id=str(receipt),
        status=status,verified=verified,authored_by='application',human_conversation=False),ensure_ascii=False)
    identifier='tool-comment-'+hashlib.sha256(str(receipt).encode()).hexdigest()[:32]
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=3)) as db,db:
            db.execute('''INSERT OR IGNORE INTO episodes
                (id,created_at,what_happened,context,action_taken,result,is_success,source,importance,status)
                VALUES(?,?,?,?,?,?,?,?,?,'active')''',
                (identifier,datetime.now(timezone.utc).isoformat(),comment,context,tool,status,
                 1 if verified and status=='success' else 0 if status=='error' else None,'tool_receipt',0.5))
        diagnostics.emit('memory.action_comment_saved',entity=config.ENTIDADE_ID,tool=tool,receipt_id=str(receipt),status=status,verified=verified)
        return True
    except Exception as exc:
        diagnostics.emit('memory.action_comment_failed',level='ERROR',entity=config.ENTIDADE_ID,
                         error_type=type(exc).__name__,action_retried=False)
        return False


def record_deliberation(identifier, comment, receipts, outcome, *, database=None):
    """Comentário final do LLM, separado de recibos e de conversa humana.

    Não indexa como conhecimento, não publica e não prova sucesso pela prosa.
    Os recibos já existentes são a fonte da distinção entre ação e intenção.
    """
    import config
    from core import diagnostics
    path = Path(database or config.DB_PATH)
    if not path.is_file():
        return False
    refs = [{k:r.get(k) for k in ('tool','receipt_id','status','verified','mutates')}
            for r in receipts]
    context = dict(kind='autonomous_deliberation', authored_by=config.ENTIDADE_ID if comment else 'application',
                   entity=config.ENTIDADE_ID, human_conversation=False, visibility='private',
                   turn_id=identifier, receipts=refs, outcome=outcome, quality_approved=False)
    text = comment.strip()[:1600] if comment else 'Registro mecânico: deliberação interna ' + outcome + '.'
    success = (0 if outcome == 'error' else
               1 if outcome == 'action' and refs and all(r['status']=='success' for r in refs)
               and any(r['verified'] for r in refs) else None)
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=3)) as db, db:
            db.execute('''INSERT OR IGNORE INTO episodes
                (id,created_at,what_happened,context,action_taken,result,is_success,source,importance,status)
                VALUES(?,?,?,?,?,?,?,?,?,'active')''',
                ('initiative-'+identifier, datetime.now(timezone.utc).isoformat(), text,
                 json.dumps(context,ensure_ascii=False), ','.join(r['tool'] for r in refs) or 'deliberar',
                 outcome, success, 'autonomous_deliberation', .4))
        diagnostics.emit('initiative.comment_saved', entity=config.ENTIDADE_ID,
                         turn_id=identifier, outcome=outcome, receipt_count=len(refs), private=True)
        return True
    except Exception as exc:
        diagnostics.emit('initiative.comment_failed', level='ERROR', error_type=type(exc).__name__,
                         turn_id=identifier, action_retried=False)
        return False
