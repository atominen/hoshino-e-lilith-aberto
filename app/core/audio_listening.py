"""Escuta por fonte da Central. PCM transitório; percepção nunca vira chat humano."""
from collections import deque
from datetime import datetime,timezone
import math
import threading
import time
import uuid

from core import ui_policy
from core.audio_sources import inventory
from core.audio_routes import Route
from ui.native_audio import Segmenter,wav_bytes

ATTENTION=('ativa','passiva','ignorar')
ENTITIES=('hoshino','lilith','alistair')


class Listening:
    def __init__(self,audio,*,route_factory=Route,autostart=True):
        self.audio=audio;self.factory=route_factory;self.autostart=autostart
        self.lock=threading.RLock();self.channels={e:{} for e in ENTITIES}
        self.events={e:deque(maxlen=200) for e in ENTITIES};self.routes={}
        self.instance=uuid.uuid4().hex;self.seq=0;self.closed=False
        self.thread=None;self.stop_event=threading.Event()

    def _entity(self,entity):
        if entity not in ENTITIES:raise ValueError('Entidade inválida.')
        return entity

    def _allowed(self,entity):return ui_policy.capability_allowed(self.audio.root,entity,'ambient')

    def _source(self,identifier):
        sources=inventory(True)
        rows=[s for s in sources['sources']+sources['streams'] if s['id']==identifier]
        if len(rows)!=1:raise ValueError('Fonte não disponível; atualize e selecione novamente.')
        source=rows[0]
        if source['kind']=='application_stream' and not source.get('isolated_capture'):
            raise ValueError('Captura isolada deste aplicativo está indisponível.')
        return source

    def open(self,entity,channel,source_id,attention='ativa'):
        entity=self._entity(entity)
        channel=str(channel).strip().lower()
        if not channel or len(channel)>60:raise ValueError('Nome de canal deve ter entre1 e60 caracteres.')
        if attention not in ATTENTION:raise ValueError('Escolha ativa, passiva ou ignorar.')
        with self.lock:
            if self.closed:raise ValueError('Escuta encerrando.')
            if self.routes.get(source_id,{}).get('cleanup_uncertain'):
                raise ValueError('Captura anterior tem encerramento não confirmado; nenhuma duplicata foi iniciada.')
            if not self._allowed(entity):raise ValueError('Ouvir o ambiente foi desativado para esta entidade.')
            source=self._source(source_id)
            if attention!='ignorar' and source_id not in self.routes:
                if len(self.routes)>=4:raise ValueError('Até quatro fontes simultâneas; feche outra antes.')
                try:route=self.factory(self.audio.root,source)
                except Exception as exc:
                    owned=getattr(exc,'owned_route',None)
                    if owned is not None:
                        self.routes[source_id]=dict(route=owned,source=source,pending=None,dropped=0,cleanup_uncertain=True)
                    raise
                self.routes[source_id]=dict(route=route,source=source,segmenter=Segmenter('detection',silence_ms=1000),
                    pending=None,dropped=0,last_check=0,segment_listeners=None)
            self.channels[entity][channel]=dict(channel=channel,source_id=source_id,source=source,
                attention=attention,version=uuid.uuid4().hex,status='ignorado' if attention=='ignorar' else 'capturando',error='')
            self._prune()
            if self.autostart and (self.thread is None or not self.thread.is_alive()):
                self.thread=threading.Thread(target=self._run,name='central-listening',daemon=True);self.thread.start()
            return self.state(entity)

    def _listeners(self,source_id):
        return [(e,c,r['version']) for e,channels in self.channels.items() for c,r in channels.items()
            if r['source_id']==source_id and r['attention']!='ignorar' and r['status']=='capturando' and self._allowed(e)]

    def _dispose(self,source_id):
        slot=self.routes.get(source_id)
        if not slot:return
        if slot.get('cleanup_uncertain'):return False
        pending=slot['pending']
        if pending:
            try:self.audio.cancel(pending['id'])
            except (ValueError,RuntimeError):pass
            self.audio.discard_environment(pending['id'])
        try:slot['route'].close()
        except Exception as exc:
            slot['cleanup_uncertain']=True
            for channels in self.channels.values():
                for row in channels.values():
                    if row['source_id']==source_id:row.update(status='indisponivel',error='Encerramento não confirmado.')
            raise RuntimeError('Encerramento da captura não confirmado; handle preservado, sem duplicata.') from exc
        self.routes.pop(source_id,None)
        return True

    def _prune(self):
        for source_id in list(self.routes):
            if not self._listeners(source_id):self._dispose(source_id)

    def stop(self,entity,channel=''):
        entity=self._entity(entity)
        with self.lock:
            if channel:self.channels[entity].pop(channel,None)
            else:self.channels[entity].clear()
            self._prune();return self.state(entity)

    def attention(self,entity,channel,attention):
        entity=self._entity(entity)
        if attention not in ATTENTION:raise ValueError('Escolha ativa, passiva ou ignorar.')
        with self.lock:
            row=self.channels[entity].get(channel)
            if not row:raise ValueError('Canal não está aberto.')
            if attention=='ignorar':
                row.update(attention=attention,version=uuid.uuid4().hex,status='ignorado');self._prune()
                return self.state(entity)
            return self.open(entity,channel,row['source_id'],attention)

    def state(self,entity):
        entity=self._entity(entity)
        with self.lock:
            channels=[]
            for row in self.channels[entity].values():
                slot=self.routes.get(row['source_id'])
                channels.append({k:v for k,v in row.items() if k!='version'}|dict(
                    pending=bool(slot and slot['pending']),dropped_segments=slot['dropped'] if slot else 0))
            return dict(instance=self.instance,entity=entity,channels=channels,allowed=self._allowed(entity),
                source_limit=4,asr='compartilhado · CPU · baixa prioridade',
                capture_count=sum(not r.get('cleanup_uncertain',False) for r in self.routes.values()),
                uncertain_count=sum(bool(r.get('cleanup_uncertain')) for r in self.routes.values()))

    def recent(self,entity,after=0):
        entity=self._entity(entity);after=float(after)
        if not math.isfinite(after) or after<0:raise ValueError('Cursor inválido.')
        with self.lock:
            items=[dict(r) for r in self.events[entity] if r['seq']>after] if self._allowed(entity) else []
            return dict(instance=self.instance,items=items,cursor=self.seq)

    def _failed(self,source_id,error):
        for channels in self.channels.values():
            for row in channels.values():
                if row['source_id']==source_id and row['attention']!='ignorar':
                    row.update(status='indisponivel',error=error)
        try:self._dispose(source_id)
        except RuntimeError:pass

    def _result(self,slot):
        pending=slot['pending']
        if pending is None:return
        job=self.audio.take_environment(pending['id'])
        if job['status'] not in ('done','error','interrupted'):return
        slot['pending']=None
        if job['status']!='done':
            if job.get('error_code')=='no_speech':return
            raise ValueError('Transcrição do canal não foi concluída; reabra após conferir a falha.')
        if not slot['route'].valid():raise ValueError('Fonte mudou antes da entrega; resultado descartado.')
        text=str((job.get('result') or {}).get('text') or '').strip()
        if not text:return
        for entity,channel,version in pending['listeners']:
            row=self.channels[entity].get(channel)
            if (not row or row['version']!=version or row['attention']=='ignorar'
                    or row['status']!='capturando' or not self._allowed(entity)):continue
            self.seq+=1
            self.events[entity].append(dict(id=self.instance+':'+str(self.seq),seq=self.seq,channel=channel,
                source_id=row['source_id'],origin=row['source']['label'],application=row['source'].get('application'),
                source_kind=row['source']['kind'],attention=row['attention'],text=text,speaker='desconhecido',
                observed_at=pending['observed_at'],asr_id=pending['id']))

    def step(self):
        with self.lock:
            if self.closed:return
            for entity,channels in self.channels.items():
                if not self._allowed(entity):
                    for row in channels.values():
                        if row['attention']!='ignorar' and row['status']=='capturando':
                            row.update(status='indisponivel',version=uuid.uuid4().hex,error='Escuta revogada na Central.')
            try:self._prune()
            except RuntimeError:pass
            for source_id,slot in list(self.routes.items()):
                if slot.get('cleanup_uncertain'):continue
                try:
                    # Antes de consumir ou publicar, a origem física deve ser a mesma.
                    if time.monotonic()-slot['last_check']>=1:
                        if not slot['route'].valid():raise ValueError('Fonte desapareceu ou mudou; selecione novamente.')
                        slot['last_check']=time.monotonic()
                    self._result(slot)
                    data=slot['route'].read(.01)
                    if not data:continue
                    was_speaking=slot['segmenter'].speaking
                    listeners_at_start=self._listeners(source_id)
                    _,segments=slot['segmenter'].feed(data)
                    if not was_speaking:slot['segment_listeners']=listeners_at_start
                    for pcm in segments:
                        if slot['pending'] is not None:slot['dropped']+=1;continue
                        listeners=slot['segment_listeners'] or []
                        if not listeners:continue
                        if not slot['route'].valid():raise ValueError('Fonte mudou; trecho descartado.')
                        try:
                            job=self.audio.submit_environment(listeners[0][0],wav_bytes(pcm))
                        except ValueError:slot['dropped']+=1;continue
                        slot['pending']=dict(id=job['id'],listeners=listeners,
                            observed_at=datetime.now(timezone.utc).isoformat())
                    if segments or not slot['segmenter'].speaking:
                        slot['segment_listeners']=listeners_at_start if slot['segmenter'].speaking else None
                except Exception as exc:
                    self._failed(source_id,str(exc)[:180])

    def _run(self):
        while not self.stop_event.is_set():
            self.step();self.stop_event.wait(.08 if self.routes else .5)

    def close(self):
        with self.lock:
            self.closed=True;self.stop_event.set()
            for entity in self.channels:self.channels[entity].clear()
            errors=[]
            for source_id in list(self.routes):
                try:
                    if self._dispose(source_id) is False:errors.append(source_id)
                except RuntimeError:errors.append(source_id)
        if self.thread and self.thread is not threading.current_thread():self.thread.join(5)
        if errors:raise RuntimeError('Encerramento de fontes não confirmado; processos próprios preservados para reconciliação.')
