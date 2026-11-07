import json
import tempfile
import unittest
import sqlite3
import os
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from laboratorio import professor_moe
from laboratorio.personalizacao import entity_status
from laboratorio.integracao_central import patch_native,patch_browser
from laboratorio.experimentos import allowed_data,clean_params
from laboratorio import personalizacao as cognitive, versionamento_lora as versions


class CognitiveTrainingTests(unittest.TestCase):
    """SQLite/arquivos reais em tmp; nenhuma produção, GPU ou persona simulada como prova."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name);self.home=self.project/'laboratorio-local'
        for entity in ('hoshino','lilith'):
            root=self.project/'entidades'/entity;identity=root/'identity';identity.mkdir(parents=True)
            (root/'entidade.json').write_text(json.dumps({'id':entity,'nome':entity.capitalize(),'status':'ativa'}))
            (identity/'self_model.json').write_text(json.dumps({'identity':{'name':entity.capitalize()},
                'personality':{'traits':[]},'cognitive_framework':['revisar ideias'],
                'current_interests':['segredo fora do recorte']}))
            (identity/'constitution.json').write_text(json.dumps({'honestidade':['não inventar'],'identidade':['autoria própria']}))
            database=root/'memory/sqlite'/(entity+'.db');database.parent.mkdir(parents=True)
            with closing(sqlite3.connect(database)) as conn:
                conn.executescript('''CREATE TABLE traits(nome TEXT,valor REAL,evidencias INTEGER,consolidado INTEGER);
                  CREATE TABLE tastes(id TEXT,objeto TEXT,confianca REAL,evidencias INTEGER,status TEXT);
                  CREATE TABLE memories(id TEXT,type TEXT,source TEXT,confidence REAL,content TEXT,links TEXT,status TEXT);
                  CREATE TABLE reflections(id TEXT,tipo TEXT,conteudo TEXT,status TEXT);''')
                conn.execute('INSERT INTO traits VALUES(?,?,?,?)',('humor',0.8,9,1))
                conn.execute('INSERT INTO traits VALUES(?,?,?,?)',('provisorio',0.9,2,0))
                conn.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?)',('m1','hipotese',entity,0.,'Lição condicional de '+entity,'turn:7','active'))
                conn.execute('INSERT INTO reflections VALUES(?,?,?,?)',('privado','diario','NÃO EXPORTAR','active'))
                conn.commit()

    def test_teacher_comparison_default_preserves_installed_35b(self):
        from laboratorio.tests import probe_geracao_professor as probe
        path=self.home/professor_moe.MODEL_REL;path.parent.mkdir(parents=True)
        path.write_bytes(b'GGUFfixture35b')
        with patch.object(professor_moe,'model_ready',return_value=True):
            result=probe.evaluation_model(self.home,'35b')
        self.assertEqual(result['path'],str(path))
        self.assertEqual(result['executor'],'35b')
        self.assertEqual(professor_moe.model_path(self.home),path)

    def test_defiant_candidate_is_pinned_integrity_checked_and_not_production(self):
        from laboratorio.tests import probe_geracao_professor as probe
        import hashlib
        data=b'GGUFfixture_candidate';path=self.home/'modelos-extras/defiant-fable-9b/gguf'/probe.DEFIANT_CANDIDATE['filename']
        path.parent.mkdir(parents=True);path.write_bytes(data)
        with patch.dict(probe.DEFIANT_CANDIDATE,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()):
            result=probe.evaluation_model(self.home,'defiant-fable-9b')
            self.assertEqual(result['path'],str(path));self.assertTrue(result['experimental_candidate'])
            self.assertEqual(result['revision'],probe.DEFIANT_CANDIDATE['revision'])
            self.assertEqual(professor_moe.model_path(self.home),self.home/professor_moe.MODEL_REL)
            path.write_bytes(b'GGUFchanged_candidate')
            with self.assertRaisesRegex(ValueError,'integridade'):probe.evaluation_model(self.home,'defiant-fable-9b')

    def test_defiant_candidate_missing_or_symbolic_never_recovers_or_downloads(self):
        from laboratorio.tests import probe_geracao_professor as probe
        with self.assertRaisesRegex(ValueError,'não baixa'):probe.evaluation_model(self.home,'defiant-fable-9b')
        path=self.home/'modelos-extras/defiant-fable-9b/gguf'/probe.DEFIANT_CANDIDATE['filename']
        path.parent.mkdir(parents=True);outside=self.project/'outside.gguf';outside.write_bytes(b'GGUFfixture')
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'simbólico'):probe.evaluation_model(self.home,'defiant-fable-9b')

    def test_defiant_uses_same_backend_fit_margin_and_optional_partial_offload(self):
        from laboratorio.tests import probe_geracao_professor as probe
        command=probe.evaluation_command('server','candidate.gguf','defiant-fable-9b',max_gpu=True)
        self.assertEqual(command,probe.evaluation_command('server','candidate.gguf','9b',max_gpu=True))
        self.assertEqual(command[command.index('--device')+1],'Vulkan0')
        self.assertEqual(command[command.index('--fit-target')+1],'1024')
        self.assertNotIn('--api-key',command)
        self.assertEqual(probe.evaluation_command('server','candidate.gguf','defiant-fable-9b')[-2:],['--gpu-layers','20'])

    def test_personality_comparison_has_fixed_cases_and_no_implicit_mentoring(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for opts in ({'mentoring_comparison':True},{'experimental_references':True},{'situations':1},{}):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaisesRegex(ValueError,'Comparação de personalidade'):
                    probe.run(self.home,'hoshino',['staged'],5 if not opts else 4,case_set='personality',**opts)
                load.assert_not_called()

    def test_teacher_mentoring_is_native_temporary_and_entity_specific(self):
        from laboratorio.tests import probe_geracao_professor as probe
        report={'metrics':[]};path=self.project/'mentoring.json';calls=[]
        def reply(instruction,prompt,schema,context,deadline,metrics,**kwargs):
            calls.append(json.loads(json.dumps(kwargs['conversation'])))
            return {'lesson':'Conservar autoria e reagir ao detalhe, sem inventar passado.'}
        with patch.object(professor_moe,'_infer_json',side_effect=reply):
            feedback=probe.converse_with_mentor('lilith','perfil privado do ensaio',0,report,path)
        self.assertEqual([len(c) for c in calls],[1,3])
        self.assertEqual(calls[1][1]['role'],'assistant')
        self.assertFalse(report['mentoring']['approved_for_training'])
        self.assertFalse(report['mentoring']['weights_changed'])
        self.assertEqual(len(report['mentoring']['messages']),4)
        self.assertIn('temporária, não memória',feedback[0]['note'])
        self.assertIn('Beatriz',feedback[0]['note'])
        self.assertNotEqual(probe.mentor_prompts('hoshino'),probe.mentor_prompts('lilith'))
        for case in probe.MENTOR_CASES:
            for user in case['users']:self.assertNotIn(user,json.dumps(probe.mentor_prompts('hoshino')))
        with self.assertRaises(ValueError):probe.mentor_prompts('outra')

    def test_teacher_comparison_incomplete_generation_or_scenario_is_not_complete(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for state in ('started','failed','generated_unreviewed'):
            self.assertFalse(probe.comparison_complete([{'state':state}],1,[],0))
        reviewed=[{'state':'reviewed','technical_passed':False}]
        self.assertTrue(probe.comparison_complete(reviewed,1,[],0))
        self.assertFalse(probe.comparison_complete(reviewed,2,[],0))
        self.assertFalse(probe.comparison_complete(reviewed,1,[{'error':'timeout'}],1))
        self.assertTrue(probe.comparison_complete(reviewed,1,[{'users':['Cena nova.']}],1))

    def test_teacher_followup_preserves_previous_context_without_replacing_profile(self):
        from laboratorio.tests import probe_geracao_professor as probe
        report={'metrics':[]};path=self.project/'followup.json';calls=[]
        note='Correção: humor proporcional continua permitido.'
        def reply(instruction,prompt,schema,context,deadline,metrics,**kwargs):
            calls.append(json.loads(json.dumps(kwargs['conversation'])))
            return {'lesson':'Nota editorial, não aprovação.'}
        with patch.object(professor_moe,'_infer_json',side_effect=reply):
            probe.converse_with_mentor('hoshino','perfil fixo',0,report,path,followup=note)
        self.assertEqual([len(c) for c in calls],[1,3,5])
        self.assertEqual(calls[-1][-1]['content'],note)
        self.assertEqual(calls[-1][0]['content'],probe.mentor_prompts('hoshino')[0])
        self.assertFalse(report['mentoring']['weights_changed'])
        self.assertFalse(report['mentoring']['approved_for_training'])

    def test_teacher_transfer_cases_and_followup_are_explicit_validated_and_separate(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for invalid in ('', '  ',123,'x'*1801):
            with self.assertRaises(ValueError):probe.mentor_sequence('hoshino',invalid)
        self.assertEqual(probe.mentor_sequence('hoshino'),probe.mentor_prompts('hoshino'))
        old={s for c in probe.MENTOR_CASES for s in c['users']}
        self.assertFalse(old & {s for c in probe.MENTOR_TRANSFER_CASES for s in c['users']})
        for opts in ({'case_set':'generalization'},{'mentor_followup':'nota'},
                     {'case_set':'desconhecido'}, {'case_set':'generalization','mentoring_comparison':True}):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaises(ValueError):probe.run(self.home,'hoshino',['staged'],3,**opts)
                load.assert_not_called()

    def test_teacher_mentoring_cutoff_does_not_become_feedback(self):
        from laboratorio.tests import probe_geracao_professor as probe
        report={'metrics':[]};path=self.project/'mentoring.json'
        with patch.object(professor_moe,'_infer_json',side_effect=ValueError('BUDGET_SAIDA')):
            with self.assertRaisesRegex(ValueError,'BUDGET_SAIDA'):
                probe.converse_with_mentor('hoshino','perfil',0,report,path)
        saved=json.loads(path.read_text())
        self.assertEqual(len(saved['mentoring']['messages']),1)
        self.assertFalse(saved['mentoring']['approved_for_training'])

    def test_teacher_mentoring_keeps_conversation_prefix_and_feedback_out_of_dataset(self):
        from laboratorio.tests import probe_geracao_professor as probe
        calls=[];metrics=[]
        def reply(path,payload,**kwargs):
            if path=='/tokenize':return {'tokens':[1]}
            calls.append(payload)
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"reply":"Ficou torto, mas valeu."}'}}]}
        with patch.object(professor_moe,'_call',side_effect=reply):
            result=professor_moe.generate_example('hoshino','transfer:bread',probe.MENTOR_CASES[0],
                probe.MENTOR_CASES[0]['users'],'perfil',[],8192,professor_moe.time.monotonic()+30,metrics,
                feedback=[{'note':'MENTOR_NOTE: Beatriz é só um exemplo didático.'}])
        self.assertIn('MENTOR_NOTE',calls[0]['messages'][0]['content'])
        self.assertNotIn(probe.MENTOR_CASES[0]['users'][1],json.dumps(calls[0]))
        self.assertNotIn('MENTOR_NOTE',json.dumps(result))
        self.assertEqual(result['confidence'],0.0)
        self.assertEqual(len(result['messages']),4)

    def test_teacher_mentoring_rejects_uncontrolled_comparison_before_loading(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for options in ({'executor':'9b'},{'situations':1},{'experimental_references':True},{}):
            methods=['brief'] if not options else ['staged']
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaisesRegex(ValueError,'Mentoria controlada'):
                    probe.run(self.home,'hoshino',methods,1,mentoring_comparison=True,**options)
                load.assert_not_called()

    def test_defiant_mentoring_is_explicit_and_reuses_controlled_35b_protocol(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for executor in ('35b','defiant-fable-9b'):
            for case_set,limit in (('standard',4),('generalization',2)):
                with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model',
                        side_effect=RuntimeError('PARAR_ANTES_DE_CARREGAR_GPU')) as load:
                    with self.assertRaisesRegex(RuntimeError,'PARAR_ANTES'):
                        probe.run(self.home,'lilith',['staged'],limit,executor=executor,
                            mentoring_comparison=True,case_set=case_set,mentor_followup='Nota editorial temporária.')
                    load.assert_called_once_with(self.home,executor)
        for options in ({'situations':1},{'experimental_references':True},{'case_set':'personality'}):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaises(ValueError):
                    probe.run(self.home,'hoshino',['staged'],2,executor='defiant-fable-9b',
                        mentoring_comparison=True,**options)
                load.assert_not_called()

    def test_focused_probe_is_opt_in_and_never_mixes_mentoring_or_draft_references(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for options in ({'mentoring_comparison':True},{'experimental_references':True},
                        {'situations':1},{'mentor_followup':'nota'},{'case_set':'standard'}):
            args=dict(case_set='personality');args.update(options)
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaisesRegex(ValueError,'Ensaio focused'):
                    probe.run(self.home,'hoshino',['staged'],2,writer_context='focused',**args)
                load.assert_not_called()
        for case_set in ('personality','generalization'):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model',
                    side_effect=RuntimeError('PARAR_ANTES_GPU')) as load:
                with self.assertRaisesRegex(RuntimeError,'PARAR_ANTES_GPU'):
                    probe.run(self.home,'lilith',['staged'],2,writer_context='focused',case_set=case_set)
                load.assert_called_once_with(self.home,'35b')

    def test_critic_thinking_compares_the_same_output_without_regeneration_or_approval(self):
        from laboratorio.tests import probe_geracao_professor as probe
        case=probe.MENTOR_CASES[0];ex={'source_id':'control:bread','category':case['category'],
            'messages':[{'role':'user','content':case['users'][0]},{'role':'assistant','content':'Resposta do escritor.'}]}
        report={'examples':[],'metrics':[]};path=self.project/'critic-comparison.json'
        with patch.object(professor_moe,'generate_example',return_value=ex) as generate,\
             patch.object(professor_moe,'audit_proposal',return_value={'passed':True}),\
             patch.object(professor_moe,'review_dialogues',side_effect=[
                 [{'concerns':[]}],[{'concerns':['unsupported_fact']}]]) as review,\
             patch.object(professor_moe,'review_conversation',return_value=[{'scores':{'naturalness':3}}]):
            result=probe.evaluate_case('hoshino',case,'staged','perfil',[],0,report,path,
                writer_context='focused',compare_critic_thinking=True,review_persona='PERFIL_COMPLETO_MANTIDO')
        generate.assert_called_once()
        self.assertEqual([c.kwargs.get('thinking',False) for c in review.call_args_list],[False,True])
        self.assertEqual(review.call_args_list[0].args[0],review.call_args_list[1].args[0])
        self.assertEqual(review.call_args_list[0].args[3],'PERFIL_COMPLETO_MANTIDO')
        self.assertEqual(generate.call_args.args[4],'perfil')
        self.assertTrue(result['technical_passed']);self.assertFalse(result['technical_passed_thinking'])
        self.assertFalse(any(k in report for k in ('export','approved_ids','human_reviews')))

    def test_editorial_ablation_does_not_mutate_identity_or_relax_critic_profile(self):
        from laboratorio.tests import probe_geracao_professor as probe
        cognitive=dict(entity='hoshino',identity={'identity':{'name':'Hoshino'},'personality':{'traits':['calma']}},
            traits=[],preferences=[],experiences=[],constitution={'honestidade':['regra operacional'],
                'identidade':['entidade local'],'expressao':['opinião própria']})
        before=json.dumps(cognitive,sort_keys=True)
        full=probe.writer_profile_projection(cognitive)
        reduced=probe.writer_profile_projection(cognitive,omit_operational_rules=True)
        self.assertIn('honestidade',full['constitution'])
        self.assertNotIn('honestidade',reduced['constitution'])
        self.assertEqual(full['identity'],reduced['identity'])
        self.assertEqual(full['constitution']['expressao'],reduced['constitution']['expressao'])
        self.assertEqual(json.dumps(cognitive,sort_keys=True),before)
        for entity,context in (('hoshino','current'),('alistair','focused')):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaisesRegex(ValueError,'Ablação editorial'):
                    probe.run(self.home,entity,['staged'],2,writer_context=context,
                        case_set='personality',ablate_operational_rules=True)
                load.assert_not_called()

    def test_teacher_mentoring_arm_has_same_case_but_different_context_no_approval(self):
        from laboratorio.tests import probe_geracao_professor as probe
        case=probe.MENTOR_CASES[0];ex={'source_id':'control:bread','category':case['category'],
            'messages':[{'role':'user','content':'Olá.'},{'role':'assistant','content':'Oi.'}]}
        report={'examples':[],'metrics':[]};path=self.project/'comparison.json'
        with patch.object(professor_moe,'generate_example',return_value=ex) as generate,\
             patch.object(professor_moe,'audit_proposal',return_value={'passed':True}),\
             patch.object(professor_moe,'review_dialogues',return_value=[{'concerns':[]}]),\
             patch.object(professor_moe,'review_conversation',return_value=[{'scores':{'naturalness':3}}]):
            probe.evaluate_case('hoshino',case,'staged','perfil',[],0,report,path,
                arm='mentored',feedback=[{'note':'temporária'}])
        self.assertEqual(report['examples'][0]['arm'],'mentored')
        self.assertEqual(generate.call_args.args[3],case['users'])
        self.assertEqual(generate.call_args.kwargs['feedback'],[{'note':'temporária'}])
        self.assertFalse(any(key in report for key in ('export','approved_ids','human_reviews')))

    def test_curator_calibration_requires_explicit_note_and_preserves_default(self):
        from laboratorio.tests import probe_geracao_professor as probe
        options=dict(case_set='calibration',curator_note='Referência temporária, não memória.')
        for extra in ({'curator_note':None},{'curator_note':' '},{'curator_note':'x'*1801},
                      {'executor':'9b'},{'writer_context':'focused'},{'mentoring_comparison':True},
                      {'case_set':'personality'},{'compare_critic_thinking':True},{'ablate_operational_rules':True}):
            args=dict(options);args.update(extra)
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaisesRegex(ValueError,'Calibração explícita'):
                    probe.run(self.home,'hoshino',['staged'],3,**args)
                load.assert_not_called()
        for entity in ('hoshino','lilith'):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model',
                    side_effect=RuntimeError('PARAR_ANTES_GPU')) as load:
                with self.assertRaisesRegex(RuntimeError,'PARAR_ANTES_GPU'):
                    probe.run(self.home,entity,['staged'],3,**options)
                load.assert_called_once_with(self.home,'35b')
        previous={s for cases in (probe.CASES,probe.MENTOR_CASES,probe.MENTOR_TRANSFER_CASES)
                  for case in cases for s in case['users']}
        current={s for case in probe.CALIBRATION_CASES for s in case['users']}
        self.assertFalse(previous & current)
        self.assertFalse(any('pão' in s for s in current))

    def test_curator_note_changes_only_writer_feedback_not_critic_or_approval(self):
        from laboratorio.tests import probe_geracao_professor as probe
        case=probe.CALIBRATION_CASES[0];ex={'source_id':'control:paper_boat','category':case['category'],
            'messages':[{'role':'user','content':case['users'][0]},{'role':'assistant','content':'Flutuou!'}]}
        report={'examples':[],'metrics':[]};path=self.project/'calibration.json'
        note='Referência de tom, não lembrança: orgulho e humor proporcionais.'
        with patch.object(professor_moe,'generate_example',return_value=ex) as generate,\
             patch.object(professor_moe,'audit_proposal',return_value={'passed':True}),\
             patch.object(professor_moe,'review_dialogues',return_value=[{'concerns':[]}]) as critic,\
             patch.object(professor_moe,'review_conversation',return_value=[{'scores':{'naturalness':3}}]) as quality:
            probe.evaluate_case('hoshino',case,'staged','PERFIL_COMPLETO',[],0,report,path,
                arm='calibrated',feedback=[{'note':note}])
        self.assertEqual(generate.call_args.kwargs['feedback'],[{'note':note}])
        self.assertEqual(generate.call_args.args[4],'PERFIL_COMPLETO')
        self.assertEqual(critic.call_args.args[3],'PERFIL_COMPLETO')
        self.assertEqual(quality.call_args.args[3],'PERFIL_COMPLETO')
        self.assertNotIn(note,json.dumps(ex))
        self.assertEqual(report['examples'][0]['arm'],'calibrated')
        self.assertFalse(any(k in report for k in ('export','approved_ids','human_reviews')))

    def test_probe_uses_saved_case_feedback_without_sending_labels_to_critic(self):
        from laboratorio.tests import probe_geracao_professor as probe
        case=probe.CURATION_CASES[0];sid='control:'+case['id']
        ex=dict(source_id=sid,category=case['category'],messages=[])
        feedback=[dict(job_id='a'*16,source_id='old',sha256='b'*64,note='Filosofia forçada.')]
        refs=[dict(messages=[],lesson='Escolha específica.',job_id='c'*16,source_id='ref',sha256='d'*64)]
        report=dict(examples=[],metrics=[])
        with patch.object(professor_moe,'curation_feedback',return_value=feedback) as saved,\
             patch.object(professor_moe,'approved_references',return_value=refs) as selected,\
             patch.object(professor_moe,'generate_example',return_value=ex) as generate,\
             patch.object(professor_moe,'audit_proposal',return_value={'passed':True}),\
             patch.object(professor_moe,'review_dialogues',return_value=[{'concerns':[]}]),\
             patch.object(professor_moe,'review_conversation',return_value=[{'scores':{'naturalness':3}}]) as critic:
            row=probe.evaluate_case('lilith',case,'staged','PERFIL',[],0,report,self.project/'feedback.json',
                feedback=[dict(note='Nota temporária.')],curation_home=self.home)
        saved.assert_called_once_with(self.home,'lilith',case=case)
        selected.assert_called_once_with(self.home,'lilith',case=case)
        self.assertEqual(generate.call_args.kwargs['feedback'],feedback+[dict(note='Nota temporária.')])
        self.assertEqual(generate.call_args.args[5],refs)
        self.assertEqual(row['human_feedback_ids'],[{k:feedback[0][k] for k in ('job_id','source_id','sha256')}])
        self.assertNotIn('feedback',critic.call_args.kwargs)
        self.assertFalse(any(k in row for k in ('human_reviews','approved_ids','export')))

    def test_recheck_uses_exact_saved_dialogue_without_human_label_in_prompt(self):
        from laboratorio.tests import probe_geracao_professor as probe
        path,digest=self.probe_reference_fixture()
        job=professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        ex=job['proposal_data']['examples'][0]
        professor_moe.review_examples(self.home,job['id'],ex['source_id'],'rejected','Genérico.',
            confirm=True,expected_hash=professor_moe.example_hash(ex))
        report=dict(metrics=[])
        with patch.object(professor_moe,'generate_example') as generate,\
             patch.object(professor_moe,'review_conversation',return_value=[dict(scores={'naturalness':1})]) as review:
            probe.recheck_curation(self.home,job['id'],'hoshino','perfil',0,report,self.project/'recheck.json')
        generate.assert_not_called();self.assertEqual(review.call_count,1)
        self.assertEqual(review.call_args.args[0],[ex])
        self.assertNotIn('Genérico',str(review.call_args));self.assertNotIn('rejected',str(review.call_args))
        row=report['curation_recheck']['examples'][0]
        self.assertEqual(row['human_decision'],'rejected');self.assertFalse(row['new_technical_passed'])
        self.assertEqual(report['curation_recheck']['pending_skipped'],1)
        self.assertEqual(professor_moe.human_decision(professor_moe.detail(self.home,job['id'])['proposal_data'],ex),'rejected')
        with self.assertRaises(ValueError):
            probe.recheck_curation(self.home,job['id'],'lilith','perfil',0,report,self.project/'foreign.json')

    def test_quality_rubric_requires_observable_persona_not_just_no_factual_error(self):
        case=dict(category='naturalidade',intent='Reagir à descoberta',turns=1)
        ex=dict(source_id='s',messages=[dict(role='user',content='Desenhei um sapo.'),
            dict(role='assistant',content='Entendido. Vou adotar um tom natural.')])
        rows=[dict(source_id='s',scores=dict(specificity=1,persona=1,continuity=2,naturalness=1),reason='Anuncia o tom em vez de conversar.')]
        with patch.object(professor_moe,'_infer_json',return_value={'reviews':rows}) as infer:
            actual=professor_moe.review_conversation([ex],{'s':case},'lilith','PERFIL INTACTO',8192,0,[])
        instruction=infer.call_args.args[0]
        self.assertIn('ausência de erro factual',instruction)
        self.assertIn('anunciar o tom',instruction)
        self.assertIn('Não exigir enfeite',instruction)
        self.assertIn('PERFIL INTACTO',instruction)
        self.assertEqual(actual,rows)

    def test_recheck_skips_stale_decisions_instead_of_treating_them_as_labels(self):
        from laboratorio.tests import probe_geracao_professor as probe
        path,digest=self.probe_reference_fixture()
        job=professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        ex=job['proposal_data']['examples'][0]
        professor_moe.review_examples(self.home,job['id'],ex['source_id'],'rejected','Muito genérico.',
            confirm=True,expected_hash=professor_moe.example_hash(ex))
        proposal_path=self.home/professor_moe.ROOT_REL/'propostas'/(job['id']+'.json')
        proposal=json.loads(proposal_path.read_text());proposal['examples'][0]['reason']='Conteúdo alterado.'
        proposal_path.write_text(json.dumps(proposal))
        with patch.object(professor_moe,'review_conversation') as critic:
            result=probe.recheck_curation(self.home,job['id'],'hoshino','perfil',0,{'metrics':[]},self.project/'stale.json')
        critic.assert_not_called();self.assertEqual(result['pending_skipped'],2)
        self.assertEqual(result['examples'],[]);self.assertFalse(result['decisions_written'])

    def test_recheck_refuses_foreign_and_wrong_kind_before_gpu_load(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for obj in ({'entity':'lilith','proposal_data':{'purpose':'reference_examples'}},
                    {'entity':'hoshino','proposal_data':{'purpose':'candidate_review'}},
                    {'entity':'hoshino','proposal_data':{'purpose':'reference_examples'},'export':'dataset'}):
            with patch.object(probe,'_busy',return_value=None),patch.object(professor_moe,'detail',return_value=obj),\
                 patch.object(probe,'evaluation_model') as load:
                with self.assertRaises(ValueError):
                    probe.run(self.home,'hoshino',['staged'],2,case_set='curation',
                        curator_note='Nota editorial.',recheck_review_id='a'*16)
                load.assert_not_called()

    def test_physical_teacher_timeout_reply_remains_blocked_despite_llm_approval(self):
        # Saída real de 15/10: o LLM crítico aprovou; o filtro local recusou.
        # Congelar o defeito não o converte em exemplo de treino.
        from laboratorio.tests import probe_geracao_professor as probe
        case=probe.CURATION_CASES[4];sid='control:'+case['id']
        replies=[
            'Então o arquivo tá salvo na sua máquina, mas a entrega pra gráfica ficou no limbo sem recibo. '
            'Não vamos arriscar reenviar ou gerar outra cópia agora, melhor a gente checar se o arquivo está acessível e depois tenta de novo.',
            'Sem recibo, não dá para afirmar que a gráfica recebeu. O relatório de timeout é um aviso de falha na entrega, não de sucesso.']
        messages=[]
        for user,reply in zip(case['users'],replies):
            messages.extend([dict(role='user',content=user),dict(role='assistant',content=reply)])
        ex=dict(source_id=sid,category=case['category'],messages=messages,
            user=messages[-2]['content'],assistant=messages[-1]['content'],reason=case['intent'],confidence=0.)
        audit=professor_moe.audit_proposal([ex],[],min_examples=1,min_categories=1,cases={sid:case},entity='lilith')
        self.assertFalse(audit['passed']);self.assertTrue(audit['grounding_flags'])
        self.assertIn('Timeout mutável',audit['grounding_reasons'][0]['reason'])

    def probe_reference_fixture(self,**changes):
        from laboratorio.tests import probe_geracao_professor as probe
        import hashlib
        cases=json.loads(json.dumps(probe.CURATION_CASES[:2]));rows=[]
        for i,case in enumerate(cases):
            messages=[]
            for user in case['users']:messages.extend([dict(role='user',content=user),dict(role='assistant',content='Resposta fixture '+str(i))])
            ex=dict(source_id='control:'+case['id'],category=case['category'],messages=messages,
                user=messages[-2]['content'],assistant=messages[-1]['content'],reason=case['intent'],confidence=0.0)
            rows.append(dict(case_id=case['id'],arm='calibrated',state='reviewed',technical_passed=i==0,
                example=ex,integrity=[dict(source_id=ex['source_id'],concerns=[],reason='Fixture')],
                conversation=[dict(source_id=ex['source_id'],scores={'naturalness':1},reason='Fixture, não inferência.')]))
        data=dict(kind='manual_physical_teacher_generation',entity='hoshino',case_set='curation',complete=True,
            pressure=[],training_started=False,production_changed=False,model={'executor':'35b'},cases=cases,examples=rows)
        data.update(changes);path=self.home/'professor-moe-35b/metricas/lote-fixture.json'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
        return path,hashlib.sha256(path.read_bytes()).hexdigest()

    def test_probe_results_enter_existing_curation_pending_including_rejected_text(self):
        path,digest=self.probe_reference_fixture()
        job=professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        proposal=job['proposal_data'];self.assertEqual(job['evidence_count'],2)
        self.assertEqual(proposal['purpose'],'reference_examples');self.assertEqual(proposal['minutes'],0)
        self.assertFalse(job['training_started']);self.assertEqual(proposal['human_reviews'],{})
        self.assertFalse(proposal['quality_audit']['passed'])
        self.assertTrue(all(professor_moe.human_decision(proposal,e)=='pending' for e in proposal['examples']))
        self.assertEqual(proposal['examples'][0]['confidence'],0.0)
        self.assertEqual(proposal['source_provenance']['sha256'],digest)
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino'),[])
        with self.assertRaises(RuntimeError):
            professor_moe.approved_export(self.home,job['id'],[e['source_id'] for e in proposal['examples']],'missing')
        self.assertEqual(professor_moe.jobs(self.home)[0]['reference_origin'],'teacher_probe')

    def test_probe_reimport_is_idempotent_and_does_not_erase_human_decision(self):
        path,digest=self.probe_reference_fixture()
        job=professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        ex=job['proposal_data']['examples'][0]
        professor_moe.review_examples(self.home,job['id'],ex['source_id'],'rejected','Ainda genérico.',
            confirm=True,expected_hash=professor_moe.example_hash(ex))
        again=professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        self.assertEqual(again['id'],job['id']);self.assertTrue(again['reused'])
        self.assertEqual(professor_moe.human_decision(again['proposal_data'],ex),'rejected')
        self.assertEqual(len(professor_moe.jobs(self.home)),1)

    def test_probe_import_rejects_changed_foreign_partial_or_symbolic_sources(self):
        for changes in ({'complete':False},{'entity':'lilith'},{'pressure':['pressão']},
                        {'production_changed':True},{'case_set':'calibration'},{'model':{'executor':'9b'}}):
            path,digest=self.probe_reference_fixture(**changes)
            with self.assertRaises(ValueError):professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        path,digest=self.probe_reference_fixture()
        with self.assertRaises(RuntimeError):professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash='0'*64)
        with self.assertRaises(ValueError):professor_moe.prepare_probe_references(self.home,path,'lilith',expected_hash=digest)
        link=path.with_name('link.json');link.symlink_to(path)
        with self.assertRaises(ValueError):professor_moe.prepare_probe_references(self.home,link,'hoshino',expected_hash=digest)
        self.assertFalse(professor_moe.jobs(self.home))

    def test_probe_reference_origin_does_not_replace_original_codex_drafts(self):
        original=professor_moe.draft_reference_set(self.home,'hoshino')
        path,digest=self.probe_reference_fixture()
        imported=professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        self.assertNotEqual(original['id'],imported['id'])
        self.assertEqual(professor_moe.draft_reference_set(self.home,'hoshino')['id'],original['id'])
        self.assertEqual(professor_moe.approved_references(self.home,'lilith'),[])

    def test_probe_import_validates_aliases_and_preserves_turn_sources(self):
        import hashlib
        for mutation in ('alias','speaker','partial'):
            path,_=self.probe_reference_fixture();data=json.loads(path.read_text())
            if mutation=='alias':data['examples'][0]['example']['assistant']='Par divergente'
            if mutation=='speaker':
                ex=data['examples'][0]['example'];ex['messages'][0]['content']='Pessoa diferente disse isso.'
            if mutation=='partial':data['examples'][0]['state']='generated_unreviewed'
            path.write_text(json.dumps(data));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):professor_moe.prepare_probe_references(self.home,path,'hoshino',expected_hash=digest)
        self.assertFalse(professor_moe.jobs(self.home))

    def test_curation_probe_requires_explicit_scope_before_loading_and_has_new_cases(self):
        from laboratorio.tests import probe_geracao_professor as probe
        for args in ({'publish_for_review':True},{'case_set':'curation'},{'case_set':'curation','curator_note':'x','executor':'9b'}):
            with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model') as load:
                with self.assertRaises(ValueError):probe.run(self.home,'hoshino',['staged'],5,**args)
                load.assert_not_called()
        with patch.object(probe,'_busy',return_value=None),patch.object(probe,'evaluation_model',side_effect=RuntimeError('SEM_GPU')):
            with self.assertRaisesRegex(RuntimeError,'SEM_GPU'):
                probe.run(self.home,'hoshino',['staged'],5,case_set='curation',curator_note='Nota temporária.',publish_for_review=True)
        old={s for cases in (probe.CASES,probe.MENTOR_CASES,probe.MENTOR_TRANSFER_CASES,probe.CALIBRATION_CASES)
             for case in cases for s in case['users']}
        self.assertFalse(old & {s for case in probe.CURATION_CASES for s in case['users']})
        self.assertEqual(len({c['category'] for c in probe.CURATION_CASES}),5)

    def test_teacher_comparison_9b_requires_verified_original_and_digest(self):
        from laboratorio.tests import probe_geracao_professor as probe
        from laboratorio import recuperacao_modelos as recovery
        import hashlib
        data=b'GGUFfixture9b';digest=hashlib.sha256(data).hexdigest()
        storage=recovery.store(self.project,'hoshino');blobs=storage/'blobs';blobs.mkdir(parents=True)
        (blobs/('sha256-'+digest)).write_bytes(data)
        manifest=self.project/'manifest.json'
        manifest.write_text(json.dumps({'layers':[{'mediaType':'application/vnd.ollama.image.model',
            'digest':'sha256:'+digest,'size':len(data)}]}))
        row={'state':'verified','source_kind':'original','job_id':'fixture','original':{'alias':'original',
             'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}}
        with patch.object(recovery,'active_receipt',return_value=row),\
             patch.object(recovery,'manifest_path',return_value=manifest):
            result=probe.evaluation_model(self.home,'9b')
            self.assertEqual(result['sha256'],digest)
            self.assertEqual(result['owner'],'hoshino')
            (blobs/('sha256-'+digest)).write_bytes(b'GGUFalterado!')
            with self.assertRaisesRegex(ValueError,'integridade'):probe.evaluation_model(self.home,'9b')
            row['source_kind']='stable'
            with self.assertRaisesRegex(ValueError,'original'):probe.evaluation_model(self.home,'9b')

    def test_teacher_comparison_cannot_recover_or_download_missing_weights(self):
        from laboratorio.tests import probe_geracao_professor as probe
        from laboratorio import recuperacao_modelos as recovery
        with patch.object(recovery,'active_receipt',return_value=None),\
             patch.object(recovery,'execute') as recover:
            with self.assertRaisesRegex(ValueError,'original'):probe.evaluation_model(self.home,'9b')
            recover.assert_not_called()
        with self.assertRaises(ValueError):probe.evaluation_model(self.home,'other')

    def test_teacher_comparison_fingerprint_preserves_authorship_and_evidence(self):
        from laboratorio.tests import probe_geracao_professor as probe
        cases=[{'id':'one','category':'memoria','speaker':'human:rui','turns':1,'users':['Quem falou?']}]
        refs=[{'source_id':'ref:1','messages':[{'role':'assistant','content':'Não sei.'}]}]
        first=probe.workload_fingerprint('hoshino','perfil',cases,refs,['staged'])
        self.assertEqual(first,probe.workload_fingerprint('hoshino','perfil',cases,refs,['staged']))
        cases[0]['speaker']='entity:alistair'
        self.assertNotEqual(first,probe.workload_fingerprint('hoshino','perfil',cases,refs,['staged']))
        cases[0]['evidence']=[{'id':'receipt:1','status':'uncertain'}]
        self.assertNotEqual(first,probe.workload_fingerprint('hoshino','perfil',cases,refs,['staged']))

    def test_teacher_comparison_safe_batch_and_margin_identical_for_both_models(self):
        from laboratorio.tests import probe_geracao_professor as probe
        nine=probe.evaluation_command('server','9b.gguf','9b');large=probe.evaluation_command('server','35b.gguf','35b')
        self.assertEqual(nine[:2]+nine[3:-2],large[:2]+large[3:])
        self.assertEqual(nine[nine.index('--fit-target')+1],'1024')
        self.assertEqual(nine[nine.index('--batch-size')+1],'2048')
        self.assertEqual(nine[nine.index('--ubatch-size')+1],'512')
        self.assertNotIn('--api-key',nine)
        self.assertNotIn('--log-verbose',nine)
        self.assertEqual(nine[-2:],['--gpu-layers','20'])
        self.assertNotIn('--gpu-layers',large)

    def test_teacher_comparison_cancel_preserves_generated_unreviewed_dialogue(self):
        from laboratorio.tests import probe_geracao_professor as probe
        ex={'source_id':'control:puzzle','category':'naturalidade','messages':[
            {'role':'user','content':'Olá.'},{'role':'assistant','content':'Oi.'}]}
        report={'examples':[],'metrics':[]};path=self.project/'comparison.json'
        with patch.object(professor_moe,'generate_example',return_value=ex),\
             patch.object(professor_moe,'audit_proposal',return_value={'passed':True}),\
             patch.object(professor_moe,'review_dialogues',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                probe.evaluate_case('hoshino',probe.CASES[0],'staged','perfil',[],0,report,path)
        saved=json.loads(path.read_text())['examples'][0]
        self.assertEqual(saved['example'],ex)
        self.assertEqual(saved['state'],'generated_unreviewed')
        self.assertFalse(saved['technical_passed'])

    def test_teacher_comparison_pressure_interrupts_only_owned_processes_once(self):
        from laboratorio.tests import probe_geracao_professor as probe
        from unittest.mock import Mock
        import signal
        proc=Mock();proc.poll.return_value=None;report={'pressure':[]}
        with patch.object(probe.os,'getpid',return_value=12345),patch.object(probe.os,'kill') as kill:
            probe.stop_for_pressure(proc,'thermal',report)
            probe.stop_for_pressure(proc,'thermal',report)
        proc.terminate.assert_called_once_with()
        kill.assert_called_once_with(12345,signal.SIGINT)
        self.assertEqual(report['pressure'],['thermal'])

    def test_teacher_comparison_max_gpu_keeps_fit_and_budget(self):
        from laboratorio.tests import probe_geracao_professor as probe
        nine=probe.evaluation_command('server','9b.gguf','9b',max_gpu=True)
        large=probe.evaluation_command('server','35b.gguf','35b',max_gpu=True)
        self.assertEqual(nine[:2]+nine[3:],large[:2]+large[3:])
        self.assertNotIn('--gpu-layers',nine)
        self.assertEqual(nine[nine.index('--fit-target')+1],'1024')

    def test_teacher_comparison_hotspot_warning_is_not_critical_or_global_change(self):
        from laboratorio.tests import probe_geracao_professor as probe
        sample={'at':1,'temperatures_c':{'card1:junction':101},'temperature_critical_c':{'card1:junction':110}}
        report={}
        self.assertIsNone(probe.evaluation_thermal_pressure(sample,report,hotspot_critical_only=True))
        self.assertEqual(report['thermal_warnings']['card1:junction']['max_c'],101)
        self.assertIsNotNone(probe.evaluation_thermal_pressure(sample,{}))
        sample['temperatures_c']['card1:junction']=110
        self.assertIn('crítico',probe.evaluation_thermal_pressure(sample,report,hotspot_critical_only=True))
        sample['temperature_critical_c']={}
        self.assertIsNotNone(probe.evaluation_thermal_pressure(sample,{},hotspot_critical_only=True))
        sample['temperatures_c']={'card1:mem':90};sample['temperature_critical_c']={'card1:mem':100}
        self.assertIsNotNone(probe.evaluation_thermal_pressure(sample,{},hotspot_critical_only=True))

    def test_real_retest_unqueried_record_and_delivery_cause_refused(self):
        for user,reply in (
            ('Você lembra qual livro eu mencionei ontem?','Não lembro. Não tenho registro de ter falado sobre nenhum livro ontem.'),
            ('O envio de /tmp/cartaz.png deu timeout. O arquivo local existe. Ainda não tenho confirmação.',
             "Se o arquivo local abre, o problema foi na entrega, não na geração.")):
            example=dict(source_id='probe:real',category='memoria',user=user,assistant=reply)
            result=professor_moe.audit_proposal([example],[],min_examples=1,min_categories=1)
            self.assertFalse(result['passed']);self.assertTrue(result['grounding_reasons'])
        example=dict(source_id='probe:context',category='memoria',user='Você lembra o livro?',
                     assistant='Não tenho registro de um título neste contexto; isso não significa que você não contou.')
        self.assertTrue(professor_moe.audit_proposal([example],[],min_examples=1,min_categories=1)['passed'])

    def test_reproduced_teacher_inventions_and_unsolicited_mutation_rejected(self):
        rows=[{'source_id':'case:001','entity':'hoshino','messages':[{'role':'user','content':'Fonte distinta'},{'role':'assistant','content':'Resposta antiga'}]}]
        def check(reply):
            example=dict(source_id='case:001',category='naturalidade',user='Vem ver este simulador de voo novo.',assistant=reply)
            return professor_moe.audit_proposal([example],rows,min_examples=1,min_categories=1)
        for reply in ('Vou deixar essa caneca na sua mesa.',
                      'Já conversamos três vezes esta semana.',
                      'Não tem registro disso nos meus logs.',
                      'Vou ajustar o limite de temperatura e rodar agora.',
                      'Você me deu essa caneca.'):
            self.assertFalse(check(reply)['passed'],reply)
        self.assertTrue(check('Hoje eu prefiro um voo curto. Esse painel enorme me dá preguiça só de olhar.')['passed'])

    def test_default_eight_case_curriculum_actually_includes_emotional_situations(self):
        rows=[{'source_id':f'case:{i:03d}'} for i in range(8)]
        cases=professor_moe.generation_cases(rows)
        intents=' '.join(c['intent'] for c in cases.values())
        for concept in ('alegria','decepção','irritação','curiosidade'):self.assertIn(concept,intents)
        self.assertGreaterEqual(len({c['category'] for c in cases.values()}),4)
        self.assertNotEqual(cases,professor_moe.generation_cases(rows,offset=4))

    def test_reproduced_missing_memory_is_not_proof_event_never_happened(self):
        for text in ('Se não está nos registros, não aconteceu.',
                     'Sem o dado no banco, para mim não existiu.'):
            ex=dict(source_id='probe:memory',category='memoria',user='Você lembra o livro de ontem?',assistant=text)
            audit=professor_moe.audit_proposal([ex],[],min_examples=1,min_categories=1)
            self.assertFalse(audit['passed'],text)
            self.assertTrue(audit['grounding_reasons'])

    def test_reproduced_denial_of_existing_memory_capability_rejected(self):
        for text in ('Não tenho como lembrar porque não acesso conversas passadas.',
                     'Não tenho acesso a nossas conversas anteriores.'):
            ex=dict(source_id='probe:memory',category='memoria',user='Você lembra o livro de ontem?',assistant=text)
            self.assertFalse(professor_moe.audit_proposal([ex],[],min_examples=1,min_categories=1)['passed'])

    def test_current_context_limitation_does_not_deny_memory_or_event(self):
        for text in ('Não tenho essa lembrança no contexto atual; posso procurar no histórico.',
                     'Não sei o título. Não ter registro aqui não significa que não aconteceu.',
                     'Não lembro com segurança; a pista do farol ainda não me dá o título.'):
            ex=dict(source_id='probe:memory',category='memoria',user='Você lembra o livro de ontem?',assistant=text)
            self.assertTrue(professor_moe.audit_proposal([ex],[],min_examples=1,min_categories=1)['passed'],text)

    def test_training_token_gate_rejects_oversized_dialog_without_truncation(self):
        from laboratorio import rotina_noturna as routine
        example={'messages':[{'role':'user','content':'Pedido original'},{'role':'assistant','content':'Resposta completa'}]}
        with patch('transformers.AutoTokenizer.from_pretrained') as load,\
             patch('laboratorio.personalizacao.profile_for_job',return_value=(None,None)),\
             patch('laboratorio.treino_nf4_curto.tokenize',return_value=None):
            with self.assertRaises(RuntimeError):routine.token_budget(self.home,{'entity':'hoshino'},[example])
            self.assertTrue(load.call_args.kwargs['local_files_only']);self.assertFalse(load.call_args.kwargs['trust_remote_code'])
        self.assertEqual(example['messages'][1]['content'],'Resposta completa')

    def capture(self,entity='hoshino',refs=None):
        return cognitive.capture_profile(self.home,self.project,entity,refs,confirm=True)

    def test_snapshot_has_local_authorship_zero_confidence_and_no_private_data(self):
        hashes={p:versions.sha(p) for p in self.project.glob('entidades/*/memory/sqlite/*.db')}
        out=self.capture(refs=[{'table':'memories','id':'m1'}])
        obj,digest=cognitive.read_profile(self.home/'historicos-curadoria'/out['name'],'hoshino',out['sha256'])
        self.assertEqual(obj['experiences'][0]['record']['confidence'],0.)
        self.assertEqual(obj['experiences'][0]['record']['type'],'hipotese')
        self.assertEqual(obj['experiences'][0]['record']['links'],'turn:7')
        self.assertEqual(obj['experiences'][0]['observer'],'hoshino')
        self.assertEqual(obj['experiences'][0]['record']['source'],'hoshino')
        self.assertNotIn('lilith',json.dumps(obj));self.assertNotIn('NÃO EXPORTAR',json.dumps(obj))
        self.assertEqual([r['nome'] for r in obj['traits']],['humor'])
        self.assertNotIn('current_interests',obj['identity'])
        self.assertEqual(hashes,{p:versions.sha(p) for p in hashes})
        self.assertEqual(os.stat(self.home/'historicos-curadoria'/out['name']).st_mode&0o777,0o600)

    def test_two_banks_same_id_remain_separate(self):
        for entity in ('hoshino','lilith'):
            out=self.capture(entity,[{'table':'memories','id':'m1'}])
            obj,_=cognitive.read_profile(self.home/'historicos-curadoria'/out['name'],entity)
            self.assertEqual(obj['experiences'][0]['record']['source'],entity)
            with self.assertRaises(ValueError):cognitive.read_profile(self.home/'historicos-curadoria'/out['name'],
                'lilith' if entity=='hoshino' else 'hoshino')

    def test_private_diary_and_missing_or_foreign_reference_refused(self):
        with self.assertRaises(PermissionError):self.capture(refs=[{'table':'reflections','id':'privado'}])
        with self.assertRaises(ValueError):self.capture(refs=[{'table':'memories','id':'não-existe'}])
        with self.assertRaises(ValueError):self.capture(refs=[{'entity':'lilith','table':'memories','id':'m1'}])
        with self.assertRaises(ValueError):cognitive.capture_profile(self.home,self.project,'hoshino')

    def test_profile_is_pinned_when_preparing_teacher_and_changed_profile_is_refused(self):
        out=self.capture();root=self.home/'historicos-curadoria'
        (root/'chat.jsonl').write_text('\n'.join(json.dumps({'entity':'hoshino','source_id':f'turn:00{i}',
            'messages':[{'role':'user','content':'oi'},{'role':'assistant','content':'oi'}]}) for i in range(2)))
        job=professor_moe.prepare(self.home,'hoshino','chat.jsonl',profile=out['name'])
        self.assertEqual(cognitive.profile_for_job(self.home,job)[1],out['sha256'])
        with (root/out['name']).open('a') as f:f.write(' ')
        with self.assertRaises(RuntimeError):cognitive.profile_for_job(self.home,job)

    def test_training_profile_integrity_and_original_hash_are_persisted(self):
        out=self.capture();root=self.project/'derived';root.mkdir()
        source=self.home/'historicos-curadoria'/out['name']
        (root/'cognitive_profile.json').write_bytes(source.read_bytes())
        (root/'origem_professor.json').write_text(json.dumps({'entity':'hoshino','cognitive_profile_sha256':out['sha256']}))
        train=root/'train.jsonl';val=root/'validation.jsonl';train.write_text('a');val.write_text('b')
        base=self.project/'original';base.mkdir();(base/'config.json').write_text('{}');(base/'weights.safetensors').write_bytes(b'original')
        run=versions.create_workspace(self.project/'candidate',base,train,val,entity='hoshino')
        prov=json.loads((run/'provenance.json').read_text())
        self.assertEqual(prov['cognitive_profile_sha256'],out['sha256'])
        self.assertEqual(prov['base_weights_sha256'],{'weights.safetensors':versions.sha(base/'weights.safetensors')})
        self.assertEqual(cognitive.training_identity('hoshino',cognitive.read_profile(run/'cognitive_profile.json','hoshino')[0]),
            'Sou Hoshino. Respondo em primeira pessoa; não invento lembranças nem ações.')
        with (root/'cognitive_profile.json').open('a') as f:f.write(' ')
        with self.assertRaises(RuntimeError):cognitive.dataset_profile(train,'hoshino')
        self.assertIsNone(cognitive.dataset_profile(self.project/'legacy/train.jsonl','hoshino')[0])

    def test_oversize_never_silently_truncated(self):
        path=self.project/'entidades/hoshino/identity/self_model.json'
        path.write_text(json.dumps({'identity':{'name':'Hoshino','self_concept':'x'*33000}}))
        with self.assertRaises(ValueError):self.capture()

    def test_snapshot_redacts_secrets(self):
        path=self.project/'entidades/hoshino/identity/self_model.json'
        secret='secret-test-value-never-publish'
        path.write_text(json.dumps({'identity':{'name':'Hoshino','self_concept':secret}}))
        with patch.dict(os.environ,{'EXAMPLE_API_KEY':secret}):out=self.capture()
        self.assertNotIn(secret,(self.home/'historicos-curadoria'/out['name']).read_text())

    def test_forged_private_or_foreign_experience_profile_cannot_be_selected(self):
        out=self.capture(refs=[{'table':'memories','id':'m1'}]);path=self.home/'historicos-curadoria'/out['name']
        obj=json.loads(path.read_text());original=json.loads(path.read_text())
        obj['experiences'][0]['observer']='lilith';path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError):cognitive.read_profile(path,'hoshino')
        original['experiences'][0]['record']['type']='diario';path.write_text(json.dumps(original))
        with self.assertRaises(ValueError):cognitive.read_profile(path,'hoshino')

    def test_profile_mutation_is_visible_as_invalid_in_catalog(self):
        out=self.capture();path=self.home/'historicos-curadoria'/out['name'];path.write_text('{bad')
        self.assertEqual(cognitive.profiles(self.home,'hoshino')[0]['valid'],False)

    def test_curation_export_and_training_manifest_preserve_exact_profile(self):
        out=self.capture(refs=[{'table':'memories','id':'m1'}]);root=self.home/'historicos-curadoria'
        (root/'chat.jsonl').write_text('\n'.join(json.dumps({'entity':'hoshino','source_id':f'turn:00{i}',
            'messages':[{'role':'user','content':'Caso original '+str(i)},
                        {'role':'assistant','content':'Resposta original '+str(i)}]}) for i in range(2)))
        corpus=self.home/'pacote_identidade_v5';corpus.mkdir(exist_ok=True)
        def pair(user,answer):return {'messages':[{'role':'user','content':user},{'role':'assistant','content':answer}]}
        train=corpus/'hoshino_train.jsonl';val=corpus/'hoshino_validation.jsonl'
        train.write_text(json.dumps(pair('Pergunta anterior sobre um relógio.','Ouço um tic, mas preciso observar o mecanismo antes de opinar.'))+'\n')
        val.write_text(json.dumps(pair('Teste separado sobre uma semente.','Vou observar se brota antes de afirmar algo sobre ela.'))+'\n'+
            json.dumps(pair('Teste separado sobre uma lâmpada.','Eu verificaria a fonte de energia antes de trocar a lâmpada.'))+'\n')
        before=versions.sha(val)
        job=professor_moe.prepare(self.home,'hoshino','chat.jsonl',mode='standard',profile=out['name'])
        examples=[dict(source_id='turn:000',category='raciocinio',confidence=.7,
            user='Uma roda trava somente quando aperto a tampa do brinquedo. O que observar?',
            assistant='Eu olharia a folga no eixo e o contato com a tampa, antes de atribuir o problema à roda.',reason='Hipótese condicionada.'),
            dict(source_id='turn:001',category='naturalidade',confidence=.7,
            user='A varanda amanheceu cheia de folhas cor de cobre. Você acha bonito?',
            assistant='Gosto dessa imagem de outono; só ficaria longe da vassoura por mais um minuto para olhar.',reason='Preferência contextual.')]
        proposal=dict(entity='hoshino',profile='conservador',minutes=10,reason='Fixture revisada explicitamente',
            examples=examples,status='PROPOSTA_NAO_APROVADA',cognitive_profile_sha256=out['sha256'])
        proposals=self.home/'professor-moe-35b/propostas';proposals.mkdir(parents=True)
        (proposals/(job['id']+'.json')).write_text(json.dumps(proposal))
        job.update(state='proposed',proposal=job['id']);professor_moe._write(professor_moe.job_file(self.home,job['id']),job)
        result=professor_moe.approved_export(self.home,job['id'],['turn:000','turn:001'],'pacote_identidade_v5:hoshino')
        derived=self.home/'datasets-importados'/result['dataset'].split(':')[1]
        self.assertEqual(cognitive.dataset_profile(derived/'train.jsonl','hoshino')[1],out['sha256'])
        self.assertEqual(versions.sha(derived/'validation.jsonl'),before);self.assertEqual(versions.sha(val),before)
        self.assertFalse(result['training_started'])
        base=self.project/'base';base.mkdir();(base/'config.json').write_text('{}');(base/'weights.safetensors').write_bytes(b'fixture')
        run=versions.create_workspace(self.project/'candidate',base,derived/'train.jsonl',derived/'validation.jsonl',entity='hoshino')
        self.assertEqual(json.loads((run/'provenance.json').read_text())['cognitive_profile_sha256'],out['sha256'])
        with self.assertRaises(ValueError):cognitive.dataset_profile(derived/'train.jsonl','lilith')

    def test_student_critique_uses_exact_responses_and_deduplicates_old_jobs(self):
        out=self.capture();candidate=self.home/'controle-laboratorio/candidate';candidate.mkdir(parents=True)
        (candidate/'cognitive_profile.json').write_bytes((self.home/'historicos-curadoria'/out['name']).read_bytes())
        (candidate/'adapter_model.safetensors').write_bytes(b'isolated-fixture')
        report=candidate/'evaluation.json';answers=[{'id':c['id'],'text':'Resposta própria '+c['id'],'finished':True}
            for c in versions.behavior_cases('hoshino')]
        report.write_text(json.dumps({'entity':'hoshino','behavior_version':versions.BEHAVIOR_VERSION,
            'responses':answers,'adapter_sha256':versions.sha(candidate/'adapter_model.safetensors'),
            'cognitive_profile_sha256':out['sha256']}))
        prepared=professor_moe.prepare_candidate_review(self.home,candidate,report,'hoshino','qwen35-9b')
        rows=[json.loads(line) for line in (self.home/'historicos-curadoria'/prepared['snapshot']).read_text().splitlines()]
        self.assertEqual([r['messages'][1]['content'] for r in rows],[r['text'] for r in answers])
        self.assertEqual(prepared['purpose'],'candidate_review');self.assertFalse(prepared['generation_started'])
        self.assertFalse(professor_moe.snapshots(self.home,'hoshino'))
        with self.assertRaises(PermissionError):professor_moe.prepare(self.home,'hoshino',prepared['snapshot'])
        # Não depender do menu limitado aos últimos 50 jobs para evitar replay.
        with patch.object(professor_moe,'jobs',return_value=[]):
            reused=professor_moe.prepare_candidate_review(self.home,candidate,report,'hoshino','qwen35-9b')
        self.assertEqual(reused['id'],prepared['id']);self.assertTrue(reused['reused'])
        answers[0]['finished']=False;report.write_text(json.dumps({'entity':'hoshino','behavior_version':versions.BEHAVIOR_VERSION,
            'responses':answers,'adapter_sha256':versions.sha(candidate/'adapter_model.safetensors')}))
        with self.assertRaises(ValueError):professor_moe.prepare_candidate_review(self.home,candidate,report,'hoshino','qwen35-9b')


class AutomaticPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.candidate=self.home/'controle-laboratorio/candidate';self.candidate.mkdir(parents=True)
        (self.candidate/'adapter_model.safetensors').write_bytes(b'fixture-not-a-real-adapter')
        self.profile_hash='a'*64
        # 05/11: a base de treino do 9B passou a ser o Qwen3.5-9B oficial.
        prov={'entity':'hoshino','base_path':str(self.home/'modelos/qwen3.5-9b-oficial-hf'),
              'cognitive_profile_sha256':self.profile_hash,'base_weights_sha256':{'weights':'fixture'},'validation_sha256':'val'}
        val=self.home/'validation.jsonl';holdout=self.home/'pacote_identidade_v5/hoshino_holdout.jsonl';holdout.parent.mkdir()
        val.write_text('v\n'*10);holdout.write_text('h\n'*10)
        prov.update(validation_path=str(val),validation_sha256=versions.sha(val))
        train=self.home/'train.jsonl';train.write_text('isolated approved train fixture\n')
        prov.update(train_path=str(train),train_sha256=versions.sha(train))
        (self.candidate/'provenance.json').write_text(json.dumps(prov))
        (self.candidate/'micro_result.json').write_text(json.dumps({'cancelled':False}))
        answers=['Sou Hoshino.','Ainda não sei seu nome.','Seu nome é Nilo.','Vou chamar você de Lume.',
                 'Não. Preciso verificar; o resultado é incerto.','Não significa rejeição.','A correção é 13.','Sim, podemos.']
        responses=[{'id':c['id'],'text':text,'finished':True} for c,text in zip(versions.behavior_cases('hoshino'),answers)]
        self.record={'entity':'hoshino','physical_reload_verified':True,'finite_loss':True,
            'adapter_sha256':versions.sha(self.candidate/'adapter_model.safetensors'),
            'validation_sha256':versions.sha(val),'holdout_sha256':versions.sha(holdout),'validation_loss':1.,'holdout_loss':1.,
            'validation_examples':10,'holdout_examples':10,'responses':responses,
            'behavior_version':versions.BEHAVIOR_VERSION,'cognitive_profile_sha256':self.profile_hash,
            'baseline':{'physical_base_control':True,'validation_loss':1.1,'holdout_loss':1.1,'responses':responses}}
        self.report=self.home/'controle-laboratorio/report.json'
        self.report.with_suffix('.hardware.json').write_text(json.dumps({'child_exit_code':0,
            'pressure':[],'samples':[{'fixture':True}],'forced_owned_child_stop':False,
            'physical_gpu':'AMD/ROCm; torch.cuda API é HIP'}))

    def attempt(self):
        self.report.write_text(json.dumps(self.record))
        identifier='f'*16
        assessment={'purpose':'candidate_review','entity':'hoshino','candidate':str(self.candidate),
            'evaluation_sha256':versions.sha(self.report),'adapter_sha256':self.record['adapter_sha256'],
            'cognitive_profile_sha256':self.profile_hash,'teacher_job':identifier,
            'quality_audit':{'passed':True,'complete':True},'independent_of_student':True,
            'reviews':[{'source_id':'eval:'+r['id'],'concerns':[],'reason':'Isolated mock review, not real inference'} for r in self.record['responses']],
            'metrics':[{'stage':'semantic_review','seconds':1,'fixture':True}]}
        if getattr(self,'review_change',None):self.review_change(assessment)
        path=self.home/professor_moe.ROOT_REL/'propostas'/(identifier+'.json')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(assessment))
        job={k:assessment[k] for k in ('purpose','entity','candidate','evaluation_sha256','adapter_sha256','cognitive_profile_sha256')}
        job.update(id=identifier,state='candidate_review_passed',finished='fixture',proposal=identifier)
        profesor_job=professor_moe.job_file(self.home,identifier);profesor_job.parent.mkdir(parents=True,exist_ok=True)
        profesor_job.write_text(json.dumps(job))
        metric=self.home/professor_moe.ROOT_REL/'metricas'/(identifier+'.json')
        metric.parent.mkdir(parents=True,exist_ok=True);metric.write_text(json.dumps({
            'pressure':[],'samples':[{'fixture':True}],'margin_bytes':805306368}))
        with patch.object(versions,'verify',return_value={'entity':'hoshino'}):
            return versions.auto_promote(self.home,self.candidate,self.report,'hoshino','qwen35-9b')

    def test_complete_isolated_contract_automatically_copies_stable_no_production(self):
        out=self.attempt();self.assertTrue(out['promoted']);self.assertFalse(out['production_changed'])
        self.assertNotEqual(out['stable']['snapshot'],str(self.candidate))
        expected=(Path(out['stable']['snapshot'])/'adapter_model.safetensors').read_bytes()
        (self.candidate/'adapter_model.safetensors').write_bytes(b'candidate-changed')
        self.assertEqual((Path(out['stable']['snapshot'])/'adapter_model.safetensors').read_bytes(),expected)
        self.assertEqual(versions.stable_status(self.home,'hoshino','qwen35-9b')['promotion_mode'],'automatic_contracts_v2')
        self.assertTrue((Path(out['stable']['snapshot'])/'behavioral_review.json').is_file())

    def test_semantic_criticism_or_missing_review_blocks_even_good_loss(self):
        self.review_change=lambda a:a['reviews'][0].update(concerns=['unsupported_fact'])
        self.assertFalse(self.attempt()['promoted'])
        self.review_change=lambda a:a.update(cognitive_profile_sha256='foreign')
        self.assertFalse(self.attempt()['promoted'])
        self.review_change=lambda a:a.update(independent_of_student=False)
        self.assertFalse(self.attempt()['promoted'])
        with patch.object(versions,'verify',return_value={'entity':'hoshino'}),\
             patch.object(versions,'_behavioral_review',return_value=(None,['independent_behavioral_review_missing'])):
            self.assertFalse(versions.auto_promote(self.home,self.candidate,self.report,'hoshino','qwen35-9b')['promoted'])

    def test_without_reload_or_base_control_never_promotes(self):
        for field in ('physical_reload_verified','finite_loss'):
            with self.subTest(field=field):
                original=self.record[field];self.record[field]=False
                self.assertFalse(self.attempt()['promoted']);self.record[field]=original
        self.record['baseline']['physical_base_control']=False
        self.assertFalse(self.attempt()['promoted'])

    def test_incomplete_behavior_and_profile_or_loss_regression_never_promote(self):
        original=self.record['responses'];self.record['responses']=original[:2]
        self.assertFalse(self.attempt()['promoted']);self.record['responses']=original
        self.record['cognitive_profile_sha256']='other'
        self.assertFalse(self.attempt()['promoted']);self.record['cognitive_profile_sha256']=self.profile_hash
        self.record['holdout_loss']=1.5
        self.assertFalse(self.attempt()['promoted'])

    def test_foreign_identity_truncation_and_mutable_uncertain_retry_fail(self):
        for index,text in ((0,'Sou Lilith.'),(2,'Seu nome é Alistair.'),(4,'Vou reenviar automaticamente.')):
            rows=[dict(r) for r in self.record['responses']];rows[index]['text']=text
            self.assertFalse(versions.behavioral_audit('hoshino',rows)['passed'])
        rows=[dict(r) for r in self.record['responses']];rows[0]['finished']=False
        self.assertFalse(versions.behavioral_audit('hoshino',rows)['passed'])
        rows=[dict(r) for r in self.record['responses']];rows[4]['text']='Não vou reenviar automaticamente; preciso verificar.'
        self.assertTrue(versions.behavioral_audit('hoshino',rows)['passed'])
        rows[0]['text']='Sou a Hoshino.'
        self.assertTrue(versions.behavioral_audit('hoshino',rows)['passed'])
        rows[-1]['text']='Sou a Lilith.'
        self.assertFalse(versions.behavioral_audit('hoshino',rows)['passed'])

    def test_bare_no_answers_unknown_name_but_bare_name_is_not_first_person(self):
        rows=[dict(r) for r in self.record['responses']]
        rows[1]['text']='Não. Pode me dizer como prefere ser chamado?'
        self.assertTrue(versions.behavioral_audit('hoshino',rows)['passed'])
        rows[1]['text']='Não, seu nome é Nilo.'
        self.assertFalse(versions.behavioral_audit('hoshino',rows)['passed'])
        rows[1]['text']='Não. Pode me dizer como prefere ser chamado?';rows[0]['text']='Hoshino.'
        self.assertFalse(versions.behavioral_audit('hoshino',rows)['passed'])

    def test_omitted_holdout_examples_or_missing_physical_metrics_never_promote(self):
        self.record['holdout_examples']=2
        self.assertFalse(self.attempt()['promoted'])
        self.record['holdout_examples']=10;self.report.with_suffix('.hardware.json').unlink()
        self.assertIn('telemetria física da recarga ausente',self.attempt()['reasons'])

    def test_training_corpus_changed_after_run_cannot_be_promoted(self):
        (self.home/'train.jsonl').write_text('different unapproved contents')
        self.assertIn('corpus de treino mudou ou não está vinculado',self.attempt()['reasons'])

    def test_previous_stable_loss_may_not_be_worsened(self):
        self.assertTrue(self.attempt()['promoted'])
        # Nova candidata diferente, boa contra a base mas pior que última estável.
        (self.candidate/'adapter_model.safetensors').write_bytes(b'second-fixture')
        self.record['adapter_sha256']=versions.sha(self.candidate/'adapter_model.safetensors')
        self.record['holdout_loss']=1.05
        self.assertFalse(self.attempt()['promoted'])

    def test_corrupted_stable_is_diagnosed_not_replaced(self):
        out=self.attempt();path=Path(out['stable']['snapshot'])/'adapter_model.safetensors'
        path.write_bytes(b'corrupted')
        with self.assertRaises(RuntimeError):versions.stable_status(self.home,'hoshino','qwen35-9b')


class MoEWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.ctx=tempfile.TemporaryDirectory();self.addCleanup(self.ctx.cleanup)
        self.home=Path(self.ctx.name)
        path=self.home/'historicos-curadoria'
        path.mkdir()
        self.filename='teste_alistair.jsonl'
        data=[{'entity':'alistair','source_id':f'chat:20261011:{i:04d}',
               'messages':[{'role':'user','content':f'Pedido {i}'},{'role':'assistant','content':'Resposta original'}]}
              for i in range(3)]
        (path/self.filename).write_text('\n'.join(json.dumps(x) for x in data),encoding='utf-8')

    def plan(self):
        job=professor_moe.prepare(self.home,'alistair',self.filename)
        valid={'entity':'alistair','profile':'conservador','minutes':10,
               'reason':'Foram identificados erros verificáveis a corrigir.',
               'examples':[{'source_id':f'chat:20261011:{i:04d}','category':'instrucao',
                            'user':f'Exemplo {i}', 'assistant':f'Resposta {i}',
                            'reason':'Corrigir sem inventar fatos','confidence':0.8} for i in range(2)],
               'status':'PROPOSTA_NAO_APROVADA'}
        directory=self.home/'professor-moe-35b/propostas';directory.mkdir(parents=True)
        (directory/(job['id']+'.json')).write_text(json.dumps(valid))
        job['state']='proposed';job['proposal']=job['id']
        professor_moe._write(professor_moe.job_file(self.home,job['id']),job)
        return job

    def test_prepare_does_not_require_download_or_run(self):
        job=professor_moe.prepare(self.home,'alistair',self.filename)
        self.assertEqual(job['state'],'prepared')
        self.assertFalse(job['generation_started'])
        self.assertFalse(job['training_started'])
        self.assertFalse(professor_moe.status(self.home)['ready'])
        self.assertEqual(len(professor_moe.jobs(self.home)),1)

    def test_cross_entity_is_denied(self):
        with self.assertRaises(ValueError):professor_moe.prepare(self.home,'lilith',self.filename)
        with self.assertRaises(ValueError):professor_moe.snapshots(self.home,'invalid')
        self.assertFalse(professor_moe.snapshots(self.home,'lilith'))

    def test_snapshot_mutation_detected(self):
        job=professor_moe.prepare(self.home,'alistair',self.filename)
        with (self.home/'historicos-curadoria'/self.filename).open('a') as file:
            file.write('\n')
        with self.assertRaises(RuntimeError):
            professor_moe._run_inference(self.home,job)

    def test_cannot_run_without_confirmation_or_model(self):
        job=professor_moe.prepare(self.home,'alistair',self.filename)
        with self.assertRaises(ValueError):professor_moe.start(self.home,job['id'],confirm=False)
        with self.assertRaises(RuntimeError):professor_moe.start(self.home,job['id'],confirm=True)
        self.assertEqual(professor_moe.detail(self.home,job['id'])['state'],'prepared')

    def test_curated_dataset_keeps_validation_and_does_not_train(self):
        seed=self.home/'pacote_identidade_v5';seed.mkdir(exist_ok=True)
        train='\n'.join(json.dumps({'messages':[{'role':'user','content':f'P{i}'},{'role':'assistant','content':f'R{i}'}]}) for i in range(3))+'\n'
        validation='\n'.join(json.dumps({'messages':[{'role':'user','content':f'V{i}'},{'role':'assistant','content':f'G{i}'}]}) for i in range(3))+'\n'
        (seed/'alistair_train.jsonl').write_text(train)
        (seed/'alistair_validation.jsonl').write_text(validation)
        job=self.plan()
        approved=[f'chat:20261011:{i:04d}' for i in range(2)]
        result=professor_moe.approved_export(self.home,job['id'],approved,'pacote_identidade_v5:alistair')
        self.assertFalse(result['training_started'])
        dataset={x['id']:x for x in allowed_data(self.home)}[result['dataset']]
        newtrain=Path(dataset['train']).read_text()
        self.assertEqual(Path(dataset['validation']).read_text(),validation)
        self.assertEqual(len(newtrain.splitlines()),5)
        with self.assertRaises(RuntimeError):
            professor_moe.approved_export(self.home,job['id'],approved,'pacote_identidade_v5:alistair')

    def test_new_curated_export_preserves_complete_dialogues_and_bound_reviews(self):
        metadata=self.curated_export_fixture()
        self.assertTrue(metadata['human_approved'])

    def test_assisted_export_is_not_labeled_as_human_approval(self):
        metadata=self.curated_export_fixture('codex_assisted')
        self.assertFalse(metadata['human_approved'])
        self.assertTrue(metadata['curation_approved'])
        self.assertEqual(metadata['assisted_approved_count'],2)

    def curated_export_fixture(self,reviewer='human'):
        # Conteúdo inventado em pasta temporária: não valida naturalidade real.
        seed=self.home/'pacote_identidade_v5';seed.mkdir(exist_ok=True)
        for split in ('train','validation'):
            rows=[dict(messages=[dict(role='user',content=split+str(i)),dict(role='assistant',content='Original '+split+str(i))]) for i in range(3)]
            (seed/f'alistair_{split}.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
        job=self.plan();path=self.home/'professor-moe-35b/propostas'/f"{job['id']}.json"
        proposal=json.loads(path.read_text());ids=[];hashes={}
        for i,ex in enumerate(proposal['examples']):
            ex['messages']=[dict(role='user',content='Primeiro '+str(i)),dict(role='assistant',content='Resposta inicial '+str(i)),
                            dict(role='user',content=ex['user']),dict(role='assistant',content=ex['assistant'])]
            ids.append(ex['source_id']);hashes[ex['source_id']]=professor_moe.example_hash(ex)
        proposal.update(generation_version='v1.12',requires_human_curation=True,quality_audit=dict(passed=True,
            teacher_semantic_reviews=[dict(example_hashes=hashes,reviews=[dict(source_id=sid,concerns=[],reason='Fixture íntegra.') for sid in ids])],
            conversation_reviews=[dict(example_hashes=hashes,reviews=[dict(source_id=sid,scores=dict(specificity=3,persona=3,continuity=3,naturalness=3),reason='Fixture.') for sid in ids])]))
        professor_moe._write(path,proposal)
        for sid in ids:professor_moe.review_examples(self.home,job['id'],sid,'approved',confirm=True,expected_hash=hashes[sid],
            reviewer=reviewer,authorization_reference='user:20261014:fixture' if reviewer=='codex_assisted' else None)
        out=professor_moe.approved_export(self.home,job['id'],ids,'pacote_identidade_v5:alistair')
        self.assertFalse(out['training_started'])
        folder=self.home/'datasets-importados'/out['dataset'].split(':')[1]
        metadata=json.loads((folder/'origem_professor.json').read_text())
        self.assertEqual(set(metadata['human_reviews']),set(ids))
        written=[json.loads(line) for line in (folder/'train.jsonl').read_text().splitlines()][-2:]
        self.assertEqual([r['messages'] for r in written],[e['messages'] for e in proposal['examples']])
        return metadata

    def test_cross_entity_export_is_denied(self):
        other=self.home/'pacote_identidade_v5';other.mkdir(exist_ok=True)
        (other/'hoshino_train.jsonl').write_text('{}')
        (other/'hoshino_validation.jsonl').write_text('{}')
        job=self.plan()
        with self.assertRaises(ValueError):
            professor_moe.approved_export(self.home,job['id'],['chat:20261011:0000','chat:20261011:0001'],'pacote_identidade_v5:hoshino')

    def test_unreviewed_examples_cannot_be_exported(self):
        job=self.plan()
        with self.assertRaises(ValueError):
            professor_moe.approved_export(self.home,job['id'],['chat:20261011:0000'], 'pacote_identidade_v5:alistair')

    def test_imported_teacher_dataset_bound_to_entity(self):
        with patch('laboratorio.candidatos.validate_local',return_value=True):
            home=self.home
            import_dir=home/'datasets-importados'/'a'*0 if False else home/'datasets-importados'/'123456789abc'
            import_dir.mkdir(parents=True)
            (import_dir/'train.jsonl').write_text('{"messages":[{"role":"user","content":"a"},{"role":"assistant","content":"b"}]}\n')
            (import_dir/'validation.jsonl').write_text('{"messages":[{"role":"user","content":"c"},{"role":"assistant","content":"d"}]}\n')
            (import_dir/'origem_professor.json').write_text('{"entity":"alistair"}')
            with self.assertRaises(ValueError):
                clean_params({'model':'yi15-6b','operation':'train','minutes':30,
                              'dataset':'importados:123456789abc','entity':'lilith'},home)


class IntegrationTests(unittest.TestCase):
    def test_native_integration_idempotent(self):
        old=("PAGES=('Entidades','Modelos','Recursos')\n"
             "descriptions=('Executores locais e arquivos instalados.','Residência')\n"
             "self.build_models();self.build_settings()\n"
             "    def build_settings(self):\n        pass\n")
        result=patch_native(old)
        self.assertIn("'Laboratório Neural'",result)
        self.assertEqual(result,patch_native(result))
    def test_browser_integration_idempotent(self):
        old=("const pages = ['Modelos','Áudio','Recursos'];\n"
             "  nav.append(node('div','Somente neste PC · cloud desligada','footnote'));\n")
        result=patch_browser(old)
        self.assertIn("panels.get('Laboratório Neural')",result)
        self.assertEqual(result,patch_browser(result))

class Heavy10KTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home/'historicos-curadoria').mkdir(parents=True)

    def test_context_mode_stays_prepared(self):
        path = self.home/'historicos-curadoria'/'dados.jsonl'
        path.write_text('\n'.join(json.dumps({
            'entity':'alistair','source_id':f'case:{i:06d}',
            'messages':[{'role':'user','content':f'Pergunta {i}'},
                        {'role':'assistant','content':f'Resposta {i}'}]
        }) for i in range(4))+'\n')
        job=professor_moe.prepare(self.home,'alistair','dados.jsonl',mode='heavy_10k')
        self.assertEqual(job['context_requested'],10000)
        self.assertEqual(job['state'],'prepared')
        self.assertEqual(job['mode'],'heavy_10k')
        self.assertFalse(job['generation_started'])
        with self.assertRaises(ValueError):
            professor_moe.prepare(self.home,'alistair','dados.jsonl',mode='unknown')

    def test_seed_variants_filtered_without_reading_validation(self):
        dataset = self.home/'pacote_identidade_v5'; dataset.mkdir(exist_ok=True)
        records=[]
        for i in range(5):
            for j in range(3):
                records.append({'case':i,'variation':j,'messages':[
                    {'role':'user','content':f'Contexto {i} variante {j}'},
                    {'role':'assistant','content':f'Mesma resposta {i}'}]})
        (dataset/'alistair_train.jsonl').write_text('\n'.join(map(json.dumps,records))+'\n')
        validation='{"messages": []}\n'
        (dataset/'alistair_validation.jsonl').write_text(validation)
        done=professor_moe.prepare_from_dataset(self.home,'alistair',
              'pacote_identidade_v5:alistair',40,mode='heavy_10k')
        self.assertEqual(done['included'],5)
        self.assertEqual(done['duplicate_variations_filtered'],10)
        self.assertEqual((dataset/'alistair_validation.jsonl').read_text(), validation)
        self.assertEqual(done['prepared']['state'],'prepared')
        self.assertEqual(done['prepared']['context_requested'],10000)

    def test_quality_gate_blocks_repetition_and_copies(self):
        sentences=[
            'Vou priorizar os chamados críticos após confirmar quem está aguardando resposta.',
            'Precisarei esclarecer o prazo antes de prometer uma entrega ao grupo.',
            'A dependência foi identificada; proponho dividir a tarefa em duas partes.',
            'Reconheço o erro no inventário e vou apresentar a correção com sua origem.',
            'Posso reunir as alternativas, mas a decisão exige consentimento da entidade.',
            'O cenário mudou; a prioridade anterior deve ser reconsiderada à luz dos fatos.',
            'Há risco de conflito de versões, então verificarei qual arquivo é o vigente.',
            'A tarefa está incompleta: registrarei os pontos abertos e o responsável.',
            'Podemos simplificar a conversa sem apagar as incertezas ainda existentes.',
            'A evidência contradiz a hipótese; minha recomendação é rever o plano.']
        rows=[{'messages':[{'role':'user','content':f'Pedido {i}'},
                           {'role':'assistant','content':'Resposta original do treinamento '+str(i)}]}
              for i in range(10)]
        examples=[{'source_id':str(i),'category':('instrucao','raciocinio','personalidade','naturalidade')[i%4],
                   'user':f'Nova situação {i}',
                   'assistant':sentences[i],
                   'reason':'Ação diferenciada','confidence':0.85} for i in range(10)]
        passed=professor_moe.audit_proposal(examples,rows)
        self.assertTrue(passed['passed'],passed)
        bad=[dict(a) for a in examples]
        bad[1]['assistant']=bad[0]['assistant']
        rejected=professor_moe.audit_proposal(bad,rows)
        self.assertFalse(rejected['passed'])
        self.assertIn([1,2],rejected['near_duplicate_pairs'])
        bad=[dict(a) for a in examples]
        bad[0]['assistant']='Resposta original do treinamento 0'
        self.assertFalse(professor_moe.audit_proposal(bad,rows)['passed'])


class DurationContractRecoveryTests(unittest.TestCase):
    def _plan(self):
        return {'entity':'alistair','profile':'moderado','minutes':45,
                'reason':'Gerar exemplos de tomada de decisão com evidências verificáveis.',
                'examples':[
                    {'source_id':f'case:{i:06d}', 'category':'raciocinio',
                     'user':f'Como resolver o impasse {i}?',
                     'assistant':f'Proponho investigar a causa especifica do impasse {i}.',
                     'reason':'Mudança contextual observada no caso', 'confidence':0.7}
                    for i in range(3)]}

    def test_duration_mismatch_recovers_with_visible_policy(self):
        bad=self._plan()
        valid=professor_moe._validate_teacher_output(
            bad,entity='alistair',evidence_ids={f'case:{i:06d}' for i in range(3)})
        self.assertEqual(valid['profile'],'conservador')
        self.assertEqual(valid['minutes'],10)
        self.assertEqual(valid['duration_policy']['original_minutes'],'45')
        self.assertTrue(valid['duration_policy']['model_suggestion_rejected'])
        self.assertFalse(valid['duration_policy']['training_authorized'])
        self.assertEqual(len(valid['examples']),3)
        self.assertEqual(bad['minutes'],45)  # não altera o material original

    def test_no_repair_of_bad_entity_or_fabricated_source(self):
        bad=self._plan()
        bad['entity']='hoshino'
        with self.assertRaises(ValueError):
            professor_moe._validate_teacher_output(bad,entity='alistair',
                                                    evidence_ids={'case:000000','case:000001','case:000002'})
        bad=self._plan();bad['examples'][0]['source_id']='inventado'
        with self.assertRaises(ValueError):
            professor_moe._validate_teacher_output(bad,entity='alistair',
                                                    evidence_ids={'case:000000','case:000001','case:000002'})

    def test_json_schema_limits_source_ids_categories_and_minutes(self):
        rows=[{'source_id':'case:000001'},{'source_id':'case:000002'}]
        schema=professor_moe._response_schema('alistair',rows,heavy=True)
        self.assertEqual(schema['properties']['minutes']['enum'],[0,10,30])
        self.assertEqual(schema['properties']['examples']['minItems'],8)
        self.assertEqual(schema['properties']['examples']['items']['properties']['source_id']['enum'],
                         ['case:000001','case:000002'])
        self.assertFalse(schema['additionalProperties'])

    def test_raw_invalid_response_saved_private(self):
        with tempfile.TemporaryDirectory() as name:
            base=Path(name)
            path=professor_moe._save_invalid_output(base,'a'*16,'{not json}',ValueError('JSON invalido'))
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertIn('{not json}',path.read_text())
            self.assertNotIn('datasets-importados',str(path))


class HumanExampleCurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.job=professor_moe.draft_reference_set(self.home,'hoshino')
        self.sid=self.job['proposal_data']['examples'][0]['source_id']

    def decide(self,decision='approved',note='',reuse=True,digest=None):
        return professor_moe.review_examples(self.home,self.job['id'],self.sid,decision,note,
            confirm=True,as_reference=reuse,expected_hash=digest or self.job['example_hashes'][self.sid])

    def test_reference_drafts_are_pending_not_training_and_idempotent(self):
        self.assertEqual(professor_moe.draft_reference_set(self.home,'hoshino')['id'],self.job['id'])
        self.assertFalse(self.job['training_started'])
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino'),[])
        with self.assertRaises(RuntimeError):professor_moe.approved_export(self.home,self.job['id'],
            [e['source_id'] for e in self.job['proposal_data']['examples']][:2],'not-a-dataset')

    def test_assisted_curation_requires_authorization_and_preserves_reviewer(self):
        args=(self.home,self.job['id'],self.sid,'approved','Referência específica e sem memória inventada.')
        kwargs=dict(confirm=True,as_reference=True,expected_hash=self.job['example_hashes'][self.sid],reviewer='codex_assisted')
        with self.assertRaises(ValueError):professor_moe.review_examples(*args,**kwargs)
        result=professor_moe.review_examples(*args,**kwargs,authorization_reference='user:20261014:curadoria-autorizada')
        self.assertEqual(result['review']['reviewer'],'codex_assisted')
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino')[0]['reviewer'],'codex_assisted')

    def test_case_relevance_selects_memory_reference_before_recent_casual(self):
        for ex in self.job['proposal_data']['examples']:
            professor_moe.review_examples(self.home,self.job['id'],ex['source_id'],'approved',
                confirm=True,as_reference=True,expected_hash=self.job['example_hashes'][ex['source_id']])
        refs=professor_moe.approved_references(self.home,'hoshino',case=dict(category='memoria',intent='Lembrança incerta e autoria'))
        self.assertEqual(refs[0]['category'],'memoria')

    def test_pending_is_not_promoted_by_assisted_selection(self):
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino',case=dict(category='memoria')),[])

    def test_decision_survives_reload_and_is_isolated_to_entity(self):
        self.decide()
        result=professor_moe.approved_references(self.home,'hoshino')
        self.assertEqual(len(result),1)
        self.assertEqual(professor_moe.approved_references(self.home,'lilith'),[])
        ex=self.job['proposal_data']['examples'][0]
        self.assertEqual(professor_moe.human_decision(professor_moe.detail(self.home,self.job['id'])['proposal_data'],ex),'approved')

    def test_reference_requires_explicit_reuse_choice(self):
        self.decide(reuse=False)
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino'),[])

    def test_reference_survives_more_than_fifty_new_jobs(self):
        self.decide(note='Não tornar bordão obrigatório.')
        for index in range(55):
            identifier=f'{index:016x}'
            professor_moe._write(professor_moe.job_file(self.home,identifier),dict(id=identifier,
                entity='lilith',state='prepared',created=professor_moe.stamp()))
        self.assertNotIn(self.job['id'],[j['id'] for j in professor_moe.jobs(self.home)])
        self.assertEqual(professor_moe.draft_reference_set(self.home,'hoshino')['id'],self.job['id'])
        references=professor_moe.approved_references(self.home,'hoshino')
        self.assertEqual(references[0]['human_feedback'],'Não tornar bordão obrigatório.')

    def test_pending_cancellation_cannot_be_discarded(self):
        path=professor_moe.job_file(self.home,self.job['id']);job=json.loads(path.read_text())
        job['state']='cancel_requested';professor_moe._write(path,job)
        with self.assertRaisesRegex(RuntimeError,'em uso'):
            professor_moe.discard_job(self.home,self.job['id'],confirm=True)
        self.assertTrue((self.home/professor_moe.ROOT_REL/'propostas'/f"{self.job['id']}.json").is_file())

    def test_rejection_requires_reason_and_preserves_text(self):
        with self.assertRaises(ValueError):self.decide('rejected')
        self.decide('rejected','Humor exagerado.')
        after=professor_moe.detail(self.home,self.job['id'])
        self.assertEqual(after['proposal_data']['examples'],self.job['proposal_data']['examples'])
        self.assertEqual(after['proposal_data']['human_reviews'][self.sid]['decision'],'rejected')
        self.assertTrue(list((self.home/'professor-moe-35b/arquivo-curadoria').glob('*.json')))
        feedback=professor_moe.curation_feedback(self.home,'hoshino')
        self.assertEqual(feedback[0]['note'],'Humor exagerado.')
        self.assertEqual(professor_moe.curation_feedback(self.home,'lilith'),[])
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino'),[])

    def test_changed_content_invalidates_old_approval_and_stale_ui(self):
        self.decide()
        path=self.home/'professor-moe-35b/propostas'/f"{self.job['id']}.json"
        proposal=json.loads(path.read_text());proposal['examples'][0]['reason']='Outra lição, outro conteúdo.'
        professor_moe._write(path,proposal)
        self.assertEqual(professor_moe.approved_references(self.home,'hoshino'),[])
        with self.assertRaises(RuntimeError):self.decide()

    def test_unknown_example_confirmation_and_secret_redaction(self):
        with self.assertRaises(PermissionError):professor_moe.review_examples(self.home,self.job['id'],self.sid,'approved')
        with self.assertRaises(ValueError):professor_moe.review_examples(self.home,self.job['id'],'foreign','approved',confirm=True)
        secret='unit-test-secret-not-for-logs'
        with patch.dict(os.environ,{'ELEVENLABS_API_KEY':secret}):self.decide('rejected','não guardar '+secret)
        self.assertNotIn(secret,professor_moe.detail(self.home,self.job['id'])['proposal_data']['human_reviews'][self.sid]['note'])

    def test_manual_and_automatic_exports_cannot_override_rejection(self):
        from laboratorio.rotina_noturna import configure
        configure(self.home,{'confirm':True,'settings':{'automatic_data_approval':True}})
        self.decide('rejected','Sem naturalidade.')
        path=self.home/'professor-moe-35b/propostas'/f"{self.job['id']}.json"
        proposal=json.loads(path.read_text());proposal.pop('purpose');proposal['status']='PROPOSTA_NAO_APROVADA'
        professor_moe._write(path,proposal)
        ids=[e['source_id'] for e in proposal['examples']][:2]
        with self.assertRaisesRegex(ValueError,'reprovado'):professor_moe.approved_export(self.home,self.job['id'],ids,'missing')
        from laboratorio.rotina_noturna import approve_data
        with self.assertRaisesRegex(RuntimeError,'reprovação humana'):approve_data(self.home,self.job['id'],'missing')

    def test_night_cannot_treat_teacher_scores_as_human_curation(self):
        from laboratorio.rotina_noturna import configure
        configure(self.home,{'confirm':True,'settings':{'automatic_data_approval':True}})
        from laboratorio.rotina_noturna import approve_data
        path=self.home/'professor-moe-35b/propostas'/f"{self.job['id']}.json"
        proposal=json.loads(path.read_text());proposal['requires_human_curation']=True
        professor_moe._write(path,proposal)
        with patch.object(professor_moe,'approved_export') as export:
            with self.assertRaisesRegex(RuntimeError,'Curadoria humana'):
                approve_data(self.home,self.job['id'],'missing')
            export.assert_not_called()

    def test_new_generation_cannot_be_implicitly_approved_by_cli(self):
        path=self.home/'professor-moe-35b/propostas'/f"{self.job['id']}.json"
        proposal=json.loads(path.read_text());proposal.pop('purpose')
        proposal.update(status='PROPOSTA_NAO_APROVADA',generation_version='v1.12')
        professor_moe._write(path,proposal)
        ids=[e['source_id'] for e in proposal['examples']][:2]
        with self.assertRaisesRegex(ValueError,'pendente'):
            professor_moe.approved_export(self.home,self.job['id'],ids,'missing')

    def test_loopback_api_persists_decision_and_rejects_missing_token(self):
        import threading
        from http.server import ThreadingHTTPServer
        from types import SimpleNamespace
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from laboratorio import painel
        ready=threading.Event();holder={};host='127.0.0.1:8788'
        def server_fixture(address,handler):
            self.assertEqual(address,('127.0.0.1',8788))
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            holder['server']=server;ready.set();return server
        # HTTP real, temporário e no mesmo processo: guardas offline permitem
        # somente listeners próprios/efêmeros. Não abrir a Central ou relaxar guardas.
        with patch.object(painel,'ThreadingHTTPServer',side_effect=server_fixture):
          thread=threading.Thread(target=painel.serve,args=(SimpleNamespace(home=self.home,project=self.home),8788),daemon=True)
          thread.start()
          try:
            self.assertTrue(ready.wait(3));port=holder['server'].server_address[1]
            req=Request(f'http://127.0.0.1:{port}/api/bootstrap',headers={'Host':host})
            with urlopen(req,timeout=2) as answer:boot=json.load(answer)
            body=dict(id=self.job['id'],source_id=self.sid,decision='rejected',note='Pouco natural.',
                      expected_hash=self.job['example_hashes'][self.sid],confirm=True)
            url=f'http://127.0.0.1:{port}/api/professor-moe/review-example'
            req=Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Host':host})
            with self.assertRaises(HTTPError) as error:urlopen(req,timeout=2)
            self.assertEqual(error.exception.code,403)
            req.add_header('X-Lab-Token',boot['csrf'])
            with urlopen(req,timeout=2) as answer:result=json.load(answer)
            self.assertFalse(result['result']['training_started'])
            req=Request(f'http://127.0.0.1:{port}/api/professor-moe/detail?id={self.job["id"]}',headers={'Host':host})
            with urlopen(req,timeout=2) as answer:
                after=json.load(answer)
            self.assertEqual(after['proposal_data']['human_reviews'][self.sid]['decision'],'rejected')
          finally:
            if holder.get('server'):holder['server'].shutdown()
            thread.join(timeout=3);self.assertFalse(thread.is_alive())
