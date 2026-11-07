"""R1/R7: gravações reais em SQLite temporário, sem LLM/modelos/rede."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import patch

import config
import main
from core import compaction, diagnostics
from memory import knowledge_store as saber
from memory.sqlite import init_db
from mind import reflection, scribe


class Autoria(unittest.TestCase):
    def test_local_synthetic_harness_is_not_human_history_or_learning(self):
        origin=scribe.origem_entrada({'id':'codex-test','nome':'Codex · ensaio'},'local',
            {'id':'in-test-one','metadata':{'synthetic_test':True,'test_actor':'Codex'}})
        self.assertEqual(origin['autor_tipo'],'sistema_teste')
        self.assertTrue(origin['synthetic_test'])
        self.assertEqual(scribe.extrair_por_regra('Meu nome é Nome de Personagem.',origem=origin),[])
        self.assertEqual(scribe.pos_turno('Meu nome é Nome de Personagem.','Entendi.',origem=origin)['fatos'],[])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='autoria-r1-')
        self.addCleanup(self.temp.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(saber.vetor, 'salvar'))
        self.stack.enter_context(patch.object(saber.vetor, 'buscar', return_value=[]))
        self.paths = {e: Path(self.temp.name)/f'{e}.db' for e in ('hoshino','lilith','alistair')}
        for path in self.paths.values():
            with patch.object(init_db, 'DB_PATH', str(path)):
                init_db.init_database(verbose=False)

    def entity(self, name):
        stack = ExitStack()
        for obj, key, value in ((config,'DB_PATH',str(self.paths[name])),
                                (saber,'DB_PATH',str(self.paths[name])),
                                (config,'ENTIDADE_ID',name),(config,'ENTIDADE_NOME',name.capitalize())):
            stack.enter_context(patch.object(obj,key,value))
        return stack

    def origin(self, author, name=None):
        return scribe.origem_entrada({'id':author,'nome':name or author},
            'localhub' if author == 'usuario' else 'interentidades',
            {'sender':author,'id':f'msg-{author}','source_id':f'source-{author}',
             'created_at':1234.5,'metadata':{'submission_id':f'submission-{author}'}},
            f'history-{author}')

    def rows(self, entity='hoshino'):
        with closing(sqlite3.connect(self.paths[entity])) as db:
            db.row_factory = sqlite3.Row
            return [saber.registro(dict(r)) for r in db.execute("SELECT * FROM memories WHERE status='active'")]

    def test_four_introductions_do_not_compete_for_user_name(self):
        with self.entity('hoshino'):
            for author, name in (('usuario','Gustavo'),('alistair','Alistair'),('lilith','Lilith'),('hoshino','Hoshino')):
                origin = self.origin(author)
                with diagnostics.context(turn_id=f'turn-{author}', input_ids=[origin['message_id']]):
                    findings = scribe.extrair_por_regra(f'Meu nome é {name}.',origem=origin)
                    self.assertEqual(len(scribe.registrar_achados(findings,'Gustavo')),len(findings))
            records = self.rows()
            self.assertEqual(len(records),4)
            by_subject = {r['evidencias'][0]['sujeito_id']:r for r in records}
            self.assertEqual(set(by_subject),{'usuario','alistair','lilith','hoshino'})
            self.assertIn('Gustavo',by_subject['usuario']['content'])
            for author,r in by_subject.items():
                evidence=r['evidencias'][0]
                self.assertEqual(evidence['autor_id'],author)
                self.assertEqual(evidence['ouvinte_id'],'hoshino')
                self.assertEqual(evidence['message_id'],f'msg-{author}')
                self.assertEqual(evidence['source_id'],f'source-{author}')
                self.assertEqual(evidence['submission_id'],f'submission-{author}')
                self.assertEqual(evidence['history_id'],f'history-{author}')
                self.assertEqual(evidence['turn_id'],f'turn-{author}')
                self.assertEqual(evidence['timestamp'],1234.5)
                self.assertEqual(evidence['basis'],'informacao_declarada_nao_verificada_externamente')
                self.assertEqual(r['tipo'],'fato')
                self.assertEqual(r['confianca'],.95)
            # Nova conexão (restart de acesso), sem reclassificar/migrar dados.
            recalled=saber.recall('nome chama Gustavo Alistair Lilith Hoshino',20,estruturado=True)
            self.assertEqual({r['id'] for r in recalled if r['tipo']=='fato'}, {r['id'] for r in records})

    def test_properties_same_name_are_scoped_by_subject_and_zero_survives(self):
        with self.entity('hoshino'):
            for author,name in (('usuario','Gustavo'),('alistair','Alistair'),('lilith','Lilith')):
                findings=scribe.extrair_por_regra('Minha cor é azul.',origem=self.origin(author,name))
                for finding in findings: finding['confianca']=0.0
                scribe.registrar_achados(findings,name)
            with closing(sqlite3.connect(config.DB_PATH)) as db:
                db.row_factory=sqlite3.Row
                rows=[saber.registro(dict(r)) for r in db.execute('SELECT * FROM properties')]
            self.assertEqual(len(rows),3)
            self.assertEqual({r['evidencias'][0]['sujeito_id'] for r in rows},{'usuario','alistair','lilith'})
            self.assertTrue(all(r['confianca']==0 for r in rows))
            self.assertTrue(all(r['evidencias'][0]['ouvinte_id']=='hoshino' for r in rows))

    def test_three_databases_remain_independent_after_reopening(self):
        for listener,author,name in (('hoshino','usuario','Gustavo'),('lilith','alistair','Alistair'),('alistair','lilith','Lilith')):
            with self.entity(listener):
                scribe.registrar_achados(scribe.extrair_por_regra(f'Eu sou {name}.',origem=self.origin(author)),name)
        for entity,subject in (('hoshino','usuario'),('lilith','alistair'),('alistair','lilith')):
            rows=self.rows(entity)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['evidencias'][0]['sujeito_id'],subject)
            self.assertEqual(rows[0]['evidencias'][0]['ouvinte_id'],entity)

    def test_questions_quotes_roleplay_hypotheses_are_not_self_declarations(self):
        origin=self.origin('lilith')
        for text in ('Meu nome é Gustavo?', 'Ele disse: "eu sou Gustavo".',
                     'Finja que eu sou Gustavo.', 'Hipótese: eu sou Gustavo.',
                     'Imagine que meu nome é Gustavo.', 'Se eu sou Gustavo, quem é você?',
                     'Eu diria: meu nome é Gustavo.', '“Meu nome é Gustavo.”',
                     'Talvez meu nome é Gustavo.', 'Refletindo: eu sou Gustavo.',
                     'Acho que meu nome é Gustavo.'):
            self.assertEqual(scribe.extrair_por_regra(text,origem=origin),[],text)
        self.assertTrue(scribe.extrair_por_regra('Meu nome é Gustavo. Tudo bem?',origem=self.origin('usuario')))

    def test_entity_claim_cannot_change_actual_author_or_human_name(self):
        finding=scribe.extrair_por_regra('Eu sou Gustavo.',origem=self.origin('alistair'))[0]
        self.assertEqual(finding['origem']['autor_nome'],'Alistair')
        self.assertEqual(finding['origem']['sujeito_id'],'alistair')
        self.assertNotIn('nome_detectado',finding)
        self.assertNotEqual(finding['chave'],'nome_do_usuario')

    def test_same_declared_name_on_two_subjects_does_not_supersede(self):
        with self.entity('hoshino'):
            for author in ('usuario','alistair','lilith'):
                scribe.registrar_achados(scribe.extrair_por_regra('Eu sou Gustavo.',origem=self.origin(author)),'Gustavo')
            rows=self.rows()
            self.assertEqual(len(rows),3)
            self.assertEqual({r['evidencias'][0]['sujeito_id'] for r in rows},{'usuario','alistair','lilith'})

    def test_unattributed_legacy_is_not_silently_superseded_or_migrated(self):
        with self.entity('hoshino'):
            saber.remember('Gustavo se chama Gustavo',entidades=['Gustavo'],chave='nome_do_usuario',fonte='escriba',confianca=0)
            with closing(sqlite3.connect(config.DB_PATH)) as db:
                old=db.execute('SELECT id,type,source,confidence,links,status FROM memories').fetchone()
            scribe.registrar_achados(scribe.extrair_por_regra('Eu sou Gustavo.',origem=self.origin('alistair')),'Gustavo')
            with closing(sqlite3.connect(config.DB_PATH)) as db:
                after=db.execute('SELECT id,type,source,confidence,links,status FROM memories WHERE id=?',(old[0],)).fetchone()
            self.assertEqual(after,old)
            self.assertEqual(len(self.rows()),2)

    def test_compaction_preserves_attribution_and_does_not_guess_legacy_author(self):
        with self.entity('lilith'):
            origin=self.origin('alistair')
            messages=[{'role':'user','content':'Eu sou Alistair.','_origem':origin},
                      {'role':'user','content':'Eu sou Gustavo.'}]
            compaction.resgatar_duraveis(messages,'usuário')
            rows=self.rows('lilith')
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['evidencias'][0]['sujeito_id'],'alistair')
            self.assertIn('msg-alistair',compaction.transcrever(messages))
            self.assertIn('Alistair',compaction.transcrever(messages))
            normalized=main.InterfaceHoshino._normalizar_mensagens_ollama(messages)
            self.assertNotIn('_origem',normalized[0])

    def test_extraction_reflection_and_tool_memory_keep_categories_and_evidence(self):
        with self.entity('hoshino'):
            origin=self.origin('usuario','Gustavo')
            scribe.aplicar_extracao(json.dumps([{'tipo':'fato','conteudo':'Gustavo inferência sobre Saturno','confianca':0},
                                               {'tipo':'hipotese','conteudo':'Saturno hipótese sobre Lilith','confianca':None}]),origem=origin)
            reflection.aplicar('- Saturno é uma reflexão pessoal.',[{'id':'episode-origin'}])
            with diagnostics.context(turn_id='turn-tool',input_sources=[origin]):
                saber.remember('Saturno registro pela ferramenta',tipo='hipotese',confianca=0)
            rows=self.rows()
            self.assertEqual({r['tipo'] for r in rows},{'interpretacao','hipotese','reflexao'})
            inferred=next(r for r in rows if 'inferência' in r['content'])
            self.assertEqual(inferred['confianca'],0)
            self.assertEqual(inferred['evidencias'][0]['autor_id'],'usuario')
            self.assertIsNone(inferred['evidencias'][0]['sujeito_id'])
            tool=next(r for r in rows if 'ferramenta' in r['content'])
            self.assertEqual(tool['evidencias'][0]['turn_id'],'turn-tool')
            self.assertEqual(tool['evidencias'][0]['message_id'],'msg-usuario')
            self.assertIsNone(tool['evidencias'][0]['sujeito_id'])

    def test_episodes_name_listener_and_speaker_without_hardcoded_hoshino(self):
        for entity,author in (('hoshino','alistair'),('lilith','usuario')):
            with self.entity(entity):
                origin=self.origin(author,'Gustavo' if author=='usuario' else 'Alistair')
                main.salvar_episodio('Olá.','Olá também.',person_id=author,autoria=origin)
            with closing(sqlite3.connect(self.paths[entity])) as db:
                text,context=db.execute('SELECT what_happened,context FROM episodes').fetchone()
            self.assertTrue(text.startswith(origin['autor_nome']+':'))
            self.assertIn(entity.capitalize()+": 'Olá também.'",text)
            self.assertEqual(json.loads(context)['autoria']['message_id'],f'msg-{author}')
            if entity=='lilith': self.assertNotIn('Hoshino',text)


if __name__=='__main__': unittest.main()
