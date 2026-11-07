"""Escuta compartilhada: fixtures offline, sem abrir microfone ou ASR real."""
import unittest
from unittest.mock import patch,Mock
from pathlib import Path
import tempfile,array

def graph(serial=226,pid='42'):
    return [dict(id=69,type='PipeWire:Interface:Node',info=dict(props={
        'media.class':'Stream/Output/Audio','node.name':'java','object.serial':serial,
        'application.process.id':pid,'application.name':'java'})),
        dict(id=55,type='PipeWire:Interface:Port',info=dict(props={
            'node.id':69,'port.direction':'out','audio.channel':'FL','object.serial':227})),
        dict(id=67,type='PipeWire:Interface:Port',info=dict(props={
            'node.id':69,'port.direction':'out','audio.channel':'FR','object.serial':228}))]

class Routes(unittest.TestCase):
    def test_partial_open_preserves_owned_handle_when_rollback_cannot_close(self):
        from core import audio_routes as routes
        source={'id':'pw:226','kind':'application_stream','serial':'226','label':'java','pid':42}
        child=Mock();child.poll.return_value=None;child.terminate.side_effect=PermissionError('fixture')
        def fail(route):route.loopback=child;raise ValueError('setup failed')
        with patch.object(routes,'graph',return_value=graph()),patch.object(routes,'process_stamp',return_value='start42'),patch.object(routes.Route,'_isolate',fail):
            with self.assertRaises(RuntimeError) as caught:routes.Route(Path('/fixture'),source)
        self.assertIs(caught.exception.owned_route.loopback,child)
    def test_close_attempts_both_owned_children_and_reports_uncertain_cleanup(self):
        from core.audio_routes import Route
        route=object.__new__(Route);route.process=Mock();route.loopback=Mock()
        route.process.poll.return_value=None;route.process.terminate.side_effect=PermissionError('fixture')
        route.loopback.poll.return_value=None
        with self.assertRaises(RuntimeError):route.close()
        route.loopback.terminate.assert_called_once()

    def test_selects_exact_stream_serial_and_keeps_pid_fingerprint(self):
        from core import audio_routes as routes
        source={'id':'pw:226','kind':'application_stream','serial':'226','label':'java','pid':42}
        with patch.object(routes,'process_stamp',return_value='start42'):
            selected=routes.resolve(source,graph())
        self.assertEqual(selected['ports'],{'FL':55,'FR':67})
        self.assertEqual(selected['stamp'],'start42')
        self.assertEqual(selected['node_id'],69)

    def test_recycled_index_or_pid_does_not_select_another_app(self):
        from core import audio_routes as routes
        source={'id':'pw:226','kind':'application_stream','serial':'226','label':'java','pid':42}
        for changed in (graph(999),graph(pid='43')):
            with self.assertRaises(ValueError):routes.resolve(source,changed)
        with patch.object(routes,'process_stamp',return_value=None),self.assertRaises(ValueError):
            routes.resolve(source,graph())

    def test_route_stale_after_pid_restart_even_if_name_and_node_match(self):
        from core import audio_routes as routes
        source={'id':'pw:226','kind':'application_stream','serial':'226','label':'java','pid':42}
        with patch.object(routes,'process_stamp',return_value='first'):
            selected=routes.resolve(source,graph())
        with patch.object(routes,'process_stamp',return_value='second'):
            self.assertFalse(routes.matches(selected,graph()))

class Listening(unittest.TestCase):
    def test_partial_open_uncertainty_is_not_forgotten_by_manager(self):
        error=RuntimeError('partial open');error.owned_route=self.route;self.factory.side_effect=error
        with self.assertRaises(RuntimeError):self.service.open('hoshino','entrada','fixture-source','ativa')
        self.assertEqual(self.service.state('hoshino')['uncertain_count'],1)
        with self.assertRaises(ValueError):self.service.open('hoshino','entrada','fixture-source','ativa')
        for slot in self.service.routes.values():slot['cleanup_uncertain']=False
    def test_close_failure_preserves_handle_and_forbids_duplicate_capture(self):
        self.service.open('hoshino','entrada','fixture-source','ativa')
        self.route.close.side_effect=RuntimeError('fechamento não confirmado')
        def allow_cleanup():
            self.route.close.side_effect=None
            for slot in self.service.routes.values():slot['cleanup_uncertain']=False
        self.addCleanup(allow_cleanup)
        with self.assertRaises(RuntimeError):self.service.stop('hoshino','entrada')
        with self.assertRaises(ValueError):self.service.open('hoshino','entrada','fixture-source','ativa')
        self.assertEqual(self.factory.call_count,1)
        self.assertIn('fixture-source',self.service.routes)

    def test_subscriber_during_partial_pcm_does_not_receive_earlier_speech(self):
        self.service.open('hoshino','entrada','fixture-source','ativa')
        self.route.read.return_value=array.array('h',[1200,-1200]*3200).tobytes();self.service.step()
        self.service.open('lilith','entrada','fixture-source','ativa')
        self.route.read.return_value=bytes(48000);self.service.step();self.route.read.return_value=b''
        self.finish_asr()
        self.assertEqual(len(self.service.recent('hoshino',0)['items']),1)
        self.assertEqual(self.service.recent('lilith',0)['items'],[])

    def test_observed_revocation_fences_result_even_after_permission_returns(self):
        self.service.open('hoshino','entrada','fixture-source','ativa')
        self.service.open('lilith','entrada','fixture-source','ativa');self.speech()
        with patch('core.audio_listening.ui_policy.capability_allowed',side_effect=lambda _r,e,_c:e!='hoshino'):
            self.service.step()
        self.finish_asr()
        self.assertEqual(self.service.recent('hoshino',0)['items'],[])
        self.assertEqual(len(self.service.recent('lilith',0)['items']),1)
    def setUp(self):
        from core import audio_listening
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.audio=Mock(root=Path(self.temp.name));self.audio.submit_environment.return_value={'id':'job-one'}
        self.audio.get.return_value={'status':'queued'}
        self.audio.take_environment=self.audio.get
        self.route=Mock();self.route.valid.return_value=True;self.route.read.return_value=b''
        self.factory=Mock(return_value=self.route)
        self.sources={'sources':[{'id':'fixture-source','label':'Entrada','kind':'microphone','serial':'50'}],'streams':[]}
        self.policy=patch.object(audio_listening.ui_policy,'capability_allowed',return_value=True);self.policy.start();self.addCleanup(self.policy.stop)
        self.inventory=patch.object(audio_listening,'inventory',return_value=self.sources);self.inventory.start();self.addCleanup(self.inventory.stop)
        self.service=audio_listening.Listening(self.audio,route_factory=self.factory,autostart=False)
        self.addCleanup(self.service.close)

    def speech(self):
        samples=array.array('h',[1200,-1200]*3200+[0]*24000)
        self.route.read.return_value=samples.tobytes();self.service.step();self.route.read.return_value=b''

    def finish_asr(self):
        self.audio.get.return_value=dict(status='done',result=dict(text='Fala do aplicativo',speaker='usuario'))
        self.service.step()

    def test_two_entities_share_capture_and_transcription_with_unknown_speaker(self):
        self.service.open('hoshino','entrada','fixture-source','ativa')
        self.service.open('lilith','entrada','fixture-source','passiva')
        self.assertEqual(self.factory.call_count,1)
        self.speech();self.assertEqual(self.audio.submit_environment.call_count,1)
        self.finish_asr()
        h=self.service.recent('hoshino',0)['items'];l=self.service.recent('lilith',0)['items']
        self.assertEqual(len(h),1);self.assertEqual(len(l),1)
        self.assertEqual(h[0]['speaker'],'desconhecido');self.assertEqual(l[0]['attention'],'passiva')
        self.assertEqual(h[0]['source_id'],'fixture-source')

    def test_close_reopen_discards_old_transcription(self):
        self.service.open('hoshino','entrada','fixture-source','ativa');self.speech()
        self.service.stop('hoshino','entrada')
        self.service.open('hoshino','entrada','fixture-source','ativa');self.finish_asr()
        self.assertEqual(self.service.recent('hoshino',0)['items'],[])

    def test_ignore_and_permission_revocation_stop_actual_capture(self):
        self.service.open('hoshino','entrada','fixture-source','ativa');self.speech()
        self.service.attention('hoshino','entrada','ignorar');self.finish_asr()
        self.route.close.assert_called_once();self.assertEqual(self.service.recent('hoshino',0)['items'],[])
        self.service.open('lilith','entrada','fixture-source','ativa')
        self.policy.stop()
        with patch('core.audio_listening.ui_policy.capability_allowed',return_value=False):self.service.step()
        self.assertEqual(self.route.close.call_count,2)

    def test_source_loss_does_not_fall_back_and_held_results_are_discarded(self):
        self.service.open('hoshino','entrada','fixture-source','ativa');self.speech()
        self.route.valid.return_value=False;self.finish_asr()
        self.assertEqual(self.service.recent('hoshino',0)['items'],[])
        self.assertEqual(self.factory.call_count,1)
        self.assertEqual(self.service.state('hoshino')['channels'][0]['status'],'indisponivel')

    def test_late_subscriber_cannot_receive_audio_from_before_subscription(self):
        self.service.open('hoshino','entrada','fixture-source','ativa');self.speech()
        self.service.open('lilith','entrada','fixture-source','ativa');self.finish_asr()
        self.assertEqual(self.service.recent('lilith',0)['items'],[])
        self.assertEqual(len(self.service.recent('hoshino',0)['items']),1)

class RunnerClient(unittest.TestCase):
    def test_supervised_runner_does_not_start_private_asr_when_central_is_unavailable(self):
        import os
        from social import escuta
        with patch.dict(os.environ,HOSHINO_CENTRAL_LISTENING='1'),patch.object(escuta,'_call',side_effect=RuntimeError('Central indisponível')):
            from tools import transcricao
            with patch.object(transcricao,'Transcritor') as private:
                self.assertIn('indisponível',escuta.ouvir('jogo','Minecraft'))
                private.assert_not_called()

if __name__=='__main__':unittest.main()
