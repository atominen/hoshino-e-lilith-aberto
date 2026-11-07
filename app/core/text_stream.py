"""Prévia transitória de resposta pública; não é memória nem recibo de ação."""
import re
import uuid
from threading import RLock
from time import monotonic, time
from core import diagnostics, interentity, job_bus

KIND = 'llm_text'
_PRIVATE = re.compile(r'<\s*/?\s*(?:think|analysis|reasoning|scratchpad)(?:\s|>|$)|'
                      r'\[\s*(?:CICLO\s+INTERNO|SISTEMA)(?:\s|\]|$)', re.I)
_FIELDS = ('id', 'entity', 'status', 'text', 'revision', 'turn_id', 'input_ids', 'reply_to',
           'chat_scope', 'conversation_session_id', 'room_day', 'final_message_id', 'reason')


class TextStream:
    def __init__(self, entity, channel, *, validator, cancelled, request_id=''):
        self.envelope = interentity.processing_envelope(entity)
        if entity not in {'hoshino', 'lilith'} or channel != 'localhub' or not self.envelope:
            raise ValueError('Prévia exige uma conversa humana local com origem verificada.')
        self.entity = entity
        self.validator, self.cancelled = validator, cancelled
        self.id = 'text-' + uuid.uuid4().hex
        self.request_id = request_id
        self.origin = diagnostics.current_turn_context()
        self.text = self.seen = ''
        self.started = self.finished = self.stopped = self.committed = False
        self.revision = 0
        self.last_write = float('-inf')
        self._lock = RLock()

    def _emit(self, status='running', **extra):
        self.revision += 1
        job_bus.publish(self.id, self.entity, status, kind=KIND, text=self.text,
                        revision=self.revision, final=self.committed,
                        turn_id=self.origin.get('turn_id'), input_ids=self.origin.get('input_ids', []),
                        reply_to=self.envelope['message_id'],
                        chat_scope=self.envelope['chat_scope'],
                        conversation_session_id=self.envelope['conversation_session_id'],
                        room_day=self.envelope['room_day'], published_at=time(), auto_retry=False, **extra)
        self.started = True
        self.last_write = monotonic()

    def push(self, text: str) -> None:
        if self.stopped or self.finished or self.committed:
            return
        try:
            if self.cancelled():
                self.stop('user_interruption'); return
            if not isinstance(text, str) or len(text) > 12000:
                self.stop('text_limit', discard_text=True); return
            if not text.startswith(self.seen):
                self.stop('prefix_changed', discard_text=True); return
            self.seen = text
            if _PRIVATE.search(text):
                self.stop('private_content', discard_text=True); return
            # Um '<thi' ou '[CICLO IN' pode atravessar vários frames. Nunca
            # publicá-lo antes de saber se é um marcador de conteúdo interno.
            visible = text
            for opening, closing in (('<', '>'), ('[', ']')):
                index = visible.rfind(opening)
                if index >= 0 and closing not in visible[index:]:
                    visible = visible[:index]
            if not visible or visible == self.text:
                return
            if not self.validator(visible):
                self.stop('verification_gate', discard_text=True); return
            # O cancelamento vem do consumidor da conversa; a geração roda
            # em outra thread. Validar fora da trava permite cancelar logo,
            # mas o último teste e a primeira publicação precisam ser atômicos.
            with self._lock:
                if self.stopped or self.finished or self.committed:
                    return
                if self.cancelled():
                    self.stop('user_interruption'); return
                self.text = visible
                if not self.started or monotonic() - self.last_write >= .1:
                    self._emit()
        except Exception as exc:
            self.stop('preview_unavailable', discard_text=True)
            diagnostics.emit('chat.preview_failed', level='WARN', error_type=type(exc).__name__)

    def finish(self, text: str) -> None:
        if self.stopped or self.finished or self.committed:
            return
        self.push(text)
        with self._lock:
            if self.stopped or self.finished or self.committed:
                return
            self.finished = True
            if self.text:
                try: self._emit()
                except Exception: self.stop('preview_unavailable', discard_text=True)

    def commit(self, message_id: str) -> None:
        with self._lock:
            if self.stopped or self.committed or not self.finished or not self.started:
                return
            with interentity._transaction() as db:
                row = db.execute('SELECT * FROM entity_messages WHERE id=?', (str(message_id),)).fetchone()
                meta = interentity._metadata(row) if row else {}
                if (not row or row['sender'] != self.entity or row['recipient'] != 'usuario'
                        or row['kind'] != 'chat' or meta.get('private')
                        or meta.get('reply_to') != self.envelope['message_id']
                        or self.id not in meta.get('text_streams', []) or row['text'] != self.seen.strip()):
                    raise ValueError('Prévia sem publicação final física correspondente.')
            self.committed = True
            self._emit('done', final_message_id=message_id)

    def stop(self, reason: str, *, discard_text=False) -> None:
        with self._lock:
            if self.committed or (self.stopped and not discard_text):
                return
            self.stopped = True
            if discard_text: self.text = ''
            if self.started:
                try: self._emit('interrupted', reason=reason, invalidated=discard_text)
                except Exception as exc:
                    diagnostics.emit('chat.preview_stop_failed', level='WARN', error_type=type(exc).__name__)


def snapshot(entity: str, session_id: str, chat_scope: str) -> dict:
    if entity not in interentity.ENTITIES or chat_scope not in {'direct', 'global'}:
        raise ValueError('Entidade ou sala de prévia inválida.')
    current = interentity.daily_session(entity)
    if session_id != current['id']:
        raise ValueError('Prévia disponível somente na sessão corrente desta entidade.')
    projected = []
    for row in job_bus.status(limit=200, kind=KIND):
        details = row['details']
        if not details.get('text') or time() - details.get('published_at', 0) > 120:
            continue
        if chat_scope == 'direct':
            allowed = (row['entity'] == entity and details.get('chat_scope') == 'direct'
                       and details.get('conversation_session_id') == session_id)
        else:
            allowed = (row['entity'] in {'hoshino', 'lilith'} and details.get('chat_scope') == 'global'
                       and details.get('room_day') == current['local_date'])
        if allowed:
            value = dict(details, id=row['id'], entity=row['entity'], status=row['status'])
            projected.append({key: value.get(key) for key in _FIELDS})
        if len(projected) == 8: break
    return dict(streams=projected)
