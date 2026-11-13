"""Senha, importância e reset: só fixtures, sem microfone/modelos reais."""
import contextlib
import json
import sqlite3
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import test_central_control as fixture
import test_central_refinamento as refinement
import test_limpeza_experiencia as cleanup_fixture
from core import central_control as cc,knowledge_editor as editor,memory_maintenance as mm


class MemoriasCartas(unittest.TestCase):
    PASSWORD='Cartas-fixture-123'
    def setUp(self):
        fixture.CentralControlTests.setUp(self)
        self.database=refinement.Refinamento.seed_logic(self)
        self.control.set_password(dict(password=self.PASSWORD,password_confirm=self.PASSWORD))
    def unlock(self,entity='hoshino'):
        return self.control.unlock_memories(dict(entity=entity,password=self.PASSWORD))['access_token']
    def create(self,title='Primeiro',entity='hoshino'):
        self.control.save_knowledge(dict(entity=entity,action='create',title=title,kind='concept',content='Conteúdo atribuído: '+title))
        return next(c for c in self.control.knowledge(entity,{})['items'] if c['title']==title)
    def importance(self,card,level):
        return dict(entity=card['entity'],action='importance',card_id=card['id'],card_revision=card['card_revision'],importance=level)

    def test_password_required_scoped_and_not_stored_as_plaintext(self):
        with self.assertRaises(PermissionError):self.control.require_memories('hoshino','')
        with self.assertRaises(ValueError):self.control.unlock_memories(dict(entity='hoshino',password='errada'))
        token=self.unlock();self.control.require_memories('hoshino',token)
        with self.assertRaises(PermissionError):self.control.require_memories('lilith',token)
        self.assertNotIn(token,str(self.control.memory_grants));self.assertNotIn(self.PASSWORD,str(self.control.memory_grants))
        self.control.lock_memories('hoshino',token)
        with self.assertRaises(PermissionError):self.control.require_memories('hoshino',token)
    def test_expiration_password_change_and_backend_restart_revoke_grants(self):
        token=self.unlock()
        with patch.object(cc.time,'monotonic',return_value=10**12):
            with self.assertRaises(PermissionError):self.control.require_memories('hoshino',token)
        token=self.unlock()
        self.control.set_password(dict(old_password=self.PASSWORD,password='Outra-fixture-123',password_confirm='Outra-fixture-123'))
        with self.assertRaises(PermissionError):self.control.require_memories('hoshino',token)
        fresh=cc.Control(self.root,self.supervisor,self.audio)
        with self.assertRaises(PermissionError):fresh.require_memories('hoshino',token)

    def test_http_enforces_read_write_and_no_inspector_bypass(self):
        card=self.create('SEMANTIC_SENTINEL')
        server,token=fixture.launcher.make_server(self.supervisor,0,self.audio)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}/api/'
        def request(path,data=None,access='',auth=True):
            headers={'Content-Type':'application/json'}
            if auth:headers['Authorization']='Bearer '+token
            if access:headers['X-Memory-Access']=access
            with urlopen(Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers),timeout=5) as response:return json.load(response)
        try:
            for path in ('control/knowledge?entity=hoshino','control/logic?entity=hoshino','control/memory?entity=hoshino'):
                with self.subTest(path=path),self.assertRaises(HTTPError) as denied:request(path)
                self.assertEqual(denied.exception.code,403)
            chat=request('control/memory?entity=hoshino&scope=chat')
            self.assertNotIn('SEMANTIC_SENTINEL',json.dumps(chat))
            data=self.importance(card,'diamante')
            with self.assertRaises(HTTPError) as denied:request('control/knowledge',data)
            self.assertEqual(denied.exception.code,403)
            access=request('control/knowledge/unlock',dict(entity='hoshino',password=self.PASSWORD))['access_token']
            out=request('control/knowledge?entity=hoshino',access=access);self.assertIn('SEMANTIC_SENTINEL',str(out))
            self.assertTrue(request('control/knowledge',data,access=access)['verified'])
            with self.assertRaises(HTTPError):request('control/knowledge?entity=lilith',access=access)
            request('control/knowledge/lock',dict(entity='hoshino'),access=access)
            with self.assertRaises(HTTPError):request('control/knowledge?entity=hoshino',access=access)
            with self.assertRaises(HTTPError):request('control/knowledge/unlock',dict(entity='hoshino',password=self.PASSWORD),auth=False)
        finally:server.shutdown();server.server_close();thread.join(5)

    def test_default_ferro_read_only_and_all_four_levels_persist(self):
        card=self.create();before=self.database.read_bytes()
        self.assertEqual(card['importance'],'ferro');self.control.knowledge('hoshino',{})
        self.assertEqual(self.database.read_bytes(),before)
        for level in editor.TIERS:
            card=next(c for c in self.control.knowledge('hoshino',{})['items'] if c['id']==card['id'])
            record=card['entries'][0];fields_before=record['fields'];revision_before=record['revision']
            out=self.control.save_knowledge(self.importance(card,level));self.assertTrue(out['verified'])
            self.assertFalse(out['confidence_changed']);self.assertTrue((Path(out['backup'])/self.database.name).is_file())
            loaded=next(c for c in cc.Control(self.root,self.supervisor,self.audio).knowledge('hoshino',{})['items'] if c['id']==card['id'])
            self.assertEqual(loaded['importance'],level);self.assertEqual(loaded['entries'][0]['fields'],fields_before)
            self.assertEqual(loaded['entries'][0]['revision'],revision_before)
    def test_rank_order_stale_version_invalid_level_and_entity_isolation(self):
        other=refinement.Refinamento.seed_logic(self,'lilith');other_before=other.read_bytes()
        low=self.create('Abaixo');high=self.create('Acima')
        for bad in ('platina',None,True):  # 07/11: a platina saiu; bronze é nível válido
            with self.assertRaises(ValueError):self.control.save_knowledge(self.importance(high,bad))
        with self.assertRaises(ValueError):self.control.save_knowledge(self.importance(high,'ouro')|dict(card_id=None))
        self.control.save_knowledge(self.importance(high,'diamante'))
        with self.assertRaises(ValueError):self.control.save_knowledge(self.importance(high,'ouro'))
        self.assertEqual(self.control.knowledge('hoshino',{})['items'][0]['id'],high['id'])
        self.assertEqual(other.read_bytes(),other_before)

    def test_delete_card_also_removes_its_importance(self):
        card=self.create();self.control.save_knowledge(self.importance(card,'diamante'))
        card=self.control.knowledge('hoshino',{'id':card['id']})['items'][0]
        targets=[dict(table=r['table'],id=r['record_id'],revision=r['revision']) for r in card['entries']]
        self.control.save_knowledge(dict(entity='hoshino',action='delete',confirm=True,password=self.PASSWORD,records=targets,card_id=card['id'],card_revision=card['card_revision']))
        self.assertEqual(self.control.knowledge('hoshino',{'id':card['id']})['items'],[])
        self.assertNotIn(card['id'],editor.tiers(self.database))

    def test_full_cleanup_preserves_tastes_preferences_and_emotional_state_not_defaults(self):
        paths,*_=cleanup_fixture.LimpezaExperiencia.seed(self,'alistair')
        state=paths.runtime/'estado_mente.json'
        emotions={'alegria':{'i':.8,'motivo':'Fixture','em':'2026-10-20T12:00:00Z'}}
        state.write_text(json.dumps(dict(humor=.6,emocoes=emotions,activity_context={'old':'chat'})))
        identity=paths.identity/'self_model.json';identity.write_text(json.dumps(dict(personality={'preferences':['Prefiro enigmas']},self_concept='Fixture preservada')));identity_before=identity.read_bytes()
        with contextlib.closing(sqlite3.connect(mm.db_path(paths))) as db,db:
            db.execute("INSERT INTO emotion_log(id,emocao,intensidade) VALUES('emotion','alegria',.8)")
            db.execute("INSERT INTO memory_card_settings VALUES('concept:fixture','diamante','2026-10-20')")
        data=dict(entity='alistair',all=True,targets=[]);preview=self.control.memory_preview(data)
        with patch.object(mm,'remove_vectors',return_value=0):
            result=self.control.delete_memory(data|dict(scope=preview['scope'],fingerprint=preview['fingerprint'],password=self.PASSWORD,confirm=True,request_id='memory-'+uuid.uuid4().hex))
        self.assertTrue(result['verified']);self.assertEqual(identity.read_bytes(),identity_before)
        self.assertEqual(json.loads(state.read_text()),dict(humor=.6,emocoes=emotions))
        with contextlib.closing(sqlite3.connect(mm.db_path(paths))) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tastes').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT valor FROM traits WHERE nome='serenidade'").fetchone()[0],.7)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM emotion_log').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memory_card_settings').fetchone()[0],0)


if __name__=='__main__':unittest.main()
