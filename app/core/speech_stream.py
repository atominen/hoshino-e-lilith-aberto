"""Sentenças de uma resposta em andamento no diário de jobs já existente."""
from contextvars import ContextVar
import re
import time
import uuid
from core import job_bus, diagnostics
from core.audio_text import SentenceBuffer, clean_for_speech

context = ContextVar('speech_stream_context',default=None)


class SpeechStream:
    def __init__(self, entity, channel, *, validator=None, cancelled=None, request_id=''):
        self.entity, self.channel = entity,channel
        self.validator = validator or (lambda _:True)
        self.cancelled = cancelled or (lambda:False)
        self.id = 'speech-'+uuid.uuid4().hex
        self.buffer = SentenceBuffer()
        self.sentences = []
        self.stopped = False
        self.started = False
        self.request_id = request_id
        self.origin = diagnostics.current_turn_context()
        from core import interentity
        self.conversation_session = interentity.processing_session(entity) if channel == 'localhub' else None
        self.envelope = interentity.processing_envelope(entity) if channel == 'localhub' else None
        self.created = time.monotonic()

    def push(self, text, *, final=False):
        if self.stopped:
            return
        if self.cancelled():
            self.stop('user_interruption')
            return
        if re.search(r'<\s*/?\s*(?:think|analysis|reasoning|scratchpad)(?:\s|>|$)|\[(?:CICLO INTERNO|SISTEMA)',text,re.I):
            self.stop('private_or_internal_content')
            return
        try:
            for sentence in self.buffer.push(text,final=final):
                cleaned = clean_for_speech(sentence)
                if not cleaned:
                    continue
                if not self.validator(cleaned) or sum(map(len,self.sentences))+len(cleaned)>2400:
                    self.stop('verification_or_length_gate')
                    return
                self.sentences.append(cleaned)
                job_bus.publish(self.id,self.entity,'running',kind='llm_speech', channel=self.channel,
                                sentences=self.sentences,request_id=self.request_id,stable_only=True,
                                turn_id=self.origin.get('turn_id'),input_ids=self.origin.get('input_ids', []),
                                conversation_session_id=(self.conversation_session or {}).get('id'),
                                chat_scope=(self.envelope or {}).get('chat_scope','direct'),
                                room_day=(self.envelope or {}).get('room_day'),
                                reply_to=(self.envelope or {}).get('message_id'),
                                elapsed_seconds=time.monotonic()-self.created)
                self.started = True
        except Exception as exc:
            self.stop('unstable_or_unavailable_stream')
            diagnostics.emit('voice.stream_failed',level='WARN',entity=self.entity,error_type=type(exc).__name__)

    def finish(self,text,*,commit=True):
        self.push(text,final=True)
        if commit: self.commit()

    def commit(self):
        if self.started and not self.stopped:
            job_bus.publish(self.id,self.entity,'done',kind='llm_speech',sentences=self.sentences)

    def stop(self,reason='cancelled'):
        self.stopped = True
        if self.started:
            try:
                old = job_bus.get(self.id,self.entity)
                status = old['status'] if old and old['status'] in job_bus.TERMINAL else 'interrupted'
                # Cancelar uma fala já gerada não reabre o job textual terminal.
                job_bus.publish(self.id,self.entity,status,kind='llm_speech',reason=reason,auto_retry=False,invalidated=True)
            except Exception as exc:
                diagnostics.exception('voice.stream_cancel_failed',exc,stream_id=self.id)
