"""Salas, nomes por mente e cartões: somente bancos/transportes de fixture."""
import contextlib
import json
import sqlite3
import unittest
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import test_central_control as fixture
import test_central_refinamento as refinement
from core import interentity as bus,chat_identity as identity,job_bus


class ChatGlobal(unittest.TestCase):
    def setUp(self):fixture.CentralControlTests.setUp(self)
    seed_logic=refinement.Refinamento.seed_logic

    def awake(self,*names):
        for name in names:bus.register(name,'awake')

    def test_global_atomic_independent_delivery_no_wake_and_logical_timeline(self):
        self.awake('hoshino','lilith');bus.register('alistair','sleeping')
        accepted=bus.send_global('Uma frase para a sala.',submission_id='fixture-global-001')
        self.assertEqual(accepted['deliveries'],['hoshino','lilith']);self.assertFalse(bus.pending_wake_requests())
        h=bus.inbox('hoshino')[0];l=bus.inbox('lilith')[0]
        self.assertNotEqual(h['id'],l['id']);bus.processing_outcome(h['id'],'hoshino','answered')
        self.assertEqual(bus.inbox('hoshino'),[]);self.assertEqual(len(bus.inbox('lilith')),1);self.assertEqual(bus.inbox('alistair'),[])
        self.assertEqual(len(bus.daily_conversation('alistair',scope='global')['conversation']),1)
        self.assertEqual(bus.daily_conversation('hoshino',scope='direct')['conversation'],[])

    def test_retry_cannot_add_newly_awake_recipient_or_change_text(self):
        self.awake('hoshino');first=bus.send_global('Aceite único.',submission_id='fixture-global-002')
        self.awake('lilith');again=bus.send_global('Aceite único.',submission_id='fixture-global-002')
        self.assertTrue(again['deduplicated']);self.assertEqual(again['id'],first['id']);self.assertEqual(bus.inbox('lilith'),[])
        with self.assertRaises(ValueError):bus.send_global('Outro texto.',submission_id='fixture-global-002')

    def test_broadcast_failure_rolls_back_all_envelopes_and_receipts(self):
        self.awake('hoshino','lilith');original=bus.send
        def fail(sender,target,*args,**kwargs):
            if target=='lilith':raise RuntimeError('fixture disk failure')
            return original(sender,target,*args,**kwargs)
        with patch.object(bus,'send',side_effect=fail):
            with self.assertRaises(RuntimeError):bus.send_global('Não pode aceitar metade.',submission_id='fixture-global-003')
        self.assertEqual(bus.inbox('hoshino'),[]);self.assertEqual(bus.inbox('lilith'),[])
        with bus._transaction() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM notification_keys').fetchone()[0],0)

    def test_no_awake_is_explicit_no_message(self):
        with self.assertRaisesRegex(ValueError,'Nenhuma entidade'):bus.send_global('Olá.',submission_id='fixture-global-004')
        self.assertEqual(bus.user_conversation('hoshino'),[])

    def test_authenticated_http_global_delivers_to_all_awake_and_retry_is_once(self):
        server,token=fixture.launcher.make_server(self.supervisor,0,self.audio)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}/api/'
            def request(path,data=None,auth=True):
                headers={'Content-Type':'application/json'}
                if auth:headers['Authorization']='Bearer '+token
                with urlopen(Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers),timeout=5) as response:return json.load(response)
            data=dict(entity='hoshino',chat_scope='global',text='Olá sala.',submission_id='fixture-http-0001')
            with self.assertRaises(HTTPError) as denied:request('send',data,False)
            self.assertEqual(denied.exception.code,403)
            self.awake('hoshino','lilith','alistair');first=request('send',data);again=request('send',data)
            self.assertEqual(first['id'],again['id']);self.assertTrue(again['deduplicated'])
            self.assertEqual(len(first['deliveries']),3)
            room=request('state?entity=hoshino&daily=1&chat_scope=global')
            self.assertEqual(len(room['conversation']),1)
            for entity in ('hoshino','lilith','alistair'):self.assertEqual(len(bus.peek(entity)),1)
            self.assertEqual(request('state?entity=hoshino&daily=1&chat_scope=direct')['conversation'],[])
        finally:server.shutdown();server.server_close();thread.join(5)

    def test_alistair_public_recall_never_reads_direct_turn_text(self):
        from alistair_runner import recall_history
        secret=bus.send('usuario','alistair','DIRECT_NAME_SENTINEL')
        self.awake('alistair');public=bus.send_global('Meu nome é Lua.',submission_id='fixture-public-001')
        with contextlib.closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE alistair_turns(source_id TEXT,sender TEXT,input TEXT,output TEXT,created_at REAL)')
            db.executemany('INSERT INTO alistair_turns VALUES(?,?,?,?,?)',[(secret['id'],'usuario','DIRECT_NAME_SENTINEL','SECRET_REPLY',1),(public['id'],'usuario','Meu nome é Lua.','Olá Lua.',2)])
            recent,recalled,info=recall_history(db,'usuario','qual meu nome?',public_only=True)
            self.assertNotIn('DIRECT_NAME_SENTINEL',str((recent,recalled,info)));self.assertNotIn('SECRET_REPLY',str(recent));self.assertIn('Lua',str(recent))

    def test_room_has_all_entity_exchanges_and_no_direct_history(self):
        secret=bus.send('usuario','hoshino','DIRECT_SENTINEL')
        exchange=bus.send('lilith','alistair','Público entre entidades.',metadata={'private':True})
        self.awake('hoshino','alistair');bus.send_global('Oi sala.',submission_id='fixture-global-005')
        incoming=bus.inbox('hoshino')[-1]
        token=bus.processing_message.set(incoming)
        try:reply=bus.send('hoshino','usuario','Resposta pública.')
        finally:bus.processing_message.reset(token)
        room=bus.daily_conversation('lilith',scope='global')['conversation'];ids={r['id'] for r in room}
        self.assertIn(exchange['id'],ids);self.assertIn(reply['id'],ids);self.assertNotIn(secret['id'],ids)
        self.assertNotIn('DIRECT_SENTINEL',bus.room_context(incoming));self.assertIn('Público entre entidades',bus.room_context(incoming))
        self.assertNotIn('Oi sala.',bus.room_context(incoming))  # no duplicate copies of this input
        direct=bus.daily_conversation('hoshino',scope='direct')['conversation']
        self.assertEqual([r['id'] for r in direct],[secret['id']])

    def test_name_is_individual_updatable_attributed_and_not_an_os_name(self):
        paths={e:self.seed_logic(e) for e in ('hoshino','lilith','alistair')}
        self.assertEqual(identity.display_name(paths['hoshino']),'Usuário')
        self.assertFalse(identity.learn(paths['hoshino'],dict(sender='lilith',text='Me chamo Alex.')))
        self.assertFalse(identity.learn(paths['hoshino'],dict(sender='usuario',text='Você acha que meu nome é Alex?')))
        self.assertTrue(identity.learn(paths['hoshino'],dict(sender='usuario',text='Meu nome é Alex.')))
        self.assertTrue(identity.learn(paths['lilith'],dict(sender='usuario',text='Pode me chamar de Lua.')))
        self.assertEqual(identity.display_name(paths['hoshino']),'Alex');self.assertEqual(identity.display_name(paths['lilith']),'Lua')
        self.assertEqual(identity.display_name(paths['alistair']),'Usuário')
        identity.learn(paths['hoshino'],dict(sender='usuario',text='Agora, me chame de Sol.'))
        self.assertEqual(identity.display_name(paths['hoshino']),'Sol')
        self.assertEqual(self.supervisor.state('hoshino')['human_display_names'],dict(hoshino='Sol',lilith='Lua',alistair='Usuário'))

    def test_entity_chosen_nickname_is_own_scoped_and_never_an_authorization(self):
        path=self.seed_logic();other=self.seed_logic('lilith')
        incoming=bus.send('usuario','hoshino','Escolha um apelido.')
        token=bus.processing_message.set(incoming)
        try:
            with self.assertRaises(ValueError):identity.prefer(path,'Sol')
            identity.learn(path,dict(sender='usuario',text='Meu nome é Alex.'))
            result=identity.prefer(path,'Sol');self.assertTrue(result['verified']);self.assertFalse(result['authorization_changed'])
        finally:bus.processing_message.reset(token)

        self.assertEqual(identity.display_name(path),'Sol');self.assertEqual(identity.display_name(other),'Usuário')
        token=bus.processing_message.set(bus.send('lilith','hoshino','Troque o nome humano.'))
        try:
            with self.assertRaises(ValueError):identity.prefer(path,'Lua')
        finally:bus.processing_message.reset(token)

    def test_name_declaration_greetings_followup_and_questions(self):
        for text,expected in [('Oi, meu nome é Alex. Estou testando.','Alex'),('Meu nome e Lua e gosto de jogos.','Lua'),('Pode me chamar de Sol!','Sol'),('Você acha que meu nome é Sol?',''),('Imagine que meu nome é Lua.',''),('"Meu nome é Lua"','')]:
            with self.subTest(text=text):self.assertEqual(identity.explicit_name(text),expected)

    def test_cards_create_update_delete_backup_stale_guard_and_no_other_mind(self):
        path=self.seed_logic();other=self.seed_logic('lilith');before_other=other.read_bytes()
        self.control.set_password(dict(password='fixture-password-123',password_confirm='fixture-password-123'))
        self.control.save_knowledge(dict(entity='hoshino',action='create',title='Combinado',kind='rule',content='Pedir antes de abrir um jogo.'))
        card=self.control.knowledge('hoshino',{'type':'rule'})['items'][0];record=card['entries'][0]
        target=dict(table=record['table'],id=record['record_id'],revision=record['revision'])
        changed=self.control.save_knowledge(dict(entity='hoshino',action='update',records=[dict(target,fields={'content':'Não abrir jogos sozinho.'})]))
        self.assertTrue(changed['verified']);self.assertTrue((Path(changed['backup'])/path.name).is_file())
        with self.assertRaises(ValueError):self.control.save_knowledge(dict(entity='hoshino',action='delete',records=[target],confirm=True,password='fixture-password-123'))
        record=self.control.knowledge('hoshino',{'type':'rule'})['items'][0]['entries'][0]
        self.control.save_knowledge(dict(entity='hoshino',action='delete',confirm=True,password='fixture-password-123',records=[dict(table=record['table'],id=record['record_id'],revision=record['revision'])]))
        self.assertEqual(self.control.knowledge('hoshino',{'type':'rule'})['items'],[])
        self.assertEqual(other.read_bytes(),before_other)
        with contextlib.closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM episodes').fetchone()[0],1)

    def test_cards_reject_active_entities_protected_fields_and_private_diaries(self):
        self.seed_logic();self.awake('hoshino')
        data=dict(entity='hoshino',action='create',title='Manual',kind='manual',content='Instruções de um jogo, não permissões do PC.')
        with self.assertRaises(ValueError):self.control.save_knowledge(data)
        bus.register('hoshino','sleeping');self.control.save_knowledge(data)
        record=self.control.knowledge('hoshino',{'type':'manual'})['items'][0]['entries'][0]
        target=dict(table=record['table'],id=record['record_id'],revision=record['revision'])
        for fields in ({'source':'inventar origem'},{'type':'diario'},{'confidence':float('nan')}):
            with self.assertRaises(ValueError):self.control.save_knowledge(dict(entity='hoshino',action='update',records=[dict(target,fields=fields)]))
        with self.assertRaises(ValueError):self.control.save_knowledge(dict(entity='hoshino',action='delete',records=[target]))

    def test_only_two_microphone_modes_with_safe_legacy_read(self):
        self.assertEqual(self.control.microphone()['settings']['mode'],'command')
        for mode in ('manual','open'):
            path=self.root/'compartilhado/config/interface.json';path.write_text(json.dumps({'microphone':{'mode':mode}}))
            read=self.control.microphone();self.assertIn(read['settings']['mode'],('command','detection'))
            with self.assertRaises(ValueError):self.control.save_microphone(dict(revision=read['revision'],settings={'mode':mode}))
            self.control.save_microphone(dict(revision=read['revision'],settings={'mode':'detection'}))
        self.assertFalse(self.control.microphone()['settings']['auto_send'])

    def test_alistair_reads_own_editable_cards_without_history_or_other_minds(self):
        from core import knowledge_editor
        path=self.seed_logic('alistair');self.seed_logic('hoshino')
        for entity,content in (('alistair','A chave azul abre o portão.'),('hoshino','OTHER_MIND_SENTINEL')):
            self.control.save_knowledge(dict(entity=entity,action='create',kind='manual',title='Portão',content=content))
        text=knowledge_editor.context(path,'Como abrir o portão com a chave?')
        self.assertIn('A chave azul',text);self.assertNotIn('OTHER_MIND_SENTINEL',text)


if __name__=='__main__':unittest.main()
