"""Reprodução factual e duplex básico: bancos temporários, nenhum modelo/quota."""
import importlib
import threading
import time
import unittest
from unittest.mock import patch
from test_audio_service import ServiceFixture, wav_bytes, transcript
from core import job_bus, speech_stream
from core import resource_manager


class PlaybackTests(ServiceFixture):
    def test_delayed_progress_does_not_revive_stale_speaking(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Olá.');self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        play=job_bus.get(job['id'])['details']['playback'];play['at']-=10
        job_bus.annotate(job['id'],'hoshino',playback=play)
        self.service.playback_event('hoshino',job['id'],'progress',0,'native',position=.1,sequence=2,observed_at=time.time()-8)
        self.assertFalse(mod.snapshot('hoshino')['speaking'])

    def test_next_chunk_progress_is_bounded_to_that_chunk_not_previous_duration(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Primeira. Segunda!');self.wait_done(job)
        chunks=job_bus.get(job['id'])['details']['chunks'];chunks[0]['duration_seconds']=30;chunks[1]['duration_seconds']=5
        job_bus.annotate(job['id'],'hoshino',chunks=chunks)
        self.service.playback_event('hoshino',job['id'],'started',0,'native',sequence=1)
        self.service.playback_event('hoshino',job['id'],'ended',0,'native',sequence=2)
        self.service.playback_event('hoshino',job['id'],'progress',1,'native',position=1,sequence=3)
        self.assertEqual(mod.snapshot('hoshino')['own'][0]['position_seconds'],1)

    def test_waiting_asr_has_priority_over_next_tts_sentence(self):
        from pathlib import Path
        first=threading.Event();release=threading.Event();asr_at_gate=threading.Event();order=[]
        self.addCleanup(release.set)
        def synth(request,*args):
            order.append('tts')
            if len(order)==1:first.set();release.wait(2)
            Path(request['output']).write_bytes(wav_bytes());return {}
        self.service.tts.call.side_effect=synth
        self.service.asr.call.side_effect=lambda *args:order.append('asr') or transcript()
        real_lease=resource_manager.lease
        def scheduling_gap(resource,owner,**kwargs):
            if owner=='audio_asr':asr_at_gate.set();time.sleep(.15)
            return real_lease(resource,owner,**kwargs)
        with patch.object(resource_manager,'lease',side_effect=scheduling_gap):
            self.service.submit_speech('hoshino',text='Primeira. Segunda!');self.assertTrue(first.wait(2))
            self.service.submit_transcription('hoshino',wav_bytes());self.assertTrue(asr_at_gate.wait(2));release.set()
            self.service.pending.join()
        self.assertEqual(order,['tts','asr','tts'])

    def test_busy_audio_compute_waits_without_losing_capture_or_speech(self):
        real_lease=resource_manager.lease
        def faster_legacy_timeout(*args,**kwargs):
            if kwargs.get('wait')==20:kwargs['wait']=.02
            return real_lease(*args,**kwargs)
        with patch.object(resource_manager,'lease',side_effect=faster_legacy_timeout):
            for kind in ('asr','tts'):
                with real_lease('cpu_audio','fixture-held'):
                    job=(self.service.submit_transcription('hoshino',wav_bytes()) if kind=='asr'
                         else self.service.submit_speech('hoshino',text='Olá.'))
                    time.sleep(.13)
                    self.assertNotIn(self.service.get(job['id'])['status'],job_bus.TERMINAL)
                self.wait_done(job)

    def test_public_context_never_contains_private_spoken_text(self):
        from core import interentity as bus
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Segredo confidencial.');self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        message=bus.send('usuario','hoshino','Olá sala',chat_scope='global')
        incoming=next(m for m in bus.peek('hoshino') if m['id']==message['id'])
        token=bus.processing_message.set(incoming)
        try:
            self.assertNotIn('Segredo confidencial',mod.context('hoshino'))
            self.assertNotIn('Segredo confidencial',str(mod.snapshot('hoshino')))
        finally:bus.processing_message.reset(token)

    def test_explicit_interrupt_cancels_done_synthesis_after_progress(self):
        job=self.service.submit_speech('hoshino',text='Olá.');self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        self.service.playback_event('hoshino',job['id'],'progress',0,'native',position=.1)
        self.service.interrupt_entity('hoshino')
        self.assertTrue(job_bus.get(job['id'])['details'].get('playback_cancel_at'))

    def test_stop_covers_done_synthesis_without_receipt_and_stale_playback(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Olá.');self.wait_done(job)
        self.assertEqual(mod.request_stop('hoshino')['requested'],1)
        self.assertTrue(job_bus.get(job['id'])['details'].get('playback_cancel_at'))
        other=self.service.submit_speech('hoshino',text='Outra.');self.wait_done(other)
        self.service.playback_event('hoshino',other['id'],'started',0,'native')
        value=job_bus.get(other['id'])['details']['playback'];value['at']-=10
        job_bus.annotate(other['id'],'hoshino',playback=value)
        self.assertTrue(mod.request_stop('hoshino')['player_confirmation_pending'])
        self.assertTrue(job_bus.get(other['id'])['details'].get('playback_cancel_at'))

    def test_mutating_stop_is_offered_only_with_voice_intent_or_own_active_voice(self):
        from core import dispatch
        def names():return {s['function']['name'] for s in dispatch.esquemas('oi tudo bem',incluir_proprias=False)}
        self.assertNotIn('parar_voz',names())
        job=self.service.submit_speech('hoshino',text='Olá.');self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        with patch.object(dispatch.config,'ENTIDADE_ID','hoshino'):
            self.assertIn('parar_voz',names())

    def test_resident_tts_does_not_allow_asr_to_start_without_ram_headroom(self):
        from core import audio_service
        python=self.root/'python';python.touch()
        worker=audio_service.Worker(self.root,python,self.root/'audio_worker.py',{'HOSHINO_WHISPER':'large-v3'})
        with patch.object(audio_service.gpu_metrics,'ram_available',return_value=0),patch.object(audio_service.subprocess,'Popen',side_effect=AssertionError('Não iniciar processo')):
            with self.assertRaisesRegex(RuntimeError,'RAM'):worker._start()

    def test_new_central_does_not_adopt_previous_player_jobs(self):
        from core.audio_service import AudioService
        job=self.service.submit_speech('hoshino',text='Olá.');self.wait_done(job)
        other=AudioService(self.root);self.addCleanup(other.close)
        with self.assertRaisesRegex(ValueError,'Central'):
            other.playback_event('hoshino',job['id'],'started',0,'native')

    def test_ended_receipt_arriving_before_started_cannot_resurrect_speech(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Olá.')
        self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'ended',0,'native',sequence=2)
        self.service.playback_event('hoshino',job['id'],'started',0,'native',sequence=1)
        self.assertEqual(mod.snapshot('hoshino')['own'][0]['state'],'finished')

    def test_stop_between_chunks_cancels_remaining_speech(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Primeira. Segunda!')
        self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        self.service.playback_event('hoshino',job['id'],'ended',0,'native')
        self.assertEqual(mod.request_stop('hoshino')['requested'],1)

    def playback(self):
        try:return importlib.import_module('core.audio_playback')
        except ImportError:self.fail('Percepção factual de reprodução ainda ausente')

    def test_synthesis_done_is_not_speech_and_progress_expires(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Primeira frase. Segunda frase.')
        self.wait_done(job)
        self.assertFalse(mod.snapshot('hoshino')['speaking'])
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        state=mod.snapshot('hoshino');self.assertEqual(state['speaking'],['hoshino'])
        self.assertEqual(state['own'][0]['current_text'],'Primeira frase.')
        self.assertEqual(mod.snapshot('lilith')['own'],[])
        self.assertNotIn('Primeira frase',str(mod.snapshot('lilith')))
        self.assertFalse(mod.snapshot('hoshino',now=time.time()+10)['speaking'])
        self.service.playback_event('hoshino',job['id'],'ended',0,'native')
        self.assertEqual(mod.snapshot('hoshino')['own'][0]['completed_text'],['Primeira frase.'])

    def test_late_progress_cannot_resurrect_ended_or_cancelled_playback(self):
        mod=self.playback();job=self.service.submit_speech('hoshino',text='Olá.')
        self.wait_done(job)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        self.service.playback_event('hoshino',job['id'],'ended',0,'native')
        self.service.playback_event('hoshino',job['id'],'progress',0,'native',position=.2)
        self.service.playback_event('hoshino',job['id'],'started',0,'native')
        self.assertFalse(mod.snapshot('hoshino')['speaking'])
        self.assertEqual(mod.snapshot('hoshino')['own'][0]['state'],'finished')

    def test_stop_requests_only_own_voice_and_does_not_claim_player_stopped(self):
        mod=self.playback()
        jobs=[self.service.submit_speech(e,text='Olá.') for e in ('hoshino','lilith')]
        self.service.pending.join()
        for e,job in zip(('hoshino','lilith'),jobs):self.service.playback_event(e,job['id'],'started',0,'native')
        self.assertEqual(mod.request_stop('hoshino')['requested'],1)
        self.assertIn('hoshino',mod.snapshot('hoshino')['speaking'])
        self.assertNotIn('playback_cancel_at',job_bus.get(jobs[1]['id'])['details'])

    def test_asr_finishes_while_llm_speech_waits_for_next_sentence(self):
        stream=speech_stream.SpeechStream('hoshino','localhub');stream.push('Primeira. Próxima')
        self.addCleanup(stream.stop)
        voice=self.service.submit_stream('hoshino',stream.id)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and not (self.service.get(voice['id'])['result'] or {}).get('chunks'):time.sleep(.01)
        job=self.service.submit_transcription('hoshino',wav_bytes())
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and self.service.get(job['id'])['status'] not in job_bus.TERMINAL:time.sleep(.01)
        self.assertEqual(self.service.get(job['id'])['status'],'done')
        self.assertEqual(self.service.get(voice['id'])['status'],'running')
        stream.finish('Primeira. Próxima!')


if __name__=='__main__':
    unittest.main()
