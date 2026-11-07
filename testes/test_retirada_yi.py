"""Retirada autorizada e substituto rápido: offline, sem pesos/rede/GPU reais."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from laboratorio import candidatos, trabalhador
from laboratorio.catalogo import BY_ID
from scripts import retirar_yi_20261024 as retirar
from scripts import retirar_qwen3_4b_20261024 as retirar_4b


class RetirementTests(unittest.TestCase):
    def test_discarded_4b_download_refused_before_network_or_path_work(self):
        with patch('laboratorio.experimentos.gate_9b') as gate:
            with self.assertRaisesRegex(ValueError,'retirado'):
                candidatos.download(Path('/missing'),'qwen3-4b')
            gate.assert_not_called()

    def test_old_worker_plan_cannot_reinstall_discarded_4b(self):
        with patch.object(trabalhador,'gate_9b') as gate:
            with self.assertRaisesRegex(ValueError,'retirado'):
                trabalhador.do_download(Path('/missing'),dict(model='qwen3-4b'))
            gate.assert_not_called()

    def test_yi_download_refused_before_any_network_or_path_work(self):
        with patch('laboratorio.experimentos.gate_9b') as gate:
            with self.assertRaisesRegex(ValueError,'retirado'):
                candidatos.download(Path('/does-not-exist'),'yi15-6b')
            gate.assert_not_called()

    def test_old_worker_download_plan_cannot_reinstall_yi(self):
        with patch.object(trabalhador,'gate_9b') as gate:
            with self.assertRaisesRegex(ValueError,'retirado'):
                trabalhador.do_download(Path('/does-not-exist'),dict(model='yi15-6b'))
            gate.assert_not_called()

    def test_4b_experiment_is_not_the_hl_replacement_or_alistair(self):
        candidate=BY_ID['qwen3-4b']
        self.assertFalse(candidate['replacement_eligible'])
        self.assertTrue(candidate['experimental_only'])
        self.assertTrue(candidate['retired'])
        self.assertEqual(candidate['repo'],'Qwen/Qwen3-4B')
        self.assertEqual(candidate['training'],'texto_qlora')
        self.assertEqual(candidate['thinking_toggle'],'hard')
        self.assertNotIn('GGUF',candidate['repo'])
        self.assertNotIn('alistair',candidate['id'])

    def test_4b_removal_exact_target_never_alistair(self):
        self.assertEqual(retirar_4b.ALIAS,'hoshino-qwen3-4b-candidate-20261024')
        self.assertNotIn('3.5',retirar_4b.ALIAS)
        self.assertEqual(len(retirar_4b.SHARDS),3)
        self.assertNotIn('download_reference',dir(candidatos))

    def test_retirement_rejects_workspace_root_and_outside(self):
        with self.assertRaises(RuntimeError):retirar.safe(retirar.ROOT)
        with self.assertRaises(RuntimeError):retirar.safe(Path('/'))

    def test_retirement_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'target').mkdir();(root/'link').symlink_to(root/'target',target_is_directory=True)
            with patch.object(retirar,'ROOT',root):
                with self.assertRaises(RuntimeError):retirar.safe(root/'link'/'weight.gguf')
                self.assertEqual(retirar.safe(root/'target'/'weight.gguf'),root/'target'/'weight.gguf')


if __name__=='__main__':unittest.main()
