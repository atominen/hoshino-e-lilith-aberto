"""
Autonomia e silêncio.

O comportamento antigo: a cada 8 batidas do heartbeat (2 minutos), mandava ao
modelo o texto "O usuário está em silêncio. Se houver metas, use ferramentas.
Caso contrário, responda 'AGUARDANDO'". O modelo quase nunca respondia só
"AGUARDANDO" — ele preenchia com comentário sobre a janela do Firefox, sobre o
horário, sobre os objetivos. Resultado: ela falava do nada, a cada dois minutos,
e às vezes citava "lembretes" que não existiam em lugar nenhum.

Duas causas, duas correções:

1. **Perguntar gera resposta.** Um modelo de linguagem chamado a cada 2 minutos
   vai produzir texto — é o que ele faz. A correção não é pedir silêncio com mais
   ênfase; é *não chamar o modelo* quando não há motivo. `avaliar_gatilhos()`
   decide isso em Python puro, sem LLM: sem gatilho concreto, o ciclo termina ali.

2. **Nada conferia o que ela dizia.** Agora toda fala espontânea passa por
   `validar_fala_autonoma()`: se mencionar lembrete/objetivo que não existe no
   banco, ou se for mensagem de preenchimento, não vai para a tela.
"""
import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from tools import agenda
from core import history

# Catálogo do modo legado limitado, não do modo contínuo configurável abaixo.
# Somente capacidades existentes, dentro da própria oficina/mente ou consultas
# de rede já permitidas. Não inclui mensagens, downloads, terminal, desktop,
# instalação, voz, edição de personalidade ou alteração de permissões.
EXPLORATION_TOOLS = frozenset({
    'web_search', 'fetch_page', 'estado_internet', 'get_system_time',
    'diario', 'oficina_logica', 'meus_gostos', 'minha_opiniao',
    'consultar_conhecimento', 'listar_oficina', 'ler_da_oficina',
    'jogar_xadrez', 'estado_partida', 'historico_xadrez', 'calcular',
})
_exploration = ContextVar('bounded_internal_exploration', default=None)
_last_receipt = ContextVar('initiative_last_tool_receipt', default=None)


@contextmanager
def exploration_scope(available, max_calls, *, persistent=False):
    """Restrição efetiva no executor, propagada também a asyncio.to_thread.

    Não é outro scheduler/recibo: os IDs são os dos dispatch/jobs existentes.
    O escopo só captura metadados dos resultados, nunca argumentos/saídas.
    """
    scope = dict(available=set(available) if persistent else set(available) & EXPLORATION_TOOLS,
                 remaining=max_calls, persistent=persistent, storage_failed=False,
                 receipts=[], stopped=False, lock=threading.Lock())
    token = _exploration.set(scope)
    try:
        yield scope
    finally:
        _exploration.reset(token)


def authorize_exploration_tool(name, arguments):
    scope = _exploration.get()
    if scope is None:
        return ''
    with scope['lock']:
        if scope['stopped'] or scope['remaining'] <= 0:
            return 'ACESSO_BLOQUEADO: deliberação encerrada; não repetir ações.'
        allowed = name in scope['available']
        if scope['persistent']:
            from core import initiative, capabilities
            pending = initiative.activity().get('pending_command')
            if pending:
                if name == 'ver_comando' and arguments.get('job_id') != pending.get('job_id'):
                    return 'ACESSO_BLOQUEADO: consulte o ID exato do comando pendente.'
                if capabilities.operation_mutates(name,arguments) and name != 'minha_atividade':
                    return 'ACESSO_BLOQUEADO: há comando pendente; verificar antes de outro efeito.'
        # Diário é voluntário/privado. A operação compartilhar não faz parte
        # deste turno interno, mesmo que o modelo a solicite explicitamente.
        if name == 'diario' and not scope['persistent']:
            allowed = allowed and arguments.get('operacao') in {'ler', 'escrever'}
        if name == 'oficina_logica' and not scope['persistent']:
            allowed = allowed and arguments.get('operacao') in {'listar', 'ler', 'salvar'}
        if not allowed:
            if not scope['persistent']:
                scope['stopped'] = True
            return 'ACESSO_BLOQUEADO: capacidade/operação fora desta deliberação privada.'
        scope['remaining'] -= 1
    return ''


def refresh_exploration_tools(names):
    scope = _exploration.get()
    if scope is not None and scope['persistent']:
        with scope['lock']:
            scope['available'] = set(names)


def recoverable_result(result):
    return (isinstance(result, dict) and
            (result.get('status') == 'permission' or
             (result.get('status') == 'error' and (
                 str(result.get('output','')).startswith('ACESSO_BLOQUEADO:') or
                 result.get('tool') == 'minha_atividade')) or
             (not result.get('mutates') and result.get('status') in {'error','not_found','offline'})))


def exploration_receipt(name, receipt_id, result, arguments=None):
    scope = _exploration.get()
    if scope is None:
        return
    if scope['persistent']:
        from core import initiative
        try:
            initiative.record_observation(name, receipt_id, arguments or {}, result)
        except Exception as exc:
            from core import diagnostics
            diagnostics.exception('initiative.observation_failed', exc, action_retried=False,
                                  receipt_id=receipt_id, tool=name)
            with scope['lock']:
                scope['storage_failed'] = scope['stopped'] = True
    with scope['lock']:
        scope['receipts'].append(dict(tool=name, receipt_id=receipt_id,
            status=result.get('status', 'unknown'), verified=result.get('verified') is True,
            mutates=result.get('mutates') is True))
        if result.get('status') != 'success' and not (scope['persistent'] and recoverable_result(result)):
            scope['stopped'] = True


def finish_exploration_actions():
    scope = _exploration.get()
    if scope is not None:
        with scope['lock']:
            scope['remaining'] = 0  # Último slot é comentário, não outro efeito.

try:
    from config import HORARIO_SILENCIO, INTERVALO_MIN_FALA_AUTONOMA
except ImportError:
    HORARIO_SILENCIO, INTERVALO_MIN_FALA_AUTONOMA = (0, 7), 600

# Frases de preenchimento: se a fala espontânea é só isso, ela não vale interrupção.
PREENCHIMENTO = [
    r"^\s*aguardando", r"estou (aqui|por aqui|à disposi|a disposi)",
    r"qualquer (coisa|necessidade|d[úu]vida)", r"posso ajudar", r"precisa de (algo|mais)",
    r"continuo (monitorando|acompanhando|observando|atenta)", r"fico no aguardo",
    r"sem novidades", r"tudo (certo|tranquilo|em ordem) por aqui",
    r"estou monitorando", r"me avise", r"avise-me", r"s[oó] avisar",
    r"estarei (aqui|atenta|dispon)", r"permane[çc]o", r"^\s*ok\.?\s*$",
]
# Termos que indicam que ela está afirmando algo sobre a agenda.
# O `s?` no fim de cada substantivo não é detalhe: sem ele, "seus lembretes das
# 8h" não casava com \blembrete\b e passava direto pelo guarda.
MENCAO_AGENDA = re.compile(
    r"\b(lembretes?|lembrar|lembr[oe]i|agendad[oa]s?|agenda|combinad[oa]s?|"
    r"voc[êe] (me )?pediu|prometi|marcad[oa]s?|prazos?|objetivos?|metas?)\b",
    re.IGNORECASE)


def em_horario_de_silencio(agora: datetime = None) -> bool:
    agora = history.local_datetime(agora)
    inicio, fim = HORARIO_SILENCIO
    if inicio == fim:
        return False
    if inicio < fim:
        return inicio <= agora.hour < fim
    return agora.hour >= inicio or agora.hour < fim  # faixa que cruza a meia-noite


def avaliar_gatilhos(agora: datetime = None, jobs_terminados=None) -> list:
    """Motivos concretos para a Hoshino falar sem ser chamada.

    Só isso autoriza uma fala espontânea. Ausência de gatilho = nada acontece,
    nem chamada ao modelo.
    """
    agora = history.local_datetime(agora)
    gatilhos = []

    for lem in agenda.lembretes_vencidos(agora):
        gatilhos.append({
            "tipo": "lembrete",
            "id": lem["id"],
            "texto": lem["mensagem"],
            "detalhe": f"lembrete {lem['id']} venceu em {lem['due_at']}",
        })

    for meta in agenda.objetivos_vencidos(agora):
        gatilhos.append({
            "tipo": "prazo",
            "id": meta["id"],
            "texto": meta["descricao"],
            "detalhe": f"o prazo do objetivo {meta['id']} chegou",
        })

    for job in (jobs_terminados or []):
        gatilhos.append({
            "tipo": "job",
            "id": job.get("id", ""),
            "texto": job.get("comando", ""),
            "detalhe": f"o job {job.get('id')} que eu iniciei terminou",
        })

    return gatilhos


def pode_falar(agora: datetime = None, ultima_fala_autonoma: datetime = None,
               gatilhos=None, *, monotonic_now=None, last_monotonic=None) -> tuple:
    """Decide se uma fala espontânea é permitida agora. Devolve (pode, motivo)."""
    agora = history.local_datetime(agora)
    if not gatilhos:
        return False, "sem gatilho concreto"
    urgente = any(g["tipo"] == "lembrete" for g in gatilhos)
    if em_horario_de_silencio(agora) and not urgente:
        return False, f"horário de silêncio ({HORARIO_SILENCIO[0]}h–{HORARIO_SILENCIO[1]}h)"
    if (ultima_fala_autonoma is not None or last_monotonic is not None) and not urgente:
        decorrido = history.runtime_elapsed(ultima_fala_autonoma, agora, start_monotonic=last_monotonic,
                                           end_monotonic=monotonic_now, operation='autonomy.speech_cooldown')
        if decorrido is None:
            return False, 'intervalo desde a última fala não confirmado'
        if decorrido < INTERVALO_MIN_FALA_AUTONOMA:
            faltam = int((INTERVALO_MIN_FALA_AUTONOMA - decorrido) / 60)
            return False, f"falei há pouco (faltam ~{faltam} min)"
    return True, "gatilho válido"


def prompt_autonomo(gatilhos: list) -> str:
    """Prompt do ciclo autônomo: entregar o gatilho, não pedir conversa."""
    lista = "\n".join(f"- [{g['tipo']}] {g['detalhe']}: {g['texto']}" for g in gatilhos)
    return (
        "[CICLO INTERNO — isto não é mensagem do usuário]\n"
        "Aconteceu algo que justifica você falar sem ser chamada:\n"
        f"{lista}\n\n"
        "Escreva UMA mensagem curta, direta, só sobre isso. Nada de saudação, nada de "
        "'estou por aqui', nada de resumo do dia, nada de comentar a tela.\n"
        "Se, olhando de novo, isso não justifica interromper a pessoa, responda exatamente "
        "SILENCIO e mais nada."
    )


# ---------------------------------------------------------------------------
# Checagem do que ela diz
# ---------------------------------------------------------------------------

def _agenda_real():
    conteudo = agenda.listar_lembretes() + "\n" + agenda.list_goals()
    tem_lembrete = "Não há nenhum lembrete" not in conteudo
    tem_objetivo = "Nenhum objetivo ativo" not in conteudo
    return conteudo, tem_lembrete, tem_objetivo


# Oferta e pergunta NÃO são afirmação. No banco real apareceu um falso positivo
# exatamente assim: ela perguntou "quer que eu configure algo antes de você sair,
# tipo lembrar da hidratação?" e o guarda tratou como se ela tivesse inventado um
# lembrete. Marcar oferta como alucinação ensina a ela a não oferecer nada.
OFERTA = re.compile(
    r"\b(quer que|posso|devo|gostaria que|se (?:você |vc )?quiser|"
    r"te aviso|quer um|crio|criar|deseja|prefere que)\b", re.IGNORECASE)


def _frases_com_mencao(texto: str) -> list:
    return [f for f in re.split(r"(?<=[.!?\n])\s+", texto or "") if MENCAO_AGENDA.search(f)]


def _e_afirmacao(frase: str) -> bool:
    """Afirmar é dizer que existe. Perguntar e oferecer, não."""
    if "?" in frase:
        return False
    if OFERTA.search(frase):
        return False
    # Futuro ("vou te lembrar às 8h") é promessa, não afirmação de agenda atual —
    # a criação do lembrete é conferida pela ferramenta, não aqui.
    if re.search(r"\b(vou|posso|irei|pretendo)\s+(?:te\s+)?(?:lembrar|avisar|criar)",
                 frase, re.IGNORECASE):
        return False
    return True


def checar_afirmacoes_de_agenda(texto: str) -> tuple:
    """Se ela AFIRMOU que existe lembrete/objetivo, confere se existe mesmo.

    Devolve (ok, correcao). `correcao` é o texto real da agenda, para reapresentar
    ao modelo antes de mostrar a resposta ao usuário.
    """
    if not texto or not MENCAO_AGENDA.search(texto):
        return True, ""
    afirmacoes = [f for f in _frases_com_mencao(texto) if _e_afirmacao(f)]
    if not afirmacoes:
        return True, ""            # só ofereceu ou perguntou: está tudo certo
    trecho = " ".join(afirmacoes)
    conteudo, tem_lembrete, tem_objetivo = _agenda_real()

    citou_lembrete = re.search(r"\b(lembretes?|lembrar|te lembr|marcad|agendad)", trecho, re.I)
    negou = re.search(r"\b(n[ãa]o (h[áa]|existe|tem)|nenhum|vazia|nada (agendado|marcado))",
                      trecho, re.I)
    if citou_lembrete and not tem_lembrete and not negou:
        return False, ("Você mencionou lembrete/agendamento, mas a agenda real está assim:\n"
                       f"{conteudo}\n"
                       "Corrija: se não existe, diga que não existe. Se o usuário quer um, "
                       "use criar_lembrete com um horário.")

    # Mesma checagem para objetivo: afirmar que existe meta quando a tabela está
    # vazia é o mesmo erro, só com outra palavra.
    citou_objetivo = re.search(r"\b(objetivos?|metas?)\b", trecho, re.I)
    if citou_objetivo and not tem_objetivo and not negou:
        return False, ("Eu falei de objetivo/meta, mas a minha agenda real está assim:\n"
                       f"{conteudo}\n"
                       "Corrijo: se não existe, eu digo que não existe. Se a pessoa quer "
                       "criar um, eu uso add_goal.")

    ids_citados = set(re.findall(r"\b(?:goal-[0-9a-f]{6}|lem-[0-9a-f]{8})\b", texto))
    if ids_citados:
        reais = set(re.findall(r"\b(?:goal-[0-9a-f]{6}|lem-[0-9a-f]{8})\b", conteudo))
        inventados = ids_citados - reais
        if inventados:
            return False, (f"Você citou {', '.join(inventados)}, que não existe(m). "
                           f"A agenda real é:\n{conteudo}")
    return True, ""


def eh_preenchimento(texto: str) -> bool:
    """Mensagem que não carrega informação nova: não justifica interromper."""
    limpo = (texto or "").strip()
    if not limpo:
        return True
    if len(limpo) < 12:
        return True
    corpo = re.sub(r"[^\w\sáàâãéêíóôõúç]", "", limpo.lower())
    for padrao in PREENCHIMENTO:
        if re.search(padrao, corpo, re.IGNORECASE):
            # Só é preenchimento se a frase for basicamente isso.
            if len(corpo) < 160:
                return True
    return False


# Palavras funcionais: não carregam assunto, então não contam para decidir se uma
# fala tem relação com o que a motivou. A alternativa óbvia — cortar por tamanho
# de palavra (a versão anterior usava 4+ letras) — rejeita paráfrase honesta:
# "o que ele faz da vida quando não está no computador" e "o que você faz da
# vida fora daqui" são a mesma pergunta reformulada, mas só compartilham "vida"
# (4 letras) e nenhuma palavra de 5+; um corte de tamanho fixo teria barrado essa
# fala legítima. Filtrar por função, não por tamanho, resolve isso de raiz.
_PARADAS_RELACAO = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos",
    "em", "no", "na", "nos", "nas", "por", "pra", "para", "com", "sem", "sob", "sobre",
    "que", "quem", "qual", "quais", "quando", "onde", "como", "porque", "pois",
    "e", "ou", "mas", "se", "nao", "não", "sim", "ja", "já", "ainda", "so", "só",
    "eu", "tu", "ele", "ela", "nos", "nós", "eles", "elas", "voce", "você", "vc",
    "me", "te", "lhe", "vos", "lhes", "meu", "minha", "meus", "minhas",
    "teu", "tua", "seu", "sua", "seus", "suas", "nosso", "nossa", "isso", "isto",
    "aquilo", "este", "esta", "esse", "essa", "aquele", "aquela", "aqueles", "aquelas",
    "eh", "é", "sou", "es", "és", "somos", "sao", "são", "era", "eram", "foi", "foram",
    "ser", "estar", "está", "estou", "estas", "estás", "estamos", "estao", "estão",
    "tem", "tém", "têm", "ter", "tenho", "tinha", "faz", "fazer", "fez",
    "vai", "vou", "vamos", "vao", "vão", "algo", "alguma", "algum", "alguns", "algumas",
    "tudo", "nada", "mais", "menos", "bem", "mal", "aqui", "ali", "la", "lá", "agora",
    "hoje", "ontem", "amanha", "amanhã", "muito", "muita", "muitos", "muitas", "pouco",
    "the", "and", "for",
}


def palavras_de_conteudo(texto: str) -> set:
    """As palavras que carregam assunto numa frase — sem depender de tamanho."""
    tokens = re.findall(r"[a-zà-ÿ]{3,}", (texto or "").lower())
    return {t for t in tokens if t not in _PARADAS_RELACAO}


def relacionada_ao_motivo(fala: str, intencao_ou_gatilhos) -> bool:
    """A fala compartilha alguma palavra de conteúdo com o que a motivou?

    Aceita uma intenção completa do kernel (dict com 'ancora'/'gatilhos') ou uma
    lista de gatilhos avulsa, para servir os dois formatos usados no projeto.
    """
    if isinstance(intencao_ou_gatilhos, dict):
        ancora = intencao_ou_gatilhos.get("ancora") or {}
        gatilhos = intencao_ou_gatilhos.get("gatilhos") or []
        pedacos = [ancora.get("texto", "")] + [
            f"{g.get('texto', '')} {g.get('detalhe', '')}" for g in gatilhos]
    else:
        pedacos = [f"{g.get('texto', '')} {g.get('detalhe', '')}"
                  for g in (intencao_ou_gatilhos or [])]
    alvo = palavras_de_conteudo(" ".join(pedacos))
    if not alvo:
        return True     # nada específico para comparar: não bloqueia por relação
    return bool(alvo & palavras_de_conteudo(fala))


def validar_fala_autonoma(texto: str, intencao=None, gatilhos: list = None) -> tuple:
    """Filtro final antes de uma fala espontânea aparecer. (pode_mostrar, motivo).

    Fala autônoma é exceção. Sem motivo social concreto, a Hoshino trabalha por
    dentro e não transforma um ciclo interno em monólogo público.
    """
    limpo = (texto or "").strip()
    if not limpo:
        return False, "resposta vazia"
    if re.fullmatch(r"(silencio|silêncio|aguardando)[.!]?", limpo, re.IGNORECASE):
        return False, "ela mesma decidiu ficar quieta"
    if eh_preenchimento(limpo):
        return False, "mensagem de preenchimento, sem conteúdo novo"

    # Compatibilidade: versões anteriores/consumidores legados passam a lista de
    # gatilhos como segundo argumento. Esse formato é explicitamente aceito por
    # ``relacionada_ao_motivo`` e não deve resultar em AttributeError. Um gatilho
    # concreto é, por definição, um motivo de aviso/conexão legítimo para o filtro.
    if isinstance(intencao, list) and gatilhos is None:
        gatilhos = intencao
        tipo = "avisar"
    else:
        tipo = str((intencao or {}).get("tipo", "")).casefold()

    # Só estas intenções têm permissão para gerar fala pública. Investigar, jogar,
    # refletir e observar são trabalhos internos; qualquer texto produzido durante
    # eles é registro, nunca conversa espontânea.
    if tipo not in {"avisar", "falar", "conhecer", "despertar"}:
        return False, f"intenção {tipo or 'desconhecida'} é interna e não deve falar"

    # A conexão sozinha nunca vira ensaio autobiográfico. Falas espontâneas são
    # curtas; uma resposta longa precisa ter vindo de um pedido explícito da pessoa.
    if len(limpo) > (420 if tipo == "avisar" else 280):
        return False, "fala autônoma longa demais para uma interrupção espontânea"
    # Ao acordar sem lembrança, dizer quem é faz parte de se apresentar a quem estiver aí.
    if tipo != "despertar" and re.match(r"^\s*(?:eu sou|sou uma|me chamo|meu nome é|meu nome e|fui criada|fui programada)\b", limpo, re.IGNORECASE):
        return False, "autoapresentação/biografia não é motivo de iniciativa"
    if tipo == "conhecer" and "?" not in limpo:
        return False, "curiosidade dirigida à pessoa precisa virar uma pergunta"

    ok, _ = checar_afirmacoes_de_agenda(limpo)
    if not ok:
        return False, "citou agenda que não existe"

    referencia = intencao if intencao is not None else (gatilhos or [])
    if not relacionada_ao_motivo(limpo, referencia):
        return False, "a fala não tem relação com o motivo concreto"
    return True, "ok"
