"""Ponte de áudio PC1 ↔ PC2 pela própria Central (pedido humano 11/11: "não quero depender de apps externos").

Substitui o SonoBus. Usa só o PulseAudio/PipeWire dos dois PCs (`parec`/`pacat`) e a porta da Central na rede
local, com o mesmo código de pareamento do painel.

- **Som do PC1 → PC2:** a Central do PC1 grava o monitor da saída padrão (tudo o que toca no PC1) e manda por
  um GET contínuo (`/api/control/pc2/som`). O painel do PC2 toca na saída padrão de lá.
- **Microfone do PC2 → PC1:** o painel do PC2 grava o microfone padrão de lá e manda por um POST contínuo
  (`/api/control/pc2/microfone`, chunked). A Central do PC1 toca em `voz_do_pc2`, cujo monitor é o microfone
  padrão do PC1: entidades e transcrição ouvem como antes.

Formato: PCM s16le 48 kHz, som em 2 canais e microfone em 1, sem compressão (~1,5 e ~0,8 Mbit/s numa LAN).

Atraso limitado: quem recebe lê a rede sem parar e, quando o tocador fica para trás (relógios de placas de som
diferentes ou rede engasgada), descarta o excesso em vez de acumular segundos de atraso. O cano até o `pacat`
é encurtado para não esconder outro terço de segundo.

Sem Qt: usado pelo backend (iniciar_entidades) e pelo painel (central_native).
"""
from __future__ import annotations

import collections
import fcntl
import http.client
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

RATE = 48000
SOM_CANAIS = 2
MIC_CANAIS = 1
BLOCO_MS = 20
LATENCIA_TOCADOR_MS = 60
FOLGA_MAX_MS = 150      # acima disso na fila, descarta…
FOLGA_ALVO_MS = 40      # …até sobrar isto
SAIDA_MIC_PC1 = 'voz_do_pc2'
ORIGEM_SOM_PC1 = '@DEFAULT_MONITOR@'
F_SETPIPE_SZ = 1031


def bytes_por_ms(canais: int) -> int:
    return RATE * 2 * canais // 1000


def comando_gravar(dispositivo: str | None, canais: int, nome: str) -> list[str]:
    cmd = ['parec', '--raw', '--format=s16le', f'--rate={RATE}', f'--channels={canais}',
           f'--latency-msec={BLOCO_MS}', '--client-name=Central Hoshino e Lilith', f'--stream-name={nome}']
    return cmd + ([f'--device={dispositivo}'] if dispositivo else [])


def comando_tocar(dispositivo: str | None, canais: int, nome: str) -> list[str]:
    cmd = ['pacat', '--playback', '--raw', '--format=s16le', f'--rate={RATE}', f'--channels={canais}',
           f'--latency-msec={LATENCIA_TOCADOR_MS}', '--client-name=Central Hoshino e Lilith', f'--stream-name={nome}']
    return cmd + ([f'--device={dispositivo}'] if dispositivo else [])


def _encurtar_cano(arquivo) -> None:
    try:
        fcntl.fcntl(arquivo.fileno(), F_SETPIPE_SZ, 4096)
    except OSError:
        pass


class Tocador:
    """Recebe blocos PCM de quem lê a rede e toca com pacat, sem deixar o atraso crescer."""

    def __init__(self, dispositivo: str | None, canais: int, nome: str, comando=None):
        self.canais = canais
        self.quadro = 2 * canais
        self.max_bytes = FOLGA_MAX_MS * bytes_por_ms(canais)
        self.alvo_bytes = FOLGA_ALVO_MS * bytes_por_ms(canais)
        self.fila: collections.deque[bytes] = collections.deque()
        self.na_fila = 0
        self.descartado_ms = 0
        self.recebido = 0
        self.erro = ''
        self.fechado = False
        self.cond = threading.Condition()
        cmd = comando or comando_tocar(dispositivo, canais, nome)
        # stderr fora: avisos do pacat num cano que ninguém lê travariam o tocador.
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
        _encurtar_cano(self.proc.stdin)
        self.escritor = threading.Thread(target=self._escrever, daemon=True, name='ponte-tocador')
        self.escritor.start()

    def alimentar(self, dados: bytes) -> None:
        if self.proc.poll() is not None:
            raise RuntimeError(self._motivo_saida())
        with self.cond:
            self.fila.append(dados)
            self.na_fila += len(dados)
            self.recebido += len(dados)
            if self.na_fila > self.max_bytes:
                sobra = self.na_fila - self.alvo_bytes
                sobra -= sobra % self.quadro
                self._descartar(sobra)
            self.cond.notify()

    def _descartar(self, quanto: int) -> None:
        tirado = 0
        while self.fila and tirado < quanto:
            bloco = self.fila.popleft()
            falta = quanto - tirado
            if len(bloco) > falta:
                self.fila.appendleft(bloco[falta:])
                bloco = bloco[:falta]
            tirado += len(bloco)
        self.na_fila -= tirado
        self.descartado_ms += tirado // bytes_por_ms(self.canais)

    def _escrever(self) -> None:
        try:
            while True:
                with self.cond:
                    while not self.fila and not self.fechado:
                        self.cond.wait(0.5)
                    if self.fechado and not self.fila:
                        return
                    bloco = self.fila.popleft()
                    self.na_fila -= len(bloco)
                self.proc.stdin.write(bloco)
                self.proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self.erro = self._motivo_saida() or type(exc).__name__

    def _motivo_saida(self) -> str:
        if self.proc.poll() is None:
            return ''
        return f'o tocador (pacat) saiu com código {self.proc.returncode}; a saída de som existe?'

    def fechar(self) -> None:
        with self.cond:
            self.fechado = True
            self.fila.clear()
            self.na_fila = 0
            self.cond.notify()
        _encerrar(self.proc)


def _encerrar(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(2)
    for cano in (proc.stdin, proc.stdout):
        try:
            if cano is not None:
                cano.close()
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------- lado do PC1 (backend da Central)

class Servidor:
    """Estado das duas pontes no PC1. Uma conexão de cada tipo por vez: a nova substitui a anterior."""

    def __init__(self, gravar=None, tocar=None):
        self.lock = threading.Lock()
        self.ativos: dict[str, dict] = {}
        self.geracao = {'som': 0, 'microfone': 0}
        self.comando_gravar = gravar
        self.comando_tocar = tocar

    def estado(self) -> dict:
        with self.lock:
            agora = time.time()
            return {tipo: dict(conectado=True, cliente=item['cliente'], desde=item['desde'],
                               segundos=int(agora - item['desde']), bytes=item['bytes'],
                               descartado_ms=item.get('descartado_ms', 0))
                    for tipo, item in self.ativos.items()}

    def _entrar(self, tipo: str, cliente: str, encerrar) -> int:
        with self.lock:
            anterior = self.ativos.get(tipo)
            self.geracao[tipo] += 1
            geracao = self.geracao[tipo]
            self.ativos[tipo] = dict(cliente=cliente, desde=time.time(), bytes=0, encerrar=encerrar, geracao=geracao)
        if anterior:
            anterior['encerrar']()
        return geracao

    def _sair(self, tipo: str, geracao: int) -> None:
        with self.lock:
            if self.ativos.get(tipo, {}).get('geracao') == geracao:
                self.ativos.pop(tipo)

    def _contar(self, tipo: str, geracao: int, n: int, descartado_ms: int | None = None) -> bool:
        with self.lock:
            item = self.ativos.get(tipo)
            if not item or item['geracao'] != geracao:
                return False
            item['bytes'] += n
            if descartado_ms is not None:
                item['descartado_ms'] = descartado_ms
            return True

    def servir_som(self, handler) -> None:
        """GET contínuo: manda o que toca no PC1 até o PC2 desconectar ou outra conexão substituir esta."""
        cmd = (self.comando_gravar or comando_gravar)(ORIGEM_SOM_PC1, SOM_CANAIS, 'Ponte para o PC2')
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        geracao = self._entrar('som', handler.client_address[0], lambda: _encerrar(proc))
        handler.close_connection = True
        try:
            handler.send_response(200)
            handler.send_header('Content-Type', f'audio/L16;rate={RATE};channels={SOM_CANAIS}')
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('Connection', 'close')
            handler.end_headers()
            handler.connection.settimeout(5)  # PC2 parado de ler por 5 s = desconectou
            bloco = BLOCO_MS * bytes_por_ms(SOM_CANAIS)
            while True:
                dados = proc.stdout.read1(bloco)
                if not dados:
                    break
                handler.wfile.write(dados)
                if not self._contar('som', geracao, len(dados)):
                    break
        except (BrokenPipeError, ConnectionError, TimeoutError, OSError):
            pass
        finally:
            _encerrar(proc)
            self._sair('som', geracao)

    def receber_microfone(self, handler) -> None:
        """POST chunked contínuo: toca o microfone do PC2 em `voz_do_pc2` (microfone padrão do PC1)."""
        if handler.headers.get('Transfer-Encoding', '').lower() != 'chunked':
            raise ValueError('Microfone do PC2: envie em Transfer-Encoding chunked.')
        tocador = Tocador(SAIDA_MIC_PC1, MIC_CANAIS, 'Microfone do PC2',
                          comando=(self.comando_tocar(SAIDA_MIC_PC1, MIC_CANAIS) if self.comando_tocar else None))
        geracao = self._entrar('microfone', handler.client_address[0], tocador.fechar)
        handler.close_connection = True
        try:
            while True:
                linha = handler.rfile.readline(64)
                if not linha:
                    break
                tamanho = int(linha.split(b';')[0].strip() or b'0', 16)
                if tamanho == 0:
                    handler.rfile.readline(64)
                    break
                if tamanho > 256 * 1024:
                    raise ValueError('Bloco do microfone grande demais.')
                dados = handler.rfile.read(tamanho)
                handler.rfile.read(2)
                if len(dados) < tamanho:
                    break
                tocador.alimentar(dados)
                if not self._contar('microfone', geracao, len(dados), tocador.descartado_ms):
                    break
        except (ConnectionError, TimeoutError, ValueError, OSError):
            pass
        finally:
            tocador.fechar()
            self._sair('microfone', geracao)
        try:
            handler.send_response(200)
            handler.send_header('Content-Length', '0')
            handler.send_header('Connection', 'close')
            handler.end_headers()
        except OSError:
            pass

    def encerrar(self) -> None:
        with self.lock:
            itens = list(self.ativos.values())
            self.ativos.clear()
        for item in itens:
            item['encerrar']()


# ---------------------------------------------------------------- lado do PC2 (painel)

class Cliente:
    """No painel do PC2: ouve o som do PC1 e manda o microfone daqui, reconectando sozinho."""

    def __init__(self, base: str, token: str, gravar=None, tocar=None):
        self.base = base.rstrip('/')
        self.token = token
        self.comando_gravar = gravar
        self.comando_tocar = tocar
        self.lock = threading.Lock()
        self.querer = {'som': False, 'microfone': False}
        self.situacao = {'som': 'desligado', 'microfone': 'desligado'}
        self.threads: dict[str, threading.Thread] = {}
        self.recursos: dict[str, object] = {}
        self.parado = threading.Event()

    def ligar(self, tipo: str, ligado: bool) -> None:
        with self.lock:
            self.querer[tipo] = bool(ligado)
            vivo = self.threads.get(tipo)
            if ligado and not (vivo and vivo.is_alive()):
                alvo = self._laco_som if tipo == 'som' else self._laco_microfone
                self.threads[tipo] = threading.Thread(target=alvo, daemon=True, name='ponte-' + tipo)
                self.threads[tipo].start()
            if not ligado:
                self.situacao[tipo] = 'desligado'
        if not ligado:
            self._soltar(tipo)

    def _soltar(self, tipo: str) -> None:
        recurso = self.recursos.pop(tipo, None)
        if isinstance(recurso, Tocador):
            recurso.fechar()
        elif isinstance(recurso, subprocess.Popen):
            _encerrar(recurso)
        conexao = self.recursos.pop(tipo + '_conexao', None)
        try:
            if conexao is not None:
                conexao.close()
        except OSError:
            pass

    def _ativo(self, tipo: str) -> bool:
        return self.querer[tipo] and not self.parado.is_set()

    def _esperar(self, segundos: float, tipo: str) -> None:
        fim = time.monotonic() + segundos
        while self._ativo(tipo) and time.monotonic() < fim:
            time.sleep(0.2)

    def _laco_som(self) -> None:
        while self._ativo('som'):
            espera = 2.0
            try:
                req = Request(self.base + '/api/control/pc2/som', headers={'Authorization': 'Bearer ' + self.token})
                resposta = urlopen(req, timeout=10)
                self.recursos['som_conexao'] = resposta
                tocador = Tocador(None, SOM_CANAIS, 'Som do PC1',
                                  comando=(self.comando_tocar(None, SOM_CANAIS) if self.comando_tocar else None))
                self.recursos['som'] = tocador
                self.situacao['som'] = 'tocando o som do PC1 desde ' + time.strftime('%H:%M:%S')
                bloco = BLOCO_MS * bytes_por_ms(SOM_CANAIS)
                while self._ativo('som'):
                    dados = resposta.read(bloco)
                    if not dados:
                        raise ConnectionError('o PC1 encerrou a ponte')
                    tocador.alimentar(dados)
            except HTTPError as exc:
                espera = 15.0
                self.situacao['som'] = f'o PC1 recusou a ponte (HTTP {exc.code}); a Central de lá está atualizada?'
            except Exception as exc:  # rede, tocador ou Central fechada: tenta de novo
                if self._ativo('som'):
                    self.situacao['som'] = 'sem som do PC1 (' + (str(exc)[:120] or type(exc).__name__) + '); tentando de novo'
            finally:
                self._soltar('som')
            self._esperar(espera, 'som')

    def _laco_microfone(self) -> None:
        while self._ativo('microfone'):
            espera = 2.0
            proc = None
            try:
                url = urlsplit(self.base)
                conexao = http.client.HTTPConnection(url.hostname, url.port, timeout=10)
                self.recursos['microfone_conexao'] = conexao
                conexao.putrequest('POST', '/api/control/pc2/microfone')
                conexao.putheader('Authorization', 'Bearer ' + self.token)
                conexao.putheader('Content-Type', 'application/octet-stream')
                conexao.putheader('Transfer-Encoding', 'chunked')
                conexao.endheaders()
                cmd = (self.comando_gravar or comando_gravar)(None, MIC_CANAIS, 'Microfone para o PC1')
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
                self.recursos['microfone'] = proc
                self.situacao['microfone'] = 'mandando o microfone deste PC desde ' + time.strftime('%H:%M:%S')
                bloco = BLOCO_MS * bytes_por_ms(MIC_CANAIS)
                while self._ativo('microfone'):
                    dados = proc.stdout.read1(bloco)
                    if not dados:
                        raise RuntimeError('o microfone deste PC parou')
                    conexao.send(b'%x\r\n' % len(dados) + dados + b'\r\n')
            except Exception as exc:
                if self._ativo('microfone'):
                    self.situacao['microfone'] = 'microfone não chega ao PC1 (' + (str(exc)[:120] or type(exc).__name__) + '); tentando de novo'
            finally:
                self._soltar('microfone')
            self._esperar(espera, 'microfone')

    def estado(self) -> dict:
        return dict(self.situacao)

    def parar(self) -> None:
        self.parado.set()
        for tipo in ('som', 'microfone'):
            self.querer[tipo] = False
            self._soltar(tipo)
