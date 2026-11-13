"""Supervisor real com transportes/processos isolados; não prova sono físico."""
import json
import logging
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'app'))
from laboratorio import treinos_unificados as lab
from testes import test_central_control as fixture
from core import diagnostics,history
from laboratorio import rotina_noturna as routine, professor_moe as teacher
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib


class NightSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.CentralControlTests(methodName='runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        # Direct laboratory unittest runs do not use executar_isolado.py.
        # Keep REAL diagnostic writes and their SQLite mirror in the fixture,
        # rather than silencing emit or leaking simulated nights to production.
        self.runtime=self.fixture.root/'telemetry';self.runtime.mkdir()
        for obj,name,value in [(diagnostics.config,'RUNTIME_DIR',str(self.runtime)),
                               (history,'DB',self.runtime/'history.sqlite3'),
                               (history,'_INITIALIZED_DB',None)]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        logger=logging.Logger('laboratory-night-fixture')
        handler=logging.FileHandler(self.runtime/'night.log',encoding='utf8')
        logger.addHandler(handler);self.addCleanup(handler.close)
        p=patch.object(diagnostics,'_logger',return_value=logger)
        p.start();self.addCleanup(p.stop)
        self.supervisor=self.fixture.supervisor
        self.home=self.fixture.root/'laboratorio-local';self.home.mkdir()
        self.supervisor.laboratory_home=self.home
        self.data={'confirm':'VOU_DORMIR_AUTORIZO_LABORATORIO','window_minutes':30,
                   'tasks':[{'model':'alistair-4b','entity':'alistair','minutes':1,'action':'train'}]}
        self.spec={'allowed':True,'entity':'alistair','preset':{'rank':4},'model':{'benchmarks':{'alistair':{'preset':{'rank':4}}}}}

    def test_night_diagnostics_are_really_persisted_only_in_fixture(self):
        self.assertEqual(Path(diagnostics.config.RUNTIME_DIR),self.runtime)
        self.assertEqual(history.DB,self.runtime/'history.sqlite3')
        self.authorize()
        records=[json.loads(line) for file in (self.runtime/'diagnostics').glob('*.jsonl')
                 for line in file.read_text().splitlines()]
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['event'],'laboratory.night_authorized')
        self.assertEqual(records[0]['data']['night_id'],self.supervisor.night['id'])
        self.assertIn('laboratory.night_authorized',(self.runtime/'night.log').read_text())
        with closing(sqlite3.connect(history.DB)) as db:
            rows=db.execute('SELECT kind,data FROM events').fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][0],'laboratory.night_authorized')
        self.assertEqual(json.loads(rows[0][1])['_diagnostic_id'],records[0]['diagnostic_id'])

    def authorize(self):
        with patch.object(lab,'plan',return_value=self.spec),patch.object(fixture.bus,'presence',
                  side_effect=lambda e:{'status':'awake' if e=='hoshino' else 'sleeping'}),patch.object(fixture.bus,'request_sleep') as sleep:
            self.supervisor.authorize_night(self.data)
            sleep.assert_called_once_with('hoshino', requester='sistema',
                reason='Pausa para a sessão de laboratório autorizada.', source='laboratorio')

    def test_wake_prepares_missing_model_without_starting_entity(self):
        from laboratorio import recuperacao_modelos as recovery
        with patch.object(fixture.bus,'presence',side_effect=lambda entity='': {'status':'sleeping'} if entity else {'entities':[]}),\
             patch.object(fixture.bus,'clear_sleep'),patch.object(fixture.bus,'register'),\
             patch.object(recovery,'ensure',return_value={'state':'recovering','id':'a'*16}) as prepare,\
             patch.object(fixture.launcher.subprocess,'Popen') as process:
            out=self.supervisor.start('hoshino')
        self.assertEqual(out['status'],'starting');process.assert_not_called()
        self.assertEqual(self.supervisor.model_recoveries,{'hoshino':'a'*16})
        prepare.assert_called_once_with(self.home,fixture.launcher.ROOT,'hoshino')

    def test_sleep_during_recovery_cancels_only_that_job_and_never_wakes(self):
        self.supervisor.model_recoveries={'lilith':'b'*16}
        with patch.object(lab,'details',return_value={'state':'running'}),patch.object(lab,'stop') as cancel,\
             patch.object(fixture.bus,'sleep_requested',return_value=True),patch.object(fixture.bus,'heartbeat'),\
             patch.object(self.supervisor,'start') as wake:
            self.supervisor.tick()
        cancel.assert_called_once_with(self.home,'b'*16,'PARAR_TREINO_UNIFICADO');wake.assert_not_called()

    def test_failed_recovery_survives_as_error_without_automatic_wake(self):
        self.supervisor.model_recoveries={'hoshino':'a'*16}
        with patch.object(lab,'details',return_value={'state':'failed','error':'fixture error'}),\
             patch.object(fixture.bus,'sleep_requested',return_value=False),patch.object(fixture.bus,'register'),\
             patch.object(self.supervisor,'start') as wake:
            self.supervisor.tick()
        wake.assert_not_called();self.assertFalse(self.supervisor.model_recoveries)
        self.assertIn('fixture error',self.supervisor.failures['hoshino'])

    def test_recovery_completed_but_owner_still_releasing_does_not_start(self):
        self.supervisor.model_recoveries={'hoshino':'a'*16}
        with patch.object(lab,'details',return_value={'state':'completed'}),patch.object(lab,'_owned_alive',return_value=True),\
             patch.object(fixture.bus,'heartbeat'),patch.object(self.supervisor,'start') as wake:
            self.supervisor.tick()
        wake.assert_not_called();self.assertEqual(self.supervisor.model_recoveries,{'hoshino':'a'*16})

    def test_restore_only_originally_awake_without_claiming_health(self):
        self.authorize()
        with patch.object(fixture.bus,'presence',return_value={'status':'sleeping'}),\
             patch.object(fixture.job_bus,'status',return_value=[]),patch.object(fixture.rm,'status',return_value=[]),\
             patch.object(lab,'_busy',return_value=None),patch.object(lab,'start',return_value={'id':'a'*16}) as train,\
             patch.object(lab,'details',return_value={'state':'completed','artifact':'fixture'}),\
             patch.object(self.supervisor,'start',return_value={'status':'starting'}) as wake:
            self.supervisor.night_tick();train.assert_called_once()
            wake.assert_not_called()
            self.supervisor.night_tick();wake.assert_called_once_with('hoshino', requester='sistema',
                reason='Restauração após a sessão de laboratório autorizada.', source='laboratorio',
                reference=self.supervisor.night['id'])
        self.assertEqual(self.supervisor.night['state'],'completed')
        self.assertTrue(self.supervisor.night['restoration_health_pending'])
        self.assertFalse(self.supervisor.laboratory_maintenance)

    def test_capacity_denial_keeps_restoration_pending_until_admitted(self):
        self.authorize()
        self.supervisor.night.update(state='restoring',restore_entities=['hoshino','lilith'])
        with patch.object(fixture.bus,'presence',return_value={'status':'sleeping'}),\
             patch.object(fixture.rm,'status',return_value=[]),patch.object(lab,'_busy',return_value=None),\
             patch.object(self.supervisor,'start',side_effect=[{'status':'awake'},ValueError('GPU16GB necessária')]):
            self.supervisor.night_tick()
        self.assertEqual(self.supervisor.night['state'],'restoring')
        self.assertEqual(self.supervisor.night['restore_pending'],['lilith'])
        deadline=self.supervisor.next_attempt['lilith']
        with patch.object(fixture.bus,'presence',return_value={'status':'sleeping'}),\
             patch.object(fixture.rm,'status',return_value=[]),patch.object(lab,'_busy',return_value=None),\
             patch.object(self.supervisor,'start') as still_waiting:
            for elapsed in (3,2,1):
                with patch.object(fixture.launcher.time,'monotonic',return_value=deadline-elapsed):
                    self.supervisor.night_tick()
                self.assertEqual(self.supervisor.next_attempt['lilith'],deadline)
            still_waiting.assert_not_called()
        self.supervisor.next_attempt.clear()
        with patch.object(fixture.bus,'presence',return_value={'status':'sleeping'}),\
             patch.object(fixture.rm,'status',return_value=[]),patch.object(lab,'_busy',return_value=None),\
             patch.object(self.supervisor,'start',return_value={'status':'starting'}) as wake:
            self.supervisor.night_tick()
        self.assertEqual(self.supervisor.night['state'],'completed')
        self.assertEqual(wake.call_count,1)
        self.assertEqual(wake.call_args.args[0],'lilith')

    def test_block_wake_and_drain_mutable_jobs_without_killing(self):
        self.authorize()
        with self.assertRaises(ValueError):self.supervisor.start('lilith')
        with patch.object(fixture.bus,'presence',return_value={'status':'sleeping'}),\
             patch.object(fixture.job_bus,'status',return_value=[{'outcome':'uncertain'}]),\
             patch.object(fixture.rm,'status',return_value=[]),patch.object(lab,'start') as start,patch('os.kill') as kill:
            self.supervisor.night_tick();start.assert_not_called();kill.assert_not_called()
        self.assertEqual(self.supervisor.night['state'],'draining')

    def test_restart_does_not_replay_or_wake_automatically(self):
        self.authorize()
        restarted=fixture.launcher.Supervisor(laboratory_home=self.home)
        self.assertEqual(restarted.night['state'],'recovery_required')
        with patch.object(restarted,'start') as wake,patch.object(lab,'start') as train:
            restarted.night_tick();wake.assert_not_called();train.assert_not_called()
        self.assertTrue(restarted.laboratory_maintenance)

    def test_evaluation_uses_exact_completed_predecessor_before_next_entity(self):
        self.authorize()
        self.supervisor.night.update(state='running',index=1,job=None,
            history=[{'id':'a'*16,'artifact':'candidate-h'}],tasks=[
                {'model':'qwen35-9b','entity':'hoshino','action':'train'},
                {'model':'qwen35-9b','entity':'hoshino','action':'evaluate','minutes':15,'candidate_from_task':0}])
        with patch.object(lab,'details',return_value={'state':'completed','action':'train','entity':'hoshino','model':'qwen35-9b','artifact':'candidate-h'}),\
             patch.object(lab,'start',return_value={'id':'b'*16}) as run:
            self.supervisor.night_tick()
        self.assertEqual(run.call_args.args[8],'candidate-h')
        self.assertEqual(self.supervisor.night['index'],1)

    def test_safe_stop_keeps_job_for_explicit_cumulative_resume(self):
        self.authorize()
        self.supervisor.night.update(state='stopping',job='a'*16)
        with patch.object(lab,'details',return_value={'state':'cancelled_checkpointed'}),patch.object(lab,'_busy',return_value='still releasing GPU'):
            self.supervisor.night_tick()
        self.assertEqual(self.supervisor.night['stopped_job'],'a'*16)
        self.assertIsNone(self.supervisor.night['job'])

    def test_policy_defaults_validation_backup_no_automatic_activation(self):
        initial=routine.config(self.home)
        self.assertEqual((initial['start_time'],initial['idle_minutes']),('00:30',30))
        self.assertFalse(initial['enabled'])
        self.assertFalse(initial['automatic_data_approval'])
        out=routine.configure(self.home,{'confirm':True,'settings':{'start_time':'01:15','idle_minutes':45}})
        self.assertEqual(out['idle_minutes'],45)
        routine.configure(self.home,{'confirm':True,'settings':{'enabled':True}})
        self.assertEqual(len(list(routine.root(self.home).glob('policy-backup-*'))),1)
        self.assertEqual((routine.root(self.home)/'policy.json').stat().st_mode&0o777,0o600)
        for settings in ({'start_time':'25:99'},{'idle_minutes':0},{'idle_minutes':True},{'enabled':'true'},{'shell':'poweroff'}):
            with self.assertRaises(ValueError):routine.configure(self.home,{'confirm':True,'settings':settings})
        with self.assertRaises(ValueError):routine.configure(self.home,{'settings':{'enabled':True}})
        routine.save(self.home,'policy.json',{'enabled':'false'})
        with self.assertRaises(ValueError):routine.config(self.home)

    def test_schedule_timezone_midnight_and_explicit_sleep_not_quote(self):
        p=routine.config(self.home)
        def at(text):return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(p['timezone'])).timestamp()
        self.assertIsNone(routine.schedule_key(p,at('2026-10-13T00:29:59')))
        self.assertEqual(routine.schedule_key(p,at('2026-10-13T00:30:00')),'2026-10-13')
        self.assertIsNone(routine.schedule_key(p,at('2026-10-13T02:30:00')))
        p['start_time']='23:50'
        self.assertEqual(routine.schedule_key(p,at('2026-10-14T00:10:00')),'2026-10-13')
        self.assertFalse(routine.note_sleep(self.home,'ela disse: vou dormir','msg-a',now=100))
        self.assertTrue(routine.note_sleep(self.home,'Boa noite! vou dormir.','msg-b',now=100))
        self.assertEqual(routine.read_permission(self.home)['source_id'],'msg-b')
        self.assertTrue(routine.note_sleep(self.home,'vou dormir agora','msg-c',now=101))
        for text in ('não vou dormir','vou dormir?','ela falou "vou dormir"'):
            self.assertFalse(routine.note_sleep(self.home,text,'msg-x',now=102))

    def test_ai_switch_off_blocks_automatic_jobs_even_when_daily_schedule_enabled(self):
        routine.configure(self.home,{'confirm':True,'settings':{'enabled':True,'automatic_data_approval':False}})
        with patch.object(routine,'guard') as guard,patch.object(self.supervisor,'authorize_night') as start:
            routine.auto_tick(self.supervisor)
        guard.assert_not_called();start.assert_not_called()
        self.assertEqual(self.supervisor.night_readiness['state'],'ai_training_disabled')
        with patch.object(teacher,'detail') as read:
            with self.assertRaises(RuntimeError):routine.approve_data(self.home,'a'*16,'pacote_identidade_v6:hoshino')
        read.assert_not_called()

    def test_disabled_ai_refuses_learn_but_not_manual_night(self):
        data=dict(self.data,tasks=[dict(action='learn',entity='hoshino',model='qwen35-9b',minutes=1,examples=8)])
        with self.assertRaisesRegex(ValueError,'desativado'):lab.night_create(self.home,self.fixture.root,data,[])
        obj=self.auto_night();routine.configure(self.home,{'confirm':True,'settings':{'automatic_data_approval':False}})
        with patch.object(teacher,'start') as start: routine.learn_tick(self.supervisor,obj['tasks'][0],1)
        start.assert_not_called();self.assertEqual(obj['state'],'stopping')

    def test_cumulative_learning_keeps_approved_stable_data_and_refuses_changed_corpus(self):
        folder=self.home/'stable-fixture';folder.mkdir()
        data=self.home/'approved-data';data.mkdir()
        train=data/'train.jsonl';train.write_text('original + aprendizado da noite anterior')
        validation=data/'val.jsonl';validation.write_text('validação intacta')
        prov=dict(entity='hoshino',train_path=str(train),train_sha256=hashlib.sha256(train.read_bytes()).hexdigest(),
                  validation_sha256=hashlib.sha256(validation.read_bytes()).hexdigest())
        (folder/'provenance.json').write_text(json.dumps(prov))
        approved=[dict(id='importados:previous-approved',train=str(train),validation=str(validation))]
        stable=dict(available=True,snapshot=str(folder))
        with patch.object(lab,'training_datasets',return_value=approved):
            self.assertEqual(routine.cumulative_dataset(self.home,'hoshino',stable),'importados:previous-approved')
            with self.assertRaises(RuntimeError):routine.cumulative_dataset(self.home,'lilith',stable)
            train.write_text('mudança silenciosa')
            with self.assertRaises(RuntimeError):routine.cumulative_dataset(self.home,'hoshino',stable)
        self.assertEqual(routine.cumulative_dataset(self.home,'hoshino',{'available':False}),'pacote_identidade_v6:hoshino')

    def test_stable_data_missing_approval_never_falls_back_silently(self):
        folder=self.home/'stable-fixture';folder.mkdir()
        train=folder/'train';train.write_text('data')
        (folder/'provenance.json').write_text(json.dumps(dict(entity='hoshino',train_path=str(train),
            train_sha256=hashlib.sha256(train.read_bytes()).hexdigest())))
        with patch.object(lab,'training_datasets',return_value=[]):
            with self.assertRaises(RuntimeError):routine.cumulative_dataset(self.home,'hoshino',dict(available=True,snapshot=str(folder)))

    def make_agendas(self):
        for entity in routine.DEFAULTS['entities']:
            file=self.fixture.root/'entidades'/entity/'memory/sqlite'/(entity+'.db')
            with closing(sqlite3.connect(file)) as db,db:
                db.executescript('CREATE TABLE goals(id TEXT,status TEXT,due_at TEXT); CREATE TABLE reminders(id TEXT,status TEXT,due_at TEXT);')

    def test_agenda_read_only_separate_entities_and_invalid_timestamp(self):
        self.make_agendas()
        dbpath=self.fixture.root/'entidades/lilith/memory/sqlite/lilith.db'
        with closing(sqlite3.connect(dbpath)) as db,db:
            db.execute('INSERT INTO goals VALUES(?,?,?)',('same-id','active','2026-10-14T08:00:00-03:00'))
        before=hashlib.sha256(dbpath.read_bytes()).hexdigest()
        out=routine.agenda(self.fixture.root,now=10)
        self.assertEqual([(r['entity'],r['id']) for r in out],[('lilith','same-id')])
        self.assertEqual(before,hashlib.sha256(dbpath.read_bytes()).hexdigest())
        with closing(sqlite3.connect(dbpath)) as db,db:db.execute("UPDATE goals SET due_at='horário inventado'")
        with self.assertRaises(ValueError):routine.agenda(self.fixture.root)

    def test_history_authorship_provenance_backlog_and_diary_exclusion(self):
        path=self.fixture.root/'entidades/hoshino/runtime/history.sqlite3'
        with closing(sqlite3.connect(path)) as db,db:
            db.executescript('CREATE TABLE messages(id TEXT,ts TEXT,direction TEXT,role TEXT,channel TEXT,channel_target TEXT,person_id TEXT,person_name TEXT,content TEXT,metadata TEXT,turn_id TEXT,session_id TEXT);')
            for i in range(4):
                meta=json.dumps({'observer_entity':'hoshino'})
                refs={'observer_entity':'hoshino','input_sources':[{'ouvinte_id':'hoshino','history_id':'in'+str(i)}]}
                if i==2:refs['private']=True
                db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('in'+str(i),'2026-10-13','in','user','localhub','','usuario','Gustavo','Eu disse algo '+str(i),meta,'','session'))
                db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('out'+str(i),'2026-10-13','out','assistant','localhub','','usuario','Gustavo','Resposta '+str(i),json.dumps(refs),'turn'+str(i),'session'))
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        out=routine.history_snapshot(self.home,self.fixture.root,'hoshino',limit=3)
        self.assertEqual(out['included'],2);self.assertEqual(len(out['skipped']),1)
        rows,digest=teacher.read_snapshot(teacher.source_dir(self.home)/out['snapshot'],'hoshino')
        self.assertEqual(len(rows),2);self.assertIn('[Gustavo]',rows[0]['messages'][0]['content'])
        self.assertEqual(out['links'][0]['messages'][0]['id'],'in0')
        self.assertEqual(out['links'][0]['messages'][1]['turn_id'],'turn0')
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
        routine.save(self.home,'history-hoshino.json',out)
        after=routine.history_snapshot(self.home,self.fixture.root,'hoshino')
        self.assertEqual(after['included'],1);self.assertNotIn('snapshot',after)
        self.assertGreater(after['cursor'],out['cursor'])
        # Sem entrada suficiente, o cursor não é confirmado automaticamente.
        self.assertEqual(json.loads((routine.root(self.home)/'history-hoshino.json').read_text())['cursor'],out['cursor'])

    def test_alistair_history_uses_existing_table_real_sender(self):
        path=self.fixture.root/'entidades/alistair/memory/sqlite/alistair.db'
        with closing(sqlite3.connect(path)) as db,db:
            db.execute('CREATE TABLE alistair_turns(source_id TEXT,sender TEXT,input TEXT,output TEXT,created_at REAL)')
            db.executemany('INSERT INTO alistair_turns VALUES(?,?,?,?,?)',[(f'msg-{i}',s,'Meu nome é '+s,'Oi, '+s,123.) for i,s in enumerate(('usuario','hoshino'))])
        out=routine.history_snapshot(self.home,self.fixture.root,'alistair')
        rows,_=teacher.read_snapshot(teacher.source_dir(self.home)/out['snapshot'],'alistair')
        self.assertIn('[hoshino]',rows[1]['messages'][0]['content'])
        self.assertEqual(out['links'][1]['sender'],'hoshino')

    def test_human_chat_ratings_export_with_exact_turn_for_three_entities_no_approval(self):
        from core import interentity as bus
        for entity in ('hoshino','lilith','alistair'):
            base=self.fixture.root/'entidades'/entity
            path=base/'memory/sqlite/alistair.db' if entity=='alistair' else base/'runtime/history.sqlite3'
            with closing(sqlite3.connect(path)) as db,db:
                if entity=='alistair':db.execute('CREATE TABLE alistair_turns(source_id TEXT,sender TEXT,input TEXT,output TEXT,created_at REAL)')
                else:db.execute('CREATE TABLE messages(id TEXT,ts TEXT,direction TEXT,role TEXT,channel TEXT,channel_target TEXT,person_id TEXT,person_name TEXT,content TEXT,metadata TEXT,turn_id TEXT,session_id TEXT)')
                for index,decision in enumerate(('liked','disliked')):
                    source_id=f'input-{entity}-{index}';text=f'Resposta {entity} {index}'
                    turn_id='turn-alistair-'+hashlib.sha256(source_id.encode()).hexdigest()[:16] if entity=='alistair' else f'turn-{entity}-{index}'
                    if entity=='alistair':db.execute('INSERT INTO alistair_turns VALUES(?,?,?,?,?)',(source_id,'usuario','Uma pergunta',text,123.))
                    else:
                        for direction,content in (('in','Uma pergunta'),('out',text)):
                            db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(source_id+direction,'2026-10-16',''+direction,'user' if direction=='in' else 'assistant','localhub','','usuario','Autor',content,json.dumps({'observer_entity':entity}),turn_id,'session'))
                    msg=bus.send(entity,'usuario',text,metadata={'turn_id':turn_id})
                    bus.save_human_feedback(entity,msg['id'],decision,'Minha observação.',text_sha256=hashlib.sha256(text.encode()).hexdigest())
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            out=routine.history_snapshot(self.home,self.fixture.root,entity)
            rows,_=teacher.read_snapshot(teacher.source_dir(self.home)/out['snapshot'],entity)
            self.assertEqual([r['human_feedback']['decision'] for r in rows],['liked','disliked'])
            self.assertTrue(all(r['human_feedback']['entity']==entity for r in rows))
            self.assertTrue(all(r['human_feedback']['purpose']=='quality_feedback_not_training_approval' for r in rows))
            self.assertEqual(rows[1]['messages'][-1]['content'],f'Resposta {entity} 1')
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertFalse(routine.config(self.home)['automatic_data_approval'])

    def auto_night(self):
        routine.configure(self.home,{'confirm':True,'settings':{'automatic_data_approval':True}})
        self.supervisor.night=dict(id='c'*16,state='running',deadline=9999999999,restore_entities=['hoshino'],
            index=0,job=None,history=[],automatic_cycle=True,policy=routine.config(self.home),
            learning={'hoshino':dict(phase='curate',attempt=1,failures=[],dataset='pacote_identidade_v6:hoshino',stable_before={'available':False})},
            tasks=[dict(action='learn',model='qwen35-9b',entity='hoshino',minutes=1,examples=8)])
        self.supervisor.laboratory_maintenance=True
        return self.supervisor.night

    def test_second_attempt_has_concrete_feedback_but_crash_never_replays(self):
        obj=self.auto_night();obj.update(job='a'*16,job_kind='teacher')
        with patch.object(lab,'_busy',return_value=None),patch.object(teacher,'detail',return_value={'state':'needs_revision','error':'Autoria incorreta'}):
            routine.learn_tick(self.supervisor,obj['tasks'][0],1)
        state=obj['learning']['hoshino'];self.assertEqual(state['attempt'],2)
        self.assertEqual(state['phase'],'prepare');self.assertIn('Autoria incorreta',json.dumps(state['feedback']))
        state['phase']='curate';obj.update(job='b'*16,job_kind='teacher')
        with patch.object(lab,'_busy',return_value=None),patch.object(teacher,'detail',return_value={'state':'interrupted_unverified'}),\
             patch('laboratorio.versionamento_lora.stable_status',return_value={'available':False}),patch.object(lab,'start') as run:
            routine.learn_tick(self.supervisor,obj['tasks'][0],2);run.assert_not_called()
        self.assertEqual(state['phase'],'failed');self.assertTrue(state['original_retained'])
        self.assertEqual(obj['index'],1)

    def test_success_requires_evaluation_promotion_not_completed_worker(self):
        obj=self.auto_night();state=obj['learning']['hoshino'];state.update(phase='evaluate',attempt=2)
        obj.update(job='a'*16,job_kind='training')
        with patch.object(lab,'_busy',return_value=None),patch.object(lab,'details',return_value={'state':'completed','automatic_promotion':{'promoted':False,'reasons':['holdout_regressed']}}),\
             patch('laboratorio.versionamento_lora.stable_status',return_value={'available':False}):
            routine.learn_tick(self.supervisor,obj['tasks'][0],2)
        self.assertEqual(state['phase'],'failed');self.assertTrue(obj['failures'])
        obj=self.auto_night();state=obj['learning']['hoshino'];state['phase']='evaluate';obj.update(job='b'*16,job_kind='training')
        with patch.object(lab,'_busy',return_value=None),patch.object(lab,'details',return_value={'state':'completed','automatic_promotion':{'promoted':True}}):
            routine.learn_tick(self.supervisor,obj['tasks'][0],3)
        self.assertEqual(state['phase'],'done');self.assertEqual(obj['index'],1)

    def test_unknown_worker_failure_has_no_concrete_correction_so_is_not_replayed(self):
        obj=self.auto_night();obj.update(job='a'*16,job_kind='teacher')
        with patch.object(lab,'_busy',return_value=None),patch.object(teacher,'detail',return_value={'state':'failed','error':'RuntimeError desconhecido'}),\
             patch('laboratorio.versionamento_lora.stable_status',return_value={'available':False}):
            routine.learn_tick(self.supervisor,obj['tasks'][0],1)
        self.assertEqual(obj['learning']['hoshino']['phase'],'failed')
        self.assertEqual(obj['learning']['hoshino']['attempt'],1)

    def test_waiting_worker_does_not_rewrite_night_file_every_tick(self):
        obj=self.auto_night();obj.update(job='a'*16,job_kind='teacher')
        with patch.object(lab,'_busy',return_value='Worker releasing GPU'),\
             patch.object(teacher,'detail',return_value={'state':'running'}),patch.object(lab,'night_save') as save:
            self.supervisor.night_tick();self.supervisor.night_tick()
            save.assert_not_called()

    def test_complete_learning_sequence_no_overlapping_workers(self):
        obj=self.auto_night();state=obj['learning']['hoshino']
        obj.update(job='a'*16,job_kind='teacher')
        with patch.object(lab,'_busy',return_value=None),patch.object(teacher,'detail',return_value={'state':'proposed'}),\
             patch.object(routine,'approve_data',return_value={'dataset':'importados:own'}),\
             patch.object(lab,'start',return_value={'id':'b'*16}) as start:
            routine.learn_tick(self.supervisor,obj['tasks'][0],1);self.assertEqual(state['phase'],'approve');start.assert_not_called()
            routine.learn_tick(self.supervisor,obj['tasks'][0],2);self.assertEqual(state['phase'],'train');start.assert_not_called()
            routine.learn_tick(self.supervisor,obj['tasks'][0],3);self.assertEqual(obj['job'],'b'*16)
        with patch.object(lab,'_busy',return_value='Worker still owns GPU'),patch.object(lab,'details',return_value={'state':'completed','artifact':'own-candidate'}):
            routine.learn_tick(self.supervisor,obj['tasks'][0],4)
        self.assertEqual(obj['job'],'b'*16)
        with patch.object(lab,'_busy',return_value=None),patch.object(lab,'details',return_value={'state':'completed','artifact':'own-candidate'}):
            routine.learn_tick(self.supervisor,obj['tasks'][0],5)
        self.assertEqual(state['phase'],'evaluate')
        with patch.object(lab,'_busy',return_value=None),patch.object(lab,'start',return_value={'id':'c'*16}) as start:
            routine.learn_tick(self.supervisor,obj['tasks'][0],6)
            self.assertEqual(start.call_args.kwargs['candidate'],'own-candidate');self.assertEqual(start.call_args.kwargs['dataset'],'importados:own')

    def test_agenda_prevents_poweroff_wakes_responsible_sleeping_entity(self):
        obj=self.auto_night()
        with patch.object(routine,'agenda',return_value=[{'entity':'lilith','id':'task','due':10000}]),patch.object(routine,'guard') as guard:
            self.assertFalse(routine.finish(self.supervisor,1));guard.assert_not_called()
        self.assertEqual(obj['restore_entities'],['hoshino','lilith'])
        self.assertFalse(self.supervisor.night_poweroff_requested)

    def test_poweroff_is_fixed_command_only_after_cooperative_gate_no_retry(self):
        obj=self.auto_night()
        with patch.object(routine,'agenda',return_value=[]),patch.object(routine,'guard',return_value={'agenda':[]}):
            self.assertTrue(routine.finish(self.supervisor,1))
        with patch.object(routine,'guard',return_value={'agenda':[]}),patch('subprocess.run',return_value=Mock(returncode=1)) as run:
            out=routine.poweroff(self.supervisor)
        self.assertFalse(out['accepted']);run.assert_called_once()
        self.assertEqual(run.call_args.args[0],['/usr/bin/systemctl','poweroff','--no-block','--no-ask-password'])
        self.assertEqual(obj['poweroff_state'],'unconfirmed_no_retry')
        with patch('subprocess.run') as run:
            self.assertFalse(routine.poweroff(self.supervisor)['accepted']);run.assert_not_called()

    def test_short_window_prioritizes_entities_skipped_last_night(self):
        policy=dict(routine.config(self.home),enabled=True,automatic_data_approval=True,window_minutes=360)
        now=datetime(2026,10,13,0,45,tzinfo=ZoneInfo(policy['timezone'])).timestamp()
        def measured(home,model,entity,minutes,action):
            return dict(allowed=True,model={'benchmarks':{entity:{'preset':{'rank':4}}}})
        with patch.object(routine,'config',return_value=policy),patch.object(routine,'guard',return_value={'idle':1800,'agenda':[]}),\
             patch.object(lab,'plan',side_effect=measured),patch.object(lab,'night_status',return_value={'skipped':[{'entity':'alistair'}]}),\
             patch.object(self.supervisor,'authorize_night',return_value={'id':'d'*16,'state':'draining'}) as start:
            routine.auto_tick(self.supervisor,now=now)
        self.assertEqual([t['entity'] for t in start.call_args.args[0]['tasks']],['alistair'])
        self.assertEqual(self.supervisor.night_readiness['state'],'authorized')

    def test_automatic_tick_is_once_per_date_and_no_permission_no_start(self):
        policy=dict(routine.config(self.home),enabled=True,automatic_data_approval=True,entities=['hoshino'])
        now=datetime(2026,10,13,0,45,tzinfo=ZoneInfo(policy['timezone'])).timestamp()
        spec=dict(self.spec,entity='hoshino',model={'benchmarks':{'hoshino':{'preset':{'rank':4}}}})
        with patch.object(routine,'config',return_value=policy),patch.object(routine,'guard',return_value={'idle':1800,'agenda':[]}),\
             patch.object(lab,'plan',return_value=spec),patch.object(self.supervisor,'authorize_night',return_value={'id':'d'*16,'state':'running'}) as start:
            routine.auto_tick(self.supervisor,now=now);start.assert_called_once()
            routine.auto_tick(self.supervisor,now=now+31);start.assert_called_once()
        self.supervisor.night_next_probe=0
        # A noite já salva impede replay mesmo num novo supervisor.
        with patch.object(routine,'config',return_value=policy),patch.object(routine,'guard') as guard:
            routine.auto_tick(self.supervisor,now=now+100);guard.assert_not_called()

    def test_auto_data_rejects_partial_or_legacy_proposal_without_export(self):
        for proposal in ({},{'quality_audit':{'passed':True,'complete_batches':False}},
                         {'quality_audit':{'passed':True,'complete_batches':True,'filter_version':'v1.9.0'}}):
            with patch.object(teacher,'detail',return_value={'state':'proposed','proposal_data':proposal}),patch.object(teacher,'approved_export') as export:
                with self.assertRaises(RuntimeError):routine.approve_data(self.home,'a'*16,'pacote_identidade_v6:hoshino')
                export.assert_not_called()

    def test_night_export_preserves_assisted_curation_provenance(self):
        routine.configure(self.home,{'confirm':True,'settings':{'automatic_data_approval':True}})
        jid='a'*16;ids=['fixture:'+str(i) for i in range(8)]
        proposal=dict(generation_version='v1.12',requires_human_curation=True,
            examples=[dict(source_id=sid) for sid in ids],quality_audit=dict(passed=True,complete_batches=True,
                filter_version=teacher.QUALITY_FILTER_VERSION,categories=['naturalidade','personalidade','memoria','instrucao'],
                teacher_semantic_reviews=[dict(reviews=[dict(source_id=sid,concerns=[],reason='Fixture.') for sid in ids])]))
        metrics=self.home/teacher.ROOT_REL/'metricas'/(jid+'.json');metrics.parent.mkdir(parents=True)
        metrics.write_text(json.dumps(dict(pressure=[],samples=[{}],margin_bytes=768*1024**2,after={'known':True})))
        folder=self.home/'datasets-importados'/'fixture';folder.mkdir(parents=True)
        file=folder/'origem_professor.json';file.write_text(json.dumps(dict(human_approved=False,assisted_approved_count=8)))
        with patch.object(teacher,'detail',return_value={'state':'proposed','proposal_data':proposal}),\
             patch.object(teacher,'human_decision',return_value='approved'),\
             patch.object(teacher,'approved_export',return_value={'dataset':'importados:fixture'}),\
             patch.object(routine,'token_budget',return_value={'max_tokens':100}):
            routine.approve_data(self.home,jid,'pacote_identidade_v6:hoshino')
        marker=json.loads(file.read_text());self.assertFalse(marker['human_approved'])
        self.assertEqual(marker['approval'],'assisted_curated_night_quality_gates_v1')

    def test_unknown_agenda_prevents_shutdown_without_restore_loop(self):
        obj=self.auto_night()
        with patch.object(routine,'agenda',side_effect=RuntimeError('DB inacessível')):
            self.assertFalse(routine.finish(self.supervisor,1))
        self.assertIn('Agenda não verificável',obj['shutdown_blocked'])

    def test_short_window_does_not_replay_or_launch_unbudgeted_learning(self):
        policy=dict(routine.config(self.home),enabled=True,automatic_data_approval=True,window_minutes=30,entities=['hoshino'])
        now=datetime(2026,10,13,0,45,tzinfo=ZoneInfo(policy['timezone'])).timestamp()
        spec=dict(self.spec,entity='hoshino',model={'benchmarks':{'hoshino':{}}})
        with patch.object(routine,'config',return_value=policy),patch.object(routine,'guard',return_value={'idle':1800,'agenda':[]}),\
             patch.object(lab,'plan',return_value=spec),patch.object(self.supervisor,'authorize_night') as start:
            routine.auto_tick(self.supervisor,now=now);start.assert_not_called()
        self.assertEqual(self.supervisor.night_readiness['state'],'waiting')

    def test_manual_restart_preview_refuses_automatic_replay(self):
        obj=self.auto_night();obj['state']='recovery_required';lab.night_save(self.home,obj)
        with self.assertRaises(RuntimeError):lab.resume_night_tasks(self.home)

    def test_real_guard_rejects_active_user_unknown_gpu_and_pending_messages(self):
        from core import world_state,gpu_metrics
        values={'collector.health':{'running':True},'desktop.idle_seconds':1900,'system.load1':0.1,'system.cpu_count':8}
        measured=dict(known=True,stable=True,utilization=0,used_bytes=200000000,total_bytes=8*1024**3)
        with patch.object(world_state,'snapshot',return_value={}),patch.object(world_state,'fresh_values',return_value=values),\
             patch.object(gpu_metrics,'snapshot',return_value=measured),patch.object(gpu_metrics,'ram_available',return_value=24*1024**3),\
             patch.object(routine,'agenda',return_value=[]),patch.object(lab,'_busy',return_value=None),\
             patch.object(fixture.rm,'status',return_value=[]),patch.object(fixture.rm,'gpu_state',return_value={'queue':[]}),\
             patch.object(fixture.job_bus,'status',return_value=[]),patch.object(fixture.bus,'pending_wake_requests',return_value=[]),\
             patch.object(fixture.bus,'presence',return_value={'status':'sleeping'}),patch.object(fixture.bus,'inbox',return_value=[]) as inbox:
            self.assertEqual(routine.guard(self.supervisor,routine.DEFAULTS)['idle'],1900)
            values['desktop.media']={'estado':'Tocando'}
            with self.assertRaises(RuntimeError):routine.guard(self.supervisor,routine.DEFAULTS)
            values['desktop.media']={'estado':'Paused','titulo':'Playing in the dark'}
            self.assertEqual(routine.guard(self.supervisor,routine.DEFAULTS)['idle'],1900)
            values['desktop.media']={'titulo':'estado desconhecido'}
            with self.assertRaises(RuntimeError):routine.guard(self.supervisor,routine.DEFAULTS)
            values.pop('desktop.media')
            values['desktop.idle_seconds']=10
            with self.assertRaises(RuntimeError):routine.guard(self.supervisor,routine.DEFAULTS)
            values['desktop.idle_seconds']=1900;measured['known']=False
            with self.assertRaises(RuntimeError):routine.guard(self.supervisor,routine.DEFAULTS)
            measured['known']=True;inbox.return_value=[{'outcome':'uncertain'}]
            with self.assertRaises(RuntimeError):routine.guard(self.supervisor,routine.DEFAULTS)
            self.assertFalse(inbox.call_args.kwargs['mark_delivered'])
