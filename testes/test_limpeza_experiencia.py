"""Limpeza explícita completa: somente fixtures sob executar_isolado.py."""
import os
if os.environ.get('HOSHINO_TEST_OFFLINE')!='1':
    raise SystemExit('Use testes/executar_isolado.py; nunca bancos reais.')
import contextlib
import json
import sqlite3
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import test_central_control as fixture
from core import memory_maintenance as mm, interentity as bus, job_bus


class LimpezaExperiencia(unittest.TestCase):
    def setUp(self):
        fixture.CentralControlTests.setUp(self)
        self.control.set_password({'password':'Senha-fixture-123','password_confirm':'Senha-fixture-123'})

    def seed(self,entity='alistair'):
        from memory.sqlite import init_db
        paths=self.control.paths(entity);mind=mm.db_path(paths)
        with patch.object(init_db,'DB_PATH',str(mind)):init_db.init_database(verbose=False)
        with contextlib.closing(sqlite3.connect(mind))as db,db:
            db.execute("INSERT INTO memories(id,type,content,created_at) VALUES('m','fato_informado','EXPERIENCIA_FIXTURE','2026-10-19')")
            db.execute("INSERT INTO people(id,nome) VALUES('p','Pessoa fixture')")
            db.execute("INSERT INTO properties(id,entity,chave,valor) VALUES('pr','Objeto fixture','cor','azul')")
            db.execute("INSERT INTO facts VALUES('f','Conhecimento fixture',.8)")
            db.execute("INSERT OR REPLACE INTO traits(nome,valor) VALUES('serenidade',.7)")
            db.execute("INSERT INTO tastes(id,objeto,valencia) VALUES('g','chá',.5)")
            db.execute("CREATE TABLE alistair_turns(source_id TEXT PRIMARY KEY,sender TEXT,input TEXT,output TEXT,created_at REAL)")
            db.execute("INSERT INTO alistair_turns VALUES('turn','usuario','Pergunta','Resposta',1)")
            db.execute("CREATE TABLE alistair_actions(id TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT)")
            db.executemany('INSERT INTO alistair_actions VALUES(?,?,?)',[
                ('effect','digest-effect',json.dumps({'id':'receipt','text':'PRIVATE_COPY','ok':True})),
                ('uncertain','digest-uncertain',None),
                ('dialogue-task:task','digest-task',json.dumps({'schema':1,'state':'waiting_presence','intro_args':{'texto':'PRIVATE_INTRO'},'receipt':{'id':'receipt'}}))])
        history=paths.runtime/'history.sqlite3'
        with contextlib.closing(sqlite3.connect(history))as db,db:
            db.execute('CREATE TABLE messages(id TEXT PRIMARY KEY,content TEXT)')
            db.execute('CREATE VIRTUAL TABLE messages_fts USING fts5(id UNINDEXED,content)')
            db.execute("INSERT INTO messages VALUES('local','HISTORICO_FIXTURE')")
            db.execute("INSERT INTO messages_fts VALUES('local','HISTORICO_FIXTURE')")
            db.execute("INSERT INTO messages_fts VALUES('orphan','HISTORICO_ORFAO_FIXTURE')")
            db.execute('CREATE TABLE events(id TEXT PRIMARY KEY,kind TEXT)')
            db.execute("INSERT INTO events VALUES('audit','diagnostic')")
        (paths.runtime/'event_log').mkdir()
        (paths.runtime/'event_log/test.jsonl').write_text('{"fixture":"EXPERIENCIA_FIXTURE"}\n')
        (paths.runtime/'reflexao_noturna_pendente.json').write_text('{"fixture":true}')
        (paths.runtime/'estado_mente.json').write_text(json.dumps({'humor':.6,'activity_context':{'old':'chat'},
            'autonomous_activity':{'objetivo':'experiência descartável','proximo_passo':'não recuperar após limpeza'}}))
        selected=bus.send('usuario',entity,'CHAT_FIXTURE')
        peer=bus.send(entity,'lilith'if entity!='lilith'else'hoshino','APRESENTACAO_FIXTURE',wake=True)
        other=bus.send('usuario','hoshino'if entity!='hoshino'else'lilith','OUTRA_ENTIDADE_FIXTURE')
        return paths,selected,peer,other

    def payload(self,entity='alistair'):
        data={'entity':entity,'all':True,'targets':[]}
        preview=self.control.memory_preview(data)
        return data|{'scope':preview['scope'],'fingerprint':preview['fingerprint'],
            'password':'Senha-fixture-123','confirm':True,'request_id':'memory-'+uuid.uuid4().hex}

    def test_full_cleanup_removes_active_experience_preserves_identity_audit_and_receipts(self):
        paths,selected,peer,other=self.seed();other_mind=mm.db_path(self.control.paths('hoshino'))
        other_mind.write_bytes(b'OTHER_ENTITY_UNTOUCHED');before=other_mind.read_bytes()
        data=self.payload()
        with patch.object(mm,'remove_vectors',return_value=3):result=self.control.delete_memory(data)
        self.assertTrue(result['verified']);self.assertTrue(result['chat_cleared']);self.assertTrue(result['knowledge_cleared'])
        self.assertEqual(other_mind.read_bytes(),before)
        with contextlib.closing(sqlite3.connect(mm.db_path(paths)))as db:
            for table in mm.EXPERIENCE_TABLES:
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0],0,table)
            self.assertEqual(db.execute('SELECT valor FROM traits WHERE nome=?',('serenidade',)).fetchone()[0],.7)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tastes').fetchone()[0],1)
            actions={r[0]:r[1:]for r in db.execute('SELECT * FROM alistair_actions')}
            self.assertEqual(actions['uncertain'],('digest-uncertain',None))
            self.assertEqual(json.loads(actions['effect'][1]),{'id':'receipt','ok':True})
            task=json.loads(actions['dialogue-task:task'][1]);self.assertEqual(task['state'],'cancelled');self.assertIsNone(task['intro_args'])
            self.assertEqual(task['receipt'],{'id':'receipt'})
        with contextlib.closing(sqlite3.connect(bus.DB_PATH))as db:
            self.assertEqual(db.execute('SELECT text,kind FROM entity_messages WHERE id=?',(selected['id'],)).fetchone(),('','deleted'))
            self.assertEqual(db.execute('SELECT text,kind FROM entity_messages WHERE id=?',(other['id'],)).fetchone(),('OUTRA_ENTIDADE_FIXTURE','chat'))
            self.assertIsNotNone(db.execute('SELECT consumed_at FROM wake_requests WHERE message_id=?',(peer['id'],)).fetchone()[0])
        with contextlib.closing(sqlite3.connect(paths.runtime/'history.sqlite3'))as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM messages_fts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT * FROM events').fetchall(),[('audit','diagnostic')])
        self.assertEqual(json.loads((paths.runtime/'estado_mente.json').read_text()),{'humor':.6})
        self.assertFalse((paths.runtime/'event_log/test.jsonl').exists())
        backup=Path(result['backup']);self.assertTrue((backup/'runtime/event_log/test.jsonl').exists())
        with contextlib.closing(sqlite3.connect(backup/'mind.sqlite3'))as db:
            self.assertEqual(db.execute('SELECT content FROM memories').fetchone()[0],'EXPERIENCIA_FIXTURE')
        self.assertEqual((backup/'manifest.json').stat().st_mode&0o777,0o600)
        with patch.object(mm,'delete',side_effect=AssertionError('no replay')):
            self.assertEqual(self.control.delete_memory(data),result)

    def test_full_cleanup_requires_new_scope_preview_and_all_peers_idle(self):
        self.seed();data=self.payload()
        with self.assertRaisesRegex(ValueError,'nova prévia'):self.control.delete_memory(data|{'scope':None})
        bus.register('lilith',status='awake')
        with patch.object(mm,'delete')as delete:
            with self.assertRaises(ValueError):self.control.delete_memory(data)
            delete.assert_not_called()

    def test_chat_change_invalidates_preview_before_effect(self):
        paths,*_=self.seed();data=self.payload();before=mm.db_path(paths).read_bytes()
        bus.send('usuario','alistair','NOVA MENSAGEM')
        with patch.object(mm,'remove_vectors')as remove:
            with self.assertRaisesRegex(ValueError,'mudaram'):self.control.delete_memory(data)
            remove.assert_not_called()
        self.assertEqual(mm.db_path(paths).read_bytes(),before)

    def test_backup_failure_changes_nothing_and_blocks_new_request_until_reconciled(self):
        paths,*_=self.seed();data=self.payload();before=mm.db_path(paths).read_bytes()
        with patch.object(mm.shutil,'copy2',side_effect=OSError('fixture backup failed')),patch.object(mm,'remove_vectors')as remove:
            with self.assertRaisesRegex(ValueError,'não confirmada'):self.control.delete_memory(data)
            remove.assert_not_called()
        self.assertEqual(mm.db_path(paths).read_bytes(),before)
        self.assertEqual(job_bus.get(data['request_id'])['details']['outcome'],'uncertain')
        with self.assertRaisesRegex(ValueError,'anterior incerta'):self.control.delete_memory(self.payload())

    def test_symlink_source_refused_without_touching_target(self):
        paths,*_=self.seed();target=paths.runtime/'event_log/test.jsonl';target.unlink()
        external=self.root/'external.jsonl';external.write_text('PRESERVE')
        target.symlink_to(external)
        with self.assertRaises(ValueError):self.payload()
        self.assertEqual(external.read_text(),'PRESERVE')

    def test_uncertain_cleanup_outside_ui_window_still_blocks_without_outcome_field(self):
        self.seed();identifier='memory-'+uuid.uuid4().hex
        job_bus.publish(identifier,'alistair','running',kind='memory_maintenance',scope=mm.EXPERIENCE_SCOPE)
        job_bus.publish(identifier,'alistair','interrupted',kind='memory_maintenance')
        for index in range(205):job_bus.publish('newer-fixture-'+str(index),'hoshino','done',kind='fixture')
        self.assertNotIn(identifier,[j['id']for j in job_bus.status(limit=200)])
        with patch.object(mm,'delete')as delete:
            with self.assertRaisesRegex(ValueError,'anterior incerta'):self.control.delete_memory(self.payload())
            delete.assert_not_called()

    def test_bus_only_entity_without_mind_db_can_clear_chat(self):
        message=bus.send('usuario','alistair','FIXTURE SEM BANCO MENTAL')
        with patch.object(mm,'remove_vectors',return_value=0):result=self.control.delete_memory(self.payload())
        self.assertTrue(result['chat_cleared']);self.assertFalse(mm.db_path(self.control.paths('alistair')).exists())
        with contextlib.closing(sqlite3.connect(bus.DB_PATH))as db:
            self.assertEqual(db.execute('SELECT kind FROM entity_messages WHERE id=?',(message['id'],)).fetchone()[0],'deleted')


if __name__=='__main__':unittest.main()
