"""Regressões de categorias e confiança, usando somente banco isolado."""
import json
import sqlite3
import unittest
import tempfile
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import config
# This historical group performs DELETE in its fixture. Refuse an accidental
# direct invocation before importing stores that could open production data.
if not any(Path(config.DB_PATH).resolve().is_relative_to(Path(p)) for p in ('/tmp','/var/tmp')):
    raise RuntimeError('Use testes/executar_isolado.py; banco mental real não é fixture.')
from memory.sqlite import init_db
from memory import knowledge_store as saber
from mind import reflection, scribe, night_reflection


class CognitiveConsolidation(unittest.TestCase):
    def setUp(self):
        from core import bd, interentity
        from memory import cognitive_notes
        self.bd=bd;self.notes=cognitive_notes
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        for obj,name,value in ((config,'RAIZ',self.root),(config,'ENTIDADE_ID','hoshino'),
                               (config,'RUNTIME_DIR',str(self.root/'runtime')),
                               (interentity,'DB_PATH',self.root/'mail.sqlite3')):
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.paths={}
        for who in ('hoshino','lilith','alistair'):
            path=self.root/'entidades'/who/'memory'/'sqlite'/(who+'.db');path.parent.mkdir(parents=True)
            self.paths[who]=path
            with patch.object(init_db,'DB_PATH',str(path)):init_db.init_database(verbose=False)
        p=patch.object(config,'DB_PATH',str(self.paths['hoshino']));p.start();self.addCleanup(p.stop)
        self.bd.executar("INSERT INTO episodes(id,created_at,what_happened,action_taken,result,source,context) VALUES(?,?,?,?,?,?,?)",
            ('experience-1','2026-10-10T12:00:00Z','Um comando declarou sucesso sem alterar o arquivo',
             'reabrir arquivo','hash diferente do esperado','ensaio',json.dumps({'autoria':{'autor_nome':'Gustavo','message_id':'message-1'}})),strict=True)
        self.graph={'nodes':[{'id':'a','label':'Recibo de execução','kind':'observacao'},
                             {'id':'b','label':'Verificação independente','kind':'condicao'}],
                    'edges':[{'from':'a','to':'b','relation':'exige','basis':'inferencia',
                              'conditions':['arquivo mutável'],'exceptions':['consulta sem efeito']}],
                    'tables':[{'title':'Comparação','columns':['Fonte','Limite'],
                               'rows':[['recibo','não prova conteúdo']]}]}
        self.refs=[dict(table='episodes',id='experience-1')]

    def test_private_diary_not_public_recall_nor_summary_or_other_entity(self):
        result=self.notes.diary_write('Dúvida','Uma confidência que não quero compartilhar.',self.refs)
        self.assertTrue(result['verified']);self.assertTrue(self.notes.diary_read(result['id'])['items'])
        self.assertNotIn('confidência',reflection.bloco_para_prompt())
        self.assertNotIn('confidência',' '.join(reflection.ultimas()))
        self.assertEqual(self.bd.um('SELECT COUNT(*) n FROM memories')['n'],0)
        with self.notes.administrative_scope(self.paths['lilith'],'lilith'):
            with self.assertRaises(ValueError):self.notes.diary_read(result['id'])
            self.assertEqual(self.notes.diary_read()['items'],[])
        from mind import daily_summary
        prepared=daily_summary.prepare('2026-10-10',agora='2026-10-10T18:00:00Z')
        self.assertNotIn('confidência',prepared['prompt'])

    def test_diary_partial_share_durable_dedup_no_wake_or_private_original(self):
        from core import interentity
        result=self.notes.diary_write('Dúvida','Quero guardar isto. Posso compartilhar esta descoberta.',self.refs)
        shared=self.notes.diary_share(result['id'],'lilith','Posso compartilhar esta descoberta.')
        repeat=self.notes.diary_share(result['id'],'lilith','Posso compartilhar esta descoberta.')
        self.assertEqual(shared['message_id'],repeat['message_id']);self.assertTrue(repeat['deduplicated'])
        row=interentity.inbox('lilith')[0]
        self.assertNotIn('Quero guardar isto',json.dumps(row));self.assertFalse(shared['read_confirmed'])
        self.assertFalse(interentity.pending_wake_requests('lilith'))
        with self.assertRaises(ValueError):self.notes.diary_share(result['id'],'lilith','Texto que não consta')

    def test_diary_restart_idempotence_and_request_collision(self):
        result=self.notes.diary_write('Dúvida','Conteúdo reservado.',self.refs,request_id='same')
        self.assertEqual(self.notes.diary_write('Dúvida','Conteúdo reservado.',self.refs,request_id='same')['id'],result['id'])
        with self.assertRaises(ValueError):self.notes.diary_write('Dúvida','Outro conteúdo.',self.refs,request_id='same')
        self.assertEqual(self.notes.diary_read(result['id'])['items'][0]['text'],'Conteúdo reservado.')

    def test_graph_revision_preserves_evidence_conditions_and_zero_confidence(self):
        self.graph['nodes'][0]['confidence']=0.0
        original=self.notes.save_model('Verificação',self.graph,self.refs)
        self.assertTrue(original['verified'])
        loaded=self.notes.models(original['id'])['items'][0]
        self.assertEqual(loaded['graph'],self.graph);self.assertIn('Gustavo',loaded['evidence'][0]['context'])
        self.graph['nodes'][0]['label']='Recibo parcial'
        new=self.notes.save_model('Verificação',self.graph,self.refs,previous=original['id'],reason='Nova interpretação revisável')
        self.assertNotEqual(new['id'],original['id'])
        old=self.bd.um('SELECT * FROM memories WHERE id=?',(original['id'],));self.assertEqual(old['status'],'superseded')
        with self.assertRaises(ValueError):self.notes.save_model('Outro',self.graph,self.refs,previous=original['id'],reason='Edição desatualizada')
        self.assertEqual(self.notes.models(new['id'])['items'][0]['graph']['nodes'][0]['confidence'],0.)

    def test_invalid_graph_or_invented_evidence_never_becomes_memory(self):
        for bad in (dict(self.graph,edges=[{'from':'a','to':'missing','relation':'causa','basis':'hipotese'}]),
                    dict(self.graph,edges=[{'from':'a','to':'b','relation':'causa'}]),
                    dict(self.graph,nodes=[{'id':'a','kind':'hipotese','label':'x','confidence':float('nan')}])):
            with self.assertRaises(ValueError):self.notes.save_model('Inválido',bad,self.refs)
        with self.assertRaises(ValueError):self.notes.save_model('Sem origem',self.graph,[dict(table='episodes',id='inventado')])
        self.assertEqual(self.bd.um('SELECT COUNT(*) n FROM memories')['n'],0)

    def test_experiential_lesson_is_conditional_revisable_not_fact_or_personality_mutation(self):
        traits=self.bd.consultar('SELECT * FROM traits')
        result=self.notes.learn_experience(['experience-1'],'O recibo era insuficiente','Quando altero arquivo',
                                          'Reabrir e verificar conteúdo',['Consultas não mutáveis'])
        row=self.bd.um('SELECT * FROM memories WHERE id=?',(result['id'],))
        self.assertEqual(row['type'],'interpretacao');self.assertEqual(row['confidence'],.6)
        self.assertIn('Consultas não mutáveis',row['content']);self.assertEqual(self.bd.consultar('SELECT * FROM traits'),traits)
        with self.notes.administrative_scope(self.paths['lilith'],'lilith'):
            self.assertEqual(self.notes.models()['items'],[])

    def test_foreign_paths_symlinks_delivery_browser_and_shell_are_guarded(self):
        from core import entity_access
        from tools import filesystem,entrega,browser,terminal
        own=self.paths['hoshino'];foreign=self.paths['lilith']
        self.assertTrue(entity_access.permitted(own));self.assertFalse(entity_access.permitted(foreign))
        link=self.root/'link.db';link.symlink_to(foreign)
        self.assertFalse(filesystem._permitido(link));self.assertFalse(entrega._seguro(str(link))[0])
        self.assertIn('ACESSO_BLOQUEADO',browser.abrir(foreign.as_uri()))
        argv=terminal._comando_shell('true','sistema',False)
        self.assertIn('--unshare-pid',argv);self.assertIn(str(foreign.parents[2]),argv)
        with patch('core.entity_access.shutil.which',return_value=None):
            with self.assertRaises(PermissionError):terminal._comando_shell('true','sistema',False)

    def test_diary_logs_redact_content_but_retain_correlation(self):
        from core import diagnostics
        with patch.object(diagnostics,'emit') as emit:
            diagnostics.tool_start('diario',{'operacao':'escrever','texto':'SECRET NOTE','id':'entry-id'},'request-id')
            diagnostics.tool_end('diario','SECRET NOTE','request-id',True,1)
        self.assertNotIn('SECRET NOTE',str(emit.call_args_list));self.assertIn('request-id',str(emit.call_args_list))
        self.assertNotIn('SECRET NOTE',str(diagnostics._redact({'tool_name':'diario','content':'SECRET NOTE'})))

    def test_diary_content_is_not_reused_in_public_compaction_or_operational_state(self):
        from core import compaction, conversation, cognition
        secret='Esta nota privada não deve ser compactada como conversa.'
        message={'role':'tool','tool_name':'diario','content':secret}
        compacted=compaction.transcrever([message,{'role':'user','content':'Qual era a condição do arquivo?'}])
        self.assertNotIn(secret,compacted)
        self.assertIn('Qual era a condição do arquivo?',compacted)
        state=conversation.ConversationState(('localhub','usuario'),'localhub','usuario')
        state.registrar_saida('diario',secret)
        state.registrar_saida('workspace','Arquivo verificado.')
        self.assertNotIn(secret,state.texto_estado())
        self.assertIn('Arquivo verificado.',state.texto_estado())
        receipt={'tool':'diario','ok':True,'status':'success','output':secret,'verified':True,
                 'requires_verification':False}
        frame=cognition.criar_frame('Consultar meu diário')
        cognition.registrar_ferramenta(frame,'diario',receipt)
        self.assertNotIn(secret,str(frame.resultados_ferramentas))
        self.assertTrue(frame.resultados_ferramentas[0]['verified'])
        self.assertEqual(receipt['output'],secret)  # the current owner still receives the real entry

    def test_diary_task_receipt_preserves_outcome_without_copying_private_content(self):
        from core import task_state
        with patch.object(task_state,'_SCHEMA_DONE',False):
            task_state._schema()
            key=('localhub','usuario');wire_key=task_state.chave_texto(key)
            self.bd.executar("INSERT INTO conversation_tasks(id,chave,objetivo,status,created_at,updated_at) VALUES('private-task',?,'Consultar diário','active',?,?)",
                (wire_key,self.bd.agora(),self.bd.agora()),strict=True)
            self.bd.executar("INSERT INTO conversation_task_steps(id,task_id,ordem,texto,ferramenta,ferramentas,status,ferramentas_executadas) VALUES('private-step','private-task',0,'Consultar diário','diario',?,'pending','[]')",
                (json.dumps([{'id':'private-op','ferramenta':'diario'}]),),strict=True)
            secret='Nota reservada somente ao diário.'
            receipt={'tool':'diario','status':'success','output':secret,'verified':True,'requires_verification':False}
            task_state.registrar_ferramenta(key,'diario','success',secret,operacao_id='private-op',recibo=receipt)
            rows=self.bd.consultar('SELECT * FROM conversation_task_steps')
            self.assertNotIn(secret,str(rows))
            self.assertNotIn(secret,str(self.bd.consultar('SELECT * FROM conversation_tasks')))
            evidence=json.loads(rows[0]['ferramentas'])[0]['evidencia']
            self.assertTrue(evidence['verified']);self.assertEqual(rows[0]['status'],'done')
            self.assertEqual(receipt['output'],secret)

    def test_diary_shared_receipt_and_raw_event_contain_no_private_content(self):
        from core import diagnostics,job_bus,dispatch
        from main import registrar_evento
        with patch.object(job_bus,'DB_PATH',self.root/'jobs.db'),patch.dict(dispatch.HANDLERS,
             {'diario':lambda a,c:json.dumps({'private':True,'items':[{'text':'SECRET NOTE'}]})}):
            out=dispatch._executar_bruto('diario',{'operacao':'ler'})
            self.assertIn('SECRET NOTE',out)  # the owner gets the actual entry
            self.assertNotIn('SECRET NOTE',str(job_bus.status()))
            self.assertTrue(job_bus.status()[0]['details']['private'])
            job_bus.annotate(job_bus.status()[0]['id'],'hoshino',result='SECRET NOTE')
            self.assertNotIn('SECRET NOTE',str(job_bus.status()))
        with patch.object(config,'EVENT_LOG_DIR',str(self.root/'events')):
            registrar_evento('ferramenta',{'nome':'diario','args':'SECRET NOTE'})
            self.assertNotIn('SECRET NOTE',''.join(p.read_text() for p in (self.root/'events').glob('*.jsonl')))
        self.assertNotIn('SECRET NOTE',str(diagnostics._redact({'tool':'diario','args':{'texto':'SECRET NOTE'},'error':'SECRET NOTE'})))

    def test_lesson_recall_follows_evidence_subject_after_restart_without_inventing_name(self):
        result=self.notes.learn_experience(['experience-1'],'Um recibo não provava o efeito',
            'Quando altero um arquivo','Verificar o conteúdo antes de afirmar sucesso',['Consultas não mutáveis'])
        row=self.bd.um('SELECT * FROM memories WHERE id=?',(result['id'],))
        self.assertNotIn('hash diferente',row['content'])
        with patch.object(saber,'DB_PATH',str(self.paths['hoshino'])),patch.object(saber.vetor,'buscar',return_value=[]):
            # New SQL connections, keyword only present in the source episode.
            self.assertIn(result['id'],saber.list_facts_about('hash diferente'))
            self.assertIn(result['id'],saber.como_funciona('hash diferente'))
            recalled=saber.recall('hash diferente',20,estruturado=True)
            self.assertIn(result['id'],{r['id'] for r in recalled})
            self.assertEqual(self.bd.um('SELECT type FROM memories WHERE id=?',(result['id'],))['type'],'interpretacao')

    def test_evidence_revalidation_rejects_changed_source_but_ignores_access_counter(self):
        original=self.notes.save_model('Verificação',self.graph,self.refs)
        ref=[dict(table='memories',id=original['id'])]
        first=self.notes.save_model('Revisão indireta',self.graph,ref)
        self.bd.executar('UPDATE memories SET access_count=99 WHERE id=?',(original['id'],),strict=True)
        self.assertEqual(first['id'],self.notes.save_model('Revisão indireta',self.graph,ref)['id'])
        stale=self.notes._evidence(self.refs)
        self.bd.executar("UPDATE episodes SET result='resultado alterado' WHERE id='experience-1'",strict=True)
        with patch.object(self.notes,'_evidence',return_value=stale):
            with self.assertRaises(ValueError):self.notes.save_model('Evidência obsoleta',self.graph,self.refs)
        self.assertFalse(self.bd.um("SELECT id FROM memories WHERE content LIKE 'Evidência obsoleta%'"))

    def test_actual_command_namespace_masks_foreign_bank_preserving_own_read(self):
        import subprocess
        from core import entity_access
        own=self.paths['hoshino'];foreign=self.paths['lilith']
        result=subprocess.run(entity_access.command(['/bin/sh','-c',
            'test -r "$1" && test ! -e "$2"','fixture',str(own),str(foreign)]),capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_existing_reflection_pipeline_handles_private_note_and_revisable_lesson(self):
        lesson={'episodios':['experience-1'],'interpretacao':'O recibo não bastava','condicao':'Depois de alterar arquivo',
                'licao':'Conferir o conteúdo','excecoes':['Consulta sem alteração']}
        text='- Preciso comparar o resultado com a intenção original.\nDIARIO: Não quero expor esta dúvida.\nLICAO_JSON: '+json.dumps(lesson)
        with patch.object(saber,'DB_PATH',str(self.paths['hoshino'])),patch.object(saber.vetor,'salvar',return_value=False):
            public=reflection.aplicar(text,[{'id':'experience-1'}])
        self.assertEqual(public,['Preciso comparar o resultado com a intenção original.'])
        self.assertEqual(len(self.notes.models()['items']),1)
        self.assertEqual(self.notes.diary_read()['items'][0]['text'],'Não quero expor esta dúvida.')
        self.assertNotIn('Não quero expor',reflection.bloco_para_prompt())
        with self.notes.administrative_scope(self.paths['lilith'],'lilith'):
            self.assertEqual(self.notes.diary_read()['items'],[]);self.assertEqual(self.notes.models()['items'],[])


class Integridade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            for t in ('memories', 'properties', 'reflections', 'procedures'):
                c.execute(f'DELETE FROM {t}')

    def recuperar(self, termo):
        return saber.recall(termo, 20, estruturado=True)

    def test_zero_e_none(self):
        saber.remember('Teste confiança zero sobre Saturno', confianca=0.0)
        saber.remember('Teste confiança ausente sobre Saturno', confianca=None)
        registros = self.recuperar('Saturno confiança')
        self.assertEqual({r['confianca'] for r in registros}, {0.0, 0.7})
        saber.registrar_propriedade('Saturno', 'temperatura', '0', confianca=0)
        self.assertIn('confiança=0.0', saber.propriedades_de('Saturno'))
        self.assertEqual(next(r for r in self.recuperar('Saturno temperatura') if r['tipo']=='propriedade')['confianca'], 0)
        saber.registrar_propriedade('Plutão', 'temperatura', '0', confianca=None)
        self.assertEqual(self.recuperar('Plutão temperatura')[0]['confianca'], .8)

    def test_categorias_proveniencia(self):
        for tipo in ('observacao', 'fato', 'interpretacao', 'hipotese', 'reflexao', 'inferencia'):
            saber.remember(f'Saturno conhecimento categoria {tipo}', tipo=tipo, fonte='teste_verificado',
                           confianca=.25, evidencias=['ep-teste'])
        rs = self.recuperar('Saturno conhecimento')
        self.assertEqual({r['tipo'] for r in rs}, {'observacao','fato','interpretacao','hipotese','reflexao','inferencia'})
        for r in rs:
            self.assertEqual(r['fonte'], 'teste_verificado')
            self.assertEqual(r['confianca'], .25)
            self.assertEqual(r['evidencias'], ['ep-teste'])
            self.assertTrue(r['created_at'])
        for consulta in (saber.recall('Saturno conhecimento'), [saber.list_facts_about('Saturno')], [saber.como_funciona('Saturno')], [night_reflection.material_do_dia()]):
            texto = '\n'.join(consulta)
            self.assertIn('[hipotese]', texto)
            self.assertIn('teste_verificado', texto)
            self.assertIn('ep-teste', texto)

    def test_reflexao_nao_fato(self):
        reflection.aplicar('- Talvez Saturno represente minha curiosidade recorrente.', [{'id':'ep-origem'}])
        r = self.recuperar('Saturno curiosidade')[0]
        self.assertEqual(r['tipo'], 'reflexao')
        self.assertEqual(r['evidencias'], ['ep-origem'])
        self.assertNotIn('[fato]', reflection.bloco_para_prompt())

    def test_legado_sem_migracao_cega(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute("INSERT INTO memories(id,type,content,created_at,source,confidence,links,status) VALUES ('legado','fato','Saturno conclusão antiga','2026-10-01','reflexao',0,'ep-antigo','active')")
            c.execute("INSERT INTO memories(id,type,content,created_at,status) VALUES ('sem-fonte','fato','Saturno dado antigo','2026-10-01','active')")
        rs = {r['id']:r for r in self.recuperar('Saturno')}
        self.assertEqual(rs['legado']['tipo'], 'reflexao')
        self.assertEqual(rs['legado']['tipo_armazenado'], 'fato')
        self.assertEqual(rs['legado']['confianca'], 0)
        self.assertEqual(rs['legado']['evidencias'], 'ep-antigo')
        self.assertEqual(rs['sem-fonte']['tipo'], 'fato')
        self.assertEqual(rs['sem-fonte']['confianca'], .5)
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            self.assertEqual(c.execute("SELECT type,confidence,links FROM memories WHERE id='legado'").fetchone(), ('fato', 0, 'ep-antigo'))

    def test_extrator_preserva_hipotese_zero(self):
        scribe.aplicar_extracao(json.dumps([dict(tipo='hipótese', conteudo='Saturno talvez indique preferência', confianca=0),
                                          dict(tipo='fato', conteudo='Saturno conclusão apenas do modelo', confianca=None)]))
        rs = self.recuperar('Saturno')
        self.assertEqual({r['tipo'] for r in rs}, {'hipotese','interpretacao'})
        self.assertEqual(next(r['confianca'] for r in rs if r['tipo']=='hipotese'), 0)

    def test_categorias_nao_se_substituem(self):
        saber.remember('Saturno é uma conclusão antiga', entidades=['Saturno'], tipo='fato', chave='origem', fonte='reflexao')
        saber.remember('Saturno é uma conclusão antiga', entidades=['Saturno'], tipo='fato', chave='origem', fonte='observacao_confirmada')
        self.assertEqual(len(self.recuperar('Saturno conclusão')), 2)

    def test_invalidos_nao_viram_certeza(self):
        for c in (float('nan'), float('inf'), 'não numérico'):
            with self.assertRaises((ValueError, TypeError)):
                saber.remember('Saturno confiança inválida', confianca=c)

    def test_procedimento_zero_nao_ganha_default_no_ranking(self):
        saber.registrar_procedimento('Saturno', 'aprender Saturno', ['Ler Saturno'], confianca=0)
        # Sem similaridade, confiança 0 não pode passar do corte de ranking .12.
        with patch.object(saber.vetor, 'buscar', return_value=[]):
            self.assertTrue(saber.consultar_procedimento('assunto_inexistente').startswith('Nada registrado'))
        saber.registrar_procedimento('Plutão', 'aprender Plutão', ['Ler Plutão'], confianca=None)
        self.assertIn('confiança 0.7', saber.consultar_procedimento('Plutão'))

    def test_contexto_nao_chama_hipotese_de_fato(self):
        from core import prompting
        texto = prompting.bloco_contexto(conhecimentos=['[hipotese] Saturno hipótese (fonte=teste; confiança=0.0)'])
        self.assertIn('não são fatos confirmados', texto)
        self.assertIn('[hipotese]', texto)


class ReflectionClockTests(unittest.TestCase):
    def setUp(self):
        from core import bd
        self.bd = bd
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for obj, name, value in ((config, 'DB_PATH', str(Path(temp.name)/'mind.db')),
                                 (init_db, 'DB_PATH', str(Path(temp.name)/'mind.db')),
                                 (config, 'LOCAL_TIMEZONE', 'America/Sao_Paulo')):
            patcher = patch.object(obj, name, value); patcher.start(); self.addCleanup(patcher.stop)
        init_db.init_database(verbose=False)
        self.now = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)
        clock = patch('core.history.local_now', return_value=self.now)
        clock.start(); self.addCleanup(clock.stop)

    def reflect(self, rid, timestamp):
        self.bd.executar("INSERT INTO reflections(id,created_at,conteudo,status) VALUES(?,?,?,'active')",
                         (rid, timestamp, 'Conclusão '+rid), strict=True)

    def episode(self, eid, timestamp):
        self.bd.executar("INSERT INTO episodes(id,created_at,what_happened,status) VALUES(?,?,?,'active')",
                         (eid, timestamp, 'Experiência '+eid), strict=True)

    def test_latest_reflection_and_material_use_instants_not_iso_text(self):
        self.reflect('latest-local', '2026-10-09T11:30:00')
        self.reflect('older-utc', '2026-10-09T14:25:00Z')
        self.episode('before', '2026-10-09T14:26:00Z')
        self.episode('after', '2026-10-09T11:40:00')
        self.assertEqual(reflection.episodios_desde_ultima(), 1)
        self.assertEqual([r['id'] for r in reflection.material()], ['after'])
        with patch('core.history.local_now', return_value=self.now):
            self.assertEqual(reflection.minutos_desde_ultima(), 30.)

    def test_unknown_or_future_reflection_time_does_not_enable_automatic_reflection(self):
        for timestamp in ('inválido', '2026-10-10T15:00:00Z'):
            self.bd.executar('DELETE FROM reflections', strict=True)
            self.reflect('known-older', '2026-10-09T11:00:00')
            self.reflect('bad', timestamp)
            with self.subTest(timestamp=timestamp), patch('core.history.local_now', return_value=self.now):
                self.assertEqual(reflection.minutos_desde_ultima(), 0.)

    def test_no_reflection_has_no_cooldown_but_missing_episode_time_is_not_new_evidence(self):
        self.episode('valid', '2026-10-09T11:40:00')
        self.episode('unknown', 'inválido')
        self.assertEqual(reflection.minutos_desde_ultima(), 1e6)
        self.assertEqual(reflection.episodios_desde_ultima(), 1)
        self.assertEqual([r['id'] for r in reflection.material()], ['valid'])

    def test_reflection_read_does_not_rewrite_timestamp_or_evidence(self):
        self.reflect('one', '2026-10-09T11:30:00')
        self.bd.executar("UPDATE reflections SET evidencias='source-original' WHERE id='one'", strict=True)
        self.episode('after', '2026-10-09T14:40:00Z')
        with self.bd.conexao() as db:
            before = list(db.iterdump())
        reflection.material(); reflection.ultimas(); reflection.bloco_para_prompt()
        with self.bd.conexao() as db:
            self.assertEqual(list(db.iterdump()), before)

    def test_empty_reflection_evidence_count_is_zero_and_future_episode_is_not_new(self):
        self.assertEqual(reflection.episodios_desde_ultima(), 0)
        self.episode('future', '2026-10-10T15:00:00Z')
        self.assertEqual(reflection.episodios_desde_ultima(), 0)
        self.assertEqual(reflection.material(), [])

    def test_new_reflection_is_utc_while_legacy_timestamp_and_evidence_are_preserved(self):
        self.reflect('legacy', '2026-10-09T11:30:00')
        before = self.bd.um("SELECT * FROM reflections WHERE id='legacy'")
        text = 'Preciso verificar a origem da observação antes de concluir algo.'
        self.assertEqual(reflection.aplicar('- '+text, [{'id': 'ep-fonte'}]), [text])
        new = self.bd.um('SELECT * FROM reflections WHERE conteudo=?', (text,))
        self.assertTrue(new['created_at'].endswith('+00:00'))
        self.assertEqual(new['tipo'], 'reflexao')
        self.assertEqual(new['evidencias'], 'ep-fonte')
        self.assertEqual(self.bd.um("SELECT * FROM reflections WHERE id='legacy'"), before)


if __name__ == '__main__':
    unittest.main()
