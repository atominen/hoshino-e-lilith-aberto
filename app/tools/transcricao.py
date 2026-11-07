"""
Microfone — falar com ela em vez de digitar.

Dois modos, como pedido:

* **apertar** (padrão): F2 começa a gravar, F2 de novo encerra e transcreve. É o
  modo honesto — o microfone só está ligado quando você mandou ligar, e a barra
  de status mostra isso. Funciona bem em ambiente barulhento porque não depende de
  adivinhar onde a fala começa.
* **contínuo**: fica escutando e recorta sozinho cada trecho de fala, usando
  detecção de atividade por energia. Mais confortável e mais sujeito a engano:
  televisão, conversa de outra pessoa e barulho de teclado viram entrada. Por isso
  existe `MIC_EXIGIR_NOME`, que só aceita o trecho se o seu nome dela aparecer no
  começo.

O pedido dizia "microfone meio ruim", e é onde está metade do trabalho aqui:

* **calibração do ruído de fundo** — o limiar de fala não é fixo, é medido nos
  primeiros 400 ms e reavaliado durante o silêncio. Um limiar fixo funciona na
  casa de quem escreveu e em nenhuma outra;
* **filtro passa-alta** de primeira ordem, que tira zumbido de fonte e ronco de
  ar-condicionado sem precisar de scipy;
* **normalização com teto de ganho**, para fala baixa subir sem que o silêncio
  vire chiado amplificado;
* **duração mínima**, que descarta tosse, clique de mouse e batida na mesa;
* **filtro de alucinação**: o Whisper, ao receber silêncio ou chiado, inventa
  frases conhecidas ("Legendas pela comunidade Amara.org", "Obrigado por
  assistir"). Num modo contínuo isso entraria como se você tivesse falado. A
  lista está aqui embaixo e é aplicada sempre;
* **viés de vocabulário**: o nome dela e os termos da casa entram como dica para
  o decodificador, o que muda bastante o acerto de nome próprio em áudio ruim.

Nada aqui é obrigatório: sem biblioteca de áudio ou sem modelo instalado, o módulo
diz exatamente o que falta e a Hoshino continua funcionando pelo teclado.
"""
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
import uuid
from collections import deque
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

# Frases que o Whisper inventa quando recebe silêncio ou ruído.
ALUCINACOES = [
    r"legendas?\s+(pela|por)\s+comunidade", r"amara\.org", r"obrigad[oa] por assistir",
    r"^\s*obrigado\.?\s*$", r"inscreva-se no canal", r"legendas?:", r"subtitles by",
    r"^\s*tchau\.?\s*$", r"^\s*\.{2,}\s*$", r"^\s*\[?m[úu]sica\]?\s*$",
    r"^\s*\[?ru[íi]do\]?\s*$", r"^\s*você\s*$", r"^\s*ah\.?\s*$", r"^\s*hum+\.?\s*$",
]
_ALUCINACAO = re.compile("|".join(ALUCINACOES), re.IGNORECASE)
_CHAMADO = re.compile(r"^\W{0,3}(hoshino|oshino|rochino|hoshi)\b", re.IGNORECASE)


# =============================================================== captura
class CapturaIndisponivel(Exception):
    pass


class FonteDeAudio:
    """Camada fina sobre a placa de som. Escolhe o que existe na máquina."""

    def __init__(self, taxa: int = None, dispositivo: str = ""):
        self.taxa = taxa or config.MIC_TAXA
        self.dispositivo = config.MIC_DISPOSITIVO if dispositivo in (None, '') else dispositivo
        self.backend = None
        self._stream = None
        self._processo = None
        self._fila = queue.Queue(maxsize=200)

    # -------------------------------------------------------- descoberta
    @staticmethod
    def backends_disponiveis() -> list:
        achados = []
        try:
            import sounddevice  # noqa: F401
            achados.append("sounddevice")
        except Exception:  # noqa: BLE001 — falta de PortAudio levanta OSError, não ImportError
            pass
        try:
            import pyaudio  # noqa: F401
            achados.append("pyaudio")
        except Exception:  # noqa: BLE001
            pass
        if shutil.which("arecord"):
            achados.append("arecord")
        if shutil.which("parec"):
            achados.append("parec")
        return achados

    # ------------------------------------------------------------ início
    def abrir(self) -> str:
        disponiveis = self.backends_disponiveis()
        if not disponiveis:
            raise CapturaIndisponivel(
                "Nenhuma forma de gravar áudio nesta máquina. Instale uma destas: "
                "`pip install sounddevice` (precisa do libportaudio2), "
                "`pip install pyaudio`, ou o utilitário `arecord` (pacote alsa-utils).")
        self.backend = disponiveis[0]
        if self.backend == "sounddevice":
            self._abrir_sounddevice()
        elif self.backend == "pyaudio":
            self._abrir_pyaudio()
        else:
            self._abrir_processo()
        return self.backend

    def _abrir_sounddevice(self):
        import sounddevice as sd
        quadro = int(self.taxa * config.MIC_QUADRO_MS / 1000)

        def retorno(dados, _quadros, _tempo, status):  # noqa: ANN001
            if status:
                pass  # overflow de buffer não é motivo para derrubar a captura
            try:
                self._fila.put_nowait(bytes(dados))
            except queue.Full:
                pass

        self._stream = sd.RawInputStream(
            samplerate=self.taxa, blocksize=quadro, dtype="int16", channels=1,
            device=None if self.dispositivo in (None, '') else self.dispositivo, callback=retorno)
        self._stream.start()

    def _abrir_pyaudio(self):
        import pyaudio
        quadro = int(self.taxa * config.MIC_QUADRO_MS / 1000)
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(format=pyaudio.paInt16, channels=1, rate=self.taxa,
                                     input=True, frames_per_buffer=quadro)
        self._parar_thread = False

        def bombear():
            while not self._parar_thread:
                try:
                    dados = self._stream.read(quadro, exception_on_overflow=False)
                    self._fila.put_nowait(dados)
                except Exception:  # noqa: BLE001
                    break
        threading.Thread(target=bombear, daemon=True).start()

    def _abrir_processo(self):
        quadro = int(self.taxa * config.MIC_QUADRO_MS / 1000)
        if self.backend == "arecord":
            comando = ["arecord", "-q", "-f", "S16_LE", "-c", "1",
                       "-r", str(self.taxa), "-t", "raw"]
            if self.dispositivo not in (None, ''):
                comando[1:1] = ["-D", str(self.dispositivo)]
        else:
            comando = ["parec", "--format=s16le", "--rate", str(self.taxa), "--channels=1"]
            if self.dispositivo not in (None, ''):
                comando.append(f"--device={self.dispositivo}")
        self._processo = subprocess.Popen(comando, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL)

        def bombear():
            tamanho = quadro * 2
            while self._processo and self._processo.poll() is None:
                dados = self._processo.stdout.read(tamanho)
                if not dados:
                    break
                try:
                    self._fila.put_nowait(dados)
                except queue.Full:
                    pass
        threading.Thread(target=bombear, daemon=True).start()

    # ------------------------------------------------------------ leitura
    def ler_quadro(self, timeout: float = 0.5):
        try:
            return self._fila.get(timeout=timeout)
        except queue.Empty:
            return None

    def fechar(self):
        try:
            if self._stream is not None:
                if hasattr(self._stream, "stop"):
                    self._stream.stop()
                    self._stream.close()
                else:
                    self._stream.stop_stream()
                    self._stream.close()
                    self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._processo:
                self._processo.terminate()
        except Exception:  # noqa: BLE001
            pass
        self._stream = self._processo = None


# =============================================================== sinal
def para_array(bruto: bytes):
    if np is None:
        return None
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0


def rms(amostras) -> float:
    if amostras is None or len(amostras) == 0:
        return 0.0
    if np is not None:
        return float(np.sqrt(np.mean(np.square(amostras))))
    return math.sqrt(sum(a * a for a in amostras) / len(amostras))


def passa_alta(amostras, taxa: int, corte: float = 90.0):
    """Filtro de primeira ordem. Tira ronco de fonte e ar-condicionado.

    Implementado na mão porque depender de scipy só para isto é exagero, e porque
    um passa-alta de um polo já resolve o caso de microfone ruim.
    """
    if np is None or len(amostras) == 0:
        return amostras
    rc = 1.0 / (2 * math.pi * corte)
    dt = 1.0 / taxa
    alfa = rc / (rc + dt)
    saida = np.empty_like(amostras)
    anterior_entrada = amostras[0]
    anterior_saida = 0.0
    for i, x in enumerate(amostras):
        anterior_saida = alfa * (anterior_saida + x - anterior_entrada)
        anterior_entrada = x
        saida[i] = anterior_saida
    return saida


def normalizar(amostras, ganho_max: float = None):
    """Sobe o volume da fala baixa sem transformar chiado em rugido."""
    if np is None or len(amostras) == 0:
        return amostras
    ganho_max = ganho_max or config.MIC_GANHO_MAX
    pico = float(np.max(np.abs(amostras)))
    if pico < 1e-5:
        return amostras
    ganho = min(ganho_max, 0.89 / pico)
    return np.clip(amostras * ganho, -1.0, 1.0)


def preparar(amostras, taxa: int):
    """A cadeia inteira de tratamento antes de mandar para o reconhecedor."""
    if np is None:
        return amostras
    tratado = amostras - float(np.mean(amostras))      # tira nível DC
    tratado = passa_alta(tratado, taxa)
    return normalizar(tratado)


# =============================================================== VAD
class DetectorDeFala:
    """Máquina de estados sobre quadros de áudio: onde a fala começa e termina.

    Energia, não modelo: é suficiente para recortar trechos e não precisa de
    webrtcvad nem de GPU. O limiar é relativo ao ruído medido, então funciona
    tanto no quarto silencioso quanto ao lado do ventilador.
    """

    JANELA_RUIDO = 120        # ~3,6 s de histórico para estimar o fundo
    PERCENTIL = 0.25          # o fundo é o quartil inferior das energias recentes

    def __init__(self, taxa: int = None):
        self.taxa = taxa or config.MIC_TAXA
        self.ms_por_quadro = config.MIC_QUADRO_MS
        self.ruido = 0.004                 # chute inicial até haver histórico
        self.calibrado = False
        self._energias = deque(maxlen=self.JANELA_RUIDO)
        self.reiniciar()

    def reiniciar(self):
        self.falando = False
        self.acima = 0
        self.silencio_ms = 0
        self.duracao_ms = 0
        self.quadros = []

    @property
    def limiar(self) -> float:
        return max(0.006, self.ruido * config.VAD_FATOR_RUIDO)

    def calibrar(self, energia: float) -> None:
        """Reestima o ruído de fundo — e faz isso mesmo durante a fala.

        A primeira versão só calibrava no silêncio, e por isso quebrava justamente
        no caso que importa: com um ventilador ligado, o ruído já entra acima do
        limiar inicial, a fala "começa" e nunca mais termina, porque nunca há um
        quadro considerado silêncio para recalibrar.

        Agora o fundo é o quartil inferior das energias recentes. Entre sílabas e
        entre frases sempre existem quadros baixos, então o estimador acompanha o
        ambiente barulhento sem engolir a voz.
        """
        self._energias.append(energia)
        if len(self._energias) < 12:
            self.calibrado = False
            return
        ordenadas = sorted(self._energias)
        fundo = ordenadas[int(len(ordenadas) * self.PERCENTIL)]
        # Sobe rápido (ligaram o ar-condicionado), desce devagar (não cortar fala).
        self.ruido = fundo if fundo > self.ruido else self.ruido * 0.85 + fundo * 0.15
        self.calibrado = True

    def empurrar(self, quadro) -> dict:
        """Processa um quadro. Devolve o que mudou de estado.

        {"evento": "comecou"|"fim"|None, "audio": [...] quando termina}
        """
        energia = rms(quadro)
        self.duracao_ms += self.ms_por_quadro
        self.calibrar(energia)          # sempre, em qualquer estado

        if not self.falando:
            # Enquanto o ruído de fundo ainda não foi medido (primeiros ~360ms),
            # o palpite inicial de limiar pode ser mais baixo que o ruído real da
            # sala — um microfone ruim com chiado de fundo alto passaria por cima
            # dele e disparia "comecou" à toa. Por isso a partida só é aceita
            # depois que a calibração tem amostra suficiente; até lá o quadro
            # ainda entra na calibração, só não conta como início de fala.
            if energia > self.limiar and self.calibrado:
                self.acima += 1
                self.quadros.append(quadro)
                if self.acima >= config.VAD_QUADROS_INICIO:
                    self.falando = True
                    self.silencio_ms = 0
                    return {"evento": "comecou", "energia": energia}
            else:
                self.acima = 0
                self.quadros = self.quadros[-config.VAD_QUADROS_INICIO:]  # pré-fala
            return {"evento": None, "energia": energia}

        self.quadros.append(quadro)
        if energia > self.limiar:
            self.silencio_ms = 0
        else:
            self.silencio_ms += self.ms_por_quadro

        excedeu = len(self.quadros) * self.ms_por_quadro >= config.FALA_MAX_SEG * 1000
        if self.silencio_ms >= config.VAD_SILENCIO_MS or excedeu:
            audio = self.quadros
            duracao = len(audio) * self.ms_por_quadro - self.silencio_ms
            self.reiniciar()
            if duracao < config.FALA_MIN_MS:
                return {"evento": "curto_demais", "duracao_ms": duracao}
            return {"evento": "fim", "audio": audio, "duracao_ms": duracao,
                    "cortado": excedeu}
        return {"evento": None, "energia": energia}


# =============================================================== reconhecimento
class Reconhecedor:
    """Whisper (faster ou original) ou Vosk — o que estiver instalado."""

    def __init__(self, preferido: str = None):
        self.preferido = preferido or config.TRANSCRITOR
        self.motor = None
        self.nome = ""
        self._modelo = None
        self._erro = ""
        self._lock = threading.RLock()

    def disponiveis(self) -> list:
        achados = []
        for modulo, rotulo in (("faster_whisper", "faster"), ("whisper", "whisper"),
                               ("vosk", "vosk")):
            try:
                __import__(modulo)
                achados.append(rotulo)
            except Exception:  # noqa: BLE001
                continue
        return achados

    def carregar(self) -> str:
        with self._lock:
            if self._modelo is not None:
                return self.nome
            ordem = self.disponiveis()
            if not ordem:
                raise CapturaIndisponivel(
                    "Nenhum transcritor instalado. O recomendado é "
                    "`pip install faster-whisper` (roda em CPU e usa modelo pequeno). "
                    "Alternativas: `pip install openai-whisper` ou `pip install vosk`.")
            escolhido = self.preferido if self.preferido in ordem else ordem[0]

            try:
                if escolhido == "faster":
                    from faster_whisper import WhisperModel
                    self._modelo = WhisperModel(
                        config.WHISPER_MODELO,
                        device=config.AUDIO_DEVICE,
                        compute_type=config.AUDIO_COMPUTE_TYPE,
                    )
                elif escolhido == "whisper":
                    import whisper
                    self._modelo = whisper.load_model(
                        config.WHISPER_MODELO, device=config.AUDIO_DEVICE)
                else:
                    from vosk import KaldiRecognizer, Model
                    caminho = os.environ.get("HOSHINO_VOSK_MODELO", "")
                    self._modelo = Model(caminho) if caminho else Model(lang="pt")
                    self._KaldiRecognizer = KaldiRecognizer
                self.nome = escolhido
                self._erro = ""
                return escolhido
            except Exception as exc:
                self._modelo = None
                self.nome = ""
                self._erro = f"{type(exc).__name__}: {exc}"
                raise

    @property
    def carregado(self) -> bool:
        return self._modelo is not None

    @property
    def erro(self) -> str:
        return self._erro
    def _dica(self) -> str:
        """Viés de vocabulário: o reconhecedor erra menos o que ele espera ouvir."""
        return (f"Conversa em português do Brasil com a {config.ENTIDADE_NOME}. Termos possíveis: "
                + ", ".join(config.VOCABULARIO) + ".")

    def transcrever(self, amostras, taxa: int = None) -> str:
        taxa = taxa or config.MIC_TAXA
        if self._modelo is None:
            self.carregar()
        if np is None:
            return ""

        if self.nome == "faster":
            segmentos, _ = self._modelo.transcribe(
                amostras, language=config.WHISPER_IDIOMA, vad_filter=True,
                initial_prompt=self._dica(), beam_size=config.WHISPER_BEAM_SIZE,
                condition_on_previous_text=False)
            return " ".join(s.text.strip() for s in segmentos).strip()

        if self.nome == "whisper":
            resultado = self._modelo.transcribe(
                amostras, language=config.WHISPER_IDIOMA, initial_prompt=self._dica(),
                fp16=False, condition_on_previous_text=False)
            return (resultado.get("text") or "").strip()

        # vosk trabalha com bytes PCM
        import json as _json
        reconhecedor = self._KaldiRecognizer(self._modelo, taxa)
        pcm = (amostras * 32767).astype("int16").tobytes()
        reconhecedor.AcceptWaveform(pcm)
        return (_json.loads(reconhecedor.FinalResult()).get("text") or "").strip()

    def transcrever_detalhado(self, amostras, taxa: int = None) -> list[dict]:
        """Retorna segmentos com tempo; usado para alinhar Whisper a oradores."""
        taxa = taxa or config.MIC_TAXA
        if self._modelo is None:
            self.carregar()
        if np is None:
            return []

        if self.nome == "faster":
            segmentos, _ = self._modelo.transcribe(
                amostras,
                language=config.WHISPER_IDIOMA,
                vad_filter=True,
                initial_prompt=self._dica(),
                beam_size=config.WHISPER_BEAM_SIZE,
                condition_on_previous_text=False,
                word_timestamps=False,
            )
            saida = []
            for s in segmentos:
                texto = str(s.text or "").strip()
                if texto:
                    saida.append({
                        "inicio": float(getattr(s, "start", 0.0) or 0.0),
                        "fim": float(getattr(s, "end", 0.0) or 0.0),
                        "texto": texto,
                    })
            return saida

        # Os motores alternativos não oferecem a mesma interface temporal de
        # modo uniforme; retornamos um único segmento, mantendo compatibilidade.
        texto = self.transcrever(amostras, taxa)
        if not texto:
            return []
        duracao = len(amostras) / max(1, taxa)
        return [{"inicio": 0.0, "fim": float(duracao), "texto": texto}]


# =============================================================== diarização local
class DiarizadorLocal:
    """Agrupa uma janela de conversa e identifica até dois oradores localmente."""

    def __init__(self):
        self.pipeline = None
        self.erro = ""
        self._lock = threading.Lock()

    def disponivel(self) -> bool:
        try:
            import pyannote.audio  # noqa: F401
            import torch as _torch  # noqa: F401
            return True
        except Exception:
            return False

    def carregar(self):
        if self.pipeline is not None:
            return self.pipeline
        with self._lock:
            if self.pipeline is not None:
                return self.pipeline
            try:
                from pyannote.audio import Pipeline
                import torch as _torch
                kwargs = {}
                if config.HOSHINO_HF_TOKEN:
                    kwargs["token"] = config.HOSHINO_HF_TOKEN
                self.pipeline = Pipeline.from_pretrained(
                    config.AUDIO_DIARIZACAO_MODELO, **kwargs)
                if str(config.AUDIO_DEVICE).casefold() == "cpu":
                    try:
                        self.pipeline.to(_torch.device("cpu"))
                    except Exception:
                        pass
                self.erro = ""
                return self.pipeline
            except Exception as exc:
                self.pipeline = None
                self.erro = f"{type(exc).__name__}: {exc}"
                raise

    def diarizar(self, wav_path: str) -> list[dict]:
        pipeline = self.carregar()
        try:
            # Não forçamos dois: "até dois" significa 1 quando só uma voz aparece.
            saida = pipeline(wav_path, min_speakers=1, max_speakers=config.AUDIO_MAX_ORADORES)
        except TypeError:
            saida = pipeline(wav_path)

        annotation = getattr(saida, "exclusive_speaker_diarization", None)
        if annotation is None:
            annotation = getattr(saida, "speaker_diarization", saida)
        turnos = []
        for intervalo, _, speaker in annotation.itertracks(yield_label=True):
            turnos.append({
                "inicio": float(intervalo.start),
                "fim": float(intervalo.end),
                "speaker_id": str(speaker),
            })
        return turnos


def _speaker_para_segmento(segmento: dict, turnos: list[dict]) -> str:
    """Escolhe o orador com maior sobreposição com um segmento Whisper."""
    inicio = float(segmento.get("inicio", 0.0))
    fim = float(segmento.get("fim", inicio))
    melhor, melhor_overlap = "", 0.0
    for turno in turnos:
        a = max(inicio, float(turno["inicio"]))
        b = min(fim, float(turno["fim"]))
        overlap = max(0.0, b - a)
        if overlap > melhor_overlap:
            melhor_overlap = overlap
            melhor = str(turno["speaker_id"])
    return melhor or "orador_desconhecido"


class ProcessadorConversaDoisOradores:
    """Pipeline ASR + diarização em segundo plano sem parar a captura do microfone."""

    def __init__(self, reconhecedor: Reconhecedor, fila_saida: queue.Queue,
                 origem: str = "microfone"):
        self.reconhecedor = reconhecedor
        self.fila_saida = fila_saida
        self.origem = origem
        self.diarizador = DiarizadorLocal()
        self.fila_trabalho = queue.Queue(maxsize=3)
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self._rodar, daemon=True)
        self.thread.start()

    def enviar(self, amostras, segundos: float):
        try:
            self.fila_trabalho.put_nowait((amostras, segundos))
        except queue.Full:
            # Mantemos a captura viva. Se a CPU estiver saturada, é melhor
            # descartar a janela mais antiga que bloquear o microfone.
            try:
                self.fila_trabalho.get_nowait()
                self.fila_trabalho.put_nowait((amostras, segundos))
            except queue.Empty:
                pass

    def _rodar(self):
        while not self.parar.is_set():
            try:
                amostras, segundos = self.fila_trabalho.get(timeout=0.4)
            except queue.Empty:
                continue
            try:
                tratados = preparar(amostras, config.MIC_TAXA)
                detalhados = self.reconhecedor.transcrever_detalhado(
                    tratados, config.MIC_TAXA)
                if not detalhados:
                    continue

                # Só gastamos pyannote se houver realmente fala aproveitável.
                for s in detalhados:
                    ok, _, _ = texto_aproveitavel(
                        s["texto"], exigir_nome=False, min_palavras=1)
                    if not ok:
                        continue

                wav_path = os.path.join(
                    config.RUNTIME_DIR,
                    f".audio_diarizacao_{uuid.uuid4().hex[:10]}.wav")
                os.makedirs(config.RUNTIME_DIR, exist_ok=True)
                salvar_wav(tratados, wav_path, config.MIC_TAXA)
                try:
                    try:
                        turnos = self.diarizador.diarizar(wav_path)
                    except Exception as exc:
                        # Sem diarização, ainda entregamos a transcrição.
                        turnos = []
                        fallback_erro = f"{type(exc).__name__}: {exc}"
                        diagnostics = None
                        try:
                            from core import diagnostics as _diag
                            _diag.emit(
                                "audio.diarization_failed",
                                level="WARN",
                                error=fallback_erro,
                            )
                        except Exception:
                            pass

                    for s in detalhados:
                        ok, limpo, motivo = texto_aproveitavel(
                            s["texto"], exigir_nome=False, min_palavras=1)
                        if not ok:
                            continue
                        speaker = _speaker_para_segmento(s, turnos) if turnos else ""
                        self.fila_saida.put({
                            "texto": limpo,
                            "origem": self.origem,
                            "quando": datetime.now(),
                            "segundos": round(float(segundos), 1),
                            "speaker_id": speaker,
                            "modalidade": "fala",
                            "diarizacao": bool(turnos),
                        })
                finally:
                    try:
                        os.remove(wav_path)
                    except OSError:
                        pass
            except Exception:
                try:
                    from core import diagnostics as _diag
                    _diag.exception("audio.continuous_processing_failed", Exception("pipeline failure"))
                except Exception:
                    pass

    def fechar(self):
        self.parar.set()
        self.thread.join(timeout=1.0)


# =============================================================== limpeza
def texto_aproveitavel(texto: str, exigir_nome: bool = None,
                       min_palavras: int = None) -> tuple:
    """(aproveitável, texto limpo, motivo da recusa).

    O mínimo de palavras vale para a escuta contínua, onde falso positivo é caro.
    No modo apertar você decidiu falar apertando um botão: "para" e "silêncio" são
    ordens legítimas e passam.
    """
    limpo = re.sub(r"\s+", " ", (texto or "")).strip()
    if not limpo:
        return False, "", "veio vazio"
    if _ALUCINACAO.search(limpo):
        return False, "", "frase que o modelo inventa em cima de silêncio"
    minimo = config.MIC_PALAVRAS_MIN if min_palavras is None else min_palavras
    if len(limpo.split()) < minimo:
        return False, "", f"curto demais ({len(limpo.split())} palavra)"

    exigir = config.MIC_EXIGIR_NOME if exigir_nome is None else exigir_nome
    if exigir:
        if not _CHAMADO.match(limpo):
            return False, "", "não me chamou pelo nome"
        limpo = _CHAMADO.sub("", limpo).lstrip(" ,.:;!?").strip()
        if not limpo:
            return False, "", "só o nome, sem pedido"
    return True, limpo, ""


# =============================================================== transcritor
class Transcritor:
    """A porta única: o laço principal fala só com esta classe.

    Uso no modo apertar:      t.comecar()  ...  texto = t.parar()
    Uso no modo contínuo:     t.iniciar_escuta()  ... t.pegar()  ... t.parar_escuta()
    """

    def __init__(self, modo: str = None, dispositivo: str = "", origem: str = "microfone"):
        self.modo = modo or config.MIC_MODO
        # `dispositivo` permite apontar este transcritor para uma fonte
        # específica do PulseAudio (o monitor do Discord, o do jogo) em vez do
        # microfone padrão — é o que torna possível escutar vários canais ao
        # mesmo tempo, cada um com a sua origem marcada.
        self.dispositivo = dispositivo
        self.origem = origem
        self.fonte = None
        self.detector = DetectorDeFala()
        self.reconhecedor = Reconhecedor()
        self.gravando = False
        self.escutando = False
        self.erro = ""
        self.ultimo = ""
        self.fila = queue.Queue()
        self._thread = None
        self._processador_audio = None
        self._parar = threading.Event()
        self._buffer = []
        self._grupo_falas = []
        self._ultima_fala_fim = 0.0

    # ----------------------------------------------------------- diagnóstico
    def diagnostico(self) -> str:
        audio = FonteDeAudio.backends_disponiveis()
        motores = self.reconhecedor.disponiveis()
        estado_modelo = "carregado" if self.reconhecedor.carregado else (f"erro: {self.reconhecedor.erro}" if self.reconhecedor.erro else "não carregado")
        linhas = [f"captura: {', '.join(audio) or 'NENHUMA'}",
                  f"transcritor: {', '.join(motores) or 'NENHUM'}",
                  f"modo: {self.modo}",
                  f"modelo: {config.WHISPER_MODELO} ({config.WHISPER_IDIOMA}, beam={config.WHISPER_BEAM_SIZE})",
                  f"modelo ASR: {estado_modelo}",
                  f"diarização: {'até ' + str(config.AUDIO_MAX_ORADORES) + ' oradores' if config.AUDIO_DIARIZACAO else 'desligada'}"]
        if not audio:
            linhas.append("-> instale: pip install sounddevice  (ou o pacote alsa-utils)")
        if not motores:
            linhas.append("-> instale: pip install faster-whisper")
        return " | ".join(linhas)

    def pronto(self) -> bool:
        return bool(FonteDeAudio.backends_disponiveis()
                    and self.reconhecedor.disponiveis())

    def preparar_async(self, callback=None) -> None:
        """Carrega o ASR antes da primeira fala, sem bloquear o TUI."""
        if not getattr(config, "WHISPER_PRELOAD", True) or self.reconhecedor.carregado:
            return

        def worker():
            try:
                nome = self.reconhecedor.carregar()
                if callback:
                    callback(f"transcritor pronto: {nome}/{config.WHISPER_MODELO}")
            except Exception as exc:  # noqa: BLE001
                self.erro = f"{type(exc).__name__}: {exc}"
                if callback:
                    callback(f"transcritor falhou ao carregar: {self.erro}")

        threading.Thread(target=worker, daemon=True, name="hoshino-asr-preload").start()

    # -------------------------------------------------------- apertar/soltar
    def comecar(self) -> str:
        """Modo apertar: abre o microfone e começa a acumular."""
        if self.gravando:
            return "Já estou gravando."
        try:
            self.fonte = FonteDeAudio(dispositivo=self.dispositivo)
            backend = self.fonte.abrir()
        except CapturaIndisponivel as e:
            self.erro = str(e)
            return str(e)
        except Exception as e:  # noqa: BLE001
            self.erro = f"{type(e).__name__}: {e}"
            return f"Não consegui abrir o microfone: {self.erro}"

        self.gravando = True
        self._buffer = []
        self._parar.clear()

        def coletar():
            while not self._parar.is_set():
                quadro = self.fonte.ler_quadro(0.3)
                if quadro:
                    self._buffer.append(quadro)
        self._thread = threading.Thread(target=coletar, daemon=True)
        self._thread.start()
        return f"Gravando ({backend}). Aperte de novo para encerrar."

    def parar(self) -> dict:
        """Fecha o microfone e devolve {'texto', 'segundos', 'motivo'}."""
        if not self.gravando:
            return {"texto": "", "motivo": "não estava gravando"}
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        self.gravando = False
        bruto = b"".join(self._buffer)
        self._buffer = []
        if self.fonte:
            self.fonte.fechar()

        segundos = len(bruto) / 2 / config.MIC_TAXA
        if segundos < config.FALA_MIN_MS / 1000:
            return {"texto": "", "segundos": segundos, "motivo": "gravação curta demais"}

        amostras = preparar(para_array(bruto), config.MIC_TAXA)
        try:
            bruto_texto = self.reconhecedor.transcrever(amostras)
        except CapturaIndisponivel as e:
            return {"texto": "", "segundos": segundos, "motivo": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"texto": "", "segundos": segundos,
                    "motivo": f"falha ao transcrever: {type(e).__name__}: {e}"}

        # No modo apertar, você escolheu falar — não precisa me chamar pelo nome.
        ok, limpo, motivo = texto_aproveitavel(bruto_texto, exigir_nome=False,
                                               min_palavras=1)
        self.ultimo = limpo
        return {"texto": limpo if ok else "", "segundos": round(segundos, 1),
                "motivo": motivo, "bruto": bruto_texto}

    # ------------------------------------------------------------- contínuo
    def iniciar_escuta(self) -> str:
        """Modo contínuo; ASR e diarização rodam em segundo plano."""
        if self.escutando:
            return "Já estou escutando."
        try:
            self.fonte = FonteDeAudio(dispositivo=self.dispositivo)
            backend = self.fonte.abrir()
            self.reconhecedor.carregar()
        except CapturaIndisponivel as e:
            self.erro = str(e)
            return str(e)
        except Exception as e:  # noqa: BLE001
            self.erro = f"{type(e).__name__}: {e}"
            return f"Não consegui começar a escutar: {self.erro}"

        self.escutando = True
        self._parar.clear()
        self.detector.reiniciar()
        self._grupo_falas = []
        self._ultima_fala_fim = 0.0

        # Processador pesado separado: captura nunca fica bloqueada esperando
        # Whisper large-v3/pyannote.
        usar_diarizacao = bool(config.AUDIO_DIARIZACAO)
        if usar_diarizacao:
            self._processador_audio = ProcessadorConversaDoisOradores(
                self.reconhecedor, self.fila, self.origem)

        def processar_grupo():
            if not self._grupo_falas:
                return
            if np is None:
                self._grupo_falas = []
                return
            # Costura os trechos de fala com pequenos silêncios artificiais.
            # Isso preserva a noção de turnos para o diarizador sem reintroduzir
            # longos vazios que só aumentariam o custo.
            blocos = []
            zero = None
            for amostra in self._grupo_falas:
                if blocos and zero is None:
                    zero = np.zeros(int(config.MIC_TAXA * 0.18), dtype=np.float32)
                    blocos.append(zero)
                blocos.append(amostra)
            amostras = np.concatenate(blocos) if blocos else None
            duracao = (len(amostras) / config.MIC_TAXA) if amostras is not None else 0.0
            self._grupo_falas = []
            if amostras is None or duracao < config.FALA_MIN_MS / 1000:
                return
            if self._processador_audio:
                self._processador_audio.enviar(amostras, duracao)
            else:
                try:
                    texto = self.reconhecedor.transcrever(preparar(amostras, config.MIC_TAXA))
                    ok, limpo, motivo = texto_aproveitavel(
                        texto, exigir_nome=False, min_palavras=1)
                    if ok:
                        self.fila.put({
                            "texto": limpo, "origem": self.origem,
                            "quando": datetime.now(), "segundos": round(duracao, 1),
                            "speaker_id": "", "modalidade": "fala", "diarizacao": False,
                        })
                    else:
                        self.ultimo = f"(descartado: {motivo})"
                except Exception as e:  # noqa: BLE001
                    self.erro = f"{type(e).__name__}: {e}"

        def escutar():
            while not self._parar.is_set():
                quadro_bruto = self.fonte.ler_quadro(0.3)
                if not quadro_bruto:
                    # Um lote em silêncio não deve ficar preso para sempre.
                    if self._grupo_falas and self._ultima_fala_fim:
                        if time.monotonic() - self._ultima_fala_fim >= config.AUDIO_SILENCIO_FLUSH_SEG:
                            processar_grupo()
                            self._ultima_fala_fim = 0.0
                    continue

                quadro = para_array(quadro_bruto)
                estado = self.detector.empurrar(quadro)
                agora = time.monotonic()

                if estado.get("evento") == "fim":
                    amostras = np.concatenate(estado["audio"]) if np is not None else None
                    if amostras is not None:
                        self._grupo_falas.append(amostras)
                        self._ultima_fala_fim = agora
                    total = sum(len(x) for x in self._grupo_falas) / max(1, config.MIC_TAXA)
                    if total >= config.AUDIO_JANELA_SEG:
                        processar_grupo()
                        self._ultima_fala_fim = 0.0

                elif self._grupo_falas and not self.detector.falando:
                    if agora - self._ultima_fala_fim >= config.AUDIO_SILENCIO_FLUSH_SEG:
                        processar_grupo()
                        self._ultima_fala_fim = 0.0

        self._thread = threading.Thread(target=escutar, daemon=True)
        self._thread.start()
        alerta = " Só respondo se me chamarem pelo nome." if config.MIC_EXIGIR_NOME else ""
        diar = (
            f" Diarização local ativa para até {config.AUDIO_MAX_ORADORES} oradores."
            if usar_diarizacao else ""
        )
        return f"Escutando continuamente ({backend}).{diar}{alerta}"

    def parar_escuta(self) -> str:
        if not self.escutando:
            return "Não estava escutando."
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        # Entrega o último grupo ainda não processado.
        if self._grupo_falas:
            try:
                if self._processador_audio and np is not None:
                    blocos = []
                    for amostra in self._grupo_falas:
                        if blocos:
                            blocos.append(np.zeros(int(config.MIC_TAXA * 0.18), dtype=np.float32))
                        blocos.append(amostra)
                    final = np.concatenate(blocos)
                    self._processador_audio.enviar(final, len(final) / config.MIC_TAXA)
                self._grupo_falas = []
            except Exception:
                self._grupo_falas = []
        if self._processador_audio:
            self._processador_audio.fechar()
            self._processador_audio = None
        if self.fonte:
            self.fonte.fechar()
        self.escutando = False
        return "Parei de escutar. Microfone fechado."

    def pegar(self):
        """O laço principal chama isto a cada tick. None quando não há nada."""
        try:
            return self.fila.get_nowait()
        except queue.Empty:
            return None

    def alternar(self) -> str:
        """A mesma tecla serve para os dois modos."""
        if self.modo == "continuo":
            return self.parar_escuta() if self.escutando else self.iniciar_escuta()
        if self.gravando:
            resultado = self.parar()
            if resultado.get("texto"):
                return f"Ouvi ({resultado['segundos']}s): {resultado['texto']}"
            return f"Nada aproveitável ({resultado.get('motivo', 'sem motivo')})."
        return self.comecar()

    def trocar_modo(self, modo: str) -> str:
        if modo not in ("apertar", "continuo"):
            return "Modo tem que ser 'apertar' ou 'continuo'."
        if self.escutando:
            self.parar_escuta()
        if self.gravando:
            self.parar()
        self.modo = modo
        return (f"Microfone agora no modo {modo}."
                + (" Aperte F2 para abrir e fechar." if modo == "apertar"
                   else " F2 liga e desliga a escuta."))

    def estado(self) -> str:
        if self.escutando:
            return "escutando"
        if self.gravando:
            return "gravando"
        return "microfone fechado"


# =============================================================== utilidades
def salvar_wav(amostras, caminho: str, taxa: int = None) -> str:
    """Guarda um trecho para conferência — útil para achar defeito no microfone."""
    taxa = taxa or config.MIC_TAXA
    if np is None:
        return "numpy ausente."
    dados = (np.clip(amostras, -1, 1) * 32767).astype("int16").tobytes()
    with wave.open(caminho, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(taxa)
        f.writeframes(dados)
    return caminho


def transcrever_arquivo(caminho: str) -> str:
    """Transcreve um .wav já existente (para testar sem depender do microfone)."""
    if not os.path.isfile(caminho):
        return f"Não achei {caminho}."
    try:
        with wave.open(caminho, "rb") as f:
            taxa = f.getframerate()
            bruto = f.readframes(f.getnframes())
    except wave.Error as e:
        return f"Não consegui ler o wav: {e}"
    if np is None:
        return "numpy ausente."
    amostras = preparar(para_array(bruto), taxa)
    reconhecedor = Reconhecedor()
    try:
        return reconhecedor.transcrever(amostras, taxa) or "(silêncio)"
    except CapturaIndisponivel as e:
        return str(e)


def medir_microfone(segundos: float = 3.0) -> str:
    """Diagnóstico de microfone ruim: mede ruído de fundo e pico de fala."""
    try:
        fonte = FonteDeAudio()
        fonte.abrir()
    except Exception as e:  # noqa: BLE001
        return f"Não consegui abrir o microfone: {e}"
    energias, limite = [], time.time() + segundos
    while time.time() < limite:
        quadro = fonte.ler_quadro(0.3)
        if quadro:
            energias.append(rms(para_array(quadro)))
    fonte.fechar()
    if not energias:
        return "Abri o microfone mas não chegou áudio nenhum."
    energias.sort()
    piso = energias[len(energias) // 10]
    pico = energias[-1]
    relacao = pico / max(piso, 1e-6)
    veredito = ("sinal bom" if relacao > 12 else
                "sinal fraco — fale mais perto ou suba o ganho do microfone"
                if relacao > 4 else
                "praticamente só ruído — confira se o microfone certo está selecionado")
    return (f"ruído de fundo {piso:.4f} | pico {pico:.4f} | relação {relacao:.1f}x -> "
            f"{veredito}")
