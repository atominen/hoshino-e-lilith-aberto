import json
import tempfile
import unittest
from pathlib import Path

from laboratorio.professor_schema import read_snapshot,validate_plan
from laboratorio.alistair import generate_seed,paths,REPO as ALISTAIR_REPO
from laboratorio.professor import verify_model,REPO,FILE

class TeacherContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.snap=self.root/'conversas.jsonl'
        self.snap.write_text('\n'.join(json.dumps({'entity':'alistair','source_id':f'chat:20261011:{i:04d}',
          'messages':[{'role':'user','content':f'Pedido {i}'},{'role':'assistant','content':'Resposta sem comprovação'}]}) for i in range(3)))
    def test_snapshot_and_pinned_hash(self):
        rows,sha=read_snapshot(self.snap,'alistair')
        self.assertEqual(len(rows),3);self.assertEqual(len(sha),64)
        self.assertFalse(verify_model(self.root))
        self.assertEqual(ALISTAIR_REPO,'Qwen/Qwen3.5-4B')
        self.assertIn('27B',FILE)
    def test_entity_isolation(self):
        with self.assertRaises(ValueError):read_snapshot(self.snap,'lilith')

    def test_snapshot_preserves_feedback_as_annotation_not_training_target(self):
        row=json.loads(self.snap.read_text().splitlines()[0])
        feedback=dict(schema=1,entity='alistair',message_id='msg-original',author='usuario',source='central_user_feedback',
            decision='disliked',note='Não invente lembranças.',at='2026-10-16T13:00:00Z',text_sha256='a'*64,
            revision='revision-1',turn_id='turn-1',purpose='quality_feedback_not_training_approval')
        row['human_feedback']=feedback;self.snap.write_text(json.dumps(row))
        rows,_=read_snapshot(self.snap,'alistair')
        self.assertEqual(rows[0]['human_feedback'],feedback)
        self.assertEqual(rows[0]['messages'],row['messages'])
        self.assertNotIn('Não invente lembranças.',json.dumps(rows[0]['messages'],ensure_ascii=False))
        for changes in ({'entity':'lilith'},{'purpose':'approved_training'},{'decision':'approved'},{'extra':'command'}):
            row['human_feedback']=feedback|changes;self.snap.write_text(json.dumps(row))
            with self.assertRaises(ValueError):read_snapshot(self.snap,'alistair')
    def test_unknown_evidence_denied(self):
        entry=self.plan();entry['examples'][0]['source_id']='fantasma:99'
        with self.assertRaises(ValueError):validate_plan(entry,entity='alistair',evidence_ids=self.ids())
    def test_unapproved_minutes_denied(self):
        entry=self.plan();entry['minutes']=600
        with self.assertRaises(ValueError):validate_plan(entry,entity='alistair',evidence_ids=self.ids())
    def test_unknown_field_denied(self):
        entry=self.plan();entry['shell_command']='sudo poweroff'
        with self.assertRaises(ValueError):validate_plan(entry,entity='alistair',evidence_ids=self.ids())
    def test_valid_proposal_not_executed(self):
        result=validate_plan(self.plan(),entity='alistair',evidence_ids=self.ids())
        self.assertEqual(result['status'],'PROPOSTA_NAO_APROVADA')
        self.assertEqual(len(result['examples']),2)
    def test_empty_skip(self):
        result=validate_plan({'entity':'alistair','profile':'nenhum','minutes':0,
            'reason':'Hoje não há material validado.','examples':[]},entity='alistair',evidence_ids=self.ids())
        self.assertEqual(result['minutes'],0)
    def test_wrong_roles(self):
        bad={'entity':'alistair','source_id':'chat:20261011:1','messages':[{'role':'tool','content':'a'},{'role':'assistant','content':'b'}]}
        self.snap.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):read_snapshot(self.snap,'alistair')
    def ids(self):return {f'chat:20261011:{i:04d}' for i in range(3)}
    def plan(self):
        return {'entity':'alistair','profile':'conservador','minutes':10,'reason':'Há erros verificáveis de confirmação.',
         'examples':[{'source_id':f'chat:20261011:{i:04d}','category':'instrucao','user':'Confirmação?',
          'assistant':'Aguardo recibo verificável.','reason':'Não inventar persistência','confidence':0.7} for i in range(2)]}

class AlistairSeedTests(unittest.TestCase):
    def test_split_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            generate_seed(home)
            _,_,ds=paths(home)
            val=[json.loads(x) for x in (ds/'alistair_validation.jsonl').read_text().splitlines()]
            train=[json.loads(x) for x in (ds/'alistair_train.jsonl').read_text().splitlines()]
            self.assertGreaterEqual(len(train),25);self.assertGreaterEqual(len(val),25)
            self.assertFalse({x['case'] for x in val}&{x['case'] for x in train})
            self.assertEqual(json.loads((ds/'recibo.json').read_text())['review_required'],True)
            with self.assertRaises(RuntimeError):generate_seed(home)

if __name__=='__main__':unittest.main()
