"""Continuidade restrita e contexto: bancos temporários, sem entidades/modelos reais."""
import copy
import os
if os.environ.get('HOSHINO_TEST_OFFLINE')!='1':
    raise SystemExit('Use testes/executar_isolado.py; este grupo exige isolamento de bancos/serviços.')
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import patch

import config
from alistair_runner import Alistair, ActionUncertain, conversation_system, simple_conversation
from core import alistair_continuity as continuity, interentity as bus, job_bus, resource_manager


def presentation(target='lilith', text='Sou Alistair. Cuido da organização nesta casa.'):
    return {'message': {'role': 'assistant', 'tool_calls': [{'function': {
        'name': 'entidades_enviar_mensagem',
        'arguments': {'entidade': target, 'texto': text, 'acordar': True}}}]}}


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.tmp.name)
        identity=self.root/'identity.json';identity.write_text('{"nome":"Alistair","personality":{"traits":["formal"]}}')
        for obj,key,value in [(config,'RAIZ',self.root),(config,'DB_PATH',self.root/'mind.db'),
                              (config,'SELF_MODEL_PATH',identity),(config,'NUM_CTX',8192),(config,'NUM_PREDICT',768),
                              (bus,'DB_PATH',self.root/'bus.db'),(job_bus,'DB_PATH',self.root/'jobs.db'),
                              (resource_manager,'DB_PATH',self.root/'rm.db'),(resource_manager,'LOCK_DIR',self.root/'locks')]:
            self.stack.enter_context(patch.object(obj,key,value))
        for target,value in [('alistair_runner.alistair_backend.configured',None),
                             ('core.activity_context.build',({},'')),('core.diagnostics.emit',None),
                             ('alistair_runner.world_state.brief',{})]:
            self.stack.enter_context(patch(target,return_value=value))
        self.al=Alistair();self.store=continuity.Store(self.al.db_path)

    def message(self,text='Acorde Lilith e se apresente.',sender='usuario',session='one'):
        sent=bus.send(sender,'alistair',text)
        return dict(id=sent['id'],sender=sender,text=text,metadata={'conversation_session_id':session})

    def sent(self):
        return [m for m in bus.conversation('alistair','lilith') if m['sender']=='alistair']

    def run_intro(self,message=None,awake=False):
        if awake:bus.register('lilith',status='awake')
        message=message or self.message()
        with patch.object(self.al,'infer',return_value=presentation())as infer:
            output=self.al.chat(message)
        return output,infer

    def test_recognizer_accepts_only_clear_complete_single_target_request(self):
        for text,target in [('voce pode comçar a acordar a lilith e se apresentar a ela','lilith'),
                            ('Alistair, por favor, acorde Hoshino e apresente-se a ela.','hoshino'),
                            ('Pode despertar a Lilith e se apresentar?','lilith')]:
            with self.subTest(text=text):self.assertEqual(continuity.presentation_request(text),target)
        for text in ['Não acorde Lilith e se apresente.', 'Explique como acordar Lilith e se apresentar.',
                     '"Acorde Lilith e se apresente"', 'Acorde Lilith e se apresente quando eu autorizar.',
                     'Acorde Lilith e se apresente depois de amanhã.', 'Se eu disser acorde Lilith e se apresente',
                     'Acorde Lilith e se apresente à Hoshino.', 'Acorde Lilith e Hoshino e se apresente.',
                     'Acorde Lilith e apresente meu amigo.', 'Imagine acorde Lilith e se apresente',
                     'Acorde Lilith e se apresente e apague seus arquivos.']:
            with self.subTest(text=text):self.assertIsNone(continuity.presentation_request(text))

    def test_voice_ambiguity_asks_before_waking_or_creating_a_task(self):
        message=self.message('Acorde Lilith e se apresente.')
        message['metadata']['audio_job_id']='fixture-audio'
        with patch.object(self.al,'infer',return_value={'message':{'content':json.dumps({
                'status':'clarify','question':'Você quis dizer Lilith ou Hoshino?'})}}) as infer:
            output=self.al.chat(message)
        self.assertEqual(output,'Você quis dizer Lilith ou Hoshino?')
        infer.assert_called_once();self.assertEqual(self.sent(),[])
        self.assertNotIn('format',infer.call_args.args[0])  # Backend Xbox preservado.
        self.assertEqual(infer.call_args.args[0]['tools'],[])
        with closing(sqlite3.connect(self.al.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM alistair_actions WHERE id LIKE 'dialogue-task:%'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT input FROM alistair_turns WHERE source_id=?',(message['id'],)).fetchone()[0],message['text'])

    def test_understood_voice_continues_normally_without_rewriting(self):
        message=self.message('Olá, Alistair!');message['metadata']['audio_job_id']='fixture-audio'
        replies=[{'message':{'content':'{"status":"understood","question":""}'}},
                 {'message':{'role':'assistant','content':'Olá!'}}]
        with patch.object(self.al,'infer',side_effect=replies) as infer:
            self.assertEqual(self.al.chat(message),'Olá!')
        self.assertEqual(infer.call_count,2)
        users=[m['content'] for m in infer.call_args_list[-1].args[0]['messages'] if m['role']=='user']
        self.assertEqual(users[-1],message['text'])

    def test_invalid_voice_review_does_not_execute_or_repeat_the_request(self):
        from core import speech_perception
        message=self.message('Acorde Lilith e se apresente.');message['metadata']['audio_job_id']='fixture-audio'
        with patch.object(self.al,'infer',return_value={'message':{'content':'vou acordar'}}) as infer:
            self.assertEqual(self.al.chat(message),speech_perception.FALLBACK)
        infer.assert_called_once();self.assertEqual(self.sent(),[])

    def test_pending_receipt_not_presence_and_no_delivery_side_effect(self):
        original=self.message();before=copy.deepcopy(original)
        output,infer=self.run_intro(original)
        self.assertIn('despertar ainda não está confirmado',output)
        self.assertNotIn('está acordada',output);self.assertEqual(infer.call_count,1)
        sent=self.sent();self.assertEqual(len(sent),1)
        self.assertEqual(sent[0]['sender'],'alistair');self.assertTrue(sent[0]['wake_requested'])
        self.assertIsNone(sent[0]['delivered_at']);self.assertIsNone(sent[0]['read_at'])
        self.assertEqual(original,before)
        task=self.store.select(self.message('continue'))
        self.assertEqual(task['receipt']['id'],sent[0]['id'])

    def test_fresh_awake_status_does_not_claim_read_or_response(self):
        output,_=self.run_intro(awake=True)
        self.assertIn('está acordada',output);self.assertIn('não confirma que ela já leu ou respondeu',output)
        self.assertEqual(self.store.select(self.message('continue'))['state'],'completed')
        self.assertFalse(self.sent()[0]['wake_requested'])

    def test_restart_and_multiple_continuations_never_resend_or_infer(self):
        self.run_intro();self.al=Alistair()
        bus.register('lilith',status='awake')
        with patch.object(self.al,'infer')as infer,patch.object(bus,'send',wraps=bus.send)as send:
            first=self.message('continue');send.reset_mock()
            self.assertIn('está acordada',self.al.chat(first));send.assert_not_called()
            again=self.message('eu autorizo');send.reset_mock()
            self.al.chat(again);send.assert_not_called();infer.assert_not_called()
        self.assertEqual(len(self.sent()),1)

    def test_same_input_replay_returns_committed_output_without_effect(self):
        message=self.message();output,_=self.run_intro(message)
        with patch.object(self.al,'infer')as infer,patch.object(bus,'send')as send:
            self.assertEqual(self.al.chat(message),output)
            infer.assert_not_called();send.assert_not_called()

    def test_deleted_presentation_is_not_claimed_or_replayed(self):
        self.run_intro();mid=self.sent()[0]['id']
        with closing(sqlite3.connect(bus.DB_PATH))as db,db:
            db.execute("UPDATE entity_messages SET text='',kind='deleted' WHERE id=?",(mid,))
        message=self.message('continue')
        with patch.object(self.al,'infer')as infer,patch.object(bus,'send')as send:
            with self.assertRaises(ActionUncertain):self.al.chat(message)
            infer.assert_not_called();send.assert_not_called()

    def test_continuation_is_scoped_to_human_and_session(self):
        self.run_intro()
        self.assertIsNone(self.store.select(self.message('continue',session='other')))
        self.assertIsNone(self.store.select(self.message('continue',sender='hoshino')))
        self.assertIsNone(self.store.select(self.message(sender='lilith')))

    def test_unrelated_message_suspends_and_cancel_never_resumes(self):
        self.run_intro()
        self.assertIsNone(self.store.select(self.message('Vamos falar de astronomia.')))
        self.assertIsNone(self.store.select(self.message('continue')))
        self.store.select(self.message())
        self.store.select(self.message('cancele'))
        self.assertIsNone(self.store.select(self.message('continue')))

    def test_task_expires_without_background_action(self):
        task=self.store.select(self.message())
        with patch.object(continuity.time,'time',return_value=time.time()+86401):
            self.assertIsNone(self.store.select(self.message('continue')))
        self.assertEqual(self.sent(),[])

    def test_old_chat_without_new_task_is_not_adopted(self):
        with closing(sqlite3.connect(self.al.db_path))as db,db:
            db.execute('INSERT INTO alistair_turns VALUES(?,?,?,?,?)',('old','usuario',self.message()['text'],'Vou apresentar.',0))
        self.assertIsNone(self.store.select(self.message('continue')))

    def test_missing_task_receipt_recovers_existing_action_without_resend(self):
        save=continuity.Store.save
        def fail_receipt(store,task):
            if task.get('receipt'):raise OSError('simulated interruption before task receipt')
            return save(store,task)
        with patch.object(continuity.Store,'save',new=fail_receipt):
            with self.assertRaises(OSError):self.run_intro()
        self.assertEqual(len(self.sent()),1);self.al=Alistair()
        message=self.message('continue')
        with patch.object(self.al,'infer')as infer,patch.object(bus,'send')as send:
            self.assertIn('registrada',self.al.chat(message));infer.assert_not_called();send.assert_not_called()
        self.assertEqual(len(self.sent()),1)

    def test_uncertain_effect_stays_blocked_even_after_restart(self):
        call=self.al.call_tool
        def interrupted(name,args):
            result=call(name,args)
            if name=='entidades_enviar_mensagem':raise OSError('simulated interruption after effect')
            return result
        with patch.object(self.al,'call_tool',side_effect=interrupted):
            with self.assertRaises(ActionUncertain):self.run_intro()
        self.assertEqual(len(self.sent()),1);self.al=Alistair()
        message=self.message('continue')
        with patch.object(self.al,'call_tool')as execute,patch.object(self.al,'infer')as infer:
            with self.assertRaises(ActionUncertain):self.al.chat(message)
            execute.assert_not_called();infer.assert_not_called()

    def test_wrong_target_is_rejected_without_effect(self):
        with patch.object(self.al,'infer',return_value=presentation('hoshino')):
            with self.assertRaises(RuntimeError):self.al.chat(self.message())
        self.assertEqual(self.sent(),[])
        self.assertEqual(bus.conversation('alistair','hoshino'),[])

    def test_plain_promise_is_not_committed_as_completion(self):
        promise={'message':{'role':'assistant','content':'Lilith acordou, vou me apresentar.'}}
        with patch.object(self.al,'infer',side_effect=[promise,presentation()])as infer:
            output=self.al.chat(self.message())
        self.assertNotIn('Lilith acordou',output);self.assertEqual(infer.call_count,2)
        self.assertEqual(len(self.sent()),1)

    def test_four_plain_promises_do_not_create_successful_turn(self):
        message=self.message()
        with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Vou fazer.'}}):
            with self.assertRaises(RuntimeError):self.al.chat(message)
        with closing(sqlite3.connect(self.al.db_path))as db:
            self.assertIsNone(db.execute('SELECT output FROM alistair_turns WHERE source_id=?',(message['id'],)).fetchone())
        self.assertEqual(self.sent(),[])

    def test_all_required_permissions_are_checked_before_inference(self):
        for denied in ['entidades_acordar','entidades_enviar_mensagem','central_estado']:
            with self.subTest(tool=denied),patch('core.ui_policy.disabled',return_value={denied}),patch.object(self.al,'infer')as infer:
                with self.assertRaises(ValueError):self.al.chat(self.message())
                infer.assert_not_called()
        self.assertEqual(self.sent(),[])

    def test_generic_send_cannot_bypass_disabled_wake(self):
        with patch('core.ui_policy.disabled',return_value={'entidades_acordar'}):
            with self.assertRaises(ValueError):self.al.call_tool('entidades_enviar_mensagem',{
                'entidade':'lilith','texto':'Oi.','acordar':True})
        self.assertEqual(self.sent(),[])

    def test_physical_message_mismatch_stops_without_resend(self):
        original=bus.send
        def different(sender,target,text,**kwargs):return original(sender,target,'different',**kwargs)
        message=self.message()
        with patch.object(bus,'send',side_effect=different),patch.object(self.al,'infer',return_value=presentation()):
            with self.assertRaises(ActionUncertain):self.al.chat(message)
        with patch.object(self.al,'infer')as infer:
            with self.assertRaises(ActionUncertain):self.al.chat(self.message('continue'))
            infer.assert_not_called()
        self.assertEqual(len(self.sent()),1)

    def test_no_schema_changes_and_task_is_not_factual_recall(self):
        with closing(sqlite3.connect(self.al.db_path))as db:
            before=db.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        self.run_intro()
        with closing(sqlite3.connect(self.al.db_path))as db:
            self.assertEqual(before,db.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
            text=db.execute('SELECT input FROM alistair_turns').fetchone()[0]
            self.assertNotIn('dialogue-task:',text)

    def test_system_prefix_stable_without_ephemeral_ids_or_snapshots(self):
        first={'id':'message-one','sender':'usuario','created_at':'old'}
        second={'id':'message-two','sender':'usuario','created_at':'new'}
        identity=copy.deepcopy(self.al.identity)
        a=conversation_system(identity,first,{'presence':'old'},[],{'scanned':1})
        b=conversation_system(identity,second,{'presence':'new'},[],{'scanned':15})
        self.assertEqual(a,b);self.assertEqual(identity,self.al.identity)
        self.assertIn('Eu sou Alistair.',a);self.assertIn('formal',a);self.assertNotIn('message-one',a)

    def test_fixed_personality_projection_keeps_configured_content_and_custom_fields(self):
        identity={'identity':{'name':'Alistair','nature':'Natureza própria','self_concept':'Papel próprio','custom':'Detalhe próprio'},
            'personality':{'traits':['formal','prestativo'],'communication_style':['direto'],'custom':'Tom próprio'},
            'cognitive_framework':['Regra própria'],'custom':'Configuração própria','custom_flag':False,'custom_zero':0}
        before=copy.deepcopy(identity)
        text=conversation_system(identity,{'sender':'usuario'},{},[],{})
        for value in ['Alistair','Natureza própria','Papel próprio','formal','prestativo','direto','Detalhe próprio','Tom próprio','Regra própria','Configuração própria']:
            self.assertIn(value,text)
        self.assertEqual(identity,before)
        self.assertIn('"custom_flag":false',text);self.assertIn('"custom_zero":0',text)

    def test_ambiguous_self_recipient_asks_once_without_effect_or_inference(self):
        message=self.message('Você poderia acordar a Lilith e se apresentar a Alistair.')
        with patch.object(self.al,'infer')as infer,patch.object(self.al,'call_tool')as execute:
            result=self.al.chat(message)
            self.assertIn('Quer que eu me apresente à Lilith?',result);self.assertIn('Ainda não enviei',result)
            self.assertNotIn('não tem autorização',result)
            self.assertEqual(self.al.chat(message),result)
            self.al.chat(self.message('continue'))
            infer.assert_not_called();execute.assert_not_called()
        self.assertEqual(self.sent(),[])

    def test_ambiguity_confirmation_is_scoped_and_effect_is_once_only(self):
        self.al.chat(self.message('Acorde Lilith e se apresente a Alistair.'))
        self.assertIsNone(self.store.select(self.message('sim',session='other')))
        self.assertIsNone(self.store.select(self.message('sim',sender='hoshino')))
        self.al=Alistair();confirmed=self.message('Sim, para a Lilith.')
        with patch.object(self.al,'infer',return_value=presentation())as infer:
            self.al.chat(confirmed);self.al.chat(confirmed);infer.assert_called_once()
        with patch.object(self.al,'infer')as infer:
            self.al.chat(self.message('continue'));infer.assert_not_called()
        self.assertEqual(len(self.sent()),1)

    def test_simple_conversation_omits_tools_but_compound_requests_do_not(self):
        for text in ['Olá!','Quem eu sou?','Você sabe quem eu sou?','Qual é o seu nome?']:
            self.assertTrue(simple_conversation(text),text)
            with patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Resposta de fixture.'}})as infer:
                self.al.chat(self.message(text));self.assertEqual(infer.call_args.args[0]['tools'],[])
        for text in ['Quem eu sou? Acorde Lilith.','Olá! Que horas são?','Consulte o estado da Lilith.']:
            self.assertFalse(simple_conversation(text),text)

    def test_simple_greeting_cannot_execute_hallucinated_tool_call(self):
        with patch.object(self.al,'infer',side_effect=[presentation(),{'message':{'role':'assistant','content':'Olá.'}}]),patch.object(self.al,'_once')as execute:
            self.al.chat(self.message('Olá!'));execute.assert_not_called()
        self.assertEqual(self.sent(),[])

    def test_conversation_projection_not_in_prompt_and_no_unrequested_snapshot(self):
        with (patch('core.activity_context.build',return_value=({'activity':'conversation'},'MUTABLE_ACTIVITY_FIXTURE')),
              patch.object(self.al,'snapshot')as snapshot,
              patch.object(self.al,'infer',return_value={'message':{'role':'assistant','content':'Olá.'}})as infer):
            self.al.chat(self.message('Oi.'))
        self.assertNotIn('MUTABLE_ACTIVITY_FIXTURE',infer.call_args.args[0]['messages'][0]['content'])
        snapshot.assert_not_called()


if __name__=='__main__':unittest.main()
