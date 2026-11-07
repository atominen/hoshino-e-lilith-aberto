"""ElevenLabs no roteador real, com transporte mockado e quota zero."""
import io
import json
import os
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from core import diagnostics, tts_router as tts
from core.audio_service import Worker
from core import speech_stream
from test_audio_service import ServiceFixture


class ElevenLabsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='eleven-mock-')
        self.addCleanup(self.tmp.cleanup)
        self.output=Path(self.tmp.name)/'speech.wav'
        self.cancel=threading.Event()
        self.secret='MOCK-ELEVEN-NOT-A-REAL-KEY'
        env=patch.dict(os.environ,{'ELEVENLABS_API_KEY':self.secret},clear=True)
        env.start(); self.addCleanup(env.stop)
        logs=patch.object(tts.diagnostics,'emit'); self.logs=logs.start(); self.addCleanup(logs.stop)
        self.router=tts.TTSRouter({'backend':'kokoro','elevenlabs':{'enabled':True,'timeout_seconds':1,
                                  'voices':{'hoshino':'voiceHoshino','lilith':'voiceLilith'}}})
        self.local=Mock(return_value={'voice':'Dora'})
        self.qwen=Mock(return_value={'voice':'Serena'})

    def run_tts(self, entity='hoshino'):
        return self.router.synthesize('Olá. Tudo bem?',self.output,entity,self.cancel,self.local,fallback=self.qwen)

    def assert_safe(self):
        self.assertNotIn(self.secret,repr(self.logs.call_args_list))
        self.assertNotIn(self.secret,repr(self.router.state()))

    def test_voice_ids_model_pcm_and_request_contract(self):
        observed=[]
        def response(req,timeout):
            observed.append(req)
            self.assertEqual(timeout,1)
            return io.BytesIO(b'\0\0'*2400)
        with patch.object(tts,'urlopen',side_effect=response):
            for entity in ('hoshino','lilith'):
                result=self.run_tts(entity)
                self.assertEqual(result['provider'],'elevenlabs')
                self.assertEqual(result['sample_rate'],24000)
                self.assertAlmostEqual(result['duration_seconds'],.1)
                with wave.open(str(self.output),'rb') as wav:
                    self.assertEqual((wav.getnchannels(),wav.getsampwidth(),wav.getnframes()),(1,2,2400))
        self.assertNotEqual(observed[0].full_url,observed[1].full_url)
        for req in observed:
            self.assertTrue(req.full_url.startswith('https://api.elevenlabs.io/v1/text-to-speech/voice'))
            self.assertTrue(req.full_url.endswith('?output_format=pcm_24000'))
            self.assertEqual(req.get_header('Xi-api-key'),self.secret)
            self.assertNotIn('Xi-api-key',req.headers)
            self.assertEqual(json.loads(req.data)['model_id'],'eleven_multilingual_v2')
            self.assertNotIn('language_code',json.loads(req.data))
        self.local.assert_not_called(); self.qwen.assert_not_called(); self.assert_safe()

    def test_no_key_preserves_configured_local_without_remote_request(self):
        os.environ.pop('ELEVENLABS_API_KEY')
        with patch.object(tts,'urlopen') as net:
            self.assertEqual(self.run_tts()['provider'],'kokoro')
        net.assert_not_called(); self.local.assert_called_once(); self.qwen.assert_not_called()

    def test_disabled_eleven_is_never_called(self):
        self.router.elevenlabs['enabled']=False
        with patch.object(tts,'urlopen') as net:
            self.assertEqual(self.run_tts()['provider'],'kokoro')
        net.assert_not_called()

    def test_existing_azure_preference_is_preserved_but_config_can_choose_eleven(self):
        with patch.dict(os.environ,{'AZURE_SPEECH_KEY':'MOCK-AZURE','AZURE_SPEECH_REGION':'brazilsouth'}):
            self.assertEqual(self.router.state()['preferred'],'azure')
            self.router.settings['preferred_provider']='elevenlabs'
            self.assertEqual(self.router.state()['preferred'],'elevenlabs')

    def test_model_and_voice_can_be_overridden_by_environment(self):
        with patch.dict(os.environ,{'ELEVENLABS_TTS_MODEL':'eleven_flash_v2_5','ELEVENLABS_TTS_VOICE_LILITH':'anotherVoice'}),\
             patch.object(tts,'urlopen',return_value=io.BytesIO(b'\0\0'*40)) as net:
            result=self.run_tts('lilith')
        self.assertEqual(result['voice'],'anotherVoice')
        self.assertEqual(json.loads(net.call_args.args[0].data)['model_id'],'eleven_flash_v2_5')

    def test_missing_or_invalid_voice_and_model_use_qwen_without_network(self):
        for variable,value in [('ELEVENLABS_TTS_VOICE_LILITH',''),('ELEVENLABS_TTS_VOICE_LILITH','../../secret'),
                               ('ELEVENLABS_TTS_MODEL','https://arbitrary.example')]:
            with patch.dict(os.environ,{variable:value}),patch.object(tts,'urlopen') as net:
                self.assertEqual(self.run_tts('lilith')['provider'],'qwen3_tts')
            net.assert_not_called()
        self.assert_safe()

    def test_failure_uses_qwen_once_with_cooldown_and_no_secret(self):
        errors=[(HTTPError('mock',429,self.secret,{},None),'quota'),
                (HTTPError('mock',401,self.secret,{},None),'auth'),
                (HTTPError('mock',503,self.secret,{},None),'http_503'),
                (URLError(self.secret),'network'),(TimeoutError(self.secret),'timeout'),
                (RuntimeError(self.secret),'provider_error')]
        for error,code in errors:
            self.router.eleven_cooldown_until=0; self.qwen.reset_mock()
            with self.subTest(code=code),patch.object(tts,'urlopen',side_effect=error) as net:
                result=self.run_tts(); self.assertEqual(result['failure'],code)
                self.assertEqual(result['fallback_from'],'elevenlabs')
                self.assertEqual(result['provider'],'qwen3_tts')
                self.qwen.assert_called_once()
                self.assertEqual(self.run_tts()['provider'],'qwen3_tts')
                net.assert_called_once()
            self.local.assert_not_called(); self.assert_safe()

    def test_invalid_pcm_is_not_published_as_valid_wav(self):
        for data in (b'',b'odd',b'x'*(24000*2*600+2)):
            self.router.eleven_cooldown_until=0
            with patch.object(tts,'urlopen',return_value=io.BytesIO(data)):
                self.assertEqual(self.run_tts()['failure'],'invalid_audio')
        self.assertFalse(self.output.exists())

    def test_cancel_before_request_does_not_start_remote_or_fallback(self):
        self.cancel.set()
        with patch.object(tts,'urlopen') as net,self.assertRaises(tts.SpeechCancelled):
            self.run_tts()
        net.assert_not_called(); self.qwen.assert_not_called(); self.local.assert_not_called()

    def test_cancel_pending_request_rejects_late_audio_and_no_fallback(self):
        began,release=threading.Event(),threading.Event()
        def response(*args,**kwargs):
            began.set(); release.wait(2); return io.BytesIO(b'\0\0'*40)
        failures=[]
        def run():
            try:self.run_tts()
            except tts.SpeechCancelled: failures.append('cancelled')
        with patch.object(tts,'urlopen',side_effect=response):
            thread=threading.Thread(target=run); thread.start()
            self.assertTrue(began.wait(1)); self.cancel.set(); thread.join(1); release.set()
            self.assertFalse(thread.is_alive())
        self.assertEqual(failures,['cancelled'])
        self.assertFalse(self.output.exists()); self.qwen.assert_not_called()

    def test_deadline_never_overwrites_fallback_with_late_response(self):
        release=threading.Event()
        def response(*args,**kwargs):
            release.wait(3); return io.BytesIO(b'\0\0'*40)
        def local():
            self.output.write_bytes(b'MOCK LOCAL'); return {}
        self.qwen.side_effect=local
        with patch.object(tts,'urlopen',side_effect=response):
            result=self.run_tts(); release.set(); time.sleep(.07)
        self.assertEqual(result['failure'],'timeout')
        self.assertEqual(self.output.read_bytes(),b'MOCK LOCAL')

    def test_worker_does_not_inherit_provider_keys_even_with_custom_name(self):
        python=Path(self.tmp.name)/'python'; python.touch()
        worker=Worker(self.tmp.name,python,'mock_script.py',secret_env_names=['CUSTOM_ELEVEN_KEY'])
        process=Mock(stdout=io.StringIO(''),stdin=io.StringIO(),poll=Mock(return_value=None))
        with patch.dict(os.environ,{'CUSTOM_ELEVEN_KEY':self.secret}),\
             patch('core.audio_service.subprocess.Popen',return_value=process) as spawn:
            # Spawn itself is mocked: neither model nor sound device is opened.
            worker._start()
        environment=spawn.call_args.kwargs['env']
        self.assertNotIn('ELEVENLABS_API_KEY',environment)
        self.assertNotIn('CUSTOM_ELEVEN_KEY',environment)

    def test_generic_diagnostics_redact_eleven_key(self):
        record=diagnostics._redact({'xi-api-key':self.secret,'error':'failed '+self.secret})
        self.assertNotIn(self.secret,repr(record))

    def test_xi_api_key_header_is_redacted_without_environment_lookup(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(diagnostics._redact({'xi-api-key':'MOCK-OLD-KEY'}),{'xi-api-key':'[REDACTED]'})

    def test_json_error_with_http_200_is_not_wrapped_as_pcm(self):
        response=io.BytesIO(b'{"error":"mock"}')
        response.headers={'Content-Type':'application/json'}
        with patch.object(tts,'urlopen',return_value=response):
            self.assertEqual(self.run_tts()['failure'],'invalid_audio')
        self.assertFalse(self.output.exists())


class ElevenServiceTests(ServiceFixture):
    def configured(self):
        self.service.router=tts.TTSRouter({'backend':'qwen3_tts','elevenlabs':{'enabled':True,
            'voices':{'hoshino':'voiceH','lilith':'voiceL'},'timeout_seconds':1}})

    def test_real_service_preserves_sentence_order_with_mock_eleven_pcm(self):
        self.configured(); texts=[]
        def response(request,timeout):
            texts.append(json.loads(request.data)['text']); return io.BytesIO(b'\0\0'*2400)
        with patch.dict(os.environ,{'ELEVENLABS_API_KEY':'MOCK-ONLY'}),patch.object(tts,'urlopen',side_effect=response):
            result=self.wait_done(self.service.submit_speech('hoshino',text='Primeira frase. Segunda frase!'))
        self.assertEqual(result['status'],'done')
        self.assertEqual(texts,['Primeira frase.','Segunda frase!'])
        self.assertEqual([c['index'] for c in result['result']['chunks']],[0,1])
        self.assertEqual(result['result']['providers'],['elevenlabs','elevenlabs'])
        self.service.tts.call.assert_not_called()

    def test_invalidated_producer_cancels_pending_remote_before_audio_publication(self):
        self.configured()
        started,release=threading.Event(),threading.Event(); self.addCleanup(release.set)
        def response(*args,**kwargs):
            started.set(); release.wait(2); return io.BytesIO(b'\0\0'*2400)
        stream=speech_stream.SpeechStream('hoshino','localhub'); stream.push('Primeira frase. Próxima')
        with patch.dict(os.environ,{'ELEVENLABS_API_KEY':'MOCK-ONLY'}),patch.object(tts,'urlopen',side_effect=response):
            job=self.service.submit_stream('hoshino',stream.id)
            self.assertTrue(started.wait(1)); stream.stop('valid_user_interruption')
            self.wait_idle_bounded(); release.set()
        self.assertEqual(self.service.get(job['id'])['status'],'interrupted')
        self.assertFalse(self.service.get(job['id'])['result'])
        self.service.tts.call.assert_not_called()

    def test_entity_interruption_preserves_asr_other_entity_and_new_reply(self):
        from core import job_bus
        # Diário/controle isolados, sem iniciar inferência para fabricar os jobs.
        with patch.object(self.service,'cancel',return_value={'status':'cancel_requested'}) as cancel:
            now=time.time()
            for identifier,entity,kind,created in [('oldH','hoshino','audio_tts',now-1),
                    ('oldL','lilith','audio_tts',now-1),('asrH','hoshino','audio_asr',now-1),
                    ('newH','hoshino','audio_tts',now+1)]:
                job_bus.publish(identifier,entity,'queued',kind=kind)
                self.service.cancels[identifier]=threading.Event()
                db=job_bus._conn(); db.execute('UPDATE jobs SET created_at=? WHERE id=?',(created,identifier)); db.commit(); db.close()
            self.assertEqual(self.service.interrupt_entity('hoshino',before=now),['oldH'])
            cancel.assert_called_once_with('oldH')
            self.service.cancels.clear()


if __name__=='__main__': unittest.main()
