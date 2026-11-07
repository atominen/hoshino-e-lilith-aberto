import json
import threading
import time
import unittest
from unittest.mock import Mock, patch
import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import shutdown, job_bus
from tools import terminal
import iniciar_entidades as launcher


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now
    def advance(self, duration): self.now += duration


class Encerramento(unittest.TestCase):
    def run_policy(self, ends_at=None):
        clock = Clock()
        cooperate, escalate = Mock(), Mock(return_value=False)
        state = lambda: dict(pending=ends_at is None or clock.now < ends_at, job={'id':'teste','mutates':True,'outcome':'uncertain'})
        with patch('core.shutdown.diagnostics.emit') as diag:
            r = shutdown.drain(state, cooperate, escalate, shutdown.Policy(1,2,3,.1), clock=clock, pause=clock.advance)
        return r, cooperate, escalate, diag

    def test_normal(self):
        r, cancel, _, _ = self.run_policy(.2)
        self.assertEqual(r['status'], 'complete')
        cancel.assert_not_called()

    def test_lento_avisa_sem_forcar(self):
        r, cancel, _, diag = self.run_policy(1.6)
        self.assertEqual(r['status'], 'complete')
        self.assertIn('shutdown.slow', [c.args[0] for c in diag.call_args_list])
        cancel.assert_not_called()

    def test_travado_e_mutavel_incerto(self):
        r, cancel, escalate, diag = self.run_policy()
        self.assertEqual(r['status'], 'blocked')
        self.assertLessEqual(r['elapsed'], 3.001)
        cancel.assert_called_once()
        self.assertEqual(r['blockers']['job']['outcome'], 'uncertain')
        self.assertFalse(r['escalated'])

    def test_observacao_travada_tambem_tem_prazo(self):
        event = threading.Event()
        try:
            started = time.monotonic()
            r = shutdown.drain(lambda: event.wait(5), lambda _:None, lambda _:False,
                               shutdown.Policy(.01,.03,.08,.01))
            self.assertEqual(r['status'], 'blocked')
            self.assertLess(time.monotonic()-started, .4)
        finally:
            event.set()

    def test_supervisor_nao_mata_entidade_travada(self):
        supervisor = launcher.Supervisor()
        proc = Mock(pid=43210)
        proc.poll.return_value = None
        supervisor.processes['hoshino'] = proc
        with patch.object(launcher.interentity, 'request_sleep') as sleep, patch.object(launcher.job_bus, 'status', return_value=[]), patch.object(launcher.resource_manager, 'status', return_value=[]), patch.object(launcher, 'ROOT', __import__('pathlib').Path(config.RUNTIME_DIR)):
            r = supervisor.shutdown(policy=shutdown.Policy(.01,.02,.05,.01))
        self.assertEqual(r['status'], 'blocked')
        sleep.assert_called()
        proc.kill.assert_not_called()
        proc.terminate.assert_not_called()
        self.assertTrue(supervisor.closing)

    def test_pid_reutilizado_e_legado_nunca_recebem_sinal(self):
        for meta in ({'pid':43210}, {'pid':43210,'process_stamp':'antigo','entity':config.ENTIDADE_ID,'project_root':str(__import__('pathlib').Path(config.RUNTIME_DIR).resolve())}):
            with patch.object(terminal, '_ler_job', return_value=meta), patch.object(terminal, '_vivo', return_value=True), patch.object(job_bus, '_process_stamp', return_value='novo'), patch.object(terminal.os, 'killpg') as signal:
                r = terminal.encerrar_comando('job-teste')
            self.assertTrue(r.startswith('Erro: posse'))
            signal.assert_not_called()

    def test_diagnostico_travado_nao_estoura_prazo(self):
        event = threading.Event()
        try:
            with patch('core.shutdown.diagnostics.emit', side_effect=lambda *a, **k: event.wait(2)):
                started = time.monotonic()
                r = shutdown.drain(lambda: {'pending': True}, lambda _:None, lambda _:False,
                                   shutdown.Policy(.01,.02,.06,.01))
                self.assertLess(time.monotonic()-started, .3)
                self.assertEqual(r['status'], 'blocked')
        finally:
            event.set()

    def test_processo_alheio_nao_e_adotado_por_metadados(self):
        import os
        meta = dict(pid=os.getpid(), process_stamp=job_bus._process_stamp(os.getpid()), entity=config.ENTIDADE_ID,
                    project_root=str(Path(config.RUNTIME_DIR).resolve()), process_token='não-pertence-a-job')
        with patch.object(terminal, '_ler_job', return_value=meta), patch.object(terminal.os, 'killpg') as signal:
            r = terminal.encerrar_comando('job-forjado')
        self.assertTrue(r.startswith('Erro: posse'))
        signal.assert_not_called()

    def cancel_owned(self, alive, signal_error=None):
        meta = dict(id='job-teste', status='rodando', pid=43210, process_stamp='stamp',
                    process_token='token', entity=config.ENTIDADE_ID,
                    project_root=str(Path(config.RUNTIME_DIR).resolve()))
        env = (b'HOSHINO_JOB_PROCESS_TOKEN=token\0HOSHINO_JOB_ROOT=' +
               str(Path(config.RUNTIME_DIR).resolve()).encode() +
               b'\0HOSHINO_JOB_ENTITY=' + config.ENTIDADE_ID.encode() + b'\0')
        with patch.object(terminal, '_ler_job', return_value=meta), patch.object(terminal, '_vivo', side_effect=alive), \
             patch.object(Path, 'read_bytes', return_value=env), patch.object(job_bus, '_process_stamp', return_value='stamp'), \
             patch.object(terminal.os, 'getpgid', return_value=43210), patch.object(terminal.os, 'killpg', side_effect=signal_error) as signal, \
             patch.object(terminal.time, 'sleep'), patch.object(terminal, '_salvar_job') as save:
            r = terminal.encerrar_comando('job-teste')
        return r, meta, signal, save

    def test_job_proprio_confirma_termino_sem_afirmar_sucesso_original(self):
        from core import dispatch
        r, meta, signal, save = self.cancel_owned([True, False, False])
        self.assertTrue(dispatch._resultado_mecanico('encerrar_comando', r)['verified'])
        signal.assert_called_once()
        self.assertEqual(meta['status'], 'encerrado')
        self.assertEqual(meta['outcome'], 'uncertain')
        self.assertFalse(meta['auto_retry'])
        save.assert_called_once()

    def test_sinal_enviado_nao_prova_termino(self):
        from core import dispatch
        r, meta, signal, save = self.cancel_owned([True, True, True])
        self.assertEqual(dispatch._resultado_mecanico('encerrar_comando', r)['status'], 'uncertain')
        self.assertEqual(signal.call_count, 2)
        self.assertEqual(meta['status'], 'rodando')
        self.assertFalse(meta['auto_retry'])
        save.assert_called_once()

    def test_erro_apos_tentar_sinal_nao_autoriza_repeticao(self):
        from core import dispatch
        r, meta, signal, save = self.cancel_owned([True], OSError('resultado do sinal indisponível'))
        self.assertEqual(dispatch._resultado_mecanico('encerrar_comando', r)['status'], 'uncertain')
        self.assertEqual(meta['outcome'], 'uncertain')
        self.assertFalse(meta['auto_retry'])
        save.assert_called_once()


if __name__ == '__main__':
    unittest.main()
