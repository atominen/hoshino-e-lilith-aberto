"""Voz das entidades: Azure opcional, Qwen/Kokoro locais e reprodução ordenada."""
from __future__ import annotations

import atexit
import asyncio
import json
import os
import select
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from core import diagnostics
from core.audio_text import clean_for_speech
from core.audio_sources import inventory as audio_inventory
from core.audio_text import sentence_chunks
from core.tts_router import TTSRouter, load_settings, SpeechCancelled, check_cancel
import config

from config import RUNTIME_DIR, VOZ, VOZ_ATIVA, TTS_BACKEND, TTS_MODEL, TTS_DEVICE, TTS_VOICE, TTS_SPEED, VENV_VOZ

_lock = asyncio.Lock()
_worker_lock = threading.RLock()
_worker: subprocess.Popen | None = None
_worker_stderr_thread = None
_mixer_pronto = False
DISPONIVEL = True
MOTIVO = ""
ULTIMO_ERRO = ""
ULTIMA_FALA = ""
_pending_cancels = set()
_local_rpc = {}
_router = None
TTS_WORKER_TIMEOUT = float(os.environ.get("HOSHINO_TTS_WORKER_TIMEOUT", "120"))

try:
    import pygame
except ImportError as e:
    DISPONIVEL = False
    MOTIVO = str(e)
    pygame = None

def _worker_python() -> Path:
    return Path(VENV_VOZ) / "bin" / "python"


def _worker_script() -> Path:
    return Path(__file__).resolve().with_name("voice_worker.py")


def _iniciar_worker() -> subprocess.Popen:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.poll() is None:
            return _worker
        py = _worker_python()
        script = _worker_script()
        if not py.is_file():
            raise RuntimeError(f"venv de voz não encontrada: {py}")
        if not script.is_file():
            raise RuntimeError(f"worker de voz não encontrado: {script}")
        secrets = _voice_router().secret_env_names()
        env = {k:v for k,v in os.environ.items() if not k.startswith(('AZURE_', 'ELEVENLABS_')) and k not in secrets}
        env["HF_HOME"] = str(Path(config.RAIZ) / "compartilhado/modelos/voz/huggingface")
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="4", MKL_NUM_THREADS="4",
                   HOSHINO_AUDIO_TTS_BACKEND="kokoro")
        _worker = subprocess.Popen(
            [str(py), "-I", str(Path(config.RAIZ) / "scripts/image_child.py"), str(os.getpid()), str(py), str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        process = _worker
        def _dreno():
            if process.stderr is None:
                return
            for linha in process.stderr:
                diagnostics.emit("voice.worker_log", level="DEBUG", message=linha.rstrip())
        global _worker_stderr_thread
        _worker_stderr_thread = threading.Thread(target=_dreno, name="hoshino-voice-stderr", daemon=True)
        _worker_stderr_thread.start()
        diagnostics.emit("voice.worker_started", model=TTS_MODEL, voice=TTS_VOICE, device=TTS_DEVICE)
        return _worker


def _parar_worker() -> None:
    global _worker
    with _worker_lock:
        p = _worker
        _worker = None
        if p is None:
            return
        try:
            if p.poll() is None and p.stdin:
                p.stdin.write(json.dumps({"op": "stop"}) + "\n")
                p.stdin.flush()
                p.wait(timeout=3)
        except Exception:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=3)
        finally:
            for stream in (p.stdin, p.stdout, p.stderr):
                if stream:
                    stream.close()


atexit.register(_parar_worker)


def _voice_router():
    global _router
    if _router is None:
        settings = load_settings(config.RAIZ) or dict(backend=TTS_BACKEND,
            python='compartilhado/ambientes/voz/bin/python', voices={config.ENTIDADE_ID:{'id':TTS_VOICE}})
        _router = TTSRouter(settings)
    return _router


def _routed_synthesis(text, output, cancel):
    from core.audio_service import Worker
    from core import resource_manager
    router = _voice_router()
    settings = router.settings
    entity = config.ENTIDADE_ID
    def synthesize(backend):
        check_cancel(cancel)
        if backend not in _local_rpc:
            qwen = backend=='qwen3_tts'
            python = 'compartilhado/ambientes/tts-qwen/bin/python' if qwen else 'compartilhado/ambientes/voz/bin/python'
            model = settings.get('model','') if qwen and settings.get('backend')=='qwen3_tts' else 'compartilhado/modelos/voz/qwen3-tts/Qwen3-TTS-12Hz-0.6B-CustomVoice'
            _local_rpc[backend] = Worker(config.RAIZ,Path(config.RAIZ)/python,_worker_script(),
                {'HOSHINO_AUDIO_TTS_BACKEND':backend, 'HOSHINO_AUDIO_TTS_MODEL':str(Path(config.RAIZ)/model),
                 'HF_HOME':str(Path(config.RAIZ)/'compartilhado/modelos/voz/huggingface')},
                secret_env_names=router.secret_env_names())
        voice = settings.get('voices',{}).get(entity,{}).get('id',TTS_VOICE)
        if backend=='qwen3_tts' and settings.get('backend')!='qwen3_tts':
            voice = {'hoshino':'Serena','lilith':'Vivian'}[entity]
        with resource_manager.lease('cpu_audio','audio_tts',entity=entity,wait=20,cancel=cancel):
            return _local_rpc[backend].call(dict(op='synthesize',text=text,voice=voice,speed=1.0,output=output,entity=entity),cancel,600)
    try:
        return router.synthesize(text,output,entity,cancel,lambda:synthesize(settings.get('backend','kokoro')),
                                 fallback=lambda:synthesize('qwen3_tts'))
    finally:
        # A thread CPU pode terminar depois do cancelamento do await. Só remove
        # o WAV temporário deste pedido, mesmo nessa conclusão tardia.
        if cancel.is_set():
            Path(output).unlink(missing_ok=True)


def _close_local_rpc():
    for worker in _local_rpc.values():
        worker.close()


atexit.register(_close_local_rpc)


def _sintetizar_kokoro(texto: str, destino: str) -> None:
    try:
        _sintetizar_pedido(texto, destino)
    except Exception:
        _parar_worker()  # Timeout nunca deixa uma resposta antiga para a próxima fala.
        raise


def _sintetizar_pedido(texto: str, destino: str) -> None:
    p = _iniciar_worker()
    with _worker_lock:
        if p.poll() is not None or p.stdin is None or p.stdout is None:
            raise RuntimeError("worker Kokoro encerrou antes da síntese")
        request_id = uuid.uuid4().hex
        p.stdin.write(json.dumps({
            "id": request_id,
            "op": "synthesize",
            "text": texto,
            "voice": TTS_VOICE,
            "speed": TTS_SPEED,
            "output": destino,
        }, ensure_ascii=False) + "\n")
        p.stdin.flush()
        limite = time.monotonic() + max(1.0, TTS_WORKER_TIMEOUT)
        pending = getattr(p, '_voice_stdout_pending', None)
        if not isinstance(pending, bytearray):
            pending = bytearray()
            p._voice_stdout_pending = pending
        while True:
            restante = limite - time.monotonic()
            if restante <= 0:
                raise TimeoutError(
                    f"worker Kokoro não respondeu em {TTS_WORKER_TIMEOUT:g}s")
            if b'\n' not in pending:
                if not select.select([p.stdout], [], [], restante)[0]:
                    raise TimeoutError(f"worker Kokoro não respondeu em {TTS_WORKER_TIMEOUT:g}s")
                # TextIO.readline pode pré-buferizar READY + RESULT. select vê
                # somente o fd, causando um falso timeout na segunda linha.
                chunk = os.read(p.stdout.fileno(), 4096)
                if not chunk:
                    raise RuntimeError("worker Kokoro encerrou sem responder")
                pending.extend(chunk)
                if len(pending) > 65536:
                    raise RuntimeError("resposta do worker Kokoro acima do limite")
                continue
            raw, _, _ = pending.partition(b'\n')
            del pending[:len(raw)+1]
            linha = raw.decode('utf-8')
            if not linha.startswith("RESULT "):
                continue
            resp = json.loads(linha[7:])
            if resp.get("id") != request_id:
                raise RuntimeError("worker respondeu a outra solicitação de voz")
            if not resp.get("ok"):
                raise RuntimeError(resp.get("error", "falha desconhecida no Kokoro"))
            return


def limpar_para_fala(texto: str) -> str:
    return clean_for_speech(texto)


def _garantir_mixer() -> bool:
    global _mixer_pronto, ULTIMO_ERRO
    if _mixer_pronto:
        return True
    if not DISPONIVEL:
        return False
    try:
        pygame.mixer.init()
        _mixer_pronto = True
        return True
    except Exception as exc:
        ULTIMO_ERRO = f"saída de áudio não abriu: {type(exc).__name__}: {exc}"
        diagnostics.emit("voice.mixer_failed", level="ERROR", error=ULTIMO_ERRO)
        return False


async def speak(text: str, forcar: bool = False):
    global ULTIMO_ERRO, ULTIMA_FALA
    if not (VOZ_ATIVA or forcar):
        return "voz desativada"
    limpo = limpar_para_fala(text)
    if not limpo or len(limpo) < 2:
        return "nada para falar"
    if len(limpo) > 2400:
        return "fala acima de 2400 caracteres; divida o texto. Nada foi cortado"
    cancel = threading.Event()
    with _worker_lock:
        _pending_cancels.add(cancel)
    destinations = []
    providers, voices = [], []
    try:
        async with _lock:
            check_cancel(cancel)
            if not _garantir_mixer():
                return ULTIMO_ERRO or "não consegui abrir a saída de áudio"
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            try:
                for sentence in sentence_chunks(limpo):
                    check_cancel(cancel)
                    destino = os.path.join(RUNTIME_DIR, f"voz_{uuid.uuid4().hex}.wav")
                    destinations.append(destino)
                    routed = await asyncio.to_thread(_routed_synthesis,sentence,destino,cancel)
                    check_cancel(cancel)
                    providers.append((routed or {}).get('provider','unknown'))
                    voices.append((routed or {}).get('voice',TTS_VOICE))
                    pygame.mixer.music.load(destino)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        check_cancel(cancel)
                        await asyncio.sleep(0.05)
                ULTIMA_FALA = limpo[:160]
                ULTIMO_ERRO = ""
                diagnostics.emit("voice.spoken", chars=len(limpo), providers=providers,voices=voices)
                return "voz reproduzida"
            except (SpeechCancelled,InterruptedError):
                return 'fala interrompida'
            except Exception as exc:
                ULTIMO_ERRO = f"falha ao sintetizar ou reproduzir: {type(exc).__name__}: {exc}"
                diagnostics.emit("voice.playback_failed", level="ERROR", error=ULTIMO_ERRO)
                return ULTIMO_ERRO
            finally:
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
    except (SpeechCancelled,InterruptedError):
        return 'fala interrompida'
    finally:
        cancel.set()
        with _worker_lock:
            _pending_cancels.discard(cancel)
        for destino in destinations:
            try:
                os.remove(destino)
            except OSError:
                pass


async def testar():
    return await speak(
        f"Teste de voz da {config.ENTIDADE_NOME}. Se você ouviu esta frase, "
        "a saída de áudio está funcionando.", forcar=True)


def parar():
    from core import audio_playback
    central=audio_playback.request_stop(config.ENTIDADE_ID)
    with _worker_lock:
        for cancel in _pending_cancels:
            cancel.set()
    if not DISPONIVEL or not _mixer_pronto:
        return "Parada solicitada ao player da Central; aguardando confirmação." if central['player_confirmation_pending'] else "nenhuma fala em reprodução"
    try:
        pygame.mixer.music.stop()
        return "Parada solicitada; a Central confirma o encerramento do player quando houver reprodução própria."
    except Exception as exc:
        return f"não consegui interromper a fala: {type(exc).__name__}: {exc}"


def estado():
    from core import audio_playback
    worker_ativo = bool(_worker is not None and _worker.poll() is None)
    partes = [
        f"voz {'ativa' if VOZ_ATIVA else 'desligada'} ({TTS_VOICE})",
        f"backend: {_voice_router().state()['preferred']} (local preservado: {TTS_BACKEND})", f"modelo: {TTS_MODEL}", f"device: {TTS_DEVICE}",
        f"worker: {'ativo' if worker_ativo else 'sob demanda'}",
        f"saída: {'pronta' if _mixer_pronto else 'ainda não testada'}",
        f"saída padrão: {_saida_padrao()}",
    ]
    if ULTIMO_ERRO:
        partes.append(f"último erro: {ULTIMO_ERRO}")
    return " | ".join(partes)+' | reprodução factual: '+json.dumps(audio_playback.snapshot(config.ENTIDADE_ID),ensure_ascii=False)


def _saida_padrao():
    return audio_inventory().get("default_output") or "não identificada"
