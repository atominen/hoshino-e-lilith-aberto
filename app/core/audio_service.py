"""Áudio da central: WAV limitado, jobs rastreáveis e workers únicos persistentes.

O launcher usa só biblioteca padrão. ASR e TTS ficam em seus ambientes próprios.
Nenhum áudio é enviado ao modelo de conversa antes da revisão/envio do usuário.
"""
from __future__ import annotations
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from pathlib import Path

import config
from core import audio_sources, interentity as bus, job_bus, resource_manager, diagnostics, gpu_metrics, ui_policy
from core.audio_text import clean_for_speech, sentence_chunks
from core.tts_router import TTSRouter, SpeechCancelled, check_cancel, wav_info
from core.work_queue import WorkQueue
from core.audio_perception_service import AcousticService

MAX_INPUT_BYTES = 8 * 1024 ** 2
MAX_RECORDING_SECONDS = 60
MAX_OUTPUT_BYTES = 40 * 1024 ** 2
MAX_ENTITY_AUDIO_BYTES = 512 * 1024 ** 2


def validate_wav(data):
    if not data or len(data) > MAX_INPUT_BYTES:
        raise ValueError("Áudio vazio ou maior que o limite de 8 MB.")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate, frames = wav.getframerate(), wav.getnframes()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                raise ValueError("Use WAV mono PCM de 16 bits.")
            if not 8000 <= rate <= 48000 or not .2 <= frames / rate <= MAX_RECORDING_SECONDS + 0.05:
                raise ValueError("Áudio deve durar de 0,2 até 60 segundos, com taxa entre 8 e 48 kHz.")
            if len(wav.readframes(frames)) != frames * 2:
                raise ValueError("Áudio incompleto.")
            return {"sample_rate": rate, "duration_seconds": frames / rate}
    except (wave.Error, EOFError) as exc:
        raise ValueError("Arquivo WAV inválido.") from exc


def speech_text(text):
    text = clean_for_speech(text)
    if not text:
        raise ValueError("Não há texto para falar.")
    if len(text) > 2400:
        raise ValueError("Fala acima de 2400 caracteres; divida o texto. Nada foi cortado.")
    return text


Cancelled = SpeechCancelled


class NoSpeech(RuntimeError):
    """Resposta ASR válida sem fala; não é crash/timeout do processo."""
    code='no_speech'


class Worker:
    def __init__(self, root, python, script, env=None, secret_env_names=()):
        self.root, self.python, self.script = Path(root), Path(python), Path(script)
        self.env = env or {}
        self.secret_env_names = set(secret_env_names) | {'AZURE_SPEECH_KEY', 'ELEVENLABS_API_KEY'}
        self.lock = threading.RLock()
        self.process = None
        self.responses = queue.Queue()
        self._gpu_capable = None

    def _qwen_gpu_available(self):
        # Probe do próprio ambiente, sem carregar pesos. Vulkan dos LLMs não
        # significa que PyTorch tenha HIP. Nunca supõe suporte CUDA/NVIDIA.
        if self._gpu_capable is None:
            try:
                result=subprocess.run([str(self.python),'-I',str(self.script),'--probe-device'],capture_output=True,text=True,timeout=15,
                                      env={'PATH':os.environ.get('PATH',''),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'})
                self._gpu_capable=result.returncode==0 and json.loads(result.stdout).get('amd_hip_available') is True
            except (OSError,ValueError,subprocess.TimeoutExpired):self._gpu_capable=False
        return self._gpu_capable

    def _start(self, cancel=None):
        if self.process is not None and self.process.poll() is None:
            return
        if not self.python.is_file():
            raise RuntimeError("Ambiente de áudio não instalado.")
        if 'HOSHINO_WHISPER' in self.env:
            required=4*gpu_metrics.GIB+resource_manager.gpu_policy()['ram_margin_bytes']
            available=gpu_metrics.ram_available()
            if available is None or available<required:
                raise RuntimeError('RAM livre insuficiente/incerta para iniciar o transcritor junto dos serviços residentes.')
        if self.env.get('HOSHINO_AUDIO_TTS_BACKEND')=='qwen3_tts':
            required = 9*gpu_metrics.GIB+resource_manager.gpu_policy()['ram_margin_bytes']
            deadline = time.monotonic()+8
            while True:
                check_cancel(cancel)
                available = gpu_metrics.ram_available()
                if available is not None and available>=required: break
                # O lease CPU de áudio já sinaliza P0 ao job de imagem. Espera
                # a confirmação de saída/liberação dele antes de carregar Qwen.
                image_active = any(r['owner']=='image' for r in resource_manager.status('gpu'))
                if not image_active or time.monotonic()>=deadline: break
                if cancel is not None: cancel.wait(.1)
                else: time.sleep(.1)
            if available is None or available<required:
                diagnostics.emit('tts.resource_unavailable',level='WARN',provider='qwen3_tts',priority=0,
                                 device='cpu',available_bytes=available,required_bytes=required)
                raise RuntimeError('RAM livre insuficiente/incerta para iniciar Qwen TTS com segurança; áudio não concluído.')
        self.responses = queue.Queue()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HOSHINO_", "OLLAMA_", "AZURE_", "ELEVENLABS_"))}
        env.update(PYTHONPATH=str(self.root / "app"), HOSHINO_ENTIDADE="hoshino",
                   HF_HOME=str(self.root / "compartilhado/modelos/huggingface"),
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false",
                   OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", NUMEXPR_NUM_THREADS="4")
        env.update(self.env)
        for name in self.secret_env_names:
            env.pop(name,None)
        log_dir = self.root / "compartilhado/runtime/audio"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / (self.script.stem + ".log")).open("a", encoding="utf-8") as log:
            self.process = subprocess.Popen([str(self.python), "-I", str(self.root / "scripts/image_child.py"),
                str(os.getpid()), str(self.python), str(self.script)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1, env=env)
        process, responses = self.process, self.responses
        def read():
            try:
                for line in process.stdout:
                    if line.startswith("RESULT "):
                        try:
                            responses.put(json.loads(line[7:]))
                        except ValueError:
                            responses.put({"error": "protocolo de áudio inválido"})
            finally:
                responses.put(None)
        threading.Thread(target=read, name="audio-rpc-reader", daemon=True).start()

    def call(self, request, cancel, timeout):
        if self.env.get('HOSHINO_AUDIO_TTS_BACKEND')!='qwen3_tts' or request.get('op')!='synthesize':
            return self._call(request,cancel,timeout)
        with self.lock:
            check_cancel(cancel)
            if not self._qwen_gpu_available():
                diagnostics.emit('tts.local_device',provider='qwen3_tts',device='cpu',reason='amd_hip_unavailable',priority=0)
                return self._call(request,cancel,timeout)
            entity=request.get('entity') or config.ENTIDADE_ID
            # Mesma fila/lease do RM. Sem concorrência agressiva, sem descarregar
            # LLM de terceiros para conseguir espaço e sem manter VRAM oculta.
            with resource_manager.compute_lease('tts',entity=entity,model_key='qwen3_tts_local',priority=0,
                    vram_bytes=4*gpu_metrics.GIB,workspace_bytes=gpu_metrics.GIB,cpu_ram_bytes=9*gpu_metrics.GIB,
                    cpu_fallback=True,overlap_safe=False,wait=20,cancel=cancel) as lease:
                gpu=lease['backend']=='gpu';device='hip' if gpu else 'cpu'
                previous=self.env.get('HOSHINO_AUDIO_TTS_DEVICE','cpu')
                if previous!=device:self.close()
                self.env['HOSHINO_AUDIO_TTS_DEVICE']=device
                try:
                    result=self._call(request,cancel,timeout)
                    return dict(result,device=device,compute_lease=lease['token'])
                finally:
                    # Worker GPU owned precisa sair ANTES de devolver o lease.
                    # CPU continua persistente. Não repete áudio após falha.
                    if gpu:self.close()

    def _call(self, request, cancel, timeout):
        with self.lock:
            if cancel.is_set():
                raise Cancelled("Operação de áudio interrompida.")
            self._start(cancel)
            request = {**request, "id": uuid.uuid4().hex}
            deadline = time.monotonic() + timeout
            try:
                self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                self.process.stdin.flush()
                while True:
                    if cancel.is_set():
                        raise Cancelled("Operação de áudio interrompida.")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("O motor de áudio excedeu o tempo; a solicitação não foi concluída.")
                    try:
                        response = self.responses.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if response is None or response.get("id") != request["id"]:
                        raise RuntimeError("Worker encerrou ou respondeu a outra solicitação.")
                    if not response.get("ok"):
                        if request.get('op')=='transcribe' and response.get('code')=='no_speech':
                            raise NoSpeech(response.get('error','Nenhuma fala aproveitável.'))
                        raise RuntimeError(response.get("error", "falha do motor de áudio"))
                    return response.get("result", response)
            except Exception as exc:
                if not isinstance(exc,NoSpeech):self.close()  # Resposta incerta/tardia nunca pertence ao próximo pedido.
                raise

    def close(self):
        with self.lock:
            process, self.process = self.process, None
            if process is None:
                return
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def alive(self):
        process = self.process
        return bool(process is not None and process.poll() is None)


class AudioService:
    def __init__(self, root=None):
        self.root = Path(root or config.RAIZ).resolve()
        self.lock = threading.RLock()
        self.pending = WorkQueue(maxsize=4)
        self.cancels = {}
        self.closed = False
        self.thread = None
        self.asr_thread = None
        self.asr_requests = set()
        self.environment_results={}
        self.playback_owner = uuid.uuid4().hex
        self.settings = self._settings()
        self.router = TTSRouter(self.settings)
        secrets = self.router.secret_env_names()
        self.asr = Worker(self.root, self.root / "compartilhado/ambientes/principal/bin/python", self.root / "app/audio_worker.py",
                          {"HOSHINO_WHISPER": str(config.WHISPER_MODELO), "HOSHINO_WHISPER_BEAM": str(config.WHISPER_BEAM_SIZE)},
                          secret_env_names=secrets)
        self.tts = Worker(self.root, self.root / self.settings["python"], self.root / "app/tools/voice_worker.py",
                          {"HOSHINO_AUDIO_TTS_BACKEND": self.settings["backend"],
                           "HOSHINO_AUDIO_TTS_MODEL": str(self.root / self.settings.get("model", "")),
                           "HF_HOME": str(self.root / "compartilhado/modelos/voz/huggingface")},secret_env_names=secrets)
        self.qwen = self.tts if self.settings['backend']=='qwen3_tts' else Worker(
            self.root, self.root/'compartilhado/ambientes/tts-qwen/bin/python', self.root/'app/tools/voice_worker.py',
            {'HOSHINO_AUDIO_TTS_BACKEND':'qwen3_tts',
             'HOSHINO_AUDIO_TTS_MODEL':str(self.root/'compartilhado/modelos/voz/qwen3-tts/Qwen3-TTS-12Hz-0.6B-CustomVoice'),
             'HF_HOME':str(self.root/'compartilhado/modelos/voz/huggingface')},secret_env_names=secrets)
        self.perception=AcousticService(self.root,Worker(self.root,
            self.root/'compartilhado/ambientes/percepcao-acustica/bin/python',self.root/'app/audio_perception_worker.py',
            {'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2'},secret_env_names=secrets))
        from core.audio_listening import Listening
        self.listening=Listening(self)

    def submit_perception(self,entity,pcm,**metadata):
        return self.perception.submit(entity,pcm,**metadata)

    def _settings(self):
        defaults = {"backend": "kokoro", "python": "compartilhado/ambientes/voz/bin/python", "model": "",
                    "voices": {"hoshino": {"id": "pf_dora", "label": "Dora · provisória"},
                               "lilith": {"id": "pf_dora", "label": "Dora · provisória"}}, "voices_ready": False}
        path = self.root / "compartilhado/config/audio.json"
        if path.is_file():
            settings = json.loads(path.read_text(encoding="utf-8"))
            if settings.get("backend") not in {"kokoro", "qwen3_tts"}:
                raise ValueError("Backend de voz desconhecido.")
            defaults.update(settings)
        return defaults

    def state(self):
        inventory = audio_sources.inventory()
        routing = self.router.state()
        voices = self.settings['voices'] if routing['preferred']!='azure' else {
            entity:dict(id=identifier,label=identifier+' · Azure pt-BR Standard')
            for entity,identifier in routing['azure_voices'].items()}
        if routing['preferred']=='elevenlabs':
            voices = {entity:dict(id=identifier,label=identifier+' · ElevenLabs')
                      for entity,identifier in routing['elevenlabs_voices'].items()}
        return {"backend": "local_shared", "acoustic":self.perception.state(), "asr": {"engine": "faster-whisper", "model": config.WHISPER_MODELO,
                "device": "cpu", "worker_alive": self.asr.alive(),
                "identity": "usuario por origem do microfone, não identificação vocal"},
                "tts": {"engine": routing['preferred'], "device": "remote_or_local", "routing":routing, "voices_ready": self.settings["voices_ready"],
                        "local_gpu_policy":"AMD/HIP somente com lease P0 do Resource Manager; CPU obrigatório; suporte e espaço precisam ser confirmados",
                        "subjective_voice_approval": self.settings.get("subjective_voice_approval", False),
                        "latency_note": "Qwen CPU pode levar cerca de cinco vezes a duração da fala; não é tempo real." if self.settings["backend"] == "qwen3_tts" else "",
                        "worker_alive": self.tts.alive()},
                "voices": voices, "sources": inventory["sources"] + inventory["streams"],
                "output": inventory, "queue": self.pending.qsize(),
                "ambient_allowed":{e:ui_policy.capability_allowed(self.root,e,'ambient') for e in bus.ENTITIES}}

    def reload_routing(self, settings):
        """Troca somente configuração do router existente, entre trabalhos.

        Worker/checkpoint local não é trocado nem descarregado por essa UI.
        O lock usado por _submit torna o gate atômico com novas solicitações.
        """
        with self.lock:
            if self.cancels or self.pending.qsize():
                raise ValueError('Áudio ainda ativo; aguarde antes de reconfigurar.')
            self.settings = settings
            self.router = TTSRouter(settings)

    def _entity(self, entity):
        if entity not in bus.ENTITIES:
            raise ValueError("Entidade inválida.")
        return entity

    def _ensure_space(self, entity, output=False):
        directory = self.root / "entidades" / entity / "runtime/audio/central"
        directory.mkdir(parents=True, exist_ok=True)
        reserve = MAX_OUTPUT_BYTES if output else MAX_INPUT_BYTES
        if shutil.disk_usage(directory).free < reserve + 128 * 1024 ** 2:
            raise ValueError("Pouco espaço livre para áudio. Nada foi apagado.")
        if output:
            size = sum(p.stat().st_size for p in directory.glob("audio-*.wav") if p.is_file() and not p.is_symlink())
            if size + reserve > MAX_ENTITY_AUDIO_BYTES:
                raise ValueError("Cache de áudio desta entidade atingiu 512 MB. Arquive os WAVs antigos antes de continuar; nada foi apagado.")

    def submit_transcription(self, entity, data, source='browser_microphone', *, mode='command',utterance=None):
        from core.asr_provenance import validate
        utterance=validate(utterance)
        entity = self._entity(entity)
        if mode not in {'command','detection'}:raise ValueError('Modo de captura inválido.')
        if mode=='detection' and not ui_policy.capability_allowed(self.root,entity,'ambient'):
            raise ValueError('Ouvir o ambiente está desativado para esta entidade. Use o modo Comando.')
        if source not in {'browser_microphone','native_microphone'}:raise ValueError('Origem de microfone inválida.')
        details = validate_wav(data)
        self._ensure_space(entity)
        job = "audio-" + uuid.uuid4().hex[:20]
        path = self.root / "entidades" / entity / "runtime/audio/central" / (job + ".input.wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        try:
            return self._submit(job, entity, "audio_asr", {"path": str(path), "source": source, "capture_mode":mode, 'utterance':utterance, **details})
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def submit_environment(self,entity,data):
        """Origem interna distinta de ASR dirigido ao humano; nunca vira chat."""
        entity=self._entity(entity)
        if not ui_policy.capability_allowed(self.root,entity,'ambient'):raise ValueError('Escuta revogada.')
        details=validate_wav(data);self._ensure_space(entity)
        job='ambient-'+uuid.uuid4().hex[:20]
        path=self.root/'entidades'/entity/'runtime/audio/central'/(job+'.input.wav')
        path.parent.mkdir(parents=True,exist_ok=True)
        with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:stream.write(data)
        try:return self._submit(job,entity,'audio_environment',dict(path=str(path),source='system_audio',capture_mode='detection',**details))
        except Exception:path.unlink(missing_ok=True);raise

    def submit_speech(self, entity, message_id="", text="", *, test=False, provider=None, model=None):
        entity = self._entity(entity)
        if bus.sleep_requested(entity) and not test:
            raise ValueError('Entidade concluindo trabalhos/dormindo; fala não iniciada.')
        if entity == "alistair":
            raise ValueError("Alistair é textual e não tem voz.")
        if test and message_id:raise ValueError('Teste isolado não usa mensagem de conversa.')
        if provider is not None and (not test or provider not in {'elevenlabs','azure','qwen3_tts','kokoro'}):raise ValueError('Provider de teste inválido.')
        if model is not None and (not test or provider!='elevenlabs' or model not in {'eleven_multilingual_v2','eleven_flash_v2_5','eleven_turbo_v2_5'}):raise ValueError('Modelo de teste inválido.')
        if provider in {'elevenlabs','azure'}:
            route=self.router.state()
            if not route.get(provider+'_configured'):
                raise ValueError('Provider '+provider+' não configurado nesta central. Confira habilitação e API key: CONFIGURADA; reinicie a sessão/central após exportar a chave. Nenhuma quota usada.')
        if provider=='kokoro' and self.settings['backend']!='kokoro':raise ValueError('Worker Kokoro não está ativo; requer restart.')
        origin = {}
        if message_id:
            messages = bus.user_conversation(entity, 200)
            message = next((m for m in messages if m["id"] == message_id), None)
            if not message or message["sender"] != entity or message["recipient"] != "usuario" or message["kind"] != "chat":
                raise ValueError("Mensagem não pertence à conversa ou não tem voz desta entidade.")
            text = message["text"]
            origin = message.get('metadata', {})
            if isinstance(origin, str):
                origin = json.loads(origin or '{}')
            if not isinstance(origin, dict):
                raise ValueError('Metadados da resposta inválidos; fala não iniciada.')
        text = speech_text(text)
        self._ensure_space(entity, output=True)
        job = "audio-" + uuid.uuid4().hex[:20]
        path = self.root / "entidades" / entity / "runtime/audio/central" / (job + ".wav")
        return self._submit(job, entity, "audio_tts", {"text": text, "message_id": message_id, "path": str(path),
                                                      "voice": self.settings["voices"][entity]["id"],
                                                      'turn_id':origin.get('turn_id'), 'input_ids':origin.get('input_ids', []),
                                                      'conversation_session_id':(origin.get('conversation_session') or {}).get('id'),
                                                      'chat_scope':origin.get('chat_scope','direct'),
                                                      'isolated_test':test,'test_provider':provider,'test_model':model})

    def submit_stream(self, entity, stream_id):
        entity = self._entity(entity)
        if bus.sleep_requested(entity):
            raise ValueError('Entidade concluindo trabalhos/dormindo; fala não iniciada.')
        if entity == 'alistair':
            raise ValueError('Alistair é textual e não tem voz.')
        stream = job_bus.get(stream_id, entity)
        if not stream or stream['kind']!='llm_speech' or stream['status'] not in {'running','done'}:
            raise ValueError('Fluxo de sentenças não disponível para esta entidade.')
        if (stream['details'].get('channel')!='localhub' or not stream['details'].get('stable_only')
                or time.time()-stream['updated_at']>120):
            raise ValueError('Fluxo de voz vencido ou de outro canal.')
        self._ensure_space(entity, output=True)
        job = 'audio-'+uuid.uuid4().hex[:20]
        path = self.root/'entidades'/entity/'runtime/audio/central'/(job+'.wav')
        return self._submit(job,entity,'audio_tts',dict(path=str(path),stream_id=stream_id,
                             voice=self.settings['voices'][entity]['id'], text='',
                             conversation_session_id=stream['details'].get('conversation_session_id'),
                             chat_scope=stream['details'].get('chat_scope','direct'),
                             turn_id=stream['details'].get('turn_id'), input_ids=stream['details'].get('input_ids', [])))

    def _sentences(self, entity, details, cancel):
        if not details.get('stream_id'):
            yield from sentence_chunks(details['text'])
            return
        index, started = 0, time.monotonic()
        while True:
            check_cancel(cancel)
            stream = job_bus.get(details['stream_id'],entity)
            if (not stream or stream['kind']!='llm_speech' or stream['status'] in {'error','interrupted'}
                    or stream['details'].get('invalidated')):
                raise Cancelled('Resposta falada interrompida/revisada.')
            sentences = stream['details'].get('sentences', [])
            while index < len(sentences):
                check_cancel(cancel)
                yield speech_text(sentences[index])
                index += 1
            if stream['status']=='done':
                return
            if time.monotonic()-started > 600:
                raise TimeoutError('Fluxo de sentenças não terminou.')
            cancel.wait(.05)

    def _stream_cancellation(self, entity, details, cancel, job_id=None):
        class Cancellation:
            def is_set(inner):
                if cancel.is_set(): return True
                try:
                    if job_id:
                        job=job_bus.get(job_id,entity)
                        if not job or job['details'].get('playback_cancel_at'):return True
                    if not details.get('stream_id'):return False
                    stream = job_bus.get(details['stream_id'], entity)
                    return (not stream or stream['kind']!='llm_speech' or
                            stream['status'] in {'error','interrupted'} or stream['details'].get('invalidated',False))
                except Exception:
                    return True  # estado indisponível: não publique voz potencialmente velha
            def wait(inner, timeout=None):
                deadline = None if timeout is None else time.monotonic()+timeout
                while not inner.is_set():
                    if deadline is not None and time.monotonic()>=deadline: return False
                    cancel.wait(.05 if deadline is None else max(0,min(.05,deadline-time.monotonic())))
                return True
        return Cancellation()

    def _synthesize_chunk(self, text, path, entity, voice, cancel, router=None):
        request = dict(op='synthesize', text=text, voice=voice, speed=1.0, output=str(path),entity=entity)
        def local():
            if router is not None and router.settings.get('backend')=='qwen3_tts' and self.settings['backend']!='qwen3_tts':
                return self.qwen.call(dict(request,voice={'hoshino':'Serena','lilith':'Vivian'}[entity]),cancel,600)
            return self.tts.call(request,cancel,600)
        def qwen():
            if self.settings['backend']=='qwen3_tts':
                return local()
            # Timbre Azure/Kokoro não é nome de speaker Qwen.
            return self.qwen.call(dict(request,voice={'hoshino':'Serena','lilith':'Vivian'}[entity]),cancel,600)
        return (router or self.router).synthesize(text,str(path),entity,cancel,local,fallback=qwen)

    def _test_router(self,details):
        if not details.get('test_provider'):return self.router
        import copy
        settings=copy.deepcopy(self.settings);selected=details['test_provider'];settings['preferred_provider']=selected
        if selected in ('qwen3_tts','kokoro'):settings['backend']=selected
        for provider in ('azure','elevenlabs'):settings.setdefault(provider,{})['enabled']=provider==selected
        if details.get('test_model'):
            settings['elevenlabs']['model_id']=details['test_model']
            # Uma escolha explícita do teste não altera defaults e não é
            # silenciosamente substituída por ELEVENLABS_TTS_MODEL.
            settings['elevenlabs']['model_env']='HOSHINO_ISOLATED_TTS_MODEL_UNUSED'
        return TTSRouter(settings)

    def _submit(self, job, entity, kind, details):
        with self.lock:
            if self.closed:
                raise ValueError("Áudio encerrando.")
            if self.pending.full():
                raise ValueError("Fila de áudio cheia; aguarde.")
            job_bus.publish(job, entity, "queued", kind=kind, playback_owner=self.playback_owner,**{k: v for k, v in details.items() if k != "text"})
            self.cancels[job] = threading.Event()
            if kind=='audio_asr':self.asr_requests.add(job)
            self.pending.put((job, entity, kind, details), block=False,
                             priority=('low' if kind=='audio_environment' else
                                ("low" if (details.get('utterance') or {}).get('preview') else "critical") if kind == "audio_asr" else "normal"))
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, args=('audio_tts',),name="shared-audio-worker", daemon=True)
                self.thread.start()
            if self.asr_thread is None or not self.asr_thread.is_alive():
                self.asr_thread=threading.Thread(target=self._run,args=('audio_asr',),name='shared-asr-worker',daemon=True)
                self.asr_thread.start()
        return {"id": job, "status": "queued"}

    def _run(self, lane='audio_tts'):
        while True:
            try:
                item = self.pending.get_matching(lambda item:item is None or item[2]==lane or
                    lane=='audio_asr' and item[2]=='audio_environment',timeout=120)
            except queue.Empty:
                # Libera RAM ociosa sem mudar contexto ou encerrar modelos de conversa.
                if lane=='audio_asr':self.asr.close()
                else:
                    self.tts.close()
                    self.qwen.close()
                continue
            if item is None:
                self.pending.task_done()
                return
            job, entity, kind, details = item
            cancel = self._stream_cancellation(entity, details, self.cancels[job],job)
            scope = diagnostics.context(turn_id=details.get('turn_id') or '', entity=entity,
                                        conversation_session_id=details.get('conversation_session_id'),
                                        input_ids=details.get('input_ids', []), audio_id=job, stream_id=details.get('stream_id'))
            scope.__enter__()
            try:
                if cancel.is_set():
                    raise Cancelled("Operação cancelada antes de iniciar.")
                if kind in ('audio_asr','audio_environment') and details.get('capture_mode')=='detection' and not ui_policy.capability_allowed(self.root,entity,'ambient'):
                    raise ValueError('Ouvir o ambiente foi desativado antes da transcrição.')
                job_bus.publish(job, entity, "running", kind=kind)
                began = time.monotonic()
                if kind in ('audio_asr','audio_environment'):
                    with resource_manager.lease('cpu_audio',kind,entity=entity,wait=None,cancel=cancel):
                        result = self.asr.call({"op": "transcribe", "path": details["path"], "source": details["source"]}, cancel, 300)
                else:
                    self._ensure_space(entity, output=True)
                    path = Path(details["path"])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    chunks = []
                    tts_router=self._test_router(details)
                    for index,text in enumerate(self._sentences(entity,details,cancel)):
                        chunk_path = path.with_name(path.stem+f'-s{index:04d}.wav')
                        while self.asr_requests:
                            check_cancel(cancel);cancel.wait(.05)
                        with resource_manager.lease('cpu_audio',kind,entity=entity,wait=None,cancel=cancel):
                            routed = self._synthesize_chunk(text,chunk_path,entity,details['voice'],cancel,tts_router)
                        info = wav_info(chunk_path.read_bytes())
                        check_cancel(cancel)
                        chunks.append(dict(index=index,path=str(chunk_path),text=text,provider=routed['provider'],
                                           voice=routed.get('voice',details['voice']),model=routed.get('model'),fallback_from=routed.get('fallback_from'),failure=routed.get('failure'),**info))
                        result = dict(audio_id=job, chunks=[{k:v for k,v in c.items() if k!='path'} for c in chunks])
                        job_bus.publish(job,entity,'running',kind=kind,result=result,chunks=chunks,phase='synthesizing')
                    if not chunks:
                        raise RuntimeError('Nenhuma sentença estável para falar.')
                    combine_wavs([Path(c['path']) for c in chunks],path)
                    if path.stat().st_size > MAX_OUTPUT_BYTES:
                        raise RuntimeError("Motor produziu áudio acima do limite de 40 MB.")
                    with wave.open(str(path), "rb") as wav:
                        frames, rate = wav.getnframes(), wav.getframerate()
                        if (frames <= 0 or wav.getnchannels() != 1 or wav.getsampwidth() != 2
                                or wav.getcomptype() != "NONE" or not 8000 <= rate <= 48000
                                or frames / rate > 600 or len(wav.readframes(frames)) != frames * 2):
                            raise RuntimeError("Motor não produziu WAV válido.")
                        result.update(sample_rate=wav.getframerate(), duration_seconds=wav.getnframes()/wav.getframerate(),
                                      voice=details['voice'], providers=[c['provider'] for c in chunks])
                if cancel.is_set():
                    raise Cancelled("Operação cancelada.")
                receipt=result
                if kind=='audio_environment':
                    with self.lock:
                        check_cancel(cancel)
                        self.environment_results[job]=result
                    # O recibo operacional não é um arquivo de conversas escutadas.
                    receipt=dict(source='system_audio',speaker='desconhecido',transcript='volatile',
                        duration_seconds=result.get('metadata',{}).get('duration_seconds'))
                job_bus.publish(job, entity, "done", kind=kind, result=receipt, elapsed_seconds=round(time.monotonic() - began, 2))
                diagnostics.emit('voice.job_finished', kind=kind, status='done',
                                 providers=result.get('providers', []), audio_id=job)
            except Exception as exc:
                if kind=='audio_environment':self.discard_environment(job)
                try:
                    job_bus.publish(job, entity, "interrupted" if isinstance(exc, (Cancelled,InterruptedError)) else "error", kind=kind,
                                    error=str(exc)[:1000],error_code=getattr(exc,'code',None))
                except Exception as persist_error:
                    # Uma falha de disco não deve abandonar a fila ou travar shutdown.
                    print(f"Áudio: não foi possível registrar {job}: {type(persist_error).__name__}", file=sys.stderr)
                if kind == "audio_tts":
                    self._remove(details["path"])
                    # Apenas arquivos temporários produzidos por este job.
                    path = Path(details['path'])
                    for chunk_path in path.parent.glob(path.stem+'-s*.wav'):
                        self._remove(chunk_path)
                diagnostics.emit('voice.job_finished', level='WARN', kind=kind, audio_id=job,
                                 status='interrupted' if isinstance(exc,(Cancelled,InterruptedError)) else 'error',
                                 error_type=type(exc).__name__)
            finally:
                scope.__exit__(None, None, None)
                if kind in ('audio_asr','audio_environment'):
                    self._remove(details["path"])
                with self.lock:
                    self.cancels.pop(job, None)
                    self.asr_requests.discard(job)
                self.pending.task_done()

    @staticmethod
    def _remove(path):
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:
            print(f"Áudio: limpeza pendente ({type(exc).__name__}).", file=sys.stderr)

    def get(self, job_id):
        job = job_bus.get(job_id)
        if not job or job["kind"] not in {"audio_asr", "audio_tts",'audio_environment'}:
            raise ValueError("Solicitação de áudio não encontrada.")
        return {"id": job["id"], "entity": job["entity"], "kind": job["kind"], "status": job["status"],
                "result": job["details"].get("result"), "error": job["details"].get("error"),'error_code':job['details'].get('error_code'),
                "capture_mode":job['details'].get('capture_mode','command'),
                "utterance":job['details'].get('utterance')}

    def take_environment(self,job_id):
        job=self.get(job_id)
        if job['kind']!='audio_environment':raise ValueError('Recibo não é uma observação de áudio.')
        if job['status'] in job_bus.TERMINAL:
            with self.lock:job['result']=self.environment_results.pop(job_id,None)
        return job

    def discard_environment(self,job_id):
        with self.lock:self.environment_results.pop(job_id,None)

    def file(self, job_id, chunk=None):
        job = job_bus.get(job_id)
        if not job or job["kind"] != "audio_tts" or job["entity"] not in bus.ENTITIES:
            raise ValueError("Áudio não está concluído.")
        if chunk is None:
            if job['status']!='done':
                raise ValueError('Áudio completo ainda não concluído.')
            path = Path(job['details']['path']).resolve()
        else:
            chunks = job['details'].get('chunks', [])
            if job['status'] not in {'running','done'} or not 0<=int(chunk)<len(chunks):
                raise ValueError('Sentença de áudio ainda não disponível.')
            path = Path(chunks[int(chunk)]['path']).resolve()
        allowed = self.root / "entidades" / job["entity"] / "runtime/audio/central"
        if not path.is_relative_to(allowed.resolve()) or path.suffix != ".wav" or path.stat().st_size > MAX_OUTPUT_BYTES:
            raise ValueError("Arquivo de áudio fora do contrato.")
        return path

    def cancel(self, job_id):
        job = self.get(job_id)
        details = (job_bus.get(job_id) or {}).get('details', {})
        with diagnostics.context(turn_id=details.get('turn_id') or '', entity=job['entity'],
                                 conversation_session_id=details.get('conversation_session_id'),
                                 input_ids=details.get('input_ids', []), audio_id=job_id):
            diagnostics.emit('voice.cancel_requested', kind=job['kind'], status=job['status'])
        if job["status"] in job_bus.TERMINAL:
            return {"id": job_id, "status": job["status"], "detail": "Operação já encerrada."}
        with self.lock:
            if job_id not in self.cancels:
                raise ValueError("A central atual não controla essa operação.")
            self.cancels[job_id].set()
            removed = self.pending.discard(lambda item: item is not None and item[0] == job_id)
            for _, _, kind, details in removed:
                try:
                    job_bus.publish(job_id, job["entity"], "interrupted", kind=kind,
                                    error="Operação cancelada antes de iniciar.")
                finally:
                    self._remove(details["path"])
                    self.cancels.pop(job_id, None)
                    self.asr_requests.discard(job_id)
            if removed:
                return {"id": job_id, "status": "interrupted"}
        return {"id": job_id, "status": "cancel_requested"}

    def playback_event(self, entity, job_id, event, chunk=None, player='browser', position=None, sequence=None, observed_at=None):
        """Relato do player no diagnóstico existente, não prova de audição humana."""
        job = self.get(job_id)
        details = job_bus.get(job_id)['details']
        if details.get('playback_owner')!=self.playback_owner:
            raise ValueError('A Central atual não controla esse player.')
        if job['entity'] != entity or job['kind'] != 'audio_tts':
            raise ValueError('Áudio não pertence à entidade.')
        if player not in ('browser','native'):raise ValueError('Player inválido.')
        basis=player+'_player_report_not_human_hearing'
        if chunk is not None and (type(chunk) is not int or chunk < 0 or
                                 chunk >= len(details.get('chunks', []))):
            raise ValueError('Trecho de reprodução inválido.')
        with diagnostics.context(turn_id=details.get('turn_id') or '', entity=entity,
                                 conversation_session_id=details.get('conversation_session_id'),
                                 input_ids=details.get('input_ids', []), audio_id=job_id):
            diagnostics.emit('voice.playback', playback_event=event, chunk=chunk,
                             basis=basis,
                             providers=(details.get('result') or {}).get('providers', []))
        from core import audio_playback
        with self.lock:
            recorded=audio_playback.record(job_bus.get(job_id),event,chunk,player,position,sequence,observed_at)
        return {'id':job_id, 'recorded':recorded}

    def interrupt_entity(self, entity, before=None):
        """Só falas pendentes possuídas por esta central; ASR e outra entidade ficam intactos."""
        with self.lock:
            identifiers = list(self.cancels)
        interrupted = []
        for identifier in identifiers:
            job = self.get(identifier)
            if (job['entity']==entity and job['kind']=='audio_tts' and job['status'] not in job_bus.TERMINAL
                    and (before is None or (job_bus.get(identifier) or {}).get('created_at',float('inf')) <= before)):
                self.cancel(identifier)
                interrupted.append(identifier)
        # Síntese pode terminar enquanto um WAV ainda toca no navegador. Não
        # reclassifica síntese done nem finge que cancelamento já foi ouvido.
        from core import audio_playback
        audio_playback.request_stop(entity,before=before,owner=self.playback_owner)
        return interrupted

    def close(self):
        with self.lock:
            self.closed = True
            for cancel in self.cancels.values():
                cancel.set()
        listening_error=None
        try:self.listening.close()
        except Exception as exc:listening_error=exc
        self.perception.close()
        self.pending.join()
        for thread in (self.thread,self.asr_thread):
            if thread and thread.is_alive():self.pending.put(None)
        for thread in (self.thread,self.asr_thread):
            if thread and thread.is_alive():thread.join(5)
        self.asr.close()
        self.tts.close()
        self.qwen.close()
        with self.lock:self.environment_results.clear()
        if listening_error:raise listening_error


def combine_wavs(paths, output):
    """Concatena na ordem; normaliza PCM se um fallback mudar a taxa."""
    import array
    buffers, rate, total = [], None, 0
    for path in paths:
        data = path.read_bytes()
        info = wav_info(data)
        with wave.open(io.BytesIO(data),'rb') as wav:
            pcm = wav.readframes(wav.getnframes())
        if rate is None:
            rate = info['sample_rate']
        if info['sample_rate']!=rate:
            source = array.array('h'); source.frombytes(pcm)
            if sys.byteorder!='little': source.byteswap()
            target = array.array('h')
            for i in range(round(len(source)*rate/info['sample_rate'])):
                position = i*info['sample_rate']/rate
                left = min(int(position),len(source)-1); right = min(left+1,len(source)-1)
                target.append(round(source[left]+(source[right]-source[left])*(position-left)))
            if sys.byteorder!='little': target.byteswap()
            pcm = target.tobytes()
        total += len(pcm)
        if total > MAX_OUTPUT_BYTES-44:
            raise RuntimeError('Áudio combinado acima de 40 MB.')
        buffers.append(pcm)
    with wave.open(str(output),'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
        for pcm in buffers:
            wav.writeframes(pcm)
