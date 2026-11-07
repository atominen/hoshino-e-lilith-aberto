"""Quietude de fragmentos digitados; não cria filas, turnos ou mensagens."""
import json,math
from datetime import datetime
from core.audio_playback import explicit_stop


def conversation_key(message):
    if message.get('sender')!='usuario' or message.get('kind','chat')!='chat':return None
    meta=message.get('metadata') or {}
    if isinstance(meta,str):
        try:meta=json.loads(meta)
        except ValueError:return None
    if not isinstance(meta,dict):return None
    session=meta.get('conversation_session');scope=meta.get('chat_scope','direct')
    if not isinstance(session,dict) or not isinstance(session.get('id'),str) or not session['id'] or scope not in ('direct','global'):return None
    return message.get('recipient'),scope,session['id']


def typed_key(message):
    key=conversation_key(message)
    if key is None:return None
    meta=message.get('metadata') or {}
    if isinstance(meta,str):meta=json.loads(meta)
    if meta.get('audio_job_id') or meta.get('audio_job_ids'):return None
    if explicit_stop(str(message.get('text') or '')):return None
    return key


def stable(message,latest_at,now,seconds):
    if typed_key(message) is None:return True
    try:
        stamp=datetime.fromisoformat(latest_at)
        if stamp.tzinfo is None or not math.isfinite(now):return False
        return now>=stamp.timestamp()+seconds
    except (TypeError,ValueError):return False


def queued_key(item):
    message=item.get('mensagem_local') or {}
    if item.get('canal')!='localhub' or item.get('modalidade')!='texto' or message.get('_text_burst_ready') is not True:return None
    return typed_key(message)
