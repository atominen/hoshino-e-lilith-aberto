"""Autonomia/retomada em bancos descartáveis; sem LLM/rede/desktop reais."""
import asyncio
from contextlib import closing
from datetime import datetime,timedelta
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import AsyncMock,Mock,patch

import config
from core import initiative,autonomy,dispatch,compaction,resource_manager,state_file,kernel
from mind import drives
from test_iniciativa_interna import Fixture


def call(name,**arguments):
    return {'role':'assistant','content':'','tool_calls':[{'function':{'name':name,'arguments':arguments}}]}


class PersistentTests(Fixture):
    def app(self):
        import main
        with patch.object(main,'semear_origem'):
            app=main.InterfaceHoshino()
        app.sys_log=Mock();app.chat_log=Mock();app.situacao=dict(self.situation)
        return app

    def test_working_point_preserves_goal_next_step_and_individual_authorship(self):
        value=json.loads(initiative.manage('atualizar',objetivo='Meu projeto de teste',
            proximo_passo='Verificar o protótipo',nota='Escolhi estudar este projeto.',capacidades=['programacao']))
        self.assertTrue(value['verified']);self.assertTrue(initiative.resumable())
        again=initiative.activity()
        self.assertEqual(again['objetivo'],'Meu projeto de teste')
        self.assertEqual(again['authored_by'],'hoshino')
        self.assertIn('Escolhi estudar',initiative.context())
        self.assertEqual(self.rows('select count(*) from goals')[0][0],0)

    def test_context_and_observation_are_private_not_promoted_to_facts(self):
        initiative.note('Resumo escolhido por mim.')
        initiative.record_observation('calcular','receipt-1',{'expressao':'2+2'},
            {'status':'success','output':'4','mutates':False})
        with patch('memory.audience.public_turn',return_value=True):
            self.assertEqual(initiative.context(),'')
            self.assertTrue(initiative.manage().startswith('ACESSO_BLOQUEADO'))
        ctx=json.loads(self.rows("select context from episodes where source='initiative_checkpoint'")[0][0])
        self.assertFalse(ctx['human_conversation']);self.assertFalse(ctx['quality_approved'])
        self.assertEqual(self.rows('select count(*) from memories')[0][0],0)

    def test_complete_result_can_be_recovered_by_exact_receipt_in_pages(self):
        output='abcd'*6000
        for _ in range(2):
            initiative.record_observation('listar_oficina','receipt-full',{},
                {'status':'success','output':output,'mutates':False})
        self.assertEqual(self.rows("select count(*) from episodes where source='initiative_observation'")[0][0],1)
        pages=[]
        for start in range(0,len(output),4000):
            page=json.loads(initiative.manage('ler_resultado',recibo='receipt-full',inicio=start,limite=4000))
            pages.append(page['output']);self.assertEqual(page['total_chars'],len(output))
        self.assertEqual(''.join(pages),output)
        self.assertIn('omitted_chars',initiative.context())

    def test_receipt_collision_does_not_replace_or_misidentify_the_original(self):
        initiative.record_observation('calcular','same',{},
            {'status':'success','output':'original','mutates':False})
        with self.assertRaises(ValueError):
            initiative.record_observation('calcular','same',{},
                {'status':'success','output':'different','mutates':False})
        self.assertEqual(json.loads(initiative.manage('ler_resultado',recibo='same'))['output'],'original')

    def test_crashed_or_unfinished_turn_prevents_blind_restart(self):
        self.assertTrue(initiative.begin_turn('original-turn'))
        self.assertFalse(drives.pode_deliberar(datetime.now()+timedelta(days=1)))
        self.assertFalse(initiative.begin_turn('duplicate-turn'))
        self.assertFalse(initiative.finish_turn('other-turn','action'))
        self.assertTrue(initiative.finish_turn('original-turn','interrupted'))
        self.assertTrue(drives.pode_deliberar())

    def test_new_tools_follow_chosen_groups_and_existing_user_switch(self):
        initiative.manage('atualizar',capacidades=['programacao','conversa','computador'])
        names={s['function']['name'] for s in dispatch.esquemas(modo_operacao='autonomo_continuo')}
        self.assertTrue({'execute_command','workspace','entidades_enviar_mensagem','observar_tela'}<=names)
        self.assertNotIn('discord_enviar',names)
        handler=Mock(return_value='not executed')
        with patch.object(dispatch.ui_policy,'allowed',return_value=False),patch.dict(dispatch.HANDLERS,execute_command=handler):
            result=dispatch.executar_resultado('execute_command',{'command':'fixture'})
        handler.assert_not_called();self.assertEqual(result['status'],'error')

    def test_pending_command_keeps_exact_id_and_blocks_new_effect(self):
        initiative.record_observation('execute_command','receipt-job',{'command':'fixture'},
            {'status':'success','output':'accepted','mutates':True,'background_job':'job-deadbeef'})
        self.assertIn('ver_comando',initiative.allowed_tools())
        with autonomy.exploration_scope({'execute_command','ver_comando'},6,persistent=True):
            self.assertTrue(autonomy.authorize_exploration_tool('execute_command',{'command':'fixture'}))
            self.assertTrue(autonomy.authorize_exploration_tool('ver_comando',{'job_id':'job-aaaaaaaa'}))
            self.assertEqual(autonomy.authorize_exploration_tool('ver_comando',{'job_id':'job-deadbeef'}),'')
        initiative.record_observation('ver_comando','receipt-other',{'job_id':'job-aaaaaaaa'},
            {'status':'success','output':'done','mutates':False})
        self.assertIn('pending_command',initiative.activity())
        initiative.record_observation('ver_comando','receipt-done',{'job_id':'job-deadbeef'},
            {'status':'success','output':'done','mutates':False})
        self.assertNotIn('pending_command',initiative.activity())

    def test_failed_read_allows_reconsideration_but_uncertain_effect_does_not(self):
        with autonomy.exploration_scope({'calcular','ler_da_oficina'},6,persistent=True):
            autonomy.exploration_receipt('ler_da_oficina','read-failed',
                {'status':'error','output':'Erro: caminho não existe','mutates':False})
            self.assertEqual(autonomy.authorize_exploration_tool('calcular',{}),'')
            autonomy.exploration_receipt('calcular','uncertain',
                {'status':'uncertain','output':'unknown','mutates':True})
            self.assertTrue(autonomy.authorize_exploration_tool('calcular',{}))

    def test_authorial_note_is_not_thinking_or_automatic_quality_approval(self):
        with self.assertRaises(ValueError):initiative.note('<think>não é nota</think>')
        with self.assertRaises(ValueError):initiative.note('a'*1601)
        self.assertEqual(self.rows('select count(*) from episodes')[0][0],0)

    def test_working_notes_and_raw_results_do_not_trigger_or_pollute_reflection(self):
        from mind import reflection,daily_summary,night_reflection
        for index in range(15):
            initiative.note('Minha decisão curta '+str(index))
            initiative.record_observation('calcular','receipt-'+str(index),{},
                {'status':'success','output':'PRIVATE_RESULT_SENTINEL'*100,'mutates':False})
        self.assertEqual(reflection.episodios_desde_ultima(),0)
        self.assertEqual(reflection.material(),[])
        now=datetime.now().astimezone()
        self.assertNotIn('PRIVATE_RESULT_SENTINEL',daily_summary.prepare(agora=now)['prompt'])

    def test_denied_capability_does_not_grant_access_or_disable_other_choices(self):
        handler=Mock(return_value='should not run')
        with autonomy.exploration_scope({'calcular'},6,persistent=True),\
             patch.dict(dispatch.HANDLERS,desligar_internet=handler):
            denied=dispatch.executar_resultado('desligar_internet',{})
            self.assertTrue(autonomy.recoverable_result(denied))
            self.assertEqual(autonomy.authorize_exploration_tool('calcular',{}),'')
        handler.assert_not_called()

    def test_changed_owner_and_missing_database_never_create_or_share_a_new_mind(self):
        initiative.manage('atualizar',objetivo='Meu projeto')
        with patch.object(config,'ENTIDADE_ID','lilith'):
            with self.assertRaises(ValueError):initiative.activity()
        missing=self.root/'missing.sqlite3'
        with patch.object(config,'DB_PATH',str(missing)):
            with self.assertRaises(sqlite3.OperationalError):initiative.note('nota')
        self.assertFalse(missing.exists())

    def test_active_goal_can_resume_without_another_idle_period_or_human_prompt(self):
        initiative.manage('atualizar',objetivo='Meu projeto',proximo_passo='Conferir o resultado')
        drives.satisfazer('deliberacao_interna',self.now)
        self.assertFalse(drives.pode_deliberar(self.now+timedelta(seconds=config.INICIATIVA_CONTINUACAO_SEGUNDOS-1)))
        now=self.now+timedelta(seconds=config.INICIATIVA_CONTINUACAO_SEGUNDOS)
        self.assertTrue(drives.pode_deliberar(now))
        decision=kernel.deliberar(dict(self.situation,agora=now,segundos_sem_interacao_observados=0),
                                  self.pressures,{'atividade_pendente':True})
        self.assertEqual(decision['tipo'],'explorar')
        busy=kernel.deliberar(dict(self.situation,agora=now),self.pressures,
                             {'atividade_pendente':True,'ocupada':True})
        self.assertEqual(busy['tipo'],'nada')

    def test_legacy_block_release_requires_exact_reconciled_turn_and_keeps_evidence(self):
        from core import action_commentary
        action_commentary.record_deliberation('old','',
            [{'tool':'ler_da_oficina','receipt_id':'read-fixture','status':'error','verified':False,'mutates':False}], 'error')
        state_file.update(config.ESTADO_MENTE,lambda d:d.update(iniciativa_bloqueada={'turn_id':'old','outcome':'error'}))
        self.assertFalse(initiative.release_known_read_block('wrong','human fixture'))
        self.assertFalse(drives.pode_deliberar())
        self.assertTrue(initiative.release_known_read_block('old','human fixture, read only'))
        state=state_file.read(config.ESTADO_MENTE)
        self.assertNotIn('iniciativa_bloqueada',state)
        self.assertEqual(state['initiative_reconciliations'][0]['previous_block']['turn_id'],'old')

    def test_read_block_release_refuses_uncertain_or_mutating_receipts(self):
        from core import action_commentary
        for outcome,mutates in [('uncertain',False),('error',True)]:
            tid=outcome+str(mutates)
            action_commentary.record_deliberation(tid,'',
                [{'tool':'fixture','receipt_id':'fixture','status':outcome,'verified':False,'mutates':mutates}],outcome)
            state_file.update(config.ESTADO_MENTE,lambda d:d.update(iniciativa_bloqueada={'turn_id':tid,'outcome':outcome}))
            self.assertFalse(initiative.release_known_read_block(tid,'human fixture'))
            self.assertEqual(state_file.read(config.ESTADO_MENTE)['iniciativa_bloqueada']['turn_id'],tid)

    def test_projection_fits_real_budget_preserves_identity_pairs_and_original(self):
        original=[{'role':'system','content':'IDENTIDADE FIXA '*300},
            {'role':'user','content':'Minha escolha original'},
            call('listar_oficina'),
            {'role':'tool','tool_name':'listar_oficina','content':'resultado '*6000,'_receipt_id':'receipt-real'}]
        # A fonte integral existe antes de projetar o trecho para inferência.
        initiative.record_observation('listar_oficina','receipt-real',{},
            {'status':'success','output':original[-1]['content'],'mutates':False})
        projected,tools=compaction.activity_projection(original,None,context_max=8192,output_max=1024)
        self.assertLessEqual(resource_manager.context_requirement(projected,tools,output_max=1024)[1],8192)
        self.assertEqual(projected[0],original[0]);self.assertEqual(projected[1],original[1])
        self.assertEqual(projected[-2]['tool_calls'],original[-2]['tool_calls'])
        self.assertIn('receipt-real',projected[-1]['content'])
        self.assertEqual(len(original[-1]['content']),60000)

    def test_no_source_no_silent_discard_or_context_limit_increase(self):
        messages=[{'role':'system','content':'identidade'},
                  {'role':'tool','content':'x'*30000}]
        with self.assertRaises(ValueError):
            compaction.activity_projection(messages,None,context_max=2048,output_max=1024)
        self.assertEqual(len(messages[-1]['content']),30000)

    def test_model_can_choose_new_capabilities_and_run_code_with_existing_executor(self):
        app=self.app();handler=Mock(return_value=(
            'Arquivo: tmp/exec_fixture.py\nPasta de execução: . (raiz da oficina) — dentro do isolamento: '
            '/workspace\n[oficina | código 0]\n4'))
        app.chamar_modelo=AsyncMock(side_effect=[
            call('minha_atividade',operacao='atualizar',objetivo='Meu cálculo experimental',
                 capacidades=['programacao'],proximo_passo='Executar e conferir'),
            call('executar_na_oficina',codigo='print(2+2)'),
            {'role':'assistant','content':'O programa retornou 4; posso continuar meu experimento.'}])
        with patch.dict(dispatch.HANDLERS,executar_na_oficina=handler):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        handler.assert_called_once()
        names={s['function']['name'] for s in app.chamar_modelo.await_args_list[1].args[1]}
        self.assertIn('executar_na_oficina',names)
        self.assertNotIn('iniciativa_bloqueada',state_file.read(config.ESTADO_MENTE))
        self.assertIn('retornou 4',initiative.context())

    def test_queue_timeout_before_compute_defers_without_blocking_or_replaying(self):
        app=self.app();app.chamar_modelo=AsyncMock(side_effect=resource_manager.GPUWaitTimeout('fixture queue'))
        asyncio.run(app.explorar({'tipo':'explorar'}))
        app.chamar_modelo.assert_awaited_once()
        state=state_file.read(config.ESTADO_MENTE)
        self.assertNotIn('iniciativa_bloqueada',state)
        self.assertNotIn('initiative_inflight',state)
        self.assertEqual(state['last_activity_turn']['outcome'],'deferred')

    def test_cooperative_queue_pause_keeps_prior_receipt_without_permanent_block(self):
        app=self.app()
        app.chamar_modelo=AsyncMock(side_effect=[
            call('minha_atividade',operacao='consultar'),
            resource_manager.GPUCancelledBeforeCompute('fixture pause before grant')])
        asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(app.chamar_modelo.await_count,2)
        state=state_file.read(config.ESTADO_MENTE)
        self.assertNotIn('iniciativa_bloqueada',state)
        self.assertNotIn('initiative_inflight',state)
        self.assertEqual(state['last_activity_turn']['outcome'],'interrupted')
        with closing(initiative._connection()) as db:
            count=db.execute("SELECT COUNT(*) FROM episodes WHERE source='initiative_observation'").fetchone()[0]
        self.assertEqual(count,1)  # A consulta anterior não é refeita nem perdida.

    def test_generic_interruption_is_not_assumed_to_be_a_safe_queue_pause(self):
        app=self.app();app.chamar_modelo=AsyncMock(side_effect=InterruptedError('unknown execution phase'))
        asyncio.run(app.explorar({'tipo':'explorar'}))
        state=state_file.read(config.ESTADO_MENTE)
        self.assertEqual(state['last_activity_turn']['outcome'],'error')
        self.assertEqual(state['iniciativa_bloqueada']['outcome'],'error')

    def test_real_read_error_reaches_model_and_does_not_permanently_block_life(self):
        app=self.app();reader=Mock(return_value='Erro: arquivo não existe na oficina.')
        calculator=Mock(return_value='4')
        app.chamar_modelo=AsyncMock(side_effect=[call('ler_da_oficina',caminho='missing.txt'),
            call('calcular',expressao='2+2'),{'role':'assistant','content':'A leitura falhou; fiz uma conta diferente, que retornou4.'}])
        with patch.dict(dispatch.HANDLERS,ler_da_oficina=reader,calcular=calculator):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        reader.assert_called_once();calculator.assert_called_once()
        self.assertNotIn('iniciativa_bloqueada',state_file.read(config.ESTADO_MENTE))
        self.assertEqual(app.chamar_modelo.await_count,3)

    def test_workspace_read_is_not_misclassified_as_a_failed_mutation(self):
        reader=Mock(return_value='Erro: arquivo não existe.')
        with autonomy.exploration_scope({'workspace','calcular'},6,persistent=True),\
             patch.dict(dispatch.HANDLERS,workspace=reader):
            result=dispatch.executar_resultado('workspace',{'operacao':'ler','caminho':'missing.txt'})
            self.assertFalse(result['mutates'])
            self.assertTrue(autonomy.recoverable_result(result))
            self.assertEqual(autonomy.authorize_exploration_tool('calcular',{}),'')
        from core.capabilities import operation_mutates
        self.assertTrue(operation_mutates('workspace',{'operacao':'salvar'}))
        self.assertTrue(operation_mutates('workspace',{}))
        self.assertFalse(operation_mutates('minha_atividade',{'operacao':'ler_resultado'}))

    def test_blank_final_after_action_uses_one_text_only_slot_without_replaying_effect(self):
        app=self.app();reader=Mock(return_value='Uma observação real da fixture.')
        app.chamar_modelo=AsyncMock(side_effect=[call('ler_da_oficina',caminho='fixture.txt'),
            {'role':'assistant','content':'','thinking':'PRIVATE_SENTINEL'},
            {'role':'assistant','content':'Li o arquivo e deixei o resultado registrado.'}])
        with patch.dict(dispatch.HANDLERS,ler_da_oficina=reader):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        reader.assert_called_once();self.assertIsNone(app.chamar_modelo.await_args_list[-1].args[1])
        self.assertTrue(app.chamar_modelo.await_args.kwargs['forcar_sem_pensar'])
        self.assertNotIn('PRIVATE_SENTINEL',initiative.context())

    def test_repeated_working_point_queries_keep_tool_replies_not_only_assistant_calls(self):
        app=self.app()
        app.chamar_modelo=AsyncMock(side_effect=[call('minha_atividade',operacao='consultar'),
            call('minha_atividade',operacao='consultar'),
            {'role':'assistant','content':'Consultei meu ponto de retomada; não havia objetivo ativo.'}])
        asyncio.run(app.explorar({'tipo':'explorar'}))
        original=app.chamar_modelo.await_args_list[-1].args[0]
        self.assertTrue(all(m.get('_receipt_id') for m in original if m['role']=='tool'))
        wire=app._normalizar_mensagens_ollama(original)
        roles=[m['role'] for m in wire]
        self.assertEqual(roles,['system','user','assistant','tool','assistant','tool'])
        replies=[m for m in wire if m['role']=='tool']
        self.assertEqual(len(replies),2)
        self.assertTrue(all('_receipt_id' not in m for m in replies))
        self.assertNotIn('iniciativa_bloqueada',state_file.read(config.ESTADO_MENTE))

    def test_pending_command_is_observed_without_model_call_or_duplicate_start(self):
        initiative.record_observation('execute_command','receipt-job',{'command':'fixture'},
            {'status':'success','output':'accepted','mutates':True,'background_job':'job-deadbeef'})
        app=self.app();app.chamar_modelo=AsyncMock()
        handler=Mock(return_value='Job job-deadbeef [rodando]\nRESULTADO_JOB=pending\nCODIGO_SAIDA=None\n')
        with patch.dict(dispatch.HANDLERS,ver_comando=handler):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        handler.assert_called_once();self.assertEqual(handler.call_args.args[0]['job_id'],'job-deadbeef')
        app.chamar_modelo.assert_not_called()
        self.assertNotIn('iniciativa_bloqueada',state_file.read(config.ESTADO_MENTE))
        self.assertIn('pending_command',initiative.activity())

    def test_failed_observation_storage_preserves_effect_and_stops_before_next_model(self):
        app=self.app();handler=Mock(return_value='read fixture')
        app.chamar_modelo=AsyncMock(side_effect=[call('ler_da_oficina',caminho='fixture.txt')])
        with patch.dict(dispatch.HANDLERS,ler_da_oficina=handler),\
             patch.object(initiative,'record_observation',side_effect=sqlite3.OperationalError('fixture full')):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        handler.assert_called_once();self.assertEqual(app.chamar_modelo.await_count,1)
        self.assertIn('iniciativa_bloqueada',state_file.read(config.ESTADO_MENTE))


if __name__=='__main__':unittest.main()
