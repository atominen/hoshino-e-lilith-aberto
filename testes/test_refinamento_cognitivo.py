"""Contratos cognitivos em bancos descartáveis; sem LLM, GPU ou dados reais."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import config

if not Path(config.DB_PATH).resolve().is_relative_to(Path('/tmp')):
    raise RuntimeError('Use testes/executar_isolado.py; dados reais não são fixtures.')

from core import bd, dispatch, history, prompting
from memory import cognitive_notes as notes, knowledge_store as store, records
from memory.sqlite import init_db
from mind import scribe


class Refinamento(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'mind.db'
        for obj, name, value in ((config, 'DB_PATH', str(self.path)),
                                 (config, 'ENTIDADE_ID', 'hoshino'),
                                 (store, 'DB_PATH', str(self.path)),
                                 (init_db, 'DB_PATH', str(self.path))):
            p = patch.object(obj, name, value)
            p.start(); self.addCleanup(p.stop)
        init_db.init_database(verbose=False)
        for name, value in (('buscar', []), ('salvar', True)):
            p = patch.object(store.vetor, name, return_value=value)
            p.start(); self.addCleanup(p.stop)
        self.graph = {'nodes': [{'id': 'a', 'kind': 'problema', 'label': 'Comparar trajetórias'},
                                {'id': 'b', 'kind': 'hipotese', 'label': 'Reduzir erro numérico'}],
                      'edges': [{'from': 'a', 'to': 'b', 'relation': 'depende_de', 'basis': 'hipotese'}],
                      'tables': [{'title': 'Plano', 'columns': ['Método', 'Verificação'],
                                  'rows': [['RK4', 'Medir convergência, ainda não executado']]}]}

    def rows(self, query, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(query, args).fetchall()

    def test_compatible_similar_facts_remain_active(self):
        a = 'A pessoa gosta de café brasileiro forte sem açúcar pela manhã.'
        b = 'A pessoa gosta de café brasileiro forte sem açúcar pela noite.'
        self.assertGreater(store._semelhanca(a,b), .75)
        for text in (a,b):store.remember(text, entidades=['pessoa'], tipo='preferencia')
        self.assertEqual(self.rows('SELECT status FROM memories'), [('active',), ('active',)])

    def test_explicit_attribute_correction_still_replaces_previous(self):
        for value in ('azul', 'verde'):
            store.remember('Cor favorita: '+value, entidades=['pessoa'], chave='cor_favorita')
        self.assertEqual(self.rows('SELECT status FROM memories ORDER BY rowid'), [('superseded',), ('active',)])

    def test_popular_recent_confident_but_irrelevant_memory_stays_out(self):
        store.remember('A bicicleta é vermelha.', confianca=1)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE memories SET access_count=10')
        mid = self.rows('SELECT id FROM memories')[0][0]
        for distance in (100., 1., None, -1., float('nan'), float('inf'), 'inválida'):
            with self.subTest(distance=distance), patch.object(store.vetor, 'buscar', return_value=[{'id':mid,'distancia':distance}]):
                self.assertEqual(store.recall('Qual a capital da Mongólia?'), [])
        self.assertEqual(self.rows('SELECT access_count FROM memories'), [(10,)])

    def test_strong_semantic_match_and_lexical_match_are_supported(self):
        store.remember('A bicicleta é vermelha.')
        mid = self.rows('SELECT id FROM memories')[0][0]
        with patch.object(store.vetor, 'buscar', return_value=[{'id':mid,'distancia':.2}]):
            self.assertEqual(len(store.recall('Qual a cor do veículo de duas rodas?')), 1)
        self.assertEqual(len(store.recall('bicicleta')), 1)
        self.assertEqual(store.recall('bicicleta', 0), [])

    def test_stale_vector_does_not_resurrect_replaced_record(self):
        store.remember('A bicicleta é vermelha.', entidades=['bicicleta'], chave='cor')
        old = self.rows('SELECT id FROM memories')[0][0]
        store.remember('A bicicleta é azul.', entidades=['bicicleta'], chave='cor')
        with patch.object(store.vetor, 'buscar', return_value=[{'id':old,'distancia':0.,'texto':'vermelha'}]):
            result=store.recall('bicicleta', estruturado=True)
        self.assertEqual(len(result),1)
        self.assertIn('azul',result[0]['content'])

    def test_recency_offsets_and_legacy_are_equivalent(self):
        instant = datetime.now(timezone.utc)-timedelta(days=1)
        local = instant.astimezone(history.local_timezone()).replace(tzinfo=None).isoformat()
        self.assertAlmostEqual(store._recencia(local),store._recencia(instant.isoformat()),places=5)
        self.assertEqual(store._recencia('inválido'),.5)
        self.assertLessEqual(store._recencia((instant+timedelta(days=100)).isoformat()),1.)

    def test_episode_recall_uses_current_sql_not_stale_vector_text(self):
        for identifier,status in (('active','active'),('removed','retired')):
            bd.executar("INSERT INTO episodes(id,created_at,what_happened,status,source) VALUES(?,?,?,?,?)",
                        (identifier,history.utc_timestamp(),'Bicicleta reparada; registro atual',status,'fixture'),strict=True)
        hits=[dict(id=i,texto='A bicicleta foi destruída; índice antigo',distancia=0.) for i in ('orphan','removed','active','active')]
        with patch.object(store.vetor,'buscar',return_value=hits):
            result=store.recall_episodes('bicicleta')
        self.assertEqual(len(result),1)
        self.assertIn('registro atual',result[0]);self.assertNotIn('destruída',result[0])
        with patch.object(store.vetor,'buscar',return_value=[dict(id='active',distancia=100.)]):
            self.assertEqual(store.recall_episodes('capital da Mongólia'),[])

    def test_user_taste_is_stored_without_copying_it_to_entity(self):
        found=scribe.extrair_por_regra('Gosto de jogar xadrez', origem=scribe.origem_entrada())
        self.assertTrue(any('gosto_usuario' in a for a in found))
        with patch.object(scribe.personality,'registrar_gosto') as own:
            self.assertTrue(scribe.registrar_achados(found))
        own.assert_not_called()
        self.assertTrue(store.recall('xadrez'))

    def test_quotes_code_and_technical_complaints_are_not_personality(self):
        self.assertEqual(scribe.evidencias_do_comportamento('> Senti falta, por que não veio?\n```\nsenti falta?\n```'),[])
        self.assertFalse(any(t=='curiosidade' for t,*_ in scribe.evidencias_do_comportamento('Pode repetir?')))
        self.assertFalse(any(t=='calor' for t,*_ in scribe.evidencias_do_comportamento('A frase era "senti falta".')))
        self.assertFalse(any(t=='teimosia' for t,*_ in scribe.evidencias_do_comportamento('Não concordo com essa conclusão.')))
        for text in ('O comando está errado', 'O app ficou ruim', '"Muito bom!"', 'Muito bom mas está errado'):
            self.assertIsNone(scribe.reacao_do_usuario(text))
        self.assertEqual(scribe.reacao_do_usuario('ficou perfeito, valeu!'),'elogio')

    def test_draft_is_hypothesis_and_persists_across_reload(self):
        saved=notes.save_model('Trajetórias',self.graph,mode='rascunho')
        row=bd.um('SELECT * FROM memories WHERE id=?',(saved['id'],))
        self.assertEqual(row['type'],'hipotese')
        self.assertEqual(notes.models(saved['id'])['items'][0]['graph'],self.graph)
        self.assertIn('RASCUNHO NÃO VALIDADO',records.registro(row)['semantic_text'])
        self.assertEqual(notes.save_model('Trajetórias',self.graph,mode='rascunho')['id'],saved['id'])
        self.assertEqual(len(self.rows('SELECT id FROM memories')),1)

    def test_draft_does_not_fake_observations_or_evidence(self):
        for kind in ('observacao','evento','fato_informado'):
            graph=copy.deepcopy(self.graph);graph['nodes'][0]['kind']=kind
            with self.assertRaises(ValueError):notes.save_model('Sem fonte',graph,mode='rascunho')
        with self.assertRaises(ValueError):notes.save_model('Sem fonte',self.graph,[])
        with self.assertRaises(ValueError):notes.save_model('Fonte falsa',self.graph,[{'table':'episodes','id':'missing'}],mode='rascunho')
        with self.assertRaises(ValueError):notes.save_model('Modo falso',self.graph,mode='qualquer')
        self.assertEqual(self.rows('SELECT id FROM memories'),[])

    def test_draft_revision_preserves_original_and_cannot_return_stale_success(self):
        saved=notes.save_model('Trajetórias',self.graph,mode='rascunho')
        revised=copy.deepcopy(self.graph);revised['nodes'][0]['label']='Comparar erro em passos distintos'
        notes.save_model('Trajetórias',revised,mode='rascunho',previous=saved['id'],reason='Definir teste de convergência')
        self.assertEqual(self.rows('SELECT status FROM memories ORDER BY rowid'),[('superseded',),('active',)])
        with self.assertRaises(ValueError):notes.save_model('Trajetórias',self.graph,mode='rascunho')

    def test_draft_can_be_revised_with_real_evidence(self):
        saved=notes.save_model('Trajetórias',self.graph,mode='rascunho')
        bd.executar("INSERT INTO episodes(id,created_at,what_happened) VALUES(?,?,?)",
                    ('measured',history.utc_timestamp(),'Fixture: resultados de convergência disponíveis'),strict=True)
        result=notes.save_model('Trajetórias',self.graph,[{'table':'episodes','id':'measured'}],
                               previous=saved['id'],reason='Adicionar resultado observado')
        self.assertEqual(notes.models(result['id'])['items'][0]['mode'],'fundamentado')
        self.assertEqual(self.rows('SELECT type FROM memories WHERE id=?',(result['id'],)),[('interpretacao',)])

    def test_agent_tool_roundtrip_and_discovery_in_both_entities(self):
        for entity in ('hoshino','lilith'):
            with self.subTest(entity=entity), patch.object(config,'ENTIDADE_ID',entity):
                names={s['function']['name'] for s in dispatch.esquemas('Faça um rascunho do problema complexo',incluir_proprias=False)}
                self.assertIn('oficina_logica',names)
                result=json.loads(dispatch._cognitive_note('oficina_logica',dict(operacao='salvar',titulo='Plano '+entity,
                                diagrama=self.graph,modo='rascunho')))
                loaded=json.loads(dispatch._cognitive_note('oficina_logica',dict(operacao='ler',id=result['id'])))
                self.assertEqual(loaded['items'][0]['graph'],self.graph)
        schema=next(s['function']['parameters'] for s in dispatch.ESQUEMAS if s['function']['name']=='oficina_logica')
        self.assertIn('nodes',schema['properties']['diagrama']['properties'])

    def test_continuity_guidance_separates_assumption_from_observation(self):
        self.assertIn('correção',prompting.CONTINUIDADE_CURTO)
        self.assertIn('pergunta curta',prompting.CONTINUIDADE_CURTO)
        self.assertIn('não copio',prompting.CONTINUIDADE_CURTO)
        self.assertIn('não resolve nem testa',prompting.APOIO_VISUAL)


if __name__=='__main__':unittest.main()
