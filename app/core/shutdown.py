"""Política limitada de drenagem, sem força contra efeitos incertos."""
from dataclasses import dataclass
import time
import threading
import hashlib
import json
import os
from pathlib import Path
import tempfile
from core import diagnostics


def record_result(root, token, result):
    """Receipt of the existing drain, bound to this authenticated lifecycle."""
    from core import job_bus
    directory=Path(root)/'compartilhado/runtime/launcher';directory.mkdir(parents=True,exist_ok=True)
    path=directory/'shutdown-result.json'
    if path.is_symlink():raise ValueError('Recibo de encerramento por link inválido.')
    data=dict(result,generation=hashlib.sha256(token.encode()).hexdigest(),pid=os.getpid(),
              process_stamp=job_bus._process_stamp(os.getpid()),at=time.time())
    fd,name=tempfile.mkstemp(prefix='.shutdown-',dir=directory)
    try:
        with os.fdopen(fd,'w') as out:
            os.fchmod(out.fileno(),0o600);json.dump(data,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return data


@dataclass(frozen=True)
class Policy:
    warn_after: float = 10
    normal_deadline: float = 30
    global_deadline: float = 45
    poll_seconds: float = .2

    def __post_init__(self):
        if not 0 <= self.warn_after <= self.normal_deadline <= self.global_deadline or self.poll_seconds <= 0:
            raise ValueError('Prazos de encerramento inválidos.')


def drain(snapshot, cooperate, escalate, policy=None, *, clock=time.monotonic, pause=time.sleep):
    """Callbacks observam/cancelam SOMENTE recursos cuja posse foi verificada.

    Se a segurança não puder ser demonstrada, termina o prazo com 'blocked',
    mantém o supervisor e registra a pendência. Não faz retries de ações.
    """
    policy = policy or Policy()
    start = clock()
    warned = cancelled = False
    probe = None
    state = {'pending': True, 'processes': [], 'jobs': [], 'diagnostic_error': 'observação inicial pendente'}
    result = []
    def report(event, **data):
        # O próprio diagnóstico pode estar com disco/SQLite bloqueado. Ele não
        # ganha permissão de estourar o prazo de drenagem.
        threading.Thread(target=diagnostics.emit, args=(event,), kwargs=data,
                         daemon=True, name='shutdown-diagnostic').start()
    def observe():
        try:
            observed = snapshot()
            if not isinstance(observed, dict):
                raise TypeError('Snapshot de encerramento inválido.')
            result.append(observed)
        except Exception as exc:
            result.append({'pending': True, 'processes': [], 'jobs': [], 'diagnostic_error': str(exc)})
            diagnostics.exception('shutdown.observation_failed', exc)
    while True:
        if probe is None or not probe.is_alive():
            if result:
                state = result.pop()
            probe = threading.Thread(target=observe, daemon=True, name='shutdown-observation')
            probe.start()
        remaining = max(0, policy.global_deadline - (clock() - start))
        probe.join(min(policy.poll_seconds, remaining))
        if result:
            state = result.pop()
        elif probe.is_alive():
            state = dict(state, pending=True, observation_pending=True)
        elapsed = clock() - start
        if not state.get('pending'):
            report('shutdown.complete', elapsed=elapsed)
            return dict(status='complete', elapsed=elapsed, blockers=[])
        if not warned and elapsed >= policy.warn_after:
            report('shutdown.slow', level='WARN', elapsed=elapsed, blockers=state)
            warned = True
        if not cancelled and elapsed >= policy.normal_deadline:
            report('shutdown.cancel_requested', level='WARN', elapsed=elapsed, blockers=state)
            def request_cancel():
                try:
                    cooperate(state)
                except Exception as exc:
                    diagnostics.exception('shutdown.cooperative_cancel_failed', exc)
            threading.Thread(target=request_cancel, daemon=True, name='shutdown-cooperative-cancel').start()
            cancelled = True
        if elapsed >= policy.global_deadline:
            # A escalada é opcional e precisa ser comprovadamente segura.
            # Este callback só pode decidir/agendar uma escalada segura, não
            # esperar processos nem operar sistemas externos indefinidamente.
            escalation = []
            def request_escalation():
                try:
                    escalation.append(escalate(state))
                except Exception as exc:
                    diagnostics.exception('shutdown.escalation_failed', exc)
            thread = threading.Thread(target=request_escalation, daemon=True)
            thread.start()
            thread.join(0)  # nenhum prazo extra depois do teto global
            escalated = escalation[0] if escalation else False
            final = state
            status = 'complete' if not final.get('pending') else 'blocked'
            report('shutdown.' + status, level='INFO' if status=='complete' else 'ERROR',
                             elapsed=clock()-start, blockers=final, escalated=escalated,
                             auto_retry=False)
            return dict(status=status, elapsed=clock()-start, blockers=final, escalated=escalated)
        pause(max(0, min(policy.poll_seconds, policy.global_deadline - (clock() - start))))
