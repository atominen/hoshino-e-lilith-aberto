"""Qt real + transporte/processos simulados. NÃO valida hardware/voz real."""
import array
import json
import os
import sys
import unittest
import time
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/ui'))
import central_native as ui
from native_audio import FRAME_BYTES
from PyQt5.QtTest import QTest
from PyQt5.QtCore import QPoint, QPointF
from PyQt5.QtGui import QWheelEvent, QKeyEvent, QFocusEvent, QImage, QCloseEvent

def daily_fixture(entity='hoshino', *, day='2026-10-09', archived=False, messages=None):
    session={'id':'fixture-'+entity+'-'+day,'entity':entity,'participant':'usuario',
             'local_date':day,'timezone':'America/Sao_Paulo','schema':1}
    current=dict(session,id='fixture-'+entity+'-2026-10-09',local_date='2026-10-09')
    return {'presence':[],'jobs':[],'resources':[],'conversation':messages or [],
            'chat_session':session,'current_chat_session':current,'chat_read_only':archived,
            'chat_sessions':[current,session] if archived else [session],
            'page':{'upper':100,'has_more':False,'next_before':None},'day_summary':{'message_count':len(messages or [])}}

class Signal:
    def __init__(self):self.handlers=[]
    def connect(self,fn):self.handlers.append(fn)
    def emit(self,*a):
        for fn in self.handlers:fn(*a)

class FakeProcess:
    NotRunning=0;FailedToStart=0;NormalExit=0
    def __init__(self,parent=None):
        self.readyReadStandardOutput=Signal();self.errorOccurred=Signal();self.finished=Signal();self.started=Signal();self.running=False;self.stdout=b''
    def start(self,program,args):self.program=program;self.args=args;self.running=True
    def terminate(self):self.running=False
    def kill(self):self.running=False
    def state(self):return int(self.running)
    def processId(self):return 4242 if self.running else 0
    def deleteLater(self):self.running=False
    def readAllStandardOutput(self):data=self.stdout;self.stdout=b'';return data
    def setWorkingDirectory(self,path):self.directory=path
    def write(self,data):self.stdin=data
    def closeWriteChannel(self):pass

class NativeContracts(unittest.TestCase):
    def test_clipboard_import_creates_a_draft_without_sending(self):
        w = self.window
        w.chat_scope = 'direct'
        w.chat_read_only = False
        w.chat_session = {'id': 'current-fixture'}
        self.requests.clear()
        clipboard = ui.QApplication.clipboard()
        self.addCleanup(clipboard.clear)
        clipboard.setText('Texto copiado para leitura')
        with patch.object(w, 'request') as request:
            w.import_clipboard()
            route, payload = request.call_args.args
            self.assertTrue(route.startswith('control/attachment?'))
            self.assertEqual(parse_qs(urlsplit(route).query)['name'], ['clipboard-texto.txt'])
            self.assertEqual(payload, b'Texto copiado para leitura')
            request.call_args.kwargs['callback']({'name': 'abc123abc123-clipboard-texto.txt'})
        self.assertIn('Leia o anexo abc123abc123-clipboard-texto.txt', w.draft.toPlainText())
        self.assertFalse(any(route == 'send' for route, _, _ in self.requests))
        image = QImage(8, 8, QImage.Format_RGB32)
        image.fill(0xff006600)
        clipboard.setImage(image)
        with patch.object(w, 'request') as request:
            w.import_clipboard()
            route, payload = request.call_args.args
            self.assertEqual(parse_qs(urlsplit(route).query)['name'], ['clipboard-print.png'])
            self.assertTrue(payload.startswith(b'\x89PNG\r\n\x1a\n'))
            request.call_args.kwargs['callback']({'name': 'abc123abc123-clipboard-print.png'})
        self.assertIn('Observe a imagem recebida abc123abc123-clipboard-print.png', w.draft.toPlainText())
        w.ui_config = {'settings': {'clipboard_import': False}}
        with patch.object(w, 'request') as request:
            w.import_clipboard()
            request.assert_not_called()

    def test_history_timeline_shows_records_and_opens_copied_content(self):
        from native_panels import HistoryTimelinePanel
        read = Mock()
        open_attachment = Mock()
        panel = HistoryTimelinePanel(read, open_attachment)
        self.addCleanup(panel.deleteLater)
        panel.set_entity('lilith')
        panel.search.setText('clipboard')
        panel.search_first()
        entity, offset, filters, callback = read.call_args.args
        self.assertEqual((entity, offset, filters['q']), ('lilith', 0, 'clipboard'))
        name = 'abc123abc123-clipboard-print.png'
        callback({'page_size': 25, 'next_offset': 25, 'items': [{
            'record_kind': 'message', 'content': 'Observe a imagem recebida ' + name, 'author': 'Usuário',
        }]})
        panel.rows.setCurrentItem(panel.rows.topLevelItem(0))
        self.assertIn(name, panel.detail.toPlainText())
        panel.preview.click()
        open_attachment.assert_called_once_with('lilith', name)
        panel.next_page()
        self.assertEqual(read.call_args.args[1], 25)

    def test_listening_panel_is_inside_audio_and_targets_selected_entity(self):
        w=self.window;p=w.listening_panel
        p.render(dict(entity='hoshino',allowed=True,channels=[],sources=[
            dict(id='pw:42',label='Minecraft',kind='application_stream',isolated_capture=True)],capture_count=0))
        p.source.setCurrentIndex(p.source.findData('pw:42'));p.channel.setText('jogo');self.requests.clear()
        p.open_source()
        sent=next(d for route,d,_ in self.requests if route=='audio/listening')
        self.assertEqual(sent,dict(action='open',entity='hoshino',channel='jogo',source_id='pw:42',attention='ativa'))
        self.assertIn('Fontes e atenção',[w.audio_tabs.tabText(i) for i in range(w.audio_tabs.count())])

    def test_stale_listening_reply_does_not_render_other_entity_channels(self):
        w=self.window;p=w.listening_panel;w.entity.setCurrentIndex(1)
        p.render(dict(entity='hoshino',allowed=True,channels=[dict(channel='segredo')],sources=[],capture_count=1))
        self.assertEqual(p.channels.topLevelItemCount(),0)

    def test_entities_page_has_no_pair_wake_and_alistair_card_has_no_emotion(self):
        # 06/11 (pedido humano): sem "Acordar Hoshino e Lilith" juntas; Alistair sem linha de emoção.
        w=self.window
        self.assertFalse(hasattr(w,'wake_pair'))
        buttons=[b.text() for b in w.findChildren(ui.QPushButton)]
        self.assertNotIn('Acordar Hoshino e Lilith',buttons);self.assertGreaterEqual(buttons.count('Acordar'),3)
        w.entity_details={'lilith':{'expression_profile':{'available':True,'dominant':'curiosidade'}}}
        w.refresh_received_for_test=None
        state=daily_fixture('hoshino');state['presence']=[{'entity_id':e,'status':'awake'} for e in ui.ENTITIES]
        with patch.object(ui.Central,'request',lambda win,path,data=None,callback=None,**k:(callback(state) if callback else None) or object()):
            w.polling=False;w.refresh()
        self.assertNotIn('Emoção',w.cards['alistair'].text());self.assertIn('Emoção: curiosidade',w.cards['lilith'].text())

    def live_fixture(self):
        w=self.window;w.mic_settings.update(auto_send=True,silence_ms=2000);self.requests.clear();sequence=[]
        def request(path,data=None,callback=None,**kwargs):
            self.requests.append((path,data,kwargs))
            if path.startswith('audio/transcribe'):
                identifier='live-'+str(len(sequence));sequence.append(identifier)
                if self.defer:self.deferred.append(callback)
                elif callback:callback({'id':identifier})
            elif path=='send' and callback:callback({'id':'accepted'})
            elif path=='audio/cancel' and callback:callback({'id':data['id'],'status':'interrupted'})
            return object()
        p=patch.object(w,'request',side_effect=request);p.start();self.addCleanup(p.stop)
        return w,sequence

    def live_result(self,w,identifier,text,error=False):
        pending=w.asr_jobs[identifier];turn,packet=pending['live']
        w.asr_result(identifier,dict(status='error' if error else 'done',error='falha' if error else None,
                                   utterance=turn.metadata(packet),result={'text':text}))

    def feed_live(self,w,voice_frames=20,quiet_frames=0):
        voiced=array.array('h',[3000]*(FRAME_BYTES//2)).tobytes()*voice_frames
        w.capture.stdout=voiced+bytes(FRAME_BYTES*quiet_frames);w.capture.readyReadStandardOutput.emit()

    def test_live_preview_is_visible_before_release_and_never_sends(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w)
        self.assertEqual(len(ids),1);self.live_result(w,ids[0],'Eu gosto de casa.')
        self.assertEqual(w.live_preview.toPlainText(),'Eu gosto de casa.')
        self.assertFalse(any(p=='send' for p,_,_ in self.requests));self.assertEqual(w.draft.toPlainText(),'')

    def test_live_final_sends_once_after_release_with_final_proof_only(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w)
        self.live_result(w,ids[0],'Eu gosto de casa.');w.stop_capture(True)
        self.assertEqual(len(ids),2);self.assertFalse(any(p=='send' for p,_,_ in self.requests))
        self.live_result(w,ids[1],'Eu gosto de café.')
        sent=[d for p,d,_ in self.requests if p=='send'];self.assertEqual(len(sent),1)
        self.assertEqual(sent[0]['text'],'Eu gosto de café.');self.assertEqual(sent[0]['audio_job_ids'],[ids[1]])
        w.poll_audio();self.assertEqual(len([p for p,_,_ in self.requests if p=='send']),1)

    def test_live_two_seconds_and_physical_boundary_form_one_message(self):
        w,ids=self.live_fixture();w.start_capture('detection');w.segmenter.maximum=FRAME_BYTES*30
        self.feed_live(w,30);self.live_result(w,ids[0],'Primeira parte.')
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))
        self.feed_live(w,10,39);self.assertFalse(any(p=='send' for p,_,_ in self.requests))
        self.feed_live(w,0,1)
        while w.asr_jobs:
            identifier=next(iter(w.asr_jobs));self.live_result(w,identifier,'Continuação.')
        sent=[d for p,d,_ in self.requests if p=='send'];self.assertEqual(len(sent),1)
        self.assertEqual(sent[0]['text'],'Primeira parte. Continuação.')

    def test_live_discard_invalidates_late_http_acceptance(self):
        w,ids=self.live_fixture();self.defer=True;w.start_capture('command');self.feed_live(w)
        self.assertEqual(len(self.deferred),1);w.stop_capture(False)
        self.deferred[0]({'id':'late'});w.poll_audio()
        self.assertNotIn('late',w.asr_jobs);self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_live_context_change_discards_final_instead_of_sending_elsewhere(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w);w.stop_capture(True)
        w.chat_session={'id':'other-session'}
        self.live_result(w,ids[0],'Texto atrasado.')
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_live_final_preserves_typed_draft_and_selection_when_not_auto_sent(self):
        w,ids=self.live_fixture();w.mic_settings['auto_send']=False
        w.draft.setPlainText('Meu rascunho');cursor=w.draft.textCursor();cursor.setPosition(1);cursor.setPosition(5,cursor.KeepAnchor);w.draft.setTextCursor(cursor)
        w.start_capture('command');self.feed_live(w);self.live_result(w,ids[0],'Prévia.');w.stop_capture(True)
        self.live_result(w,ids[1],'Fala final.')
        self.assertEqual(w.draft.toPlainText(),'Meu rascunho\nFala final.')
        self.assertEqual(w.draft.textCursor().selectedText(),'eu r')
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_live_failed_final_keeps_preview_for_recovery_without_send(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w)
        self.live_result(w,ids[0],'Prévia recuperável.');w.stop_capture(True)
        self.live_result(w,ids[1],'',error=True)
        self.assertIn('Prévia recuperável.',w.draft.toPlainText())
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_live_non_speech_sound_keeps_detection_listening(self):
        w,ids=self.live_fixture();w.start_capture('detection');capture=w.capture
        self.feed_live(w,10,40)
        pending=w.asr_jobs[ids[0]];turn,packet=pending['live']
        w.asr_result(ids[0],dict(status='error',error='Não foi detectada fala.',error_code='no_speech',
                               utterance=turn.metadata(packet),result=None))
        self.assertIs(w.capture,capture);self.assertTrue(capture.running)
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_live_late_preview_is_shown_while_final_is_pending(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w);w.stop_capture(True)
        self.live_result(w,ids[0],'Uma prévia tardia.')
        self.assertEqual(w.live_preview.toPlainText(),'Uma prévia tardia.')
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_live_pressing_command_again_keeps_completed_utterance_pending(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w);w.stop_capture(True)
        pending=w.asr_jobs[ids[0]];turn,_=pending['live'];w.ptt_start()
        self.assertFalse(turn.discarded);self.assertIn(ids[0],w.asr_jobs);self.assertIsNone(w.capture)
        self.live_result(w,ids[0],'Prévia.');self.live_result(w,ids[1],'Fala concluída.')
        self.assertEqual(len([p for p,_,_ in self.requests if p=='send']),1)

    def test_live_discard_cancels_owned_jobs_and_late_acceptance(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w);w.stop_capture(False)
        self.assertTrue(any(p=='audio/cancel' and d['id']==ids[0] for p,d,_ in self.requests))
        self.defer=True;w.start_capture('command');self.feed_live(w);w.stop_capture(False)
        self.deferred[-1]({'id':'late-owned'})
        self.assertTrue(any(p=='audio/cancel' and d['id']=='late-owned' for p,d,_ in self.requests))

    def test_live_discard_never_cancels_old_ids_on_new_backend(self):
        w,ids=self.live_fixture();self.defer=True;w.start_capture('command');self.feed_live(w)
        accepted=self.deferred[-1];w.stop_capture(False);w.token='new-backend';accepted({'id':'old-id'})
        self.assertFalse(any(p=='audio/cancel' and d['id']=='old-id' for p,d,_ in self.requests))

    def test_live_unconfirmed_cancel_blocks_new_capture_until_terminal_status(self):
        w,ids=self.live_fixture();w.start_capture('command');self.feed_live(w)
        original=w.request.side_effect
        def uncertain(path,data=None,callback=None,**kw):
            if path=='audio/cancel':self.requests.append((path,data,kw));return object()
            return original(path,data,callback,**kw)
        w.request.side_effect=uncertain;w.stop_capture(False);w.start_capture('command')
        self.assertIsNone(w.capture)

    def test_live_short_residual_after_physical_boundary_is_preserved_and_sent(self):
        w,ids=self.live_fixture();w.start_capture('command');w.segmenter.maximum=FRAME_BYTES*30
        self.feed_live(w,30);self.live_result(w,ids[0],'Parte longa.')
        self.feed_live(w,1);w.stop_capture(True)
        self.assertEqual(len(ids),2);self.live_result(w,ids[1],'Fim.')
        sent=[d for p,d,_ in self.requests if p=='send'];self.assertEqual(sent[0]['text'],'Parte longa. Fim.')

    def test_live_final_backlog_limit_applies_across_utterances(self):
        from native_asr import LiveTranscript
        w,ids=self.live_fixture();w.start_capture('detection');self.feed_live(w)
        for i in range(2):
            turn=LiveTranscript(w.current_entity(),w.chat_session['id'],w.chat_scope,'detection',True)
            turn.connection=(w.base,w.token)
            for _ in range(2):turn.seal(bytes(6400),ended=False)
            w.live_turns.append(turn)
        w.live_event(bytes(6400),True)
        self.assertIsNone(w.capture);self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_first_audio_request_fetches_chunk_zero_not_the_complete_reply(self):
        w=self.window;w.voice_job='job';w.voice_entity='lilith';w.voice_index=0;played=[]
        def request(path,data=None,callback=None,**kwargs):
            if path.startswith('audio/job?'):
                callback(dict(status='done',result={'chunks':[{'index':0},{'index':1}]}))
            elif path.startswith('audio/file?'):
                params=parse_qs(urlsplit(path).query)
                callback({'0':b'FIRST','1':b'SECOND'}.get(params.get('chunk',[''])[0],b'FULL_REPLY'))
            return object()
        def play(data,*args):played.append(data);w.voice_index+=1
        with patch.object(w,'request',side_effect=request),patch.object(w,'play_bytes',side_effect=play):
            w.poll_audio();w.poll_audio()
        self.assertEqual(played,[b'FIRST',b'SECOND'])

    def test_cancel_is_confirmed_only_after_owned_player_exits(self):
        w=self.window;w.voice_job='job';w.voice_entity='hoshino';w.voice_index=0
        w.play_bytes(b'fixture','job','hoshino',0);player=w.player;player.started.emit()
        player.terminate=lambda:None
        w.stop_voice()
        reports=lambda:[d['playback_event'] for p,d,_ in self.requests if p=='audio/job']
        self.assertNotIn('cancelled',reports());self.assertIs(w.player,player)
        self.assertFalse(w.can_auto_speak('lilith'))
        player.running=False;player.finished.emit(-1,0)
        self.assertEqual(reports().count('cancelled'),1);self.assertIsNone(w.player)

    def test_ordinary_message_does_not_cut_voice_in_native_client(self):
        w=self.window;w.voice_job='playing';w.voice_entity='hoshino';w.player=FakeProcess()
        w.draft.setPlainText('E também gosto de astronomia.')
        with patch.object(w,'refresh'):w.send()
        self.assertEqual(w.voice_job,'playing');self.assertIsNotNone(w.player)

    def test_player_progress_reports_actual_active_chunk_and_stops_after_end(self):
        w=self.window;w.play_bytes(b'fixture','job','hoshino',0);player=w.player;player.started.emit()
        w.playback_progress['last']-=2;w.poll_audio()
        reports=[d for p,d,_ in self.requests if p=='audio/job']
        self.assertEqual([d['playback_event'] for d in reports],['started','progress'])
        player.finished.emit(0,0);w.poll_audio()
        self.assertIsNone(w.playback_progress)

    def test_opening_microphone_does_not_cut_current_voice(self):
        w=self.window
        for mode in ('command','detection'):
            w.voice_job='playing';w.voice_entity='hoshino';player=FakeProcess();w.player=player
            w.start_capture(mode)
            self.assertIs(w.player,player);self.assertEqual(w.voice_job,'playing')
            w.stop_capture(False);w.player=None;w.voice_job=None

    def test_headphones_keep_speech_transcription_during_playback(self):
        w=self.window;w.start_capture('detection');capture=w.capture;w.player=FakeProcess()
        capture.stdout=(b'\xff\x3f'*16000)+bytes(64000);capture.readyReadStandardOutput.emit()
        self.assertTrue(any(p.startswith('audio/transcribe') for p,_,_ in self.requests))
        self.assertIsNotNone(w.player)

    def test_global_progressive_voice_uses_other_entity_and_not_direct_streams(self):
        w=self.window;w.auto_voice.setChecked(True)
        out=daily_fixture();session=out['chat_session']
        def stream(identifier,scope):
            return dict(id=identifier,entity='lilith',kind='llm_speech',status='running',updated_at=ui.time.time(),
                details=dict(channel='localhub',stable_only=True,sentences=['Olá.'],chat_scope=scope,
                             room_day=session['local_date'],conversation_session_id='lilith-other-session'))
        out['jobs']=[stream('direct-secret','direct'),stream('global-visible','global')]
        with patch.object(w,'request',side_effect=lambda p,callback=None,**kw:callback(out) or object()),patch.object(w,'begin_speech',return_value=True) as speak:
            w.refresh()
        self.assertEqual(speak.call_count,1)
        self.assertEqual(speak.call_args.args[0],'lilith')
        self.assertEqual(speak.call_args.args[2]['stream_id'],'global-visible')

    def text_stream_fixture(self):
        w=self.window;w.nav.setCurrentRow(ui.PAGES.index('Conversa'));w.chat_stream_timer.stop()
        data=daily_fixture();callbacks=[];calls=[]
        preview=dict(id='text-fixture',entity='hoshino',text='Olá mundo',status='running',revision=1,
                     chat_scope='global',conversation_session_id=data['chat_session']['id'],room_day='2026-10-09')
        def request(path,data=None,callback=None,**kwargs):
            calls.append(path)
            if path.startswith('chat/streams?'):
                callbacks.append(callback);return object()
            if path.startswith('state?') and callback:callback(daily)
            return object()
        daily=data
        p=patch.object(w,'request',side_effect=request);p.start();self.addCleanup(p.stop)
        w.refresh();return w,daily,preview,callbacks,calls

    def test_text_stream_is_visible_before_final_and_not_duplicated_after_commit(self):
        w,daily,preview,callbacks,_=self.text_stream_fixture()
        w.auto_voice.setChecked(False);w.poll_chat_streams();callbacks.pop(0)({'streams':[preview]})
        self.assertIn('Olá mundo',w.chat.toPlainText());self.assertIn('gerando',w.chat.toPlainText())
        daily['conversation']=[dict(id='final',sender='hoshino',recipient='usuario',text='Olá mundo',kind='chat',
                                    metadata={'text_streams':['text-fixture']})]
        w.refresh();self.assertEqual(w.chat.toPlainText().count('Olá mundo'),1)
        self.assertNotIn('gerando',w.chat.toPlainText())

    def test_text_stream_keeps_selection_scroll_focus_and_draft_when_reading_above(self):
        w,daily,preview,callbacks,_=self.text_stream_fixture()
        daily['conversation']=[dict(id=str(i),sender='usuario',recipient='hoshino',text=('Mensagem antiga '+str(i)+'\n')*8,metadata={}) for i in range(30)]
        w.show();w.refresh();ui.QApplication.processEvents()
        bar=w.chat.verticalScrollBar();bar.setValue(bar.maximum()//3);position=bar.value()
        cursor=w.chat.textCursor();cursor.setPosition(10);cursor.setPosition(24,cursor.KeepAnchor);w.chat.setTextCursor(cursor)
        bar.setValue(position);selected=w.chat.textCursor().selectedText()
        w.draft.setPlainText('Rascunho preservado');w.draft.setFocus();focus=w.focusWidget()
        w.poll_chat_streams();callbacks.pop(0)({'streams':[preview]});ui.QApplication.processEvents()
        self.assertEqual(bar.value(),position);self.assertEqual(w.chat.textCursor().selectedText(),selected)
        self.assertEqual(w.draft.toPlainText(),'Rascunho preservado');self.assertIs(w.focusWidget(),focus)

    def test_text_stream_follows_bottom_and_escapes_html(self):
        w,daily,preview,callbacks,_=self.text_stream_fixture()
        daily['conversation']=[dict(id='long',sender='usuario',recipient='hoshino',text='Antiga\n'*100,metadata={})]
        w.show();w.refresh();ui.QApplication.processEvents();bar=w.chat.verticalScrollBar();bar.setValue(bar.maximum())
        w.poll_chat_streams();callbacks.pop(0)({'streams':[preview|dict(text='<b>texto literal</b>\n'*40)]})
        ui.QApplication.processEvents();self.assertEqual(bar.value(),bar.maximum())
        self.assertIn('<b>texto literal</b>',w.chat.toPlainText())

    def test_text_stream_one_request_in_flight_and_no_foreign_callback_after_reset(self):
        w,_,preview,callbacks,calls=self.text_stream_fixture()
        w.poll_chat_streams();w.poll_chat_streams()
        self.assertEqual(len([p for p in calls if p.startswith('chat/streams?')]),1)
        w.reset_chat_view();callbacks.pop(0)({'streams':[preview]})
        self.assertNotIn('Olá mundo',w.chat.toPlainText())

    def test_text_stream_survives_old_state_and_does_not_regress_revision(self):
        w,_,preview,callbacks,_=self.text_stream_fixture()
        w.poll_chat_streams();callbacks.pop(0)({'streams':[preview|dict(revision=2,text='Resposta mais nova')]})
        w.refresh();self.assertIn('Resposta mais nova',w.chat.toPlainText())
        w.poll_chat_streams();callbacks.pop(0)({'streams':[preview]})
        self.assertIn('Resposta mais nova',w.chat.toPlainText())
        w.poll_chat_streams();callbacks.pop(0)({'streams':[]})
        self.assertNotIn('Resposta mais nova',w.chat.toPlainText())

    def test_text_stream_does_not_poll_archives_filters_or_during_shutdown(self):
        w,_,_,_,calls=self.text_stream_fixture()
        for field,value in [('chat_read_only',True),('chat_query','busca'),('chat_before',12),('shutdown_pending',True),('closing',True)]:
            old=getattr(w,field);setattr(w,field,value);w.poll_chat_streams();setattr(w,field,old)
        self.assertFalse(any(p.startswith('chat/streams?') for p in calls))

    def test_text_stream_network_failure_never_sends_or_speaks(self):
        w,_,preview,callbacks,calls=self.text_stream_fixture()
        w.poll_chat_streams();callbacks.pop(0)({'streams':[preview]})
        w.poll_chat_streams();callbacks.pop(0)(None)
        self.assertIn('Olá mundo',w.chat.toPlainText())
        self.assertIn('atualização',w.chat.toPlainText())
        self.assertFalse(any(p=='send' or p.startswith('audio/') for p in calls))

    def test_text_stream_growth_above_selection_keeps_same_message_and_visible_line(self):
        w,_,preview,callbacks,_=self.text_stream_fixture();w.show()
        h=preview|dict(text='Linha de Hoshino\n'*18)
        l=preview|dict(id='text-lilith',entity='lilith',text='Linha de Lilith\n'*18+
                       'LILITH_TRECHO_SELECIONADO\n'+'Fim de Lilith\n'*35)
        w.poll_chat_streams();callbacks.pop(0)({'streams':[h,l]});ui.QApplication.processEvents()
        selected=w.chat.document().find('LILITH_TRECHO_SELECIONADO');self.assertTrue(selected.hasSelection())
        w.chat.setTextCursor(selected);ui.QApplication.processEvents()
        top=w.chat.cursorForPosition(w.chat.viewport().rect().topLeft())
        before=(top.block().text(),top.positionInBlock(),w.chat.cursorRect(top).top())
        self.assertLess(w.chat.verticalScrollBar().value(),w.chat.verticalScrollBar().maximum()-8)
        w.poll_chat_streams();callbacks.pop(0)({'streams':[h|dict(text=h['text']+'Linha nova de Hoshino\n'*25,revision=2),l]})
        ui.QApplication.processEvents()
        self.assertEqual(w.chat.textCursor().selectedText(),'LILITH_TRECHO_SELECIONADO')
        top=w.chat.cursorForPosition(w.chat.viewport().rect().topLeft())
        self.assertEqual((top.block().text(),top.positionInBlock(),w.chat.cursorRect(top).top()),before)

    def test_text_stream_polling_resumes_after_shutdown_is_blocked(self):
        w,_,_,_,_=self.text_stream_fixture();w.chat_stream_timer.start()
        with patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.Yes):w.closeEvent(ui.QEvent(ui.QEvent.Close))
        self.assertTrue(w.shutdown_pending);self.assertFalse(w.chat_stream_timer.isActive())
        with patch.object(ui.QMessageBox,'warning'):w.shutdown_failed('fixture: job ainda ativo')
        self.assertFalse(w.shutdown_pending);self.assertTrue(w.chat_stream_timer.isActive())

    def grouped_tools_fixture(self):
        w=self.window;w.tool_config=None
        controls=[dict(key='discord',label='Discord',description='Conversas pelo Discord.',enabled=True),
                  dict(key='read',label='Ler arquivos',description='Ler e listar.',enabled=True,legacy_restrictions=1),
                  dict(key='write',label='Escrever arquivos',description='Criar e editar.',enabled=True)]
        calls=[]
        def request(path,data=None,callback=None,**kwargs):
            calls.append((path,data))
            if path.startswith('control/capabilities?'):value={'entity':w.current_entity(),'revision':'tools-revision','controls':controls,'note':'Memórias não são ferramentas.'}
            elif path=='control/tools':
                for item in controls:
                    if item['key'] in data['capabilities']:item['enabled']=data['capabilities'][item['key']];item['legacy_restrictions']=0
                value={'saved':True}
            else:value=None
            if callback:callback(value)
            return object()
        p=patch.object(w,'request',side_effect=request);p.start();self.addCleanup(p.stop)
        w.load_tools();return calls

    def test_tools_are_flat_capabilities_not_technical_or_memory_entries(self):
        self.grouped_tools_fixture();tree=self.window.tools
        self.assertEqual([tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())],['Discord','Ler arquivos','Escrever arquivos'])
        self.assertTrue(all(tree.topLevelItem(i).childCount()==0 for i in range(tree.topLevelItemCount())))
        self.assertEqual(tree.topLevelItem(1).checkState(0),ui.Qt.PartiallyChecked)

    def test_tools_save_only_changed_group_preserving_untouched_legacy_restriction(self):
        calls=self.grouped_tools_fixture();w=self.window;w.save_tools()
        self.assertFalse(any(path=='control/tools' for path,_ in calls))
        w.tools.topLevelItem(0).setCheckState(0,ui.Qt.Unchecked);w.save_tools()
        posts=[data for path,data in calls if path=='control/tools']
        self.assertEqual(posts,[dict(entity='hoshino',capabilities={'discord':False},revision='tools-revision')])
        self.assertEqual(w.tools.topLevelItem(1).checkState(0),ui.Qt.PartiallyChecked)

    def test_ambient_off_stops_detection_not_speech_and_still_accepts_command_capture(self):
        w=self.window;w.chat_read_only=False;w.start_capture('detection');self.assertIsNotNone(w.capture)
        w.voice_job='fixture-speech-keep'
        w.apply_ambient_policy({'ambient_allowed':{'hoshino':False,'lilith':True,'alistair':True}})
        self.assertIsNone(w.capture);self.assertEqual(w.voice_job,'fixture-speech-keep')
        w.start_capture('detection');self.assertIsNone(w.capture)
        w.voice_job=None;w.start_capture('command');self.assertIsNotNone(w.capture)
        self.assertEqual(w.segmenter.mode,'command');w.stop_capture(False)

    @staticmethod
    def wheel(widget, delta=-120, pixels=False):
        position=QPointF(widget.rect().center())
        event=QWheelEvent(position,QPointF(widget.mapToGlobal(widget.rect().center())),
            QPoint(0,delta) if pixels else QPoint(),QPoint() if pixels else QPoint(0,delta),
            ui.Qt.NoButton,ui.Qt.NoModifier,ui.Qt.ScrollUpdate if pixels else ui.Qt.NoScrollPhase,False)
        ui.QApplication.sendEvent(widget,event)

    def test_wheel_never_changes_focused_options_volume_or_tabs_or_sends_settings(self):
        w=self.window
        controls=[(w.entity,w.entity.currentIndex),(w.models,w.models.currentIndex),
                  (w.context,w.context.value),(w.out_tokens,w.out_tokens.value),
                  (w.threshold,w.threshold.value),(w.silence,w.silence.value),
                  (w.volume,w.volume.value),(w.audio_tabs.tabBar(),w.audio_tabs.currentIndex)]
        self.requests.clear()
        for widget,value in controls:
            before=value();widget.setFocus()
            for pixels in (False,True):
                for delta in (-120,120):self.wheel(widget,delta,pixels)
            self.assertEqual(value(),before,type(widget).__name__)
        self.assertEqual(self.requests,[])

    def test_wheel_over_option_still_scrolls_page_and_scrollbar_itself_works(self):
        area=ui.QScrollArea();area.resize(400,180);area.setWidgetResizable(True)
        self.addCleanup(area.deleteLater)
        page=ui.QWidget();page.setMinimumHeight(1600);layout=ui.QVBoxLayout(page)
        spin=ui.QSpinBox();spin.setRange(0,100);spin.setValue(50);layout.addWidget(spin);layout.addStretch()
        area.setWidget(page);area.show();ui.QApplication.processEvents()
        bar=area.verticalScrollBar();self.assertGreater(bar.maximum(),200)
        bar.setValue(100);self.wheel(spin)
        self.assertGreater(bar.value(),100);self.assertEqual(spin.value(),50)
        bar.setValue(100);self.wheel(bar)
        self.assertGreater(bar.value(),100)

    def test_dynamic_dialog_options_and_spin_editor_are_protected_but_keyboard_and_click_work(self):
        dialog=ui.QDialog(self.window);self.addCleanup(dialog.deleteLater);layout=ui.QVBoxLayout(dialog)
        combo=ui.QComboBox();combo.addItems(['Primeira','Segunda','Terceira']);layout.addWidget(combo)
        spin=ui.QSpinBox();spin.setValue(10);layout.addWidget(spin)
        dialog.show();ui.QApplication.processEvents()
        self.wheel(combo);self.wheel(spin.lineEdit())
        self.assertEqual(combo.currentIndex(),0);self.assertEqual(spin.value(),10)
        QTest.keyClick(combo,ui.Qt.Key_Down);QTest.keyClick(spin,ui.Qt.Key_Up)
        self.assertEqual(combo.currentIndex(),1);self.assertEqual(spin.value(),11)
        QTest.mouseClick(spin,ui.Qt.LeftButton,pos=QPoint(spin.width()-5,spin.height()//4))
        self.assertEqual(spin.value(),12)
        combo.showPopup();ui.QApplication.processEvents()
        QTest.keyClick(combo.view(),ui.Qt.Key_Down);QTest.keyClick(combo.view(),ui.Qt.Key_Return)
        self.assertEqual(combo.currentIndex(),2)

    def test_open_combo_list_can_scroll_without_committing_another_option(self):
        combo=ui.QComboBox(self.window);self.addCleanup(combo.deleteLater)
        combo.setStyleSheet('QComboBox { combobox-popup: 0; }');combo.setMaxVisibleItems(5)
        combo.addItems([f'Escolha {i}' for i in range(100)]);combo.showPopup();ui.QApplication.processEvents()
        view=combo.view();bar=view.verticalScrollBar();before=bar.value()
        self.wheel(view.viewport())
        self.assertGreater(bar.value(),before);self.assertEqual(combo.currentIndex(),0)
        combo.hidePopup()

    def password_form(self,configured=False,post_ok=True,verify=True):
        calls=[];state={'configured':configured,'saved':False,'verify':verify}
        def request(path,data=None,callback=None,**kwargs):
            self.assertEqual(path,'control/password');calls.append((path,data))
            if data is not None:
                if post_ok:
                    state['saved']=True;out={'configured':True}
                else:
                    self.window.notice.setText('Senha incorreta.');out=None
            elif state['saved']:
                out={'configured':state['verify']}
            else:out={'configured':state['configured']}
            if callback:callback(out)
            return object()
        p=patch.object(self.window,'request',side_effect=request);p.start();self.addCleanup(p.stop)
        self.window.set_password();dialog=self.window.password_dialog
        self.addCleanup(lambda:dialog.reject()if self.window.password_dialog is dialog else None)
        return dialog,calls,state

    def test_password_setup_short_input_stays_visible_without_request_or_new_dialog(self):
        dialog,calls,_=self.password_form()
        for field in (dialog.old,dialog.password,dialog.confirm):self.assertEqual(field.echoMode(),ui.QLineEdit.Password)
        dialog.password.setText('abc123');dialog.confirm.setText('abc123');dialog.submit()
        self.assertIn('8 a 200',dialog.error.text());self.assertEqual(len(calls),1)
        self.assertIs(self.window.password_dialog,dialog);self.assertTrue(dialog.save_button.isEnabled())
        dialog.password.setText('x'*201);dialog.confirm.setText('x'*201);dialog.submit()
        self.assertEqual(len(calls),1)

    def test_password_mismatch_and_current_password_required_before_network(self):
        dialog,calls,_=self.password_form(configured=True)
        self.assertFalse(dialog.old_row.isHidden())
        dialog.password.setText('fixture-pass-123');dialog.confirm.setText('different-pass-123');dialog.submit()
        self.assertIn('não coincidem',dialog.error.text())
        dialog.confirm.setText(dialog.password.text());dialog.submit()
        self.assertIn('senha atual',dialog.error.text());self.assertEqual(len(calls),1)

    def test_password_success_requires_post_and_fresh_readback_never_deletes_memory(self):
        dialog,calls,_=self.password_form()
        dialog.password.setText('fixture-pass-123');dialog.confirm.setText('fixture-pass-123');dialog.submit()
        self.assertEqual([data is not None for _,data in calls],[False,True,False])
        self.assertEqual(calls[1][1]['password_confirm'],'fixture-pass-123')
        self.assertEqual(dialog.result(),ui.QDialog.Accepted);self.assertIsNone(self.window.password_dialog)
        self.assertIn('salva e conferida',self.window.memory_status.text());self.assertEqual(dialog.password.text(),'')

    def test_password_server_error_remains_in_same_form_without_automatic_retry(self):
        dialog,calls,_=self.password_form(configured=True,post_ok=False)
        dialog.old.setText('wrong-fixture');dialog.password.setText('fixture-pass-123');dialog.confirm.setText('fixture-pass-123');dialog.submit()
        self.assertIs(self.window.password_dialog,dialog);self.assertIn('Senha incorreta',dialog.error.text())
        self.assertEqual(sum(data is not None for _,data in calls),1)
        self.assertEqual(dialog.password.text(),'fixture-pass-123');self.assertTrue(dialog.save_button.isEnabled())

    def test_password_not_confirmed_offers_only_readback_not_another_save(self):
        dialog,calls,state=self.password_form(verify=False)
        dialog.password.setText('fixture-pass-123');dialog.confirm.setText('fixture-pass-123');dialog.submit()
        self.assertIs(self.window.password_dialog,dialog);self.assertFalse(dialog.save_button.isEnabled())
        self.assertTrue(dialog.check_button.isEnabled());self.assertIn('não foi confirmada',dialog.error.text())
        dialog.submit();dialog.check_requested.emit()
        self.assertEqual(sum(data is not None for _,data in calls),1)
        state['verify']=True;dialog.check_requested.emit()
        self.assertEqual(dialog.result(),ui.QDialog.Accepted)
        self.assertEqual(sum(data is not None for _,data in calls),1)

    def test_password_form_second_click_does_not_create_another_dialog_or_fetch(self):
        dialog,calls,_=self.password_form()
        self.window.set_password();self.assertIs(self.window.password_dialog,dialog);self.assertEqual(len(calls),1)
        dialog.password.setText('fixture-pass-123');dialog.reject()
        self.assertIsNone(self.window.password_dialog);self.assertEqual(dialog.password.text(),'')
        self.assertEqual(sum(data is not None for _,data in calls),0)

    def test_password_initial_read_error_keeps_form_and_requires_explicit_check(self):
        def request(path,data=None,callback=None,**kwargs):
            if callback:callback(None)
            return object()
        with patch.object(self.window,'request',side_effect=request)as transport:
            self.window.set_password();dialog=self.window.password_dialog
            self.assertFalse(dialog.save_button.isEnabled());self.assertTrue(dialog.check_button.isEnabled())
            self.assertIn('Conferir estado',dialog.error.text());self.assertEqual(transport.call_count,1)
            dialog.check_requested.emit();self.assertEqual(transport.call_count,2);dialog.reject()

    def test_password_save_pending_cannot_duplicate_and_cancel_ignores_late_reply(self):
        callbacks=[];calls=[]
        def request(path,data=None,callback=None,**kwargs):
            calls.append(data)
            if data is None:callback({'configured':False})
            else:callbacks.append(callback)
            return object()
        with patch.object(self.window,'request',side_effect=request):
            self.window.set_password();dialog=self.window.password_dialog
            dialog.password.setText('fixture-pass-123');dialog.confirm.setText('fixture-pass-123');dialog.submit();dialog.submit()
            self.assertEqual(len(callbacks),1);self.assertTrue(dialog.busy)
            dialog.reject();callbacks[0]({'configured':True})
            self.assertEqual(len(calls),2);self.assertIsNone(self.window.password_dialog)

    def test_password_setup_is_cancelled_when_backend_generation_changes(self):
        dialog,calls,_=self.password_form()
        self.rotate_endpoint();self.assertTrue(self.window.sync_endpoint())
        self.assertIsNone(self.window.password_dialog);self.assertEqual(dialog.result(),ui.QDialog.Rejected)

    def test_xbox_saved_and_applied_limits_are_visible_without_start(self):
        w=self.window;w.entity.setCurrentIndex(2);self.requests.clear()
        out=dict(settings=dict(destination='xbox',xbox_ip='10.0.0.103',auto_start=True,auto_sync=True,trusted_lan=True),
                 revision='fixture',xbox=dict(state='sleeping',fresh=False),credentials_configured=True,certificate_configured=True,
                 note='Fixture Xbox',model_limits=dict(configured=dict(context=4096,output=512),applied=dict(context=8192,output=768),pending=True,error=None))
        def request(path,data=None,callback=None,**kwargs):
            if callback:callback(out)
        with patch.object(w,'request',side_effect=request):w.load_execution(True)
        self.assertIn('contexto 4096 / saída 512',w.execution_status.text())
        self.assertIn('contexto 8192 / saída 768',w.execution_status.text())
        self.assertIn('aguardando sincronização',w.execution_status.text())
        self.assertFalse(any(p=='start'or p.endswith('/check')for p,_,_ in self.requests))

    def test_context_and_output_use_nearest_valid_value_typed(self):
        # 06/11 (pedido humano): o número digitado vira o valor válido mais próximo ao terminar a edição.
        w=self.window;w.model_config=dict(output_max=8192);w.context.setRange(2048,32768);w.context.setSingleStep(1024)
        w.context.setValue(16384);w.out_tokens.setValue(4096)
        for typed,used in (('40000',32768),('20000',20480),('1000',2048),('24k',24576),('24.576',24576)):
            w.context.lineEdit().setText(typed);w.context.interpretText()
            self.assertEqual(w.context.value(),used,typed)
        self.assertIn('1000 não é válido aqui; ajustado para 2048',w.notice.text())
        w.context.setValue(32768);w.out_tokens.lineEdit().setText('10000');w.out_tokens.interpretText()
        self.assertEqual(w.out_tokens.value(),8192);self.assertIn('Limite de saída: 10000',w.notice.text())
        w.out_tokens.lineEdit().setText('1000');w.out_tokens.interpretText();self.assertEqual(w.out_tokens.value(),1024)
        # Digitar 24576 não passa por 2457 cortando o limite de saída no meio do caminho.
        w.out_tokens.setValue(4096);w.context.setValue(16384);w.context.lineEdit().selectAll()
        QTest.keyClicks(w.context.lineEdit(),'24576');self.assertEqual(w.out_tokens.value(),4096)
        QTest.keyClick(w.context.lineEdit(),ui.Qt.Key_Return)
        self.assertEqual((w.context.value(),w.out_tokens.value()),(24576,4096))
        # Texto ainda no campo ao clicar em aplicar vale o valor mais próximo, não o anterior.
        w.model_config=dict(output_max=8192,revision='r',gpu_layers=None);w.context.lineEdit().setText('30000');self.requests.clear()
        w.save_model();sent=next(d for p,d,_ in self.requests if p=='control/models');self.assertEqual(sent['context'],29696)
    def test_gpu_alert_banner_notifies_once_escalates_for_message_and_opens_models(self):
        w=self.window;calls=[]
        alert=dict(entity='lilith',key='lilith:1',title='Lilith está sem VRAM',text='faltam 182 MiB',message_waiting=False)
        with patch.object(FakeProcess,'startDetached',staticmethod(lambda program,args:calls.append((program,args))),create=True),\
             patch.object(ui.QApplication,'alert'):
            w.render_gpu_alerts([alert]);w.render_gpu_alerts([alert])
            self.assertFalse(w.gpu_alert_box.isHidden());self.assertIn('Lilith está sem VRAM',w.gpu_alert_text.text())
            self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'notify-send');self.assertIn('normal',calls[0][1])
            w.render_gpu_alerts([dict(alert,message_waiting=True)])
            self.assertEqual(len(calls),2);self.assertIn('critical',calls[1][1])
            w.open_gpu_alert_models()
            self.assertEqual((w.current_entity(),ui.PAGES[w.nav.currentRow()]),('lilith','Modelos'))
            w.dismiss_gpu_alert();self.assertTrue(w.gpu_alert_box.isHidden())
            w.render_gpu_alerts([dict(alert,message_waiting=True)]);self.assertTrue(w.gpu_alert_box.isHidden())
            w.render_gpu_alerts([dict(alert,key='lilith:2')]);self.assertFalse(w.gpu_alert_box.isHidden());self.assertEqual(len(calls),3)
            w.render_gpu_alerts([]);self.assertTrue(w.gpu_alert_box.isHidden())
        # Poller: um pedido por vez e só conectado.
        self.requests.clear();w.connected=False;w.poll_gpu_alerts();self.assertFalse(self.requests)
        w.connected=True;w.poll_gpu_alerts();self.assertEqual([p for p,_,_ in self.requests],['control/gpu-alerts'])
        self.assertIsNone(w.gpu_alert_sent)
        self.requests.clear();w.gpu_alert_sent=time.monotonic();w.poll_gpu_alerts();self.assertFalse(self.requests)
        # Backend antigo sem a rota (404): o poller fica mudo, sem cobrir o aviso da Central a cada 3 s.
        worker=type('Thread',(),{})();worker.done=Signal();worker.finished=Signal();worker.start=lambda:None
        self.patch.stop()
        with patch.object(ui,'Rpc',return_value=worker):
            w.gpu_alert_sent=None;w.notice.setText('aviso do usuário');w.poll_gpu_alerts()
        self.patch.start();worker.done.emit({'ok':False,'error':'não encontrado','status':404})
        self.assertEqual(w.notice.text(),'aviso do usuário');self.assertIsNone(w.gpu_alert_sent);w.workers.clear()
    def test_every_copy_is_sent_to_shared_area_without_button(self):
        # 06/11 (pedido humano): Ctrl+C em qualquer app vai sozinho para a área compartilhada.
        w=self.window;clipboard=ui.QApplication.clipboard();self.addCleanup(clipboard.clear)
        w.connected=True;w.ui_config={'settings':{}};self.requests.clear()
        sent=lambda:[(p,d) for p,d,_ in self.requests if p.startswith('control/clipboard')]
        clipboard.setText('https://www.youtube.com/@GamesEduUu');w.capture_clipboard()
        self.assertEqual(sent(),[('control/clipboard?kind=texto','https://www.youtube.com/@GamesEduUu'.encode())])
        w.capture_clipboard();self.assertEqual(len(sent()),1)  # a mesma cópia não sai duas vezes
        from PyQt5.QtCore import QMimeData
        secret=QMimeData();secret.setText('senha-do-banco');secret.setData('x-kde-passwordManagerHint',b'secret')
        clipboard.setMimeData(secret);w.capture_clipboard();self.assertEqual(len(sent()),1)
        image=QImage(4,3,QImage.Format_RGB32);image.fill(0x336699);clipboard.setImage(image);w.capture_clipboard()
        path,payload=sent()[-1];self.assertEqual(path,'control/clipboard?kind=imagem');self.assertTrue(payload.startswith(b'\x89PNG'))
        w.ui_config={'settings':{'clipboard_auto':False}};clipboard.setText('outra');w.capture_clipboard()
        self.assertEqual(len(sent()),2)
        self.assertTrue(hasattr(w,'clipboard_timer') and w.clipboard_timer.isSingleShot())
    def test_pc2_panel_points_to_lan_and_closing_keeps_pc1_running(self):
        # 06/11 (pedido humano): no PC2 o central.url aponta para o IP privado do PC1.
        self.endpoint_path.write_text('http://10.0.0.102:8770/#codigo-de-pareamento')
        self.assertEqual(ui.endpoint(Path(sys.argv_root)),('http://10.0.0.102:8770','codigo-de-pareamento'))
        for bad in ('http://8.8.8.8:8770/#x','http://exemplo.com:8770/#x','https://10.0.0.102:8770/#x','http://10.0.0.102:8770/'):
            self.endpoint_path.write_text(bad)
            with self.assertRaises(ValueError,msg=bad):ui.endpoint(Path(sys.argv_root))
        w=self.window;self.assertFalse(w.remote_panel())
        w.base='http://10.0.0.102:8770';self.assertTrue(w.remote_panel())
        with patch.object(ui.QMessageBox,'question',side_effect=AssertionError('não pergunta encerrar o PC1')),\
             patch.object(w,'finish_window_only') as only:
            w.closeEvent(QCloseEvent())
        only.assert_called_once();self.assertFalse(any(p=='control/shutdown' for p,_,_ in self.requests))
        # A seção de rede só aparece no PC1 (o backend do PC1 recusa a leitura vinda do PC2).
        w.render_lan(None);self.assertTrue(w.lan_box.isHidden())
        w.render_lan(dict(enabled=True,port=8770,addresses=['10.0.0.102'],code='abc123',active=False))
        self.assertFalse(w.lan_box.isHidden());self.assertIn('instalar_painel_pc2.sh 10.0.0.102 abc123',w.lan_info.text())
        self.assertIn('10.0.0.0/24',w.lan_info.text())
        clipboard=ui.QApplication.clipboard();self.addCleanup(clipboard.clear)
        w.connected=True;w.ui_config={'settings':{}};self.requests.clear();w.copy_lan_command();w.capture_clipboard()
        self.assertFalse([p for p,_,_ in self.requests if p.startswith('control/clipboard')])  # o código não vai para a área
    def test_vram_margin_section_previews_usable_memory_and_saves_choice(self):
        w=self.window
        w.render_vram(None);self.assertTrue(w.vram_box.isHidden())
        w.render_vram(dict(margin_mib=512,options=[128,256,384,512,768,1024],minimum_mib=128,default_mib=768,
                           total_mib=8176,used_mib=99,usable_mib=7664,revision='rev-gpu'))
        self.assertFalse(w.vram_box.isHidden());self.assertEqual(w.vram_margin.currentData(),512)
        self.assertIn('até 7.664 MiB no total',w.vram_info.text())
        w.vram_margin.setCurrentIndex(w.vram_margin.findData(128))
        self.assertIn('até 8.048 MiB no total',w.vram_info.text());self.assertIn('desktop leve',w.vram_info.text())
        self.assertIn('piso',w.vram_margin.currentText())
        self.requests.clear();w.save_vram()
        self.assertEqual([d for p,d,_ in self.requests if p=='control/vram'],[{'margin_mib':128,'revision':'rev-gpu'}])
    def test_pc2_panel_runs_allowed_commands_and_sends_senses_only_when_remote(self):
        # 06/11 (pedido humano): no PC2 o painel é o corpo remoto; no PC1 nada disso roda.
        from PyQt5.QtCore import QProcess as RealProcess
        w=self.window;w.connected=True;self.requests.clear()
        w.pc2_poll_commands();w.pc2_collect_senses();self.assertFalse(self.requests)  # painel local: não faz nada
        w.base='http://10.0.0.102:8770';self.assertTrue(w.remote_panel())
        local=w.pc2_local_path();self.addCleanup(lambda:local.unlink(missing_ok=True))
        w.pc2_allow.setChecked(False);w.pc2_poll_commands()
        self.assertEqual([d for p,d,_ in self.requests if p=='control/pc2/proximo'],[{'permitido':False,'permitido_tela':False}])
        w.pc2_allow.setChecked(True);self.assertEqual(json.loads(local.read_text()),{'comandos':True})
        replies={'control/pc2/proximo':{'comando':{'id':'pc2-abc','comando':'echo pc2-ok; exit 3','timeout':10,'entidade':'lilith'}}}
        fake=ui.Central.request
        def request(window,path,data=None,callback=None,**kw):
            self.requests.append((path,data,kw))
            if callback:callback(replies.pop(path,{}))
            return object()
        self.requests.clear()
        with patch.object(ui.Central,'request',request),patch.object(ui,'QProcess',RealProcess):
            w.pc2_poll_commands()
            for _ in range(50):
                if any(p=='control/pc2/resultado' for p,_,_ in self.requests):break
                QTest.qWait(100)
            result=next(d for p,d,_ in self.requests if p=='control/pc2/resultado')
            self.assertEqual((result['id'],result['codigo'],result['saida']),('pc2-abc',3,'pc2-ok\n'))
            self.assertIsNone(w.pc2_command);self.assertIn('saída 3',w.pc2_status.text())
            w.pc2_collect_senses()
            for _ in range(80):
                if any(p=='control/pc2/sentidos' for p,_,_ in self.requests):break
                QTest.qWait(100)
            senses=next(d for p,d,_ in self.requests if p=='control/pc2/sentidos')
            self.assertTrue({'janela_ativa','janelas','ociosidade_x11'}<=set(senses['estado']))
            # Pedido de tela: só com a permissão de tela; o print vai em PNG para o PC1.
            replies['control/pc2/proximo']={'comando':{'id':'pc2-tela1','comando':'tela','timeout':20,'entidade':'hoshino','tipo':'tela'}}
            w.pc2_screen.setChecked(False);self.requests.clear();w.pc2_poll_commands()
            self.assertFalse([p for p,_,_ in self.requests if p.startswith('control/pc2/tela')])
            replies['control/pc2/proximo']={'comando':{'id':'pc2-tela2','comando':'tela','timeout':20,'entidade':'hoshino','tipo':'tela'}}
            w.pc2_screen.setChecked(True);self.requests.clear();w.pc2_poll_commands()
            sent=[(p,d) for p,d,_ in self.requests if p.startswith('control/pc2/tela') or p=='control/pc2/resultado']
            self.assertEqual(len(sent),1)
            path,data=sent[0]
            if path.startswith('control/pc2/tela'):
                self.assertEqual(path,'control/pc2/tela?id=pc2-tela2');self.assertTrue(data.startswith(b'\x89PNG'))
            else:
                self.assertEqual(data['id'],'pc2-tela2')  # plataforma sem tela: falha relatada, nunca silêncio
        self.assertEqual(json.loads(local.read_text()),{'comandos':True,'tela':True})
        w.base='http://127.0.0.1:8769'
    def test_chat_shows_source_links_and_attached_images(self):
        # 06/11 (pedido humano): pesquisa profunda com links clicáveis e imagens das fontes no chat.
        from PyQt5.QtCore import QUrl, QBuffer as Buf, QIODevice as IO
        w=self.window;img=QImage(40,30,QImage.Format_RGB32);img.fill(0x3366aa)
        b=Buf();b.open(IO.WriteOnly);img.save(b,'JPG');jpeg=bytes(b.data());calls=[]
        w.chat.fetch=lambda ident:(calls.append(ident),jpeg)[1]
        msg={'id':'m1','sender':'lilith','recipient':'usuario','text':'Fonte [1] https://pt.wikipedia.org/wiki/The_Boxer.\n[[imagem:0123456789ab]] <script>x</script>','metadata':{}}
        rendered,_=ui.chat_bubbles([msg],'lilith')
        self.assertIn('href="https://pt.wikipedia.org/wiki/The_Boxer"',rendered);self.assertIn('src="anexo:0123456789ab"',rendered)
        self.assertNotIn('<script>',rendered)
        loaded=w.chat.loadResource(2,QUrl('anexo:0123456789ab'));w.chat.loadResource(2,QUrl('anexo:0123456789ab'))
        self.assertFalse(loaded.isNull());self.assertEqual((loaded.width(),calls),(40,['0123456789ab']))  # busca uma vez só
        self.assertTrue(w.chat.loadResource(2,QUrl('anexo:../../x')).isNull())
        opened=[]
        with patch.object(ui.QDesktopServices,'openUrl',side_effect=lambda u:opened.append(u.toString())):
            w.review_interaction(QUrl('https://pt.wikipedia.org/wiki/The_Boxer'))
        self.assertEqual(opened,['https://pt.wikipedia.org/wiki/The_Boxer'])
    def test_context_form_reserves_input_and_matches_xbox_step(self):
        w=self.window;w.model_config=dict(output_max=7680)
        w.context.setSingleStep(256);w.context.setValue(4096);w.out_tokens.setValue(3000)
        self.assertEqual(w.out_tokens.maximum(),3584);self.assertEqual(w.context.singleStep(),256)
        w.context.setValue(2048);self.assertEqual(w.out_tokens.maximum(),1536)
        self.assertEqual(w.out_tokens.value(),1536)

    def test_alistair_executor_panel_password_hidden_and_no_auto_start(self):
        w=self.window;w.entity.setCurrentIndex(2);self.requests.clear()
        self.assertEqual(w.execution_password.echoMode(),ui.QLineEdit.Password)
        self.assertEqual([w.execution_destination.itemData(i)for i in range(w.execution_destination.count())],['local','pc2','xbox'])
        w.execution_destination.setCurrentIndex(2)
        self.assertFalse(any(p=='start' or p.endswith('/check')for p,_,_ in self.requests))

    def test_alistair_executor_save_uses_existing_api_and_clears_password(self):
        w=self.window;w.entity.setCurrentIndex(2);self.requests.clear()
        w.execution_config={'revision':'fixture'};w.execution_destination.setCurrentIndex(2)
        w.execution_ip.setText('10.0.0.103');w.execution_lan.setChecked(True)
        w.execution_user.setText('fixture-user');w.execution_password.setText('fixture-secret')
        w.save_execution()
        payload=next(d for p,d,_ in self.requests if p=='control/alistair/execution')
        self.assertEqual(payload['settings']['destination'],'xbox');self.assertEqual(payload['revision'],'fixture')
        self.assertEqual(w.execution_password.text(),'');self.assertFalse(any(p=='start'for p,_,_ in self.requests))

    def test_hotkey_diagnostic_recognizes_press_release_without_opening_microphone(self):
        w=self.window;w.hotkey_process=FakeProcess();w.mic_settings['hotkey']='Alt+W';w.test_hotkey()
        w.global_hotkey_event('press');w.global_hotkey_event('release')
        self.assertIsNone(w.capture);self.assertFalse(self.requests);self.assertIn('reconhecido',w.hotkey_status.text())

    def test_knowledge_cards_escape_details_and_clear_when_entity_changes(self):
        panel=self.window.knowledge_panel
        card={'id':'x','entity':'hoshino','title':'<script>Nome</script>','kind':'concept',
              'entries':[{'text':'<b>Informação</b>','type':'hipotese','confidence':None,'source':'conversa'}]}
        panel.render({'entity':'hoshino','items':[card],'total':1,'note':'Somente consulta'})
        self.assertEqual(len(panel.cards),1);self.assertEqual(panel.grid.count(),1)
        self.window.entity.setCurrentIndex(1);self.assertEqual(panel.cards,[])
        self.assertEqual(panel.page,0)

    def memory_unlock_fixture(self):
        w=self.window;w.nav.setCurrentRow(ui.PAGES.index('Memórias'));requests=[];deferred=[]
        card=dict(id='concept:one',entity='hoshino',title='Fixture privada',kind='concept',importance='diamante',card_revision='version-one',entries=[dict(table='memories',record_id='one',revision='row-one',text='Conteúdo privado fixture',type='concept',fields={'content':'Conteúdo privado fixture'})])
        def request(path,data=None,callback=None,**kwargs):
            requests.append((path,data))
            if path=='control/knowledge/unlock':out=dict(unlocked=True,access_token='fixture-memory-access-long-enough-00001',expires_in=300)
            elif path.startswith('control/knowledge?'):out=dict(entity='hoshino',items=[card],total=1)
            elif path=='control/knowledge/lock':out=dict(locked=True)
            else:out={}
            if callback:callback(out)
            return object()
        p=patch.object(w,'request',side_effect=request);p.start();self.addCleanup(p.stop)
        with patch.object(ui.QInputDialog,'getText',return_value=('fixture-password',True)) as ask:w.unlock_memories()
        self.assertEqual(ask.call_args.args[3],ui.QLineEdit.Password)
        return requests,card

    def test_memories_tab_renamed_locked_by_default_and_no_background_read(self):
        w=self.window;self.assertIn('Memória do chat',ui.PAGES);self.assertIn('Memórias',ui.PAGES);self.assertNotIn('Conhecimento',ui.PAGES)
        w.nav.setCurrentRow(ui.PAGES.index('Memórias'));w.load_knowledge()
        self.assertEqual(w.memory_gate.currentIndex(),0);self.assertFalse(w.knowledge_panel.cards)
        self.assertFalse(any(p.startswith('control/knowledge?') for p,_,_ in self.requests))

    def test_memory_unlock_then_leave_revokes_and_clears_cards(self):
        requests,card=self.memory_unlock_fixture();w=self.window
        self.assertTrue(w.memories_authorized());self.assertEqual(w.memory_gate.currentIndex(),1);self.assertEqual(w.knowledge_panel.cards[0]['title'],card['title'])
        w.nav.setCurrentRow(ui.PAGES.index('Conversa'))
        self.assertFalse(w.memory_access);self.assertEqual(w.memory_gate.currentIndex(),0);self.assertEqual(w.knowledge_panel.cards,[])
        self.assertIn(('control/knowledge/lock',{'entity':'hoshino'}),requests);self.assertFalse(w.memory_timer.isActive())

    def test_memory_unlock_switch_entity_and_expiration_do_not_reuse_access(self):
        requests,_=self.memory_unlock_fixture();w=self.window;w.entity.setCurrentIndex(1)
        self.assertFalse(w.memory_access);self.assertEqual(w.knowledge_panel.cards,[])
        self.assertIn(('control/knowledge/lock',{'entity':'hoshino'}),requests)
        w.entity.setCurrentIndex(0);w.memory_access='fixture-memory-access-long-enough-00001';w.memory_entity='hoshino';w.memory_until=ui.time.monotonic()+300
        w.memory_timer.timeout.emit();self.assertFalse(w.memory_access);self.assertFalse(w.knowledge_panel.cards)

    def test_late_memory_read_cannot_repopulate_after_lock(self):
        _,card=self.memory_unlock_fixture();w=self.window;callbacks=[]
        with patch.object(w,'request',side_effect=lambda p,data=None,callback=None,**kw:callbacks.append(callback) if p.startswith('control/knowledge?') else object()):
            w.load_knowledge();w.lock_memories(revoke=False);callbacks[0](dict(entity='hoshino',items=[card],total=1))
        self.assertEqual(w.knowledge_panel.cards,[]);self.assertEqual(w.memory_gate.currentIndex(),0)

    def test_card_hover_and_reduced_motion_and_four_levels(self):
        from native_panels import MemoryCard,TIERS
        self.assertEqual([key for _,key,_ in TIERS],['ferro','ouro','diamante','platina'])
        card=MemoryCard('Fixture','platina',lambda:True);card.highlight(True);QTest.qWait(200)
        self.assertGreater(card.hoverProgress,.9);card.highlight(False);QTest.qWait(200);self.assertLess(card.hoverProgress,.1)
        reduced=MemoryCard('Fixture','ouro',lambda:False);reduced.highlight(True)
        self.assertEqual(reduced.hoverProgress,0);self.assertEqual(reduced.hover_animation.state(),0)
        card.deleteLater();reduced.deleteLater()

    def test_memory_card_layout_four_tiers_fixture(self):
        from native_panels import MemoryCard,TIERS
        w=self.window;w.nav.setCurrentRow(ui.PAGES.index('Memórias'))
        w.memory_access='fixture-visual-access-only-000000001';w.memory_entity='hoshino';w.memory_until=ui.time.monotonic()+300
        w.memory_gate.setCurrentIndex(1)
        cards=[dict(id='concept:'+key,title=label+' · cartão de teste',entity='hoshino',kind='concept',importance=key,card_revision=key+'-revision',entries=[dict(table='memories',record_id=key,revision='row',text='Informação fictícia para validar a apresentação; não é memória de uma pessoa real.',type='concept',fields={'content':'Fixture'})]) for label,key,_ in TIERS]
        w.knowledge_panel.render(dict(entity='hoshino',items=cards,total=4,note='SIMULAÇÃO OFFLINE · entidades e modelos não foram iniciados.'))
        w.reduced_motion.setChecked(True);w.page_animation.stop();w.page_effect.setEnabled(False)
        w.resize(1440,1080);w.show();QTest.qWait(220)
        widgets=w.knowledge_panel.findChildren(MemoryCard)
        self.assertEqual([c.property('importance') for c in widgets],['ferro','ouro','diamante','platina'])
        qa=os.environ.get('HOSHINO_NATIVE_QA_DIR')
        if qa:
            path=Path(qa).resolve();self.assertTrue(path.is_relative_to('/tmp'));path.mkdir(parents=True,exist_ok=True)
            self.assertTrue(w.grab().save(str(path/'memorias-cartas-fixture.png')))

    def test_closing_rejects_old_receipt_and_never_treats_missing_backend_as_success(self):
        w=self.window;w.shutdown_pending=True;w.shutdown_generation=ui.hashlib.sha256(w.token.encode()).hexdigest();w.shutdown_requested_at=time.time()
        receipt=w.root/'compartilhado/runtime/launcher/shutdown-result.json'
        receipt.write_text(json.dumps({'generation':'old','status':'complete','at':time.time(),'pid':999999999}))
        with patch.object(w,'finish_window_only') as finished:
            w.poll_shutdown();finished.assert_not_called()
            receipt.write_text(json.dumps({'generation':w.shutdown_generation,'status':'complete','at':time.time(),'pid':999999999,'process_stamp':'12345'}))
            w.poll_shutdown();finished.assert_called_once()
        receipt.unlink()

    def test_blocked_shutdown_keeps_window_and_does_not_retry(self):
        w=self.window;w.shutdown_pending=True;w.shutdown_generation=ui.hashlib.sha256(w.token.encode()).hexdigest();w.shutdown_requested_at=time.time()
        receipt=w.root/'compartilhado/runtime/launcher/shutdown-result.json'
        receipt.write_text(json.dumps({'generation':w.shutdown_generation,'status':'blocked','at':time.time()}))
        with patch.object(ui.QMessageBox,'warning') as warning:w.poll_shutdown()
        self.assertFalse(w.closing);self.assertFalse(w.shutdown_pending);warning.assert_called_once()
        self.assertFalse(any(p=='control/shutdown' for p,_,_ in self.requests));receipt.unlink()

    def test_delete_all_button_shows_verified_result_and_scopes_target(self):
        w=self.window;calls=[]
        def request(path,data=None,callback=None,**kwargs):
            calls.append((path,data));out={}
            if path=='control/password':out={'configured':True}
            elif path.startswith('state?'):out={'presence':[{'entity_id':'hoshino','status':'sleeping'}]}
            elif path=='control/memory/preview':out={'scope':'experience-v1','counts':{'memories':2},'fingerprint':'fp','note':'Preserva identidade.'}
            elif path=='control/memory/delete':out={'verified':True,'deleted':2,'backup':'/fixture/backup','chat_cleared':True}
            elif path.startswith('control/memory?'):out={'items':[]}
            if callback:callback(out)
            return object()
        with patch.object(w,'request',side_effect=request),patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.Yes),patch.object(ui.QInputDialog,'getText',return_value=('test-password',True)):
            w.erase_memory(True)
        sent=next(data for path,data in calls if path=='control/memory/delete')
        self.assertEqual(sent['entity'],'hoshino');self.assertTrue(sent['all']);self.assertEqual(sent['fingerprint'],'fp');self.assertEqual(sent['scope'],'experience-v1')
        self.assertIn('VERIFICADA',w.memory_status.text());self.assertFalse(w.memory_delete_busy)

    def test_delete_all_error_is_visible_not_reported_as_success(self):
        w=self.window
        def request(path,data=None,callback=None,**kwargs):
            out={'configured':True} if path=='control/password' else {'presence':[{'entity_id':'hoshino','status':'sleeping'}]} if path.startswith('state?') else {'counts':{},'fingerprint':'fp'}
            if path=='control/memory/delete':w.notice.setText('Senha incorreta.');out=None
            if callback:callback(out)
            return object()
        with patch.object(w,'request',side_effect=request),patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.Yes),patch.object(ui.QInputDialog,'getText',return_value=('test',True)),patch.object(ui.QMessageBox,'warning') as warning:
            w.erase_memory(True)
        warning.assert_called_once();self.assertIn('Senha incorreta',w.memory_status.text());self.assertFalse(w.memory_delete_busy)

    def test_live_asr_autosends_only_spoken_text_without_consuming_typed_draft(self):
        w=self.window;w.mic_settings['auto_send']=True;w.draft.setPlainText('Rascunho digitado, não enviar')
        w.asr_jobs['spoken']={'entity':'hoshino','test':False,'session_id':w.chat_session['id']}
        w.asr_result('spoken',{'status':'done','result':{'text':'Olá, bom dia.'}})
        sent=[d for p,d,_ in self.requests if p=='send']
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['text'],'Olá, bom dia.')
        self.assertTrue(sent[0]['automatic_asr']);self.assertEqual(w.draft.toPlainText(),'Rascunho digitado, não enviar')
        w.asr_result('spoken',{'status':'done','result':{'text':'Olá, bom dia.'}})
        self.assertEqual(len([p for p,_,_ in self.requests if p=='send']),1)

    def test_late_asr_autosends_to_capture_entity_not_new_selection(self):
        w=self.window;w.mic_settings['auto_send']=True;session=w.chat_session['id']
        w.asr_jobs['late']={'entity':'hoshino','test':False,'session_id':session}
        w.entity.setCurrentIndex(1);w.asr_result('late',{'status':'done','result':{'text':'Mensagem falada.'}})
        sent=[d for p,d,_ in self.requests if p=='send']
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['entity'],'hoshino')
        self.assertEqual(sent[0]['conversation_session_id'],session);self.assertEqual(w.draft.toPlainText(),'')

    def test_close_cancel_does_not_stop_capture_or_backend(self):
        w=self.window;w.start_capture('command');capture=w.capture
        event=type('Event',(),{'ignore':lambda _:None})()
        with patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.No):w.closeEvent(event)
        self.assertIs(w.capture,capture);self.assertFalse(w.closing)
        self.assertFalse(any(p=='control/shutdown' for p,_,_ in self.requests))

    def test_close_confirm_requests_shutdown_once_and_keeps_window_until_verified(self):
        w=self.window;event=type('Event',(),{'ignore':lambda _:None})()
        with patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.Yes):
            w.closeEvent(event);w.closeEvent(event)
        self.assertEqual(len([p for p,_,_ in self.requests if p=='control/shutdown']),1)
        self.assertTrue(w.shutdown_pending);self.assertFalse(w.closing)

    def test_global_hotkey_is_configurable_but_closed_by_default(self):
        w=self.window
        self.assertFalse(w.hotkey_enabled.isChecked());self.assertIsNone(w.hotkey_process)
        w.hotkey_edit.setKeySequence(ui.QKeySequence('F8'));w.hotkey_enabled.setChecked(True)
        w.save_mic()
        data=next(d for p,d,_ in self.requests if p=='control/microphone')
        self.assertEqual(data['settings']['hotkey'],'F8');self.assertTrue(data['settings']['hotkey_enabled'])
        self.assertIsNone(w.capture)

    def test_microphone_hotkey_does_not_type_in_chat_or_erase_the_draft(self):
        w=self.window;w.nav.setCurrentRow(ui.PAGES.index('Conversa'))
        w.mic_settings.update(hotkey_enabled=True,hotkey='Alt+W');w.configure_hotkey()
        w.draft.setPlainText('rascunho preservado');w.draft.selectAll()
        QTest.keyClick(w.draft,ui.Qt.Key_W,ui.Qt.AltModifier)
        self.assertEqual(w.draft.toPlainText(),'rascunho preservado')
        self.assertIsNone(w.capture)  # o listener global continua sendo o único dono do PTT
        self.assertFalse(any(path=='send' for path,_,_ in self.requests))
        QTest.keyClick(w.draft,ui.Qt.Key_W)
        self.assertEqual(w.draft.toPlainText(),'w')

    def test_microphone_hotkey_consumes_repeat_until_key_release_not_the_next_w(self):
        w=self.window;w.mic_settings.update(hotkey_enabled=True,hotkey='Alt+W');w.configure_hotkey()
        w.draft.setPlainText('')
        for kind,mods,repeat in ((ui.QEvent.KeyPress,ui.Qt.AltModifier,False),
                                 (ui.QEvent.KeyPress,ui.Qt.NoModifier,True),
                                 (ui.QEvent.KeyRelease,ui.Qt.NoModifier,False)):
            ui.QApplication.sendEvent(w.draft,QKeyEvent(kind,ui.Qt.Key_W,mods,'w',repeat))
        self.assertEqual(w.draft.toPlainText(),'')
        QTest.keyClick(w.draft,ui.Qt.Key_W)
        self.assertEqual(w.draft.toPlainText(),'w')

    def test_microphone_shortcut_does_not_capture_other_modifiers_or_disabled_keys(self):
        w=self.window;w.mic_settings.update(hotkey_enabled=True,hotkey='Ctrl+Alt+M');w.configure_hotkey()
        w.draft.setPlainText('')
        QTest.keyClick(w.draft,ui.Qt.Key_W,ui.Qt.AltModifier)
        self.assertEqual(w.draft.toPlainText(),'w')
        w.mic_settings.update(hotkey_enabled=False,hotkey='Alt+W');w.configure_hotkey()
        QTest.keyClick(w.draft,ui.Qt.Key_W,ui.Qt.AltModifier)
        self.assertEqual(w.draft.toPlainText(),'ww')

    def test_microphone_repeat_after_focus_roundtrip_preserves_draft_without_sticky_keys(self):
        w=self.window;w.mic_settings.update(hotkey_enabled=True,hotkey='Alt+W');w.configure_hotkey()
        w.draft.setPlainText('rascunho preservado');w.draft.selectAll()
        ui.QApplication.sendEvent(w.draft,QKeyEvent(ui.QEvent.KeyPress,ui.Qt.Key_W,ui.Qt.AltModifier,'w'))
        ui.QApplication.sendEvent(w.draft,QFocusEvent(ui.QEvent.FocusOut))
        ui.QApplication.sendEvent(w.draft,QFocusEvent(ui.QEvent.FocusIn))
        ui.QApplication.sendEvent(w.draft,QKeyEvent(ui.QEvent.KeyPress,ui.Qt.Key_W,ui.Qt.NoModifier,'w',True))
        self.assertEqual(w.draft.toPlainText(),'rascunho preservado')
        # Se a liberação ocorreu em outra janela, uma NOVA tecla W continua normal.
        QTest.keyClick(w.draft,ui.Qt.Key_W)
        self.assertEqual(w.draft.toPlainText(),'w')

    def test_global_events_lock_capture_recipient_and_ignore_foreign_release(self):
        w=self.window;w.global_hotkey_event('press');own=w.capture
        self.assertIsNotNone(own);self.assertEqual(w.capture_entity,'hoshino')
        w.entity.setCurrentIndex(1);w.global_hotkey_event('release')
        self.assertIsNone(w.capture);self.assertEqual(w.capture_entity,'hoshino')
        w.start_capture('command');local=w.capture;w.global_hotkey_event('release')
        self.assertIs(w.capture,local)

    def test_stream_and_final_are_not_synthesized_twice_even_after_failure(self):
        w=self.window;w.auto_voice.setChecked(True)
        stream={'id':'stream-once','created_at':1}
        w.handle_new_voice('hoshino',[],[stream]);w.finish_voice()
        reply={'id':'reply-once','metadata':{'speech_streams':['stream-once']}}
        w.handle_new_voice('hoshino',[reply],[])
        self.assertEqual([p for p,_,_ in self.requests if p in ('audio/stream','audio/synthesize')],['audio/stream'])

    def test_enter_sends_shift_enter_newline_and_archive_stays_readonly(self):
        w=self.window;w.draft.setPlainText('Olá');QTest.keyClick(w.draft,ui.Qt.Key_Return)
        self.assertEqual(len([p for p,_,_ in self.requests if p=='send']),1)
        self.requests.clear();w.draft.setPlainText('Outra linha');QTest.keyClick(w.draft,ui.Qt.Key_Return,ui.Qt.ShiftModifier)
        self.assertIn('\n',w.draft.toPlainText());self.assertFalse(any(p=='send' for p,_,_ in self.requests))
        w.chat_read_only=True;w.chat_controls();QTest.keyClick(w.draft,ui.Qt.Key_Return)
        self.assertFalse(any(p=='send' for p,_,_ in self.requests))

    def test_busy_voice_does_not_consume_new_reply_and_never_retries_uncertain(self):
        w=self.window;w.auto_voice.setChecked(True)
        reply={'id':'fresh-reply','sender':'hoshino','recipient':'usuario','text':'Olá','metadata':{}}
        w.voice_job='busy';w.handle_new_voice('hoshino',[reply],[])
        self.assertNotIn('fresh-reply',w.voice_seen)
        self.defer=True;w.finish_voice();w.handle_new_voice('hoshino',[reply],[])
        self.assertEqual(len([p for p,_,_ in self.requests if p=='audio/synthesize']),1)
        self.deferred.pop()(None);w.handle_new_voice('hoshino',[reply],[])
        self.assertEqual(len([p for p,_,_ in self.requests if p=='audio/synthesize']),1)

    def test_two_replies_are_read_once_in_order_and_disabled_audio_has_no_backlog(self):
        w=self.window;w.auto_voice.setChecked(True)
        replies=[{'id':str(i),'sender':'hoshino','recipient':'usuario','metadata':{}} for i in (1,2)]
        w.handle_new_voice('hoshino',replies,[]);w.handle_new_voice('hoshino',replies,[])
        self.assertEqual([d['message_id'] for p,d,_ in self.requests if p=='audio/synthesize'],['1'])
        w.finish_voice();w.handle_new_voice('hoshino',replies,[])
        self.assertEqual([d['message_id'] for p,d,_ in self.requests if p=='audio/synthesize'],['1','2'])
        w.auto_voice.setChecked(False);w.handle_new_voice('hoshino',[{'id':'disabled','metadata':{}}],[])
        w.auto_voice.setChecked(True);w.finish_voice();w.handle_new_voice('hoshino',[{'id':'disabled','metadata':{}}],[])
        self.assertEqual(len([p for p,_,_ in self.requests if p=='audio/synthesize']),2)

    def setUp(self):
        self.requests=[];self.defer=False;self.deferred=[]
        self.endpoint_path=Path(sys.argv_root)/'compartilhado/runtime/launcher/central.url'
        original=self.endpoint_path.read_text();self.addCleanup(lambda:self.endpoint_path.write_text(original))
        def request(window,path,data=None,callback=None,**kwargs):
            self.requests.append((path,data,kwargs))
            args=parse_qs(urlsplit(path).query)
            value={'settings':window.mic_settings,'revision':'fixture'} if path=='control/microphone' else daily_fixture(args.get('entity',['hoshino'])[0]) if path.startswith('state?') else {'items':[]} if path.startswith('control/memory?') else {}
            if path=='control/interface':value={'settings':{},'revision':'fixture'}
            if path=='control/files':value={'items':[]}
            if path=='control/alistair/execution':
                value=({'saved':True,'note':'Destino fixture salvo.'}if data is not None else
                       {'settings':{'destination':'local','xbox_ip':'10.0.0.103','auto_start':True,'auto_sync':True,'trusted_lan':False},
                        'revision':'fixture','xbox':{},'credentials_configured':False,'certificate_configured':False,'note':'Fixture, banco noPC.'})
            if path=='send':value={'id':'fixture-mail'}
            if path.startswith('audio/') and data is not None:
                value={'id':'fixture-audio'}
                if path=='audio/perception/stop':value={'cancelled':True,'capture_id':data['capture_id']}
                if self.defer:self.deferred.append(callback);return object()
            if callback:callback(value)
            return object()
        self.patch=patch.object(ui.Central,'request',request);self.patch.start();self.addCleanup(self.patch.stop)
        self.process=patch.object(ui,'QProcess',FakeProcess);self.process.start();self.addCleanup(self.process.stop)
        self.which=patch.object(ui.shutil,'which',return_value='/fixture/pulse');self.which.start();self.addCleanup(self.which.stop)
        self.window=ui.Central(Path(sys.argv_root));self.window.owned_timeout=lambda *a:None
        self.window.state_timer.stop();self.window.detail_timer.stop();self.window.audio_timer.stop();self.window.focus_timer.stop();self.window.gpu_alert_timer.stop();self.window.pc2_sense_timer.stop();self.window.pc2_command_timer.stop();self.requests.clear()
        if hasattr(self.window,'chat_stream_timer'):self.window.chat_stream_timer.stop()
        def cleanup():
            w=self.window
            for timer in w.findChildren(ui.QTimer):timer.stop()
            for animation in w.findChildren(ui.QPropertyAnimation):animation.stop()
            w.stop_capture(False);w.stop_voice();w.temp.cleanup()
            # A fixture destrói muitas janelas no MESMO QApplication. Não
            # deixar callbacks/seleções/efeitos de uma janela morta vazarem
            # para o próximo caso quando ele processar eventos Qt.
            for child in w.findChildren(ui.QWidget):child.blockSignals(True)
            w.blockSignals(True);w.hide();w.deleteLater()
            ui.QApplication.sendPostedEvents(None,ui.QEvent.DeferredDelete)
        self.addCleanup(cleanup)
    def test_model_versions_render_all_sources_and_require_explicit_experimental_consent(self):
        w=self.window
        common=dict(entity='hoshino',model_id='qwen35-9b',ready=False,ref='fixture',source_sha256='a'*64,
                    evaluation_available=True,behavioral_passed=6,behavioral_total=8)
        w.version_data=dict(entity='hoshino',revision='catalog',families=[dict(model_id='qwen35-9b',label='9B',entries=[
            common|dict(kind=k,experimental=k!='original') for k in ('original','checkpoint','trained')])])
        w.version_family.addItem('9B','qwen35-9b');w.version_family_changed()
        self.assertEqual(w.version_source.count(),3);w.version_source.setCurrentIndex(2)
        self.assertIn('6/8',w.version_status.text());self.assertIn('Experimental',w.version_status.text())
        with patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.No):w.use_model_version(True)
        self.assertFalse(any(p=='control/model-versions/prepare' for p,_,_ in self.requests))
        with patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.Yes):w.use_model_version(True)
        sent=next(data for p,data,_ in self.requests if p=='control/model-versions/prepare')
        self.assertEqual(sent['ref'],'fixture');self.assertTrue(sent['experimental_consent'])
        w.use_model_version(False)
        self.assertFalse(any(p=='control/model-versions' for p,_,_ in self.requests))

    def rotate_endpoint(self):
        self.endpoint_path.write_text('http://127.0.0.1:23457/#fixture-new-session')

    def test_feedback_bubble_discreet_scoped_escaped_and_bounded(self):
        for entity in ui.ENTITIES:
            message=dict(id='msg-<unsafe>',sender=entity,recipient='usuario',text='<script>unsafe</script>',
                         metadata={},feedback_target={'text_sha256':'a'*64,'expected_revision':None})
            rendered,targets=ui.chat_bubbles([message],entity)
            self.assertIn('☆ Avaliar',rendered);self.assertIn('feedback://'+entity,rendered)
            self.assertNotIn('<script>',rendered);self.assertEqual(list(targets),[message['id']])
            self.assertFalse(ui.chat_bubbles([message|{'recipient':'lilith'}],entity)[1])
            self.assertFalse(ui.chat_bubbles([message|{'metadata':{'private':True}}],entity)[1])
            self.assertFalse(ui.chat_bubbles([message],'usuario')[1])
        messages=[message|{'id':str(i)} for i in range(170)]
        self.assertEqual(len(ui.chat_bubbles(messages,'alistair')[1]),150)

    def test_feedback_dialog_requires_choice_bounded_note_and_can_cancel(self):
        message={'metadata':{}}
        dialog=ui.InteractionReview(message,self.window)
        dialog.accept_review();self.assertEqual(dialog.result(),0)
        dialog.decision.setCurrentIndex(1);dialog.note.setPlainText('a'*601)
        dialog.accept_review();self.assertEqual(dialog.result(),0)
        dialog.note.setPlainText('Gostei do ritmo.');dialog.accept_review()
        self.assertEqual(dialog.result(),ui.QDialog.Accepted);self.assertFalse(self.requests)
        dialog.deleteLater()

    def test_feedback_click_uses_exact_message_not_selected_latest_no_training(self):
        from types import SimpleNamespace
        from PyQt5.QtCore import QUrl
        message=dict(id='reply-older',sender='hoshino',recipient='usuario',metadata={},
                     feedback_target={'text_sha256':'b'*64,'expected_revision':None})
        self.window.review_targets={message['id']:message}
        fake=SimpleNamespace(exec_=lambda:ui.QDialog.Accepted,decision=SimpleNamespace(currentData=lambda:'disliked'),
                             note=SimpleNamespace(toPlainText=lambda:'Confundiu quem falou.'))
        with patch.object(ui,'InteractionReview',return_value=fake):
            self.window.review_interaction(QUrl('feedback://hoshino/?message_id=reply-older'))
        path,data,_=self.requests[-1]
        self.assertEqual(path,'control/chat/feedback');self.assertEqual(data['message_id'],'reply-older')
        self.assertEqual(data['entity'],'hoshino');self.assertEqual(data['text_sha256'],'b'*64)
        self.assertEqual(data['note'],'Confundiu quem falou.')
        count=len(self.requests)
        self.window.review_interaction(QUrl('https://example.com'))
        self.window.review_interaction(QUrl('feedback://lilith/?message_id=reply-older'))
        self.assertEqual(len(self.requests),count)
    def test_logic_workshop_nodes_edges_tables_preserve_semantics_when_dragged(self):
        editor=self.window.logic_workshop
        editor.loaded_entity='hoshino';editor.graph={'nodes':[{'id':'a','kind':'hipotese','label':'Origem validada','x':0,'y':0},
            {'id':'b','kind':'condicao','label':'Transferência','x':330,'y':0}],
            'edges':[{'from':'a','to':'b','relation':'exige','basis':'hipotese','exceptions':['alarme']}],
            'tables':[{'title':'Condições','columns':['Estado','Ação'],'rows':[['âmbar','investigar']]}]}
        editor.render();editor.node_items['a'].setPos(50,70)
        self.assertTrue(editor.dirty);self.assertEqual(editor.graph['nodes'][0]['x'],50)
        self.assertEqual(editor.graph['edges'][0]['exceptions'],['alarme'])
        editor.table.item(0,1).setText('investigar antes de agir')
        self.assertEqual(editor.graph['tables'][0]['rows'][0][1],'investigar antes de agir')
        self.assertFalse(any(data for _,data,_ in self.requests))
        qa=os.environ.get('HOSHINO_LOGIC_QA_FILE')
        if qa:
            self.window.nav.setCurrentRow(ui.PAGES.index('Memória do chat'))
            tabs=editor.parentWidget().parentWidget()
            tabs.setCurrentWidget(editor)
            self.window.show();ui.QApplication.processEvents();editor.view.fitInView(editor.scene.itemsBoundingRect(),ui.Qt.KeepAspectRatio)
            ui.QApplication.processEvents();self.assertTrue(self.window.grab().save(qa))
    def test_logic_workshop_cannot_save_under_another_entity(self):
        editor=self.window.logic_workshop;editor.loaded_entity='lilith';editor.save()
        self.assertIn('Entidade mudou',editor.info.text());self.assertFalse(self.requests)
    def test_logic_workshop_save_uses_existing_contract_with_evidence_no_private_diary(self):
        editor=self.window.logic_workshop;editor.loaded_entity=self.window.current_entity()
        editor.mode.setCurrentIndex(editor.mode.findData('fundamentado'))
        editor.title.setText('Hipótese revisável');editor.refs.setText('episodes:ep-1')
        editor.graph={'nodes':[{'id':'a','kind':'hipotese','label':'Texto <não HTML>'}],'edges':[],'tables':[]}
        editor.save();path,data,_=self.requests[-1]
        self.assertEqual(path,'control/logic');self.assertEqual(data['entity'],editor.loaded_entity)
        self.assertEqual(data['evidencias'],[{'table':'episodes','id':'ep-1'}]);self.assertIsNone(data['anterior'])
        self.assertEqual(data['modo'],'fundamentado')
    def test_logic_workshop_can_save_explicit_draft_without_invented_refs(self):
        editor=self.window.logic_workshop;editor.loaded_entity=self.window.current_entity()
        editor.mode.setCurrentIndex(editor.mode.findData('rascunho'))
        editor.title.setText('Hipótese ainda não testada');editor.refs.clear()
        editor.graph={'nodes':[{'id':'a','kind':'hipotese','label':'Comparar alternativas'}],'edges':[],'tables':[]}
        editor.save();path,data,_=self.requests[-1]
        self.assertEqual(path,'control/logic');self.assertEqual(data['modo'],'rascunho')
        self.assertEqual(data['evidencias'],[])
    def test_reduced_motion_stops_page_animation_without_actions(self):
        self.window.change_page(1)
        self.assertEqual(self.window.page_animation.state(),ui.QPropertyAnimation.Running)
        self.window.reduced_motion.setChecked(True)
        self.assertEqual(self.window.page_animation.state(),ui.QPropertyAnimation.Stopped)
        self.assertFalse(self.window.page_effect.isEnabled())
        self.window.change_page(2)
        self.assertEqual(self.window.page_animation.state(),ui.QPropertyAnimation.Stopped)
        self.assertFalse(any(data is not None for _,data,_ in self.requests))
    def test_orb_animation_budget_and_raster_render(self):
        from native_style import animation_interval,paint_orb
        from PyQt5.QtGui import QImage,QPainter
        self.assertEqual(animation_interval('working'),33)
        self.assertEqual(animation_interval('sleeping'),66)
        self.assertEqual(animation_interval('speaking',reduced=True),0)
        self.assertEqual(animation_interval('working',visible=False),0)
        outputs=[]
        for entity,color in ui.COLORS.items():
            image=QImage(88,100,QImage.Format_ARGB32);image.fill(ui.Qt.transparent)
            painter=QPainter(image);paint_orb(painter,color,entity,'sleeping');painter.end()
            self.assertEqual(image.pixelColor(0,0).alpha(),0)
            self.assertGreater(image.pixelColor(44,37).alpha(),0);outputs.append(image)
        self.assertNotEqual(outputs[0],outputs[1]);self.assertNotEqual(outputs[1],outputs[2])
    def test_resource_panel_missing_metrics_bounded_history_and_real_values(self):
        panel=self.window.resources_panel
        for _ in range(130):panel.render({'cpu_percent':0,'ram_total':100,'ram_available':25,'gpu':{}})
        self.assertEqual(panel.metrics['cpu'].value.text(),'0.0%');self.assertEqual(panel.metrics['ram'].value.text(),'75.0%')
        self.assertEqual(panel.metrics['vram'].value.text(),'Indisponível');self.assertEqual(len(panel.metrics['cpu'].trend.samples),120)
        panel.render({'cpu_percent':None});self.assertIsNone(panel.metrics['cpu'].trend.samples[-1])
    def test_resource_cache_caps_are_not_presented_as_allocated_memory(self):
        panel=self.window.resources_panel
        panel.render({'ram_prompt_cache':{'aggregate_mib':8192,'per_entity_mib':{'hoshino':3584,'lilith':3584,'alistair':1024}},'gpu':{}})
        label=panel.cache.text()
        for expected in ('8.00 GiB','Hoshino: 3.50 GiB','Lilith: 3.50 GiB','Alistair: 1.00 GiB','não confirmados'):
            self.assertIn(expected,label)
        panel.render({'ram_prompt_cache':{'valid':False,'aggregate_mib':0},'gpu':{}})
        self.assertIn('Configuração inválida',panel.cache.text())
        panel.render(None);self.assertIn('uso não medido',panel.cache.text());self.assertNotIn('8.00 GiB',panel.cache.text())
    def test_resource_profiles_are_last_observed_not_active_or_benchmarked(self):
        panel=self.window.resources_panel
        panel.render({'gpu':{},'resource_profiles':{'available':[{'label':'Qualidade'},{'label':'Recursos disputados'}],
            'observations':{'hoshino':{'label':'Recursos disputados','ts':'fixture-date','held':True}}}})
        text=panel.profiles.text()
        for expected in ('Hoshino: Recursos disputados','Lilith: sem decisão','fixture-date',
                         'proteção contra trocas frequentes','não perfil ativo','não medido'):
            self.assertIn(expected,text)
        panel.render(None);self.assertNotIn('fixture-date',panel.profiles.text())
    def test_activity_filter_ids_and_output_are_plain_text(self):
        panel=self.window.activity_panel
        panel.render({'items':[{'id':'a','ts':'now','level':'ERROR','event':'tool.failed','entity':'hoshino','turn_id':'turn-123','data':{'message_id':'msg-1'}},{'id':'b','level':'INFO','event':'tts.done'}]})
        panel.search.setText('msg-1');self.assertEqual(panel.timeline.topLevelItemCount(),1)
        panel.timeline.topLevelItem(0).setSelected(True);self.assertIn('turn-123',panel.detail.toPlainText())
        panel.render_commands({'items':[{'id':'cmd','comando':'echo','status':'done','codigo':0,'output':'<script>not HTML</script>'}]})
        panel.commands.topLevelItem(0).setSelected(True);self.assertEqual(panel.output.toPlainText(),'<script>not HTML</script>')
    def test_activity_tab_local_times_error_label_routine_toggle_and_machine_column(self):
        # 06/11 (pedido humano): horário local completo, "eventos de erro", rotina escondida e coluna Onde.
        import native_panels as panels
        panel=self.window.activity_panel
        self.assertEqual(panels.hora_local({'ts':'2026-11-07T00:20:05.382+00:00'}),
                         __import__('datetime').datetime.fromisoformat('2026-11-07T00:20:05.382+00:00').astimezone().strftime('%d/%m %H:%M:%S'))
        self.assertEqual(panels.hora_local({'timestamp':{'local':'2026-11-06T21:20:05-03:00'}})[:5],'06/11')
        panel.render({'items':[{'id':'e1','ts':'2026-11-07T00:20:05+00:00','level':'ERROR','event':'tool.end','entity':'lilith'}]})
        self.assertNotIn('T00:20',panel.timeline.topLevelItem(0).text(0));self.assertIn(':05',panel.timeline.topLevelItem(0).text(0))
        self.assertIn('1 eventos de erro',panel.summary.text());self.assertNotIn('erros na consulta',panel.summary.text())
        self.assertIn('escondidas',panel.summary.text())
        panel.render_commands({'items':[{'id':'pc2-1','onde':'PC2','comando':'uname -n','status':'concluido','codigo':0,
                                         'inicio':'2026-11-06T21:30:00','output':'gutavo2'}]})
        row=panel.commands.topLevelItem(0);self.assertEqual((row.text(0),row.text(1),row.text(3)),('PC2','uname -n','06/11 21:30:00'))
        self.window.show();self.requests.clear();self.window.nav.setCurrentRow(ui.PAGES.index('Atividade'))
        self.requests.clear();panel.show_routine.setChecked(True)
        self.assertTrue(any(p.startswith('control/activity?') and 'rotina=1' in p for p,_,_ in self.requests))
        panel.show_routine.setChecked(False)
        timeline=self.window.history_timeline;timeline.set_entity('lilith');timeline.routine.setChecked(True)
        sent=[]
        timeline.request=lambda entity,offset,filters,callback:(sent.append(dict(filters)),object())[1]
        timeline.search_first();self.assertEqual(sent[-1]['rotina'],'1')
        self.assertTrue(self.window.diagnostics_panel.show_routine.isHidden())
    def test_portrait_rejects_remote_invalid_and_preserves_identity_ring(self):
        from native_style import load_orb_image,mood_color,paint_orb
        from PyQt5.QtGui import QImage,QPainter,QColor
        self.assertTrue(load_orb_image('https://example.com/x.png').isNull())
        path=Path(self.window.temp.name)/'portrait.png';portrait=QImage(32,32,QImage.Format_ARGB32);portrait.fill(QColor('#ff0000'));portrait.save(str(path))
        loaded=load_orb_image(str(path));self.assertFalse(loaded.isNull())
        canvas=QImage(88,100,QImage.Format_ARGB32);canvas.fill(ui.Qt.transparent);p=QPainter(canvas)
        paint_orb(p,'#123456','lilith','awake',identity_color='#c6a3ed',portrait=loaded);p.end()
        self.assertEqual(canvas.pixelColor(44,37).name(),'#ff0000')
        alternate=QImage(88,100,QImage.Format_ARGB32);alternate.fill(ui.Qt.transparent);p=QPainter(alternate)
        paint_orb(p,'#ff0000','lilith','awake',identity_color='#c6a3ed',portrait=loaded);p.end()
        self.assertEqual(canvas.pixelColor(72,37),alternate.pixelColor(72,37))
        self.assertEqual(mood_color('#123456',None),'#123456');self.assertNotEqual(mood_color('#123456','alegria'),'#123456')
    def test_services_configuration_does_not_claim_connection_or_display_key(self):
        panel=self.window.services_panel
        panel.render({'preferred_provider':'elevenlabs','local_backend':'qwen3_tts','providers':{'elevenlabs':{'enabled':True,'key_configured':True,'api_key':'SECRET_SENTINEL','voices':{'hoshino':'voice-h'},'connection':'não testada nesta consulta'}}})
        state,key,detail,connection=panel.providers['elevenlabs']
        self.assertEqual(state.text(),'Habilitado');self.assertIn('CONFIGURADA',key.text());self.assertIn('não testada',connection.text())
        self.assertNotIn('SECRET_SENTINEL',' '.join(w.text() for w in panel.findChildren(ui.QLabel)))
        self.assertEqual(panel.providers['azure'][0].text(),'Indisponível')
        self.assertFalse(any(data is not None for _,data,_ in self.requests))
    def real_request(self,path,data=None,callback=None):
        worker=type('Thread',(),{})();worker.done=Signal();worker.finished=Signal();worker.start=lambda:None
        self.patch.stop()
        try:
            with patch.object(ui,'Rpc',return_value=worker) as rpc:
                self.window.request(path,data,callback=callback)
        finally:self.patch.start()
        return worker,rpc
    def test_new_request_refreshes_endpoint_without_replaying_voice(self):
        self.rotate_endpoint();worker,rpc=self.real_request('control/audio')
        self.assertEqual(rpc.call_args.args[:2],('http://127.0.0.1:23457','fixture-new-session'))
        self.assertEqual(rpc.call_count,1);self.assertFalse(any(p=='audio/test' for p,_,_ in self.requests))
        self.window.workers.clear()
    def test_same_endpoint_preserves_pending_work_and_edits(self):
        self.window.voice_job='own-audio';self.window.audio_config={'revision':'unsaved'};epoch=self.window.voice_epoch
        self.assertTrue(self.window.sync_endpoint());self.assertEqual(self.window.voice_job,'own-audio')
        self.assertEqual(self.window.audio_config,{'revision':'unsaved'});self.assertEqual(self.window.voice_epoch,epoch)
    def test_restart_discards_old_mutable_callback_without_retry(self):
        received=[];worker,rpc=self.real_request('send',{'text':'não repetir'},received.append)
        self.rotate_endpoint();worker.done.emit({'ok':True,'value':{'id':'old-message'}})
        self.assertEqual(received,[]);self.assertEqual(rpc.call_count,1);self.assertFalse(self.requests)
        self.assertIn('não foram repetidos',self.window.notice.text());self.window.workers.clear()
    def test_restart_resets_only_client_work_and_preserves_drafts(self):
        self.window.draft.setPlainText('Rascunho humano');self.window.drafts['lilith']='Outro rascunho'
        self.window.start_capture('detection');capture=self.window.capture
        self.window.voice_job='old-audio';self.window.asr_jobs={'old-asr':{'entity':'hoshino','test':False}}
        self.window.resume_capture=('detection','hoshino');self.window.audio_config={'revision':'old'}
        self.window.auto_voice.setChecked(True);self.requests.clear();self.rotate_endpoint()
        self.assertTrue(self.window.sync_endpoint());self.assertFalse(capture.running);self.assertIsNone(self.window.capture)
        self.assertFalse(self.window.asr_jobs);self.assertIsNone(self.window.voice_job);self.assertIsNone(self.window.resume_capture)
        self.assertIsNone(self.window.audio_config);self.assertFalse(self.window.auto_voice.isChecked())
        self.assertEqual(self.window.draft.toPlainText(),'Rascunho humano');self.assertEqual(self.window.drafts['lilith'],'Outro rascunho')
        self.assertFalse(self.requests)
    def test_explicit_mic_stop_after_backend_restart_does_not_send_old_capture_or_reenter_stop(self):
        w=self.window;w.start_capture('detection');self.requests.clear();self.rotate_endpoint()
        w.stop_capture(False)
        self.assertIsNone(w.capture);self.assertFalse(self.requests)
    def test_invalid_endpoint_is_rejected_without_remote_request_or_secret(self):
        self.endpoint_path.write_text('https://external.invalid/#DO_NOT_DISPLAY')
        worker,rpc=self.real_request('audio/test',{'text':'teste'})
        self.assertEqual(rpc.call_count,0);self.assertFalse(self.window.workers)
        self.assertNotIn('DO_NOT_DISPLAY',self.window.notice.text());self.assertIn('indisponível',self.window.notice.text())
    def test_old_player_started_does_not_report_to_new_backend(self):
        self.window.play_bytes(b'fixture','old-job','hoshino',0);player=self.window.player
        self.rotate_endpoint();player.started.emit()
        self.assertFalse(any(p=='audio/job' for p,_,_ in self.requests));self.assertIsNone(self.window.player)
    def test_first_explicit_voice_after_restart_is_not_cancelled_as_stale(self):
        self.rotate_endpoint();worker=type('Thread',(),{})();worker.done=Signal();worker.finished=Signal();worker.start=lambda:None
        self.patch.stop()
        try:
            with patch.object(ui,'Rpc',return_value=worker):self.window.begin_speech('lilith','audio/test',{'entity':'lilith'},True)
        finally:self.patch.start()
        worker.done.emit({'ok':True,'value':{'id':'new-audio'}})
        self.assertEqual(self.window.voice_job,'new-audio');self.assertEqual(self.window.voice_entity,'lilith')
        self.assertFalse(any(p=='audio/cancel' for p,_,_ in self.requests));self.window.workers.clear()
    def test_current_session_callback_still_delivered_once(self):
        received=[];worker,rpc=self.real_request('control/audio',callback=received.append)
        worker.done.emit({'ok':True,'value':{'revision':'current'}})
        self.assertEqual(received,[{'revision':'current'}]);self.assertEqual(rpc.call_count,1);self.window.workers.clear()
    def test_volume_starts_at_100_and_story_never_auto_synthesizes(self):
        self.assertEqual(self.window.volume.value(),100);self.assertIn('Era uma vez',self.window.test_text.toPlainText())
        self.assertLess(len(self.window.test_text.toPlainText()),600);self.assertFalse(self.requests);self.assertIsNone(self.window.player)
    def test_player_initial_volume_50_and_zero_use_owned_paplay(self):
        for value,expected in ((50,32768),(0,0)):
            self.window.volume.setValue(value);self.window.play_bytes(b'fixture')
            self.assertIn('--volume='+str(expected),self.window.player.args)
            self.assertIn('--stream-name='+self.window.player_stream,self.window.player.args);self.window.stop_voice()
    def test_saved_volume_is_partial_preference_write_no_synthesis(self):
        self.window.volume.setValue(35);self.window.save_volume()
        path,data,_=self.requests[-1];self.assertEqual(path,'control/microphone');self.assertEqual(data['settings'],{'output_volume':35})
        self.assertFalse(any(p.startswith('audio/') for p,_,_ in self.requests))
    def test_restored_volume_preserves_muted_zero(self):
        self.window.loaded_microphone({'settings':dict(self.window.mic_settings,output_volume=0),'revision':'restored'})
        self.assertEqual(self.window.volume.value(),0);self.assertEqual(self.window.volume_label.text(),'0% · mudo');self.assertIsNone(self.window.player)
    def test_live_volume_targets_only_matching_player_stream(self):
        self.window.play_bytes(b'fixture');player=self.window.player;name=self.window.player_stream
        self.window.volume.setValue(25);self.window.apply_volume();inventory=self.window.volume_process
        self.assertEqual(inventory.args,['--format=json','list','sink-inputs'])
        inventory.stdout=json.dumps([{'index':10,'properties':{'application.process.id':'111','media.name':name}},
                                    {'index':11,'properties':{'application.process.id':str(player.processId()),'media.name':name}}]).encode()
        inventory.finished.emit(0,0);setter=self.window.volume_process
        self.assertEqual(setter.program,'pactl');self.assertEqual(setter.args,['set-sink-input-volume','11','16384'])
        setter.finished.emit(0,0);self.assertIsNone(self.window.volume_process)
    def test_live_volume_missing_or_stale_stream_never_touches_other_apps(self):
        for stale in (False,True):
            self.window.play_bytes(b'fixture');player=self.window.player;name=self.window.player_stream
            self.window.apply_volume();inventory=self.window.volume_process
            inventory.stdout=json.dumps([{'index':11,'properties':{'application.process.id':str(player.processId()) if stale else '111','media.name':name}}]).encode()
            if stale:self.window.stop_voice();self.window.play_bytes(b'new-player')
            inventory.finished.emit(0,0);self.assertIsNone(self.window.volume_process)
        self.assertFalse(any(p.startswith('audio/') for p,_,_ in self.requests))
    def test_live_volume_failure_is_visible_and_never_replays_audio(self):
        self.window.play_bytes(b'fixture');player=self.window.player;self.window.apply_volume();inventory=self.window.volume_process
        inventory.finished.emit(1,0);self.assertIn('não confirmado',self.window.notice.text());self.assertIs(self.window.player,player)
        self.assertIsNone(self.window.volume_process);self.assertFalse(self.requests)
    def test_no_capture_or_voice_on_window_start(self):
        self.assertIsNone(self.window.capture);self.assertIsNone(self.window.player);self.assertFalse(self.window.mic_settings['auto_send'])
    def test_daily_archive_blocks_send_capture_attachments_and_autoplay(self):
        self.window.chat_view_loaded(daily_fixture(day='2026-10-08',archived=True))
        self.window.auto_voice.setChecked(True);self.window.draft.setPlainText('não enviar')
        self.window.send();self.window.start_capture('detection');self.window.attach()
        self.assertTrue(self.window.draft.isReadOnly());self.assertFalse(self.window.chat_send.isEnabled())
        self.assertFalse(self.window.can_auto_speak('hoshino'));self.assertIsNone(self.window.capture)
        self.assertFalse(any(p=='send' or p.startswith('control/attachment') for p,_,_ in self.requests))
        # Teste de mic descartável continua explícito e não conversa com entidade.
        self.window.start_capture('command',True);self.assertIsNotNone(self.window.capture);self.window.stop_capture(False)
    def test_daily_today_and_entity_selection_restore_backend_session(self):
        self.window.draft.setPlainText('rascunho preservado')
        self.window.chat_view_loaded(daily_fixture(day='2026-10-08',archived=True));self.window.chat_today()
        self.assertFalse(self.window.chat_read_only);self.assertEqual(self.window.draft.toPlainText(),'rascunho preservado')
        self.window.entity.setCurrentIndex(1)
        self.assertEqual(self.window.chat_session['entity'],'lilith');self.assertFalse(self.window.chat_read_only)
        self.assertTrue(any('daily=1' in p for p,_,_ in self.requests if p.startswith('state?')))
    def test_daily_late_http_send_does_not_delete_new_draft(self):
        callbacks=[]
        def delayed(path,data=None,callback=None,**kwargs):
            if path=='send':callbacks.append((data,callback))
            return object()
        with patch.object(self.window,'request',side_effect=delayed):
            self.window.draft.setPlainText('primeira');self.window.send()
            self.window.draft.setPlainText('segunda');callbacks[0][1]({'id':'accepted'})
        self.assertEqual(self.window.draft.toPlainText(),'segunda')
        self.assertEqual(callbacks[0][0]['conversation_session_id'],'fixture-hoshino-2026-10-09')
    def test_daily_stale_http_view_cannot_replace_selected_archive(self):
        callbacks=[]
        with patch.object(self.window,'request',side_effect=lambda p,**kw:callbacks.append(kw['callback']) or object()):
            self.window.refresh();self.window.reset_chat_view('fixture-hoshino-2026-10-08')
            callbacks[0](daily_fixture(messages=[{'id':'new','sender':'usuario','recipient':'hoshino','text':'não mostrar'}]))
        self.assertEqual(self.window.chat.toPlainText(),'');self.assertTrue(self.window.chat_read_only)
    def test_daily_midnight_preserves_draft_and_does_not_start_old_session_audio(self):
        self.window.draft.setPlainText('rascunho antes da meia-noite');self.window.auto_voice.setChecked(True)
        old=self.window.chat_session['id'];out=daily_fixture(day='2026-10-10')
        out['current_chat_session']=out['chat_session']
        out['jobs']=[{'id':'old-stream','entity':'hoshino','status':'running','kind':'llm_speech',
                      'updated_at':ui.time.time(),'details':{'channel':'localhub','stable_only':True,
                          'sentences':['Resposta de ontem.'],'conversation_session_id':old}}]
        with patch.object(self.window,'request',side_effect=lambda p,callback=None,**kw:callback(out) or object()):self.window.refresh()
        self.assertEqual(self.window.chat_session['local_date'],'2026-10-10');self.assertFalse(self.window.chat_read_only)
        self.assertEqual(self.window.draft.toPlainText(),'rascunho antes da meia-noite');self.assertIsNone(self.window.voice_job)
        self.assertNotIn('old-stream',self.window.stream_seen)
    def test_global_main_view_includes_entity_exchanges_without_hidden_panel(self):
        self.assertFalse(hasattr(self.window,'show_private'));self.assertEqual(self.window.chat_scope,'global')
        out=daily_fixture();out['conversation']=[{'sender':'hoshino','recipient':'lilith','text':'entre as duas'},
                                              {'sender':'alistair','recipient':'lilith','text':'também pública para Hoshino'}]
        with patch.object(self.window,'request',side_effect=lambda p,callback=None,**kw:callback(out) or object()):self.window.refresh()
        self.assertIn('entre as duas',self.window.chat.toPlainText());self.assertIn('também pública para Hoshino',self.window.chat.toPlainText())
    def test_scope_switch_preserves_separate_drafts_and_routes_send(self):
        w=self.window;w.draft.setPlainText('Público');w.send();sent=next(data for path,data,_ in self.requests if path=='send')
        self.assertEqual(sent['chat_scope'],'global');w.draft.setPlainText('Rascunho global');w.chat_channel.setCurrentIndex(1)
        self.assertEqual(w.chat_scope,'direct');self.assertEqual(w.draft.toPlainText(),'')
        w.draft.setPlainText('Rascunho direto');w.chat_channel.setCurrentIndex(0);self.assertEqual(w.draft.toPlainText(),'Rascunho global')
    def test_human_display_label_and_all_speakers_feedback(self):
        message=dict(id='fixture-feedback',sender='alistair',recipient='usuario',text='Olá',feedback_target={'text_sha256':'hash'})
        rendered,targets=ui.chat_bubbles([message],'hoshino','Lua')
        self.assertIn('Alistair → Lua',rendered);self.assertIn('feedback://alistair',rendered);self.assertIn(message['id'],targets)
        rendered,_=ui.chat_bubbles([dict(sender='usuario',recipient='lilith',text='Oi')],'hoshino')
        self.assertIn('Usuário → Lilith',rendered)
    def test_global_voice_uses_actual_speaker_even_with_alistair_selected(self):
        w=self.window;w.auto_voice.setChecked(True)
        replies=[dict(id='l-reply',sender='lilith',recipient='usuario',metadata={})]
        with patch.object(w,'begin_speech',return_value=True) as speak:
            w.handle_new_voice('alistair',replies,[])
        self.assertEqual(speak.call_args.args[0],'lilith');self.assertIn('l-reply',w.voice_seen)
    def test_card_editor_sends_only_changed_record_with_revision(self):
        from native_panels import KnowledgePanel
        calls=[]
        panel=KnowledgePanel(lambda:None,lambda data,done:(calls.append(data),done({'verified':True})))
        card=dict(id='concept:one',title='Regra',entity='hoshino',kind='rule',entries=[dict(table='memories',record_id='one',revision='version-one',fields={'content':'Antes','type':'rule'},text='Antes')])
        panel.render(dict(entity='hoshino',items=[card],total=1))
        def edit(dialog):
            editor=dialog.findChildren(ui.QPlainTextEdit)[0];editor.setPlainText('Depois')
            button=next(b for b in dialog.findChildren(ui.QPushButton) if b.text().startswith('Salvar este'))
            button.click();return dialog.result()
        with patch.object(ui.QDialog,'exec_',edit):panel.editor(card)
        self.assertEqual(calls,[dict(action='update',records=[dict(table='memories',id='one',revision='version-one',fields={'content':'Depois'})])])
        panel.deleteLater()
    def test_modes_and_push_to_talk_use_owned_process_only(self):
        self.assertEqual(self.window.mic_mode.count(),2)
        self.assertTrue(self.window.pages['Áudio'].parent() is not None)
        for mode in ('command','detection'):
            self.window.start_capture(mode);self.assertEqual(self.window.segmenter.mode,mode);self.assertEqual(self.window.capture.program,'parec');self.window.stop_capture(False)
        self.window.ptt_start();self.assertEqual(self.window.segmenter.mode,'command');self.window.stop_capture(False)
    def test_mic_failure_does_not_leave_capture_falsely_open(self):
        self.window.start_capture('command');process=self.window.capture;process.errorOccurred.emit(FakeProcess.FailedToStart)
        self.assertIsNone(self.window.capture);self.assertIsNone(self.window.segmenter);self.assertIn('indisponível',self.window.notice.text())
    def test_open_mic_stays_open_during_speech_without_restart(self):
        self.window.auto_voice.setChecked(True);self.window.start_capture('detection');self.assertTrue(self.window.can_auto_speak('hoshino'))
        capture=self.window.capture
        self.window.begin_speech('hoshino','audio/test',{'entity':'hoshino'},True)
        self.assertIs(self.window.capture,capture);self.assertIsNone(self.window.resume_capture)
        self.requests.clear();self.window.finish_voice();self.assertEqual(self.window.segmenter.mode,'detection')
        self.assertIs(self.window.capture,capture)
        self.assertFalse(any(p=='audio/cancel' for p,_,_ in self.requests))
    def test_explicit_interrupt_prevents_auto_reopening_microphone(self):
        self.window.start_capture('detection');self.window.begin_speech('hoshino','audio/test',{},True);self.window.stop_voice();self.window.finish_voice()
        self.assertIsNotNone(self.window.capture)
        self.window.stop_capture(False);self.window.finish_voice();self.assertIsNone(self.window.capture)
    def test_acoustic_windows_include_silence_below_speech_gate_without_sending_chat(self):
        w=self.window;w.start_capture('detection');capture=w.capture
        capture.stdout=bytes(31200);capture.readyReadStandardOutput.emit()
        calls=[(p,d) for p,d,_ in self.requests if p.startswith('audio/perception?')]
        self.assertEqual(len(calls),1);self.assertEqual(len(calls[0][1]),31200)
        self.assertFalse(any(p=='send' or p.startswith('audio/transcribe') for p,_,_ in self.requests))
        self.assertIs(w.capture,capture)
    def test_acoustic_backpressure_keeps_only_latest_and_stop_invalidates_result(self):
        w=self.window;w.start_capture('detection');self.defer=True;capture=w.capture
        capture.stdout=bytes(31200+15360*5);capture.readyReadStandardOutput.emit()
        self.assertEqual(len(self.deferred),1);self.assertIsNotNone(w.acoustic_waiting)
        self.assertGreater(w.acoustic_dropped,0);old=self.deferred.pop(0)
        w.stop_capture(False);self.defer=False;self.requests.clear()
        old({'events':[{'label':'risada'}]})
        self.assertFalse(any(p.startswith('audio/perception?') for p,_,_ in self.requests))
        self.assertIsNone(w.acoustic_waiting);self.assertIsNone(w.capture)
    def test_headphones_keep_detection_and_transcription_during_own_playback(self):
        w=self.window;w.start_capture('detection');capture=w.capture
        w.player=FakeProcess();capture.stdout=(b'\xff\x3f'*8000)+bytes(32000)
        capture.readyReadStandardOutput.emit()
        self.assertIs(w.capture,capture)
        self.assertTrue(any(p.startswith('audio/transcribe') for p,_,_ in self.requests))
        params=[parse_qs(urlsplit(p).query) for p,_,_ in self.requests if p.startswith('audio/perception?')]
        self.assertTrue(params);self.assertTrue(all(q['playback_overlap']==['true'] for q in params))
    def test_asr_saturation_never_stops_continuous_detector(self):
        w=self.window;w.start_capture('detection');capture=w.capture
        w.asr_jobs['busy']={};w.asr_waiting=[(b'x','hoshino',False,None,'global','detection')]*4
        w.transcribe(bytes(16000),'hoshino',mode='detection')
        self.assertIs(w.capture,capture);self.assertEqual(len(w.asr_waiting),4)
    def test_http_slot_saturation_replaces_oldest_window_without_later_replay(self):
        w=self.window;w.start_capture('detection');sent=[];available=False
        def request(path,data=None,callback=None,**kwargs):
            sent.append(data)
            if not available:return None
            if callback:callback({'events':[]})
            return object()
        with patch.object(w,'request',side_effect=request):
            first=bytes(31200);second=b'\x01\x00'*15600
            w.acoustic_window(first,False,time.time());available=True
            w.acoustic_window(second,False,time.time())
        self.assertEqual(sent,[first,second]);self.assertIsNone(w.acoustic_waiting)
        self.assertEqual(w.acoustic_dropped,1)
    def test_first_actual_ui_url_reaches_service_with_sequence_zero(self):
        import contextlib
        from unittest.mock import Mock
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
        from core import audio_perception_service as service
        worker=Mock();worker.call.return_value={'events':[]}
        detector=service.AcousticService(Path(sys.argv_root),worker);self.addCleanup(detector.close)
        w=self.window;w.start_capture('detection');results=[]
        def request(path,data=None,callback=None,**kwargs):
            query={k:v[0] for k,v in parse_qs(urlsplit(path).query).items()}
            result=detector.submit(query['entity'],data,source=query['source'],capture_id=query['capture_id'],
                sequence=int(query.get('sequence','-1')),scope=query['scope'],playback_overlap=query['playback_overlap']=='true',observed_at=query['observed_at'])
            results.append(result)
            if callback:callback(result)
            return object()
        with patch.object(w,'request',side_effect=request),patch.object(service.resource_manager,'lease',return_value=contextlib.nullcontext()),patch.object(service.gpu_metrics,'ram_available',return_value=8*1024**3):
            w.capture.stdout=bytes(31200);w.capture.readyReadStandardOutput.emit()
        self.assertEqual(results[0]['sequence'],0);worker.call.assert_called_once()
    def test_cancel_has_reserved_rpc_slot_and_blocks_new_detection_until_ack(self):
        w=self.window;w.start_capture('detection');identifier=w.acoustic_capture_id
        worker=type('Thread',(),{})();worker.done=Signal();worker.finished=Signal();worker.start=lambda:None
        w.workers=[object() for _ in range(8)];self.patch.stop()
        try:
            with patch.object(ui,'Rpc',return_value=worker) as rpc:
                w.stop_capture(False);self.assertEqual(rpc.call_count,1)
                self.assertIsNotNone(w.acoustic_stop_pending)
                w.stop_acoustic();w.start_capture('detection');self.assertIsNone(w.capture)
                self.assertIsNone(w.request('control/audio'));self.assertEqual(rpc.call_count,1)
                worker.done.emit({'ok':True,'value':{'cancelled':True,'capture_id':identifier}})
                self.assertIsNone(w.acoustic_stop_pending)
        finally:self.patch.start();w.workers.clear()
        w.start_capture('detection');self.assertIsNotNone(w.capture)
    def test_uncertain_cancel_is_not_retried_or_falsely_confirmed(self):
        w=self.window;w.start_capture('detection');callbacks=[]
        def request(path,data=None,callback=None,**kwargs):
            if callback:callbacks.append(callback)
            return object()
        with patch.object(w,'request',side_effect=request):
            w.stop_capture(False);callbacks[0](None);w.start_capture('detection')
            self.assertIsNone(w.capture);self.assertIsNotNone(w.acoustic_stop_pending)
            self.assertEqual(len(callbacks),1);self.assertIn('não confirmado',w.acoustic_status.text())
    def test_cancel_connection_unavailable_retains_obligation_instead_of_rearming(self):
        w=self.window;w.start_capture('detection')
        with patch.object(w,'sync_endpoint',return_value=False):w.stop_capture(False)
        self.assertIsNotNone(w.acoustic_stop_pending)
        w.start_capture('detection');self.assertIsNone(w.capture)
    def test_pending_speech_prevents_duplicate_and_late_response_is_cancelled(self):
        self.defer=True;self.window.auto_voice.setChecked(True);self.window.begin_speech('hoshino','audio/test',{},True)
        self.assertFalse(self.window.can_auto_speak('hoshino'));callback=self.deferred.pop();self.window.stop_voice();self.defer=False;callback({'id':'late-audio'})
        self.assertTrue(any(p=='audio/cancel' and d['id']=='late-audio' for p,d,_ in self.requests));self.assertIsNone(self.window.voice_job)
    def test_entity_switch_during_asr_preserves_origin_entity(self):
        self.window.asr_jobs['transcription']={'entity':'hoshino','test':False};self.window.entity.setCurrentIndex(1)
        self.window.asr_result('transcription',{'status':'done','result':{'text':'Meu nome é Gustavo'}})
        self.assertEqual(self.window.drafts['hoshino'],'Meu nome é Gustavo');self.assertEqual(self.window.draft.toPlainText(),'');self.assertIn('hoshino',self.window.origins)
    def test_asr_test_never_sends_even_when_auto_send_enabled(self):
        self.window.mic_settings['auto_send']=True;self.window.asr_jobs['test']={'entity':'hoshino','test':True}
        self.window.asr_result('test',{'status':'done','result':{'text':'teste'}})
        self.assertFalse(any(p=='send' for p,_,_ in self.requests));self.assertEqual(self.window.draft.toPlainText(),'teste')
    def test_custom_voice_text_provider_model_and_sleeping_entity(self):
        self.window.test_text.setPlainText('Minha frase específica.');self.window.provider.setCurrentText('elevenlabs');self.window.tts_model.setCurrentText('eleven_flash_v2_5')
        with patch.object(ui.QMessageBox,'question',return_value=ui.QMessageBox.Yes):self.window.test_voice('lilith')
        payload=next(d for p,d,_ in self.requests if p=='audio/test');self.assertEqual(payload['text'],'Minha frase específica.');self.assertEqual(payload['model'],'eleven_flash_v2_5');self.assertEqual(payload['entity'],'lilith')
        self.assertFalse(any(p=='start' for p,_,_ in self.requests))
    def test_player_reports_order_and_native_basis_not_hearing(self):
        self.window.voice_epoch=1;self.window.play_bytes(b'fixture-not-real-audio','job','lilith',0);player=self.window.player
        self.assertEqual(player.program,'paplay');player.started.emit();player.finished.emit(0,0)
        reports=[d for p,d,_ in self.requests if p=='audio/job'];self.assertEqual([r['playback_event'] for r in reports],['started','ended']);self.assertTrue(all(r['player']=='native' for r in reports));self.assertEqual(self.window.voice_index,1)
    def test_player_failed_start_cleans_pending_state(self):
        self.window.play_bytes(b'fixture','job','hoshino',0);player=self.window.player;player.errorOccurred.emit(FakeProcess.FailedToStart)
        self.assertIsNone(self.window.player);self.assertFalse(list(Path(self.window.temp.name).glob('*.wav')))
        self.assertTrue(any(p=='audio/job' and d['playback_event']=='failed' for p,d,_ in self.requests))
    def test_sleep_controls_only_target_entity(self):
        self.window.voice_entity='lilith';self.window.voice_job='lilith-audio';self.window.sleep('hoshino')
        self.assertEqual(self.window.voice_job,'lilith-audio');self.assertTrue(any(p=='sleep' and d['entity']=='hoshino' for p,d,_ in self.requests))
    def test_mic_pcm_is_only_draft_and_bounded_backpressure(self):
        pcm=array.array('h',[3000]*int(FRAME_BYTES/2*8)).tobytes();self.defer=True;self.window.transcribe(pcm,'hoshino');self.window.transcribe(pcm,'hoshino')
        self.assertEqual(len([p for p,_,_ in self.requests if p.startswith('audio/transcribe')]),1);self.assertEqual(len(self.window.asr_waiting),1)
    def test_periodic_memory_refresh_does_not_destroy_selection(self):
        self.window.show();self.window.nav.setCurrentRow(ui.PAGES.index('Memória do chat'));self.requests.clear();self.window.refresh_active(True)
        self.assertFalse(self.requests)
    def test_window_close_cancels_late_own_audio_reply_not_backend(self):
        worker=type('Thread',(),{})();worker.done=Signal();worker.finished=Signal();worker.start=lambda:None
        # Exercita request real mantendo transporte simulado (sem thread/rede).
        self.patch.stop()
        with patch.object(ui,'Rpc',return_value=worker):self.window.request('audio/test',{})
        self.patch.start();self.window.closing=True;worker.done.emit({'ok':True,'value':{'id':'late-after-close'}})
        self.assertTrue(any(p=='audio/cancel' and d['id']=='late-after-close' for p,d,_ in self.requests))
        self.assertFalse(any(p=='control/shutdown' for p,_,_ in self.requests));self.window.workers.clear()

if __name__=='__main__':
    sys.argv_root=sys.argv.pop(1);app=ui.QApplication([]);unittest.main()
