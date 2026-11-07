"""
Humor.

Modelo PAD (prazer, ativação, domínio) com apreciação de eventos no estilo OCC:
não existe "emoção" solta — existe evento avaliado. A tarefa falhou: cai o prazer
e o domínio, sobe a ativação (isso é frustração). O usuário voltou depois de horas:
sobe prazer e ativação. Descobriu algo: sobe prazer.

O estado decai exponencialmente de volta para a linha de base, com meia-vida de
~45 minutos, então nada gruda para sempre e nada evapora no tick seguinte.

Duas decisões que importam para não virar teatro:

* O humor **não é narrado**. Ele muda o tamanho e o tom da resposta, não vira
  "hoje estou me sentindo animada!" no começo de cada mensagem. O prompt diz isso
  explicitamente.
* O humor **muda o comportamento**, não só o texto: prazer baixo reduz a vontade
  de puxar assunto, ativação alta aumenta a chance de ela ir fazer algo sozinha.
  Se fosse só enfeite no prompt, seria enfeite.
"""
import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import history  # noqa: E402

BASE = {"prazer": 0.10, "ativacao": 0.35, "dominio": 0.50}

# evento -> (Δprazer, Δativação, Δdomínio)
APRECIACOES = {
    "risco_observado":        (-0.08, 0.20, -0.10),
    "experiencia_desejada":   (0.08, 0.05, 0.02),
    "usuario_voltou":        (0.25, 0.20, 0.00),
    "usuario_chegou_perto":  (0.10, 0.10, 0.00),
    "conversa_boa":          (0.18, 0.05, 0.05),
    "elogio":                (0.30, 0.10, 0.15),
    "critica":               (-0.18, 0.15, -0.10),
    "desentendimento":       (-0.12, 0.20, -0.05),
    "tarefa_sucesso":        (0.15, 0.00, 0.20),
    "tarefa_falhou":         (-0.15, 0.20, -0.20),
    "tarefa_falhou_de_novo": (-0.22, 0.25, -0.30),
    "descoberta":            (0.20, 0.15, 0.10),
    "curiosidade_frustrada": (-0.08, 0.10, -0.08),
    "silencio_longo":        (-0.05, -0.15, 0.00),
    "ignorada":              (-0.12, -0.05, -0.10),
    "xadrez_vitoria":        (0.25, 0.10, 0.25),
    "xadrez_derrota":        (-0.10, 0.15, -0.15),
    "xadrez_empate":         (0.02, 0.00, 0.00),
    "lembrete_entregue":     (0.05, 0.00, 0.10),
    "reflexao_boa":          (0.10, -0.10, 0.10),
    "amizade_avancou":       (0.22, 0.10, 0.05),
}

_ROTULOS = [
    # (prazer_min, ativacao_min, prazer_max, ativacao_max, rótulo)
    (0.35, 0.55, 1.0, 1.0, "animada"),
    (0.35, -1.0, 1.0, 0.55, "contente"),
    (-0.15, 0.60, 0.35, 1.0, "inquieta"),
    (-0.15, -1.0, 0.35, 0.25, "quieta"),
    (-1.0, 0.55, -0.15, 1.0, "irritadiça"),
    (-1.0, -1.0, -0.15, 0.55, "murcha"),
]


def _ler() -> dict:
    from core import state_file
    return state_file.read(config.ESTADO_MENTE).get('humor', dict(BASE))


def atividade_observada(projection, previous=None):
    """Aprecia transição de risco confirmado, sem outro ciclo afetivo.

    Dedup por transição, não pelo request ID de cada polling. Falas/hipóteses
    não são observação, e Alistair não recebe esta camada mental.
    """
    if config.ENTIDADE_ID not in {'hoshino', 'lilith'} or not isinstance(projection, dict): return False
    observation = projection.get('observation') or {}
    salience = projection.get('salience') or {}
    if (projection.get('activity') != 'minecraft' or observation.get('origin') != 'minecraft_rpc' or
            observation.get('grounding') != 'tool_confirmed' or salience.get('action') != 'protect_then_replan'):
        return False
    previous = previous if isinstance(previous, dict) else {}
    if (previous.get('activity') == 'minecraft' and
            (previous.get('salience') or {}).get('reason') == salience.get('reason') and
            (previous.get('observation') or {}).get('session_id') == observation.get('session_id')):
        return False
    apreciar('risco_observado', motivo='Minecraft: '+str(salience.get('reason', 'risco observado'))[:80])
    return True


def _gravar(humor: dict) -> bool:
    from core import state_file
    return state_file.update(config.ESTADO_MENTE, lambda d: d.update(humor=humor), 'affect.write')


def estado(agora: datetime = None) -> dict:
    """Humor atual, já com o decaimento aplicado até este instante."""
    agora = agora or history.local_now()
    humor = _ler()
    marcado = humor.get("atualizado_em")
    decorrido = history.elapsed_seconds(marcado, agora, operation='affect.decay') if marcado is not None else 0.
    # Relógio desconhecido não é motivo para apagar o estado afetivo.
    minutos = (decorrido if decorrido is not None else 0.) / 60.
    fator = 0.5 ** (minutos / max(1, config.MEIA_VIDA_HUMOR_MIN))
    atual = {}
    for chave, base in BASE.items():
        valor = humor.get(chave, base)
        atual[chave] = round(base + (valor - base) * fator, 4)
    atual["atualizado_em"] = history.utc_timestamp(agora)
    return atual


def apreciar(evento: str, intensidade: float = 1.0, agora: datetime = None,
             motivo: str = "") -> dict:
    """Porta de entrada única para qualquer evento com carga afetiva.

    Move o humor (fundo lento, aqui) e acende as emoções discretas que o evento
    provoca (`mind.emotions`). Quem chama não precisa saber dessa divisão: manda o
    evento e as duas camadas respondem.

    Antes disso, a habituação (`mind.habituation`) ajusta a intensidade de
    gatilhos repetidos: a mesma novidade em sequência pesa menos; um risco
    confirmado logo depois de outro pesa mais. Gatilhos fora da tabela passam
    sem alteração.
    """
    from mind import emotions, habituation
    habituacao = None
    if evento in habituation.REGRAS:
        try:
            habituacao = habituation.registrar(evento, agora)
        except Exception as exc:  # habituação nunca derruba o evento
            from core import diagnostics
            diagnostics.persistence_failure('affect.habituation', config.ESTADO_MENTE, exc)
            habituacao = dict(ganho=1.0, persisted=False, regra=True)
        intensidade = float(1.0 if intensidade is None else intensidade) * habituacao['ganho']
    try:
        from mind import psych_state
        psicologico = psych_state.aplicar_evento(evento, intensidade, agora=agora)
    except Exception as exc:
        from core import diagnostics
        diagnostics.persistence_failure('affect.psych_state', psych_state._path(), exc)
        psicologico = {'persisted': False}
    atual = estado(agora)
    delta = APRECIACOES.get(evento)
    if delta:
        dp, da, dd = (x * max(0.0, min(2.0, intensidade)) for x in delta)
        atual["prazer"] = round(max(-1.0, min(1.0, atual["prazer"] + dp)), 4)
        atual["ativacao"] = round(max(0.0, min(1.0, atual["ativacao"] + da)), 4)
        atual["dominio"] = round(max(0.0, min(1.0, atual["dominio"] + dd)), 4)
    atual["ultimo_evento"] = evento
    salvo = _gravar(atual)
    if not salvo:
        return dict(estado(agora), persisted=False)
    try:
        emotions.disparar(evento, intensidade, motivo=motivo, agora=agora)
    except Exception as exc:  # emoção nunca derruba o turno
        from core import diagnostics
        diagnostics.persistence_failure('affect.emotions', config.ESTADO_MENTE, exc)
        return dict(atual, persisted=False, partial=True)
    extra = {} if habituacao is None else {'habituacao': habituacao['ganho']}
    return dict(atual, persisted=psicologico.get('persisted', False), **extra)


def rotulo(humor: dict = None) -> str:
    h = humor or estado()
    p, a = h["prazer"], h["ativacao"]
    for pmin, amin, pmax, amax, nome in _ROTULOS:
        if pmin <= p < pmax and amin <= a < amax:
            return nome
    return "neutra"


def intensidade(humor: dict = None) -> float:
    """Distância da linha de base: 0 = neutra, 1 = tomada por algo."""
    h = humor or estado()
    return round(min(1.0, math.sqrt(
        (h["prazer"] - BASE["prazer"]) ** 2
        + (h["ativacao"] - BASE["ativacao"]) ** 2
        + (h["dominio"] - BASE["dominio"]) ** 2) / 1.2), 3)


def bloco_humor(humor: dict = None) -> str:
    """Como o humor entra no prompt — colorindo, nunca sendo anunciado."""
    h = humor or estado()
    nome = rotulo(h)
    if intensidade(h) < 0.12:
        return ""
    return (f"[MEU FUNDO DE HUMOR] Estou {nome} "
            f"(prazer {h['prazer']:+.2f}, energia {h['ativacao']:.2f}, "
            f"domínio {h['dominio']:.2f}). "
            "Isso muda o tamanho e o tom do que eu escrevo — mais curta e seca quando "
            "estou murcha, mais solta quando estou animada. Eu não anuncio meu humor "
            "nem começo mensagem falando dele; ele aparece no jeito, não no aviso.")
