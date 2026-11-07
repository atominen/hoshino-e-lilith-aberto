"""
Impulsos — o motor da iniciativa.

A versão anterior tinha um único "gatilho" de iniciativa: lembrete vencido. Fora
disso ela era reativa, e quando tentava não ser, preenchia o silêncio com
comentário sobre a janela aberta. O problema não era falta de vontade: era falta
de *motivo*. Um agente que só reage a input é um chatbot com timer.

Aqui existem seis pressões, todas calculadas em Python a partir do estado do
mundo, sem passar pelo modelo. Cada uma cresce por um motivo concreto e é
descarregada por uma ação específica. Nada de "às vezes ela fala": ela fala
quando uma pressão passa do limiar, e a pressão vem de algo que aconteceu.

  curiosidade  cresce  com pergunta em aberto e coisa nova no ambiente
               descarrega  pesquisando, observando, perguntando
  conexão      cresce  com tempo sem trocar palavra (satura, não explode)
               descarrega  conversando
  competência  cresce  com objetivo que falhou e habilidade parada
               descarrega  tentando de novo por outro caminho, treinando
  coerência    cresce  com episódio vivido e não refletido
               descarrega  refletindo, consolidando memória
  cuidado      cresce  com lembrete vencido e sinal de que a pessoa precisa de algo
               descarrega  avisando
  ócio         cresce  quando não acontece nada e ninguém está por perto
               descarrega  jogando, explorando

Período refratário: descarregou, aquela pressão cai e leva tempo para voltar.
É o que impede o comportamento de "uma vez por tick para sempre".
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import history  # noqa: E402

# nome -> (segundos de refratário depois de satisfeito, ação que descarrega)
IMPULSOS = {
    "curiosidade": (900, "investigar"),
    "conexao":     (config.INTERVALO_INICIATIVA_SOCIAL, "conversar"),
    "competencia": (1200, "treinar"),
    "coerencia":   (config.REFLEXAO_INTERVALO_MIN * 60, "refletir"),
    "cuidado":     (300, "avisar"),
    "ocio":        (config.OCIO_REFRATARIO_SEGUNDOS, "jogar"),
}


def _estado() -> dict:
    from core import state_file
    return state_file.read(config.ESTADO_MENTE)


def _gravar(dados: dict) -> bool:
    from core import state_file
    return state_file.update(config.ESTADO_MENTE, lambda d: d.update(dados), 'drives.write')


def satisfazer(impulso: str, agora: datetime = None) -> bool:
    """Marca que a pressão foi descarregada agora."""
    from core import state_file
    def mutate(dados):
        dados.setdefault('satisfacoes', {})[impulso] = history.utc_timestamp(agora)
    return state_file.update(config.ESTADO_MENTE, mutate, 'drives.satisfy')


def _refratario(impulso: str, agora: datetime) -> float:
    """1.0 = livre, 0.0 = acabou de ser satisfeito."""
    marcado = _estado().get("satisfacoes", {}).get(impulso)
    if marcado is None:
        return 1.0
    decorrido = history.elapsed_seconds(marcado, agora, operation='drives.refractory')
    if decorrido is None:
        # Timestamp corrompido/futuro não libera iniciativa como se não tivesse
        # havido atividade. O diagnóstico permite corrigir a origem, sem replay.
        return 0.0
    janela = IMPULSOS.get(impulso, (600, ""))[0]
    return max(0.0, min(1.0, decorrido / janela))


def _satura(valor: float, escala: float) -> float:
    """Crescimento que satura: rápido no começo, assintótico depois."""
    return 1.0 - (1.0 / (1.0 + max(0.0, valor) / max(1e-6, escala)))


def pode_deliberar(agora: datetime = None) -> bool:
    """Cadência de oportunidade interna, inclusive após erro/reinício.

    Não é emoção nem aprovação. Falha física/incerteza bloqueia novas partidas
    até reconciliação; silêncio escolhido apenas respeita o mesmo intervalo.
    """
    state = _estado()
    if state.get('iniciativa_bloqueada') or state.get('initiative_inflight'):
        return False
    last = state.get('satisfacoes', {}).get('deliberacao_interna')
    if last is None:
        return True
    elapsed = history.elapsed_seconds(last, agora, operation='initiative.cooldown')
    from core import initiative
    return elapsed is not None and elapsed >= initiative.interval()


def avaliar(situacao: dict, agora: datetime = None) -> dict:
    """Pressão de cada impulso agora. `situacao` vem do core.situation.

    Não chama o modelo, não toca no disco além de ler o refratário: pode rodar a
    cada tick sem custo.
    """
    agora = agora or history.local_now()
    s = situacao or {}
    humor = s.get("humor") or {}
    prazer = humor.get("prazer", 0.1)
    energia = humor.get("ativacao", 0.35)
    presente = s.get("usuario_presente", True)
    ocioso = s.get("segundos_ociosos", 0)
    # Ócio interno pode acumular desde o primeiro despertar sem fabricar uma
    # interação humana. Conexão continua usando somente a interação conhecida;
    # presença desconhecida mantém o mesmo fator conservador de antes.
    ocio_observado = s.get("segundos_sem_interacao_observados", ocioso)

    bruto = {
        # Pergunta em aberto pesa mais que novidade no ambiente: novidade some,
        # pergunta sem resposta incomoda.
        "curiosidade": (0.55 * _satura(s.get("curiosidades_abertas", 0), 2.5)
                        + 0.45 * _satura(s.get("novidades", 0), 2.0)),
        # Vontade de conversar é duas coisas: tempo sem trocar palavra e ter o que
        # perguntar. Só o tempo dava uma curva que saturava perto de 0.67 e nunca
        # passava do limiar de fala — ou seja, ela nunca puxaria assunto. Quem tem
        # pergunta guardada puxa antes; quem não tem, demora mais.
        "conexao": (0.75 * _satura(max(0, ocioso - config.OCIOSO_PARA_INICIATIVA), 900)
                    + 0.25 * _satura(s.get("curiosidades_sobre_pessoa", 0), 1.5))
                   * (1.0 if presente else 0.12),
        "competencia": (0.6 * _satura(s.get("objetivos_travados", 0), 1.5)
                        + 0.4 * _satura(s.get("dias_sem_treinar", 0), 2.0)),
        # Coerência não é uma barra que pode crescer indefinidamente. Só há
        # pressão para refletir quando as duas pré-condições reais estão
        # satisfeitas: material acumulado E intervalo mínimo desde a última
        # reflexão. Isso evita transformar qualquer lote de episódios em uma
        # chamada de modelo num tick que deveria ser calmo.
        "coerencia": 0.0,
        "cuidado": min(1.0, 0.75 * s.get("lembretes_vencidos", 0)
                       + 0.4 * _satura(s.get("prazos_proximos", 0), 1.5)),
        "ocio": (_satura(max(0, ocio_observado - 600), 2400) * (0.9 if presente is False else config.OCIO_FATOR_PRESENTE)),
    }
    try:
        from mind import reflection
        bruto["coerencia"] = 1.0 if reflection.precisa_refletir() else 0.0
    except Exception:  # noqa: BLE001
        bruto["coerencia"] = 0.0

    # O humor inclina a balança: sem energia ela não vai atrás de nada, e murcha
    # ela não puxa assunto (o que é mais honesto do que fingir animação).
    modulador = {
        "curiosidade": 0.6 + 0.8 * energia,
        "conexao": 0.5 + 0.9 * max(0.0, (prazer + 1) / 2),
        "competencia": 0.7 + 0.6 * energia,
        "coerencia": 1.0,
        "cuidado": 1.0,                      # cuidado não depende de humor
        "ocio": 0.5 + 0.8 * energia,
    }

    # Emoção discreta puxa impulso: com raiva ela puxa menos assunto, com
    # curiosidade vai atrás das coisas. É aqui que sentimento vira comportamento.
    try:
        from mind import emotions
        emocional = emotions.influencia_nos_impulsos(agora)
    except Exception:  # noqa: BLE001
        emocional = {}
    try:
        from mind import psych_state
        psicologico = psych_state.influencia()
    except Exception:  # noqa: BLE001
        psicologico = {}

    saida = {}
    for nome in IMPULSOS:
        pressao = (bruto.get(nome, 0.0) * modulador.get(nome, 1.0)
                   * emocional.get(nome, 1.0) * psicologico.get(nome, 1.0)
                   * _refratario(nome, agora))
        saida[nome] = {
            "pressao": round(max(0.0, min(1.0, pressao)), 3),
            "acao": IMPULSOS[nome][1],
            "refratario": round(_refratario(nome, agora), 2),
            "emocao": round(emocional.get(nome, 1.0), 2),
        }
    return saida


def dominante(pressoes: dict, limiar: float = None):
    """O impulso mais forte acima do limiar, ou None se está tudo calmo."""
    limiar = config.LIMIAR_IMPULSO_ACAO if limiar is None else limiar
    if not pressoes:
        return None
    nome, dados = max(pressoes.items(), key=lambda kv: kv[1]["pressao"])
    if dados["pressao"] < limiar:
        return None
    return {"nome": nome, **dados}


def resumo(pressoes: dict) -> str:
    return "  ".join(f"{n}:{d['pressao']:.2f}" for n, d in sorted(
        pressoes.items(), key=lambda kv: -kv[1]["pressao"]))
