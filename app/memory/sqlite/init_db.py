"""
Esquema do banco + migração.

Roda tanto em banco novo quanto no banco que já existe (com os 17 episódios e
3 objetivos atuais) — nada é apagado. Chamado automaticamente na inicialização
da Hoshino, então não dá para o código sair da frente do esquema.

Tabelas da v6 (a mente): traços de personalidade com contador de evidência,
gostos com valência, impulsos, pessoas e confiança, tentativas por objetivo
(para tentar caminho diferente quando falha), reflexões, curiosidades abertas,
sessões de atividade do usuário, resumos de contexto compactado e partidas de
xadrez com a evolução de força dela.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import DB_PATH, ENTIDADE_NOME

TABELAS = {
    'memory_card_settings': """CREATE TABLE IF NOT EXISTS memory_card_settings (
        id TEXT PRIMARY KEY,tier TEXT NOT NULL CHECK(tier IN ('bronze','ferro','ouro','diamante')),
        updated_at TEXT NOT NULL)""",
    "episodes": """
        CREATE TABLE IF NOT EXISTS episodes (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, what_happened TEXT NOT NULL,
            context TEXT, action_taken TEXT, result TEXT, is_success BOOLEAN,
            evaluation TEXT, source TEXT, importance REAL, emotional_salience REAL,
            access_count INTEGER DEFAULT 0, last_accessed TEXT, status TEXT DEFAULT 'active')""",
    "memories": """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, created_at TEXT NOT NULL,
            valid_from TEXT, valid_to TEXT, source TEXT, confidence REAL, importance REAL,
            emotional_salience REAL, access_count INTEGER DEFAULT 0, last_accessed TEXT,
            content TEXT NOT NULL, entities TEXT, links TEXT, supersedes TEXT,
            chave TEXT, status TEXT DEFAULT 'active')""",
    "properties": """
        CREATE TABLE IF NOT EXISTS properties (
            id TEXT PRIMARY KEY, entity TEXT NOT NULL, chave TEXT NOT NULL, valor TEXT,
            unidade TEXT, confidence REAL DEFAULT 0.8, source TEXT, created_at TEXT,
            valid_to TEXT, access_count INTEGER DEFAULT 0, status TEXT DEFAULT 'active')""",
    "procedures": """
        CREATE TABLE IF NOT EXISTS procedures (
            id TEXT PRIMARY KEY, nome TEXT NOT NULL, objetivo TEXT, passos TEXT,
            precondicoes TEXT, resultado_esperado TEXT, tags TEXT, ambiente TEXT,
            sucessos INTEGER DEFAULT 0, falhas INTEGER DEFAULT 0, ultima_utilizacao TEXT,
            created_at TEXT, notas TEXT, confidence REAL DEFAULT 0.7,
            status TEXT DEFAULT 'active')""",
    "reminders": """
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY, created_at TEXT, message TEXT NOT NULL, due_at TEXT NOT NULL,
            repeat_rule TEXT, goal_id TEXT, status TEXT DEFAULT 'pending', fired_at TEXT,
            origem TEXT)""",
    "traits": """
        CREATE TABLE IF NOT EXISTS traits (
            nome TEXT PRIMARY KEY, valor REAL DEFAULT 0.5, evidencias INTEGER DEFAULT 0,
            soma_evidencia REAL DEFAULT 0, ultima_evidencia TEXT, consolidado INTEGER DEFAULT 0,
            descricao TEXT, atualizado_em TEXT)""",
    "tastes": """
        CREATE TABLE IF NOT EXISTS tastes (
            id TEXT PRIMARY KEY, objeto TEXT NOT NULL, categoria TEXT,
            valencia REAL NOT NULL, confianca REAL DEFAULT 0.4, motivo TEXT,
            evidencias INTEGER DEFAULT 1, origem TEXT, created_at TEXT,
            atualizado_em TEXT, status TEXT DEFAULT 'active')""",
    "people": """
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, nome TEXT NOT NULL, apelidos TEXT, papel TEXT,
            canais TEXT, confianca REAL DEFAULT 0.3, familiaridade REAL DEFAULT 0.0,
            afinidade REAL DEFAULT 0.0, interacoes INTEGER DEFAULT 0,
            primeiro_contato TEXT, ultimo_contato TEXT, notas TEXT,
            status TEXT DEFAULT 'active')""",
    "person_events": """
        CREATE TABLE IF NOT EXISTS person_events (
            id TEXT PRIMARY KEY, person_id TEXT, created_at TEXT, tipo TEXT,
            descricao TEXT, delta_confianca REAL, delta_afinidade REAL)""",
    "attempts": """
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY, goal_id TEXT, created_at TEXT, abordagem TEXT,
            detalhe TEXT, resultado TEXT, licao TEXT, numero INTEGER DEFAULT 1)""",
    "reflections": """
        CREATE TABLE IF NOT EXISTS reflections (
            id TEXT PRIMARY KEY, created_at TEXT, tema TEXT, conteudo TEXT,
            evidencias TEXT, tipo TEXT DEFAULT 'reflexao', importancia REAL DEFAULT 0.6,
            status TEXT DEFAULT 'active')""",
    "curiosities": """
        CREATE TABLE IF NOT EXISTS curiosities (
            id TEXT PRIMARY KEY, created_at TEXT, pergunta TEXT NOT NULL, sobre TEXT,
            origem TEXT, urgencia REAL DEFAULT 0.5, status TEXT DEFAULT 'aberta',
            resposta TEXT, respondida_em TEXT, tentativas INTEGER DEFAULT 0)""",
    "activity_sessions": """
        CREATE TABLE IF NOT EXISTS activity_sessions (
            id TEXT PRIMARY KEY, tipo TEXT, rotulo TEXT, inicio TEXT, fim TEXT,
            duracao_seg INTEGER, detalhe TEXT)""",
    "context_summaries": """
        CREATE TABLE IF NOT EXISTS context_summaries (
            id TEXT PRIMARY KEY, created_at TEXT, faixa TEXT, mensagens INTEGER,
            tokens_antes INTEGER, resumo TEXT, fatos_extraidos INTEGER)""",
    "chess_games": """
        CREATE TABLE IF NOT EXISTS chess_games (
            id TEXT PRIMARY KEY, created_at TEXT, terminou_em TEXT, oponente TEXT,
            cor_hoshino TEXT, resultado TEXT, lances INTEGER, pgn TEXT,
            rating_antes INTEGER, rating_depois INTEGER, erros TEXT, licao TEXT,
            status TEXT DEFAULT 'em_andamento')""",
    "emotion_log": """
        CREATE TABLE IF NOT EXISTS emotion_log (
            id TEXT PRIMARY KEY, created_at TEXT, emocao TEXT, intensidade REAL,
            gatilho TEXT, motivo TEXT)""",
    "skill_profile": """
        CREATE TABLE IF NOT EXISTS skill_profile (
            habilidade TEXT PRIMARY KEY, rating REAL, praticas INTEGER DEFAULT 0,
            vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0, empates INTEGER DEFAULT 0,
            nivel INTEGER DEFAULT 1, desbloqueios TEXT, atualizado_em TEXT)""",
    "facts": "CREATE TABLE IF NOT EXISTS facts (id TEXT PRIMARY KEY, content TEXT, confidence REAL)",
    "goals": """
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY, description TEXT, status TEXT, created_at TEXT,
            due_at TEXT, priority INTEGER DEFAULT 3, notes TEXT)""",
    "self_model_versions": """
        CREATE TABLE IF NOT EXISTS self_model_versions (
            version INTEGER PRIMARY KEY, content TEXT, created_at TEXT)""",
    "checkpoints": """
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY, state_hash TEXT, created_at TEXT, payload TEXT)""",
    "events_index": """
        CREATE TABLE IF NOT EXISTS events_index (
            event_id TEXT PRIMARY KEY, timestamp TEXT, kind TEXT, task_id TEXT, detalhe TEXT)""",
    "conversation_tasks": """
        CREATE TABLE IF NOT EXISTS conversation_tasks (
            id TEXT PRIMARY KEY, chave TEXT NOT NULL, objetivo TEXT NOT NULL,
            status TEXT DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            etapa_atual INTEGER DEFAULT 0, ultima_acao TEXT, ultimo_resultado TEXT)""",
    "conversation_task_steps": """
        CREATE TABLE IF NOT EXISTS conversation_task_steps (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, ordem INTEGER NOT NULL,
            texto TEXT NOT NULL, ferramenta TEXT, ferramentas TEXT DEFAULT '',
            ferramentas_executadas TEXT DEFAULT '', status TEXT DEFAULT 'pending',
            resultado TEXT)""",
}

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_mem_status ON memories(status, type)",
    "CREATE INDEX IF NOT EXISTS ix_prop_entity ON properties(entity, chave, status)",
    "CREATE INDEX IF NOT EXISTS ix_rem_due ON reminders(status, due_at)",
    "CREATE INDEX IF NOT EXISTS ix_goal_status ON goals(status)",
    "CREATE INDEX IF NOT EXISTS ix_ep_created ON episodes(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_taste_obj ON tastes(objeto, status)",
    "CREATE INDEX IF NOT EXISTS ix_people_nome ON people(nome)",
    "CREATE INDEX IF NOT EXISTS ix_attempt_goal ON attempts(goal_id)",
    "CREATE INDEX IF NOT EXISTS ix_cur_status ON curiosities(status, urgencia)",
    "CREATE INDEX IF NOT EXISTS ix_act_inicio ON activity_sessions(inicio)",
    "CREATE INDEX IF NOT EXISTS ix_chess_status ON chess_games(status)",
    "CREATE INDEX IF NOT EXISTS ix_ct_chave ON conversation_tasks(chave, status, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_cts_task ON conversation_task_steps(task_id, ordem)",
    "CREATE INDEX IF NOT EXISTS ix_emo_nome ON emotion_log(emocao, created_at)",
]

COLUNAS_NOVAS = [
    ("goals", "created_at", "TEXT"),
    ("goals", "due_at", "TEXT"),
    ("goals", "priority", "INTEGER DEFAULT 3"),
    ("goals", "notes", "TEXT"),
    ("memories", "chave", "TEXT"),
    ("memories", "rotulo", "TEXT"),       # 11/11: assunto fixo (memory/rotulos.py)
    ("checkpoints", "payload", "TEXT"),
    ("events_index", "detalhe", "TEXT"),
    ("goals", "tipo", "TEXT DEFAULT 'usuario'"),      # usuario|propria|curiosidade|origem
    ("goals", "person_id", "TEXT"),
    ("goals", "tentativas", "INTEGER DEFAULT 0"),
    ("goals", "ultima_tentativa", "TEXT"),
    ("episodes", "person_id", "TEXT"),
    ("episodes", "canal", "TEXT DEFAULT 'tui'"),
    ("episodes", "humor", "TEXT"),
    ("conversation_task_steps", "ferramentas_executadas", "TEXT DEFAULT ''"),
    ("conversation_task_steps", "ferramentas", "TEXT DEFAULT ''"),
    ("people", "autorizacao_operacional", "INTEGER DEFAULT 0"),
    ("memories", "person_id", "TEXT"),
    # Objetivo sustentado: não é tarefa de conclui-e-esquece, é diretiva que ela
    # retoma sozinha enquanto a condição durar (ex: "fica jogando até eu voltar").
    ("goals", "sustentar", "INTEGER DEFAULT 0"),
    ("goals", "enquanto", "TEXT"),        # ausente|sempre — quando a diretiva vale
    ("goals", "acao", "TEXT"),            # jogar|investigar|refletir — o que retomar
]


def _colunas(cur, tabela):
    return {linha[1] for linha in cur.execute(f"PRAGMA table_info({tabela})")}


def _existe(cur, tabela):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabela,))
    return cur.fetchone() is not None


def migrar_niveis_cartoes(db) -> bool:
    """07/11 (pedido humano): níveis bronze, ferro, ouro e diamante. A platina sai; o que estava nela vira diamante."""
    linha = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='memory_card_settings'").fetchone()
    if not linha or "'bronze'" in (linha[0] or ""):
        return False
    db.execute("ALTER TABLE memory_card_settings RENAME TO memory_card_settings_antiga")
    db.execute(TABELAS['memory_card_settings'])
    db.execute("INSERT INTO memory_card_settings(id,tier,updated_at) SELECT id, CASE WHEN tier='platina' THEN 'diamante' "
               "ELSE tier END, updated_at FROM memory_card_settings_antiga WHERE tier IN ('ferro','ouro','diamante','platina')")
    db.execute("DROP TABLE memory_card_settings_antiga")
    return True


def init_database(verbose: bool = True):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    relatorio = []

    # procedures antiga (id, command, strategy) e vazia -> recria no formato novo
    if _existe(cur, "procedures"):
        colunas = _colunas(cur, "procedures")
        if "nome" not in colunas:
            cur.execute("SELECT COUNT(*) FROM procedures")
            if cur.fetchone()[0] == 0:
                cur.execute("DROP TABLE procedures")
                relatorio.append("procedures recriada no formato novo")
            else:
                cur.execute("ALTER TABLE procedures RENAME TO procedures_antiga")
                relatorio.append("procedures antiga preservada como procedures_antiga")

    if migrar_niveis_cartoes(cur):
        relatorio.append("níveis dos cartões: bronze, ferro, ouro, diamante (platina virou diamante)")

    for nome, ddl in TABELAS.items():
        existia = _existe(cur, nome)
        cur.execute(ddl)
        if not existia:
            relatorio.append(f"tabela {nome} criada")

    for tabela, coluna, tipo in COLUNAS_NOVAS:
        if _existe(cur, tabela) and coluna not in _colunas(cur, tabela):
            cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            relatorio.append(f"{tabela}.{coluna} adicionada")

    for ddl in INDICES:
        cur.execute(ddl)

    conn.commit()
    conn.close()
    if verbose:
        print(f"Banco de {ENTIDADE_NOME} pronto em", DB_PATH)
        for linha in relatorio:
            print("  -", linha)
    return relatorio


if __name__ == "__main__":
    init_database()
