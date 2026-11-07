"""Regressões nos workers/dispatcher reais; bancos e transportes isolados."""
import asyncio
import json
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import config
import main
from core import cognition, dispatch, interentity as bus, task_state
from core.conversation import parece_correcao
from social import channels
from tools import minecraft
from integracoes.discord_bot import entregar_mensagem


def app_fixture():
    app = object.__new__(main.InterfaceHoshino)
    app.sys_log = app.chat_log = SimpleNamespace(write=lambda *a: None)
    app.messages = []
    app.saidas_recentes = deque(maxlen=8)
    app._fila_conversa = deque()
    app._fila_chaves = {}
    app._workers_por_chave = {}
    app._travas_conversa = {}
    app._historicos_por_chave = {}
    app._revisoes_conversa = {}
    app._saidas_por_conversa = {}
    app._versao_fila_conversa = 0
    app._interentity_inflight = set()
    app._interentity_enabled = True
    app.ultima_entrada = ''
    app.canal_atual = 'tui'
    app.pessoa = app.pessoa_local = {'id':'usuario', 'nome':'usuario'}
    app.prompt_sistema = 'Identidade externa preservada.'
    app.situacao = {'nome':'conversando'}
    app.confirmacao_pendente = None
    app._memory_generation = 0
    app.contexto_do_turno = Mock(return_value='Contexto do turno')
    app.compactar_se_precisar = AsyncMock()
    app.conferir_agenda = AsyncMock(side_effect=lambda text, _:text)
    return app


class MessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_synthetic_harness_keeps_human_presence_and_never_uses_voice(self):
        await self.install_model();human=self.app.pessoa_local
        self.app.ultima_interacao_monotonic=123
        sent=channels.publicar_entrada('local','Mensagem sintética de ensaio.','Codex','codex_teste','codex')
        message=next(m for m in channels.receber(20,False) if m['id']==sent)
        message['metadata']={'synthetic_test':True,'test_actor':'Codex'}
        self.app._channels_inflight={sent}
        with patch.object(config,'VOZ_ATIVA',True),patch.object(config,'FALAR_VOZ_TEXTO',True),patch.object(main,'speak',new=AsyncMock()) as speak:
            self.app.receber_de_pessoa(message['texto'],canal='local',pessoa={'id':'codex','nome':'Codex'},responder_para='codex',mensagem_canal=message)
            await self.finish()
        self.assertIs(self.app.pessoa_local,human)
        self.assertEqual(self.app.ultima_interacao_monotonic,123)
        speak.assert_not_awaited()
    def deliver_at(self,at):
        rows=bus.inbox(config.ENTIDADE_ID,settle_text_seconds=2,now=at,limit=20,
                       exclude_ids=self.app._interentity_inflight)
        for msg in rows:
            self.app._interentity_inflight.add(msg['id'])
            self.app.receber_de_pessoa(msg['text'],canal='localhub',pessoa=self.app.pessoa,
                                      responder_para='usuario',mensagem_local=msg)

    async def test_real_inbox_stop_cannot_resurrect_a_held_request(self):
        from datetime import datetime
        base=datetime.fromisoformat('2026-10-26T12:00:00+00:00').timestamp()
        await self.install_model()
        with patch.object(bus,'_agora',return_value='2026-10-26T12:00:00+00:00'):
            old=bus.send('usuario',config.ENTIDADE_ID,'Execute o pedido anterior')
        with patch.object(bus,'_agora',return_value='2026-10-26T12:00:00.200000+00:00'):
            stop=bus.send('usuario',config.ENTIDADE_ID,'Pare')
        self.deliver_at(base+.3);await self.finish()
        self.deliver_at(base+3);await self.finish()
        self.assertEqual(self.calls,[['Pare']])
        rows=bus.inbox(config.ENTIDADE_ID,unread_only=False)
        old_row=next(r for r in rows if r['id']==old['id'])
        self.assertEqual(old_row['metadata']['processing']['status'],'superseded')
        self.assertEqual(old_row['metadata']['processing']['superseded_by'],stop['id'])
        self.assertTrue(old_row['read_at'])

    async def test_real_inbox_correction_beyond_page_cancels_older_pending_inputs(self):
        from datetime import datetime
        base=datetime.fromisoformat('2026-10-26T12:00:00+00:00').timestamp()
        await self.install_model()
        with patch.object(bus,'_agora',return_value='2026-10-26T12:00:00+00:00'):
            old=[bus.send('usuario',config.ENTIDADE_ID,f'Pedido antigo {i}') for i in range(25)]
            correction=bus.send('usuario',config.ENTIDADE_ID,'Na verdade faça somente o pedido novo')
        self.deliver_at(base+3);await self.finish()
        self.assertEqual(self.calls,[['Na verdade faça somente o pedido novo']])
        rows=bus.inbox(config.ENTIDADE_ID,unread_only=False)
        cancelled=[r for r in rows if r['id'] in {m['id'] for m in old}]
        self.assertEqual(len(cancelled),25)
        self.assertTrue(all(r['metadata']['processing']['status']=='superseded' for r in cancelled))

    def receive_ready(self,text,scope='direct'):
        sent=bus.send('usuario',config.ENTIDADE_ID,text,chat_scope=scope)
        msg=next(m for m in bus.peek(config.ENTIDADE_ID,200) if m['id']==sent['id']);msg['_text_burst_ready']=True
        self.app._interentity_inflight.add(msg['id'])
        self.app.receber_de_pessoa(text,canal='localhub',pessoa=self.app.pessoa,responder_para='usuario',mensagem_local=msg)
        return sent['id']

    async def test_ready_typed_fragments_form_one_model_turn_and_keep_all_receipts(self):
        await self.install_model();first=self.receive_ready('Primeira parte');second=self.receive_ready('Segunda parte')
        await self.finish()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0],['Primeira parte','Segunda parte'])
        replies=bus.peek('usuario');self.assertEqual(len(replies),1)
        self.assertEqual(replies[0]['metadata']['input_ids'],[first,second])
        self.assertTrue(all(m['read_at'] for m in bus.inbox(config.ENTIDADE_ID,unread_only=False)))

    async def test_ready_fragments_during_inference_keep_first_turn_then_one_next_batch(self):
        first=asyncio.Event();release=asyncio.Event();await self.install_model(first,release)
        a=self.receive_ready('Objetivo original')
        await asyncio.wait_for(first.wait(),1)
        b=self.receive_ready('Um detalhe');c=self.receive_ready('Outro detalhe');release.set();await self.finish()
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[0],['Objetivo original'])
        replies=bus.peek('usuario');self.assertEqual(len(replies),2)
        self.assertEqual([r['metadata']['input_ids'] for r in replies],[[a],[b,c]])

    async def test_ready_fragments_from_direct_and_global_do_not_mix(self):
        await self.install_model();self.receive_ready('Mensagem direta');self.receive_ready('Mensagem global','global')
        await self.finish();self.assertEqual(len(self.calls),2)

    async def test_ready_fragments_from_different_days_do_not_mix(self):
        await self.install_model()
        with patch.object(bus,'_agora',return_value='2026-10-24T12:00:00+00:00'):self.receive_ready('Dia antigo')
        self.receive_ready('Dia atual');await self.finish();self.assertEqual(len(self.calls),2)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='causalidade-')
        self.addCleanup(self.tmp.cleanup)
        self.app = app_fixture()
        for context in (patch.object(bus,'DB_PATH',Path(self.tmp.name)/'messages.db'),
                        patch.object(config,'BUS_DIR',self.tmp.name+'/channels'),
                        patch.object(config,'DEBOUNCE_CONVERSA_MS',0),
                        patch.object(main.scribe,'pos_turno',return_value={'fatos':[]}),
                        patch.object(main,'salvar_episodio'),
                        patch.object(self.app,'atualizar_pessoa'),
                        patch.object(self.app,'extrair_memoria',new=AsyncMock()),
                        patch.object(task_state,'iniciar_ou_continuar',return_value=None),
                        patch.object(main.situation,'descrever',return_value='conversa')):
            context.start(); self.addCleanup(context.stop)

    def receive(self, text):
        sent = bus.send('usuario',config.ENTIDADE_ID,text)
        message = next(m for m in bus.peek(config.ENTIDADE_ID,200) if m['id']==sent['id'])
        self.app._interentity_inflight.add(message['id'])
        self.app.receber_de_pessoa(text,canal='localhub',pessoa=self.app.pessoa,
                                  responder_para='usuario',mensagem_local=message)
        return sent['id']

    async def finish(self):
        await asyncio.wait_for(asyncio.gather(*list(self.app._workers_por_chave.values())),2)
        if getattr(self.app,'_background_tasks',None):
            await asyncio.gather(*self.app._background_tasks)

    async def install_model(self, first=None, release=None):
        self.calls = []
        async def model(messages, *args, **kwargs):
            goal = [m['content'] for m in messages if m['role']=='user'][-1]
            self.calls.append([m['content'] for m in messages if m['role']=='user'])
            if len(self.calls)==1 and first:
                first.set(); await release.wait()
            return {'role':'assistant','content':'Resposta '+goal+'.'}
        self.app.chamar_modelo = model

    async def test_deleted_test_content_is_not_context_or_backlog_and_retains_dedup(self):
        with self.assertRaises(ValueError):
            bus.send('usuario', 'hoshino', 'Não esconder uma mensagem nova', kind='deleted')
        incoming = bus.send('usuario', 'hoshino', 'Pedido antigo de teste', dedupe_key='discard-test-input')
        parent = next(m for m in bus.peek('hoshino') if m['id'] == incoming['id'])
        scope = bus.processing_message.set(parent)
        try:
            reply = bus.send('hoshino', 'usuario', 'Resposta antiga de teste')
        finally:
            bus.processing_message.reset(scope)
        peer = bus.send('alistair', 'hoshino', 'Apresentação antiga de teste')
        self.assertTrue(bus.processing_outcome(peer['id'], 'hoshino', 'uncertain', reason='efeito não confirmado'))
        with bus._transaction() as db:
            db.execute("UPDATE entity_messages SET text='',kind='deleted'")
        self.assertEqual(bus.inbox('hoshino', unread_only=False, include_held=True), [])
        self.assertEqual(bus.peek('hoshino'), [])
        self.assertEqual(bus.conversation('usuario', 'hoshino'), [])
        self.assertEqual(bus.conversation('alistair', 'hoshino'), [])
        self.assertEqual(bus.private_history(), [])
        self.assertEqual(bus.user_conversation('hoshino'), [])
        daily = bus.daily_conversation('hoshino')
        self.assertEqual(daily['conversation'], [])
        self.assertEqual(daily['day_summary']['message_count'], 0)
        repeated = bus.send('usuario', 'hoshino', 'Pedido antigo de teste', dedupe_key='discard-test-input')
        scope = bus.processing_message.set(parent)
        try:
            repeated_reply = bus.send('hoshino', 'usuario', 'Não emitir novamente')
        finally:
            bus.processing_message.reset(scope)
        self.assertEqual(repeated['id'], incoming['id'])
        self.assertEqual(repeated_reply['id'], reply['id'])
        with bus._transaction() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM entity_messages').fetchone()[0], 3)
            raw = db.execute('SELECT metadata FROM entity_messages WHERE id=?', (peer['id'],)).fetchone()[0]
        self.assertEqual(json.loads(raw)['processing']['status'], 'uncertain')
        self.assertEqual(bus.peek('hoshino'), [])

    async def test_abc_backlog_gets_three_real_turns_without_future_context(self):
        await self.install_model()
        ids = [self.receive(text) for text in ('A','B','C')]
        await self.finish()
        self.assertEqual(self.calls,[['A'],['A','B'],['A','B','C']])
        answers = [m for m in bus.user_conversation(config.ENTIDADE_ID) if m['sender']!= 'usuario']
        self.assertEqual([json.loads(m['metadata'])['reply_to'] for m in answers],ids)
        self.assertEqual(bus.peek(config.ENTIDADE_ID),[])
        self.assertFalse(self.app._interentity_inflight)
        self.assertEqual([m['role'] for m in self.app._historico_da_conversa(('localhub','usuario','usuario'))],
                         ['user','assistant','user','assistant','user','assistant'])

    async def test_messages_during_generation_do_not_cancel_ordinary_turn(self):
        first, release = asyncio.Event(), asyncio.Event()
        await self.install_model(first,release)
        self.receive('A')
        await asyncio.wait_for(first.wait(),1)
        self.receive('B'); self.receive('C'); release.set()
        await self.finish()
        self.assertEqual(self.calls,[['A'],['A','B'],['A','B','C']])
        self.assertFalse(self.app._interentity_inflight)

    async def test_stop_with_explanation_supersedes_active_response(self):
        first, release = asyncio.Event(), asyncio.Event()
        await self.install_model(first, release)
        original = self.receive('Abra uma página de teste')
        await asyncio.wait_for(first.wait(), 1)
        stop = self.receive('PARA. Cancele a tentativa atual; não execute novas ações.')
        release.set()
        await self.finish()
        answers = [m for m in bus.user_conversation(config.ENTIDADE_ID) if m['sender'] != 'usuario']
        self.assertEqual([json.loads(m['metadata'])['reply_to'] for m in answers], [stop])
        previous = next(m for m in bus.user_conversation(config.ENTIDADE_ID) if m['id'] == original)
        self.assertEqual(json.loads(previous['metadata'])['processing']['status'], 'superseded')

    async def test_sleep_during_inference_drains_without_publishing_stale_reply(self):
        first, release = asyncio.Event(), asyncio.Event()
        await self.install_model(first, release)
        self.receive('Abra uma página de teste')
        await asyncio.wait_for(first.wait(), 1)
        self.app._draining = True
        release.set()
        await self.finish()
        self.assertFalse([m for m in bus.user_conversation(config.ENTIDADE_ID) if m['sender'] != 'usuario'])
        self.assertFalse(self.app._interentity_inflight)
        main.salvar_episodio.assert_not_called()

    async def test_sleep_before_turn_never_starts_inference(self):
        await self.install_model()
        self.app._draining = True
        self.receive('Mensagem recebida antes do sono')
        await self.finish()
        self.assertEqual(self.calls, [])

    async def simultaneous(self, listener, sender):
        first,release=asyncio.Event(),asyncio.Event()
        with patch.object(config,'ENTIDADE_ID',listener),patch.object(config,'ENTIDADE_NOME',listener.capitalize()):
            await self.install_model(first,release)
            human=self.receive('Apresentação humana')
            await asyncio.wait_for(first.wait(),1)
            sent=bus.send(sender,listener,f'Eu sou {sender.capitalize()}.')
            message=next(m for m in bus.inbox(listener,200) if m['id']==sent['id'])
            self.app._interentity_inflight.add(message['id'])
            self.app.receber_de_pessoa(message['text'],canal='interentidades',
                pessoa={'id':sender,'nome':sender.capitalize()},responder_para=sender,mensagem_local=message)
            # Fios diferentes têm proprietários próprios, sem ordem causal global inventada.
            await asyncio.sleep(.01)
            release.set();await self.finish()
            human_reply=[m for m in bus.user_conversation(listener) if m['sender']==listener]
            peer_reply=[m for m in bus.conversation(sender,listener) if m['sender']==listener]
            self.assertEqual(len(human_reply),1);self.assertEqual(len(peer_reply),1)
            self.assertEqual(json.loads(human_reply[0]['metadata'])['reply_to'],human)
            daily = bus.daily_conversation(listener)
            self.assertEqual({m['id'] for m in daily['conversation']}, {human,human_reply[0]['id']})
            self.assertEqual(json.loads(human_reply[0]['metadata'])['conversation_session']['entity'],listener)
            self.assertEqual(json.loads(peer_reply[0]['metadata'])['reply_to'],sent['id'])
            self.assertEqual(peer_reply[0]['recipient'],sender)
            self.assertNotIn('conversation_session',json.loads(peer_reply[0]['metadata']))
            self.assertEqual(bus.peek(listener),[])
            self.assertFalse(self.app._interentity_inflight)

    async def test_human_hoshino_and_alistair_hoshino_simultaneously(self):
        await self.simultaneous('hoshino','alistair')

    async def test_hoshino_lilith_while_lilith_handles_human(self):
        await self.simultaneous('lilith','hoshino')

    async def test_daily_midnight_does_not_interrupt_ongoing_turn_or_move_reply(self):
        first,release=asyncio.Event(),asyncio.Event()
        await self.install_model(first,release)
        with patch.object(bus,'_agora',return_value='2026-10-10T02:59:59Z'):
            human=self.receive('continue a conversa')
            old=bus.daily_session(config.ENTIDADE_ID)['id']
            await asyncio.wait_for(first.wait(),1)
        with patch.object(bus,'_agora',return_value='2026-10-10T03:00:01Z'):
            self.assertEqual(bus.daily_conversation(config.ENTIDADE_ID)['conversation'],[])
            release.set();await self.finish()
            archive=bus.daily_conversation(config.ENTIDADE_ID,session_id=old)
            self.assertTrue(archive['chat_read_only'])
            self.assertEqual(len(archive['conversation']),2)
            self.assertEqual(archive['conversation'][1]['metadata']['reply_to'],human)
            self.assertEqual(bus.peek(config.ENTIDADE_ID),[])
            self.assertFalse(self.app._interentity_inflight)

    async def test_semantic_correction_suppresses_old_answer_and_releases_inflight(self):
        first, release = asyncio.Event(), asyncio.Event()
        await self.install_model(first,release)
        original = self.receive('vai para esquerda')
        await asyncio.wait_for(first.wait(),1)
        corrected = self.receive('não, direita'); release.set()
        await self.finish()
        messages = bus.user_conversation(config.ENTIDADE_ID)
        answers = [m for m in messages if m['sender']!= 'usuario']
        self.assertEqual(len(answers),1)
        self.assertEqual(json.loads(answers[0]['metadata'])['reply_to'], corrected)
        old = next(m for m in messages if m['id']==original)
        self.assertEqual(json.loads(old['metadata'])['processing']['status'],'superseded')
        self.assertFalse(self.app._interentity_inflight)

    async def test_correction_before_worker_does_not_execute_old_intention(self):
        await self.install_model()
        self.receive('vai para esquerda'); self.receive('não, direita')
        await self.finish()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][-1],'não, direita')

    async def test_generation_failure_is_held_not_read_or_retried(self):
        self.app.ciclo_de_ferramentas = AsyncMock(side_effect=TimeoutError('mock'))
        identifier = self.receive('teste')
        await self.finish()
        pending = bus.peek(config.ENTIDADE_ID)
        self.assertEqual(pending[0]['id'],identifier)
        self.assertIsNone(pending[0]['read_at'])
        self.assertEqual(pending[0]['metadata']['processing']['status'],'uncertain')
        self.assertEqual(bus.inbox(config.ENTIDADE_ID),[])
        self.assertFalse(self.app._interentity_inflight)

    async def test_empty_reply_is_not_success(self):
        self.app.ciclo_de_ferramentas = AsyncMock(return_value=('',[]))
        self.receive('teste')
        await self.finish()
        pending=bus.peek(config.ENTIDADE_ID)
        self.assertEqual(pending[0]['metadata']['processing']['status'],'failed')
        self.assertIsNone(pending[0]['read_at'])

    async def test_compaction_keeps_answer_anchor_before_future_messages(self):
        first, release = asyncio.Event(), asyncio.Event()
        await self.install_model(first,release)
        async def compact(messages, _person, **kwargs):
            messages.insert(0, {'role':'system','content':'Resumo compacto.'})
        self.app.compactar_se_precisar = compact
        self.receive('A'); await asyncio.wait_for(first.wait(),1)
        self.receive('B'); release.set(); await self.finish()
        history=self.app._historico_da_conversa(('localhub','usuario','usuario'))
        self.assertLess(next(i for i,m in enumerate(history) if m['content']=='Resposta A.'),
                        next(i for i,m in enumerate(history) if m['content']=='B'))

    async def test_transcription_metadata_reaches_worker(self):
        bus.send('usuario',config.ENTIDADE_ID,'fala revisada',metadata={'audio_job_id':'audio-mock','speaker':'usuario'})
        with patch.object(main.people,'identificar',return_value=self.app.pessoa):
            self.app.responder=AsyncMock(return_value={'status':'failed'})
            await self.app.ler_interentidades(); await self.finish()
        self.assertEqual(self.app.responder.call_args.kwargs['modalidade_entrada'],'fala')
        self.assertEqual(self.app.contexto_do_turno.call_args.kwargs['speakers'],['usuario'])

    async def test_owned_stop_can_interrupt_navigation_without_waiting_action_lock(self):
        owner=('localhub','usuario','usuario')
        self.app._minecraft_navigation_owner=owner
        self.app._minecraft_active_action='minecraft_ir_para'
        self.app.trava_acao=asyncio.Lock()
        await self.app.trava_acao.acquire()
        self.app.responder=AsyncMock(return_value={'status':'answered'})
        result=dispatch._resultado_mecanico('minecraft_parar','Navegação parada.')
        with patch.object(dispatch,'executar_resultado',return_value=result) as execute,\
             patch.object(task_state,'registrar_ferramenta'):
            self.receive('PARA'); await self.finish()
        self.assertEqual(execute.call_args.args[0],'minecraft_parar')
        self.assertIsNone(self.app._minecraft_navigation_owner)
        self.assertTrue(self.app.trava_acao.locked())
        self.app.trava_acao.release()

    async def test_stop_does_not_interrupt_other_author(self):
        self.app._minecraft_navigation_owner=('discord','channel','other-user')
        self.app.responder=AsyncMock(return_value={'status':'answered'})
        with patch.object(dispatch,'executar_resultado') as execute:
            self.receive('PARA'); await self.finish()
        execute.assert_not_called()

    async def test_stop_does_not_interrupt_craft(self):
        self.app._minecraft_navigation_owner=('localhub','usuario','usuario')
        self.app._minecraft_active_action='minecraft_craft'
        self.app.responder=AsyncMock(return_value={'status':'answered'})
        with patch.object(dispatch,'executar_resultado') as execute:
            self.receive('PARA'); await self.finish()
        execute.assert_not_called()

    async def test_context_failure_releases_input_and_processes_later_message(self):
        await self.install_model()
        self.app.contexto_do_turno.side_effect=[RuntimeError('mock'), 'contexto válido']
        self.receive('A'); self.receive('B'); await self.finish()
        self.assertEqual(self.calls[-1][-1],'B')
        self.assertFalse(self.app._interentity_inflight)
        self.assertEqual(bus.peek(config.ENTIDADE_ID)[0]['metadata']['processing']['status'],'failed')

    async def test_microphone_correction_invalidates_text_for_same_local_participant(self):
        first, release=asyncio.Event(),asyncio.Event()
        await self.install_model(first,release)
        original=self.receive('vai para esquerda'); await asyncio.wait_for(first.wait(),1)
        self.app.receber_de_pessoa('não, direita',canal='voz',modalidade='fala')
        release.set(); await self.finish()
        old=next(m for m in bus.user_conversation(config.ENTIDADE_ID) if m['id']==original)
        self.assertEqual(json.loads(old['metadata'])['processing']['status'],'superseded')

    async def test_valid_correction_invalidates_active_audio_immediately(self):
        self.app.responder=AsyncMock(return_value={'status':'failed'})
        stream=Mock()
        self.app._speech_contexts_por_chave={('localhub','usuario','usuario'):{'streams':[stream]}}
        self.receive('PARA')
        stream.stop.assert_called_once_with('user_interruption')
        await self.finish()

    async def test_audio_correction_during_final_verification_is_not_delayed(self):
        first,release=asyncio.Event(),asyncio.Event(); stream=Mock()
        await self.install_model()
        async def verify(text,_):
            context=self.app._speech_contexts_por_chave[('localhub','usuario','usuario')]
            if not first.is_set():
                context['streams'].append(stream); first.set(); await release.wait()
            return text
        self.app.conferir_agenda=verify
        self.receive('A'); await asyncio.wait_for(first.wait(),1)
        self.receive('PARA')
        stream.stop.assert_called_with('user_interruption')
        release.set(); await self.finish()
        self.assertFalse(self.app._speech_contexts_por_chave)


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_budget_exhaustion_pauses_durable_pending_task(self):
        from memory.sqlite import init_db
        init_db.init_database(verbose=False)
        app=app_fixture();key=('test','bounded-pending-task','')
        task=task_state.iniciar_ou_continuar(key,'Leia a fonte-inexistente.txt.')
        task_state.definir_operacoes(key,[dict(id='read',ferramenta='workspace',operacao='ler',instrucao='Leia fonte-inexistente.txt.')])
        app._obter_args_de_tarefa=AsyncMock(return_value=({'operacao':'ler','caminho':'fonte-inexistente.txt'},''))
        app._executar_chamadas_da_etapa=AsyncMock(return_value=[('workspace',{},dict(ok=False,status='error',output='Erro: arquivo não existe.'))])
        with patch.object(config,'MAX_PASSOS_TAREFA_LONGA',1):
            answer,tools=await app.ciclo_de_ferramentas([dict(role='user',content=task.objetivo)],[],
                chave_conversa=key,canal='tui',tarefa_turno=task)
        self.assertEqual(task_state.status_id(task.id),'paused')
        self.assertTrue(any(e['status']=='pending' for e in task_state.carregar_por_id(task.id).etapas))
        self.assertNotIn('concluída',answer)

    async def test_discord_preserves_mentions_of_other_participants(self):
        from integracoes import discord_bot
        text='<@11> pergunte ao <@22> e à <@!33> sobre astronomia.'
        self.assertEqual(discord_bot.texto_sem_mencao_bot(text,'11'),
            'pergunte ao <@22> e à <@!33> sobre astronomia.')
        self.assertEqual(discord_bot.texto_sem_mencao_bot('Oi <@!11>','11'),'Oi')
        self.assertEqual(discord_bot.texto_sem_mencao_bot(text,''),text)

    def test_correction_markers_do_not_turn_dependencies_into_cancellations(self):
        for text in ('PARA','pare!','não, direita','espera, direita'):
            self.assertTrue(parece_correcao(text),text)
        for text in ('não sei','para conversar','depois faça uma bancada','leva comida também'):
            self.assertFalse(parece_correcao(text),text)

    async def test_cancel_after_waiting_lock_never_starts_mutation(self):
        app=app_fixture(); app.trava_acao=asyncio.Lock()
        await app.trava_acao.acquire()
        cancelled=False
        with patch.object(dispatch,'executar_resultado') as execute:
            task=asyncio.create_task(app._executar_chamadas_da_etapa(
                [{'function':{'name':'workspace','arguments':{'operacao':'pasta','caminho':'/tmp/mock'}}}],
                cognition.criar_frame('consultar estados',[]),1,set(),cancelar=lambda:cancelled))
            await asyncio.sleep(.01); cancelled=True; app.trava_acao.release()
            with self.assertRaises(main.TurnoCancelado): await task
        execute.assert_not_called()

    async def test_receipt_survives_mid_batch_correction(self):
        app=app_fixture(); cancelled=False
        def execute(*args):
            nonlocal cancelled
            cancelled=True
            return {'ok':True,'status':'success','output':'efeito confirmado','verified':True}
        with patch.object(dispatch,'executar_resultado',side_effect=execute) as executed:
            result=await app._executar_chamadas_da_etapa(
                [{'function':{'name':'workspace','arguments':{'operacao':'pasta','caminho':'/tmp/mock'}}}]*2,
                cognition.criar_frame('consultar estados',[]),1,set(),cancelar=lambda:cancelled)
        self.assertEqual(executed.call_count,1)
        self.assertEqual(result[0][2]['output'],'efeito confirmado')

    async def test_worker_cancellation_does_not_release_lock_while_mutation_thread_runs(self):
        app=app_fixture(); started,release=threading.Event(),threading.Event()
        def effect(*args):
            started.set(); release.wait(2)
            return {'status':'success','ok':True,'output':'efeito confirmado'}
        with patch.object(dispatch,'executar_resultado',side_effect=effect):
            task=asyncio.create_task(app._executar_chamadas_da_etapa(
                [{'function':{'name':'workspace','arguments':{'operacao':'pasta','caminho':'/tmp/mock'}}}],
                cognition.criar_frame('consultar estados',[]),1,set()))
            for _ in range(100):
                if started.is_set(): break
                await asyncio.sleep(.005)
            self.assertTrue(started.is_set()); task.cancel(); await asyncio.sleep(.01)
            self.assertTrue(app._obter_trava_acao().locked())
            self.assertFalse(task.done()); release.set()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertFalse(app._obter_trava_acao().locked())

    def test_mutable_timeout_blocks_repeat_through_existing_receipt(self):
        with patch.object(minecraft,'_ponte_compativel',return_value=({'protocol':3},'')),\
             patch.object(minecraft.requests,'post',side_effect=minecraft.requests.Timeout('mock')) as post:
            first=dispatch.executar_resultado('minecraft_chat',{'texto':'teste'},False,'tui',None)
            second=dispatch.executar_resultado('minecraft_chat',{'texto':'teste'},False,'tui',None)
        self.assertTrue(first['outcome_uncertain'])
        self.assertTrue(second['outcome_uncertain'])
        self.assertEqual(post.call_count,1)

    def test_read_timeout_is_safe_error_not_mutation(self):
        with patch.object(minecraft,'_ponte_compativel',return_value=({'protocol':3},'')),\
             patch.object(minecraft.requests,'post',side_effect=minecraft.requests.Timeout('mock')):
            result=dispatch.executar_resultado('minecraft_estado',{},False,'tui',None)
        self.assertEqual(result['status'],'error')
        self.assertFalse(result['outcome_uncertain'])

    def test_held_messages_do_not_hide_new_messages_and_old_metadata_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus,'DB_PATH',Path(tmp)/'bus.db'):
            for i in range(25):
                msg=bus.send('usuario',config.ENTIDADE_ID,str(i))
                bus.processing_outcome(msg['id'],config.ENTIDADE_ID,'failed',reason='mock')
            new=bus.send('usuario',config.ENTIDADE_ID,'nova')
            self.assertEqual([m['id'] for m in bus.inbox(config.ENTIDADE_ID)], [new['id']])
            self.assertEqual(len(bus.peek(config.ENTIDADE_ID,200)),26)

    def test_commit_order_matches_ui_even_when_timestamps_disagree(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus,'DB_PATH',Path(tmp)/'bus.db'):
            a=bus.send('usuario',config.ENTIDADE_ID,'A'); b=bus.send('usuario',config.ENTIDADE_ID,'B')
            with bus._transaction() as conn:
                conn.execute("UPDATE entity_messages SET created_at='1900' WHERE id=?",(b['id'],))
            self.assertEqual([m['id'] for m in bus.inbox(config.ENTIDADE_ID)],[a['id'],b['id']])

    def test_client_submission_dedup_does_not_dedup_intentional_identical_text(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus,'DB_PATH',Path(tmp)/'bus.db'):
            a=bus.send('usuario',config.ENTIDADE_ID,'oi',dedupe_key='central:submission-1')
            b=bus.send('usuario',config.ENTIDADE_ID,'oi',dedupe_key='central:submission-1')
            c=bus.send('usuario',config.ENTIDADE_ID,'oi',dedupe_key='central:submission-2')
            self.assertEqual(a['id'],b['id']); self.assertNotEqual(a['id'],c['id'])
            with self.assertRaises(ValueError):
                bus.send('usuario',config.ENTIDADE_ID,'diferente',dedupe_key='central:submission-1')

    def test_inflight_entries_do_not_occupy_inbox_page(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bus,'DB_PATH',Path(tmp)/'bus.db'):
            old=[bus.send('usuario',config.ENTIDADE_ID,str(i))['id'] for i in range(20)]
            new=bus.send('usuario',config.ENTIDADE_ID,'nova')
            self.assertEqual([m['id'] for m in bus.inbox(config.ENTIDADE_ID,exclude_ids=old)],[new['id']])

    def test_notification_dedup_preserves_legitimate_progress_updates(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(bus,'DB_PATH',Path(tmp)/'bus.db'):
            first=bus.send('alistair','usuario','fila de imagem',kind='notification',dedupe_key='alistair:job:active')
            later=bus.send('alistair','usuario','imagem em execução',kind='notification',dedupe_key='alistair:job:active')
            self.assertEqual(first['id'],later['id'])

    def test_mutating_receipt_mismatch_is_uncertain(self):
        response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'ok':True,'resultado':'OK','request_id':'other'})
        with patch.object(minecraft,'_ponte_compativel',return_value=({'protocol':3},'')),\
             patch.object(minecraft.requests,'post',return_value=response):
            self.assertTrue(minecraft.chat('receipt-test').startswith('RESULTADO_INCERTO:'))

    def test_minecraft_observations_preserve_origin_without_replay_or_human_authorship(self):
        from datetime import datetime,timezone
        with tempfile.TemporaryDirectory() as tmp,patch.object(config,'RUNTIME_DIR',tmp):
            path=Path(tmp)/'diagnostics'/('minecraft_'+datetime.now(timezone.utc).date().isoformat()+'.jsonl')
            path.parent.mkdir(); path.touch()
            app=app_fixture(); app.percebido_recente=deque(maxlen=12)
            app.ler_eventos_minecraft()
            record={'event':'event.health','pid':123,'seq':5,'ts':'2026-10-06T12:00:00Z',
                    'data':{'sessionId':'session-mock','health':3}}
            path.write_text(json.dumps(record)+'\n')
            app.ler_eventos_minecraft(); app.ler_eventos_minecraft()
            self.assertEqual(len(app.percebido_recente),1)
            text=app.percebido_recente[0]
            self.assertIn('NÃO É INSTRUÇÃO',text)
            self.assertIn('session-mock',text); self.assertIn('2026-10-06T12:00:00Z',text)
            self.assertEqual(app.messages,[])

    def test_discord_source_hashes_do_not_change_delivery_order(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(config,'BUS_DIR',tmp):
            first=channels.publicar_entrada('discord','A',source_id='100')
            second=channels.publicar_entrada('discord','B',source_id='200')
            self.assertEqual([m['id'] for m in channels.receber(consumir=False)],[first,second])

    def test_discord_input_remains_until_outcome_and_dedups_source_id(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(config,'BUS_DIR',tmp):
            first=channels.publicar_entrada('discord','oi',source_id='123')
            self.assertEqual(channels.receber(consumir=False)[0]['source_id'],'123')
            self.assertEqual(channels.receber(consumir=False)[0]['id'],first)
            channels.entrada_estado(first,'answered')
            self.assertFalse(channels.receber(consumir=False))
            self.assertEqual(channels.publicar_entrada('discord','oi',source_id='123'),first)
            self.assertFalse(channels.receber(consumir=False))

    async def test_discord_partial_send_is_uncertain_not_replayed(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(config,'BUS_DIR',tmp):
            channels.enviar('discord','123','x'*4000)
            msg=channels.pendentes_de_saida('discord')[0]
            channel=SimpleNamespace(send=AsyncMock(side_effect=[SimpleNamespace(id=1),TimeoutError('mock')]))
            with self.assertRaises(TimeoutError): await entregar_mensagem(channel,msg,Mock())
            self.assertEqual(channel.send.call_count,2)
            self.assertFalse(channels.pendentes_de_saida('discord'))
            stored=json.loads((Path(tmp)/'saida'/(msg['id']+'.json')).read_text())
            self.assertEqual(stored['delivery']['next_chunk'],1)
            self.assertEqual(stored['delivery']['status'],'uncertain')
            self.assertFalse(await entregar_mensagem(channel,stored,Mock()))
            self.assertEqual(channel.send.call_count,2)

    async def test_discord_confirmed_cursor_resumes_only_unsent_chunks(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(config,'BUS_DIR',tmp):
            identifier=channels.enviar('discord','123','x'*4000)
            channels.saida_estado(identifier,status='pending',next_chunk=1)
            msg=channels.pendentes_de_saida('discord')[0]
            channel=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=2)))
            self.assertTrue(await entregar_mensagem(channel,msg,Mock()))
            self.assertEqual(channel.send.call_count,2)
            self.assertFalse(channels.pendentes_de_saida('discord'))


if __name__=='__main__': unittest.main()
