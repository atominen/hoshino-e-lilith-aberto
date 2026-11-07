"""Admissão atômica das entidades; não agenda inferência nem encerra processos."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path

from core import gpu_metrics, interentity

MINIMUM = 16 * gpu_metrics.GIB
# Drivers reservam alguns MiB em placas nominais16GiB. Não arredondar uma
# classe inferior de memória nem somar a memória de outras placas.
DRIVER_RESERVE = 64 * 1024**2
ACTIVE = {'starting','awake','stopping'}


def _busy(root, entity, processes):
    busy = {e for e,p in (processes or {}).items() if e != entity and p.poll() is None}
    busy.update(row['entity_id'] for row in interentity.presence()['entities']
                if row['entity_id'] != entity and row['status'] in ACTIVE)
    for other in interentity.ENTITIES:
        if other == entity:
            continue
        for name in ('entity.lock','entity.boot.lock'):
            path = Path(root)/'entidades'/other/'runtime'/name
            if not path.exists():
                continue
            try:
                with path.open('r') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    fcntl.flock(lock,fcntl.LOCK_UN)
            except OSError:
                busy.add(other)  # Processo/lock incerto: não admitir outra entidade.
    return sorted(busy)


@contextmanager
def guard(root, entity, *, processes=None):
    """Mantém a verificação e a reserva inicial indivisíveis entre processos."""
    if entity not in interentity.ENTITIES:
        raise ValueError('Entidade inválida.')
    # 05/11 (pedido humano): nenhuma entidade inicia durante treino do laboratório nem perto da partida agendada.
    from core import bloqueio_treino
    bloqueio_treino.exigir_livre(root)
    path=Path(root)/'compartilhado/runtime/entity-admission.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        capacity=gpu_metrics.dedicated_capacity()
        total=capacity.get('total_bytes')
        eligible=(capacity.get('known') is True and type(total) is int and total >= MINIMUM-DRIVER_RESERVE)
        busy=_busy(root,entity,processes)
        if busy and not eligible:
            raise ValueError('Somente uma entidade ativa: executar mais de uma exige uma GPU com pelo menos '
                             '16 GB de VRAM dedicada. Já ativa/em inicialização/drenagem: '+', '.join(busy)+'. '
                             'Aguarde essa entidade dormir antes de iniciar outra.')
        yield dict(multiple_allowed=eligible,capacity=capacity,other_entities=busy)


@contextmanager
def _reservation(root, entity, *, bootstrap):
    handle=None
    try:
        with guard(root,entity):
            directory=Path(root)/'entidades'/entity/'runtime'
            directory.mkdir(parents=True,exist_ok=True)
            path=directory/('entity.boot.lock' if bootstrap else 'entity.lock')
            inherited=os.environ.get('HOSHINO_ENTITY_LOCK_FD')
            if inherited is not None:
                try:
                    fd=int(inherited); actual=os.fstat(fd); expected=(directory/'entity.boot.lock').stat()
                    if (actual.st_dev,actual.st_ino)!=(expected.st_dev,expected.st_ino):
                        raise ValueError('arquivo diferente')
                    if bootstrap:handle=os.fdopen(os.dup(fd),'a+')
                except (OSError,ValueError) as exc:
                    raise ValueError('Reserva de entidade com descritor herdado inválido.') from exc
            if handle is None:
                handle=path.open('a+')
            try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(f'{entity.title()} já está em execução.') from exc
        yield handle
    finally:
        if handle is not None:
            handle.close()


def instance(root, entity):
    """Trava do runner, separada da manutenção que recupera modelos locais."""
    return _reservation(root,entity,bootstrap=False)


def boot(root, entity):
    """Reserva de admissão durante boot/recuperação; herdada só pelo runner."""
    return _reservation(root,entity,bootstrap=True)
