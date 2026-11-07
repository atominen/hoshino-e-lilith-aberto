#!/usr/bin/env python3
"""Revisão atribuída de continuidade de sessão Minecraft após recarga do condutor.

Uso (com a entidade acordada e conectada, tarefa pausada pela trava de sessão):

    HOSHINO_ENTIDADE=lilith PYTHONPATH=app:. python scripts/minecraft_revisar_sessao.py \\
        salvar TAREFA ARQUIVO            # antes do sono: guarda o último estado da ponte
    HOSHINO_ENTIDADE=lilith PYTHONPATH=app:. python scripts/minecraft_revisar_sessao.py \\
        revisar TAREFA ARQUIVO "motivo"  # depois de reconectar

Só registra a revisão quando a sessão anterior é a do estado salvo e posição e
inventário são idênticos; qualquer divergência recusa sem alterar nada. Não
executa ação de jogo, não resolve efeitos pendentes e não é ferramenta do LLM.
"""
import json
import sys
from pathlib import Path

import requests

from core import bd, minecraft_agent as agent

BRIDGE = 'http://127.0.0.1:8766/health'
RECONCILIATION = Path('compartilhado/runtime/ensaios/minecraft-reconciliation-20261027')


def _health():
    state = requests.get(BRIDGE, timeout=5).json()['state']
    return state, {i['name']: i['count'] for i in state.get('inventory') or []}


def salvar(task_id, path):
    state, inventory = _health()
    data = {'session': state['sessionId'], 'position': state['position'], 'inventory': inventory}
    Path(path).write_text(json.dumps(data, ensure_ascii=False))
    print('estado salvo:', data)


def revisar(task_id, path, reason):
    last = json.loads(Path(path).read_text())
    state, inventory = _health()
    row = bd.um('SELECT payload FROM conversation_task_game_states WHERE task_id=?', (task_id,))
    cp = json.loads(row['payload'])
    old = cp['session_id']
    diff = {k: (last['inventory'].get(k), inventory.get(k))
            for k in set(inventory) | set(last['inventory']) if inventory.get(k) != last['inventory'].get(k)}
    problems = [p for p, bad in (
        ('efeito pendente no checkpoint', bool(cp.get('pending'))),
        ('sessão registrada difere do estado salvo', old != last['session']),
        ('sessão não mudou', old == state['sessionId']),
        ('posição difere', state['position'] != last['position']),
        ('inventário difere: ' + json.dumps(diff, ensure_ascii=False), bool(diff))) if bad]
    if problems:
        print('NÃO revisado:', '; '.join(problems))
        return 1
    RECONCILIATION.mkdir(parents=True, exist_ok=True)
    stem = RECONCILIATION / f"session-{old}-to-{state['sessionId']}"
    stem.with_suffix('.before.json').write_text(row['payload'])
    review = agent.review_session_continuity(
        cp, state, reviewer='Claude · condutor do ensaio', reason=reason,
        evidence=[f"before:sessão {old} pos{tuple(last['position'].values())} inv {json.dumps(last['inventory'], sort_keys=True)}",
                  *([f"última observação: sessão {last['observed_session']} recibo {last['observed_receipt']}"]
                    if last.get('observed_session') else []),
                  f"now:sessão {state['sessionId']} porta {state.get('port')} pos e inventário idênticos"])
    bd.executar('UPDATE conversation_task_game_states SET payload=?,updated_at=? WHERE task_id=?',
                (json.dumps(cp, ensure_ascii=False), bd.agora(), task_id), strict=True)
    stem.with_suffix('.review.json').write_text(json.dumps(
        {'review': review, 'inventory': inventory, 'position': state['position']}, ensure_ascii=False, indent=1))
    print('revisão registrada:', old, '->', state['sessionId'])
    return 0


if __name__ == '__main__':
    command, task_id, path, *rest = sys.argv[1:]
    if command == 'salvar':
        salvar(task_id, path)
    elif command == 'revisar' and rest:
        sys.exit(revisar(task_id, path, rest[0]))
    else:
        sys.exit('uso: salvar TAREFA ARQUIVO | revisar TAREFA ARQUIVO "motivo"')
