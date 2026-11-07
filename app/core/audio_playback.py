"""Recibos do player; síntese e audição humana são coisas distintas."""
import json
import math
import re
import time
import unicodedata
from core import job_bus, interentity

FRESH_SECONDS = 4


def record(job, event, chunk, player, position=None, sequence=None, observed_at=None):
    details=job['details'];chunks=details.get('chunks',[])
    if event not in {'started','progress','ended','autoplay_denied','failed','cancelled'}:
        raise ValueError('Evento de reprodução inválido.')
    if chunk is not None and (type(chunk) is not int or not 0<=chunk<len(chunks)):
        raise ValueError('Trecho de reprodução inválido.')
    if event in {'started','progress','ended'} and chunk is None:
        raise ValueError('Reprodução exige trecho.')
    if position is not None and (type(position) not in (float,int) or not math.isfinite(position) or position<0):
        raise ValueError('Posição de reprodução inválida.')
    old=details.get('playback',{});completed=list(old.get('completed',[]))
    if sequence is not None:
        if type(sequence) is not int or sequence<1:raise ValueError('Sequência de reprodução inválida.')
        if sequence<=old.get('sequence',0):return False
    if old.get('state') in {'cancelled','failed'} or chunk in completed:return False
    if event=='started':
        if chunk!=len(completed):return False
        if old.get('state')=='speaking':return False
    elif event in {'progress','ended'}:
        active=old.get('state')=='speaking' and old.get('chunk')==chunk and old.get('player')==player
        if not active and not (sequence is not None and chunk==len(completed)):return False
    now=time.time();at=now if observed_at is None else observed_at
    if type(at) not in (int,float) or not math.isfinite(at) or at>now+2 or at<0:
        raise ValueError('Instante de reprodução inválido.')
    if event in {'started','progress'} and now-at>=FRESH_SECONDS:return False
    state=event
    if event in {'started','progress'}:state='speaking'
    elif event=='ended':completed.append(chunk);state='between_chunks'
    duration=chunks[chunk].get('duration_seconds',0) if chunk is not None else 0
    position=min(float(position or 0),duration)
    if event=='progress' and old.get('chunk')==chunk:position=min(duration,max(position,old.get('position_seconds',0)))
    if event=='ended':position=duration
    value=dict(state=state,chunk=chunk,completed=completed,at=at,player=player,position_seconds=position,sequence=sequence or old.get('sequence',0))
    job_bus.annotate(job['id'],job['entity'],playback=value,playback_event=event,
                     playback_at=at,playback_basis=player+'_player_report_not_human_hearing')
    return True


def snapshot(entity, now=None):
    if entity not in interentity.ENTITIES:raise ValueError('Entidade inválida.')
    now=time.time() if now is None else now
    from memory.audience import public_turn
    public_only=public_turn();own=[];speaking=[]
    if not job_bus.DB_PATH.is_file():return dict(speaking=[],own=[],basis='player_report_not_human_hearing')
    for job in job_bus.status(limit=200,kind='audio_tts'):
        details=job['details'];play=details.get('playback',{});state=play.get('state','not_started')
        if not 0<=now-job['updated_at']<300:continue
        fresh=0<=now-play.get('at',0)<FRESH_SECONDS
        if state=='speaking' and not fresh:state='unknown'
        if state=='speaking':speaking.append(job['entity'])
        if job['entity']!=entity:continue
        chunks=details.get('chunks',[]);index=play.get('chunk');completed=play.get('completed',[])
        visible=not public_only or details.get('chat_scope')=='global'
        if state=='between_chunks' and job['status']=='done' and len(completed)==len(chunks):state='finished'
        own.append(dict(id=job['id'],state=state,chunk=index,synthesis_status=job['status'],
                        position_seconds=play.get('position_seconds',0),
                        current_text=chunks[index].get('text','') if visible and type(index) is int and index<len(chunks) else '',
                        completed_text=[chunks[i].get('text','') for i in completed if visible and i<len(chunks)],
                        stop_requested=bool(details.get('playback_cancel_at'))))
        if len(own)>2:own.pop()
    return dict(speaking=sorted(set(speaking)),own=own,basis='player_report_not_human_hearing')


def pending(entity, *, before=None, owner=None):
    if entity not in interentity.ENTITIES:raise ValueError('Entidade inválida.')
    if not job_bus.DB_PATH.is_file():return []
    result=[]
    for job in job_bus.status(limit=200,kind='audio_tts'):
        details=job['details']
        if job['entity']!=entity:continue
        if before is not None and job['created_at']>before:continue
        if owner is not None and details.get('playback_owner')!=owner:continue
        play=details.get('playback',{})
        if play.get('state') in {'cancelled','failed'}:continue
        if job['status'] in {'queued','running'} or len(play.get('completed',[]))<len(details.get('chunks',[])):
            result.append(job)
    return result


def request_stop(entity, *, before=None, owner=None):
    jobs=pending(entity,before=before,owner=owner);requested=[]
    for job in jobs:
        if not job['details'].get('playback_cancel_at'):
            job_bus.annotate(job['id'],entity,playback_cancel_at=time.time())
            requested.append(job['id'])
    return dict(requested=len(requested),status='stop_requested',player_confirmation_pending=bool(jobs))


def context(entity):
    state=snapshot(entity)
    if not state['own'] and not state['speaking']:return ''
    return ('[REPRODUÇÃO DE VOZ — observação do player, não audição humana]\n'+json.dumps(state,ensure_ascii=False)+
            '\nUma mensagem nova não exige cortar a fala. Posso usar estado_voz para consultar e parar_voz '
            'para pedir o encerramento da minha própria fala se o contexto ou a pessoa pedirem. '
            'Posso aguardar a fala em curso; texto gerado ainda não é texto falado. Estado unknown não confirma reprodução.')


def explicit_stop(text):
    if not isinstance(text,str):return False
    value=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')
    value=re.sub(r'[,!.?;:]',' ',value);value=' '.join(value.split())
    return bool(re.fullmatch(r'(?:por favor )?(?:pare|para|parem)(?: de falar| a voz| o audio)?(?: por favor)?|silencio(?: por favor)?',value))
