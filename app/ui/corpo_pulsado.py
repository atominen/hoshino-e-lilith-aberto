#!/usr/bin/env python3
"""Corpo expressivo dos orbes: núcleo LIF original do Pestinha, só leitura.

A rede fica depois do estado emocional. Recebe o que o overlay já tem (estado da
presença, emoções do `expression_profile`) e as interações com o próprio orbe
(cutucar, arrastar, carinho) e devolve só a expressão do corpo: amplitude e
velocidade do balanço, brilho e sobressalto. Não alimenta decisões, emoções,
humor nem prompt; nada daqui volta para a entidade.

Roda como processo auxiliar do overlay (`--serve`), com o Python que tem numpy.
O overlay continua no Python do sistema com Qt; se este processo faltar ou cair,
o orbe volta à animação fixa. O estado do corpo (habituação) fica em
`compartilhado/runtime/overlay/corpo_<entidade>.json`, fora da mente da entidade.

Pestinha: GPL-3.0, checkout fixado em `compartilhado/servicos/pestinha`
(fora do git). Ensaio que aprovou este desenho: scripts/ensaiar_corpo_orbe_pestinha.py.

Protocolo (uma linha JSON por mensagem):
  entrada  {"tipo":"estado","entidade":"lilith","status":"working","emocoes":{"curiosidade":0.6},"reduzido":false}
           {"tipo":"cutucar"|"carinho","entidade":"lilith"}
           {"tipo":"arrastar","entidade":"lilith","ativo":true}
  saída    {"corpos":{"lilith":{"rotulo":"curioso","animacao":{...}}, ...}}   a 10 Hz
"""
import argparse
import hashlib
import json
import math
import queue
import signal
import sys
import threading
import time
from pathlib import Path

UPSTREAM_COMMIT = '984fb8677093cd868bf4f9712a43f19b44215f75'
STEP_MS = 100
DT = STEP_MS / 1000
PERFIL = dict(emotion_tau=5.0, emotion_dwell=1.5)       # perfil "normal" do upstream
EXPRESSAO = ('STARTLE', 'WATCH', 'WANDER', 'CHEER', 'SETTLE', 'DROWSE', 'ANGRY', 'SAD')

# Emoção real -> canal sensorial sem habituação (d = 0) usado como tônus.
TONUS = {
    'alegria': 'TOY_NEAR', 'orgulho': 'TOY_NEAR',
    'afeto': 'CARESS', 'amor': 'CARESS',
    'curiosidade': 'BOREDOM', 'desejo': 'BOREDOM',
    'raiva': 'RECUSA',
    'tristeza': 'LONELY', 'vergonha': 'LONELY',
    'tedio': 'SILENCE',
    'medo': 'ANTICIPATE', 'apreensao': 'ANTICIPATE',
}
STATUS_TONUS = {
    'working': {'WORK': 1.0}, 'speaking': {'SOCIAL': 0.8},
    'sleeping': {'FATIGUE': 1.0, 'SILENCE': 1.0}, 'offline': {'FATIGUE': 1.0, 'SILENCE': 1.0},
}
STATUS_CONHECIDOS = {'offline', 'sleeping', 'starting', 'stopping', 'awake', 'working',
                     'speaking', 'waiting', 'error'}
QUIETOS = {'sleeping', 'offline'}

# BOREDOM->PLAYFUL = 0 é do adaptador: BOREDOM serve de tônus da curiosidade e, com a
# ligação ao PLAYFUL, a curiosidade real aparecia como "feliz" em 100% das amostras.
ADAPTADOR = {'BOREDOM->PLAYFUL': 0.0}
# Propostos a partir das descrições de identidade (05/11/2026); ajustáveis com aval humano.
TEMPERAMENTOS = {
    'lilith': {'CURIOUS': 1.3, 'NOVELTY->CURIOUS': 1.2, 'POKE->PLAYFUL': 1.2,
               'DRAG->CURIOUS': 1.3, 'DRAG->FRUSTRATION': 0.8, **ADAPTADOR},
    'hoshino': {'TIRED': 1.25, 'CALM': 1.2, 'CARESS->CALM': 1.3,
                'POKE->PLAYFUL': 0.9, 'DRAG->FRUSTRATION': 1.2, **ADAPTADOR},
    'alistair': dict(ADAPTADOR),
}
MAX_LINHA = 4096
SALVAR_A_CADA_S = 300


def semente(entidade):
    return int(hashlib.sha256(f'corpo-orbe:{entidade}'.encode()).hexdigest()[:8], 16) % 2**31


def carregar_nucleo(upstream):
    """Importa o núcleo do checkout fixado; recusa outra revisão."""
    upstream = Path(upstream).resolve()
    head = (upstream / '.git/HEAD').read_text(encoding='utf-8').strip()
    if head != UPSTREAM_COMMIT:
        raise RuntimeError(f'Pestinha em {head[:12]}; esperado {UPSTREAM_COMMIT[:12]}')
    sys.path.insert(0, str(upstream))
    import numpy as np
    from pestinha.core.nervous_system import LIFBrain, MotorDecoder
    from pestinha.core.emotion import EmotionState
    fonte = (upstream / 'pestinha/core/nervous_system.py').read_bytes()
    revisao = hashlib.sha256(fonte + json.dumps(TEMPERAMENTOS, sort_keys=True).encode()
                             + json.dumps(TONUS, sort_keys=True).encode()).hexdigest()[:12]
    return (LIFBrain, MotorDecoder, EmotionState, np), revisao


class CorpoPulsado:
    """Uma rede por entidade. Só lê o estado; devolve expressão."""

    def __init__(self, nucleo, entidade, revisao, ruido=None, temperamento=None):
        LIFBrain, MotorDecoder, EmotionState, np = nucleo
        self.np = np
        self.entidade, self.revisao = entidade, revisao
        self.brain = LIFBrain(seed=semente(entidade),
                              temperament=TEMPERAMENTOS[entidade] if temperamento is None else temperamento)
        if ruido is not None:
            self.brain.rng = np.random.default_rng(ruido)
        self.decoder = MotorDecoder()
        self.emocao = EmotionState()
        self.emocao.since = float('-inf')
        self.agora = 0.0
        self.pulsos = {}
        self.arrastando = False
        self.arraste = 0.0
        self.quieto_desde = None

    # interações com o próprio orbe (amplitudes do ComputerSenses upstream)
    def cutucar(self):
        self.pulsos['POKE'] = (0.8, self.agora, 1.5)

    def acariciar(self):
        self.pulsos['CARESS'] = (0.8, self.agora, 3.0)

    def arrastar(self, ativo):
        self.arrastando = bool(ativo)

    def entradas(self, status, perfil):
        ins = dict(STATUS_TONUS.get(status, {}))
        if perfil.get('available'):
            for nome, valor in (perfil.get('emotions') or {}).items():
                canal = TONUS.get(nome)
                if canal:
                    ins[canal] = max(ins.get(canal, 0.0), float(valor))
        for canal, (forca, t0, tau) in list(self.pulsos.items()):
            nivel = forca * math.exp(-(self.agora - t0) / tau)
            if nivel < 0.01:
                del self.pulsos[canal]
            else:
                ins[canal] = max(ins.get(canal, 0.0), nivel)
        self.arraste += ((1.0 if self.arrastando else 0.0) - self.arraste) * (1 - math.exp(-DT / 0.7))
        if self.arraste > 0.01:
            ins['DRAG'] = self.arraste
        return ins

    def _recuperar_quieto(self):
        """Habituação recuperada pelo tempo sem simular (mesma fórmula do load() upstream)."""
        if self.quieto_desde is None:
            return
        decorrido = max(0.0, self.agora - self.quieto_desde)
        Ns = self.brain.Ns
        self.brain.p[:Ns] = 1.0 - (1.0 - self.brain.p[:Ns]) * self.np.exp(-decorrido / self.brain.s_tau_rec[:Ns])
        self.quieto_desde = self.agora

    def passo(self, status, perfil, reduzido=False, agora=None, simular_quieto=True):
        self.agora = self.agora + DT if agora is None else float(agora)
        quieto = status in QUIETOS
        if quieto and not simular_quieto:
            if self.quieto_desde is None:
                self.quieto_desde = self.agora
            self.pulsos.clear()
            motores = {m: 0.0 for m in EXPRESSAO}
        else:
            self._recuperar_quieto()
            self.quieto_desde = None
            self.brain.stimulate(self.entradas(status, perfil))
            self.brain.step(STEP_MS)
            motores = {m: hz for m, hz in self.brain.motor_activity().items() if m in EXPRESSAO}
        comportamento, _ = self.decoder.update(motores, now=self.agora)
        rotulo = self.emocao.update(motores, DT, PERFIL, now=self.agora)
        if quieto:
            rotulo = 'dormindo'
        v, a = self.emocao.valence, self.emocao.arousal
        animacao = dict(
            amplitude_px=0.0 if reduzido else round(1.6 * (1 + max(-0.8, a)), 2),
            velocidade=0.0 if reduzido else round(1 + 0.8 * max(0.0, a), 2),
            brilho=round(0.5 + 0.35 * v, 2),
            sobressalto=(rotulo == 'assustado') and not reduzido,
        )
        return dict(rotulo=rotulo, comportamento=comportamento, valencia=v, ativacao=a,
                    motores=motores, animacao=animacao)

    # persistência: o arquivo upstream mais identidade e revisão, numa só troca atômica
    def salvar(self, caminho):
        self._recuperar_quieto()
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_name(caminho.name + '.nucleo')
        self.brain.save(tmp)
        dados = json.loads(tmp.read_text(encoding='utf-8'))
        tmp.unlink()
        dados.update(entidade=self.entidade, revisao_corpo=self.revisao)
        parcial = caminho.with_name(caminho.name + '.tmp')
        parcial.write_text(json.dumps(dados, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        parcial.replace(caminho)

    def carregar(self, caminho):
        try:
            dados = json.loads(Path(caminho).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return False, 'ilegível'
        if not isinstance(dados, dict):
            return False, 'formato'
        if dados.get('entidade') != self.entidade:
            return False, 'outra entidade'
        if dados.get('revisao_corpo') != self.revisao:
            return False, 'outra revisão'
        ok = self.brain.load(caminho)       # valida versão, semente, forma e domínio
        return ok, 'ok' if ok else 'recusado pelo núcleo'


def perfil_de(emocoes):
    forcas = {k: v for k, v in emocoes.items() if v >= 0.18}
    return dict(available=True, dominant=max(forcas, key=forcas.get) if forcas else None, emotions=forcas)


def interpretar(linha):
    """Mensagem validada do overlay, ou None. Nunca confia no conteúdo."""
    if len(linha) > MAX_LINHA:
        return None
    try:
        msg = json.loads(linha)
    except ValueError:
        return None
    if not isinstance(msg, dict) or msg.get('entidade') not in TEMPERAMENTOS:
        return None
    tipo = msg.get('tipo')
    if tipo in ('cutucar', 'carinho'):
        return dict(tipo=tipo, entidade=msg['entidade'])
    if tipo == 'arrastar':
        return dict(tipo=tipo, entidade=msg['entidade'], ativo=msg.get('ativo') is True)
    if tipo != 'estado':
        return None
    status = msg.get('status') if msg.get('status') in STATUS_CONHECIDOS else 'awake'
    emocoes = {}
    bruto = msg.get('emocoes')
    if isinstance(bruto, dict):
        for nome, valor in bruto.items():
            if nome in TONUS and isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor):
                emocoes[nome] = min(1.0, max(0.0, float(valor)))
    return dict(tipo=tipo, entidade=msg['entidade'], status=status, emocoes=emocoes,
                reduzido=msg.get('reduzido') is True)


def servir(root, upstream, entrada=sys.stdin, saida=sys.stdout, max_ticks=None):
    nucleo, revisao = carregar_nucleo(upstream)
    pasta = Path(root) / 'compartilhado/runtime/overlay'
    corpos, estados = {}, {}
    for entidade in TEMPERAMENTOS:
        corpo = CorpoPulsado(nucleo, entidade, revisao)
        arquivo = pasta / f'corpo_{entidade}.json'
        if arquivo.exists():
            ok, motivo = corpo.carregar(arquivo)
            if not ok:
                print(f'[corpo] estado de {entidade} não carregado: {motivo}; começando do zero', file=sys.stderr)
        corpos[entidade] = corpo
        estados[entidade] = dict(status='offline', emocoes={}, reduzido=False)

    mensagens, fim = queue.Queue(), threading.Event()

    def ler():
        for linha in entrada:
            mensagens.put(linha)
        fim.set()
    threading.Thread(target=ler, daemon=True).start()

    def salvar_todos():
        for entidade, corpo in corpos.items():
            try:
                corpo.salvar(pasta / f'corpo_{entidade}.json')
            except (OSError, ValueError) as exc:
                print(f'[corpo] não salvou {entidade}: {exc}', file=sys.stderr)

    parar = threading.Event()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, lambda *_: parar.set())
    inicio = proximo = time.monotonic()
    ultimo_salvo, ticks = inicio, 0
    while not parar.is_set() and not (fim.is_set() and mensagens.empty()):
        while not mensagens.empty():
            msg = interpretar(mensagens.get_nowait())
            if not msg:
                continue
            corpo = corpos[msg['entidade']]
            if msg['tipo'] == 'cutucar':
                corpo.cutucar()
            elif msg['tipo'] == 'carinho':
                corpo.acariciar()
            elif msg['tipo'] == 'arrastar':
                corpo.arrastar(msg['ativo'])
            else:
                estados[msg['entidade']] = msg
        agora = time.monotonic() - inicio
        saidas = {}
        for entidade, corpo in corpos.items():
            e = estados[entidade]
            r = corpo.passo(e['status'], perfil_de(e['emocoes']), e['reduzido'], agora=agora, simular_quieto=False)
            saidas[entidade] = dict(rotulo=r['rotulo'], animacao=r['animacao'])
        try:
            saida.write(json.dumps(dict(corpos=saidas), ensure_ascii=False) + '\n')
            saida.flush()
        except (BrokenPipeError, ValueError):
            break
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        if time.monotonic() - ultimo_salvo >= SALVAR_A_CADA_S:
            salvar_todos(); ultimo_salvo = time.monotonic()
        proximo += DT
        espera = proximo - time.monotonic()
        if espera > 0:
            parar.wait(espera)
        else:
            proximo = time.monotonic()      # atrasou: não acumula passos
    salvar_todos()
    return ticks


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--upstream', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'compartilhado/servicos/pestinha')
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    if not args.serve:
        parser.error('use --serve (processo auxiliar do overlay)')
    servir(args.root.resolve(), args.upstream)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
