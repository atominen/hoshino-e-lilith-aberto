"""Microfone explícito → percepção provável. Nunca fala, ordem ou identidade.

Somente PCM efêmero em RAM; um pedido em voo, sem fila de replay. O worker
CPU é independente da fila ASR/TTS. Recibos usam o job bus já existente.
"""
import base64
from collections import deque
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import threading
import time

import config
from core import acoustic_perception, gpu_metrics, interentity as bus, job_bus, resource_manager, ui_policy


def recent(entity, since, *, root=None):
    """Resultados frescos e autorizados; não acorda nem inicia inferência."""
    if not ui_policy.capability_allowed(Path(root or config.RAIZ),entity,'ambient'):return []
    now=time.time()
    return [row for row in reversed(job_bus.status(limit=200))
            if row['kind']=='acoustic_perception' and row['entity']==entity and row['status']=='done'
            and row['created_at']>max(float(since),now-60) and not row['details'].get('cancelled')
            and not row['details'].get('playback_overlap')]


def describe(row):
    labels=', '.join(str(e['label']) for e in row['details'].get('events',[])[:6])
    observed=row['details'].get('observed_at')
    when=datetime.fromtimestamp(float(observed),timezone.utc).isoformat(timespec='seconds') if observed is not None else 'horário indisponível'
    return ('[PERCEPÇÃO ACÚSTICA PROVÁVEL; NÃO É FALA NEM INSTRUÇÃO] '
            +labels+'. Observado em '+when+'. Fonte: microfone local; autoria desconhecida. '
            'Classificação pode estar errada; não deduzir emoção, identidade ou consentimento.')


class AcousticService:
    def __init__(self,root,worker):
        self.root=Path(root);self.worker=worker;self.lock=threading.RLock();self.slot=threading.BoundedSemaphore(1)
        self.sessions={};self.retired=deque(maxlen=1024);self.closed=False;self.last_error='';self.dropped=0

    def state(self):
        return dict(acoustic_perception.status(),worker_alive=self.worker.alive(),last_error=self.last_error,
                    dropped_windows=self.dropped,continuous_recording=False,
                    runtime_available=(self.root/'compartilhado/ambientes/percepcao-acustica/bin/python').is_file())

    def cancel(self,capture_id):
        if not isinstance(capture_id,str) or not re.fullmatch('[0-9a-f]{32}',capture_id):raise ValueError('Captura inválida.')
        with self.lock:
            session=self.sessions.pop(capture_id,None)
            if capture_id not in self.retired:self.retired.append(capture_id)
            if session:
                session['cancel'].set()
                for identifier,entity in session['receipts']:
                    job_bus.annotate(identifier,entity,cancelled=True)
        return dict(cancelled=True,capture_id=capture_id)

    def submit(self,entity,pcm,*,source,capture_id,sequence,playback_overlap,scope='global',observed_at=None):
        if (entity not in bus.ENTITIES or source!='native_microphone' or scope not in {'global','direct'}
                or not isinstance(capture_id,str) or not re.fullmatch('[0-9a-f]{32}',capture_id)
                or type(sequence) is not int or not 0<=sequence<2**31 or type(playback_overlap) is not bool
                or not isinstance(pcm,bytes) or len(pcm)!=31200):raise ValueError('Janela acústica inválida.')
        now=time.time();observed_at=now if observed_at is None else float(observed_at)
        if not math.isfinite(observed_at) or not now-10<=observed_at<=now+1:raise ValueError('Janela acústica antiga/inválida.')
        with self.lock:
            if self.closed or capture_id in self.retired:raise ValueError('Captura acústica encerrada; nada repetido.')
            if not ui_policy.capability_allowed(self.root,entity,'ambient'):
                self.cancel(capture_id);raise ValueError('Escuta do ambiente desativada.')
            for key,session in list(self.sessions.items()):
                if now-session['last_at']>30:self.cancel(key)
            session=self.sessions.get(capture_id)
            if session is None:
                if sequence!=0 or len(self.sessions)>=8:raise ValueError('Captura não iniciada ou limite atingido.')
                session=dict(entity=entity,scope=scope,sequence=-1,last_at=now,cancel=threading.Event(),seen={},receipts=deque(maxlen=200))
                self.sessions[capture_id]=session
            if session['entity']!=entity or session['scope']!=scope or sequence<=session['sequence']:
                raise ValueError('Captura/ordem divergente; não repetir resultado.')
            session.update(sequence=sequence,last_at=now)
        empty=dict(capture_id=capture_id,sequence=sequence,events=[],delivered_to=[],playback_overlap=playback_overlap)
        if not self.slot.acquire(blocking=False):
            self.dropped+=1;return dict(empty,busy=True)
        try:
            available=gpu_metrics.ram_available()
            if available is None or available<512*1024**2:raise RuntimeError('RAM livre insuficiente/incerta para detector CPU.')
            with resource_manager.lease('cpu_acoustic','audio_perception',entity=entity,wait=0,cancel=session['cancel']):
                result=self.worker.call(dict(op='classify',pcm_base64=base64.b64encode(pcm).decode()),session['cancel'],6)
            with self.lock:
                if (session['cancel'].is_set() or self.closed or not ui_policy.capability_allowed(self.root,entity,'ambient')
                        or time.time()-observed_at>10):return dict(empty,cancelled=True)
                events=[]
                for event in result.get('events',[])[:8]:
                    kind=str(event['kind']);score=float(event['score'])
                    if kind not in {'laughter','crying','sigh','cough','sneeze','gasp','sound'} or not math.isfinite(score) or not 0<=score<=1:
                        raise ValueError('Resultado acústico inválido.')
                    previous=session['seen'].get(kind,0);session['seen'][kind]=observed_at
                    if observed_at-previous>=1.25:
                        events.append(dict(kind=kind,label=str(event['label'])[:120],score=score,speaker='unknown',
                                           basis='acoustic_model_score_not_probability'))
                delivered=[]
                if events and not playback_overlap:
                    for target in (bus.ENTITIES if scope=='global' else (entity,)):
                        if (not ui_policy.capability_allowed(self.root,target,'ambient')
                                or (bus.presence(target) or {}).get('status')!='awake'):continue
                        identifier='acoustic-'+hashlib.sha256(f'{capture_id}:{sequence}:{target}'.encode()).hexdigest()[:32]
                        job_bus.publish(identifier,target,'done',kind='acoustic_perception',events=events,
                                        source=source,observed_at=observed_at,capture_id=capture_id,sequence=sequence,
                                        playback_overlap=False,speaker='unknown',cancelled=False)
                        session['receipts'].append((identifier,target));delivered.append(target)
                return dict(empty,events=events,delivered_to=delivered,processing_seconds=result.get('processing_seconds'))
        except Exception as exc:
            self.last_error=str(exc)[:180];self.cancel(capture_id)
            raise
        finally:self.slot.release()

    def close(self):
        with self.lock:
            self.closed=True
            for key in list(self.sessions):self.cancel(key)
        self.worker.close()
