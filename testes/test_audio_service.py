"""Áudio/HTTP/RPC: temporários e motores simulados, nunca hardware ou mentes."""
import importlib.util
import builtins
import contextlib
import io
import json
import queue
import subprocess
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from core import audio_service as audio, interentity as bus, job_bus, resource_manager
from core import audio_sources


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audio_test_launcher", ROOT / "iniciar_entidades.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def wav_bytes(seconds=0.5, rate=16000, channels=1, width=2):
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(round(seconds * rate) * channels * width))
    return data.getvalue()


def transcript(text="Olá, Gustavo. A imagem está pronta."):
    return {"text": text, "source": "browser_microphone", "speaker": "usuario",
            "speaker_basis": "source_role", "segments": [], "language": "pt",
            "metadata": {"speaker_identification_performed": False}}


class LiveASRContract:
    def live_meta(self,part=0,preview=False):
        return dict(id='a'*32,part=part,revision=part+1,preview=preview,session_id='session-one',scope='direct')

    def test_live_metadata_survives_job_and_preview_cannot_be_sent(self):
        job=self.service.submit_transcription('hoshino',wav_bytes(),source='native_microphone',utterance=self.live_meta(preview=True))
        state=self.wait_done(job)
        self.assertTrue(state['utterance']['preview'])
        with self.assertRaises(ValueError):
            launcher.audio_origin(self.service,'hoshino',dict(audio_job_id=job['id'],draft_origin=True,text=state['result']['text'],conversation_session_id='session-one',chat_scope='direct'))

    def test_live_origin_joins_final_parts_once_and_preserves_acoustic_signals(self):
        values=[dict(transcript('Uma frase.'),segments=[{'average_log_probability':-.2}]),
                dict(transcript('Com continuação.'),segments=[{'average_log_probability':-1.2,'no_speech_probability':.7}])]
        self.service.asr.call.side_effect=values;jobs=[]
        for i in range(2):
            job=self.service.submit_transcription('hoshino',wav_bytes(),utterance=self.live_meta(i));self.wait_done(job);jobs.append(job['id'])
        data=dict(audio_job_ids=jobs,draft_origin=True,text='Uma frase. Com continuação.',conversation_session_id='session-one',chat_scope='direct',automatic_asr=True)
        origin=launcher.audio_origin(self.service,'hoshino',data)
        self.assertEqual(origin['audio_job_ids'],jobs);self.assertEqual(origin['audio_job_id'],jobs[-1])
        self.assertEqual(origin['utterance_id'],'a'*32);self.assertFalse(origin['draft_reviewed'])
        self.assertEqual(origin['speech_perception']['minimum_average_log_probability'],-1.2)
        for change in ({'audio_job_ids':jobs[::-1]},{'audio_job_ids':[jobs[0],jobs[0]]},
                       {'conversation_session_id':'other'},{'chat_scope':'global'},
                       {'audio_job_ids':[jobs[1]]}):
            with self.subTest(change=change),self.assertRaises(ValueError):launcher.audio_origin(self.service,'hoshino',dict(data,**change))

    def test_live_origin_rejects_other_utterance_and_metadata_tampering(self):
        for change in ({'preview':'false'},{'part':True},{'session_id':''},{'scope':'private'},{'extra':1}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.service.submit_transcription('hoshino',wav_bytes(),utterance=dict(self.live_meta(),**change))
        ids=[]
        for i in range(2):
            m=self.live_meta(i);m['id']=('a' if i==0 else 'b')*32
            job=self.service.submit_transcription('hoshino',wav_bytes(),utterance=m);self.wait_done(job);ids.append(job['id'])
        with self.assertRaises(ValueError):launcher.audio_origin(self.service,'hoshino',dict(audio_job_ids=ids,draft_origin=True,text=transcript()['text'],conversation_session_id='session-one',chat_scope='direct'))

class ServiceFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="audio-service-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for entity in bus.ENTITIES:
            folder = self.root / "entidades" / entity
            folder.mkdir(parents=True)
            (folder / "entidade.json").write_text(json.dumps({"id": entity, "nome": entity.title(), "status": "ativa"}))
        for obj, name, value in [(bus, "DB_PATH", self.root / "bus.db"),
                                 (job_bus, "DB_PATH", self.root / "jobs.db"),
                                 (resource_manager, "DB_PATH", self.root / "resources.db"),
                                 (resource_manager, "LOCK_DIR", self.root / "locks"),
                                 (launcher, "ROOT", self.root)]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.service = audio.AudioService(self.root)
        self.service.asr = Mock(call=Mock(return_value=transcript()), alive=Mock(return_value=False))

        def synthesize(request, *_args):
            Path(request["output"]).write_bytes(wav_bytes())
            return {"ok": True}

        self.service.tts = Mock(call=Mock(side_effect=synthesize), alive=Mock(return_value=False))
        self.addCleanup(self.service.close)

    def wait_done(self, job, expected="done"):
        self.service.pending.join()
        state = self.service.get(job["id"])
        self.assertEqual(state["status"], expected, state)
        return state

    def wait_idle_bounded(self, seconds=3):
        deadline = time.monotonic() + seconds
        while self.service.pending.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        if self.service.pending.unfinished_tasks:
            # Uma regressão que mata _run não pode travar a própria limpeza da
            # suíte. Corrige apenas a contabilidade desta fixture e falha o teste.
            if self.service.thread and not self.service.thread.is_alive():
                while True:
                    try:
                        self.service.pending.get_nowait()
                    except queue.Empty:
                        break
                    self.service.pending.task_done()
                while self.service.pending.unfinished_tasks:
                    self.service.pending.task_done()
            self.fail("A fila de áudio não concluiu task_done após uma falha.")


class LiveASRTests(LiveASRContract,ServiceFixture):
    pass


class ServiceTests(ServiceFixture):
    def test_environment_transcript_is_volatile_not_in_durable_job_receipt(self):
        sentinel='PRIVATE_AMBIENT_SENTINEL'
        self.service.asr.call.return_value=dict(transcript(),text=sentinel)
        job=self.service.submit_environment('hoshino',wav_bytes());self.wait_done(job)
        self.assertNotIn(sentinel,json.dumps(job_bus.get(job['id'])))
        self.assertEqual(self.service.take_environment(job['id'])['result']['text'],sentinel)
        self.assertIsNone(self.service.take_environment(job['id'])['result'])

    def test_environment_uses_shared_asr_but_cannot_become_a_user_message(self):
        job=self.service.submit_environment('hoshino',wav_bytes())
        state=self.wait_done(job)
        self.assertEqual(state['kind'],'audio_environment')
        self.assertEqual(self.service.asr.call.call_args.args[0]['source'],'system_audio')
        with self.assertRaises(ValueError):
            launcher.audio_origin(self.service,'hoshino',dict(audio_job_id=job['id'],draft_origin=True,text='fixture'))

    def test_no_speech_code_survives_job_status(self):
        error=RuntimeError('Nenhuma fala aproveitável.');error.code='no_speech'
        self.service.asr.call.side_effect=error
        state=self.wait_done(self.service.submit_transcription('hoshino',wav_bytes()),'error')
        self.assertEqual(state.get('error_code'),'no_speech')
    def test_qwen_cpu_build_never_claims_gpu(self):
        worker=audio.Worker(self.root,Path('/fixture/python'),Path('/fixture/worker'),{'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts'})
        with patch.object(worker,'_qwen_gpu_available',return_value=False),patch.object(worker,'_call',return_value={'device':'cpu'}) as call,patch.object(resource_manager,'compute_lease',side_effect=AssertionError('no GPU')):
            self.assertEqual(worker.call({'op':'synthesize'},threading.Event(),10)['device'],'cpu');call.assert_called_once()
    def test_qwen_gpu_lease_scoped_and_owned_worker_closed_before_release(self):
        worker=audio.Worker(self.root,Path('/fixture/python'),Path('/fixture/worker'),{'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts'})
        order=[]
        @contextlib.contextmanager
        def lease(*args,**kwargs):
            self.assertEqual(kwargs['priority'],0);self.assertFalse(kwargs['overlap_safe']);self.assertTrue(kwargs['cpu_fallback']);self.assertEqual(kwargs['entity'],'lilith')
            order.append('acquire');yield {'backend':'gpu','token':'owned'};order.append('release')
        with patch.object(worker,'_qwen_gpu_available',return_value=True),patch.object(worker,'_call',side_effect=lambda *a:order.append('synthesize') or {}),patch.object(worker,'close',side_effect=lambda:order.append('close')),patch.object(resource_manager,'compute_lease',side_effect=lease):
            result=worker.call({'op':'synthesize','entity':'lilith'},threading.Event(),10)
        self.assertEqual(order,['acquire','close','synthesize','close','release']);self.assertEqual(result['device'],'hip');self.assertEqual(result['compute_lease'],'owned')
    def test_qwen_gpu_failure_closes_without_automatic_replay(self):
        worker=audio.Worker(self.root,Path('/fixture/python'),Path('/fixture/worker'),{'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts','HOSHINO_AUDIO_TTS_DEVICE':'hip'})
        order=[]
        @contextlib.contextmanager
        def lease(*a,**k):
            try:yield {'backend':'gpu','token':'owned'}
            finally:order.append('release')
        with patch.object(worker,'_qwen_gpu_available',return_value=True),patch.object(worker,'_call',side_effect=RuntimeError('failed')) as call,patch.object(worker,'close',side_effect=lambda:order.append('close')),patch.object(resource_manager,'compute_lease',side_effect=lease):
            with self.assertRaises(RuntimeError):worker.call({'op':'synthesize'},threading.Event(),10)
        self.assertEqual(order,['close','release']);call.assert_called_once()
    def test_qwen_rm_cpu_fallback_preserves_cpu_worker(self):
        worker=audio.Worker(self.root,Path('/fixture/python'),Path('/fixture/worker'),{'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts'})
        with patch.object(worker,'_qwen_gpu_available',return_value=True),patch.object(worker,'_call',return_value={}),patch.object(worker,'close') as close,patch.object(resource_manager,'compute_lease',return_value=contextlib.nullcontext({'backend':'cpu','token':'cpu'})):
            self.assertEqual(worker.call({'op':'synthesize'},threading.Event(),10)['device'],'cpu');close.assert_not_called()
    def test_storage_limit_and_free_space_fail_without_deleting_existing_audio(self):
        directory = self.root / "entidades/hoshino/runtime/audio/central"
        directory.mkdir(parents=True)
        existing = directory / "audio-existing.wav"
        existing.write_bytes(wav_bytes())
        before = existing.read_bytes()
        with patch.object(audio, "MAX_ENTITY_AUDIO_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "Cache"):
                self.service.submit_speech("hoshino", text="teste")
        with patch.object(audio.shutil, "disk_usage", return_value=SimpleNamespace(free=1)):
            with self.assertRaisesRegex(ValueError, "espaço"):
                self.service.submit_transcription("hoshino", wav_bytes())
        self.assertEqual(existing.read_bytes(), before)
        self.assertEqual(job_bus.status(), [])

    def test_asr_settings_are_shared_and_report_actual_configured_model(self):
        with patch.object(audio.config, "WHISPER_MODELO", "test-only-model"), \
                patch.object(audio.config, "WHISPER_BEAM_SIZE", 2), \
                patch.object(audio.audio_sources, "inventory", return_value={"sources": [], "streams": []}):
            service = audio.AudioService(self.root)
            self.addCleanup(service.close)
            self.assertEqual(service.state()["asr"]["model"], "test-only-model")
            self.assertEqual(service.asr.env["HOSHINO_WHISPER"], "test-only-model")
            self.assertEqual(service.asr.env["HOSHINO_WHISPER_BEAM"], "2")

    def test_wav_validation_rejects_invalid_truncated_and_limits(self):
        self.assertEqual(audio.validate_wav(wav_bytes())["sample_rate"], 16000)
        invalid = [b"", b"not WAV", wav_bytes()[:-10], wav_bytes(channels=2),
                   wav_bytes(width=1), wav_bytes(rate=6000), wav_bytes(seconds=.1), wav_bytes(seconds=61),
                   b"x" * (audio.MAX_INPUT_BYTES + 1)]
        for data in invalid:
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    audio.validate_wav(data)

    def test_transcription_is_draft_only_and_input_removed(self):
        with patch.object(bus, "send") as send:
            job = self.service.submit_transcription("lilith", wav_bytes())
            state = self.wait_done(job)
            self.assertEqual(state["entity"], "lilith")
            self.assertEqual(state["result"]["speaker_basis"], "source_role")
            send.assert_not_called()
        request = self.service.asr.call.call_args.args[0]
        self.assertEqual(request["source"], "browser_microphone")
        self.assertFalse(Path(request["path"]).exists())
        self.assertEqual(resource_manager.status(), [])

    def test_asr_failure_does_not_become_done_or_message(self):
        self.service.asr.call.side_effect = RuntimeError("Não foi detectada fala.")
        with patch.object(bus, "send") as send:
            state = self.wait_done(self.service.submit_transcription("hoshino", wav_bytes()), "error")
            send.assert_not_called()
        self.assertIn("fala", state["error"])
        self.assertIsNone(state["result"])
        self.assertEqual(list((self.root / "entidades/hoshino/runtime/audio/central").glob("*.input.wav")), [])

    def test_tts_saved_in_own_entity_and_preserves_resident_asr(self):
        state = self.wait_done(self.service.submit_speech("lilith", text="**Olá!** [Site](https://example.invalid)"))
        path = self.service.file(state["id"])
        self.assertTrue(path.is_relative_to(self.root / "entidades/lilith/runtime/audio/central"))
        self.assertEqual(state["result"]["audio_id"], state["id"])
        self.assertEqual(state["result"]["sample_rate"], 16000)
        self.service.asr.close.assert_not_called()
        self.assertEqual([c.args[0]['text'] for c in self.service.tts.call.call_args_list], ['Olá!', 'Site'])
        self.wait_done(self.service.submit_transcription("hoshino", wav_bytes()))
        self.service.tts.close.assert_not_called()

    def test_invalid_tts_output_is_error_and_removed(self):
        def corrupt(request, *_args):
            Path(request["output"]).write_bytes(b"not WAV")
        self.service.tts.call.side_effect = corrupt
        job = self.service.submit_speech("hoshino", text="teste")
        self.wait_done(job, "error")
        self.assertEqual(list((self.root / "entidades/hoshino/runtime/audio/central").glob("*.wav")), [])

    def test_tts_wav_advertising_missing_frames_is_not_success(self):
        def incomplete(request, *_args):
            Path(request["output"]).write_bytes(wav_bytes()[:-100])
        self.service.tts.call.side_effect = incomplete
        job = self.service.submit_speech("hoshino", text="teste de arquivo incompleto")
        state = self.wait_done(job, "error")
        self.assertIsNone(state["result"])
        self.assertEqual(list((self.root / "entidades/hoshino/runtime/audio/central").glob("*.wav")), [])

    def test_publish_running_and_error_failure_do_not_abandon_queue(self):
        original = job_bus.publish
        failed = []

        def disk_error(job_id, entity, status, **details):
            if not failed and status == "queued":
                failed.append(job_id)
            if failed and job_id == failed[0] and status in {"running", "error"}:
                raise OSError("falha simulada de persistência")
            return original(job_id, entity, status, **details)

        with contextlib.redirect_stderr(io.StringIO()), patch.object(job_bus, "publish", side_effect=disk_error):
            first = self.service.submit_transcription("hoshino", wav_bytes())
            second = self.service.submit_transcription("lilith", wav_bytes())
            self.wait_idle_bounded()
        self.assertNotEqual(self.service.get(first["id"])["status"], "done")
        self.assertEqual(self.service.get(second["id"])["status"], "done")
        self.assertEqual(self.service.asr.call.call_count, 1)
        self.assertEqual(self.service.cancels, {})
        self.assertTrue(self.service.thread.is_alive())

    def test_unlink_permission_error_does_not_kill_thread_or_next_job(self):
        with contextlib.redirect_stderr(io.StringIO()), patch.object(Path, "unlink", side_effect=PermissionError("fixture protegida")):
            first = self.service.submit_transcription("hoshino", wav_bytes())
            second = self.service.submit_transcription("lilith", wav_bytes())
            self.wait_idle_bounded()
        self.assertEqual(self.service.get(first["id"])["status"], "done")
        self.assertEqual(self.service.get(second["id"])["status"], "done")
        self.assertTrue(self.service.thread.is_alive())
        self.assertEqual(self.service.pending.unfinished_tasks, 0)
        self.assertEqual(self.service.cancels, {})

    def test_voice_identity_and_message_authorship_are_checked(self):
        hoshino = bus.send("hoshino", "usuario", "Olá.")
        user = bus.send("usuario", "hoshino", "Não é uma resposta da Hoshino.")
        for entity, message in [("lilith", hoshino["id"]), ("hoshino", user["id"]), ("hoshino", "missing")]:
            with self.assertRaises(ValueError):
                self.service.submit_speech(entity, message_id=message)
        with self.assertRaises(ValueError):
            self.service.submit_speech("alistair", text="Não tenho voz.")
        self.wait_done(self.service.submit_speech("hoshino", message_id=hoshino["id"]))

    def test_cancel_queued_job_never_runs_inference(self):
        running = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)

        def block(*_args):
            running.set()
            release.wait(3)
            return transcript()

        self.service.asr.call.side_effect = block
        first = self.service.submit_transcription("hoshino", wav_bytes())
        self.assertTrue(running.wait(2))
        second = self.service.submit_transcription("lilith", wav_bytes())
        self.service.cancel(second["id"])
        release.set()
        self.wait_done(first)
        self.assertEqual(self.service.get(second["id"])["status"], "interrupted")
        self.assertEqual(self.service.asr.call.call_count, 1)
        self.assertEqual(self.service.cancels, {})

    def test_full_queue_rejects_and_removes_failed_input(self):
        running = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        self.service.asr.call.side_effect = lambda *_a: (running.set(), release.wait(3), transcript())[-1]
        self.service.submit_transcription("hoshino", wav_bytes())
        self.assertTrue(running.wait(2))
        for _ in range(4):
            self.service.submit_transcription("hoshino", wav_bytes())
        with self.assertRaises(ValueError):
            self.service.submit_transcription("hoshino", wav_bytes())
        folder = self.root / "entidades/hoshino/runtime/audio/central"
        self.assertEqual(len(list(folder.glob("*.input.wav"))), 5)
        release.set()
        self.service.pending.join()
        self.assertEqual(list(folder.glob("*.input.wav")), [])

    def test_close_cancels_running_job_and_rejects_new_work(self):
        running = threading.Event()

        def until_cancel(_req, cancel, _timeout):
            running.set()
            if cancel.wait(3):
                raise audio.Cancelled("Cancelado na parada.")
            raise AssertionError("close não cancelou o job")

        self.service.asr.call.side_effect = until_cancel
        job = self.service.submit_transcription("hoshino", wav_bytes())
        self.assertTrue(running.wait(2))
        self.service.close()
        self.assertEqual(self.service.get(job["id"])["status"], "interrupted")
        self.assertFalse(self.service.thread.is_alive())
        self.service.asr.close.assert_called()
        self.service.tts.close.assert_called()
        with self.assertRaises(ValueError):
            self.service.submit_transcription("hoshino", wav_bytes())
        self.assertEqual(self.service.cancels, {})

    def test_file_rejects_other_job_kind_outside_paths_and_symlinks(self):
        outside = self.root / "outside.wav"
        outside.write_bytes(wav_bytes())
        inside = self.root / "entidades/hoshino/runtime/audio/central"
        inside.mkdir(parents=True)
        link = inside / "link.wav"
        link.symlink_to(outside)
        for job_id, kind, status, path in [("outside", "audio_tts", "done", outside),
                                           ("symlink", "audio_tts", "done", link),
                                           ("image", "image", "done", outside),
                                           ("pending", "audio_tts", "queued", outside)]:
            job_bus.publish(job_id, "hoshino", status, kind=kind, path=str(path))
            with self.subTest(job=job_id), self.assertRaises(ValueError):
                self.service.file(job_id)


class WorkerTests(unittest.TestCase):
    def test_no_speech_result_preserves_worker_and_typed_error(self):
        self.respond(lambda req:{'id':req['id'],'ok':False,'error':'Nenhuma fala.','code':'no_speech'})
        with self.assertRaises(RuntimeError) as raised:self.worker.call({'op':'transcribe'},threading.Event(),2)
        self.assertEqual(getattr(raised.exception,'code',None),'no_speech')
        self.assertIs(self.worker.process,self.process)

    def setUp(self):
        self.worker = audio.Worker(ROOT, Path(__file__), Path(__file__))
        self.process = Mock(stdin=Mock(), stdout=Mock(), poll=Mock(return_value=None))
        self.worker.process = self.process
        self.start = patch.object(self.worker, "_start")
        self.start.start()
        self.addCleanup(self.start.stop)

    def respond(self, response):
        def write(raw):
            request = json.loads(raw)
            self.worker.responses.put(response(request))
        self.process.stdin.write.side_effect = write

    def test_request_id_matches_actual_reply(self):
        self.respond(lambda req: {"id": req["id"], "ok": True, "result": {"text": "oi"}})
        result = self.worker.call({"op": "transcribe", "id": "untrusted caller id"}, threading.Event(), 2)
        self.assertEqual(result, {"text": "oi"})
        request = json.loads(self.process.stdin.write.call_args.args[0])
        self.assertNotEqual(request["id"], "untrusted caller id")
        self.process.terminate.assert_not_called()

    def test_stale_response_fails_and_stops_worker(self):
        self.respond(lambda req: {"id": "previous-request", "ok": True, "result": {"text": "stale"}})
        with self.assertRaises(RuntimeError):
            self.worker.call({"op": "transcribe"}, threading.Event(), 2)
        self.process.terminate.assert_called_once()
        self.assertIsNone(self.worker.process)

    def test_engine_failure_is_not_success(self):
        self.respond(lambda req: {"id": req["id"], "ok": False, "error": "motor falhou"})
        with self.assertRaisesRegex(RuntimeError, "motor falhou"):
            self.worker.call({"op": "transcribe"}, threading.Event(), 2)
        self.assertIsNone(self.worker.process)

    def test_cancel_and_timeout_stop_worker(self):
        cancel = threading.Event()
        # Cancelamento depois de escrever um pedido deve descartar o worker e
        # qualquer resposta tardia; antes de começar, não há pedido para drenar.
        self.process.stdin.write.side_effect = lambda _raw: cancel.set()
        with self.assertRaises(audio.Cancelled):
            self.worker.call({"op": "transcribe"}, cancel, 2)
        self.assertIsNone(self.worker.process)
        self.worker.process = self.process
        self.process.stdin.write.side_effect = None
        with self.assertRaises(TimeoutError):
            self.worker.call({"op": "transcribe"}, threading.Event(), 0)
        self.assertEqual(self.process.terminate.call_count, 2)

    def test_cancel_before_start_sends_nothing_and_preserves_idle_worker(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(audio.Cancelled):
            self.worker.call({"op": "transcribe"}, cancel, 2)
        self.worker._start.assert_not_called()
        self.process.stdin.write.assert_not_called()
        self.process.terminate.assert_not_called()
        self.assertIs(self.worker.process, self.process)

    def test_close_kills_uncooperative_process(self):
        self.process.wait.side_effect = [subprocess.TimeoutExpired("worker", 5), 0]
        self.worker.close()
        self.process.kill.assert_called_once()
        self.process.stdin.close.assert_called_once()
        self.process.stdout.close.assert_called_once()

    def test_start_discards_stale_queue_and_isolates_environment(self):
        with tempfile.TemporaryDirectory(prefix="audio-rpc-start-test-") as directory:
            worker = audio.Worker(Path(directory), Path(__file__), Path(__file__),
                                  {"HF_HOME": "test-only-voice-cache", "HOSHINO_AUDIO_TTS_BACKEND": "kokoro"})
            old_queue = worker.responses
            old_queue.put({"id": "stale", "ok": True})
            process = Mock(stdin=Mock(), stdout=io.StringIO(""), poll=Mock(return_value=None))
            with patch.dict("os.environ", {"HOSHINO_MODEL": "other-entity-model",
                                            "OLLAMA_MODELS": "other-entity-store"}), \
                    patch.object(audio.subprocess, "Popen", return_value=process) as spawn:
                worker._start()
                env = spawn.call_args.kwargs["env"]
                self.assertIsNot(worker.responses, old_queue)
                self.assertEqual(env["HF_HOME"], "test-only-voice-cache")
                self.assertEqual(env["HOSHINO_AUDIO_TTS_BACKEND"], "kokoro")
                self.assertEqual(env["HF_HUB_OFFLINE"], "1")
                self.assertNotIn("HOSHINO_MODEL", env)
                self.assertNotIn("OLLAMA_MODELS", env)
                worker.close()


class VoiceChunkTests(unittest.TestCase):
    @staticmethod
    def module():
        path = ROOT / "app/tools/voice_worker.py"
        spec = importlib.util.spec_from_file_location("voice_chunk_test_worker", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_import_and_chunking_do_not_import_or_load_engines(self):
        original = builtins.__import__

        def no_engine(name, *args, **kwargs):
            if name in {"torch", "qwen_tts", "kokoro", "soundfile", "numpy"}:
                raise AssertionError("Um motor foi importado no teste de texto: " + name)
            return original(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=no_engine):
            module = self.module()
            with patch.object(module, "load_engine") as load:
                self.assertEqual(list(module.text_chunks("Olá, Gustavo.")), ["Olá, Gustavo."])
                load.assert_not_called()

    def test_chunks_preserve_normalized_content_beyond_worker_size_limit(self):
        module = self.module()
        text = ("Olá,\tGustavo.\nA imagem está pronta. Podemos conversar enquanto a outra tarefa continua.  " * 40).strip()
        self.assertGreater(len(text), 2400)
        chunks = list(module.text_chunks(text))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= 220 for chunk in chunks))
        self.assertEqual(" ".join(" ".join(chunks).split()), " ".join(text.split()))

    def test_long_indivisible_word_is_rejected_without_changed_speech(self):
        module = self.module()
        with self.assertRaises(ValueError):
            list(module.text_chunks("prefixo " + "x" * 221 + " sufixo"))


class SourceInventoryTests(unittest.TestCase):
    def test_selection_id_changes_when_stream_serial_or_process_is_reused(self):
        pid=[42];stamp=['start-a']
        def run(command,**kwargs):
            body=[] if command[-1]=='sources' else [{'index':9,'properties':{'application.name':'App','object.serial':'226','application.process.id':str(pid[0])}}]
            return SimpleNamespace(returncode=0,stdout=json.dumps(body))
        with patch.object(audio_sources.shutil,'which',return_value='/fixture/pactl'),patch.object(audio_sources.subprocess,'run',side_effect=run),patch.object(audio_sources,'_process_stamp',side_effect=lambda _p:stamp[0]):
            old=audio_sources.inventory(True)['streams'][0]['id']
            pid[0]=43;new=audio_sources.inventory(True)['streams'][0]['id']
            self.assertNotEqual(old,new)
            stamp[0]='start-b';restarted=audio_sources.inventory(True)['streams'][0]['id']
            self.assertNotEqual(new,restarted)
    def test_virtual_source_is_not_physical_and_stream_is_not_isolated_capture(self):
        sources = [{"name": "virtual_input", "description": "Entrada virtual", "monitor_of_sink": "4294967295"},
                   {"name": "output.monitor", "description": "(null)", "properties": {"device.description": "Headset"}}]

        def run(command, **_kwargs):
            if command[-1] == "sources":
                body = sources
            elif command[-1] == "sink-inputs":
                body = [{"index": 3, "properties": {"application.name": "Discord"}}]
            else:
                return SimpleNamespace(returncode=0, stdout="auto_null\n")
            return SimpleNamespace(returncode=0, stdout=json.dumps(body))

        with patch.object(audio_sources.shutil, "which", return_value="pactl"), \
                patch.object(audio_sources.subprocess, "run", side_effect=run), \
                patch.object(audio_sources, "_cached", None), patch.object(audio_sources, "_at", 0):
            state = audio_sources.inventory(True)
            self.assertFalse(state["physical_microphone_detected"])
            self.assertEqual(state["sources"][0]["kind"], "microphone")
            self.assertEqual(state["sources"][1]["kind"], "output_mix")
            self.assertEqual(state["sources"][1]["label"], "Headset · monitor da saída")
            self.assertFalse(state["streams"][0]["isolated_capture"])
            sources.append({"name": "hardware_input", "flags": ["HARDWARE"]})
            self.assertTrue(audio_sources.inventory(True)["physical_microphone_detected"])


class HttpAudioTests(ServiceFixture):
    def test_listening_api_requires_auth_and_controls_actual_shared_source(self):
        from core import audio_listening
        source=dict(id='fixture-source',label='Fixture',kind='microphone',serial='50')
        route=Mock();route.valid.return_value=True;route.read.return_value=b''
        self.service.listening.factory=Mock(return_value=route);self.service.listening.autostart=False
        with patch.object(audio_listening,'inventory',return_value=dict(sources=[source],streams=[])):
            self.request('/api/audio/listening?entity=hoshino',headers={'Authorization':''},expected=403)
            self.request('/api/audio/listening',dict(action='open',entity='hoshino',channel='entrada',source_id=source['id'],attention='ativa'))
            state,_=self.request('/api/audio/listening?entity=hoshino')
            self.assertEqual(state['channels'][0]['status'],'capturando')
            other,_=self.request('/api/audio/listening?entity=lilith');self.assertEqual(other['channels'],[])
            self.request('/api/audio/listening',dict(action='stop',entity='hoshino',channel='entrada'))
            route.close.assert_called_once()
            self.request('/api/audio/listening',dict(action='other',entity='hoshino'),expected=400)

    def test_live_http_metadata_is_required_for_preview_proof_and_returned_by_get(self):
        meta=dict(id='a'*32,part=0,revision=1,preview=True,session_id='session-one',scope='direct')
        path='/api/audio/transcribe?'+urlencode(dict(entity='hoshino',source='native_microphone',utterance=json.dumps(meta)))
        self.request(path,wav_bytes(),headers={'Content-Type':'audio/wav','Authorization':''},expected=403)
        job,_=self.request(path,wav_bytes(),headers={'Content-Type':'audio/wav'},expected=202)
        state=self.wait_done(job);self.assertEqual(state.get('utterance'),meta)
        self.request('/api/send',dict(entity='hoshino',audio_job_id=job['id'],draft_origin=True,text=state['result']['text']),expected=400)
        bad=path.replace('session-one','')
        self.request(bad,wav_bytes(),headers={'Content-Type':'audio/wav'},expected=400)

    def test_ordinary_message_does_not_cancel_speech(self):
        with patch.object(self.service,'interrupt_entity') as interrupt:
            self.request('/api/send',{'entity':'hoshino','text':'Também gosto de astronomia.'})
            interrupt.assert_not_called()

    def test_http_acoustic_route_auth_pcm_metadata_and_stop(self):
        path='/api/audio/perception?entity=hoshino&source=native_microphone&capture_id='+('a'*32)+'&sequence=0&scope=global&playback_overlap=true'
        self.request(path,b'x',headers={'Content-Type':'application/octet-stream','Authorization':''},expected=403)
        self.request(path,b'x',headers={'Content-Type':'application/octet-stream'},expected=400)
        with patch.object(self.service,'submit_perception',return_value={'events':[]}) as submit:
            self.request(path,bytes(31200),headers={'Content-Type':'application/octet-stream'})
            self.assertTrue(submit.call_args.kwargs['playback_overlap']);self.assertEqual(submit.call_args.kwargs['sequence'],0)
        with patch.object(self.service.perception,'cancel',return_value={'cancelled':True}) as cancel:
            self.request('/api/audio/perception/stop',{'capture_id':'a'*32});cancel.assert_called_once_with('a'*32)
    def test_playback_diagnostics_reject_foreign_audio_and_dont_claim_hearing(self):
        message=bus.send('hoshino','usuario','Olá.',metadata={'turn_id':'turn-playback','input_ids':['msg-input']})
        job=self.service.submit_speech('hoshino',message_id=message['id'])
        self.wait_done(job)
        with patch.object(audio.diagnostics,'emit',wraps=audio.diagnostics.emit) as emit:
            result,_=self.request('/api/audio/job',{'entity':'hoshino','id':job['id'],'playback_event':'autoplay_denied','chunk':0})
            self.assertTrue(result['recorded'])
            event=next(c for c in emit.call_args_list if c.args[0]=='voice.playback')
            self.assertEqual(event.kwargs['basis'],'browser_player_report_not_human_hearing')
        self.request('/api/audio/job',{'entity':'lilith','id':job['id'],'playback_event':'ended'},expected=400)
        self.request('/api/audio/job',{'entity':'hoshino','id':job['id'],'playback_event':'ended','chunk':9},expected=400)

    def setUp(self):
        super().setUp()
        self.server, self.token = launcher.make_server(launcher.Supervisor(), 0, audio=self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, data=None, headers=None, expected=200):
        h = {"Authorization": "Bearer " + self.token}
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        try:
            response = urlopen(Request(self.base + path, data=data, headers=h), timeout=5)
        except HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, expected)
            body = response.read()
            content_type = response.headers["Content-Type"]
            if content_type.startswith("application/json"):
                body = json.loads(body)
            return body, content_type

    def test_http_audio_routes_require_auth_and_local_origin(self):
        for path in ("/api/audio/state", "/api/audio/job?id=missing", "/api/audio/file?id=missing"):
            self.request(path, headers={"Authorization": ""}, expected=403)
        self.request("/api/audio/cancel", {"id": "missing"}, headers={"Origin": "https://invalid.example"}, expected=403)
        self.request("/api/audio/state", headers={"Host": "invalid.example"}, expected=403)

    def test_http_binary_upload_draft_review_and_provenance(self):
        job, _ = self.request("/api/audio/transcribe?entity=hoshino", wav_bytes(), {"Content-Type": "audio/wav"}, 202)
        self.wait_done(job)
        self.assertEqual(bus.peek("hoshino"), [])  # Transcrição não envia conversa automaticamente.
        result, _ = self.request("/api/audio/job?id=" + job["id"])
        self.assertEqual(result["status"], "done")
        text = result["result"]["text"]
        self.request("/api/send", {"entity": "hoshino", "text": text, "audio_job_id": job["id"], "draft_origin": True})
        message = bus.peek("hoshino")[0]
        self.assertEqual(message["metadata"]["audio_job_id"], job["id"])
        self.assertEqual(message["metadata"]["speaker_basis"], "source_role")
        self.assertTrue(message["metadata"]["draft_reviewed"])
        self.assertFalse(message["metadata"]["speaker_identification_performed"])

    def test_http_submission_id_is_idempotent_and_payload_bound(self):
        data={'entity':'hoshino','text':'mensagem idempotente','submission_id':'submission-http-test'}
        first,_=self.request('/api/send',data)
        again,_=self.request('/api/send',data)
        self.assertEqual(first['id'],again['id'])
        self.assertTrue(again['deduplicated'])
        self.assertEqual(len(bus.peek('hoshino')),1)
        self.request('/api/send',{**data,'text':'outra intenção'},expected=400)
        third,_=self.request('/api/send',{**data,'submission_id':'submission-http-new'})
        self.assertNotEqual(first['id'],third['id'])

    def test_http_rejected_or_retried_submission_does_not_cancel_newer_audio(self):
        with patch.object(self.service,'interrupt_entity') as interrupt:
            data={'entity':'hoshino','text':'Pare de falar.','submission_id':'submission-cancel-test'}
            self.request('/api/send',data)
            self.assertEqual(interrupt.call_count,1)
            self.assertEqual(interrupt.call_args.args,('hoshino',))
            self.assertIsInstance(interrupt.call_args.kwargs['before'],float)
            self.request('/api/send',data)
            self.request('/api/send',{**data,'text':'ID com texto diferente'},expected=400)
            self.assertEqual(interrupt.call_count,1)

    def test_http_rejects_wrong_entity_unreviewed_or_replaced_audio_draft(self):
        job = self.service.submit_transcription("hoshino", wav_bytes())
        self.wait_done(job)
        for data in [{"entity": "lilith", "text": transcript()["text"], "draft_origin": True},
                     {"entity": "hoshino", "text": transcript()["text"], "draft_origin": False},
                     {"entity": "hoshino", "text": "texto totalmente diferente", "draft_origin": True}]:
            self.request("/api/send", {**data, "audio_job_id": job["id"]}, expected=400)
        self.assertEqual(bus.peek("hoshino"), [])
        self.assertEqual(bus.peek("lilith"), [])

    def test_http_rejects_pending_failed_or_tts_job_as_user_audio_origin(self):
        for job_id, kind, status in [("pending-asr", "audio_asr", "queued"),
                                      ("failed-asr", "audio_asr", "error"),
                                      ("tts-not-input", "audio_tts", "done")]:
            job_bus.publish(job_id, "hoshino", status, kind=kind, result=transcript())
            self.request("/api/send", {"entity": "hoshino", "text": transcript()["text"],
                                       "audio_job_id": job_id, "draft_origin": True}, expected=400)
        self.assertEqual(bus.peek("hoshino"), [])

    def test_http_speech_requires_entity_reply_and_returns_wav(self):
        message = bus.send("lilith", "usuario", "Olá, Gustavo.")
        self.request("/api/audio/synthesize", {"entity": "lilith", "text": "texto livre"}, expected=400)
        self.request("/api/audio/synthesize", {"entity": "hoshino", "message_id": message["id"]}, expected=400)
        job, _ = self.request("/api/audio/synthesize", {"entity": "lilith", "message_id": message["id"]}, expected=202)
        self.wait_done(job)
        body, mime = self.request("/api/audio/file?id=" + job["id"])
        self.assertEqual(mime, "audio/wav")
        self.assertEqual(body[:4], b"RIFF")

    def test_http_rejects_invalid_wav_type_entity_and_size(self):
        self.request("/api/audio/transcribe?entity=hoshino", b"invalid", {"Content-Type": "audio/wav"}, 400)
        self.request("/api/audio/transcribe?entity=hoshino", wav_bytes(), {"Content-Type": "audio/webm"}, 400)
        self.request("/api/audio/transcribe?entity=unknown", wav_bytes(), {"Content-Type": "audio/wav"}, 400)
        self.request("/api/audio/transcribe?entity=hoshino", b"x",
                     {"Content-Type": "audio/wav", "Content-Length": str(audio.MAX_INPUT_BYTES + 1)}, 400)

    def test_http_cancel_needs_no_entity_and_unknown_job_fails(self):
        job = self.service.submit_transcription("hoshino", wav_bytes())
        self.wait_done(job)
        self.request("/api/audio/cancel", {"id": job["id"]})
        self.request("/api/audio/cancel", {"id": "missing"}, expected=400)

    def test_http_state_is_read_only_and_server_close_closes_audio(self):
        inventory = {"sources": [], "streams": [], "physical_microphone_detected": False,
                     "application_capture_isolated": False, "available": False}
        with patch.object(audio.audio_sources, "inventory", return_value=inventory):
            state, _ = self.request("/api/audio/state")
        self.assertFalse(state["tts"]["voices_ready"])
        self.service.asr.call.assert_not_called()
        self.service.tts.call.assert_not_called()
        self.server.server_close()
        self.assertTrue(self.service.closed)


if __name__ == "__main__":
    unittest.main()
