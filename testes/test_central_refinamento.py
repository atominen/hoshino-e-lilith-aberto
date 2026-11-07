"""Refinamento: fixtures, sem quota/captura/entidades/bancos mentais reais."""
import array
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'));sys.path.insert(0,str(ROOT/'app/ui'))
import test_central_control as fixture
from core import central_control as cc, memory_maintenance as mm, ui_policy, interentity as bus, job_bus
from native_audio import Segmenter,rms,wav_bytes,RATE,FRAME_BYTES


class Refinamento(unittest.TestCase):
    def test_real_isolated_supervisor_shutdown_exits_and_persists_completion(self):
        # Real subprocess + HTTP + drain, no entities/models or production DB.
        code='''import runpy,sys,threading,time,socket,json
from pathlib import Path
project=Path(sys.argv[1]);root=Path(sys.argv[2]);sys.path[:0]=[str(project/"app"),str(project)]
from core import interentity,job_bus,resource_manager
interentity.DB_PATH=root/"isolated-bus.db";job_bus.DB_PATH=root/"isolated-jobs.db"
resource_manager.DB_PATH=root/"isolated-rm.db";resource_manager.LOCK_DIR=root/"locks"
ns=runpy.run_path(str(project/"iniciar_entidades.py"),run_name="isolated_shutdown_probe")
ns["main"].__globals__["ROOT"]=root
allowed={"port":None};connect=socket.socket.connect
def fixture_only(self,address):
 if not isinstance(address,tuple) or address[0]!="127.0.0.1" or address[1]!=allowed["port"]:raise PermissionError("Only this isolated HTTP fixture")
 return connect(self,address)
socket.socket.connect=fixture_only
def close_own_server():
 from urllib.parse import urlsplit
 from urllib.request import Request,urlopen
 link=root/"compartilhado/runtime/launcher/central.url"
 while not link.exists():time.sleep(.02)
 p=urlsplit(link.read_text());allowed["port"]=p.port
 req=Request(f"http://127.0.0.1:{p.port}/api/control/shutdown",data=b'{"confirm":true}',headers={"Authorization":"Bearer "+p.fragment,"Content-Type":"application/json"})
 with urlopen(req,timeout=5) as response:assert json.load(response)["accepted"]
threading.Thread(target=close_own_server,daemon=True).start()
sys.argv=["probe","--no-browser","--port","0"]
raise SystemExit(ns["main"]())
'''
        proc=subprocess.Popen([sys.executable,'-B','-c',code,str(ROOT),str(self.root)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            link=self.root/'compartilhado/runtime/launcher/central.url';deadline=time.monotonic()+12
            while not link.exists() and proc.poll() is None and time.monotonic()<deadline:time.sleep(.1)
            self.assertTrue(link.exists(),'Isolated supervisor did not start')
            from urllib.parse import urlsplit
            p=urlsplit(link.read_text())
            output,_=proc.communicate(timeout=15);self.assertEqual(proc.returncode,0,output)
            receipt=json.loads((link.parent/'shutdown-result.json').read_text())
            self.assertEqual(receipt['status'],'complete');self.assertEqual(receipt['blockers'],[])
            self.assertEqual(receipt['generation'],hashlib.sha256(p.fragment.encode()).hexdigest())
            self.assertNotIn(p.fragment,json.dumps(receipt))
        finally:
            if proc.poll() is None:proc.terminate();proc.communicate(timeout=12)

    def test_knowledge_cards_project_existing_data_without_diaries_or_cross_entity_merge(self):
        path=self.seed_logic();other=self.seed_logic('lilith');before_other=other.read_bytes()
        with contextlib.closing(sqlite3.connect(path)) as db,db:
            db.executemany("INSERT INTO people(id,nome,papel) VALUES(?,?,?)",[('p1','Alex','Amigo'),('p2','Alex','Colega'),('p3','Bia','Amiga')])
            db.execute("INSERT INTO properties(id,entity,chave,valor,confidence,source) VALUES('prop','Caneca','cor','azul',0.0,'observação')")
            db.execute("INSERT INTO memories(id,type,content,entities,confidence,source,person_id,links,created_at) VALUES('fact','fato_informado','Prefere chá','[\"Bia\"]',0.8,'usuario','p3','[]','2026-10-16')")
            db.execute("INSERT INTO memories(id,type,content,entities,confidence,source,links,created_at) VALUES('ambiguous','hipotese','Talvez goste de jogos','[\"Alex\"]',0.2,'conversa','[]','2026-10-16')")
            db.execute("INSERT INTO reflections(id,tema,conteudo,tipo,status) VALUES('private','Privado','PRIVATE_DIARY_SENTINEL','diario','active')")
        before=path.read_bytes();out=self.control.knowledge('hoshino',{})
        self.assertTrue(out['read_only']);self.assertEqual(out['entity'],'hoshino')
        ids={c['id'] for c in out['items']};self.assertTrue({'person:p1','person:p2','person:p3','topic:caneca','topic:alex'}<=ids)
        self.assertNotIn('PRIVATE_DIARY_SENTINEL',json.dumps(out))
        person=next(c for c in out['items'] if c['id']=='person:p3')
        self.assertTrue(any(e['text']=='Prefere chá' and e['subject_resolution']=='person_id' for e in person['entries']))
        prop=next(c for c in out['items'] if c['id']=='topic:caneca')['entries'][0]
        self.assertEqual(prop['confidence'],0.0);self.assertEqual(prop['source'],'observação')
        self.assertNotIn('Prefere chá',json.dumps(self.control.knowledge('lilith',{})))
        self.assertEqual(path.read_bytes(),before);self.assertEqual(other.read_bytes(),before_other)
        self.assertEqual(self.control.knowledge('hoshino',{'q':'caneca','type':'item'})['total'],1)

    def test_knowledge_pages_are_bounded_and_do_not_fabricate_legacy_confidence(self):
        path=self.seed_logic()
        with contextlib.closing(sqlite3.connect(path)) as db,db:
            db.executemany("INSERT INTO properties(id,entity,chave,valor,confidence) VALUES(?,?,?,?,NULL)",[(str(i),f'Objeto {i}','cor','verde') for i in range(30)])
        first=self.control.knowledge('hoshino',{});second=self.control.knowledge('hoshino',{'page':'1'})
        self.assertEqual(len(first['items']),24);self.assertTrue(first['has_more']);self.assertEqual(len(second['items']),6)
        self.assertIsNone(first['items'][0]['entries'][0]['confidence'])
        for query in ({'page':'-1'},{'page':'nan'},{'type':'private'},{'q':'a'*201}):
            with self.assertRaises(ValueError):self.control.knowledge('hoshino',query)
        with self.assertRaises(ValueError):self.control.knowledge('../lilith',{})

    def test_shutdown_receipt_is_bound_to_generation_and_contains_no_token(self):
        from core import shutdown
        result=shutdown.record_result(self.root,'test-secret-token',{'status':'complete','blockers':[]})
        path=self.root/'compartilhado/runtime/launcher/shutdown-result.json'
        self.assertNotIn('test-secret-token',path.read_text());self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(result['generation'],hashlib.sha256(b'test-secret-token').hexdigest())
        self.assertEqual(result['pid'],os.getpid());self.assertTrue(result['process_stamp'])

    def setUp(self):fixture.CentralControlTests.setUp(self)
    def seed(self,entity='hoshino'):
        path=mm.db_path(self.control.paths(entity))
        with contextlib.closing(sqlite3.connect(path)) as db,db:
            db.execute('CREATE TABLE memories (id TEXT PRIMARY KEY,type TEXT,content TEXT,source TEXT,confidence REAL,links TEXT)')
            db.executemany('INSERT INTO memories VALUES(?,?,?,?,?,?)',[('a','fato_informado','Meu nome é Gustavo','usuario',.8,'[]'),('b','hipotese','Talvez goste de jogos','usuario',0.0,'[]')])
            db.execute('CREATE TABLE context_summaries (id TEXT PRIMARY KEY,resumo TEXT)');db.execute("INSERT INTO context_summaries VALUES('cache','resumo derivado')")
            db.execute('CREATE TABLE people (id TEXT,nome TEXT)');db.execute("INSERT INTO people VALUES('friend','amigo')")
            db.execute('CREATE TABLE traits (nome TEXT,valor REAL)');db.execute("INSERT INTO traits VALUES('calma',0.5)")
        return path
    def seed_logic(self,entity='hoshino'):
        from memory.sqlite import init_db
        path=mm.db_path(self.control.paths(entity))
        with patch.object(init_db,'DB_PATH',str(path)):init_db.init_database(verbose=False)
        with contextlib.closing(sqlite3.connect(path)) as db,db:
            db.execute("INSERT INTO episodes(id,created_at,what_happened,context) VALUES('origin','2026-10-10T12:00:00Z','Ensaio declarado','origem preservada')")
        return path
    def logic_data(self):
        return {'entity':'hoshino','titulo':'Hipótese causal',
                'diagrama':{'nodes':[{'id':'a','label':'Condição observada','kind':'hipotese','confidence':0}], 'edges':[],'tables':[]},
                'evidencias':[{'table':'episodes','id':'origin'}]}
    def test_logic_editor_backend_backup_revision_scope_and_stale_edit(self):
        path=self.seed_logic();self.seed_logic('lilith');data=self.logic_data()
        result=self.control.save_logic_model(data)
        self.assertTrue(result['verified']);self.assertTrue((Path(result['backup'])/'hoshino.db').is_file())
        loaded=self.control.logic_models('hoshino',{'id':result['id']})['items'][0]
        self.assertEqual(loaded['graph'],data['diagrama']);self.assertEqual(self.control.logic_models('lilith',{})['items'],[])
        revised=self.control.save_logic_model(data|{'anterior':result['id'],'motivo':'Nova evidência de interpretação','titulo':'Revisão'})
        with self.assertRaises(ValueError):self.control.save_logic_model(data|{'anterior':result['id'],'motivo':'Edição desatualizada'})
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT status FROM memories WHERE id=?',(result['id'],)).fetchone()[0],'superseded')
        self.assertNotEqual(revised['id'],result['id'])
    def test_logic_editor_refuses_busy_entity_invented_evidence_and_private_diary(self):
        path=self.seed_logic();data=self.logic_data()
        job_bus.publish('ongoing','hoshino','running',kind='llm_speech')
        with self.assertRaises(ValueError):self.control.save_logic_model(data)
        job_bus.publish('ongoing','hoshino','done',kind='llm_speech')
        with self.assertRaises(ValueError):self.control.save_logic_model(data|{'evidencias':[{'table':'episodes','id':'invented'}]})
        with contextlib.closing(sqlite3.connect(path)) as db,db:
            db.execute("INSERT INTO reflections(id,tema,conteudo,tipo,status) VALUES('private','Dúvida','PRIVATE NOTE','diario','active')")
        self.assertNotIn('PRIVATE NOTE',str(self.control.memory('hoshino',{})))
        with self.assertRaises(PermissionError):self.control.save_logic_model(data|{'evidencias':[{'table':'reflections','id':'private'}]})
        self.assertFalse(list(path.parents[2].glob('runtime/memory-backups/logic-*')))
    def test_logic_editor_draft_roundtrip_stays_unvalidated(self):
        self.seed_logic()
        data=self.logic_data()|{'modo':'rascunho','evidencias':[]}
        result=self.control.save_logic_model(data)
        loaded=self.control.logic_models('hoshino',{'id':result['id']})['items'][0]
        self.assertEqual(loaded['mode'],'rascunho');self.assertEqual(loaded['type'],'hipotese')
        self.assertEqual(loaded['evidence'],[]);self.assertEqual(loaded['graph'],data['diagrama'])
    def password(self):self.control.set_password({'password':'Senha-de-teste-123','password_confirm':'Senha-de-teste-123'})
    def deletion(self,entity='hoshino',all_memories=False):
        data={'entity':entity,'all':all_memories,'targets':[] if all_memories else [{'table':'memories','id':'a'}]}
        preview=self.control.memory_preview(data)
        return data|{'confirm':True,'password':'Senha-de-teste-123','scope':preview.get('scope','memories'),'fingerprint':preview['fingerprint'],'request_id':'memory-'+uuid.uuid4().hex}
    def test_microphone_persistence_validation_and_no_auto_capture(self):
        before=self.control.microphone();self.assertFalse(before['settings']['auto_send'])
        self.control.save_microphone({'revision':before['revision'],'settings':{'mode':'detection','threshold':.025,'source':'alsa_input.fixture','silence_ms':700}})
        self.assertEqual(self.control.microphone()['settings']['mode'],'detection')
        for settings in ({'mode':'unknown'},{'threshold':0},{'threshold':float('nan')},{'source':'$(command)'},{'segment_seconds':100},{'auto_send':'yes'}):
            with self.assertRaises(ValueError):self.control.save_microphone({'revision':self.control.microphone()['revision'],'settings':settings})
    def test_output_volume_persistent_zero_and_legacy_defaults(self):
        before=self.control.microphone();self.assertEqual(before['settings']['output_volume'],100)
        saved=self.control.save_microphone({'revision':before['revision'],'settings':{'output_volume':0}})
        restored=cc.Control(self.root,self.supervisor,self.audio).microphone()
        self.assertEqual(restored['settings']['output_volume'],0);self.assertEqual(restored['revision'],saved['revision'])
        self.assertEqual(restored['settings']['mode'],before['settings']['mode']);self.assertFalse(restored['settings']['auto_send'])
        settings=self.control.ui_settings()['settings'];self.assertIn('output_volume',settings['microphone']);self.assertFalse(settings['overlay_enabled'])
    def test_output_volume_invalid_does_not_write_config_or_use_tts(self):
        before=self.control.microphone()
        with patch.object(self.audio,'_submit',side_effect=AssertionError('não sintetizar')):
            for value in (-1,101,True,None,1.5,'50',float('nan')):
                with self.assertRaises(ValueError):self.control.save_microphone({'revision':before['revision'],'settings':{'output_volume':value}})
        self.assertEqual(self.control.microphone(),before)
    def test_tool_policy_scoped_and_backend_filters_schemas(self):
        data={'entity':'hoshino','disabled':['minecraft_conectar'],'revision':self.control.ui_settings()['revision']}
        result=self.control.save_tools(data);self.assertFalse(result['cancel_running'])
        self.assertFalse(ui_policy.allowed(self.root,'hoshino','minecraft_conectar'));self.assertTrue(ui_policy.allowed(self.root,'lilith','minecraft_conectar'))
        schemas=[{'function':{'name':'minecraft_conectar'}},{'function':{'name':'get_system_time'}}]
        self.assertEqual(ui_policy.filter_schemas(self.root,'hoshino',schemas),schemas[1:])
        with self.assertRaises(ValueError):self.control.save_tools(data|{'disabled':['ferramenta_que_nao_existe'],'revision':result['revision']})
    def test_invalid_policy_fails_closed(self):
        path=self.root/'compartilhado/config/interface.json'
        for value in ('{broken','[]','null','{"disabled_tools": []}','{"disabled_tools": {"hoshino": null}}'):
            path.write_text(value);self.assertFalse(ui_policy.allowed(self.root,'hoshino','execute_command'))
    def test_actual_dispatch_denial_has_no_handler_effect_and_no_success(self):
        from core import dispatch
        path=self.root/'compartilhado/config/interface.json';path.write_text(json.dumps({'disabled_tools':{'hoshino':['get_system_time']}}))
        with patch.object(dispatch.config,'RAIZ',self.root),patch.object(dispatch.config,'ENTIDADE_ID','hoshino'),patch.dict(dispatch.HANDLERS,{'get_system_time':Mock(side_effect=AssertionError('must not execute'))}):
            output=dispatch.executar('get_system_time',{});self.assertIn('ACESSO_BLOQUEADO',output)
            self.assertFalse(dispatch._resultado_mecanico('get_system_time',output)['ok'])
            self.assertNotIn('get_system_time',[e['function']['name'] for e in dispatch.esquemas(todos=True)])
    def test_tts_model_configuration_does_not_use_quota(self):
        data={'preferred_provider':'elevenlabs','enabled':True,'voices':{'hoshino':'voice-h','lilith':'voice-l'},'model_id':'eleven_flash_v2_5','revision':self.control.audio_settings()['revision']}
        with patch('core.tts_router.urlopen',side_effect=AssertionError('quota forbidden')):self.control.save_audio(data)
        self.assertEqual(self.audio.settings['elevenlabs']['model_id'],'eleven_flash_v2_5')
        with self.assertRaises(ValueError):self.control.save_audio(data|{'model_id':'new_unapproved_model','revision':self.control.audio_settings()['revision']})
    def test_sleeping_entity_allows_explicit_voice_test_not_conversation(self):
        bus.request_sleep('hoshino')
        with patch.object(self.audio,'_submit',return_value={'id':'fixture-test'}) as submit:
            out=self.audio.submit_speech('hoshino',text='Frase definida pelo usuário.',test=True,provider='qwen3_tts')
            self.assertEqual(out['id'],'fixture-test');details=submit.call_args.args[3];self.assertTrue(details['isolated_test']);self.assertEqual(details['text'],'Frase definida pelo usuário.')
        with self.assertRaises(ValueError):self.audio.submit_speech('hoshino',text='resposta comum')
    def test_missing_eleven_key_refuses_explicit_test_instead_of_fake_provider(self):
        with patch.dict(os.environ,{},clear=True),patch.object(self.audio,'_submit',side_effect=AssertionError('must not queue')):
            with self.assertRaisesRegex(ValueError,'não configurado'):self.audio.submit_speech('hoshino',text='teste',test=True,provider='elevenlabs',model='eleven_flash_v2_5')
    def test_test_model_snapshot_no_global_mutation_or_env_override(self):
        with patch.dict(os.environ,{'ELEVENLABS_TTS_MODEL':'eleven_multilingual_v2'}):
            router=self.audio._test_router({'test_provider':'elevenlabs','test_model':'eleven_flash_v2_5'})
            self.assertEqual(router.eleven_model(),'eleven_flash_v2_5');self.assertEqual(self.audio.router.eleven_model(),'eleven_multilingual_v2')
    def test_explicit_qwen_test_uses_qwen_not_legacy_kokoro(self):
        import threading
        self.audio.settings['backend']='kokoro';router=self.audio._test_router({'test_provider':'qwen3_tts'})
        with patch.object(self.audio.tts,'call',side_effect=AssertionError('wrong worker')),patch.object(self.audio.qwen,'call',return_value={'voice':'Serena'}) as call:
            result=self.audio._synthesize_chunk('teste',self.root/'test.wav','hoshino','legacy-kokoro',threading.Event(),router)
        self.assertEqual(result['provider'],'qwen3_tts');self.assertEqual(call.call_args.args[0]['voice'],'Serena')
    def test_preferred_qwen_switch_reuses_fallback_with_kokoro_preserved(self):
        import threading
        from core.tts_router import TTSRouter
        self.audio.settings.update(backend='kokoro',preferred_provider='qwen3_tts');self.audio.router=TTSRouter(self.audio.settings)
        with patch.object(self.audio.tts,'call',side_effect=AssertionError('wrong worker')),patch.object(self.audio.qwen,'call',return_value={'voice':'Serena'}):
            result=self.audio._synthesize_chunk('teste',self.root/'test.wav','hoshino','legacy-kokoro',threading.Event())
        self.assertEqual(result['provider'],'qwen3_tts');self.assertEqual(self.audio.router.state()['preferred'],'qwen3_tts');self.assertEqual(self.audio.settings['backend'],'kokoro')
    def test_native_player_report_is_not_human_hearing_or_browser(self):
        job_bus.publish('native-play','hoshino','done',kind='audio_tts',playback_owner=self.audio.playback_owner,chunks=[{'index':0}],result={'providers':['qwen3_tts']})
        self.audio.playback_event('hoshino','native-play','started',0,'native')
        self.assertEqual(job_bus.get('native-play')['details']['playback_basis'],'native_player_report_not_human_hearing')
        with self.assertRaises(ValueError):self.audio.playback_event('lilith','native-play','ended',0,'native')
    def test_native_asr_origin_without_fictitious_review(self):
        job={'id':'audio-fixture','entity':'hoshino','kind':'audio_asr','status':'done','result':{'text':'Meu nome é Gustavo','source':'native_microphone'}}
        result=fixture.launcher.audio_origin(Mock(get=Mock(return_value=job)),'hoshino',{'audio_job_id':job['id'],'draft_origin':True,'text':'Meu nome é Gustavo','automatic_asr':True})
        self.assertEqual(result['source'],'native_microphone');self.assertFalse(result['draft_reviewed']);self.assertFalse(result['speaker_identification_performed'])
    def test_password_hash_permissions_and_ui_never_returns_password(self):
        self.password();path=self.root/'compartilhado/config/central_security.json'
        self.assertNotIn('Senha-de-teste-123',path.read_text());self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.control.password_state(),{'configured':True})
        with self.assertRaises(ValueError):self.control.set_password({'password':'outra-senha-123','password_confirm':'outra-senha-123'})
    def test_password_rejected_before_write_and_valid_password_survives_new_control(self):
        path=self.root/'compartilhado/config/central_security.json'
        for password,confirm in [('abc123','abc123'),('x'*201,'x'*201),('valid-fixture','different-fixture')]:
            with self.assertRaises(ValueError):self.control.set_password(dict(password=password,password_confirm=confirm))
            self.assertFalse(path.exists());self.assertEqual(self.control.password_state(),{'configured':False})
        self.password();fresh=cc.Control(self.root,self.supervisor,self.audio)
        self.assertEqual(fresh.password_state(),{'configured':True});fresh._check_password('Senha-de-teste-123')
        with self.assertRaisesRegex(ValueError,'Senha incorreta'):fresh._check_password('wrong-fixture')
    def test_password_required_and_rate_limit(self):
        self.seed();data=self.deletion()
        with self.assertRaises(ValueError):self.control.delete_memory(data)
        self.password()
        for _ in range(5):
            with self.assertRaisesRegex(ValueError,'Senha incorreta'):self.control.delete_memory(data|{'password':'errada'})
        with self.assertRaisesRegex(ValueError,'tentativas'):self.control.delete_memory(data)
    def test_specific_delete_backup_vector_and_other_entity_preserved(self):
        path=self.seed();other=self.seed('lilith');other_before=other.read_bytes();self.password();data=self.deletion()
        with patch.object(mm,'remove_vectors',return_value=1) as remove:
            result=self.control.delete_memory(data)
        self.assertTrue(result['verified']);self.assertEqual(remove.call_args.args[0].id,'hoshino');self.assertEqual(other.read_bytes(),other_before)
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT id FROM memories').fetchall(),[('b',)]);self.assertEqual(db.execute('SELECT COUNT(*) FROM context_summaries').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT nome FROM people').fetchone()[0],'amigo');self.assertEqual(db.execute('SELECT valor FROM traits').fetchone()[0],.5)
        backup=Path(result['backup'])/path.name
        with contextlib.closing(sqlite3.connect(backup)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0],2)
    def test_delete_all_only_selected_entity_clears_learned_people_preserves_traits(self):
        path=self.seed('lilith');other=self.seed();before=other.read_bytes();self.password()
        with patch.object(mm,'remove_vectors',return_value=0) as remove:result=self.control.delete_memory(self.deletion('lilith',True))
        self.assertTrue(remove.call_args.args[2]);self.assertEqual(other.read_bytes(),before)
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0],0);self.assertEqual(db.execute('SELECT COUNT(*) FROM people').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT valor FROM traits').fetchone()[0],.5)
    def test_delete_busy_entity_and_unconfirmed_change_rejected(self):
        path=self.seed();self.password();data=self.deletion();bus.register('hoshino','awake')
        with self.assertRaises(ValueError):self.control.delete_memory(data)
        bus.register('hoshino','sleeping')
        with contextlib.closing(sqlite3.connect(path)) as db,db:db.execute("UPDATE memories SET content='editado' WHERE id='a'")
        with self.assertRaisesRegex(ValueError,'mudaram'):self.control.delete_memory(data)
    def test_missing_confirmation_invalid_scope_and_traversal(self):
        self.seed();self.password();data=self.deletion()
        with self.assertRaises(ValueError):self.control.delete_memory(data|{'confirm':False})
        for target in ({'table':'people','id':'friend'},{'table':'memories;DROP TABLE people','id':'a'}):
            with self.assertRaises(ValueError):self.control.memory_preview({'entity':'hoshino','targets':[target]})
        with self.assertRaises(ValueError):self.control.memory_preview({'entity':'../lilith','all':True})
    def test_vector_failure_is_uncertain_not_fake_success_and_sql_preserved(self):
        path=self.seed();self.password();data=self.deletion();before=path.read_bytes()
        with patch.object(mm,'remove_vectors',side_effect=RuntimeError('failure')):
            with self.assertRaisesRegex(ValueError,'não confirmada'):self.control.delete_memory(data)
        self.assertEqual(path.read_bytes(),before);job=job_bus.get(data['request_id']);self.assertEqual(job['status'],'interrupted');self.assertEqual(job['details']['outcome'],'uncertain')
        with self.assertRaisesRegex(ValueError,'não repetir'):self.control.delete_memory(data)
    def test_idempotent_request_replay_and_conflicting_request_id(self):
        self.seed();self.password();data=self.deletion()
        with patch.object(mm,'remove_vectors',return_value=0):result=self.control.delete_memory(data)
        with patch.object(mm,'delete',side_effect=AssertionError('do not replay')):self.assertEqual(self.control.delete_memory(data),result)
        with self.assertRaises(ValueError):self.control.delete_memory(data|{'fingerprint':'different'})
    def test_real_temporary_vector_delete_no_embeddings_or_download(self):
        self.seed();paths=self.control.paths('hoshino')
        # Guardas da suíte deliberadamente não importam Chroma/modelos. Aqui
        # um filho isolado exercita só IDs com embeddings explícitos temporários.
        code='''import sys,socket
from pathlib import Path
from types import SimpleNamespace
def reject(*a,**k):raise AssertionError("offline: no network")
socket.socket.connect=reject
sys.path.insert(0,sys.argv[1])
import chromadb
from chromadb.config import Settings
from core import memory_maintenance as mm
paths=SimpleNamespace(id="hoshino",memory=Path(sys.argv[2]),runtime=Path(sys.argv[3]),raiz=Path(sys.argv[2]).parent)
client=chromadb.PersistentClient(path=str(paths.memory/"vector/db"),settings=Settings(anonymized_telemetry=False))
c=client.create_collection("hoshino_knowledge",embedding_function=None)
c.add(ids=["a","b","orphan"],embeddings=[[1.,0.],[0.,1.],[1.,1.]],documents=["nome","hipotese","orfao"])
from unittest.mock import patch
# Central em outro Python não deve impedir o worker vetorial do projeto.
with patch.object(mm.sys,"executable","/central-sem-chroma/python"):
    r=mm.delete(paths,mm.plan(paths,[{"table":"memories","id":"a"}]))
assert r["deleted_vectors"]==1 and set(c.get(include=[])["ids"])=={"b","orphan"}
r=mm.delete(paths,mm.plan(paths,all_memories=True))
assert r["deleted_vectors"]==2 and c.count()==0
assert (Path(r["backup"])/"vector/chroma.sqlite3").is_file()
print("temporary vector deletion verified; no model or quota")
'''
        env={k:v for k,v in os.environ.items() if k in {'PATH','LANG'}};env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',ANONYMIZED_TELEMETRY='False')
        result=subprocess.run([sys.executable,'-c',code,str(ROOT/'app'),str(paths.memory),str(paths.runtime)],env=env,capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_native_open_process_no_ai_credentials_no_browser(self):
        with patch.dict(os.environ,{'ELEVENLABS_API_KEY':'secret-do-not-copy','DISCORD_TOKEN':'secret-discord'}),patch('subprocess.Popen',return_value=Mock(pid=1)) as start:
            out=self.control.start_native({'entity':'lilith'})
        self.assertTrue(out['accepted']);self.assertNotIn('ELEVENLABS_API_KEY',start.call_args.kwargs['env']);self.assertNotIn('DISCORD_TOKEN',start.call_args.kwargs['env'])
        self.assertIn('central_native.py',' '.join(start.call_args.args[0]));self.assertNotIn('webbrowser',' '.join(start.call_args.args[0]))
    def test_native_qt_window_offscreen_backend_survives_close(self):
        server,token=fixture.launcher.make_server(self.supervisor,0,self.audio);self.addCleanup(server.server_close)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.shutdown)
        folder=self.root/'compartilhado/runtime/launcher';folder.mkdir(parents=True)
        (folder/'central.url').write_text(f'http://127.0.0.1:{server.server_port}/#{token}')
        with tempfile.TemporaryDirectory() as tmp:
            env={k:v for k,v in os.environ.items() if k in {'PATH','LANG'}};env.update(QT_QPA_PLATFORM='offscreen',QT_OPENGL='software',XDG_CONFIG_HOME=tmp,XDG_CACHE_HOME=tmp,XDG_RUNTIME_DIR=tmp)
            qa=os.environ.get('HOSHINO_NATIVE_QA_DIR');snapshot=Path(qa)/'central-nativa-audio.png' if qa else Path(tmp)/'native.png'
            if qa:
                self.assertTrue(snapshot.resolve().is_relative_to(Path('/tmp')));snapshot.parent.mkdir(parents=True,exist_ok=True)
            result=subprocess.run(['/usr/bin/python3',str(ROOT/'app/ui/central_native.py'),'--root',str(self.root),'--smoke-seconds','12' if qa else '2','--snapshot',str(snapshot),'--smoke-page','Áudio'],env=env,capture_output=True,text=True,timeout=25)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertTrue(snapshot.is_file());self.assertIn('"backend_shutdown_sent": false',result.stdout)
            print(result.stdout.strip())
        self.assertTrue(thread.is_alive());self.assertFalse(self.supervisor.closing)
    def test_native_qt_interactions_mock_transport_and_processes(self):
        folder=self.root/'compartilhado/runtime/launcher';folder.mkdir(parents=True)
        (folder/'central.url').write_text('http://127.0.0.1:23456/#fixture-not-a-key')
        with tempfile.TemporaryDirectory() as tmp:
            env={k:v for k,v in os.environ.items() if k in {'PATH','LANG'}};env.update(QT_QPA_PLATFORM='offscreen',QT_OPENGL='software',XDG_CONFIG_HOME=tmp,XDG_CACHE_HOME=tmp,XDG_RUNTIME_DIR=tmp)
            if os.environ.get('HOSHINO_NATIVE_QA_DIR'):
                qa=Path(os.environ['HOSHINO_NATIVE_QA_DIR']).resolve();self.assertTrue(qa.is_relative_to('/tmp'));env['HOSHINO_NATIVE_QA_DIR']=str(qa)
            result=subprocess.run(['/usr/bin/python3','-X','faulthandler',str(ROOT/'testes/native_central_contracts.py'),str(self.root)],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertRegex(result.stderr,r'Ran \d+ tests')
    def test_desktop_launcher_uses_login_environment_without_embedding_keys(self):
        desktop=ROOT/'Hoshino e Lilith.desktop'
        parsed=subprocess.run(['/usr/bin/python3','-c',
            'import json,sys; from gi.repository import Gio,GLib; p=Gio.DesktopAppInfo.new_from_filename(sys.argv[1]); print(json.dumps(GLib.shell_parse_argv(p.get_commandline())[1]))',str(desktop)],
            env={'PATH':os.environ['PATH']},capture_output=True,text=True,timeout=5)
        self.assertEqual(parsed.returncode,0,parsed.stderr);argv=json.loads(parsed.stdout)
        self.assertEqual(argv[:2],['/bin/bash','-lc']);self.assertEqual(len(argv),3)
        import shlex
        self.assertEqual(shlex.split(argv[2]),['exec',str(ROOT/'iniciar_entidades.py')])
        self.assertIn('Terminal=false',desktop.read_text());self.assertNotIn('API_KEY',desktop.read_text())
        validated=subprocess.run(['desktop-file-validate',str(desktop)],capture_output=True,text=True,timeout=5)
        self.assertEqual(validated.returncode,0,validated.stderr)
    def test_desktop_shell_preserves_path_spaces_and_passes_environment(self):
        # Sem ler o perfil real/segredos: ambiente e executável descartáveis.
        import shlex
        folder=self.root/'pasta com espaços';folder.mkdir();program=folder/'iniciar_entidades.py'
        program.write_text('#!/usr/bin/python3\nimport os\nassert os.environ.get("HOSHINO_LAUNCH_FIXTURE")=="fixture-only"\nprint("fixture-launch-ok")\n');program.chmod(0o700)
        result=subprocess.run(['/bin/bash','--noprofile','--norc','-lc','exec '+shlex.quote(str(program))],
            env={'PATH':os.environ['PATH'],'HOSHINO_LAUNCH_FIXTURE':'fixture-only'},capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'fixture-launch-ok')


class PCMTests(unittest.TestCase):
    def pcm(self,value,frames):return array.array('h',[value]*(FRAME_BYTES//2*frames)).tobytes()
    def test_silence_does_not_create_detection_segment(self):
        engine=Segmenter('detection');_,segments=engine.feed(self.pcm(0,200));self.assertEqual(segments,[]);self.assertLessEqual(len(engine.pre),FRAME_BYTES*6)
    def test_detection_finalizes_complete_phrase_after_silence(self):
        engine=Segmenter('detection',silence_ms=300);engine.feed(self.pcm(0,5));_,a=engine.feed(self.pcm(3000,8));_,b=engine.feed(self.pcm(0,6))
        self.assertEqual(len(a+b),1);self.assertGreater(rms(b[0]),0);self.assertTrue(wav_bytes(b[0]).startswith(b'RIFF'))
    def test_two_modes_bounded_detection_and_command_release(self):
        for mode in ('manual','open','unknown'):
            with self.assertRaises(ValueError):Segmenter(mode)
        engine=Segmenter('detection');_,out=engine.feed(self.pcm(3000,1000));self.assertEqual(len(out),1);self.assertLess(len(engine.buffer),45*RATE*2)
        ptt=Segmenter('command');ptt.feed(self.pcm(3000,8));self.assertEqual(len(ptt.finish()),8*FRAME_BYTES);self.assertEqual(ptt.finish(),b'')
    def test_pcm_wav_bounds_and_partial_input(self):
        with self.assertRaises(ValueError):wav_bytes(b'1')
        with self.assertRaises(ValueError):wav_bytes(bytes(46*RATE*2))
        engine=Segmenter();engine.feed(b'\0'*1599);self.assertEqual(len(engine.pending),1599);engine.feed(b'\0');self.assertEqual(len(engine.pending),0)
    def test_pulse_volume_bounds_and_mute(self):
        from native_audio import pulse_volume
        self.assertEqual([pulse_volume(v) for v in (0,50,100)],[0,32768,65536])
        for value in (-1,101,True,None,1.5,'50'):
            with self.assertRaises(ValueError):pulse_volume(value)
    def test_sink_input_requires_unique_pid_and_stream_not_other_apps(self):
        from native_audio import owned_sink_input
        own={'index':9,'properties':{'application.process.id':'42','media.name':'own-stream'}}
        foreign={'index':8,'properties':{'application.process.id':'43','media.name':'own-stream'}}
        self.assertEqual(owned_sink_input([foreign,own],42,'own-stream'),9)
        self.assertIsNone(owned_sink_input([foreign],42,'own-stream'))
        self.assertIsNone(owned_sink_input([own,own],42,'own-stream'))
        self.assertIsNone(owned_sink_input([own],42,'different-stream'))
        self.assertIsNone(owned_sink_input([own],0,'own-stream'))


if __name__=='__main__':unittest.main()
