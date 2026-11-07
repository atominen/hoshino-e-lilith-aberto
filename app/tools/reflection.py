"""
Reflexão sobre si mesma.

A versão anterior quebrava se `personality` não existisse no JSON, gravava a
versão de backup com o número errado e não deixava registro nenhum no banco —
`self_model_versions` ficou com zero linhas desde sempre.

Continua sendo uma mudança simples e explícita (não é evolução automática de
personalidade — isso exige evidência acumulada, e o lugar disso é a memória),
mas agora: valida, versiona no arquivo E no banco, e recusa duplicata.
"""
import json
import os
import shutil
import sqlite3
from datetime import datetime

from config import DB_PATH, SELF_MODEL_PATH, VERSOES_DIR


def _carregar():
    with open(SELF_MODEL_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _gravar(dados):
    from core import state_file
    if not state_file.update(SELF_MODEL_PATH, lambda atual: atual.update(dados), 'self_model.write'):
        raise OSError('Self-model não confirmado; arquivo anterior preservado quando não houve replace.')


def _registrar_versao(dados):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute(
            "INSERT OR REPLACE INTO self_model_versions (version, content, created_at) "
            "VALUES (?, ?, ?)",
            (dados.get("version", 0), json.dumps(dados, ensure_ascii=False),
             datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        return True
    except sqlite3.Error as exc:
        from core import diagnostics
        diagnostics.persistence_failure('self_model.version_index', DB_PATH, exc,
                                        retry_safe=True, committed=True, partial=True)
        return False  # arquivo salvo; não repetir aprendizado para reparar índice
    finally:
        if conn is not None:
            conn.close()


def learn_preference(new_preference: str) -> str:
    """Internaliza uma preferência no self-model, gerando nova versão."""
    preferencia = (new_preference or "").strip()
    if not preferencia:
        return "Erro: diga qual preferência."
    if not os.path.exists(SELF_MODEL_PATH):
        return "Erro: self_model.json não encontrado."

    try:
        dados = _carregar()
    except json.JSONDecodeError as e:
        return f"Erro: self_model.json está corrompido ({e}). Não vou sobrescrever."

    dados.setdefault("personality", {}).setdefault("preferences", [])
    atuais = dados["personality"]["preferences"]
    if any(preferencia.lower() == p.lower() for p in atuais):
        return f"'{preferencia}' já estava internalizada — não dupliquei."

    versao_atual = int(dados.get("version", 1))
    os.makedirs(VERSOES_DIR, exist_ok=True)
    shutil.copy(SELF_MODEL_PATH,
                os.path.join(VERSOES_DIR, f"self_model_v{versao_atual}.json"))

    atuais.append(preferencia)
    dados["version"] = versao_atual + 1
    dados["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    _gravar(dados)
    indexada = _registrar_versao(dados)
    return (f"Preferência internalizada: '{preferencia}'. Self-model agora na versão "
            f"{dados['version']} (a v{versao_atual} ficou guardada)." +
            ('' if indexada else ' Persistência parcial: arquivo salvo, índice SQLite de versões falhou; consulte o diagnóstico. Não repetir o aprendizado.'))


def estado_do_self_model() -> str:
    """Resumo do que ela consolidou sobre si mesma até aqui."""
    if not os.path.exists(SELF_MODEL_PATH):
        return "self_model.json não encontrado."
    dados = _carregar()
    p = dados.get("personality", {})
    return (f"Self-model v{dados.get('version')}: "
            f"{len(p.get('traits', []))} traços, {len(p.get('preferences', []))} preferências, "
            f"{len(p.get('aversions', []))} aversões, "
            f"{len(dados.get('beliefs_about_self', []))} crenças sobre si.")
