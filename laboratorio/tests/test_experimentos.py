import json
import sys
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from laboratorio.catalogo import MODELS,BY_ID
from laboratorio.candidatos import installed_models,validate_local,model_root
from laboratorio.experimentos import (clean_params,inspect_plan,allowed_data,import_dataset,
                                      read_jobs,create_job,job_info,cancel_job,gate_9b)

class ExperimentosTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.home=Path(t.name)
        d=self.home/'pacote_identidade_v6';d.mkdir(exist_ok=True)
        records=[{'messages':[{'role':'user','content':f'Pergunta {i}'},{'role':'assistant','content':f'Resposta {i}'}]} for i in range(4)]
        self.lines=[json.dumps(x,ensure_ascii=False) for x in records]
        (d/'hoshino_train.jsonl').write_text('\n'.join(self.lines[:2]))
        (d/'hoshino_validation.jsonl').write_text('\n'.join(self.lines[2:]))

    def install_fake(self,model_id):
        root=model_root(self.home,model_id);root.mkdir(parents=True)
        (root/'config.json').write_text('{}')
        (root/'model.safetensors').write_bytes(b'x'*8192)
        (root/'lab_revision.json').write_text(json.dumps({'repo':BY_ID[model_id]['repo'],'revision':'a'*40}))
        return root

    def test_reject_partials_until_marker(self):
        root=model_root(self.home,'qwen3-8b');root.mkdir(parents=True)
        (root/'config.json').write_text('{}')
        (root/'model.safetensors').write_bytes(b'x'*8192)
        self.assertFalse(validate_local(root,BY_ID['qwen3-8b']['repo']))
        self.assertEqual(installed_models(self.home),[])
        with self.assertRaises(ValueError):clean_params({'model':'qwen3-8b','operation':'train','dataset':'pacote_identidade_v6:hoshino'},self.home)

    def test_unknown_downloaded_inventory_read_only(self):
        root=self.home/'modelos-extras'/'outro-modelo'/'hf';root.mkdir(parents=True)
        (root/'config.json').write_text('{}')
        (root/'model.safetensors').write_bytes(b'x'*8192)
        (root/'lab_revision.json').write_text(json.dumps({'repo':'usuario/ModeloVerificado','revision':'b'*40}))
        registered=installed_models(self.home)
        self.assertEqual(len(registered),1)
        self.assertEqual(registered[0]['training'],'pesquisa')
        with self.assertRaises(ValueError):clean_params({'model':'outro-modelo','operation':'train'},self.home)

    def test_exactly_30m_cycle(self):
        self.install_fake('qwen3-8b')
        with self.assertRaises(ValueError):clean_params({'model':'qwen3-8b','operation':'cycle_30m','dataset':'pacote_identidade_v6:hoshino','minutes':15},self.home)
        params=clean_params({'model':'qwen3-8b','operation':'cycle_30m','dataset':'pacote_identidade_v6:hoshino','minutes':30},self.home)
        self.assertEqual(params['minutes'],30)
        self.assertEqual(params['entity'],'hoshino')

    def test_catalog_models_real(self):
        self.assertEqual(len(MODELS),5)
        self.assertTrue(all(m['thinking'] and m['thinking_toggle'] for m in MODELS if m['size'] in ('7B','8B')))
        self.assertFalse(BY_ID['yi15-6b']['thinking'])
        self.assertEqual(set(BY_ID),{'qwen3-6b-sniper','qwen3-4b','qwen3-8b','hunyuan-7b','yi15-6b'})
        self.assertTrue(BY_ID['yi15-6b']['retired'])
        self.assertEqual(BY_ID['qwen3-4b']['repo'],'Qwen/Qwen3-4B')
        self.assertEqual(BY_ID['qwen3-6b-sniper']['training'],'pesquisa')
        self.assertEqual(BY_ID['qwen3-6b-sniper']['revision'],'d6990725bfc555b09e1c1b76bd07cd0dcaf7aceb')
        self.assertEqual(installed_models(self.home),[])

    def test_select_existing_pair(self):
        ds=allowed_data(self.home)
        self.assertEqual(len(ds),1)
        root=self.install_fake('qwen3-8b')
        p=clean_params({'model':'qwen3-8b','operation':'train','dataset':ds[0]['id'],'minutes':15},self.home)
        self.assertEqual(p['minutes'],15)
        self.assertEqual(inspect_plan(p,self.home)['files_safetensors'],1)
        self.assertEqual(installed_models(self.home)[0]['id'],'qwen3-8b')

    def test_guard_vision_not_training(self):
        with self.assertRaises(ValueError):
            clean_params({'model':'qwen25-vl-7b','operation':'train','dataset':'pacote_identidade_v6:hoshino'},self.home)
        with self.assertRaises(ValueError):
            clean_params({'model':'yi-vl-6b','operation':'ollama_test'},self.home)

    def test_no_cross_entity_corpus(self):
        self.install_fake('qwen3-8b')
        with self.assertRaises(ValueError):
            clean_params({'model':'qwen3-8b','operation':'train','dataset':'pacote_identidade_v6:hoshino','entity':'lilith'},self.home)

    def test_invalid_model_and_time(self):
        with self.assertRaises(ValueError):clean_params({'model':'invalid/path','operation':'download'},self.home)
        self.install_fake('qwen3-8b')
        with self.assertRaises(ValueError):clean_params({'model':'qwen3-8b','operation':'train','dataset':'../../etc/passwd'},self.home)
        with self.assertRaises(ValueError):clean_params({'model':'qwen3-8b','operation':'train','dataset':'pacote_identidade_v6:hoshino','minutes':300},self.home)

    def test_upload_valid_jsonl(self):
        d=import_dataset(self.home,'\n'.join(self.lines[:2]),'\n'.join(self.lines[2:]))
        self.assertEqual((d['train_rows'],d['validation_rows']),(2,2))
        self.assertTrue(any(x['id']==d['id'] for x in allowed_data(self.home)))

    def test_upload_overlap_bad_json(self):
        with self.assertRaises(ValueError):import_dataset(self.home,self.lines[0]+'\n'+self.lines[1],self.lines[0]+'\n'+self.lines[1])
        with self.assertRaises(ValueError):import_dataset(self.home,'not_json','not_json')

    def test_no_heavy_job_in_9b_window(self):
        schedule=self.home/'controle-laboratorio/agendamento.json';schedule.parent.mkdir(parents=True)
        schedule.write_text(json.dumps({'at':(datetime.now()+timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')}))
        with self.assertRaises(RuntimeError):gate_9b(self.home,'train')
        with self.assertRaises(RuntimeError):gate_9b(self.home,'ollama_test')

    def test_no_implicit_execution(self):
        self.assertEqual(read_jobs(self.home),[])
        self.assertFalse((self.home/'modelos-extras').exists())

if __name__=='__main__':unittest.main()
