"""Providers remotos opcionais no roteador existente; fallback local obrigatório.

Só este adaptador vê a chave, lida com SSML e recebe a resposta remota. Não
registra headers, corpo de erro, exceções remotas ou texto sintetizado.
"""
import io
import math
import json
import os
import re
import socket
import time
import queue
import threading
import wave
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.sax.saxutils import escape

from core import diagnostics

STANDARD_PT_BR = {'pt-BR-'+name+'Neural' for name in (
    'Francisca','Antonio','Brenda','Donato','Elza','Fabio','Giovanna','Humberto',
    'Julio','Leila','Leticia','Manuela','Nicolau','Thalita','Valerio','Yara')}
DEFAULT_VOICES = {'hoshino':'pt-BR-FranciscaNeural', 'lilith':'pt-BR-BrendaNeural'}
MAX_WAV_BYTES = 40 * 1024 ** 2


class SpeechCancelled(RuntimeError):
    pass


class AzureFailure(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__('Azure TTS indisponível: '+code)


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise SpeechCancelled('Operação de áudio interrompida.')


def wav_info(data):
    try:
        if not 0 < len(data) <= MAX_WAV_BYTES:
            raise ValueError('invalid_audio')
        with wave.open(io.BytesIO(data), 'rb') as stream:
            frames, rate = stream.getnframes(), stream.getframerate()
            if (stream.getnchannels()!=1 or stream.getsampwidth()!=2 or stream.getcomptype()!='NONE' or
                not 8000<=rate<=48000 or frames<=0 or frames/rate>600 or
                len(stream.readframes(frames))!=frames*2):
                raise ValueError('invalid_audio')
            return dict(sample_rate=rate, duration_seconds=frames/rate)
    except (wave.Error, EOFError, ValueError):
        raise AzureFailure('invalid_audio') from None


class TTSRouter:
    def __init__(self, settings=None):
        self.settings = settings or {}
        supplied = self.settings.get('azure', {})
        self.azure = dict(supplied) if isinstance(supplied,dict) else {'enabled':False}
        for name,default in (('key_env','AZURE_SPEECH_KEY'),('region_env','AZURE_SPEECH_REGION')):
            value = self.azure.get(name,default)
            self.azure[name] = value if isinstance(value,str) and re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',value) else default
        for name in ('voices','voice_env'):
            if not isinstance(self.azure.get(name,{}),dict): self.azure[name] = {}
        self.cooldown_until = 0
        supplied = self.settings.get('elevenlabs', {})
        self.elevenlabs = dict(supplied) if isinstance(supplied, dict) else {'enabled': False}
        for name, default in (('key_env','ELEVENLABS_API_KEY'), ('model_env','ELEVENLABS_TTS_MODEL')):
            value = self.elevenlabs.get(name, default)
            self.elevenlabs[name] = value if isinstance(value,str) and re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',value) else default
        for name in ('voices', 'voice_env'):
            if not isinstance(self.elevenlabs.get(name), dict): self.elevenlabs[name] = {}
        self.eleven_cooldown_until = 0

    def secret_env_names(self):
        return (self.azure['key_env'], self.elevenlabs['key_env'])

    def seconds(self, name, default, maximum, provider='azure'):
        try:
            value = float((self.elevenlabs if provider=='elevenlabs' else self.azure).get(name,default))
            return max(1,min(maximum,value)) if math.isfinite(value) else default
        except (TypeError,ValueError,OverflowError):
            return default

    def voice(self, entity):
        selected = self.azure.get('voices', {}).get(entity, DEFAULT_VOICES.get(entity))
        env = self.azure.get('voice_env', {}).get(entity, 'AZURE_TTS_VOICE_'+entity.upper())
        if not isinstance(env,str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',env):
            env = 'AZURE_TTS_VOICE_'+entity.upper()
        selected = os.environ.get(env, selected)
        if not isinstance(selected,str) or selected not in STANDARD_PT_BR:
            raise AzureFailure('voice_not_pt_br_standard')
        return selected

    def _credentials(self):
        # Configuração guarda NOMES de variáveis, nunca chaves.
        return (os.environ.get(self.azure.get('key_env','AZURE_SPEECH_KEY'), '').strip(),
                os.environ.get(self.azure.get('region_env','AZURE_SPEECH_REGION'), '').strip())

    def eleven_voice(self, entity):
        env = self.elevenlabs['voice_env'].get(entity, 'ELEVENLABS_TTS_VOICE_'+entity.upper())
        if not isinstance(env,str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',env):
            env = 'ELEVENLABS_TTS_VOICE_'+entity.upper()
        voice = os.environ.get(env, self.elevenlabs['voices'].get(entity, ''))
        if entity not in DEFAULT_VOICES or not isinstance(voice,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',voice):
            raise AzureFailure('elevenlabs_voice_missing_or_invalid')
        return voice

    def eleven_model(self):
        model = os.environ.get(self.elevenlabs['model_env'], self.elevenlabs.get('model_id','eleven_multilingual_v2'))
        if not isinstance(model,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',model):
            raise AzureFailure('elevenlabs_model_invalid')
        return model

    def state(self):
        key, region = self._credentials()
        configured = self.azure.get('enabled', True) is True and bool(key) and bool(re.fullmatch('[a-z0-9]+',region))
        voices = {}
        valid = True
        for entity in DEFAULT_VOICES:
            try:
                voices[entity] = self.voice(entity)
            except AzureFailure:
                valid = False
        route = dict(preferred=('azure' if valid and time.monotonic()>=self.cooldown_until else 'qwen3_tts')
                    if configured else self.settings.get('backend','qwen3_tts'),
                    azure_configured=configured, azure_voices=voices, standard_only=True,
                    configuration_failure=None if valid else 'voice_not_pt_br_standard',
                    cooldown_seconds=max(0, round(self.cooldown_until-time.monotonic(),1)),
                    local_fallback='qwen3_tts', configured_local=self.settings.get('backend','qwen3_tts'))
        eleven_configured = (self.elevenlabs.get('enabled', False) is True and
                             bool(os.environ.get(self.elevenlabs['key_env'], '').strip()))
        eleven_voices, eleven_failure = {}, None
        try:
            model = self.eleven_model()
            for entity in DEFAULT_VOICES: eleven_voices[entity] = self.eleven_voice(entity)
        except AzureFailure as exc:
            eleven_failure = exc.code
            model = None
        selected = ('elevenlabs' if eleven_configured and (self.settings.get('preferred_provider')=='elevenlabs' or not configured)
                    else 'azure' if configured else None)
        if selected=='elevenlabs':
            route.update(preferred='elevenlabs' if not eleven_failure and time.monotonic()>=self.eleven_cooldown_until else 'qwen3_tts',
                         configuration_failure=eleven_failure,
                         cooldown_seconds=max(0, round(self.eleven_cooldown_until-time.monotonic(),1)))
        route.update(remote_selected=selected, elevenlabs_configured=eleven_configured,
                     elevenlabs_voices=eleven_voices, elevenlabs_model=model)
        if selected is None and self.settings.get('preferred_provider')=='qwen3_tts':route['preferred']='qwen3_tts'
        return route

    def _request_audio(self, req, timeout, cancel):
        started = time.monotonic()
        try:
            check_cancel(cancel)
            with urlopen(req, timeout=timeout) as response:
                content_type = getattr(response, 'headers', {}).get('Content-Type', '')
                if isinstance(content_type,str) and ('json' in content_type or content_type.startswith('text/')):
                    raise AzureFailure('invalid_audio')
                parts, length = [], 0
                while True:
                    check_cancel(cancel)
                    if time.monotonic()-started >= timeout: raise AzureFailure('timeout')
                    part = response.read(32768)
                    if not part: break
                    length += len(part)
                    if length > MAX_WAV_BYTES: raise AzureFailure('audio_too_large')
                    parts.append(part)
        except HTTPError as exc:
            code = 'quota' if exc.code==429 else 'auth' if exc.code in (401,403) else 'http_'+str(exc.code)
            raise AzureFailure(code) from None
        except (TimeoutError, socket.timeout):
            raise AzureFailure('timeout') from None
        except (URLError, OSError):
            raise AzureFailure('network') from None
        return b''.join(parts)

    def _fetch_audio(self, text, entity, cancel):
        check_cancel(cancel)
        key, region = self._credentials()
        if not key or not re.fullmatch('[a-z0-9]+',region):
            raise AzureFailure('not_configured')
        voice = self.voice(entity)
        timeout = self.seconds('timeout_seconds',6,15)
        body = ('<speak version="1.0" xml:lang="pt-BR"><voice name="'+voice+'">'+
                escape(text)+'</voice></speak>').encode('utf-8')
        req = Request('https://'+region+'.tts.speech.microsoft.com/cognitiveservices/v1', data=body,
                      headers={'Content-Type':'application/ssml+xml',
                               'X-Microsoft-OutputFormat':'riff-24khz-16bit-mono-pcm',
                               'User-Agent':'Hoshino-Lilith-TTS'}, method='POST')
        req.add_unredirected_header('Ocp-Apim-Subscription-Key',key)
        data = self._request_audio(req, timeout, cancel)
        info = wav_info(data)
        check_cancel(cancel)
        return data,dict(provider='azure', voice=voice, **info)

    def _fetch_eleven(self, text, entity, cancel):
        check_cancel(cancel)
        voice, model = self.eleven_voice(entity), self.eleven_model()
        key = os.environ.get(self.elevenlabs['key_env'], '').strip()
        if not key: raise AzureFailure('not_configured')
        req = Request('https://api.elevenlabs.io/v1/text-to-speech/'+voice+'?output_format=pcm_24000',
                      data=json.dumps(dict(text=text, model_id=model),ensure_ascii=False).encode('utf-8'),
                      headers={'Content-Type':'application/json','Accept':'application/octet-stream'},method='POST')
        req.add_unredirected_header('xi-api-key',key)
        pcm = self._request_audio(req,self.seconds('timeout_seconds',6,15,'elevenlabs'),cancel)
        if not pcm or len(pcm)%2 or len(pcm)>24000*2*600: raise AzureFailure('invalid_audio')
        output = io.BytesIO()
        with wave.open(output,'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000); stream.writeframes(pcm)
        data = output.getvalue()
        info = wav_info(data)
        check_cancel(cancel)
        return data, dict(provider='elevenlabs',voice=voice,model=model,**info)

    def _azure(self, text, output, entity, cancel):
        return self._remote('azure',text,output,entity,cancel)

    def _remote(self, provider, text, output, entity, cancel):
        # O prazo total também cobre resposta lenta/gotejante. A thread de rede
        # não escreve em disco: uma resposta tardia não sobrescreve o fallback.
        timeout = self.seconds('timeout_seconds',6,15,provider)
        stopped = threading.Event()
        class Cancellation:
            def is_set(self):
                return stopped.is_set() or (cancel is not None and cancel.is_set())
        results = queue.Queue(maxsize=1)
        def fetch():
            try:
                fetch_audio = self._fetch_eleven if provider=='elevenlabs' else self._fetch_audio
                results.put((True,fetch_audio(text,entity,Cancellation())))
            except SpeechCancelled:
                results.put((False,SpeechCancelled('Operação de áudio interrompida.')))
            except AzureFailure as exc:
                results.put((False,AzureFailure(exc.code)))
            except Exception:
                results.put((False,AzureFailure('provider_error')))
        threading.Thread(target=fetch,name=provider+'-tts-request',daemon=True).start()
        deadline = time.monotonic()+timeout
        try:
            while True:
                check_cancel(cancel)
                remaining = deadline-time.monotonic()
                if remaining<=0:
                    raise AzureFailure('timeout')
                try:
                    ok,result = results.get(timeout=min(.05,remaining))
                except queue.Empty:
                    continue
                if not ok:
                    raise result
                data,info = result
                break
        finally:
            stopped.set()
        check_cancel(cancel)
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Esta etapa só escreve áudio, jamais chave ou SSML em arquivo.
        with path.open('wb') as stream:
            stream.write(data)
        return info

    def synthesize(self, text, output, entity, cancel, local, *, fallback=None):
        """local() é o worker existente; fallback() é Qwen obrigatório se Azure.

        Falha remota não pode expor headers/segredos. Cancelamento não dá
        permissão para iniciar fallback e falar uma resposta já interrompida.
        """
        check_cancel(cancel)
        route = self.state()
        began = time.monotonic()
        failed = None
        provider = route['remote_selected']
        if route['preferred'] in {'azure','elevenlabs'}:
            try:
                result = (self._azure(text,output,entity,cancel) if provider=='azure'
                          else self._remote(provider,text,output,entity,cancel))
            except SpeechCancelled:
                raise
            except AzureFailure as exc:
                failed = exc.code
            except Exception:
                failed = 'provider_error'  # nunca interpolar exceção com credenciais
            if failed:
                cooldown = time.monotonic()+self.seconds('cooldown_seconds',30,300,provider)
                if provider=='azure': self.cooldown_until = cooldown
                else: self.eleven_cooldown_until = cooldown
                diagnostics.emit('tts.provider_failed', level='WARN', provider=provider, entity=entity,
                                 failure=failed, latency_ms=round((time.monotonic()-began)*1000), fallback='qwen3_tts', priority=0)
                check_cancel(cancel)
                result = (fallback or local)()
                result = dict(result or {}, provider='qwen3_tts', fallback_from=provider, failure=failed)
            else:
                diagnostics.emit('tts.synthesized', provider=provider, entity=entity, priority=0,
                                 latency_ms=round((time.monotonic()-began)*1000), voice=result['voice'])
                return result
        else:
            if provider and route['configuration_failure']:
                diagnostics.emit('tts.provider_failed',level='WARN',provider=provider,entity=entity,priority=0,
                                 failure=route['configuration_failure'],fallback='qwen3_tts',latency_ms=0)
            # No período de cooldown continua usando o fallback Qwen do Azure.
            use_qwen = (provider is not None or self.settings.get('preferred_provider')=='qwen3_tts') and fallback is not None
            result = (fallback if use_qwen else local)()
            result = dict(result or {}, provider='qwen3_tts' if use_qwen else self.settings.get('backend','qwen3_tts'))
        check_cancel(cancel)
        diagnostics.emit('tts.synthesized', provider=result['provider'], entity=entity, priority=0,
                         latency_ms=round((time.monotonic()-began)*1000), fallback=failed,
                         device=result.get('device','cpu'), gpu_compute=result.get('device')=='hip',compute_lease=result.get('compute_lease'))
        return result


def load_settings(root):
    path = Path(root)/'compartilhado/config/audio.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
