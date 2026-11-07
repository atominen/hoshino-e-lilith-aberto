"""
O núcleo — o que ela faz neste instante, e por quê.

Duas ideias velhas sustentam este arquivo.

**Espaço de trabalho global** (Baars). Num dado momento existem vários conteúdos
disputando atenção: um lembrete que venceu, um programa que ela nunca viu, uma
pergunta que ficou sem resposta ontem, um objetivo travado, tédio. Eles competem
por saliência e só um vence. O que vence é o que ocupa o pensamento — o resto
continua existindo, só não é o assunto do momento.

**BDI** (Bratman; Rao & Georgeff). Crença, desejo, intenção. As crenças vêm da
situação e da memória; os desejos são os impulsos; a intenção é o compromisso que
sai daqui. A parte que costuma faltar em agente de LLM é o compromisso: sem ele o
"agente" é uma sequência de reações independentes, cada uma recomeçando do zero.

A regra que organiza tudo: **decidir é de graça, falar é caro.** A deliberação
inteira roda em Python a cada tick, sem tocar no modelo. O modelo só é chamado
depois que já existe uma intenção concreta — e, quando a intenção é falar, só
depois de existir uma âncora: uma coisa específica sobre a qual falar.

É essa ordem que conserta o "fala do nada". A versão anterior gerava texto e
depois filtrava o que era enchimento. Aqui o enchimento não chega a ser gerado,
porque sem âncora a decisão de falar não acontece.
"""
import os
import re
import math
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import bd, situation, history  # noqa: E402
from mind import drives  # noqa: E402

# Intenções que produzem fala (interrompem a pessoa) e as que não produzem.
FALANTES = {"avisar", "falar", "conhecer", "despertar"}
INTERNAS = {"investigar", "refletir", "jogar", "retomar_objetivo", "observar_tela", "explorar"}


# --------------------------------------------------------------- saliência
def candidatos(situacao: dict, pressoes: dict) -> list:
    """Tudo que está disputando a atenção dela agora, com um peso cada."""
    itens = []
    s = situacao or {}

    if s.get("lembretes_vencidos"):
        itens.append({"fonte": "lembrete", "saliencia": 1.0,
                      "texto": f"{s['lembretes_vencidos']} lembrete(s) venceram"})
    if s.get("prazos_proximos"):
        itens.append({"fonte": "prazo", "saliencia": 0.8,
                      "texto": f"{s['prazos_proximos']} prazo(s) chegando"})

    for evento in s.get("eventos", []):
        peso = {"app_novo": 0.7, "voltou": 0.6, "musica": 0.35,
                "app_trocado": 0.2, "sumiu": 0.15}.get(evento["tipo"], 0.2)
        itens.append({"fonte": evento["tipo"], "saliencia": peso,
                      "texto": evento["texto"], "evento": evento})

    for nome, dados in (pressoes or {}).items():
        if dados["pressao"] >= 0.5:
            itens.append({"fonte": f"impulso:{nome}", "saliencia": dados["pressao"] * 0.9,
                          "texto": f"impulso de {nome} em {dados['pressao']:.0%}"})

    return sorted(itens, key=lambda i: -i["saliencia"])


def foco(situacao: dict, pressoes: dict):
    """O conteúdo que venceu a disputa. None quando está tudo calmo."""
    lista = candidatos(situacao, pressoes)
    return lista[0] if lista else None


# ----------------------------------------------------------------- âncoras
def buscar_ancora(situacao: dict) -> dict:
    """Procura um motivo social concreto para interromper a pessoa.

    Novidade de aplicativo, reflexão interna e tempo ocioso NÃO são motivos para
    falar com alguém. Eles podem gerar uma ação interna (investigar/refletir), mas
    não devem virar um texto endereçado a ninguém. Para fala espontânea, a única
    fonte aqui é uma curiosidade explicitamente relacionada à pessoa.
    """
    from mind import scribe

    abertas = scribe.curiosidades_abertas(8)
    for cur in abertas:
        origem = str(cur.get("origem") or "").casefold()
        sobre = str(cur.get("sobre") or "").casefold()
        if origem == "pessoa" or "pessoa" in origem or "pessoa" in sobre:
            return {"tipo": "curiosidade", "id": cur["id"], "texto": cur["pergunta"],
                    "motivo": "tenho uma pergunta real sobre a pessoa e quero saber a resposta"}
    return {}


# ------------------------------------------------------------- limitadores
def _pode_falar_agora(agora: datetime, ultima_fala, urgente: bool, *,
                       monotonic_now=None, last_monotonic=None) -> tuple:
    agora = history.local_datetime(agora)
    inicio, fim = config.HORARIO_SILENCIO
    if inicio != fim and not urgente:
        dentro = (inicio <= agora.hour < fim) if inicio < fim \
            else (agora.hour >= inicio or agora.hour < fim)
        if dentro:
            return False, f"horário de silêncio ({inicio}h–{fim}h)"
    if (ultima_fala is not None or last_monotonic is not None) and not urgente:
        decorrido = history.runtime_elapsed(ultima_fala, agora, start_monotonic=last_monotonic,
                                           end_monotonic=monotonic_now, operation='kernel.speech_cooldown')
        if decorrido is None:
            return False, 'intervalo desde a última fala não confirmado'
        if decorrido < config.INTERVALO_MIN_FALA_AUTONOMA:
            faltam = int((config.INTERVALO_MIN_FALA_AUTONOMA - decorrido) / 60)
            return False, f"falei há pouco (faltam ~{faltam} min)"
    return True, ""


def _pode_agir_agora(agora: datetime, ultima_acao, acoes_na_hora: int, *,
                      monotonic_now=None, last_monotonic=None) -> tuple:
    if acoes_na_hora >= config.ACOES_INTERNAS_POR_HORA:
        return False, "cota de ações internas da hora esgotada"
    if ultima_acao is not None or last_monotonic is not None:
        decorrido = history.runtime_elapsed(ultima_acao, agora, start_monotonic=last_monotonic,
                                           end_monotonic=monotonic_now, operation='kernel.action_cooldown')
        if decorrido is None:
            return False, 'intervalo desde a última ação não confirmado'
        if decorrido < config.INTERVALO_MIN_ACAO_INTERNA:
            return False, f"agi há {int(decorrido)}s"
    return True, ""


def _pode_olhar_tela(agora: datetime, ultima_olhada, *, monotonic_now=None, last_monotonic=None) -> bool:
    """Olhar a tela é a única ação interna que custa uma passada pelo modelo de
    visão, então tem uma janela própria (INTERVALO_MIN_OLHAR_TELA, 15 min) além
    da cota geral de ações internas — senão, numa hora de ócio ela passaria a
    cota inteira tirando print."""
    if ultima_olhada is None and last_monotonic is None:
        return True
    decorrido = history.runtime_elapsed(ultima_olhada, agora, start_monotonic=last_monotonic,
                                       end_monotonic=monotonic_now, operation='kernel.screen_cooldown')
    return decorrido is not None and decorrido >= config.INTERVALO_MIN_OLHAR_TELA


# --------------------------------------------------------------- decisão

def _audio_dirigido(situacao: dict) -> dict | None:
    """Escolhe áudio dirigido à entidade que realmente está ouvindo."""
    eventos = list((situacao or {}).get("audio_eventos") or [])
    for ev in reversed(eventos[-12:]):
        origem = str(ev.get("origem", "")).lower()
        texto = str(ev.get("texto", "")).strip()
        canal = str(ev.get("canal", "")).lower()
        if not texto or canal in {"jogo", "sistema", "musica", "música"}:
            continue
        nome = re.escape(config.ENTIDADE_NOME)
        dirigido = bool(re.search(r"\b("+nome+r"|você|voce|escuta|tá aí|ta ai|está aí|esta ai)\b", texto, re.I))
        if dirigido or ev.get("dirigido") is True:
            return ev
    return None


def _recursos_saturados(situacao: dict) -> bool:
    carga = (situacao or {}).get("carga") or {}
    mem = float(carga.get("memoria_usada_pct") or 0)
    load1 = float(carga.get("load1") or 0)
    disco = float(carga.get("disco_usado_pct") or 0)
    try:
        limite_load = max(4.0, (os.cpu_count() or 4) * 2.0)
    except Exception:
        limite_load = 8.0
    return mem >= 94.0 or load1 >= limite_load * 4.0 or disco >= 98.0


def deliberar(situacao: dict, pressoes: dict, estado: dict = None) -> dict:
    """Decide a intenção deste tick. Python puro — nenhuma chamada ao modelo.

    `estado` traz o que só o laço principal sabe: última fala espontânea, última
    ação interna, cota da hora, modo silencioso, se há partida em andamento.
    """
    estado = estado or {}
    agora = (situacao or {}).get("agora") or history.local_now()
    speech_clock = dict(monotonic_now=estado.get('monotonic_now'), last_monotonic=estado.get('ultima_fala_monotonic'))
    action_clock = dict(monotonic_now=estado.get('monotonic_now'), last_monotonic=estado.get('ultima_acao_monotonic'))
    silencioso = estado.get("modo_silencioso", False)
    vencido = foco(situacao, pressoes)

    def decisao(tipo, motivo, **extra):
        return {"tipo": tipo, "motivo": motivo, "foco": vencido,
                "hora": agora.isoformat(timespec="seconds"), **extra}

    # 1. Compromisso concreto vence tudo: lembrete é promessa feita à pessoa.
    if situacao.get("lembretes_vencidos") or situacao.get("gatilhos_diretos"):
        pode, porque = _pode_falar_agora(agora, estado.get("ultima_fala"), urgente=True, **speech_clock)
        if silencioso:
            return decisao("nada", "modo silencioso: lembretes ficam engavetados")
        if pode:
            return decisao("avisar", "lembrete vencido",
                           gatilhos=situacao.get("gatilhos_diretos", []))
        return decisao("nada", porque)

    if situacao.get("jobs_terminados"):
        if not silencioso:
            pode, porque = _pode_falar_agora(agora, estado.get("ultima_fala"), urgente=False, **speech_clock)
            if pode:
                return decisao("avisar", "um trabalho que eu iniciei terminou",
                               gatilhos=situacao.get("jobs_terminados", []))

    # Áudio dirigido é um evento externo, não um impulso. Tem prioridade para não parecer surda.
    audio = _audio_dirigido(situacao)
    if audio and not silencioso:
        return decisao("reagir_audio", "ouvi uma fala dirigida a mim",
                       gatilhos=[{"tipo": "audio", "texto": audio.get("texto", ""),
                                  "detalhe": f"canal={audio.get('canal','')} origem={audio.get('origem','')}"}],
                       alvo={"tipo": "audio", "texto": audio.get("texto", ""), "canal": audio.get("canal", ""), "origem": audio.get("origem", "")})

    # Carga extrema bloqueia ações internas pesadas; não bloqueia resposta normal do usuário.
    if _recursos_saturados(situacao):
        return decisao("nada", "recursos do sistema saturados; adio ações internas pesadas")

    if estado.get('ocupada'):
        return decisao('nada', 'conversa ou trabalho em andamento tem prioridade')

    # 1.2 Despertar (pedido humano 06/11): acordar sem ninguém e sem lembrança não
    #     pode virar ficar boiando. Uma fala, logo após acordar, sem exigir âncora nem
    #     presença confirmada; o laço principal oferece isto uma vez por despertar.
    #     Modo silencioso e horário de silêncio continuam valendo.
    if estado.get('despertar_pendente') and not silencioso:
        pode, _ = _pode_falar_agora(agora, estado.get("ultima_fala"), urgente=False, **speech_clock)
        if pode:
            return decisao('despertar', 'acabei de acordar: me localizar e avisar no chat',
                           fatos=dict(estado.get('despertar_fatos') or {}))

    # 1.5 Diretiva sustentada: "fica jogando xadrez até eu voltar" não é impulso
    #     de ócio, é compromisso que ela registrou (add_goal com sustentar=1).
    #     Furo a fila de propósito: ócio satisfaz e entra em refratário assim
    #     que ela DECIDE jogar, não quando a partida termina — então sem isto,
    #     uma diretiva contínua vira "jogou uma vez e parou" (era exatamente o
    #     bug: pressão de ócio já descarregada, próxima partida só depois de
    #     30 min de refratário, se é que ócio volta a ser a pressão dominante).
    from tools import agenda
    diretiva = agenda.diretiva_ativa(situacao.get("usuario_presente", True))
    if diretiva:
        if diretiva["acao"] == "jogar":
            if not estado.get("partida_em_andamento"):
                return decisao("jogar", f"diretiva sustentada: {diretiva['description']}",
                               treino=True)
        else:
            pode_agir, _ = _pode_agir_agora(
                agora, estado.get("ultima_acao_interna"), estado.get("acoes_na_hora", 0), **action_clock)
            if pode_agir:
                return decisao(diretiva["acao"], f"diretiva sustentada: {diretiva['description']}",
                               alvo={"tipo": "diretiva", "goal_id": diretiva["id"],
                                     "texto": diretiva["description"]})

    if estado.get('atividade_pendente') and config.ENTIDADE_ID in {'hoshino','lilith'}:
        pode, _ = _pode_agir_agora(agora, estado.get('ultima_acao_interna'),
                                  estado.get('acoes_na_hora',0), **action_clock)
        if pode and not estado.get('deliberacao_bloqueada') and drives.pode_deliberar(agora):
            return decisao('explorar','retomar minha atividade registrada, sem nova mensagem humana')

    def privado_ou_nada(motivo):
        # A ausência de lembranças não pode impedir descobrir interesses. Isto
        # abre uma escolha interna, não obriga ação nem autoriza falar. Usa
        # observação contínua real, nunca tempo de ausência humana presumida.
        idle = situacao.get('segundos_sem_interacao_observados', 0)
        pode, _ = _pode_agir_agora(agora, estado.get('ultima_acao_interna'),
                                  estado.get('acoes_na_hora', 0), **action_clock)
        if (config.ENTIDADE_ID in {'hoshino', 'lilith'}
                and type(idle) in (int, float) and math.isfinite(idle) and idle >= config.INICIATIVA_INATIVIDADE_SEGUNDOS
                and not estado.get('deliberacao_bloqueada')
                and not estado.get('partida_em_andamento') and pode and drives.pode_deliberar(agora)):
            return decisao('explorar', 'tempo livre realmente observado; decidir uma atividade própria ou descansar')
        return decisao('nada', motivo)

    # 2. Uma vontade social inviável não bloqueia toda atividade interna.
    dominante = drives.dominante(pressoes)
    if not dominante:
        return privado_ou_nada('nenhuma pressão acima do limiar')

    nome = dominante["nome"]
    pode_agir, porque_nao = _pode_agir_agora(
        agora, estado.get("ultima_acao_interna"), estado.get("acoes_na_hora", 0), **action_clock)

    # 2a. Falar com a pessoa é o caminho mais caro: exige pressão alta, presença,
    #     janela de tempo e — principalmente — assunto.
    if nome == "conexao":
        if silencioso:
            return privado_ou_nada('modo silencioso')
        if dominante["pressao"] < config.LIMIAR_IMPULSO_FALA:
            return privado_ou_nada(f"vontade de conversar em {dominante['pressao']:.0%}, "
                                  f"abaixo do limiar de {config.LIMIAR_IMPULSO_FALA:.0%}")
        if not situacao.get("usuario_presente"):
            return privado_ou_nada('presença humana não confirmada')
        pode, porque = _pode_falar_agora(agora, estado.get("ultima_fala"), urgente=False, **speech_clock)
        if not pode:
            return privado_ou_nada(porque)
        ancora = buscar_ancora(situacao)
        if not ancora:
            return privado_ou_nada('vontade de falar, mas nada concreto a dizer')
        tipo = "conhecer" if ancora.get("tipo") == "curiosidade" else "falar"
        return decisao(tipo, f"puxar assunto: {ancora['motivo']}", ancora=ancora)

    # 2b. As demais são internas: não interrompem ninguém.
    if not pode_agir:
        return decisao("nada", porque_nao)

    if nome == "coerencia":
        return decisao("refletir", "episódios acumulados sem conclusão")

    if nome == "curiosidade":
        from mind import scribe
        abertas = scribe.curiosidades_abertas(1)
        if abertas:
            return decisao("investigar", "tenho pergunta em aberto",
                           alvo={"tipo": "curiosidade", "id": abertas[0]["id"],
                                 "texto": abertas[0]["pergunta"]})
        novidade = next((e for e in situacao.get("eventos", [])
                         if e["tipo"] == "app_novo"), None)
        if novidade:
            return decisao("investigar", "programa que eu não conheço",
                           alvo={"tipo": "novidade", "id": "",
                                 "texto": novidade["rotulo"]})
        # Curiosa e sem alvo: olhar a tela é o jeito mais barato de arrumar um.
        # Esta era a ponta solta do projeto — `observar_tela` já constava em
        # INTERNAS e INTERVALO_MIN_OLHAR_TELA já existia no config, mas nada
        # emitia a intenção, então a pressão de curiosidade sem pergunta em
        # aberto simplesmente evaporava em "sem alvo definido" a cada tick.
        # Espaçado pelo próprio intervalo (15 min) porque é caro: capturar a
        # tela e passar pelo modelo de visão não é de graça como deliberar.
        if _pode_olhar_tela(agora, estado.get("ultima_olhada"),
                            monotonic_now=estado.get('monotonic_now'), last_monotonic=estado.get('ultima_olhada_monotonic')):
            if situacao.get("usuario_presente"):
                return decisao("observar_tela",
                               "curiosa, sem pergunta em aberto: vou ver o que ela está fazendo")
        return privado_ou_nada('curiosidade sem alvo definido')

    if nome == "competencia":
        from mind import strategies
        travados = strategies.objetivos_travados()
        if travados:
            objetivo = travados[0]
            proxima = strategies.proxima_abordagem(objetivo["id"])
            if proxima:
                return decisao("retomar_objetivo",
                               f"objetivo travado há {objetivo['falhas']} tentativa(s)",
                               alvo={"goal_id": objetivo["id"],
                                     "descricao": objetivo["description"],
                                     "abordagem": proxima})
        novo = strategies.proximo_objetivo_novo()
        if novo:
            proxima = strategies.proxima_abordagem(novo["id"])
            return decisao("retomar_objetivo",
                           f"objetivo na fila, prioridade {novo['priority']}, ainda não comecei",
                           alvo={"goal_id": novo["id"], "descricao": novo["description"],
                                 "abordagem": proxima})
        if estado.get("xadrez_disponivel", True):
            return decisao("jogar", "treinar para melhorar de verdade", treino=True)
        return decisao("nada", "sem objetivo travado e sem treino possível")

    if nome == "ocio":
        if (config.ENTIDADE_ID in {'hoshino','lilith'} and not estado.get('deliberacao_bloqueada')
                and not estado.get('partida_em_andamento') and drives.pode_deliberar(agora)):
            return decisao('explorar', 'ócio: escolher meu próximo passo, sem passatempo imposto')
        return decisao('nada', 'deliberação interna em intervalo ou atividade em andamento')

    if nome == "cuidado":
        return decisao("nada", "cuidado sem lembrete concreto vencido")

    return decisao("nada", f"impulso {nome} sem ação mapeada")


# ----------------------------------------------------------------- registro
def registrar_ciclo(intencao: dict, situacao: dict, pressoes: dict) -> None:
    """Grava no índice de eventos — é o rastro para entender o comportamento dela."""
    if intencao.get("tipo") == "nada":
        return
    bd.executar(
        "INSERT OR REPLACE INTO events_index (event_id, timestamp, kind, task_id, detalhe) "
        "VALUES (?,?,?,?,?)",
        (bd.novo_id("ev", 10), bd.agora(), f"intencao:{intencao['tipo']}", "",
         f"{intencao.get('motivo', '')} | {drives.resumo(pressoes)} | "
         f"{situation.descrever(situacao)}"[:500]))


def explicar(intencao: dict, pressoes: dict) -> str:
    """Uma linha para o painel: o que ela decidiu e por quê."""
    tipo = intencao.get("tipo", "nada")
    if tipo == "nada":
        return f"quieta — {intencao.get('motivo', '')}"
    return f"{tipo} — {intencao.get('motivo', '')} [{drives.resumo(pressoes)}]"
