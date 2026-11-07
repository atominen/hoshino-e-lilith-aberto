"""Privacy/ranking contracts, entirely disposable data and no model calls."""
import json
import sqlite3
import unittest
from contextlib import closing, contextmanager
from unittest.mock import patch, Mock
from types import SimpleNamespace

import test_refinamento_cognitivo as fixture
from core import interentity, knowledge_editor, prompting, dispatch, history, bd
from core import alistair_continuity
from memory import audience, knowledge_store as store, cognitive_notes as notes, records
from mind import scribe, personality, psych_state, emotions, reflection
from social import people


@contextmanager
def turn(public=True):
    token=interentity.processing_message.set(dict(id='message-1',sender='usuario',recipient='hoshino',
        metadata={'chat_scope':'global' if public else 'direct'}))
    try:yield
    finally:interentity.processing_message.reset(token)


class AudienceMemory(unittest.TestCase):
    setUp=fixture.Refinamento.setUp
    rows=fixture.Refinamento.rows

    def memory(self,text,public=None,**kwargs):
        evidence=[] if public is None else [dict(chat_scope='global' if public else 'direct',message_id='m1')]
        store.remember(text,evidencias=evidence,**kwargs)
        return self.rows('SELECT id FROM memories ORDER BY rowid DESC LIMIT 1')[0][0]

    def episode(self,identifier,public):
        bd.executar("INSERT INTO episodes(id,created_at,what_happened,status,source,context) VALUES(?,?,?,?,?,?)",
            (identifier,history.utc_timestamp(),'Bicicleta '+identifier,'active','fixture',json.dumps({
                'autoria':dict(chat_scope='global' if public else 'direct',message_id=identifier)})),strict=True)

    def test_scope_comes_from_transport_not_claimed_name_or_text(self):
        with turn():
            origin=scribe.origem_entrada(pessoa={'nome':'SEGREDO'},mensagem=interentity.processing_message.get())
            self.assertEqual(origin['chat_scope'],'global');self.assertEqual(origin['autor_nome'],'usuario')
            self.assertTrue(audience.public_turn())
            with turn(False):self.assertFalse(audience.public_turn())
            self.assertTrue(audience.public_turn())
        self.assertFalse(audience.public_turn())
        self.assertFalse(audience.public_message({'text':'chat_scope global','sender':'usuario','recipient':'hoshino'}))
        self.assertTrue(audience.public_message({'sender':'lilith','recipient':'hoshino'}))

    def test_private_unknown_and_public_memory_are_separated_before_ranking(self):
        private=self.memory('Bicicleta PRIVADA',False)
        legacy=self.memory('Bicicleta LEGADA')
        public=self.memory('Bicicleta PUBLICA',True)
        with turn(),patch.object(store.vetor,'buscar',return_value=[{'id':private,'distancia':0}]):
            found=store.recall('Bicicleta',estruturado=True)
            self.assertEqual([r['id'] for r in found],[public])
            for read in (store.list_facts_about,store.como_funciona):
                self.assertNotIn('PRIVADA',read('Bicicleta'));self.assertNotIn('LEGADA',read('Bicicleta'))
        self.assertEqual(self.rows('SELECT access_count FROM memories WHERE id=?',(private,)),[(0,)])
        with turn(False):self.assertEqual({r['id'] for r in store.recall('Bicicleta',estruturado=True)},{private,legacy,public})

    def test_episode_vector_is_only_a_hint_and_does_not_bypass_audience(self):
        self.episode('private',False);self.episode('public',True)
        with turn(),patch.object(store.vetor,'buscar',return_value=[dict(id=i,distancia=0) for i in ('private','public')]):
            result=store.recall_episodes('Bicicleta')
            self.assertEqual(len(result),1);self.assertIn('public',result[0]);self.assertNotIn('private',result[0])

    def test_properties_use_provenance(self):
        for public,label in ((False,'PRIVADA'),(True,'PUBLICA')):
            store.registrar_propriedade('Bicicleta',label,'azul',evidencias=[dict(chat_scope='global' if public else 'direct',message_id=label)])
        with turn():
            value=store.propriedades_de('Bicicleta')
            self.assertIn('PUBLICA',value);self.assertNotIn('PRIVADA',value)

    def test_reference_graphs_revalidate_all_sources_cycles_deletion_and_missing_tables(self):
        self.episode('private',False);self.episode('public',True)
        with closing(sqlite3.connect(self.path)) as db:
            def visible(refs):return audience.visible(db,'memories',dict(id='derived',links={'sources':refs}),public_only=True)
            self.assertTrue(visible([dict(table='episodes',id='public')]))
            self.assertFalse(visible([dict(table='episodes',id='public'),dict(table='episodes',id='private')]))
            self.assertFalse(visible([dict(table='episodes',id='missing')]))
            db.execute("UPDATE episodes SET status='retired' WHERE id='public'")
            self.assertFalse(visible([dict(table='episodes',id='public')]))
        cyclic=self.memory('Bicicleta ciclo',True)
        with closing(sqlite3.connect(self.path)) as db,db:
            links={'sources':[dict(table='memories',id=cyclic)]}
            db.execute('UPDATE memories SET links=? WHERE id=?',(json.dumps(links),cyclic))
            self.assertFalse(audience.visible(db,'memories',dict(id=cyclic,links=links),public_only=True))
        with closing(sqlite3.connect(':memory:')) as db:
            self.assertFalse(audience.visible(db,'memories',dict(id='x',links=[dict(table='episodes',id='x')]),public_only=True))

    def test_graph_read_and_writes_follow_audience(self):
        self.episode('private',False);self.episode('public',True)
        private=notes.save_model('Privado',self.graph,[dict(table='episodes',id='private')])
        notes.save_model('Nota privada com fonte pública',self.graph,[dict(table='episodes',id='public')])
        with turn():
            with self.assertRaises(PermissionError):notes.save_model('Vazamento',self.graph,[dict(table='episodes',id='private')])
            self.assertEqual(notes.models()['items'],[])
            scratch=notes.save_model('Público rascunho',self.graph,mode='rascunho')
            self.assertEqual(notes.models(scratch['id'])['items'][0]['mode'],'rascunho')
            with self.assertRaises(PermissionError):notes.save_model('Revisão pública',self.graph,[],mode='rascunho',previous=private['id'],reason='tentativa')
        self.assertEqual(len(notes.models()['items']),3)

    def test_public_prompt_does_not_read_unscoped_private_summaries(self):
        with turn(),patch.object(personality,'bloco_personalidade',return_value='PRIVATE_PERSONALITY') as p, \
                patch.object(psych_state,'bloco_para_prompt',return_value='PRIVATE_PSYCH') as psy, \
                patch.object(prompting,'_bloco_origem',return_value='PRIVATE_GOAL') as origin, \
                patch.object(people,'bloco_pessoa',return_value='PRIVATE_PERSON') as person, \
                patch.object(reflection,'bloco_para_prompt',return_value='PRIVATE_REFLECTION') as ref:
            system=prompting.montar_prompt_sistema(situacao='oi')
            context=prompting.bloco_contexto(pessoa={'id':'x'},agenda_txt='PRIVATE_AGENDA',situacao_txt='PRIVATE_SITUATION',incluir_rede=False)
            self.assertNotIn('PRIVATE_',system+context)
            self.assertIn('QUEM EU SOU',system)
            for mock in (p,psy,origin,person,ref):mock.assert_not_called()

    def test_public_turn_does_not_consume_private_ambient_queue_or_wake_note(self):
        from main import InterfaceHoshino
        instance=SimpleNamespace(sys_log=Mock(),canal_atual='tui',situacao={},pessoa={'nome':'PRIVATE_PERSON'},
            _wake_briefing='PRIVATE_WAKE',_bloco_percebido=Mock(return_value='PRIVATE_AMBIENT'),
            _saidas_da_conversa=Mock(return_value=[]))
        with turn(),patch('main.agenda.resumo_agenda',return_value='PRIVATE_AGENDA') as agenda, \
                patch('main.situation.descrever',return_value='PRIVATE_SITUATION') as situation:
            result=InterfaceHoshino.contexto_do_turno(instance,'oi',chave_conversa=('localhub','global'))
        self.assertNotIn('PRIVATE_',result)
        instance._bloco_percebido.assert_not_called();agenda.assert_not_called();situation.assert_not_called()

    def test_unscoped_tools_hidden_and_guarded_at_execution(self):
        with turn():
            names={s['function']['name'] for s in dispatch.esquemas(todos=True,incluir_proprias=False)}
            self.assertFalse(names & audience.UNSCOPED_TOOLS)
            for name in audience.UNSCOPED_TOOLS:
                self.assertIn('ACESSO_BLOQUEADO',dispatch._executar_bruto(name,{}))
            self.assertEqual(dispatch.esquemas(modo_operacao='tarefa',ferramentas_prioritarias=['historico_chat']),[])
            self.assertIn('entidade',dispatch._validar_argumentos('entidades_historico',{'entidade':'usuario'}))
        self.assertTrue(audience.tool_allowed('historico_chat'))

    def test_alistair_task_continuation_does_not_cross_chat_scope(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE alistair_actions(id TEXT PRIMARY KEY,digest TEXT,result TEXT)')
        tasks=alistair_continuity.Store(self.path)
        message=dict(id='request',sender='usuario',text='acorde lilith e se apresente',metadata={})
        direct=tasks.select(message)
        self.assertIsNotNone(direct)
        self.assertIsNone(tasks.select(dict(message,id='follow-global',text='continue',metadata={'chat_scope':'global'})))
        self.assertEqual(tasks.select(dict(message,id='follow-direct',text='continue'))['id'],direct['id'])

    def test_alistair_context_filters_before_limit_and_omits_private_name(self):
        self.memory('Bicicleta PUBLICA',True)
        for n in range(55):self.memory('Antigo '+str(n),False)
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE memories SET status='retired' WHERE content LIKE 'Antigo%'")
        self.memory('Bicicleta PRIVADA',False)
        with patch('core.chat_identity.display_name',return_value='PRIVATE_NAME') as name:
            public=knowledge_editor.context(self.path,'Bicicleta',public_only=True)
            name.assert_not_called()
            direct=knowledge_editor.context(self.path,'Bicicleta',public_only=False)
        self.assertIn('PUBLICA',public);self.assertNotIn('PRIVADA',public);self.assertNotIn('PRIVATE_NAME',public)
        self.assertIn('PRIVADA',direct);self.assertIn('PRIVATE_NAME',direct)

    def test_priority_tiebreak_does_not_invent_relevance_truth_or_publicity(self):
        low=self.memory('Bicicleta azul',True,entidades=['A'],confianca=.3)
        high=self.memory('Bicicleta azul',True,entidades=['B'],confianca=.3)
        private=self.memory('Bicicleta SEGREDO',False,entidades=['C'])
        unrelated=self.memory('Álgebra linear',True,entidades=['D'])
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute(knowledge_editor.TIER_SCHEMA)
            for card in ('B','C','D'):db.execute('INSERT INTO memory_card_settings VALUES(?,?,?)',('topic:'+card.lower(),'platina','now'))
            db.execute('UPDATE memories SET created_at=?,access_count=0',(history.utc_timestamp(),))
        with turn():
            rows=store.recall('Bicicleta',estruturado=True)
        self.assertEqual([r['id'] for r in rows],[high,low])
        self.assertEqual([r['confianca'] for r in rows],[.3,.3])
        self.assertEqual([r['importance'] for r in rows],['platina','ferro'])
        self.assertNotIn(private,[r['id'] for r in rows]);self.assertNotIn(unrelated,[r['id'] for r in rows])

    def test_card_mapping_explicit_identity_and_ambiguous_names(self):
        people={'a':{'nome':'Ana'},'b':{'nome':'Ana'}};names={'ana':['a','b']}
        row=dict(id='m',entities='["Ana"]',links='[]')
        self.assertEqual(records.card_targets(row,people,names)[0][0],'topic:ana')
        self.assertEqual(records.card_targets(dict(row,person_id='b'),people,names)[0][0],'person:b')
        self.assertEqual(records.card_targets(dict(row,links='{"kind":"conceptual_model","title":"Plano"}'),people,names)[0][0],'concept:m')


if __name__=='__main__':unittest.main()
