"""Regressoes v0.5: recursos, contexto, isolamento e excecao 6B."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from laboratorio.recursos_professor import GIB,resource_plan,estimate_tokens,memory_bytes
from laboratorio.catalogo import BY_ID
from laboratorio.experimentos import allowed_data,clean_params
from laboratorio.candidatos import validate_local

class ResourcePolicyTests(unittest.TestCase):
    def test_context_grows_with_evidence(self):
        kw=dict(total=32*GIB,available=31*GIB,cpu_count=12,gpu_free=0)
        tiny=resource_plan(payload='a'*200,**kw)
        medium=resource_plan(payload='a'*11500,**kw)
        self.assertEqual(tiny['ctx'],4096)
        self.assertGreater(medium['ctx'],tiny['ctx'])
        self.assertEqual(tiny['threads'],10)
        self.assertEqual(tiny['gpu_layers'],0)
    def test_avoid_swap_and_excessive_context(self):
        kw=dict(total=32*GIB,available=18*GIB,cpu_count=12)
        with self.assertRaises(RuntimeError):resource_plan(payload='a'*200,**kw)
        with self.assertRaises(RuntimeError):resource_plan(payload='a'*180000,total=32*GIB,available=31*GIB,cpu_count=12)
    def test_gpu_only_when_vram_measured(self):
        kw=dict(payload='a'*200,total=32*GIB,available=30*GIB,cpu_count=12)
        self.assertEqual(resource_plan(**kw,gpu_free=6*GIB)['gpu_layers'],4)
        self.assertEqual(resource_plan(**kw,gpu_free=3*GIB)['gpu_layers'],0)
        self.assertEqual(resource_plan(**kw,gpu_free=6*GIB,gpu_layers='0')['gpu_layers'],0)
        with self.assertRaises(ValueError):resource_plan(**kw,gpu_layers='999')
    def test_memory_reading(self):
        total,avail=memory_bytes('MemTotal:    32768000 kB\nMemAvailable:   24576000 kB\n')
        self.assertLess(avail,total)

class SixBTests(unittest.TestCase):
    def test_only_sixb_exception_no_thinking(self):
        self.assertFalse(BY_ID['yi15-6b']['thinking'])
        self.assertTrue(BY_ID['hunyuan-7b']['thinking'])
        self.assertTrue(BY_ID['qwen3-8b']['thinking'])
        self.assertEqual(BY_ID['yi15-6b']['repo'],'01-ai/Yi-1.5-6B-Chat')
    def test_alistair_corpus_not_crossed(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);d=home/'pacote_identidade_v5';d.mkdir(exist_ok=True)
            (d/'alistair_train.jsonl').write_text('{"messages":[]}\n');(d/'alistair_validation.jsonl').write_text('{"messages":[]}\n')
            names={x['id'] for x in allowed_data(home)}
            self.assertIn('pacote_identidade_v5:alistair',names)
            import laboratorio.candidatos as ca
            with patch.object(ca,'validate_local',return_value=True):
                p=dict(model='yi15-6b',operation='cycle_30m',minutes=30,
                       dataset='pacote_identidade_v5:alistair',entity='alistair')
                self.assertEqual(clean_params(p,home)['entity'],'alistair')
                p['entity']='hoshino'
                with self.assertRaises(ValueError):clean_params(p,home)
    def test_6b_not_visible_until_download_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'config.json').write_text('{}')
            (root/'model.safetensors').write_bytes(b'0'*8000)
            self.assertFalse(validate_local(root,'01-ai/Yi-1.5-6B-Chat'))
            (root/'lab_revision.json').write_text(json.dumps({'repo':'01-ai/Yi-1.5-6B-Chat','revision':'a'*40}))
            self.assertTrue(validate_local(root,'01-ai/Yi-1.5-6B-Chat'))

if __name__=='__main__':unittest.main()

class PilotPlanTests(unittest.TestCase):
    def test_no_automatic_download_or_training(self):
        from laboratorio.pilotos import plan
        with tempfile.TemporaryDirectory() as temp:
            x=plan(Path(temp),'alistair')
            self.assertFalse(x['ready_to_run'])
            self.assertFalse(x['will_download'])
            self.assertFalse(x['will_change_production'])
    def test_requires_explicit_student(self):
        from laboratorio.pilotos import plan
        with self.assertRaises(ValueError):plan(Path('/tmp'),'unknown')
