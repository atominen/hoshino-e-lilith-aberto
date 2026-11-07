"""Predefinições de roteamento no RM existente, sem outro scheduler.

São heurísticas de custo, não ensaios de velocidade. Não alteram reservas,
camadas GPU, contexto, prioridade, permissões ou os gates físicos do RM.
"""
from dataclasses import dataclass
import math
import threading
import time

GIB = 1024**3
HOLD_SECONDS = 60


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    description: str
    reload_weight: float = 1
    queue_weight: float = 1
    hot_bonus: float = 1
    reservation_weight: float = 0


PROFILES = {
    'quality': Profile('quality', 'Qualidade', 'Tarefa complexa: conserva o principal e o contexto integral.'),
    'interactive': Profile('interactive', 'Resposta rápida', 'Pedido humano simples: equilibra latência, fila e recarga.'),
    'shared': Profile('shared', 'Recursos disputados', 'Há demanda de outra entidade: penaliza recargas e favorece pesos já quentes.', 2, 1, 1.5),
    'background': Profile('background', 'Trabalho de fundo', 'Atividade não interativa: evita trocas caras; fila humana mantém prioridade.', 2, 0, 1.5),
    'pressure': Profile('pressure', 'Pressão de memória', 'Favorece menor reserva entre opções elegíveis, sem rebaixar tarefas complexas.', 1, 1, 0, 16),
    'conservative': Profile('conservative', 'Conservador', 'Métricas incertas: evita recargas; o RM físico continua impedindo concessões inseguras.', 2, 1, 1.5),
}


def catalog():
    return [dict(id=p.id, label=p.label, description=p.description) for p in PROFILES.values()]


def select(*, complexity, priority, entity, state, ram, previous=None, now=None, wall_now=None):
    """Decisão pura; histerese só entre tarefas, nunca durante uma inferência."""
    now = time.monotonic() if now is None else now
    wall_now = time.time() if wall_now is None else wall_now
    metrics, policy = state.get('metrics', {}), state.get('policy', {})
    observed = metrics.get('observed_at')
    total, used = metrics.get('total_bytes'), metrics.get('used_bytes')
    known = (metrics.get('known') is True and metrics.get('stable') is True
             and type(observed) in {int, float} and math.isfinite(observed) and abs(wall_now-observed) <= 2
             and type(total) is int and total > 0 and type(used) is int and 0 <= used <= total
             and type(ram) is int and ram >= 0)
    if not known:
        target, reason = 'conservative', 'metrics_unknown_or_stale'
    elif (ram < policy.get('ram_margin_bytes', 2*GIB)+4*GIB
          or total-used < policy.get('margin_bytes', 768*1024**2)):
        target, reason = 'pressure', 'memory_headroom_low'
    elif complexity != 'simple':
        target, reason = 'quality', 'quality_required'
    else:
        # Presença/residência não prova demanda: só compute ou fila reais.
        demands = [*state.get('compute', []), *state.get('queue', [])]
        peer = any((row.get('request') or row).get('entity') not in {None, '', entity} for row in demands)
        if peer:
            target, reason = 'shared', 'other_entity_demand'
        elif priority <= 1:
            target, reason = 'interactive', 'interactive_request'
        else:
            target, reason = 'background', 'noninteractive_request'
    chosen, held, since = target, False, now
    if previous and previous.get('id') in PROFILES:
        old = previous['id']; age = now-previous['since']
        urgent = target in {'pressure', 'conservative', 'quality'} or (target == 'interactive' and old == 'background')
        if old == target:
            since = previous['since']
        elif not urgent and old != 'quality' and 0 <= age < HOLD_SECONDS:
            chosen, held, since = old, True, previous['since']
    return dict(id=chosen, label=PROFILES[chosen].label, reason=reason, requested=target,
                held=held, since=since, basis='heuristic_not_benchmark')


class Controller:
    """Histerese por entidade/processo; reiniciar não herda um perfil obsoleto."""
    def __init__(self):
        self._previous = {}
        self._lock = threading.Lock()

    def choose(self, **kwargs):
        with self._lock:
            entity = kwargs['entity']
            decision = select(**kwargs, previous=self._previous.get(entity))
            self._previous[entity] = decision
            return decision
