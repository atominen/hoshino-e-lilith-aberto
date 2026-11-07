"""Atividade, projeções e instalação: offline, sem mentes/modelos reais."""
import asyncio
import hashlib
import importlib.util
import io
import json
import statistics
import tarfile
import tempfile
import time
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import config
import main
from core import activity_context as ac, cognition, state_file, diagnostics
from mind import emotions

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


class Activity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.json';self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(config,'ESTADO_MENTE',str(self.path)))
        self.stack.enter_context(patch.object(config,'ENTIDADE_ID','hoshino'))
        self.events=[];self.stack.enter_context(patch.object(diagnostics,'emit',side_effect=lambda *a,**k:self.events.append((a,k))))
    def observe(self,**values):
        snapshot=dict(sessionId='session-a',connected=True,verified=True,health=20,food=20,
                      nearbyEntities=[],inventory=[{'name':'oak_log','count':3}],position={'x':1,'y':64,'z':2})|values
        self.assertTrue(ac.observe_minecraft(snapshot,session_id=snapshot['sessionId'],request_id='mc-a',now=100))
    def build(self,**values):return ac.build(text='Minecraft',names=['minecraft_estado','minecraft_coletar'],now=101,**values)
    def test_fresh_origin_grounding_and_budget(self):
        self.observe();p,b=self.build(goal='pegar madeira',participant={'id':'gustavo','nome':'Gustavo'})
        self.assertEqual(p['observation']['origin'],'minecraft_rpc');self.assertEqual(p['observation']['confidence'],1.)
        self.assertEqual(p['participants'][0]['author_id'],'gustavo');self.assertEqual(p['salience']['reason'],'goal_before_opportunity')
        self.assertLessEqual(len(b),ac.MAX_CONTEXT_CHARS);self.assertIn('mc-a',b)
    def test_expired_future_and_missing_are_unknown(self):
        self.observe()
        for now in (90,109,999):
            p,_=ac.build(text='Minecraft',now=now)
            self.assertEqual(p['observation']['grounding'],'unknown')
    def test_foreign_session_and_older_probe_refused(self):
        self.observe()
        self.assertFalse(ac.observe_minecraft({'sessionId':'b'},session_id='a',request_id='r'))
        ac.observe_minecraft({'sessionId':'old'},session_id='old',request_id='r',now=90)
        self.assertEqual(ac._read()['minecraft']['session_id'],'session-a')
    def test_threat_is_inference_not_observation_of_intent(self):
        self.observe(nearbyEntities=[{'name':'creeper','distance':3,'id':44}])
        p,_=self.build(goal='pegar madeira')
        self.assertEqual(p['salience']['action'],'protect_then_replan')
        self.assertEqual(p['salience']['grounding'],'inference_from_observation')
        self.assertEqual(p['goal'],'pegar madeira')
    def test_occluded_hostile_does_not_block_work_but_unknown_visibility_still_protects(self):
        for visibility,expected in ((False,'next_goal_step_or_wait'),(True,'protect_then_replan'),
                                    (None,'protect_then_replan'),('false','protect_then_replan')):
            self.observe(nearbyEntities=[{'name':'skeleton','distance':5,'id':44,'lineOfSight':visibility}])
            p,_=self.build(goal='fabricar picareta')
            self.assertEqual(p['salience']['action'],expected)
    def test_low_health_and_unknown_are_distinct(self):
        self.observe(health=4);p,_=self.build();self.assertEqual(p['salience']['reason'],'low_health')
        self.observe(health=None);p,_=self.build();self.assertNotEqual(p['salience']['reason'],'low_health')
    def test_transition_does_not_leak_minecraft_or_reset_identity(self):
        state_file.update(self.path,lambda d:d.update(emocoes={'afeto':{'i':.6,'em':'2026-10-07T10:00:00'}}))
        self.observe();self.build()
        p,b=ac.build(text='como você está?',now=102)
        self.assertEqual(p['activity'],'conversation');self.assertNotIn('session-a',b)
        self.assertIn('afeto',state_file.read(self.path)['emocoes'])
    def test_four_modes_not_four_personalities(self):
        examples=[('Minecraft pegue madeira',['minecraft_coletar'],'integrated_agent'),
                  ('Minecraft não apenas planeje: execute e confira o inventário',['minecraft_coletar'],'integrated_agent'),
                  ('Minecraft não só sugira: colete recursos',['minecraft_coletar'],'integrated_agent'),
                  ('Minecraft não execute: apenas planeje',['minecraft_coletar'],'copilot'),
                  ('Minecraft me oriente enquanto eu jogo',['minecraft_estado'],'copilot'),
                  ('planeje uma estratégia Minecraft',['minecraft_estado'],'strategist'),
                  ('abra uma janela',['abrir_aplicativo'],'tool_executor')]
        for text,names,mode in examples:self.assertEqual(ac.classify(text,names)[1],mode)
    def test_available_tools_not_current_activity(self):
        self.observe()
        p,b=ac.build(text='Oi, como você está?',names=['minecraft_estado','minecraft_coletar','abrir_aplicativo'],now=101)
        self.assertEqual(p['activity'],'conversation');self.assertNotIn('session-a',b)
        p,b=ac.build(text='abra o Spotify',names=['minecraft_estado','abrir_aplicativo'],now=101)
        self.assertEqual(p['activity'],'media');self.assertNotIn('session-a',b)
    def test_malformed_large_snapshot_and_participant_have_hard_budget(self):
        self.observe(position={'x':'x'*50000},inventory=[{'name':'x'*50000}]*100,nearbyEntities=[{'name':'x'*50000,'position':{'x':'x'*50000}}]*100)
        p,b=self.build(participant={'id':'x'*50000,'nome':'x'*50000},channel='x'*50000,task_id='x'*50000)
        self.assertLessEqual(len(b),ac.MAX_CONTEXT_CHARS)
        self.assertEqual(ac._read()['current'],p)
    def test_repeat_failure_requires_other_approach(self):
        for at in (100,101):ac.record_result('scope','minecraft_coletar',{'bloco':'oak_log'},{'status':'error','mutates':True},now=at)
        self.assertEqual(ac.retry_block('scope','minecraft_coletar',{'bloco':'oak_log'},now=102),'repeated_failure_change_approach')
        self.assertEqual(ac.retry_block('scope','minecraft_coletar',{'bloco':'birch_log'},now=102),'')
    def test_uncertain_survives_restart_time_scope_and_history_truncation(self):
        ac.record_result('old','execute_command',{'comando':'operation'},{'status':'uncertain','mutates':True},now=100)
        for n in range(100):ac.record_result('new','read',{'n':n},{'status':'success'},now=200+n)
        self.assertEqual(len(ac._read()['attempts']),32)
        self.assertEqual(ac.retry_block('new','execute_command',{'comando':'operation'},now=99999),'uncertain_effect_requires_review')
        self.assertFalse(ac.view(state_file.read(self.path),entity='hoshino',now=99999)['automatic_resume'])
    def test_uncertain_reviewed_in_job_bus_no_longer_blocks(self):
        from core import job_bus
        args={'nome':'crafting_table'}
        ac.record_result('mc','minecraft_colocar_bloco',args,{'status':'uncertain','mutates':True,'receipt_id':'tool-x'},now=100)
        with patch.object(job_bus,'get',return_value={'details':{'resolved':False}}):
            self.assertEqual(ac.retry_block('mc','minecraft_colocar_bloco',args,now=101),'uncertain_effect_requires_review')
        with patch.object(job_bus,'get',return_value={'details':{'resolved':True}}):
            self.assertEqual(ac.retry_block('mc','minecraft_colocar_bloco',args,now=101),'')
        with patch.object(job_bus,'get',side_effect=RuntimeError('db')):  # sem conferir: continua incerto
            self.assertEqual(ac.retry_block('mc','minecraft_colocar_bloco',args,now=101),'uncertain_effect_requires_review')
    def test_arguments_and_secrets_not_stored(self):
        ac.record_result('s','execute_command',{'api_key':'SENSITIVE_TEST_MARKER'},{'status':'error','output':'SENSITIVE_TEST_MARKER'})
        self.assertNotIn('SENSITIVE_TEST_MARKER',self.path.read_text());self.assertNotIn('api_key',self.path.read_text())
    def test_three_entities_separated(self):
        for entity in ('hoshino','lilith','alistair'):
            with patch.object(config,'ENTIDADE_ID',entity),patch.object(config,'ESTADO_MENTE',str(self.path.parent/(entity+'.json'))):
                p,_=ac.build(text='oi',participant={'id':'gustavo'},now=100)
                self.assertEqual(p['entity'],entity)
        self.assertFalse(ac.view(json.loads((self.path.parent/'lilith.json').read_text()),entity='hoshino')['available'])
    def test_correction_invalidates_projection_not_emotions(self):
        self.observe();self.build();ac.invalidate('superseded')
        self.assertNotIn('current',ac._read());self.assertEqual(ac._read()['interruption']['reason'],'superseded')
    def test_corrupt_state_preserved_and_does_not_crash_builder(self):
        self.path.write_text('broken')
        p,b=ac.build(text='oi',now=100)
        self.assertEqual(self.path.read_text(),'broken');self.assertEqual(p['activity'],'conversation')
    def test_context_and_projection_do_not_write_memory_or_call_llm(self):
        with patch.object(main.dispatch,'executar_resultado',side_effect=AssertionError('effect forbidden')),patch.object(main.requests,'post',side_effect=AssertionError('network forbidden')):
            self.observe();self.build();ac.invalidate('stop')
        self.assertFalse(list(self.path.parent.glob('*.db')))
    def test_bounded_load_benchmark_fixture_not_llm(self):
        self.observe();samples=[]
        for n in range(100):
            start=time.perf_counter();p,b=self.build(goal='coletar madeira');samples.append((time.perf_counter()-start)*1000)
        samples.sort();print(json.dumps({'fixture_activity_cycles':100,'p50_ms':round(statistics.median(samples),3),'p95_ms':round(samples[94],3),'context_chars':len(b),'state_bytes':self.path.stat().st_size,'real_llm':False}))
        self.assertLess(self.path.stat().st_size,20000)


class ActionGates(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app=object.__new__(main.InterfaceHoshino);self.app.sys_log=Mock()
        self.app._executar_mutacao_protegida=AsyncMock(return_value={'ok':True,'status':'success','mutates':True,'output':'receipt'})
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(config,'ESTADO_MENTE',str(Path(self.tmp.name)/'state.json')))
        self.stack.enter_context(patch.object(diagnostics,'emit'))
        ac.observe_minecraft({'sessionId':'a','connected':True,'verified':True,'health':20},session_id='a',request_id='r')
        self.frame=cognition.criar_frame('Minecraft')
        self.frame.activity_scope='scope';self.frame.activity_name='minecraft';self.frame.activity_mode='integrated_agent'
    async def execute(self,names,**kwargs):
        calls=[{'function':{'name':n,'arguments':a}} for n,a in names]
        return await self.app._executar_chamadas_da_etapa(calls,self.frame,1,set(),**kwargs)
    async def test_copilot_does_not_execute(self):
        self.frame.activity_mode='copilot';result=await self.execute([('minecraft_coletar',{'bloco':'oak_log'})])
        self.app._executar_mutacao_protegida.assert_not_awaited();self.assertFalse(result[0][2]['ok'])
    async def test_starting_bridge_does_not_require_an_already_connected_bot(self):
        ac.observe_minecraft({'sessionId':'offline','connected':False,'verified':False},session_id='offline',request_id='offline')
        result=await self.execute([('minecraft_iniciar_ponte',{})])
        self.app._executar_mutacao_protegida.assert_awaited_once()
        self.assertTrue(result[0][2]['ok'])
    async def test_one_mutation_per_observation_cycle(self):
        result=await self.execute([('minecraft_coletar',{'bloco':'oak_log'}),('minecraft_craft',{'item':'crafting_table'})])
        self.app._executar_mutacao_protegida.assert_awaited_once();self.assertTrue(result[0][2]['ok']);self.assertFalse(result[1][2]['ok'])
    async def test_threat_blocks_collection(self):
        ac.observe_minecraft({'sessionId':'a','connected':True,'verified':True,'health':3},session_id='a',request_id='r')
        result=await self.execute([('minecraft_coletar',{'bloco':'oak_log'})])
        self.app._executar_mutacao_protegida.assert_not_awaited();self.assertIn('Risco observado',result[0][2]['output'])
    async def test_stop_priority_cancel_never_starts_effect(self):
        with self.assertRaises(main.TurnoCancelado):await self.execute([('minecraft_coletar',{'bloco':'oak_log'})],cancelar=lambda:True)
        self.app._executar_mutacao_protegida.assert_not_awaited()
    async def test_uncertain_across_turns_blocks_replay(self):
        ac.record_result('prior','minecraft_coletar',{'bloco':'oak_log'},{'status':'uncertain','mutates':True})
        result=await self.execute([('minecraft_coletar',{'bloco':'oak_log'})])
        self.assertTrue(result[0][2]['outcome_uncertain']);self.app._executar_mutacao_protegida.assert_not_awaited()
    async def test_threat_rechecked_after_action_lock_wait(self):
        lock=self.app._obter_trava_acao();await lock.acquire()
        job=asyncio.create_task(self.execute([('minecraft_coletar',{'bloco':'oak_log'})]))
        await asyncio.sleep(0)
        ac.observe_minecraft({'sessionId':'a','connected':True,'verified':True,'health':3},session_id='a',request_id='new')
        lock.release();result=await asyncio.wait_for(job,2)
        self.app._executar_mutacao_protegida.assert_not_awaited();self.assertFalse(result[0][2]['ok'])
    async def test_goal_attempt_does_not_learn_success_from_optimistic_text(self):
        self.app.prompt_sistema='Eu sou Hoshino';self.app.contexto_do_turno=Mock(return_value='context')
        self.app.ciclo_de_ferramentas=AsyncMock(return_value=('Consegui tudo!', ['minecraft_estado']))
        with patch.object(main.strategies,'registrar_tentativa',return_value='t'),patch.object(main.strategies,'bloco_para_prompt',return_value=''),\
             patch.object(main.strategies,'concluir_tentativa') as conclude,patch.object(main.affect,'apreciar'),patch.object(main.prompting,'prompt_por_intencao',return_value='prompt'):
            await self.app.retomar_objetivo({'tipo':'retomar_objetivo','alvo':{'goal_id':'g','descricao':'Minecraft pegar madeira'}})
            self.assertIs(conclude.call_args.args[1],False)


class AttemptEvidence(unittest.TestCase):
    def test_read_incidental_is_not_requested_action(self):
        f=cognition.criar_frame('Minecraft pegue madeira');f.ferramenta_sugerida='minecraft_coletar'
        cognition.registrar_ferramenta(f,'minecraft_estado',{'ok':True,'status':'success','verified':True,'output':'state'})
        self.assertFalse(cognition.tentativa_verificada(f))
    def test_verified_receipt_required_not_only_tool_or_text(self):
        for verified in (False,True):
            f=cognition.criar_frame('x');f.iniciativa_requerida=False;f.ferramenta_sugerida=''
            cognition.registrar_ferramenta(f,'workspace',{'ok':True,'status':'success','verified':verified,'output':'Consegui'})
            self.assertIs(cognition.tentativa_verificada(f),verified)


class EmotionAndStyle(unittest.TestCase):
    def test_real_expression_decay_no_provider_modification(self):
        now=datetime(2026,10,7,10,0)
        profile=emotions.visual_profile({'emocoes':{'medo':{'i':.8,'em':now.isoformat()}}},agora=now)
        self.assertEqual(profile['dominant'],'medo');self.assertFalse(profile['voice_modulation_applied'])
        self.assertIsNone(emotions.visual_profile({'emocoes':{'medo':{'i':.8,'em':now.isoformat()}}},agora=now+timedelta(hours=2))['dominant'])
    def test_unknown_not_fake_happy(self):self.assertFalse(emotions.visual_profile(None)['available'])
    def test_corrupt_emotions_do_not_break_ui(self):
        for raw in (None,[],0,'invalid'):
            self.assertFalse(emotions.visual_profile({'emocoes':raw})['available'])
    def test_observed_threat_uses_existing_affect_once_not_alistair_or_hypothesis(self):
        from mind import affect
        p={'activity':'minecraft','observation':{'session_id':'s','origin':'minecraft_rpc','grounding':'tool_confirmed'},
           'salience':{'action':'protect_then_replan','reason':'low_health'}}
        with patch.object(config,'ENTIDADE_ID','hoshino'),patch.object(affect,'apreciar') as appreciate:
            self.assertTrue(affect.atividade_observada(p));self.assertFalse(affect.atividade_observada(p,p))
            appreciate.assert_called_once();self.assertEqual(appreciate.call_args.args[0],'risco_observado')
            for entity in ('lilith','alistair'):
                with patch.object(config,'ENTIDADE_ID',entity):
                    self.assertIs(affect.atividade_observada(p),entity=='lilith')
            fake=dict(p,observation={'grounding':'hypothesis','origin':'chat'})
            self.assertFalse(affect.atividade_observada(fake))
    def test_new_emotions_existing_catalog_not_alistair_pipeline(self):
        self.assertTrue({'medo','amor','desejo'}<=emotions.EMOCOES.keys());self.assertLess(emotions.GATILHOS['amizade_avancou'][-1][1],.1)
    def test_style_first_person_and_brief_no_forced_response_truncation(self):
        from core import prompting
        self.assertIn('1–3 frases',prompting.ESCRITA);self.assertIn('primeira pessoa', (ROOT/'app/alistair_runner.py').read_text())
        self.assertIn('admito meu limite',(ROOT/'app/alistair_runner.py').read_text())


class InstallerExport(unittest.TestCase):
    def setUp(self):
        self.installer=load('installer',Path('instalar.py'));self.exporter=load('exporter',Path('scripts/exportar_codigo_privado.py'))
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_default_plan_has_no_install_download_start(self):
        with patch.object(self.installer.subprocess,'run',side_effect=AssertionError('effect forbidden')):
            self.assertFalse(self.installer.plan('principal',self.root)['auto_start'])
    def test_archive_traversal_symlink_and_duplicate_refused(self):
        for name in ('/etc/evil','alistair_pc2/../../evil','other/file'):
            with self.assertRaises(ValueError):self.installer.validate_members([tarfile.TarInfo(name)])
        m=tarfile.TarInfo('alistair_pc2/file')
        with self.assertRaises(ValueError):self.installer.validate_members([m,m])
        link=tarfile.TarInfo('alistair_pc2/link');link.type=tarfile.SYMTYPE;link.linkname='/tmp/evil'
        with self.assertRaises(ValueError):self.installer.validate_members([link])
    def test_wrong_hash_and_existing_destination_refused(self):
        archive=self.root/'a.tar';archive.write_bytes(b'fixture')
        with self.assertRaises(ValueError):self.installer.install_pc2(self.root/'target',archive,'0'*64)
        target=self.root/'target';target.mkdir()
        with self.assertRaises(ValueError):self.installer.install_pc2(target,archive,self.installer.digest(archive))
    def test_atomic_move_never_replaces_concurrently_created_destination(self):
        source=self.root/'source';source.mkdir();(source/'file').write_text('source')
        dest=self.root/'target';dest.mkdir()
        with self.assertRaises(ValueError):self.installer.move_without_replace(source,dest)
        self.assertTrue(source.is_dir());self.assertEqual(list(dest.iterdir()),[])
        final=self.root/'new';self.installer.move_without_replace(source,final)
        self.assertEqual((final/'file').read_text(),'source')
    def test_valid_package_install_does_not_start_service(self):
        content=b'#!/bin/sh\n# fixture, no model execution\n';data={'package':'alistair_pc2','model':'alistair-qwen3-4b:latest',
            'credentials_included':False,'entity_minds_included':False,'files':{'iniciar.sh':{'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}}}
        archive=self.root/'valid.tar'
        with tarfile.open(archive,'w') as tar:
            for name,payload in [('iniciar.sh',content),('manifesto.json',json.dumps(data).encode())]:
                member=tarfile.TarInfo('alistair_pc2/'+name);member.size=len(payload);tar.addfile(member,io.BytesIO(payload))
        with patch.object(self.installer.subprocess,'run',side_effect=AssertionError('service forbidden')):
            result=self.installer.install_pc2(self.root/'target',archive,self.installer.digest(archive))
        self.assertTrue(result['integrity_verified']);self.assertFalse(result['hardware_validated']);self.assertFalse(result['auto_start'])
    def test_space_pressure_refuses_before_extract(self):
        archive=self.root/'valid.tar'
        with tarfile.open(archive,'w') as tar:tar.addfile(tarfile.TarInfo('alistair_pc2'))
        with patch.object(self.installer.shutil,'disk_usage',return_value=Mock(free=1)):
            with self.assertRaises(OSError):self.installer.plan('pc2',self.root/'target',archive)
        self.assertFalse((self.root/'target').exists())
    def test_export_excludes_mind_keys_models_and_evolved_identity(self):
        for name in ('app/x.py','app/runtime/log.py','entidades/hoshino/identity/self_model.json','compartilhado/modelos/weights.py','discord.env'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PRIVATE_TEST_MARKER' if name!='app/x.py' else 'print("source")')
        result=self.exporter.export(self.root,self.root/'export')
        self.assertFalse(result['minds_exported'])
        combined=''.join(p.read_text() for p in (self.root/'export').rglob('*') if p.is_file())
        self.assertNotIn('PRIVATE_TEST_MARKER',combined)
        self.assertFalse((self.root/'export/entidades/hoshino/identity/self_model.json').exists())
        self.assertTrue((self.root/'export/entidades/hoshino/identity/self_model.json.example').is_file())
    def test_secret_literal_blocks_export_without_printing_secret(self):
        p=self.root/'app/x.py';p.parent.mkdir();p.write_text('api_key="'+('x'*30)+'"')
        with self.assertRaises(ValueError) as e:self.exporter.export(self.root,self.root/'export')
        self.assertNotIn('x'*30,str(e.exception));self.assertFalse((self.root/'export').exists())


if __name__=='__main__':unittest.main(verbosity=2)
