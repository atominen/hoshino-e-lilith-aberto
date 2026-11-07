"""Bloqueio de inicialização das entidades durante os treinos do laboratório (pedido humano 05/11).

Só leitura dos registros duráveis do laboratório; não para nem cancela nada. É consultado
por `entity_admission.guard`, por onde passam a Central, o `iniciar_hoshino.sh` e os
próprios runners. Bloqueia:

- de ANTECEDENCIA_S antes do início de uma sessão agendada até o fim da janela dela
  (uma entidade acordada às 22:50 ainda teria reserva de GPU às 23:00, e a sessão se
  recusa a começar com reservas ativas);
- enquanto uma sessão noturna estiver ativa ou em recuperação;
- enquanto houver job de treino, medição ou avaliação do laboratório em andamento.

A recuperação de modelos do boot (`action == 'recover'`) não bloqueia, porque é ela
que prepara a entidade para acordar.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ANTECEDENCIA_S = 30 * 60
SESSAO_ATIVA = {'draining', 'running', 'stopping', 'restoring', 'recovery_required'}
JOB_ATIVO = {'started', 'running', 'cancel_requested'}
ACOES_DE_TREINO = {'smoke', 'train', 'evaluate'}


def _registro(root) -> Path:
    home = os.environ.get('HOSHINO_LAB_HOME') or str(Path(root) / 'laboratorio-local')
    return Path(home) / 'controle-laboratorio' / 'treinamento-unificado'


def _ler(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _hora(ts) -> str:
    return time.strftime('%d/%m %H:%M', time.localtime(ts))


def motivo(root, now: float | None = None) -> str:
    """Texto do bloqueio, ou '' quando as entidades podem iniciar."""
    reg = _registro(root)
    if not reg.is_dir():
        return ''
    now = time.time() if now is None else now
    sessao = _ler(reg / 'nights' / 'current.json')
    if isinstance(sessao, dict) and sessao.get('state') in SESSAO_ATIVA:
        return (f"Treino do laboratório em andamento (sessão {sessao.get('id', '?')}, estado {sessao['state']}); "
                'as entidades só iniciam quando ele terminar.')
    agenda = _ler(reg / 'nights' / 'scheduled-once.json')
    if isinstance(agenda, dict):
        plano: dict = agenda['plan'] if isinstance(agenda.get('plan'), dict) else {}
        inicio, fim = plano.get('starts_at'), plano.get('ends_at')
        # Depois do fim da janela vale só o estado real da sessão (acima): uma Central que caiu no meio
        # não pode deixar o registro 'started' bloqueando as entidades para sempre.
        if agenda.get('state') in ('attempting', 'started') and not (isinstance(fim, (int, float)) and now > fim):
            return (f"Treino agendado em andamento (sessão {agenda.get('id', '?')}); "
                    'as entidades só iniciam quando ele terminar.')
        if (agenda.get('state') == 'scheduled' and isinstance(inicio, (int, float)) and isinstance(fim, (int, float))
                and inicio - ANTECEDENCIA_S <= now <= fim):
            return (f'Treino agendado de {_hora(inicio)} até {_hora(fim)}: as entidades ficam bloqueadas desde '
                    f'{_hora(inicio - ANTECEDENCIA_S)} para a GPU estar livre na partida.')
    for arquivo in (reg / 'jobs').glob('*.json'):
        if arquivo.name.endswith('.state.json'):
            continue
        job = _ler(arquivo)
        if isinstance(job, dict) and job.get('state') in JOB_ATIVO and job.get('action') in ACOES_DE_TREINO:
            return (f"Job do laboratório em andamento ({job.get('action')} {job.get('model', '?')}/{job.get('entity', '?')}); "
                    'as entidades só iniciam quando ele terminar.')
    return ''


def exigir_livre(root) -> None:
    texto = motivo(root)
    if texto:
        raise ValueError(texto)
