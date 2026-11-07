"""Bloqueio de inicialização das entidades durante treinos (05/11). Só diretórios temporários."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from core import bloqueio_treino as b  # noqa: E402


class BloqueioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reg = self.root / 'laboratorio-local/controle-laboratorio/treinamento-unificado'
        (self.reg / 'nights').mkdir(parents=True); (self.reg / 'jobs').mkdir()
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start(); self.addCleanup(patcher.stop)
        os.environ.pop('HOSHINO_LAB_HOME', None)
        self.inicio = time.time() + 3600; self.fim = self.inicio + 13 * 3600

    def agenda(self, estado):
        (self.reg / 'nights/scheduled-once.json').write_text(json.dumps(
            {'id': 'x', 'state': estado, 'plan': {'starts_at': self.inicio, 'ends_at': self.fim}}))

    def test_sem_laboratorio_ou_sem_nada_agendado_libera(self):
        self.assertEqual(b.motivo(self.root / 'outro'), '')
        self.assertEqual(b.motivo(self.root), '')

    def test_janela_agendada_bloqueia_desde_a_antecedencia_ate_o_fim(self):
        self.agenda('scheduled')
        self.assertEqual(b.motivo(self.root, now=self.inicio - b.ANTECEDENCIA_S - 60), '')
        self.assertIn('bloqueadas desde', b.motivo(self.root, now=self.inicio - b.ANTECEDENCIA_S + 60))
        self.assertTrue(b.motivo(self.root, now=self.fim - 1))
        self.assertEqual(b.motivo(self.root, now=self.fim + 1), '')

    def test_agenda_perdida_cancelada_ou_encerrada_nao_bloqueia(self):
        for estado in ('blocked', 'cancelled', 'finished'):
            self.agenda(estado)
            self.assertEqual(b.motivo(self.root, now=self.inicio + 60), '', estado)
        self.agenda('started')
        self.assertIn('em andamento', b.motivo(self.root, now=self.fim - 60))
        self.assertEqual(b.motivo(self.root, now=self.fim + 60), '')   # registro preso não bloqueia para sempre

    def test_sessao_noturna_ativa_e_jobs_de_treino_bloqueiam_mas_recuperacao_nao(self):
        (self.reg / 'nights/current.json').write_text(json.dumps({'id': 's', 'state': 'running'}))
        self.assertIn('sessão s', b.motivo(self.root))
        (self.reg / 'nights/current.json').write_text(json.dumps({'id': 's', 'state': 'completed'}))
        self.assertEqual(b.motivo(self.root), '')
        job = self.reg / 'jobs/j.json'
        job.write_text(json.dumps({'state': 'running', 'action': 'recover', 'model': 'qwen35-9b', 'entity': 'lilith'}))
        self.assertEqual(b.motivo(self.root), '')
        job.write_text(json.dumps({'state': 'running', 'action': 'train', 'model': 'qwen35-9b', 'entity': 'lilith'}))
        self.assertIn('train qwen35-9b/lilith', b.motivo(self.root))
        job.write_text(json.dumps({'state': 'completed', 'action': 'train'}))
        self.assertEqual(b.motivo(self.root), '')

    def test_arquivos_corrompidos_nao_quebram(self):
        (self.reg / 'nights/current.json').write_text('{lixo')
        (self.reg / 'nights/scheduled-once.json').write_text('[]')
        (self.reg / 'jobs/a.json').write_text('nada')
        self.assertEqual(b.motivo(self.root), '')

    def test_admissao_recusa_entidade_durante_treino(self):
        from core import entity_admission
        (self.reg / 'nights/current.json').write_text(json.dumps({'id': 's', 'state': 'running'}))
        with self.assertRaisesRegex(ValueError, 'Treino do laboratório em andamento'):
            with entity_admission.guard(self.root, 'lilith'):
                pass

    def test_home_do_laboratorio_por_ambiente(self):
        outro = self.root / 'lab'; (outro / 'controle-laboratorio/treinamento-unificado/nights').mkdir(parents=True)
        (outro / 'controle-laboratorio/treinamento-unificado/nights/current.json').write_text(
            json.dumps({'id': 'z', 'state': 'draining'}))
        with mock.patch.dict(os.environ, {'HOSHINO_LAB_HOME': str(outro)}):
            self.assertIn('sessão z', b.motivo(self.root))


if __name__ == '__main__':
    unittest.main()
