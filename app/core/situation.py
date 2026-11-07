"""
Situação — o que está acontecendo, e há quanto tempo.

"Estar consciente a todo momento" não é chamar o modelo a cada 15 segundos: isso é
o que a versão anterior fazia, e o resultado foi ela comentando a janela do Firefox
de dois em dois minutos. Consciência aqui é outra coisa — é manter um modelo do
presente atualizado o tempo todo, de graça, e só gastar pensamento quando esse
modelo muda de um jeito que importa.

O que este módulo mantém:

* **o que a pessoa está fazendo agora** e há quanto tempo (sessões de atividade,
  gravadas no banco — é memória de ambiente: "ontem você passou 3h no Rust");
* **novidade**: rótulo de aplicativo que ela nunca viu antes pesa diferente de um
  que aparece todo dia. É daqui que nasce curiosidade legítima, em vez de comentar
  o óbvio;
* **presença**: separa interação recente, inatividade de entrada e presença
  desconhecida. Silêncio e ociosidade X11 não comprovam ausência física;
* **pendências reais** do banco: lembrete vencido, prazo perto, curiosidade em
  aberto, objetivo travado, episódios sem reflexão.

Nada aqui chama o modelo. Tudo isto roda a cada tick sem custo.
"""
import json
import os
import re
import sys
import math
import time
import unicodedata
import uuid
import hashlib
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import bd, history, diagnostics  # noqa: E402

SEPARADORES = re.compile(r"\s+[—–\-|]\s+")
_DURACAO_MINIMA_SESSAO = 45   # abaixo disso é troca de janela, não atividade
_OBSERVATION_EPOCH = uuid.uuid4().hex  # uma execução, nunca reutilizar monotônico após restart
_APPS_VISTOS_MAX = 64   # apps vistos mesmo de relance, para não renascerem como novidade


def _sem_icones(texto: str) -> str:
    """Tira ícones de status das pontas do título ('◐ Projeto' -> 'Projeto').

    Terminais e agentes animam o título com spinners (◐◑◒◓, ✳, braille ⠋⠙…).
    Sem isso, cada quadro da animação virava um "programa nunca visto" e a
    curiosidade disparava a cada segundo (55 de 84 novidades da Lilith, 24-30/10).
    Só a categoria Unicode So (símbolo "outro") é removida: '+', '$' e afins ficam.
    """
    inicio, fim = 0, len(texto)
    while inicio < fim and (texto[inicio].isspace() or unicodedata.category(texto[inicio]) == 'So'):
        inicio += 1
    while fim > inicio and (texto[fim - 1].isspace() or unicodedata.category(texto[fim - 1]) == 'So'):
        fim -= 1
    return texto[inicio:fim]


def _partes(titulo: str) -> list:
    return [p for p in (_sem_icones(p.strip()) for p in SEPARADORES.split(titulo)) if p]


def rotulo_app(titulo: str) -> str:
    """'Documento X — LibreOffice Writer' -> 'LibreOffice Writer'.

    O título muda a cada aba; o aplicativo é o que dá para acompanhar ao longo do
    tempo. Em ambiente GNOME/Cinnamon o nome do app fica no último pedaço.
    """
    if not titulo:
        return ""
    partes = _partes(titulo)
    return (partes[-1] if partes else _sem_icones(titulo.strip()))[:60]


def detalhe_app(titulo: str) -> str:
    if not titulo:
        return ""
    partes = _partes(titulo)
    return (" — ".join(partes[:-1]) if len(partes) > 1 else "")[:120]


# ------------------------------------------------------------- persistência
def _memoria_curta() -> dict:
    from core import state_file
    return state_file.read(config.ESTADO_MENTE).get('situacao', {})


def _gravar_memoria_curta(dados: dict) -> bool:
    from core import state_file
    return state_file.update(config.ESTADO_MENTE, lambda d: d.update(situacao=dados), 'situation.write')


def ja_viu(rotulo: str) -> bool:
    if not rotulo:
        return True
    return bool(bd.um("SELECT id FROM activity_sessions WHERE rotulo = ? LIMIT 1", (rotulo,)))


def _fechar_sessao(sessao: dict, agora: datetime) -> None:
    # Só intervalos observados, não horas em que o processo estava dormindo ou
    # sensores indisponíveis. Legado sem duração confirmada não é retropreenchido.
    duracao = sessao.get('duracao_observada_seg', 0.)
    if not isinstance(duracao, (int, float)) or not math.isfinite(duracao):
        return
    duracao = int(duracao)
    if duracao < _DURACAO_MINIMA_SESSAO or history.elapsed_seconds(sessao.get('inicio'), agora) is None:
        return
    try:
        inicio = history.local_datetime(sessao['inicio']).replace(tzinfo=None).isoformat(timespec='seconds')
        fim = history.local_datetime(agora).replace(tzinfo=None).isoformat(timespec='seconds')
    except (ValueError, TypeError):
        return
    identifier = sessao.get('id') or 'act-'+hashlib.sha256(
        json.dumps([sessao.get('observation_epoch'), sessao.get('inicio'), sessao.get('rotulo')],
                   ensure_ascii=False).encode('utf-8')).hexdigest()[:24]
    bd.executar(
        "INSERT INTO activity_sessions (id, tipo, rotulo, inicio, fim, duracao_seg, detalhe) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
        (identifier, sessao.get("tipo", "app"), sessao.get("rotulo", ""),
         inicio, fim, duracao,
         (sessao.get("detalhe") or "")[:200]), strict=True)
    saved = bd.um('SELECT inicio,fim,duracao_seg FROM activity_sessions WHERE id=?', (identifier,), strict=True)
    if not saved:
        raise OSError('Fechamento da sessão de atividade não confirmado.')
    if (saved['inicio'], saved['fim'], saved['duracao_seg']) != (inicio, fim, duracao):
        # A primeira gravação continua sendo a evidência. Não sobrescrever nem
        # duplicar uma duração divergente após falha da atualização do JSON.
        diagnostics.emit('activity.close_conflict', level='WARN', entity=config.ENTIDADE_ID,
                         activity_id=identifier, overwritten=False, duplicated=False)


def tempo_em(rotulo: str, dias: int = 7) -> int:
    """Segundos acumulados num app nos últimos dias — memória de ambiente."""
    desde = (history.local_now() - timedelta(days=dias)).replace(tzinfo=None).isoformat(timespec="seconds")
    linha = bd.um("SELECT SUM(duracao_seg) AS total FROM activity_sessions "
                  "WHERE rotulo = ? AND inicio >= ?", (rotulo, desde))
    return int(linha["total"] or 0) if linha else 0


def resumo_do_dia(dia: str = None) -> str:
    dia = dia or history.local_now().date().isoformat()
    linhas = bd.consultar(
        "SELECT rotulo, SUM(duracao_seg) AS total FROM activity_sessions "
        "WHERE inicio LIKE ? GROUP BY rotulo ORDER BY total DESC LIMIT 6", (f"{dia}%",))
    if not linhas:
        return "Nada registrado nesse dia."
    return "\n".join(f"- {l['rotulo']}: {int(l['total'] // 60)} min" for l in linhas)


# ---------------------------------------------------------------- avaliação
def _observacao_entidade(anterior: dict, agora: datetime, mono: float) -> dict:
    """Tempo realmente observado nesta execução, independente de foco/presença.

    O primeiro despertar após uma limpeza não tem última interação humana.
    Isso não significa zero tempo livre para sempre, nem comprova ausência da
    pessoa. Restart, suspensão e lacunas não entram nesta duração.
    """
    previous = anterior.get('observacao_entidade') or {}
    last = previous.get('monotonic_last')
    duration = previous.get('duracao_observada_seg')
    gap = history.elapsed_seconds(previous.get('last_observed_at'), agora)
    maximum_gap = max(60., float(config.HEARTBEAT_SEGUNDOS) * 3.)
    continuous = (
        previous.get('observation_epoch') == _OBSERVATION_EPOCH
        and type(last) in (int, float) and math.isfinite(last)
        and type(duration) in (int, float) and math.isfinite(duration) and duration >= 0
        and 0 <= mono-last <= maximum_gap
        and gap is not None and gap <= maximum_gap
    )
    return {
        'observation_epoch': _OBSERVATION_EPOCH,
        'duracao_observada_seg': duration + mono-last if continuous else 0.,
        'monotonic_last': mono,
        'last_observed_at': history.utc_timestamp(agora),
    }


def atualizar(sensores: dict, ultima_interacao: datetime = None,
              agora: datetime = None, humor: dict = None, *, monotonic_now=None) -> dict:
    """Compara o agora com o instante anterior e devolve a situação completa."""
    # Mantém o contrato local ingênuo usado pela agenda/kernel legados. Cálculos
    # de duração e marcadores JSON abaixo possuem seus próprios contratos.
    agora = agora or history.local_now().replace(tzinfo=None)
    mono = time.monotonic() if monotonic_now is None else monotonic_now
    if isinstance(mono, bool) or not isinstance(mono, (int, float)) or not math.isfinite(mono) or mono < 0:
        raise ValueError('Relógio monotônico inválido.')
    sensores = sensores or {}
    anterior = _memoria_curta()
    eventos = []

    titulo = sensores.get("janela_ativa", "") or ""
    app = rotulo_app(titulo)
    detalhe = detalhe_app(titulo)
    midia = sensores.get("midia") or {}

    app_antes = anterior.get("app")
    # Sessões < 45 s não vão para activity_sessions, então `ja_viu` sozinho não
    # lembra de um app visto de relance; esta lista curta lembra.
    apps_vistos = [r for r in (anterior.get("apps_vistos") or []) if isinstance(r, str)][-_APPS_VISTOS_MAX:]
    sessao = anterior.get("sessao") or {}
    novidades = 0
    baseline = not sessao
    if sessao:
        last_mono = sessao.get('monotonic_last')
        observed = sessao.get('duracao_observada_seg')
        elapsed_wall = history.elapsed_seconds(sessao.get('last_observed_at'), agora)
        maximum_gap = max(60., float(config.HEARTBEAT_SEGUNDOS) * 3.)
        continuous = (sessao.get('observation_epoch') == _OBSERVATION_EPOCH
                      and isinstance(last_mono, (int, float)) and math.isfinite(last_mono)
                      and isinstance(observed, (int, float)) and math.isfinite(observed) and observed >= 0
                      and 0 <= mono-last_mono <= maximum_gap
                      and elapsed_wall is not None and elapsed_wall <= maximum_gap)
        if continuous:
            sessao['duracao_observada_seg'] += mono-last_mono
        else:
            # Fechar no último retrato conhecido, não no horário de acordar.
            cutoff = sessao.get('last_observed_at') or anterior.get('atualizado_em') or agora
            _fechar_sessao(sessao, cutoff)
            diagnostics.emit('activity.observation_rebased', entity=config.ENTIDADE_ID,
                             reason='restart_or_observation_gap', unobserved_interval_counted=False)
            sessao = {}
            baseline = True
    if not app and sessao:
        _fechar_sessao(sessao, agora)
        sessao = {}  # Não atribuir a uma janela o tempo em que o foco ficou desconhecido.

    if app and (app != app_antes or not sessao):
        if sessao:
            _fechar_sessao(sessao, agora)

        # O primeiro retrato do processo é somente uma linha de base. Se ele fosse
        # tratado como ``app_novo``, todo boot geraria curiosidade/pressão artificial
        # só porque o estado anterior ainda não existia. Trocas reais continuam
        # produzindo novidade normalmente.
        primeiro_retrato = baseline or anterior.get("app_observation_known") is False
        inedito = app not in apps_vistos and not ja_viu(app)
        if not primeiro_retrato:
            eventos.append({"tipo": "app_novo" if inedito else "app_trocado",
                            "rotulo": app, "detalhe": detalhe,
                            "texto": (f"apareceu um programa que eu nunca tinha visto: {app}"
                                      if inedito else f"agora está no {app}")})
            if inedito:
                novidades += 1
        sessao = {"tipo": "app", "rotulo": app, "detalhe": detalhe,
                  "inicio": history.utc_timestamp(agora), 'duracao_observada_seg': 0.,
                  'observation_epoch': _OBSERVATION_EPOCH, 'id': bd.novo_id('act', 8)}
    elif app and detalhe and detalhe != (sessao.get("detalhe") or ""):
        sessao["detalhe"] = detalhe    # mesma janela, conteúdo diferente

    faixa_antes = (anterior.get("midia") or {}).get("titulo")
    if not baseline and midia.get("titulo") and midia["titulo"] != faixa_antes:
        artista = midia.get("artista") or ""
        eventos.append({"tipo": "musica", "rotulo": midia["titulo"], "detalhe": artista,
                        "texto": f"começou a tocar {midia['titulo']}"
                                 + (f", de {artista}" if artista else "")})
        if artista and not bd.um("SELECT id FROM tastes WHERE lower(objeto) = lower(?)",
                                 (artista,)):
            novidades += 1

    decorrido = history.elapsed_seconds(ultima_interacao, agora, operation='situation.last_interaction') if ultima_interacao is not None else None
    ociosos = decorrido if decorrido is not None else 0.
    observacao = _observacao_entidade(anterior, agora, mono)
    # Relógio interno separado: não inventa uma conversa anterior para fazer o
    # ócio avançar. Uma interação inválida também não libera o fallback.
    sem_interacao_observados = (
        min(observacao['duracao_observada_seg'], decorrido) if decorrido is not None
        else observacao['duracao_observada_seg'] if ultima_interacao is None else 0.
    )
    idle_x11 = sensores.get("ociosidade_x11", -1)
    # Interpretação privada, não comprovação de presença física/identidade.
    recente = decorrido is not None and ociosos < config.AUSENTE_APOS
    if recente:
        presente, base_presenca = True, "interacao_recente_com_entidade"
    elif 0 <= idle_x11 < 300:
        presente, base_presenca = True, "entrada_recente_no_computador"
    elif idle_x11 >= 900:
        presente, base_presenca = None, "inatividade_de_entrada"
    else:
        presente, base_presenca = None, "evidencia_insuficiente"

    voltou_antes = anterior.get("presente")
    if presente is None and base_presenca == 'inatividade_de_entrada' and voltou_antes is True:
        eventos.append({"tipo": "inatividade_entrada", "rotulo": "", "detalhe": "",
                        "texto": "inatividade de entrada; presença da pessoa não confirmada"})

    minutos_na_atividade = int(sessao.get('duracao_observada_seg', 0.) // 60) if sessao else 0
    if sessao:
        sessao.update(last_observed_at=history.utc_timestamp(agora), monotonic_last=mono)

    app_familiar = (app in apps_vistos or ja_viu(app)) if app else True
    if app and app not in apps_vistos:
        apps_vistos = (apps_vistos + [app])[-_APPS_VISTOS_MAX:]
    _gravar_memoria_curta({"app": app or None, "app_observation_known": bool(app), "midia": midia, "sessao": sessao,
                           "apps_vistos": apps_vistos,
                           "observacao_entidade": observacao,
                           "presente": presente,
                           "atualizado_em": history.utc_timestamp(agora)})

    pendencias = _pendencias(agora)
    situacao = {
        "agora": agora,
        "app": app,
        "detalhe": detalhe,
        "minutos_na_atividade": minutos_na_atividade,
        "app_familiar": app_familiar,
        "midia": midia,
        "eventos": eventos,
        "novidades": novidades,
        "usuario_presente": presente,
        "interpretacao_presenca": {"valor": presente, "base": base_presenca,
                                   "presenca_fisica_confirmada": False},
        "world_state": sensores.get("world_state", {"source": "local_probe"}),
        "segundos_ociosos": int(ociosos),
        "segundos_sem_interacao_observados": int(sem_interacao_observados),
        "ultima_interacao_conhecida": decorrido is not None,
        "ociosidade_x11": idle_x11,
        # O núcleo decide se uma ação autônoma pesada cabe agora. Antes os
        # sensores coletavam carga, mas ela era descartada aqui e esse freio
        # nunca recebia dados reais da máquina.
        "carga": {chave: sensores[chave] for chave in
                   ("load1", "memoria_usada_pct", "disco_usado_pct", "disco_livre_gb")
                   if chave in sensores},
        "humor": humor or {},
        **pendencias,
    }
    return situacao


def _pendencias(agora: datetime) -> dict:
    """Tudo que o banco tem de pendente. Uma consulta por coisa, tudo barato."""
    from mind import reflection, strategies
    from tools import agenda

    try:
        vencidos = len(agenda.lembretes_vencidos(agora))
    except Exception:  # noqa: BLE001
        vencidos = 0
    proximo = history.timestamp_epoch(agora) + 6 * 3600
    prazos = bd.um("SELECT COUNT(*) AS n FROM goals WHERE status='active' AND due_at IS NOT NULL "
                   "AND project_epoch(due_at) <= ?", (proximo,))
    curiosas = bd.um("SELECT COUNT(*) AS n FROM curiosities WHERE status='aberta'")
    sobre_pessoa = bd.um("SELECT COUNT(*) AS n FROM curiosities WHERE status='aberta' "
                         "AND origem IN ('origem','pessoa')")
    ultimo_treino = bd.um("SELECT atualizado_em FROM skill_profile WHERE habilidade='xadrez'")
    dias_sem_treinar = 0.0
    if ultimo_treino:
        elapsed = history.elapsed_seconds(ultimo_treino['atualizado_em'], agora, operation='situation.last_training')
        dias_sem_treinar = elapsed // 86400 if elapsed is not None else 0.
    return {
        "lembretes_vencidos": vencidos,
        "prazos_proximos": prazos["n"] if prazos else 0,
        "curiosidades_abertas": curiosas["n"] if curiosas else 0,
        "curiosidades_sobre_pessoa": sobre_pessoa["n"] if sobre_pessoa else 0,
        "objetivos_travados": len(strategies.objetivos_travados()),
        "episodios_sem_refletir": reflection.episodios_desde_ultima(),
        "dias_sem_treinar": dias_sem_treinar,
    }


def descrever(situacao: dict) -> str:
    """A linha de situação que entra no contexto de cada turno."""
    s = situacao or {}
    partes = []
    if s.get("app"):
        tempo = f" há {s['minutos_na_atividade']} min" if s.get("minutos_na_atividade") else ""
        alvo = f"{s['app']}{tempo}"
        if s.get("detalhe"):
            alvo += f" ({s['detalhe'][:60]})"
        partes.append(f"na frente: {alvo}")
    m = s.get("midia") or {}
    if m.get("titulo"):
        partes.append(f"tocando: {m['titulo']}"
                      + (f" — {m['artista']}" if m.get("artista") else ""))
    if s.get("usuario_presente") is False:
        partes.append("sem atividade de entrada recente; presença física não confirmada")
    elif s.get("usuario_presente") is None:
        partes.append("presença da pessoa desconhecida")
    elif s.get("segundos_ociosos", 0) > 300:
        partes.append(f"sem falar com você há {int(s['segundos_ociosos'] // 60)} min")
    return " | ".join(partes) or "nada de especial acontecendo"
