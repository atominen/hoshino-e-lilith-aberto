"""Estações que a entidade colocou no mundo Minecraft (bancada, forno...), lembradas entre tarefas.

30/10, pedido humano: ela não recuperava as fornalhas e bancadas que construía; cada tarefa começava sem saber delas e
fabricava outras (4 tábuas ou 8 pedras cada). Os registros vêm só de recibos de colocação verificados pela ponte; a
ausência é marcada quando, de perto, a percepção não a encontra mais (inclusive depois de ela recolher). Só informa
e oferece opções: usar, voltar, recolher ou fazer outra continua sendo decisão dela.
"""
from __future__ import annotations

import hashlib
import json
import math

from core import bd

# Só os tipos que a percepção da ponte enxerga (USEFUL_BLOCKS); os outros sumiriam na primeira conferência.
STATIONS = {'crafting_table', 'furnace'}
# Revisões Codex: ausência na percepção só vale de perto e no mesmo chunk em que ela está (sempre carregado); no chunk
# vizinho o bloco pode ainda não ter carregado, e não se afirma que sumiu.
CONFERIR_ATE = 8.0


def _chunk(x, z) -> tuple[int, int]:
    return int(math.floor(x)) >> 4, int(math.floor(z)) >> 4


def _schema() -> None:
    bd.executar('''CREATE TABLE IF NOT EXISTS minecraft_stations(
        key TEXT PRIMARY KEY, server TEXT NOT NULL, name TEXT NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL,
        z INTEGER NOT NULL, dimension TEXT, placed_at TEXT NOT NULL, receipt_id TEXT, removed_at TEXT,
        removed_reason TEXT)''', strict=True)


def _server(state_or_target: dict) -> str | None:
    host, port = state_or_target.get('host'), state_or_target.get('port')
    return f'{host}:{port}' if isinstance(host, str) and host and isinstance(port, int) else None


def _key(server: str, dimension, position: dict) -> str:
    return hashlib.sha256(json.dumps([server, dimension, [position[k] for k in 'xyz']]).encode()).hexdigest()[:24]


def registrar_colocacao(target: dict, placed: dict, receipt_id: str | None) -> None:
    """Chamado com o recibo de colocação verificado (minecraft_agent.record)."""
    server = _server(target)
    p = placed.get('position') or {}
    if (placed.get('name') not in STATIONS or not server or not all(type(p.get(k)) is int for k in 'xyz')
            or not isinstance(placed.get('dimension'), str)):  # dimensão desconhecida não vira registro
        return
    _schema()
    bd.executar('''INSERT INTO minecraft_stations(key,server,name,x,y,z,dimension,placed_at,receipt_id,removed_at,removed_reason)
        VALUES(?,?,?,?,?,?,?,?,?,NULL,NULL) ON CONFLICT(key) DO UPDATE SET name=excluded.name,placed_at=excluded.placed_at,
        receipt_id=excluded.receipt_id,removed_at=NULL,removed_reason=NULL''',
        (_key(server, placed.get('dimension'), p), server, placed['name'], p['x'], p['y'], p['z'], placed.get('dimension'),
         bd.agora(), receipt_id), strict=True)


def conferir_e_listar(state: dict, perception: dict | None, limite: int = 4) -> list[dict]:
    """Estações dela neste servidor e dimensão, da mais perto para a mais longe. As que estão a até CONFERIR_ATE blocos,
    no mesmo chunk que ela, e não aparecem numa percepção lida (o mais próximo daquele tipo está mais longe que ela, ou
    não há nenhum) são marcadas como ausentes antes de listar."""
    server, here = _server(state), state.get('position') or {}
    if (not server or not isinstance(state.get('dimension'), str)
            or not all(type(here.get(k)) in (int, float) for k in 'xyz')):
        return []
    _schema()
    rows = bd.consultar('''SELECT key,name,x,y,z,placed_at FROM minecraft_stations WHERE server=? AND dimension=?
        AND removed_at IS NULL''', (server, state['dimension']), strict=True)
    arredores = (perception or {}).get('arredores') if isinstance(perception, dict) else None
    lidos = isinstance(arredores, dict) and bool(arredores)  # percepção vazia pode ser mundo ainda carregando
    out = []
    for row in rows:
        p = {'x': row['x'], 'y': row['y'], 'z': row['z']}
        dist = math.dist([here[k] for k in 'xyz'], [p[k] + .5 for k in 'xyz'])
        if lidos and dist <= CONFERIR_ATE and _chunk(p['x'], p['z']) == _chunk(here['x'], here['z']):
            seen = arredores.get(row['name']) if isinstance(arredores.get(row['name']), dict) else None
            if seen is None or (type(seen.get('distancia')) in (int, float) and seen['distancia'] > dist + 1.5):
                bd.executar('UPDATE minecraft_stations SET removed_at=?,removed_reason=? WHERE key=?',
                            (bd.agora(), 'não está mais lá (percepção de perto)', row['key']), strict=True)
                continue
        out.append({'nome': row['name'], 'posicao': p, 'distancia': round(dist, 1), 'colocada_em': row['placed_at'][:16]})
    return sorted(out, key=lambda s: s['distancia'])[:limite]
