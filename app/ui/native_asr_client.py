"""Integração Qt da fala em andamento com o transporte de áudio existente."""
import json
from PyQt5.QtGui import QTextCursor
from native_audio import wav_bytes
from native_asr import LiveTranscript


class LiveASRClient:
    def init_live_asr(self):
        self.live_turns=[];self.live_current=None;self.live_cancels={};self.live_ignoring=False

    def live_context_ok(self,turn):
        return (not turn.discarded and not self.closing and not self.shutdown_pending and
                not self.chat_read_only and not self.chat_before and not self.chat_query and
                turn.entity==self.current_entity() and turn.scope==self.chat_scope and
                turn.session_id==self.chat_session.get('id') and turn.connection==(self.base,self.token))

    def discard_live(self,cancel=True):
        owned=[(key,pending['live'][0].connection) for key,pending in self.asr_jobs.items() if key!='pending' and pending.get('live')]
        for turn in self.live_turns:turn.discard()
        self.live_turns.clear();self.live_current=None;self.live_ignoring=False
        for key in list(self.asr_jobs):
            if self.asr_jobs[key].get('live'):self.asr_jobs.pop(key,None)
        if hasattr(self,'live_preview'):self.live_preview.clear();self.live_preview.hide()
        if cancel:
            for identifier,connection in owned:self.cancel_live_job(identifier,connection)
        else:self.live_cancels.clear()

    def cancel_live_job(self,identifier,connection):
        if connection!=(self.base,self.token) or identifier in self.live_cancels:return
        pending={'connection':connection,'polling':False};self.live_cancels[identifier]=pending
        def cancelled(out):
            if self.live_cancels.get(identifier) is not pending:return
            if out and out.get('status') in ('done','error','interrupted'):self.live_cancels.pop(identifier,None)
        # Uma mutação por ID. Se o aceite for incerto, reconciliar com GET,
        # bloquear nova captura e nunca reenviar o cancelamento automaticamente.
        self.request('audio/cancel',{'id':identifier},callback=cancelled,quiet=True)

    def poll_live_cancels(self):
        for identifier,pending in list(self.live_cancels.items()):
            if pending['connection']!=(self.base,self.token):self.live_cancels.pop(identifier,None);continue
            if pending['polling']:continue
            pending['polling']=True
            def observed(out,i=identifier,p=pending):
                if self.live_cancels.get(i) is not p:return
                p['polling']=False
                if out and out.get('status') in ('done','error','interrupted'):self.live_cancels.pop(i,None)
            if not self.request(self.query('audio/job',id=identifier),callback=observed,quiet=True):pending['polling']=False

    def live_turn(self):
        if self.live_current is None:
            if len(self.live_turns)>=4:raise BufferError('Falas aguardando transcrição; envio incompleto bloqueado.')
            turn=LiveTranscript(self.capture_entity,self.capture_session,self.capture_scope,
                                self.segmenter.mode if self.segmenter else self.live_capture_mode,self.mic_settings['auto_send'])
            turn.connection=(self.base,self.token);self.live_turns.append(turn);self.live_current=turn
        return self.live_current

    def live_event(self,pcm,ended=False):
        if self.live_ignoring:
            if ended:self.live_ignoring=False
            return
        if not pcm and self.live_current is None:return
        try:
            if pcm and sum(len(t.waiting) for t in self.live_turns)>=4:raise BufferError('Fila de fala cheia; envio incompleto bloqueado.')
            turn=self.live_turn();turn.seal(pcm,ended=ended)
        except BufferError as exc:
            self.live_failure(str(exc));return
        if ended:self.live_current=None
        self.render_live();self.pump_live()

    def live_snapshot(self,pcm):
        if self.live_ignoring or len(pcm)<32000:return
        try:self.live_turn().preview(pcm)
        except BufferError as exc:self.live_failure(str(exc));return
        self.render_live();self.pump_live()

    def render_live(self):
        if not hasattr(self,'live_preview'):return
        turns=[t for t in self.live_turns if self.live_context_ok(t) and not t.sent]
        text='\n\n'.join(t.text() for t in turns if t.text())
        if self.live_preview.toPlainText()!=text:self.live_preview.setPlainText(text)
        self.live_preview.setVisible(bool(turns))

    def pump_live(self):
        if self.asr_jobs or self.closing:return
        for turn in list(self.live_turns):
            if not self.live_context_ok(turn):
                turn.discard();self.live_turns.remove(turn)
                if self.live_current is turn:self.live_current=None
        # Todos os definitivos aguardando precedem qualquer prévia.
        candidates=sorted(self.live_turns,key=lambda t:not bool(t.waiting))
        for turn in candidates:
            packet=turn.take()
            if packet is None:
                if turn.ready():self.finish_live(turn)
                continue
            try:data=wav_bytes(packet.pcm)
            except ValueError as exc:
                turn.complete(packet,'',{},error=str(exc));self.live_failure(str(exc));return
            pending=dict(entity=turn.entity,test=False,session_id=turn.session_id,scope=turn.scope,
                         mode=turn.mode,live=(turn,packet))
            self.asr_jobs['pending']=pending
            def accepted(out,t=turn,p=packet,entry=pending):
                if self.asr_jobs.get('pending') is entry:self.asr_jobs.pop('pending',None)
                if not self.live_context_ok(t):
                    if out and isinstance(out.get('id'),str):self.cancel_live_job(out['id'],t.connection)
                    return
                if out and isinstance(out.get('id'),str):self.asr_jobs[out['id']]=entry
                else:
                    t.complete(p,'',{},error='Aceite da transcrição não confirmado.')
                    if not p.preview:self.live_failure('Transcrição não confirmada; envio automático bloqueado.')
            path=self.query('audio/transcribe',entity=turn.entity,source='native_microphone',mode=turn.mode,
                            utterance=json.dumps(turn.metadata(packet),separators=(',',':')))
            if not self.request(path,data,callback=accepted,binary=True,quiet=packet.preview):accepted(None)
            return

    def live_result(self,identifier,out):
        pending=self.asr_jobs.get(identifier)
        if not pending:return
        pending['polling']=False
        if out is None or out.get('status') not in ('done','error','interrupted'):return
        self.asr_jobs.pop(identifier,None);turn,packet=pending['live']
        if not self.live_context_ok(turn):turn.discard();self.render_live();return
        valid=out.get('utterance')==turn.metadata(packet)
        if valid and out.get('error_code')=='no_speech' and not packet.preview:
            self.insert_live_text(turn,turn.text(),proof=False)
            if self.live_current is turn:
                self.live_current=None;self.live_ignoring=True  # aguardar o fim real, sem enviar a continuação órfã
            turn.discard()
            if turn in self.live_turns:self.live_turns.remove(turn)
            self.notice.setText('Som sem fala transcritível; escuta preservada. Nada enviado automaticamente.')
            self.render_live();self.pump_live();return
        error=None if out['status']=='done' and valid else out.get('error') or 'Origem da transcrição não confirmada.'
        turn.complete(packet,identifier,out.get('result'),error=error)
        if turn.failed:self.live_failure('Falha na fala definitiva; texto disponível no rascunho para revisão.');return
        self.render_live()
        if turn.ready():self.finish_live(turn)
        self.pump_live()

    def insert_live_text(self,turn,text,*,proof=True):
        if not text or not self.live_context_ok(turn):return
        editor=self.draft;old=editor.toPlainText();cursor=editor.textCursor();anchor,position=cursor.anchor(),cursor.position()
        at_end=not cursor.hasSelection() and position==len(old)
        insertion=QTextCursor(editor.document());insertion.movePosition(QTextCursor.End)
        insertion.insertText(('\n' if old else '')+text)
        restored=QTextCursor(editor.document())
        if at_end:restored.movePosition(QTextCursor.End)
        else:restored.setPosition(anchor);restored.setPosition(position,QTextCursor.KeepAnchor)
        editor.setTextCursor(restored);self.drafts[turn.entity]=editor.toPlainText()
        if proof:self.origins[turn.entity]=dict(id=turn.jobs()[-1],ids=turn.jobs(),text=text)
        else:self.origins.pop(turn.entity,None)

    def live_failure(self,message):
        for turn in self.live_turns:
            if not turn.sent:self.insert_live_text(turn,turn.text(),proof=False)
        self.stop_capture(False);self.discard_live();self.notice.setText(message)

    def finish_live(self,turn):
        if turn.sent or not turn.ready() or not self.live_context_ok(turn):return
        turn.sent=True;text=turn.text();jobs=turn.jobs()
        if len(text)>6000:
            self.insert_live_text(turn,text);self.notice.setText('Fala longa demais para envio automático; revise e divida o rascunho.');self.live_turns.remove(turn);self.render_live();return
        if not turn.auto_send:
            self.insert_live_text(turn,text);self.live_turns.remove(turn);self.render_live()
            self.notice.setText('Fala concluída no rascunho; envio automático desativado.');return
        key=(turn.scope,turn.entity,turn.session_id,text);self.submissions[key]=turn.submission_id
        data=dict(entity=turn.entity,text=text,wake=True,submission_id=turn.submission_id,
                  conversation_session_id=turn.session_id,chat_scope=turn.scope,
                  audio_job_id=jobs[-1],audio_job_ids=jobs,draft_origin=True,automatic_asr=True)
        def sent(out):
            if not self.live_context_ok(turn):return
            if out:
                self.submissions.pop(key,None);self.notice.setText('Fala completa enviada.');self.refresh()
            else:
                self.insert_live_text(turn,text)
                self.notice.setText('Envio não confirmado; rascunho preservado. Confira o chat antes de reenviar. Não houve repetição automática.')
            if turn in self.live_turns:self.live_turns.remove(turn)
            self.render_live()
        if not self.request('send',data,callback=sent):sent(None)
