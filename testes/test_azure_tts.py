"""Azure inteiramente simulado: nenhuma credencial real, quota ou rede."""
import io
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from core import tts_router as tts
from core.audio_text import SentenceBuffer, sentence_chunks
from core.audio_service import Worker
from core import gpu_metrics
from test_audio_service import wav_bytes


class AzureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tts-azure-mock-')
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)/'speech.wav'
        self.cancel = threading.Event()
        self.secret = 'MOCK-SECRET-NOT-A-REAL-KEY'
        self.env = patch.dict(os.environ, {'AZURE_SPEECH_KEY':self.secret,
            'AZURE_SPEECH_REGION':'brazilsouth'}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
        self.raw_emit=tts.diagnostics.emit
        self.events = patch.object(tts.diagnostics,'emit')
        self.logs = self.events.start(); self.addCleanup(self.events.stop)
        self.router = tts.TTSRouter({'backend':'kokoro','azure':{'timeout_seconds':1}})
        def local():
            self.output.write_bytes(wav_bytes())
            return {'voice':'Serena'}
        self.local = Mock(side_effect=local)
        self.qwen = Mock(side_effect=local)

    def run_tts(self, entity='hoshino'):
        return self.router.synthesize('Olá <mundo> & você.',self.output,entity,self.cancel,
                                     self.local,fallback=self.qwen)

    def assert_no_secret(self):
        self.assertNotIn(self.secret,repr(self.logs.call_args_list))
        self.assertNotIn(self.secret,repr(self.router.state()))

    def test_missing_key_keeps_existing_local_provider(self):
        os.environ.pop('AZURE_SPEECH_KEY')
        with patch.object(tts,'urlopen') as net:
            self.assertEqual(self.run_tts()['provider'],'kokoro')
        net.assert_not_called(); self.qwen.assert_not_called(); self.local.assert_called_once()
        self.assert_no_secret()

    def test_generic_diagnostics_and_sqlite_mirror_redact_subscription_secret(self):
        with patch('core.history.event') as mirror:
            record=self.raw_emit('test.azure_redaction',header={'Ocp-Apim-Subscription-Key':self.secret},
                                 output='Azure error '+self.secret,complete_history='x'*3000)
        self.assertNotIn(self.secret,repr(record)); self.assertNotIn(self.secret,repr(mirror.call_args))
        self.assertEqual(record['data']['header']['Ocp-Apim-Subscription-Key'],'[REDACTED]')
        self.assertEqual(mirror.call_args.kwargs['data']['complete_history'],'x'*3000)
        with patch.dict(os.environ,{'CUSTOM_SPEECH_CREDENTIAL':self.secret}),\
             patch.object(tts.diagnostics,'_speech_secret_env_names',return_value={'CUSTOM_SPEECH_CREDENTIAL'}):
            self.assertNotIn(self.secret,repr(tts.diagnostics._redact({'CUSTOM_SPEECH_CREDENTIAL':self.secret,
                                                                     'error':'falha '+self.secret})))

    def test_default_local_qwen_and_disabled_azure(self):
        self.router = tts.TTSRouter({'backend':'qwen3_tts','azure':{'enabled':False}})
        with patch.object(tts,'urlopen') as net:
            self.assertEqual(self.run_tts()['provider'],'qwen3_tts')
        net.assert_not_called()

    def test_standard_separate_voices_and_ssml_escaping(self):
        observed = []
        def respond(request, timeout):
            observed.append(request)
            self.assertEqual(timeout,1)
            return io.BytesIO(wav_bytes(rate=24000))
        with patch.object(tts,'urlopen',side_effect=respond):
            for entity in ('hoshino','lilith'):
                self.assertEqual(self.run_tts(entity)['provider'],'azure')
        self.local.assert_not_called(); self.qwen.assert_not_called()
        self.assertNotEqual(self.router.voice('hoshino'),self.router.voice('lilith'))
        for req in observed:
            self.assertEqual(req.full_url,'https://brazilsouth.tts.speech.microsoft.com/cognitiveservices/v1')
            self.assertIn(b'&lt;mundo&gt; &amp;',req.data)
            self.assertEqual(req.get_header('Ocp-apim-subscription-key'),self.secret)
            self.assertNotIn('Ocp-apim-subscription-key',req.headers)  # Não propagar em redirects.
            self.assertEqual(req.get_header('X-microsoft-outputformat'),'riff-24khz-16bit-mono-pcm')
        self.assert_no_secret()

    def test_voice_env_override_rejects_hd_multilingual_and_other_language(self):
        for value in ('pt-BR-Thalita:DragonHDLatestNeural','pt-BR-ThalitaMultilingualNeural','en-US-JennyNeural'):
            os.environ['AZURE_TTS_VOICE_LILITH']=value
            with self.assertRaises(tts.AzureFailure): self.router.voice('lilith')
            with patch.object(tts,'urlopen') as net:
                self.assertEqual(self.run_tts('lilith')['provider'],'qwen3_tts')
            net.assert_not_called()
        os.environ['AZURE_TTS_VOICE_LILITH']='pt-BR-YaraNeural'
        self.assertEqual(self.router.voice('lilith'),'pt-BR-YaraNeural')

    def test_remote_failures_fall_back_to_qwen_once_without_secrets(self):
        failures = [(HTTPError('mock',429,self.secret,{},None),'quota'),
                    (HTTPError('mock',401,self.secret,{},None),'auth'),
                    (HTTPError('mock',503,self.secret,{},None),'http_503'),
                    (URLError(self.secret),'network'),(TimeoutError(self.secret),'timeout'),
                    (RuntimeError(self.secret),'provider_error')]
        for error,code in failures:
            with self.subTest(code=code):
                self.router.cooldown_until=0; self.qwen.reset_mock()
                with patch.object(tts,'urlopen',side_effect=error): result=self.run_tts()
                self.assertEqual(result['provider'],'qwen3_tts'); self.assertEqual(result['failure'],code)
                self.qwen.assert_called_once(); self.local.assert_not_called(); self.assert_no_secret()

    def test_corrupt_wav_falls_back_and_cooldown_skips_next_request(self):
        with patch.object(tts,'urlopen',return_value=io.BytesIO(b'not WAV')) as net:
            result=self.run_tts()
            self.assertEqual(result['failure'],'invalid_audio')
            self.assertEqual(self.run_tts()['provider'],'qwen3_tts')
            net.assert_called_once()
        self.assertEqual(self.qwen.call_count,2)
        self.assertEqual(self.router.state()['preferred'],'qwen3_tts')

    def test_malformed_azure_settings_do_not_break_local_fallback(self):
        self.router=tts.TTSRouter({'backend':'kokoro','azure':False})
        with patch.object(tts,'urlopen') as net: self.assertEqual(self.run_tts()['provider'],'kokoro')
        net.assert_not_called()
        self.router=tts.TTSRouter({'backend':'kokoro','azure':{'cooldown_seconds':None,'timeout_seconds':'invalid'}})
        with patch.object(tts,'urlopen',side_effect=URLError(self.secret)):
            self.assertEqual(self.run_tts()['provider'],'qwen3_tts')
        self.assert_no_secret()

    def test_cancel_before_request_never_calls_azure_or_local(self):
        self.cancel.set()
        with patch.object(tts,'urlopen') as net, self.assertRaises(tts.SpeechCancelled): self.run_tts()
        net.assert_not_called(); self.local.assert_not_called(); self.qwen.assert_not_called()

    def test_cancel_pending_network_does_not_fallback_or_write_late_audio(self):
        began=threading.Event(); release=threading.Event(); ended=threading.Event()
        def slow(*_args):
            began.set(); release.wait(3); ended.set()
            return wav_bytes(),{'provider':'azure','voice':'pt-BR-FranciscaNeural'}
        outcome=[]
        def run():
            try: self.run_tts()
            except tts.SpeechCancelled: outcome.append('cancelled')
        with patch.object(self.router,'_fetch_audio',side_effect=slow):
            thread=threading.Thread(target=run); thread.start()
            self.assertTrue(began.wait(1)); self.cancel.set(); thread.join(1)
            release.set(); self.assertTrue(ended.wait(1)); thread.join(1)
        self.assertEqual(outcome,['cancelled']); self.assertFalse(self.output.exists())
        self.qwen.assert_not_called()

    def test_absolute_deadline_does_not_overwrite_local_with_late_result(self):
        release=threading.Event(); ended=threading.Event()
        def slow(*_args):
            release.wait(3); ended.set()
            return b'late-remote-data',{'provider':'azure','voice':'pt-BR-FranciscaNeural'}
        with patch.object(self.router,'_fetch_audio',side_effect=slow):
            start=time.monotonic(); result=self.run_tts(); elapsed=time.monotonic()-start
            before=self.output.read_bytes(); release.set(); self.assertTrue(ended.wait(1))
        self.assertEqual(result['failure'],'timeout'); self.assertLess(elapsed,2)
        self.assertEqual(self.output.read_bytes(),before); self.qwen.assert_called_once()

    def test_local_worker_does_not_receive_default_or_custom_secret_environment(self):
        python=Path(self.tmp.name)/'python'; python.touch()
        process=Mock(stdout=io.StringIO(''),stdin=io.StringIO(),poll=Mock(return_value=None))
        worker=Worker(self.tmp.name,python,'fake.py',secret_env_names=('CUSTOM_SPEECH_KEY',))
        with patch.dict(os.environ,{'CUSTOM_SPEECH_KEY':self.secret,'VISIBLE_SETTING':'safe'}),\
             patch('core.audio_service.subprocess.Popen',return_value=process) as spawn:
            worker._start(); worker.close()
        env=spawn.call_args.kwargs['env']
        self.assertNotIn('AZURE_SPEECH_KEY',env); self.assertNotIn('CUSTOM_SPEECH_KEY',env)
        self.assertEqual(env['VISIBLE_SETTING'],'safe')

    def test_qwen_cold_start_requires_known_free_ram_without_swap_assumption(self):
        python=Path(self.tmp.name)/'python'; python.touch()
        worker=Worker(self.tmp.name,python,'fake.py',{'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts'})
        for available in (None,2*gpu_metrics.GIB):
            with patch.object(gpu_metrics,'ram_available',return_value=available),\
                 patch('core.audio_service.subprocess.Popen') as spawn,self.assertRaisesRegex(RuntimeError,'RAM'):
                worker._start()
            spawn.assert_not_called()

    def test_local_start_waits_for_owned_image_to_release_ram_before_loading(self):
        python=Path(self.tmp.name)/'python'; python.touch()
        worker=Worker(self.tmp.name,python,'fake.py',{'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts'})
        process=Mock(stdout=io.StringIO(''),stdin=io.StringIO(),poll=Mock(return_value=None))
        with patch.object(gpu_metrics,'ram_available',side_effect=[2*gpu_metrics.GIB,20*gpu_metrics.GIB]),\
             patch('core.audio_service.resource_manager.status',return_value=[{'owner':'image'}]),\
             patch('core.audio_service.subprocess.Popen',return_value=process) as spawn:
            worker._start(self.cancel); worker.close()
        spawn.assert_called_once()


class SentenceTests(unittest.TestCase):
    def test_incomplete_tokens_are_held_and_sentences_not_duplicated(self):
        buf=SentenceBuffer()
        self.assertEqual(buf.push('Oi'),[])
        self.assertEqual(buf.push('Oi.'),[])
        self.assertEqual(buf.push('Oi. Tudo'),['Oi.'])
        self.assertEqual(buf.push('Oi. Tudo bem! Próxima'),['Tudo bem!'])
        self.assertEqual(buf.push('Oi. Tudo bem! Próxima frase',final=True),['Próxima frase'])
        self.assertEqual(buf.push('Oi. Tudo bem! Próxima frase',final=True),[])

    def test_abbreviation_decimal_and_open_code_are_not_cut(self):
        self.assertEqual(sentence_chunks('Dr. Gustavo viu 3.14. Tudo certo!'),
                         ['Dr. Gustavo viu 3.14.','Tudo certo!'])
        buf=SentenceBuffer()
        self.assertEqual(buf.push('```python\nx. Ainda'),[])
        self.assertEqual(buf.push('```python\nx. Ainda``` Pronto.',final=True),
                         ['```python\nx. Ainda``` Pronto.'])
        self.assertEqual(SentenceBuffer().push('[link. Ainda'),[])

    def test_prefix_rewrite_requires_cancellation(self):
        buf=SentenceBuffer(); self.assertEqual(buf.push('Primeira. Segunda'),['Primeira.'])
        with self.assertRaises(ValueError): buf.push('Outra. Segunda')


if __name__=='__main__': unittest.main()
