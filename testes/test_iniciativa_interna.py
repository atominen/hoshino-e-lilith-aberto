"""Iniciativa pós-reset: escolha real, limites e recibos; nenhum modelo/hardware."""
import asyncio
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from contextlib import closing

import config
from core import autonomy, kernel, dispatch, action_commentary, job_bus
from memory.sqlite import init_db
from memory import audience
from mind import drives
from tools import agenda


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root/'mind.db'
        for obj, key, value in (
            (config, 'DB_PATH', str(self.db)), (init_db, 'DB_PATH', str(self.db)),
            (config, 'ESTADO_MENTE', str(self.root/'state.json')),
            (config, 'RUNTIME_DIR', str(self.root)), (config, 'ENTIDADE_ID', 'hoshino'),
            (job_bus, 'DB_PATH', self.root/'jobs.db'),
            (agenda, 'DB_PATH', str(self.db)),
        ):
            p = patch.object(obj, key, value); p.start(); self.addCleanup(p.stop)
        init_db.init_database(verbose=False)
        self.now = datetime(2026,10,23,9)
        self.situation = dict(agora=self.now, eventos=[], usuario_presente=None,
                              segundos_sem_interacao_observados=600, segundos_ociosos=0)
        self.pressures = {'ocio':dict(pressao=.25)}
        p = patch.object(dispatch.ui_policy, 'allowed', return_value=True)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(dispatch.ui_policy, 'filter_schemas', side_effect=lambda root,e,s:s)
        p.start(); self.addCleanup(p.stop)

    def rows(self,sql):
        with closing(sqlite3.connect(self.db)) as c:return c.execute(sql).fetchall()


class InitiativeTests(Fixture):
    def test_empty_memory_and_unknown_presence_allow_choice_not_forced_action_or_speech(self):
        d = kernel.deliberar(self.situation, self.pressures)
        self.assertEqual(d['tipo'], 'explorar')
        self.assertNotIn(d['tipo'], kernel.FALANTES)
        self.assertEqual(self.rows('select count(*) from curiosities')[0][0], 0)
        self.assertEqual(self.rows('select count(*) from goals')[0][0], 0)

    def test_quiet_boot_recent_interaction_and_missing_clock_do_not_poll_model(self):
        for idle in (0, 30, config.INICIATIVA_INATIVIDADE_SEGUNDOS-1, None):
            s = dict(self.situation, segundos_sem_interacao_observados=idle)
            self.assertEqual(kernel.deliberar(s, self.pressures)['tipo'], 'nada')

    def test_existing_safety_and_activity_gates_are_not_bypassed(self):
        for state in ({'ocupada':True}, {'partida_em_andamento':True},
                      {'acoes_na_hora':config.ACOES_INTERNAS_POR_HORA},
                      {'ultima_acao_interna':self.now}):
            self.assertEqual(kernel.deliberar(self.situation, self.pressures, state)['tipo'], 'nada')
        loaded = dict(self.situation, carga={'memoria_usada_pct':99})
        self.assertEqual(kernel.deliberar(loaded,self.pressures)['tipo'],'nada')
        with patch.object(config,'ENTIDADE_ID','alistair'):
            self.assertEqual(kernel.deliberar(self.situation,self.pressures)['tipo'],'nada')
            self.assertEqual(kernel.deliberar(self.situation,{'ocio':{'pressao':.95}})['tipo'],'nada')

    def test_cooldown_survives_restart_and_uncertain_or_future_state_blocks(self):
        self.assertTrue(drives.satisfazer('deliberacao_interna',self.now))
        self.assertFalse(drives.pode_deliberar(self.now+timedelta(seconds=config.INICIATIVA_INTERVALO_SEGUNDOS-1)))
        self.assertTrue(drives.pode_deliberar(self.now+timedelta(seconds=config.INICIATIVA_INTERVALO_SEGUNDOS)))
        self.assertFalse(drives.pode_deliberar(self.now-timedelta(days=1)))
        with patch.object(drives,'_estado',return_value={'iniciativa_bloqueada':{'outcome':'uncertain'}}):
            self.assertFalse(drives.pode_deliberar(self.now))

    def test_internal_choice_does_not_relax_social_anchor_or_force_chess(self):
        high = {'conexao':{'pressao':.95}}
        d = kernel.deliberar(dict(self.situation, usuario_presente=True), high)
        self.assertEqual(d['tipo'],'explorar')
        self.assertNotIn(d['tipo'],kernel.FALANTES)
        d = kernel.deliberar(self.situation, {'ocio':{'pressao':.95}})
        self.assertEqual(d['tipo'],'explorar')

    def test_schemas_exclude_system_actions_and_diary_share_without_mutating_other_modes(self):
        with patch.object(dispatch.rede,'ativa',return_value=False):
            schemas=dispatch.esquemas(modo_operacao='autonomo_exploracao')
        names={s['function']['name'] for s in schemas}
        self.assertIn('diario', names)
        self.assertIn('jogar_xadrez',names)
        for name in ('execute_command','desligar_internet','gerar_imagem','web_search',
                     'baixar_arquivo','entidades_enviar_mensagem','registrar_gosto'):
            self.assertNotIn(name,names)
        diary=next(s for s in schemas if s['function']['name']=='diario')
        self.assertEqual(diary['function']['parameters']['properties']['operacao']['enum'],['ler','escrever'])
        original=next(s for s in dispatch.ESQUEMAS if s['function']['name']=='diario')
        self.assertIn('compartilhar',original['function']['parameters']['properties']['operacao']['enum'])

    def test_hallucinated_tool_is_blocked_at_executor_including_worker_thread(self):
        handler=Mock(return_value='não deve executar')
        with patch.dict(dispatch.HANDLERS, desligar_internet=handler), \
             autonomy.exploration_scope({'calcular'},4):
            result=asyncio.run(asyncio.to_thread(dispatch._executar_bruto,'desligar_internet',{}))
        self.assertTrue(result.startswith('ACESSO_BLOQUEADO:'))
        handler.assert_not_called()

    def test_private_diary_cannot_be_shared_from_exploration(self):
        with autonomy.exploration_scope({'diario'},4):
            result=dispatch._executar_bruto('diario',dict(operacao='compartilhar',
                id='not-read',destinatario='lilith',texto='private'))
        self.assertTrue(result.startswith('ACESSO_BLOQUEADO:'))

    def test_call_budget_and_first_failure_stop_further_effects(self):
        with autonomy.exploration_scope({'calcular'},2):
            self.assertEqual(autonomy.authorize_exploration_tool('calcular',{}),'')
            self.assertEqual(autonomy.authorize_exploration_tool('calcular',{}),'')
            self.assertTrue(autonomy.authorize_exploration_tool('calcular',{}))
        with autonomy.exploration_scope({'calcular','diario'},4) as s:
            autonomy.exploration_receipt('calcular','real-id',{'status':'error'})
            self.assertTrue(autonomy.authorize_exploration_tool('diario',{'operacao':'escrever'}))
        self.assertEqual(s['receipts'][0]['receipt_id'],'real-id')

    def test_comment_is_private_entity_authored_not_a_human_message_or_quality_approval(self):
        for _ in range(2):
            self.assertTrue(action_commentary.record_deliberation('same-id',
                'Prefiro descansar agora.', [], 'no_action'))
        rows=self.rows('select * from episodes')
        self.assertEqual(len(rows),1)
        with closing(sqlite3.connect(self.db)) as db:
            db.row_factory=sqlite3.Row
            r=db.execute('select * from episodes').fetchone()
            self.assertFalse(audience.visible(db,'episodes',r,public_only=True))
        ctx=json.loads(r['context'])
        self.assertFalse(ctx['human_conversation']);self.assertFalse(ctx['quality_approved'])
        self.assertIsNone(r['is_success'])
        self.assertEqual(ctx['authored_by'],'hoshino')

class RuntimeTests(Fixture):
    def app(self):
        import main
        self.main=main
        with patch.object(main,'semear_origem'):
            app=main.InterfaceHoshino()
        app.sys_log=Mock();app.chat_log=Mock()
        app.situacao=dict(self.situation)
        return app

    def test_model_may_choose_silence_without_a_forced_retry_or_publication(self):
        app=self.app()
        app.chamar_modelo=AsyncMock(return_value={'role':'assistant','content':'SILENCIO'})
        asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(app.chamar_modelo.await_count,1)
        row=self.rows("select result,is_success from episodes where source='autonomous_deliberation'")[0]
        self.assertEqual(row,('no_action',None))
        self.assertFalse(drives.pode_deliberar())
        self.assertNotIn('iniciativa_bloqueada',json.loads(Path(config.ESTADO_MENTE).read_text()))

    def test_actual_notebook_write_has_receipt_and_natural_comment_without_invented_human_input(self):
        app=self.app()
        app.chamar_modelo=AsyncMock(side_effect=[
            {'role':'assistant','content':'','tool_calls':[{'function':{'name':'diario',
                'arguments':{'operacao':'escrever','titulo':'Experimento próprio','texto':'Uma anotação de teste.'}}}]},
            {'role':'assistant','content':'Escrevi uma anotação no meu caderno.'}])
        asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(len(self.rows("select id from reflections where tipo='diario'")),1)
        row=self.rows("select context,result from episodes where source='autonomous_deliberation'")[0]
        ctx=json.loads(row[0])
        self.assertEqual(row[1],'action')
        self.assertEqual(ctx['receipts'][0]['tool'],'diario')
        self.assertTrue(ctx['receipts'][0]['verified'])
        self.assertFalse(ctx['human_conversation'])
        self.assertEqual(len(self.rows('select id from curiosities')),0)

    def test_model_failure_is_not_replayed_and_blocks_new_starts(self):
        app=self.app();app.chamar_modelo=AsyncMock(side_effect=RuntimeError('fixture timeout'))
        asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(app.chamar_modelo.await_count,1)
        self.assertFalse(drives.pode_deliberar(datetime.now()+timedelta(days=1)))
        asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(app.chamar_modelo.await_count,1)

    def test_last_model_slot_is_for_comment_not_another_action(self):
        app=self.app()
        call={'role':'assistant','tool_calls':[{'function':{'name':'diario','arguments':{'operacao':'ler'}}}]}
        app.chamar_modelo=AsyncMock(side_effect=[call,call,call,
            {'role':'assistant','content':'Consultei meu caderno; não havia entrada para continuar.'}])
        with patch.object(config,'INICIATIVA_MAX_PASSOS',4):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(app.chamar_modelo.await_count,4)
        self.assertIsNone(app.chamar_modelo.await_args_list[-1].args[1])
        r=self.rows("select context from episodes where source='autonomous_deliberation'")[0]
        self.assertEqual(len(json.loads(r[0])['receipts']),3)

    def test_unavailable_comment_storage_blocks_new_autonomous_attempt(self):
        app=self.app();app.chamar_modelo=AsyncMock(return_value={'role':'assistant','content':'SILENCIO'})
        with patch.object(action_commentary,'record_deliberation',return_value=False):
            asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertTrue(app._iniciativa_bloqueada)
        self.assertFalse(drives.pode_deliberar(datetime.now()+timedelta(days=1)))

    def test_old_investigation_retains_restricted_mode_through_execution(self):
        app=self.app();app.contexto_do_turno=Mock(return_value='contexto da fixture')
        app.ciclo_de_ferramentas=AsyncMock(return_value=('',[]))
        with patch.object(self.main.affect,'apreciar'):
            asyncio.run(app.investigar({'tipo':'investigar','alvo':{'texto':'Pergunta da fixture'}}))
        self.assertEqual(app.ciclo_de_ferramentas.await_args.kwargs['modo_operacao'],'autonomo_interno')

    def test_new_human_worker_takes_priority_before_another_effect(self):
        app=self.app()
        async def human_arrived(*args, **kwargs):
            worker=Mock();worker.done.return_value=False
            app._workers_por_chave={'human':worker}
            return {'role':'assistant','tool_calls':[{'function':{'name':'diario',
                'arguments':{'operacao':'escrever','titulo':'Não deve salvar','texto':'Efeito bloqueado'}}}]}
        app.chamar_modelo=AsyncMock(side_effect=human_arrived)
        asyncio.run(app.explorar({'tipo':'explorar'}))
        self.assertEqual(self.rows("select count(*) from reflections where tipo='diario'")[0][0],0)
        self.assertEqual(self.rows("select result from episodes where source='autonomous_deliberation'")[0][0],'interrupted')
        app._active_ticks=2
        self.assertTrue(app._estado_autonomia(datetime.now(),100.)['ocupada'])


if __name__=='__main__':unittest.main()
