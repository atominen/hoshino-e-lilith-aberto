"""Administração da memória persistente da Hoshino.

O reset de memória remove todo estado dinâmico persistente da Hoshino: memória,
conversa, pessoas, objetivos, lembretes, emoções, tarefas, checkpoints e vetores.
Preserva somente os arquivos estáticos de identidade e configuração necessários
para a aplicação continuar iniciando.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

import config
from config import DB_PATH

# Tudo que pode contribuir para "lembrar do passado".
# goals/reminders são compromissos; traits/tastes/self-model são a identidade
# que se forma e não devem desaparecer num apagamento de memória.
TABELAS_MEMORIA = (
    # F6 significa apagar registros dinâmicos, não apenas "episódios".
    # Mantemos as tabelas/schema para a aplicação continuar funcionando.
    "episodes", "memories", "facts", "properties", "procedures",
    "reminders", "traits", "tastes", "people", "person_events", "attempts",
    "reflections", "curiosities", "activity_sessions", "context_summaries",
    "chess_games", "emotion_log", "skill_profile", "goals",
    "self_model_versions", "checkpoints", "events_index",
    "conversation_tasks", "conversation_task_steps",
)

COLECOES_VETORIAIS = tuple(
    f"{config.ENTIDADE_ID}_{sufixo}"
    for sufixo in ("episodes", "knowledge", "procedures")
)

_RUNTIME_DIR = Path(config.RUNTIME_DIR)
_ESTADO_MENTE = _RUNTIME_DIR / "estado_mente.json"
_REFLEXAO_NOTURNA = _RUNTIME_DIR / "reflexao_noturna.json"
_REFLEXAO_NOTURNA_PENDENTE = _RUNTIME_DIR / "reflexao_noturna_pendente.json"
_RUNTIME_JSON_DINAMICOS = (
    _RUNTIME_DIR / "bus" / "discord_estado.json",
    _RUNTIME_DIR / "bus" / "discord_usuarios.json",
    _RUNTIME_DIR / "bus" / "discord_contatos.json",
)
_RUNTIME_GLOB_DINAMICOS = (
    _RUNTIME_DIR / "bus" / "entrada",
    _RUNTIME_DIR / "bus" / "saida",
    _RUNTIME_DIR / "jobs",
)


def _tabelas_dinamicas(cur: sqlite3.Cursor) -> list[str]:
    """Retorna todas as tabelas da aplicação, incluindo futuras tabelas de estado."""
    rows = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows if str(row[0]).strip()]


def wipe_persistent_memory() -> str:
    """Zera todos os registros persistentes da aplicação, mantendo apenas o schema.

    O F6 é intencionalmente total no banco: memória, chat, pessoas, objetivos,
    emoções, tarefas, checkpoints, histórico e qualquer tabela nova são apagados.
    Arquivos estáticos de identidade e configurações ficam intactos.
    """
    apagados: list[str] = []

    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            # Não dependemos de uma lista manual de tabelas; isso evita deixar
            # resíduos quando um novo módulo criar uma tabela no futuro.
            conn.execute("PRAGMA foreign_keys=OFF")
            cur = conn.cursor()
            tabelas = _tabelas_dinamicas(cur)
            cur.execute("BEGIN")
            for tabela in tabelas:
                cur.execute(f'DELETE FROM "{tabela}"')
                apagados.append(f"{tabela} ({cur.rowcount})")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        apagados.append("SQLite não encontrado")

    # Limpa o vetor sem apagar configurações ou banco do restante da aplicação.
    try:
        import memory.vector.chroma_store as cs
        if not cs.DISPONIVEL:
            apagados.append("vetorial indisponível")
        else:
            erros = []
            for nome in COLECOES_VETORIAIS:
                try:
                    cs.client.delete_collection(nome)
                except Exception as exc:  # noqa: BLE001
                    if "not found" not in str(exc).lower():
                        erros.append(f"{nome}: {exc}")
            cs.collection = cs.client.get_or_create_collection(name=COLECOES_VETORIAIS[0])
            cs.knowledge_collection = cs.client.get_or_create_collection(name=COLECOES_VETORIAIS[1])
            cs.procedure_collection = cs.client.get_or_create_collection(name=COLECOES_VETORIAIS[2])
            apagados.append("Chroma (3 coleções vazias)")
            if erros:
                apagados.append("avisos vetoriais: " + " | ".join(erros))
    except Exception as exc:  # noqa: BLE001
        apagados.append(f"ERRO no Chroma: {exc}")

    # O histórico fica em outro SQLite; ele também é memória de conversa e
    # precisa ser zerado para o F6 realmente significar "esquecer tudo".
    try:
        from core import history
        bruto = history.clear_all()
        apagados.append(f"histórico (mensagens={bruto['mensagens']}, eventos={bruto['eventos']})")
    except Exception as exc:  # noqa: BLE001
        apagados.append(f"ERRO no histórico: {exc}")

    # Estado mental que não passa pelo SQLite.
    for caminho in (_ESTADO_MENTE, _REFLEXAO_NOTURNA, _REFLEXAO_NOTURNA_PENDENTE):
        try:
            if caminho.exists():
                caminho.unlink()
                apagados.append(caminho.name)
        except OSError as exc:
            apagados.append(f"ERRO {caminho.name}: {exc}")

    # Registros operacionais que também fazem a Hoshino "lembrar" de um estado
    # anterior: contatos observados do Discord, filas de mensagens e jobs.
    # Não tocamos em rede.json, microfone.json ou discord.env: são configuração/
    # credenciais, não memória aprendida. Também não apagamos logs de auditoria.
    for caminho in _RUNTIME_JSON_DINAMICOS:
        try:
            if caminho.exists():
                caminho.unlink()
                apagados.append(str(caminho.relative_to(_RUNTIME_DIR)))
        except OSError as exc:
            apagados.append(f"ERRO {caminho.name}: {exc}")

    for pasta in _RUNTIME_GLOB_DINAMICOS:
        if not pasta.is_dir():
            continue
        try:
            for caminho in pasta.iterdir():
                if caminho.is_file() and caminho.suffix in {".json", ".tmp"}:
                    caminho.unlink()
                    apagados.append(str(caminho.relative_to(_RUNTIME_DIR)))
        except OSError as exc:
            apagados.append(f"ERRO {pasta.name}: {exc}")

    restantes = memoria_restante()
    if restantes:
        return ("Memória zerada com ressalvas: " + "; ".join(apagados) +
                f". Ainda há registros: {restantes}.")
    return "Todos os registros persistentes foram zerados: " + "; ".join(apagados) + "."


def memoria_restante() -> str:
    """Retorna qualquer registro dinâmico que sobreviva ao F6."""
    partes = []
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            cur = conn.cursor()
            tabelas = _tabelas_dinamicas(cur)
            for tabela in tabelas:
                if not cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
                ).fetchone():
                    continue
                n = int(cur.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0])
                if n:
                    partes.append(f"{tabela}={n}")
        finally:
            conn.close()

    for caminho in (_ESTADO_MENTE, _REFLEXAO_NOTURNA, _REFLEXAO_NOTURNA_PENDENTE, *_RUNTIME_JSON_DINAMICOS):
        if caminho.exists():
            partes.append(str(caminho.relative_to(_RUNTIME_DIR)))
    for pasta in _RUNTIME_GLOB_DINAMICOS:
        if pasta.is_dir():
            n = sum(1 for p in pasta.iterdir() if p.is_file() and p.suffix in {".json", ".tmp"})
            if n:
                partes.append(f"{pasta.name}={n}")
    return ", ".join(partes)


def estatisticas_brutas() -> str:
    """Contagem auditável dos registros dinâmicos."""
    if not os.path.exists(DB_PATH):
        return "Banco não encontrado."
    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        cur = conn.cursor()
        partes = []
        for tabela in _tabelas_dinamicas(cur):
            if not cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)
            ).fetchone():
                partes.append(f"{tabela}: ausente")
                continue
            partes.append(f"{tabela}: {int(cur.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0])}")
        return " | ".join(partes)
    finally:
        conn.close()
