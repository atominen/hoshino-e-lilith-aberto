"""
Agenda — objetivos e lembretes de verdade.

O que existia antes: `remind_goal(goal_id, message)` que devolvia a string
"[LEMBRETE DA AGENDA]: ..." e nada mais. Não tinha horário, não tinha
armazenamento, não checava se o objetivo existia e não disparava nunca. Ou
seja: qualquer "lembrete" que a Hoshino mencionasse era invenção dela, porque
não havia lembrete nenhum no sistema. Também dava para cadastrar o mesmo
objetivo várias vezes (o banco tinha "Lembrar de beber água" duplicado).

Agora:
  * tabela `reminders` com mensagem, horário de disparo, repetição e estado;
  * interpretação de tempo em português ("em 20 min", "amanhã 9h", "todo dia
    às 8", "a cada 2 horas", "15/09 14:30");
  * horário obrigatório: sem data válida, o lembrete NÃO é criado e ela recebe
    um erro claro pedindo o horário — em vez de "anotado!" sem nada anotado;
  * `lembrar_objetivo` confere no banco se o objetivo existe;
  * `resumo_agenda()` injeta o estado real na conversa, então ela não precisa
    (nem pode) adivinhar o que está agendado;
  * objetivo/lembrete quase idêntico a um já ativo é recusado com o ID do que
    já existe, em vez de duplicar.
"""
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timedelta
from datetime import timezone

from config import DB_PATH
from core import history

DIAS_SEMANA = {
    "segunda": 0, "segunda-feira": 0, "terca": 1, "terça": 1, "terca-feira": 1,
    "terça-feira": 1, "quarta": 2, "quarta-feira": 2, "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}
UNIDADES = {
    "s": 1, "seg": 1, "segundo": 1, "segundos": 1,
    "m": 60, "min": 60, "mins": 60, "minuto": 60, "minutos": 60,
    "h": 3600, "hora": 3600, "horas": 3600,
    "d": 86400, "dia": 86400, "dias": 86400,
    "semana": 604800, "semanas": 604800,
}


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=5000")
    history.register_sql_clock(conn)
    return conn


def _agora():
    return history.local_now().replace(tzinfo=None)


def _iso(dt: datetime) -> str:
    return history.utc_timestamp(dt)


def _fmt(dt_iso: str) -> str:
    try:
        dt = history.local_datetime(dt_iso)
    except (TypeError, ValueError):
        return str(dt_iso)
    hoje = history.local_datetime(_agora()).date()
    if dt.date() == hoje:
        return f"hoje {dt:%H:%M}"
    if dt.date() == hoje + timedelta(days=1):
        return f"amanhã {dt:%H:%M}"
    return f"{dt:%d/%m %H:%M}"


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _semelhanca(a: str, b: str) -> float:
    """Semelhança entre dois registros, para não cadastrar a mesma coisa duas vezes.

    Jaccard puro não pegava "estudar X" vs "estudar X agora" (0.67) nem os dois
    "beber água" que já estavam duplicados no banco real. Por isso combina com o
    coeficiente de sobreposição: se um texto contém todas as palavras do outro,
    é o mesmo assunto dito com mais palavras.
    """
    vazias = {"de", "da", "do", "para", "a", "o", "e", "em", "que", "me", "lembrar",
              "lembre", "um", "uma", "no", "na", "ao", "com", "por", "regularmente",
              "agora", "hoje", "sempre", "mais", "bem"}
    ta = {p for p in re.findall(r"\w+", _normalizar(a)) if p not in vazias and len(p) > 2}
    tb = {p for p in re.findall(r"\w+", _normalizar(b)) if p not in vazias and len(p) > 2}
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    sobreposicao = len(ta & tb) / min(len(ta), len(tb))
    # Um texto contém (quase) todas as palavras do outro: mesmo assunto dito
    # com mais palavras. Não exijo jaccard alto aqui — é exatamente o caso em
    # que o texto maior soma palavras novas (tipo "regularmente para manter a
    # hidratação adequada") que derruba o jaccard sem mudar o assunto.
    if min(len(ta), len(tb)) >= 2 and sobreposicao >= 0.85:
        return max(jaccard, 0.85)
    return jaccard


# ---------------------------------------------------------------------------
# Interpretação de tempo em português
# ---------------------------------------------------------------------------

def _hora_do_texto(texto: str, padrao_hora=9, padrao_min=0):
    """Extrai HH:MM de trechos como 'às 14:30', '9h', '8 horas', '14h05'."""
    m = re.search(r"(?:as|às|as\s+|\bpara\s+as\s+)?\b([0-2]?\d)\s*[:h]\s*([0-5]\d)\b", texto)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b([0-2]?\d)\s*h\b", texto)
    if m:
        return int(m.group(1)), 0
    m = re.search(r"\b(?:as|às)\s+([0-2]?\d)\b", texto)
    if m:
        return int(m.group(1)), 0
    m = re.search(r"\b([0-2]?\d)\s*horas?\b", texto)
    if m:
        return int(m.group(1)), 0
    return padrao_hora, padrao_min


def interpretar_tempo(texto: str, agora: datetime = None):
    """Converte uma expressão de tempo em (datetime, regra_repeticao, erro).

    Devolve (None, None, mensagem) quando não consegue entender — e é isso que
    impede um lembrete fantasma de ser criado sem horário.
    """
    # Calendário no fuso configurado; preservar retorno naive usado pelo parser
    # original. A persistência abaixo converte novos registros para UTC.
    agora = history.local_datetime(agora if agora is not None else _agora()).replace(tzinfo=None)
    bruto = (texto or "").strip()
    if not bruto:
        return None, None, "não veio nenhum horário"
    t = _normalizar(bruto)

    # --- "agora", "já", "imediatamente": a pessoa quer ser lembrada na hora, não
    # daqui a X minutos. Sem isto, "lembra agora de beber água" caía no catch-all
    # de erro e o lembrete nunca era criado — silenciosamente, porque quem pediu
    # não teve como saber que a palavra não era reconhecida.
    if re.search(r"\b(agora mesmo|imediatamente|agora|ja|já)\b", t):
        return agora + timedelta(seconds=5), None, None

    # --- repetição por intervalo: "a cada 2 horas"
    m = re.search(r"a cada\s+(\d+)\s*(\w+)", t)
    if m:
        qtd, unidade = int(m.group(1)), m.group(2)
        seg = UNIDADES.get(unidade)
        if not seg:
            return None, None, f"não entendi a unidade de tempo '{unidade}'"
        total = qtd * seg
        if total < 60:
            return None, None, "intervalo mínimo de repetição é 1 minuto"
        return agora + timedelta(seconds=total), f"intervalo:{total}", None

    # --- repetição diária: "todo dia 8h", "diariamente às 20:00"
    if re.search(r"\b(todo dia|todos os dias|diariamente|toda manha|toda noite)\b", t):
        hora, minuto = _hora_do_texto(t, 9, 0)
        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if alvo <= agora:
            alvo += timedelta(days=1)
        return alvo, "diario", None

    # --- repetição semanal: "toda segunda 9h"
    m = re.search(r"\b(?:toda|todo)\s+(segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo)", t)
    if m:
        alvo_dia = DIAS_SEMANA[m.group(1)]
        hora, minuto = _hora_do_texto(t, 9, 0)
        delta = (alvo_dia - agora.weekday()) % 7
        alvo = (agora + timedelta(days=delta)).replace(hour=hora, minute=minuto,
                                                       second=0, microsecond=0)
        if alvo <= agora:
            alvo += timedelta(days=7)
        return alvo, "semanal", None

    # --- relativo: "em 30 min", "daqui a 2 horas", "em 1h30"
    m = re.search(r"\b(?:em|daqui a|dentro de)\s+(\d+)\s*(\w+)", t)
    if m:
        qtd, unidade = int(m.group(1)), m.group(2)
        seg = UNIDADES.get(unidade)
        if not seg:
            return None, None, (f"não entendi '{unidade}'. Use minutos, horas, dias ou semanas")
        alvo = agora + timedelta(seconds=qtd * seg)
        m2 = re.search(r"\b(\d+)\s*h\s*(\d{1,2})\b", t)
        if m2 and unidade in ("h", "hora", "horas"):
            alvo = agora + timedelta(hours=int(m2.group(1)), minutes=int(m2.group(2)))
        return alvo, None, None

    # --- data explícita: "15/09 14:30", "15/09/2026"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        ano = int(m.group(3)) if m.group(3) else agora.year
        if ano < 100:
            ano += 2000
        hora, minuto = _hora_do_texto(t, 9, 0)
        try:
            alvo = datetime(ano, mes, dia, hora, minuto)
        except ValueError:
            return None, None, f"data inválida: {dia}/{mes}"
        if alvo <= agora and not m.group(3):
            try:
                alvo = alvo.replace(year=ano + 1)
            except ValueError:
                pass
        return alvo, None, None

    # --- dia nomeado: "amanhã 9h", "hoje 22:00", "depois de amanhã"
    base = None
    if "depois de amanha" in t:
        base = agora + timedelta(days=2)
    elif "amanha" in t:
        base = agora + timedelta(days=1)
    elif "hoje" in t:
        base = agora
    else:
        for nome, indice in DIAS_SEMANA.items():
            if re.search(rf"\b{re.escape(_normalizar(nome))}\b", t):
                delta = (indice - agora.weekday()) % 7 or 7
                base = agora + timedelta(days=delta)
                break
    if base is not None:
        hora, minuto = _hora_do_texto(t, 9 if base.date() != agora.date() else agora.hour + 1, 0)
        alvo = base.replace(hour=min(hora, 23), minute=minuto, second=0, microsecond=0)
        if alvo <= agora:
            alvo += timedelta(days=1)
        return alvo, None, None

    # --- só a hora: "14:30", "9h"
    m = re.search(r"\b([0-2]?\d)[:h]([0-5]\d)\b", t) or re.search(r"\b([0-2]?\d)\s*h\b", t)
    if m:
        hora = int(m.group(1))
        minuto = int(m.group(2)) if m.lastindex and m.lastindex >= 2 else 0
        if hora > 23 or minuto > 59:
            return None, None, "hora inválida"
        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if alvo <= agora:
            alvo += timedelta(days=1)
        return alvo, None, None

    return None, None, (f"não consegui entender '{bruto}' como horário. "
                        f"Exemplos que funcionam: 'em 30 minutos', 'amanhã às 9h', "
                        f"'todo dia 8h', '15/09 14:30', 'a cada 2 horas'")


def _proxima_ocorrencia(atual: datetime, regra: str, agora: datetime) -> datetime:
    if not regra:
        return None
    atual, agora = history.local_datetime(atual), history.local_datetime(agora)
    if regra in ('diario', 'semanal'):
        dias = 1 if regra == 'diario' else 7
        saltos = max(1, (agora.date() - atual.date()).days // dias)
        prox = atual + timedelta(days=saltos * dias)
        if prox.timestamp() <= agora.timestamp():
            prox += timedelta(days=dias)
    elif regra.startswith('intervalo:'):
        segundos = int(regra.split(':', 1)[1])
        if segundos < 60:
            raise ValueError('Intervalo mínimo de repetição é 1 minuto.')
        # Tempo decorrido, não horário de calendário. Não iterar cada minuto
        # perdido durante anos de suspensão ou desligamento.
        atual = atual.astimezone(timezone.utc)
        saltos = max(1, int((agora.astimezone(timezone.utc) - atual).total_seconds() // segundos) + 1)
        prox = atual + timedelta(seconds=saltos * segundos)
    else:
        raise ValueError('Regra de repetição desconhecida.')
    return prox


# ---------------------------------------------------------------------------
# Lembretes
# ---------------------------------------------------------------------------

def criar_lembrete(mensagem: str, quando: str, goal_id: str = None,
                   origem: str = "usuario") -> str:
    """Cria um lembrete real, com horário de disparo."""
    mensagem = (mensagem or "").strip()
    if not mensagem:
        return "Erro: o lembrete precisa de um texto."
    alvo, regra, erro = interpretar_tempo(quando)
    if erro:
        return f"Lembrete NÃO criado: {erro}. Pergunte o horário ao usuário."

    conn = _conn()
    cur = conn.cursor()
    if goal_id:
        cur.execute("SELECT id FROM goals WHERE id=?", (goal_id,))
        if not cur.fetchone():
            conn.close()
            return (f"Lembrete NÃO criado: o objetivo '{goal_id}' não existe. "
                    f"Use list_goals para ver os IDs reais.")

    cur.execute("SELECT id, message, due_at FROM reminders WHERE status='pending'")
    for rid, msg, due in cur.fetchall():
        if _semelhanca(msg, mensagem) >= 0.8:
            conn.close()
            return (f"Já existe um lembrete parecido: [{rid}] '{msg}' para {_fmt(due)}. "
                    f"Não criei outro. Cancele ou adie aquele se for o caso.")

    rid = f"lem-{uuid.uuid4().hex[:8]}"
    cur.execute(
        """INSERT INTO reminders (id, created_at, message, due_at, repeat_rule, goal_id,
                                  status, fired_at, origem)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?)""",
        (rid, _iso(_agora()), mensagem, _iso(alvo), regra, goal_id, origem))
    conn.commit()
    conn.close()
    repeticao = {"diario": " (todo dia)", "semanal": " (toda semana)"}.get(regra, "")
    if regra and regra.startswith("intervalo:"):
        repeticao = f" (a cada {int(regra.split(':')[1]) // 60} min)"
    return f"Lembrete [{rid}] criado para {_fmt(_iso(alvo))}{repeticao}: {mensagem}"


def listar_lembretes(incluir_concluidos: bool = False) -> str:
    """Lista os lembretes que existem de verdade no banco."""
    conn = _conn()
    cur = conn.cursor()
    if incluir_concluidos:
        cur.execute("SELECT id, message, due_at, status, repeat_rule FROM reminders "
                    "ORDER BY project_epoch(due_at) DESC LIMIT 30")
    else:
        cur.execute("SELECT id, message, due_at, status, repeat_rule FROM reminders "
                    "WHERE status='pending' ORDER BY project_epoch(due_at) IS NULL, project_epoch(due_at) LIMIT 30")
    linhas = cur.fetchall()
    conn.close()
    if not linhas:
        return ("Não há nenhum lembrete cadastrado. Se você achou que havia, estava "
                "enganada — a lista é esta, vazia.")
    saida = []
    for rid, msg, due, status, regra in linhas:
        extra = f" [{status}]" if status != "pending" else ""
        rep = f" ·{regra}" if regra else ""
        saida.append(f"[{rid}] {_fmt(due)}{rep}{extra} — {msg}")
    return "Lembretes:\n" + "\n".join(saida)


def lembretes_vencidos(agora: datetime = None) -> list:
    """Lembretes cujo horário já chegou. É o único gatilho legítimo para a
    Hoshino falar sozinha sobre lembrete."""
    agora = agora or _agora()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""SELECT id, message, due_at, repeat_rule, goal_id FROM reminders
                   WHERE status='pending' AND project_epoch(due_at) <= ?
                   ORDER BY project_epoch(due_at), id""",
                (history.timestamp_epoch(agora),))
    linhas = cur.fetchall()
    invalidos = cur.execute("SELECT COUNT(*) FROM reminders WHERE status='pending' "
                            "AND project_epoch(due_at) IS NULL").fetchone()[0]
    conn.close()
    if invalidos:
        history._clock_warning('agenda.due', 'invalid_due_time')
    vencidos = []
    for r in linhas:
        if r[3]:
            try:
                _proxima_ocorrencia(datetime.fromisoformat(r[2]), r[3], agora)
            except (ValueError, TypeError, OverflowError):
                # Mantém pendente e visível na agenda, mas não fala a cada tick
                # sobre uma recorrência impossível de confirmar/reagendar.
                history._clock_warning('agenda.due', 'invalid_recurrence')
                continue
        vencidos.append({'id': r[0], 'mensagem': r[1], 'due_at': r[2], 'repeat_rule': r[3], 'goal_id': r[4]})
    return vencidos


def marcar_entregue(lembrete_id: str) -> str:
    """Marca um lembrete como entregue. Se for repetitivo, reagenda o próximo."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT due_at, repeat_rule FROM reminders WHERE id=?", (lembrete_id,))
    linha = cur.fetchone()
    if not linha:
        conn.close()
        return f"Lembrete '{lembrete_id}' não existe."
    due, regra = linha
    agora = _agora()
    if regra:
        try:
            prox = _proxima_ocorrencia(datetime.fromisoformat(due), regra, agora)
        except (ValueError, TypeError, OverflowError):
            conn.close()
            history._clock_warning('agenda.deliver', 'invalid_recurrence')
            return f'Lembrete {lembrete_id} NÃO marcado como entregue: horário/regra de repetição inválido. Corrija a agenda.'
        cur.execute("UPDATE reminders SET due_at=?, fired_at=? WHERE id=?",
                    (_iso(prox), _iso(agora), lembrete_id))
        resultado = f"Lembrete {lembrete_id} entregue; próximo em {_fmt(_iso(prox))}."
    else:
        cur.execute("UPDATE reminders SET status='done', fired_at=? WHERE id=?",
                    (_iso(agora), lembrete_id))
        resultado = f"Lembrete {lembrete_id} entregue e encerrado."
    conn.commit()
    conn.close()
    return resultado


def adiar_lembrete(lembrete_id: str, tempo: str = "em 10 minutos") -> str:
    """Adia um lembrete existente."""
    alvo, _, erro = interpretar_tempo(tempo)
    if erro:
        return f"Não adiei: {erro}"
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT message FROM reminders WHERE id=? AND status='pending'", (lembrete_id,))
    linha = cur.fetchone()
    if not linha:
        conn.close()
        return f"Lembrete '{lembrete_id}' não existe ou já foi encerrado."
    cur.execute("UPDATE reminders SET due_at=? WHERE id=?", (_iso(alvo), lembrete_id))
    conn.commit()
    conn.close()
    return f"Lembrete {lembrete_id} adiado para {_fmt(_iso(alvo))}."


def cancelar_lembrete(lembrete_id: str) -> str:
    """Cancela um lembrete."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET status='cancelled' WHERE id=? AND status='pending'",
                (lembrete_id,))
    mudou = cur.rowcount
    conn.commit()
    conn.close()
    return (f"Lembrete {lembrete_id} cancelado." if mudou
            else f"Lembrete '{lembrete_id}' não existe ou já não estava ativo.")


# ---------------------------------------------------------------------------
# Objetivos
# ---------------------------------------------------------------------------

def add_goal(description: str, prazo: str = None, prioridade: int = 3,
             sustentar: bool = False, enquanto: str = "", acao: str = "") -> str:
    """Adiciona um objetivo persistente (com prazo opcional).

    `sustentar`/`enquanto`/`acao` são para diretiva contínua ("fica jogando
    xadrez até eu voltar"), não para tarefa de fazer-e-concluir: ver o schema
    de add_goal em core/dispatch.py para a descrição completa que o modelo lê.
    """
    description = (description or "").strip()
    if not description:
        return "Erro: descreva o objetivo."
    enquanto = (enquanto or "").strip().lower()
    acao = (acao or "").strip().lower()
    if enquanto not in ("", "ausente", "sempre"):
        return f"Erro: 'enquanto' precisa ser 'ausente' ou 'sempre' (recebi '{enquanto}')."
    if sustentar and acao not in ("jogar", "investigar", "refletir"):
        return "Erro: objetivo sustentado precisa de 'acao' (jogar, investigar ou refletir)."
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, description FROM goals WHERE status='active'")
    for gid, desc in cur.fetchall():
        if _semelhanca(desc, description) >= 0.8:
            conn.close()
            return (f"Já existe um objetivo equivalente: [{gid}] {desc}. "
                    f"Não criei duplicado.")
    due = None
    if prazo:
        alvo, _, erro = interpretar_tempo(prazo)
        if erro:
            conn.close()
            return f"Objetivo NÃO criado: {erro}"
        due = _iso(alvo)
    gid = f"goal-{uuid.uuid4().hex[:6]}"
    cur.execute("""INSERT INTO goals (id, description, status, created_at, due_at,
                   priority, sustentar, enquanto, acao)
                   VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?)""",
                (gid, description, _iso(_agora()), due, prioridade,
                 1 if sustentar else 0, enquanto, acao))
    conn.commit()
    conn.close()
    rotulo = " (diretiva contínua)" if sustentar else ""
    return f"Objetivo [{gid}] criado{f' com prazo {_fmt(due)}' if due else ''}{rotulo}: {description}"


def objetivos_sustentados(enquanto: str = None) -> list:
    """Diretivas contínuas ativas — kernel.deliberar() checa isto a cada ciclo,
    com prioridade sobre o impulso de ócio normal (que tem período refratário
    e não sustenta 'fica fazendo isso até eu voltar')."""
    conn = _conn()
    cur = conn.cursor()
    if enquanto:
        cur.execute("SELECT id, description, acao, enquanto FROM goals "
                    "WHERE status='active' AND sustentar=1 AND enquanto=?", (enquanto,))
    else:
        cur.execute("SELECT id, description, acao, enquanto FROM goals "
                    "WHERE status='active' AND sustentar=1")
    linhas = [dict(id=r[0], description=r[1], acao=r[2], enquanto=r[3]) for r in cur.fetchall()]
    conn.close()
    return linhas


def diretiva_ativa(usuario_presente: bool | None):
    """A diretiva sustentada que vale AGORA, dado se a pessoa está por perto —
    ou None se nenhuma diretiva ativa se aplica neste momento. 'ausente' só
    vale com ausência confirmada; inatividade ou desconhecido não bastam.
    'sempre' vale o tempo todo até ser concluída."""
    for d in objetivos_sustentados():
        if d["enquanto"] == "sempre" or (d["enquanto"] == "ausente" and usuario_presente is False):
            return d
    return None


def concluir_diretivas(enquanto: str) -> list:
    """Fecha toda diretiva sustentada cuja condição de parada acabou de se
    cumprir (ex: 'ausente' quando a pessoa volta). Devolve os IDs concluídos."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM goals WHERE status='active' AND sustentar=1 AND enquanto=?",
               (enquanto,))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        cur.executemany("UPDATE goals SET status='completed' WHERE id=?", [(i,) for i in ids])
        conn.commit()
    conn.close()
    return ids


def list_goals(incluir_concluidos: bool = False) -> str:
    """Lista objetivos."""
    conn = _conn()
    cur = conn.cursor()
    consulta = ("SELECT id, description, status, due_at, sustentar, enquanto FROM goals "
                "ORDER BY status, id" if incluir_concluidos else
                "SELECT id, description, status, due_at, sustentar, enquanto FROM goals "
                "WHERE status='active'")
    cur.execute(consulta)
    linhas = cur.fetchall()
    conn.close()
    if not linhas:
        return "Nenhum objetivo ativo."
    return "Objetivos:\n" + "\n".join(
        f"[{gid}] {desc}" + (f" (prazo {_fmt(due)})" if due else "")
        + (f" — diretiva contínua ({enquanto})" if sustentar else "")
        + (f" — {st}" if st != "active" else "")
        for gid, desc, st, due, sustentar, enquanto in linhas)


def complete_goal(goal_id: str) -> str:
    """Conclui um objetivo."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE goals SET status='completed' WHERE id=? AND status='active'", (goal_id,))
    mudou = cur.rowcount
    conn.commit()
    conn.close()
    return (f"Objetivo {goal_id} concluído." if mudou
            else f"Objetivo '{goal_id}' não existe ou já estava concluído.")


def lembrar_objetivo(goal_id: str) -> str:
    """Traz o texto REAL de um objetivo para citar ao usuário.

    Substitui o antigo `remind_goal(goal_id, message)`, em que a mensagem era
    escrita pelo modelo e nada era conferido — origem dos 'lembretes' que não
    existiam em lugar nenhum.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT description, status, due_at FROM goals WHERE id=?", (goal_id,))
    linha = cur.fetchone()
    conn.close()
    if not linha:
        return (f"Não existe objetivo com ID '{goal_id}'. Não invente um lembrete: "
                f"consulte list_goals e use um ID real, ou diga que não há nada agendado.")
    desc, status, due = linha
    if status != "active":
        return f"O objetivo {goal_id} existe mas está '{status}': {desc}"
    return f"Objetivo {goal_id} (ativo): {desc}" + (f" — prazo {_fmt(due)}" if due else "")


# ---------------------------------------------------------------------------
# Visão consolidada (injetada no contexto)
# ---------------------------------------------------------------------------

def objetivos_vencidos(agora: datetime = None) -> list:
    agora = agora or _agora()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""SELECT id, description, due_at FROM goals
                   WHERE status='active' AND due_at IS NOT NULL AND project_epoch(due_at) <= ?
                   ORDER BY project_epoch(due_at), id""",
                (history.timestamp_epoch(agora),))
    linhas = cur.fetchall()
    conn.close()
    return [{"id": r[0], "descricao": r[1], "due_at": r[2]} for r in linhas]


def resumo_agenda() -> str:
    """Estado real da agenda, para entrar no contexto de cada resposta.

    É a peça que impede lembrete inventado: ela nunca precisa lembrar de cabeça
    o que está agendado, porque a verdade está aqui em toda mensagem.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT id, description FROM goals WHERE status='active' LIMIT 10")
    metas = cur.fetchall()
    cur.execute("""SELECT id, message, due_at FROM reminders WHERE status='pending'
                   ORDER BY project_epoch(due_at) IS NULL, project_epoch(due_at) LIMIT 10""")
    lembretes = cur.fetchall()
    conn.close()
    partes = []
    partes.append("Objetivos ativos: " + (
        "; ".join(f"[{g}] {d}" for g, d in metas) if metas else "nenhum"))
    partes.append("Lembretes agendados: " + (
        "; ".join(f"[{r}] {_fmt(d)} {m}" for r, m, d in lembretes) if lembretes
        else "nenhum (não existe nenhum lembrete)"))
    return " | ".join(partes)
