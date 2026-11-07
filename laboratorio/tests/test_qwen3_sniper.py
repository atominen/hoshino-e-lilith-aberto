"""Contrato de aquisição do candidato podado, sem rede/modelos/hardware reais."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

from laboratorio import candidatos
from laboratorio.catalogo import BY_ID
from laboratorio.experimentos import clean_params
from scripts.testar_qwen3_6b_sniper import observed_swap,generation_options


class SniperCandidateTests(unittest.TestCase):
    def test_dead_child_does_not_mask_exit_with_missing_swap(self):
        dead=types.SimpleNamespace(pid=123,poll=lambda:1)
        absent=Mock(side_effect=RuntimeError('VmSwap ausente'))
        self.assertIsNone(observed_swap(dead,absent))
        finishing=types.SimpleNamespace(pid=123,poll=lambda:None,wait=Mock(return_value=1))
        self.assertIsNone(observed_swap(finishing,absent))
        finishing.wait.assert_called_once_with(timeout=.2)
        alive=types.SimpleNamespace(pid=123,poll=lambda:None,
            wait=Mock(side_effect=subprocess.TimeoutExpired('fixture',.2)))
        with self.assertRaises(RuntimeError):observed_swap(alive,absent)

    def test_qwen_sampling_is_explicit_not_a_hidden_budget_increase(self):
        options=generation_options('qwen')
        self.assertEqual(options,dict(do_sample=True,temperature=.7,top_p=.8,top_k=20,min_p=0.))
        self.assertNotIn('max_new_tokens',options)
        with self.assertRaises(ValueError):generation_options('unknown')

    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.home=Path(folder.name);self.root=self.home/'hf'
        self.root.mkdir()
        self.hub=types.ModuleType('huggingface_hub')
        self.hub.model_info=Mock(side_effect=AssertionError('Revisão pinada não consulta main'))
        def snapshot(**kwargs):
            (self.root/'config.json').write_text('{}')
            (self.root/'model.safetensors').write_bytes(b'x'*8192)
            (self.root/'modeling_pruned.py').write_bytes(b'# audited fixture\n')
        self.hub.snapshot_download=Mock(side_effect=snapshot)

    def test_pinned_revision_and_only_explicit_code_file(self):
        expected=hashlib.sha256(b'# audited fixture\n').hexdigest()
        with patch.dict(sys.modules,{'huggingface_hub':self.hub}):
            candidatos._perform_download(self.root,'owner/model',revision='d'*40,
                source_files={'modeling_pruned.py':expected})
        self.hub.model_info.assert_not_called()
        kwargs=self.hub.snapshot_download.call_args.kwargs
        self.assertEqual(kwargs['revision'],'d'*40)
        self.assertIn('modeling_pruned.py',kwargs['allow_patterns'])
        self.assertNotIn('*.py',kwargs['allow_patterns'])
        self.assertTrue(candidatos.validate_local(self.root,'owner/model'))

    def test_wrong_hash_never_marks_installed(self):
        with patch.dict(sys.modules,{'huggingface_hub':self.hub}):
            with self.assertRaisesRegex(RuntimeError,'SHA256 divergente'):
                candidatos._perform_download(self.root,'owner/model',revision='d'*40,
                    source_files={'modeling_pruned.py':'0'*64})
        self.assertFalse((self.root/'lab_revision.json').exists())
        self.assertFalse(candidatos.validate_local(self.root))

    def test_mutable_revision_or_path_escape_refused_before_download(self):
        with patch.dict(sys.modules,{'huggingface_hub':self.hub}):
            with self.assertRaises(RuntimeError):
                candidatos._perform_download(self.root,'owner/model',revision='main')
            with self.assertRaises(ValueError):
                candidatos._perform_download(self.root,'owner/model',revision='d'*40,
                    source_files={'../foreign.py':'0'*64})
        self.hub.snapshot_download.assert_not_called()

    def test_research_candidate_cannot_enter_training(self):
        model=BY_ID['qwen3-6b-sniper']
        self.assertEqual(model['size'],'6B')
        self.assertEqual(model['training'],'pesquisa')
        self.assertEqual(model['repo'],'parmanu-lcs2/Qwen3-6B')
        root=candidatos.model_root(self.home,model['id']);root.mkdir(parents=True)
        (root/'config.json').write_text('{}')
        (root/'model.safetensors').write_bytes(b'x'*8192)
        (root/'lab_revision.json').write_text(json.dumps(dict(repo=model['repo'],revision=model['revision'])))
        with patch('laboratorio.experimentos.allowed_data',return_value=[dict(id='fixture')]):
            with self.assertRaisesRegex(ValueError,'trein'):
                clean_params(dict(model=model['id'],operation='train',dataset='fixture'),self.home)


if __name__=='__main__':unittest.main()
