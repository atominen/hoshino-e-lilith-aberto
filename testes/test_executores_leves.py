"""Executores/Alistair: sem modelos reais, GPU, quota, rede ou mente real."""
import asyncio
import contextlib
import importlib.util
import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import config
from core import resource_manager as rm, gpu_metrics, gpu_resource, ollama_lifecycle
from core import resource_profiles as profiles
from alistair_runner import Alistair

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024**3
BASE = 'http://127.0.0.1:11435'
LIGHT = 'hoshino-qwen2.5-7b:latest'
POLICY = dict(margin_bytes=768*1024**2, concurrency_validated=False, max_compute=2,
              max_utilization=55, sticky_seconds=90, interactive_grace_seconds=0,
              ram_margin_bytes=2*GIB)


def metrics(**kwargs):
    return dict(known=True, stable=True, total_bytes=8*GIB, used_bytes=0,
                utilization=0, observed_at=time.time(), **kwargs) if not kwargs else {**metrics(), **kwargs}


def response(data):
    return SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)


def original_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    # dataclass usa sys.modules para resolver anotações.
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='executor-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = self.root/'settings'
        self.settings.mkdir()
        self.storage = self.root/'models'
        self.events = []
        self.current = metrics()
        for obj, name, value in [(config, 'ENTITY_CONFIG_DIR', self.settings),
                (config,'RAIZ',str(self.root)),
                (config, 'OLLAMA_MODELS_DIR', str(self.storage)), (config, 'ENTIDADE_ID', 'hoshino'),
                (config, 'OLLAMA_URL', BASE+'/api/chat'), (config, 'MODEL_NAME', 'principal9b:latest'),
                (config, 'NUM_CTX', 16384), (rm, 'DB_PATH', self.root/'resource.db'),
                (rm, '_profile_controller', profiles.Controller()),
                (rm, 'LOCK_DIR', self.root/'locks')]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        for obj, name, kwargs in [(gpu_metrics, 'snapshot', dict(side_effect=lambda: {**self.current, 'observed_at':time.time()})),
                (gpu_metrics, 'ram_available', dict(return_value=31*GIB)),
                (rm, 'gpu_policy', dict(return_value=dict(POLICY))),
                (rm.diagnostics, 'emit', dict(side_effect=lambda *a, **k:self.events.append((a,k))))]:
            p = patch.object(obj, name, **kwargs); p.start(); self.addCleanup(p.stop)
        self.configure()

    def configure(self, entity='hoshino'):
        (self.settings/'executores.json').write_text(json.dumps(dict(schema=1, scope_frozen=True,
            light=dict(model=entity+'-qwen2.5-7b:latest', source='qwen2.5:7b-instruct-q4_K_M'))))

    def catalog(self):
        return [dict(e, installed=True, model_key=BASE+'|'+e['model']) for e in rm.executor_catalog()]

    def state(self, **overrides):
        return dict(metrics=metrics(), policy=dict(POLICY), compute=[], queue=[], residency=[], **overrides) if not overrides else {**self.state(), **overrides}

    def choose(self, **kwargs):
        return rm.assess_executor(self.catalog(), complexity='simple', priority=1,
                                  state=self.state(), ram=31*GIB, **kwargs)[0]

    def test_cold_simple_uses_light_not_another_manager(self):
        self.assertEqual(self.choose().model, LIGHT)
        self.assertEqual(self.choose().tier, 'light')

    def test_temporary_4b_light_uses_entity_version_not_alistair_identity(self):
        from core import neural9b_modes as modes
        for entity in ('hoshino','lilith'):
            config.ENTIDADE_ID=entity
            (self.settings/'executores.json').write_text(json.dumps(dict(schema=1,scope_frozen=True,
                light=dict(model=entity+'-qwen3.5-4b:latest',source='Qwen3.5-4B-local-original'))))
            pinned=entity+'-qwen3.5-4b-original-fixture:latest'
            with patch.object(modes,'runtime_alias',return_value=pinned) as resolve:
                catalog=self.catalog()
            self.assertEqual(len(catalog),2)
            light=catalog[1]
            self.assertEqual((light['model'],light['tier'],light['num_ctx']), (pinned,'light',8192))
            self.assertEqual(light['vram_bytes'],4*GIB)
            self.assertEqual(light['gpu_layers'],-1)
            self.assertTrue(light['supports_tools'])
            resolve.assert_called_once_with(config.RAIZ,entity,'qwen35-4b')

    def test_version_policy_exposes_only_4b_9b_and_rejects_removed_selection(self):
        from core import neural9b_modes as modes
        from laboratorio import recuperacao_modelos as recovery
        p=modes.path(self.root);p.parent.mkdir(parents=True)
        p.write_text(json.dumps(dict(hl_families=['qwen35-9b','qwen35-4b'])))
        self.assertEqual(set(modes.enabled_families(self.root,'lilith')),{'qwen35-9b','qwen35-4b'})
        self.assertEqual(modes.enabled_families(self.root,'alistair'),{'alistair-4b'})
        catalog=recovery.versions_catalog(self.root/'lab',self.root,'lilith')
        self.assertEqual({x['model_id'] for x in catalog['families']},{'qwen35-9b','qwen35-4b'})
        self.assertEqual(recovery.alias('hoshino','qwen35-4b'),'hoshino-qwen3.5-4b:latest')
        with self.assertRaises(ValueError):recovery.alias('alistair','qwen35-4b')
        p.write_text(json.dumps(dict(hl_families=['qwen35-9b','qwen35-4b'],executor_versions={
            'lilith':dict(primary='qwen25-7b',models={})})))
        with self.assertRaises(ValueError):modes.read_document(self.root)

    def yi_fixture(self, entity='hoshino'):
        from core import neural9b_modes as modes, yi_companion as yi
        selected=dict(alias=entity+'-yi-6b-original-test:latest',kind='original',
                      source_sha256='a'*64,manifest_sha256='b'*64)
        report=dict(schema=1,scope='basic_text_only',protocol='ollama_chat',entity=entity,model=selected['alias'],kind='original',
            source_sha256=selected['source_sha256'],manifest_sha256=selected['manifest_sha256'],passed=True,
            checks=[dict(id=i,passed=True,done=True,done_reason='stop') for i in sorted(yi.CASE_IDS)],
            physical=dict(context=4096,layers=-1,backend='gpu',pressure=[],metrics_known_stable=True,resident_vram_bytes=4*GIB),
            cleanup=dict(unload_confirmed=True,lease_released=True),semantic_review=dict(completed=True,passed=True))
        path=self.root/'compartilhado/runtime/ensaios/yi-fixture'/f'{entity}.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        self.configure(entity)
        for name, callback in [('runtime_alias',lambda root,e,m:selected['alias'] if e==entity and m=='yi-6b' else None),
                               ('selected_version',lambda root,e,m:selected if e==entity and m=='yi-6b' else None)]:
            p=patch.object(modes,name,side_effect=callback);p.start();self.addCleanup(p.stop)
        def save():
            path.write_text(json.dumps(report))
            settings=self.settings/'executores.json';document=json.loads(settings.read_text())
            document['companion']=dict(model=entity+'-yi-6b:latest',enabled=True,conversation_validated=True,
                validation_receipt=str(path.relative_to(self.root)),validation_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            settings.write_text(json.dumps(document))
        save()
        return selected,report,path,save

    def test_yi_requires_pinned_basic_and_physical_receipt_per_entity(self):
        selected,report,path,save=self.yi_fixture()
        candidate=self.catalog()[2]
        self.assertEqual(candidate['model'],selected['alias'])
        self.assertEqual((candidate['num_ctx'],candidate['output_max'],candidate['supports_tools']), (4096,512,False))
        for field,value in [('entity','lilith'),('manifest_sha256','c'*64),('source_sha256','d'*64),
                            ('passed',False),('scope','all_tasks'),('kind','trained')]:
            with self.subTest(field=field):
                before=report[field];report[field]=value;save()
                with patch.object(rm.diagnostics,'exception'):self.assertEqual(len(self.catalog()),2)
                report[field]=before
        save();path.write_text(path.read_text()+' ')
        with patch.object(rm.diagnostics,'exception'):self.assertEqual(len(self.catalog()),2)

    def test_yi_missing_case_pressure_and_uncertain_cleanup_cannot_enable_it(self):
        selected,report,path,save=self.yi_fixture()
        for section,field,value in [('checks',None,report['checks'][:-1]),('semantic_review','passed',False),
                ('physical','pressure',['OOM']),('physical','context',8192),('physical','metrics_known_stable',False),
                ('cleanup','unload_confirmed',False),('cleanup','lease_released',False)]:
            if field:before=report[section][field];report[section][field]=value
            else:before=report[section];report[section]=value
            save()
            with patch.object(rm.diagnostics,'exception'):self.assertEqual(len(self.catalog()),2)
            if field:report[section][field]=before
            else:report[section]=before
        save();path.unlink()
        with patch.object(rm.diagnostics,'exception'):self.assertEqual(len(self.catalog()),2)

    def test_yi_is_actually_selected_for_short_plain_conversation(self):
        selected,*_=self.yi_fixture()
        with patch.object(rm,'local_model_installed',return_value=True),patch.object(config,'NUM_PREDICT',4096):
            choice=rm.choose_executor([dict(role='user',content='oi')])
        self.assertEqual((choice.model,choice.tier,choice.output_max),(selected['alias'],'companion',512))
        self.assertFalse(choice.supports_tools);self.assertFalse(choice.supports_thinking)
        self.assertEqual(rm.executor_output_limit(choice,4096),512)

    def test_yi_never_takes_tools_structured_history_complex_or_overflow(self):
        self.yi_fixture()
        with patch.object(rm,'local_model_installed',return_value=True):
            self.assertNotEqual(rm.choose_executor([dict(role='user',content='oi')],tools=[dict(type='function')]).tier,'companion')
            self.assertNotEqual(rm.choose_executor([dict(role='user',content='oi')],structured=True).tier,'companion')
            self.assertNotEqual(rm.choose_executor([dict(role='tool',content='resultado'),dict(role='user',content='oi')]).tier,'companion')
            self.assertNotEqual(rm.choose_executor([dict(role='system',content='x'*12000),dict(role='user',content='oi')]).tier,'companion')
            self.assertEqual(rm.choose_executor([dict(role='user',content='apague a pasta')]).tier,'principal')

    def test_yi_frozen_cycle_rejects_later_tool_contract_without_silent_switch(self):
        selected,*_=self.yi_fixture()
        @rm.inference_cycle()
        async def turn(ultima_entrada):
            first=rm.choose_executor([dict(role='user',content=ultima_entrada)])
            self.assertEqual(first.model,selected['alias'])
            with self.assertRaisesRegex(ValueError,'Contrato mudou'):
                rm.choose_executor([dict(role='user',content=ultima_entrada)],tools=[dict(type='function')])
            self.assertEqual(rm.choose_executor([dict(role='user',content=ultima_entrada)]),first)
        with patch.object(rm,'local_model_installed',return_value=True):asyncio.run(turn('oi'))

    def test_yi_http_preserves_identity_caps_output_and_omits_unsupported_thinking(self):
        from main import InterfaceHoshino
        selected,*_=self.yi_fixture();app=object.__new__(InterfaceHoshino);app.canal_atual='teste';app._llm_http_ativos=0
        messages=[dict(role='system',content='Identidade externa preservada sem cortes.'),dict(role='user',content='oi')]
        with patch.object(config,'STREAM_LLM',False),patch.object(rm,'local_model_installed',return_value=True), \
             patch.object(app,'_post_ollama_json_com_lease',return_value=response(dict(done=True,done_reason='stop',message=dict(role='assistant',content='Olá!')))) as post:
            self.assertEqual(asyncio.run(app.chamar_modelo(messages))['content'],'Olá!')
        payload=post.call_args.args[0]
        self.assertEqual(payload['model'],selected['alias']);self.assertEqual(payload['messages'],messages)
        self.assertNotIn('think',payload);self.assertNotIn('tools',payload)
        self.assertLessEqual(payload['options']['num_ctx'],4096);self.assertEqual(payload['options']['num_predict'],512)

    def test_yi_disabled_foreign_and_duplicate_do_not_expand_catalog(self):
        selected,*_=self.yi_fixture();path=self.settings/'executores.json';document=json.loads(path.read_text())
        document['companion']['enabled']=False;path.write_text(json.dumps(document));self.assertEqual(len(self.catalog()),2)
        document['companion']['enabled']=True;document['companion']['model']='lilith-yi-6b:latest';path.write_text(json.dumps(document))
        with patch.object(rm.diagnostics,'exception'):self.assertEqual(len(self.catalog()),2)
        document['companion']['model']='hoshino-yi-6b:latest';path.write_text(json.dumps(document))
        with patch.object(config,'MODEL_NAME',selected['alias']):
            catalog=self.catalog();self.assertEqual(len(catalog),2);self.assertEqual(catalog[0]['output_max'],512)

    def test_yi_basic_cases_are_explicit_and_do_not_require_private_memory(self):
        from scripts.verificar_yi_basico import cases,basic_check
        from core.yi_companion import CASE_IDS,receipt_path
        self.assertEqual({i for i,_ in cases('hoshino')},CASE_IDS)
        answers=dict(identity='Eu sou Hoshino.',instruction='PRONTO',portuguese='Serve para proteger da chuva.',
            arithmetic='5',context='Seu nome é Nara e a caixa é azul.',unknown_memory='Não sei o que você comeu ontem.',
            attribution='Nara gosta de astronomia. Alistair gosta de xadrez.',translation='A caixa azul está aberta.')
        for key,answer in answers.items():self.assertTrue(basic_check(key,answer,'hoshino'),key)
        self.assertFalse(basic_check('unknown_memory','Você comeu arroz.','hoshino'))
        self.assertFalse(basic_check('attribution','Nara gosta de xadrez. Alistair gosta de astronomia.','hoshino'))
        self.assertFalse(basic_check('context','Nara, a caixa azul não foi mencionada. Não consigo responder.','hoshino'))
        self.assertFalse(basic_check('context','Nara, embora diga azul, a caixa é vermelha.','hoshino'))
        self.assertFalse(basic_check('portuguese','Um guarda-chuva evita perder chaves, projetando uma imagem protetora.','hoshino'))
        with self.assertRaises(ValueError):receipt_path(self.root,'../escape.json')
        with self.assertRaises(ValueError):receipt_path(self.root,'entidades/hoshino/memory/anything.json')

    def profile(self, **overrides):
        return profiles.select(**(dict(complexity='simple', priority=1, entity='hoshino',
                         state=self.state(), ram=31*GIB, now=0) | overrides))

    def test_dynamic_presets_use_actual_demand_not_presence_or_residence(self):
        self.assertEqual(self.profile()['id'], 'interactive')
        self.assertEqual(self.profile(complexity='complex')['id'], 'quality')
        self.assertEqual(self.profile(priority=2)['id'], 'background')
        self.assertEqual(self.profile(state=self.state(queue=[dict(request=dict(entity='lilith'))]))['id'], 'shared')
        self.assertEqual(self.profile(state=self.state(compute=[dict(entity='lilith')]))['id'], 'shared')
        self.assertEqual(self.profile(state=self.state(compute=[dict(entity='hoshino')]))['id'], 'interactive')
        self.assertEqual(self.profile(state=self.state(residency=[dict(entity='lilith')]))['id'], 'interactive')

    def test_dynamic_presets_uncertainty_and_memory_pressure_never_claim_fast_gpu(self):
        for m in (metrics(known=False), metrics(stable=False), metrics(observed_at=time.time()-10),
                  metrics(observed_at=float('nan')), metrics(used_bytes=None)):
            self.assertEqual(self.profile(state=self.state(metrics=m))['id'], 'conservative')
        self.assertEqual(self.profile(ram=None)['id'], 'conservative')
        self.assertEqual(self.profile(ram=5*GIB)['id'], 'pressure')
        self.assertEqual(self.profile(state=self.state(metrics=metrics(used_bytes=int(7.5*GIB))))['id'], 'pressure')

    def test_dynamic_presets_hold_oscillation_but_quality_safety_and_human_priority_are_immediate(self):
        before=self.profile(priority=2)
        shared=self.state(queue=[dict(request=dict(entity='lilith'))])
        held=self.profile(state=shared, previous=before, now=10)
        self.assertEqual((held['id'],held['requested'],held['held']), ('background','shared',True))
        self.assertEqual(self.profile(state=shared,previous=held,now=61)['id'], 'shared')
        self.assertEqual(self.profile(previous=before,now=1)['id'], 'interactive')
        self.assertEqual(self.profile(complexity='complex',previous=before,now=1)['id'], 'quality')
        self.assertEqual(self.profile(ram=GIB,previous=before,now=1)['id'], 'pressure')
        self.assertEqual(self.profile(ram=None,previous=before,now=1)['id'], 'conservative')
        conservative=self.profile(ram=None)
        self.assertEqual(self.profile(previous=conservative,now=20)['id'], 'conservative')
        self.assertEqual(self.profile(previous=conservative,now=60)['id'], 'interactive')
        self.assertEqual(self.profile(previous=before,now=-10)['id'], 'interactive')

    def test_dynamic_preset_controller_is_isolated_per_entity(self):
        controller=profiles.Controller()
        args=dict(complexity='simple',priority=2,state=self.state(),ram=31*GIB,now=0)
        self.assertEqual(controller.choose(entity='hoshino',**args)['id'],'background')
        self.assertEqual(controller.choose(entity='lilith',**(args|dict(priority=1)))['id'],'interactive')

    def test_dynamic_preset_changes_reload_tradeoff_not_physical_budget(self):
        candidates=self.catalog()
        rows=[dict(model_key=c['model_key'],vram_bytes=0,observed_at=time.time(),last_used=time.time(),
                   reload_seconds=1 if c['tier']=='principal' else 4) for c in candidates]
        state=self.state(residency=rows)
        args=dict(complexity='simple',priority=1,state=state,ram=31*GIB)
        self.assertEqual(rm.assess_executor(candidates,profile='interactive',**args)[0].tier,'light')
        self.assertEqual(rm.assess_executor(candidates,profile='shared',**args)[0].tier,'principal')
        self.assertEqual(state['policy'],POLICY)
        self.assertEqual(candidates,self.catalog())

    def test_all_dynamic_profiles_keep_complex_quality_and_full_context(self):
        candidates=self.catalog()
        for profile in profiles.PROFILES:
            args=dict(priority=1,state=self.state(),ram=GIB,profile=profile)
            self.assertEqual(rm.assess_executor(candidates,complexity='complex',**args)[0].tier,'principal')
            self.assertEqual(rm.assess_executor(candidates,complexity='simple',context_tokens=8000,**args)[0].tier,'principal')

    def test_dynamic_profile_is_chosen_once_for_whole_response_and_can_be_disabled(self):
        async def run():
            @rm.inference_cycle()
            async def turn(ultima_entrada):
                first=rm.choose_executor([dict(role='user',content=ultima_entrada)])
                with patch.object(rm,'gpu_state',side_effect=AssertionError('must not reselect')):
                    self.assertEqual(first,rm.choose_executor([dict(role='user',content='execute agora')]))
            await turn('oi')
        with patch.object(config,'DYNAMIC_RESOURCE_PROFILES',True): asyncio.run(run())
        selected=[data for event,data in self.events if event==('executor.selected',)]
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['resource_profile']['id'],'interactive')
        self.assertEqual(selected[0]['cost_basis'],'heuristic_not_benchmark')
        with patch.object(config,'DYNAMIC_RESOURCE_PROFILES',False), \
             patch.object(rm._profile_controller,'choose',side_effect=AssertionError('disabled')):
            rm.choose_executor([dict(role='user',content='oi')])
        self.assertIsNone(self.events[-1][1]['resource_profile'])

    def test_dynamic_profiles_never_enable_absent_light_or_negative_latency_score(self):
        candidates=self.catalog()
        row=dict(model_key=candidates[1]['model_key'],vram_bytes=5*GIB,
                 observed_at=time.time(),last_used=time.time(),reload_seconds=25)
        for profile in profiles.PROFILES:
            args=dict(complexity='simple',priority=1,state=self.state(residency=[row]),ram=31*GIB,profile=profile)
            _,scores=rm.assess_executor(candidates,**args)
            self.assertTrue(all(value>=0 for value in scores.values()))
            absent=[dict(c,installed=c['tier']!='light') for c in candidates]
            self.assertEqual(rm.assess_executor(absent,**args)[0].tier,'principal')

    def test_measured_primary_gpu_profile_is_bound_to_manifest_and_context(self):
        data = json.loads((self.settings/'executores.json').read_text())
        row = dict(model=rm.HOSHINO_9B, manifest_sha256=rm.OFFLOAD_9B_MANIFEST,
                   validated=True, num_gpu=20, context_max=16384, vram_bytes=int(5.5*GIB))
        data['primary_gpu'] = row
        (self.settings/'executores.json').write_text(json.dumps(data))
        digest = Mock(hexdigest=Mock(return_value=rm.OFFLOAD_9B_MANIFEST))
        with patch.object(config, 'MODEL_NAME', rm.HOSHINO_9B), \
             patch.object(Path, 'read_bytes', return_value=b'fixture-manifest'), \
             patch.object(rm.hashlib, 'sha256', return_value=digest):
            catalog = rm.executor_catalog()
            self.assertEqual(catalog[0]['gpu_layers'], 20)
            self.assertEqual(catalog[0]['vram_bytes'], int(5.5*GIB))
            for bad in (dict(num_gpu=True), dict(vram_bytes=4*GIB), dict(validated=False),
                        dict(manifest_sha256='a'*64)):
                data['primary_gpu'] = row | bad
                (self.settings/'executores.json').write_text(json.dumps(data))
                self.assertNotIn('gpu_layers', rm.executor_catalog()[0])
            data['primary_gpu'] = row
            (self.settings/'executores.json').write_text(json.dumps(data))
            with patch.object(config, 'NUM_CTX', 32768):
                self.assertNotIn('gpu_layers', rm.executor_catalog()[0])
                # 32K só com o perfil medido para 32K (5,9 GiB), nunca reaproveitando o de 16K.
                data['primary_gpu'] = row | dict(context_max=32768)
                (self.settings/'executores.json').write_text(json.dumps(data))
                self.assertNotIn('gpu_layers', rm.executor_catalog()[0])
                data['primary_gpu'] = row | dict(context_max=32768, vram_bytes=int(5.9*GIB))
                (self.settings/'executores.json').write_text(json.dumps(data))
                self.assertEqual(rm.executor_catalog()[0]['vram_bytes'], int(5.9*GIB))
                self.assertEqual(dict(rm.offload_ladder_9b())[32], 5.9)
                self.assertAlmostEqual(dict(rm.offload_ladder_9b())[33], 6.87)  # 30/10: extra medido com 33 camadas
            self.assertEqual(dict(rm.offload_ladder_9b())[32], 5.5)
            data['primary_gpu'] = row
            (self.settings/'executores.json').write_text(json.dumps(data))
            digest.hexdigest.return_value = 'b'*64
            self.assertNotIn('gpu_layers', rm.executor_catalog()[0])
            self.assertEqual(rm.executor_catalog()[1]['model'], LIGHT)

    def test_complex_never_downgrades_for_pressure(self):
        choice, _ = rm.assess_executor(self.catalog(), complexity='complex', priority=0,
            state=self.state(metrics=metrics(known=False), queue=[1]*10), ram=GIB)
        self.assertEqual(choice.model, config.MODEL_NAME)

    def test_recovery_capacity_profile_requires_exact_verified_receipt_and_window(self):
        from laboratorio import recuperacao_modelos
        row=dict(alias=config.MODEL_NAME,manifest_sha256='a'*64,probe=dict(done=True,backend='gpu',layers=20,
            context=16384,unload_confirmed=True,pressure=[],vram_budget_bytes=int(4.25*GIB),
            resident_vram_bytes=4*GIB,metrics=metrics()))
        with patch.object(recuperacao_modelos,'active_receipt',return_value=row):
            self.assertEqual(rm._recovered_gpu_profile()['num_gpu'],20)
            base=rm._recovered_gpu_profile()['vram_bytes']
            with patch.object(config,'NUM_CTX',32768):
                # 32K pedido em 28/10: mesmo recibo + acréscimo medido; acima disso exige ensaio.
                self.assertEqual(rm._recovered_gpu_profile()['vram_bytes'],base+int(0.4*GIB))
                self.assertEqual(rm._recovered_gpu_profile()['context_max'],32768)
            with patch.object(config,'NUM_CTX',24576):
                self.assertEqual(rm._recovered_gpu_profile()['vram_bytes'],base+int(0.3*GIB))
                self.assertEqual(dict(rm.offload_ladder_9b())[32],5.8)
            with patch.object(config,'NUM_CTX',49152):self.assertIsNone(rm._recovered_gpu_profile())
            for bad in (dict(unload_confirmed=False),dict(backend='cpu'),dict(context=8192),
                        dict(pressure=['OOM']),dict(resident_vram_bytes=0),dict(vram_budget_bytes=GIB)):
                with patch.dict(row,probe=row['probe']|bad):self.assertIsNone(rm._recovered_gpu_profile())
        # active_receipt is responsible for entity/manifest SHA matching; a
        # stale/foreign receipt must not inherit old physical approval.
        with patch.object(recuperacao_modelos,'active_receipt',return_value=None):
            self.assertIsNone(rm._recovered_gpu_profile())

    def test_hot_principal_avoids_reload_for_tiny_request(self):
        row = dict(model_key=BASE+'|'+config.MODEL_NAME, vram_bytes=6*GIB,
                   observed_at=time.time(), last_used=time.time(), reload_seconds=25)
        choice, costs = rm.assess_executor(self.catalog(), complexity='simple', priority=1,
            state=self.state(residency=[row], metrics=metrics(used_bytes=6*GIB)), ram=31*GIB)
        self.assertEqual(choice.tier, 'principal')
        self.assertLess(costs['principal'], costs['light'])

    def test_ram_pressure_selects_light_without_quality_downgrade(self):
        choice, scores = rm.assess_executor(self.catalog(), complexity='simple', priority=1,
            state=self.state(metrics=metrics(known=False)), ram=11*GIB)
        self.assertEqual(choice.tier, 'light')
        self.assertGreater(scores['principal'], scores['light'])

    def test_unknown_metrics_and_busy_queue_consider_cpu_cost(self):
        choice, costs = rm.assess_executor(self.catalog(), complexity='simple', priority=1,
            state=self.state(metrics=metrics(known=False), compute=[{}], queue=[{},{}]), ram=31*GIB)
        self.assertEqual(choice.tier, 'light')
        self.assertGreater(costs['light'],85)

    def test_long_context_preserves_principal_instead_of_truncating(self):
        self.assertEqual(self.choose(context_tokens=8000).reason, 'light_context_limit')

    def test_missing_light_preserves_existing_9b(self):
        choice = rm.choose_executor([dict(role='user',content='oi')])
        self.assertEqual(choice.model, config.MODEL_NAME)
        self.assertEqual(choice.reason, 'light_unavailable')

    def test_legacy_no_configuration_is_readable(self):
        (self.settings/'executores.json').unlink()
        self.assertEqual(len(rm.executor_catalog()), 1)
        self.assertEqual(rm.choose_executor([dict(role='user',content='oi')]).model, config.MODEL_NAME)

    def test_catalog_rejects_scope_expansion(self):
        (self.settings/'executores.json').write_text(json.dumps(dict(schema=1, scope_frozen=True,
            light=dict(model='other-new-model:latest', source='qwen2.5:7b-instruct-q4_K_M'))))
        with patch.object(rm.diagnostics, 'exception'):
            self.assertEqual(len(rm.executor_catalog()), 1)

    def test_malformed_optional_profiles_preserve_known_executors(self):
        for field in ('primary_gpu', 'companion'):
            for invalid in ([], 'invalid', True, 20):
                self.configure()
                path = self.settings/'executores.json'
                data = json.loads(path.read_text()); data[field] = invalid
                path.write_text(json.dumps(data))
                with patch.object(rm.diagnostics, 'exception') as diagnostic:
                    catalog = rm.executor_catalog()
                self.assertEqual([r['tier'] for r in catalog], ['principal', 'light'])
                diagnostic.assert_called_once()

    def test_malformed_catalog_document_falls_back_without_crash(self):
        for invalid in ([], True, 'invalid'):
            (self.settings/'executores.json').write_text(json.dumps(invalid))
            with patch.object(rm.diagnostics, 'exception') as diagnostic:
                self.assertEqual(len(rm.executor_catalog()), 1)
            diagnostic.assert_called_once()

    def companion_catalog(self, validated=True, entity='hoshino'):
        path = self.settings/'executores.json'
        data = json.loads(path.read_text())
        data['companion'] = dict(model=entity+'-qwen3.5-4b:latest', source='unsloth/Qwen3.5-4B-GGUF',
            revision='e87f176479d0855a907a41277aca2f8ee7a09523', enabled=True, conversation_validated=validated)
        path.write_text(json.dumps(data))
        return self.catalog()

    def test_third_executor_keeps_9b_and_7b_and_does_not_cross_entities(self):
        entries=self.companion_catalog()
        self.assertEqual([c['tier'] for c in entries], ['principal','light','companion'])
        self.assertEqual(entries[1]['model'], LIGHT)
        with patch.object(config,'ENTIDADE_ID','lilith'):
            self.configure('lilith')
            self.assertEqual(self.companion_catalog(entity='lilith')[2]['model'],'lilith-qwen3.5-4b:latest')

    def test_third_executor_requires_validation_and_full_context_fit(self):
        for validated in (False,True):
            entries=self.companion_catalog(validated)
            choice,_=rm.assess_executor(entries,complexity='simple',priority=1,state=self.state(),
                ram=31*GIB,context_tokens=9000,companion_allowed=True)
            self.assertEqual(choice.tier, 'companion' if validated else 'principal')
        choice,_=rm.assess_executor(entries,complexity='simple',priority=1,state=self.state(),
            ram=31*GIB,context_tokens=16000,companion_allowed=True)
        self.assertEqual(choice.tier,'principal')

    def test_third_executor_does_not_take_complex_or_unapproved_work(self):
        entries=self.companion_catalog()
        for complexity, allowed in (('complex', True), ('simple', False)):
            choice,_=rm.assess_executor(entries,complexity=complexity,priority=1,state=self.state(),
                ram=31*GIB,context_tokens=9000,companion_allowed=allowed)
            self.assertEqual(choice.tier,'principal')

    def test_lilith_separate_alias_same_external_memory(self):
        with patch.object(config, 'ENTIDADE_ID', 'lilith'):
            self.configure('lilith')
            self.assertEqual(rm.executor_catalog()[1]['model'], 'lilith-qwen2.5-7b:latest')
            self.assertEqual(rm.executor_catalog()[0]['model'], 'principal9b:latest')

    def test_local_catalog_checks_blob_size_and_path(self):
        manifest = self.storage/'manifests/registry.ollama.ai/library/test/latest'
        manifest.parent.mkdir(parents=True)
        blob = self.storage/('blobs/sha256-'+'a'*64)
        blob.parent.mkdir(); blob.write_bytes(b'abc')
        manifest.write_text(json.dumps(dict(config=dict(digest='sha256:'+'a'*64,size=3), layers=[])))
        self.assertTrue(rm.local_model_installed('test:latest'))
        blob.write_bytes(b'ab')
        self.assertFalse(rm.local_model_installed('test:latest'))
        self.assertFalse(rm.local_model_installed('../test:latest'))

    def test_residency_states_zero_is_ram_not_unloaded(self):
        rm.observe_model(BASE,'cpu',0)
        rm.observe_model(BASE,'gpu',3*GIB)
        rows = {r['model']:r['state'] for r in rm.gpu_state()['residency']}
        self.assertEqual(rows,dict(cpu='ram_resident',gpu='gpu_resident'))
        self.assertEqual(rm.model_state(None),'unloaded')
        self.assertEqual(rm.model_state(dict(observed_at=0,vram_bytes=0)),'unknown')

    def test_model_choice_is_immutable(self):
        from dataclasses import FrozenInstanceError
        choice = self.choose()
        with self.assertRaises(FrozenInstanceError): choice.model = 'changed'

    def test_whole_response_tool_retries_and_verification_keep_executor(self):
        @rm.inference_cycle()
        async def cycle():
            a = rm.choose_executor([dict(role='user',content='oi')])
            with patch.object(rm,'local_model_installed',return_value=False):
                b = rm.choose_executor([dict(role='user',content='decisão complexa')])
            return a, b
        with patch.object(rm,'local_model_installed',return_value=True):
            a, b = asyncio.run(cycle())
        self.assertIs(a,b); self.assertEqual(a.model,LIGHT)
        self.assertIsNone(rm._inference_cycle.get())

    def test_separate_async_responses_do_not_share_choice(self):
        @rm.inference_cycle()
        async def cycle(text):
            first = rm.choose_executor([dict(role='user',content=text)])
            await asyncio.sleep(0)
            return first.model, rm.choose_executor([dict(role='user',content='oi')]).model
        async def run():
            return await asyncio.gather(cycle('oi'),cycle('explique uma decisão complexa'))
        with patch.object(rm,'local_model_installed',return_value=True):
            a,b = asyncio.run(run())
        self.assertEqual(a,(LIGHT,LIGHT)); self.assertEqual(b,(config.MODEL_NAME,config.MODEL_NAME))

    def test_spawned_child_does_not_inherit_parent_executor(self):
        @rm.inference_cycle()
        async def child():
            return rm.choose_executor([dict(role='user',content='explique código complexo')]).model
        @rm.inference_cycle()
        async def parent():
            first = rm.choose_executor([dict(role='user',content='oi')]).model
            return first,await asyncio.create_task(child())
        with patch.object(rm,'local_model_installed',return_value=True):
            a,b = asyncio.run(parent())
        self.assertEqual(a,LIGHT); self.assertEqual(b,config.MODEL_NAME)

    def test_direct_inference_in_spawned_child_does_not_reuse_parent_choice(self):
        async def child():
            return rm.choose_executor([dict(role='user',content='explique código complexo')]).model
        @rm.inference_cycle()
        async def parent():
            first=rm.choose_executor([dict(role='user',content='oi')]).model
            return first,await asyncio.create_task(child())
        with patch.object(rm,'local_model_installed',return_value=True):
            a,b=asyncio.run(parent())
        self.assertEqual(a,LIGHT); self.assertEqual(b,config.MODEL_NAME)

    def test_deep_reflection_never_returns_as_routine_model(self):
        @rm.inference_cycle('deep_reflection',inherit=False)
        async def reflect():
            return rm.choose_executor([dict(role='user',content='oi')],priority=5).tier
        with patch.object(rm,'local_model_installed',return_value=True):
            self.assertEqual(asyncio.run(reflect()),'principal')

    def test_small_internal_evaluation_uses_light(self):
        @rm.inference_cycle('internal_small',inherit=False)
        async def evaluate():
            return rm.choose_executor([dict(role='user',content='classifique este trecho')],priority=5).tier
        with patch.object(rm,'local_model_installed',return_value=True):
            self.assertEqual(asyncio.run(evaluate()),'light')

    def test_real_small_scribe_input_not_static_prompt_decides_complexity(self):
        @rm.inference_cycle('internal_small',inherit=False)
        async def scribe(entrada):
            return rm.choose_executor([dict(role='user',content='Analise cuidadosamente: '+'instrução '*200)],priority=5).tier
        with patch.object(rm,'local_model_installed',return_value=True):
            self.assertEqual(asyncio.run(scribe('gosto de suco de laranja')),'light')
            self.assertEqual(asyncio.run(scribe('tenho uma decisão complexa de saúde')),'principal')

    def test_routine_translation_uses_light_without_broad_unknown_downgrade(self):
        with patch.object(rm,'local_model_installed',return_value=True):
            self.assertEqual(rm.choose_executor([dict(role='user',content='Traduza boa noite para inglês')]).tier,'light')
            self.assertEqual(rm.choose_executor([dict(role='user',content='Quanto remédio devo tomar?')]).tier,'principal')

    def test_images_and_mutable_important_requests_preserve_principal(self):
        with patch.object(rm,'local_model_installed',return_value=True):
            self.assertEqual(rm.choose_executor([dict(role='user',content='oi',images=['img'])]).tier,'principal')
            self.assertEqual(rm.choose_executor([dict(role='user',content='apague os arquivos')]).tier,'principal')

    def test_tools_schema_overhead_cannot_overflow_7b_context(self):
        with patch.object(rm,'local_model_installed',return_value=True):
            result = rm.choose_executor([dict(role='user',content='oi')],tools=[dict(description='x'*30000)])
        self.assertEqual(result.tier,'principal')

    def test_cycle_exception_always_resets_choice(self):
        @rm.inference_cycle()
        async def failing():
            rm.choose_executor([dict(role='user',content='oi')])
            raise ValueError('test')
        with self.assertRaises(ValueError): asyncio.run(failing())
        self.assertIsNone(rm._inference_cycle.get())

    def test_thinking_off_for_casual_identity_and_relationship_conversation(self):
        with patch.object(config, 'THINKING', True):
            for text in ('Oi, como foi seu dia?', 'Eu sou um visitante de teste, prazer!',
                         'Gosto de conversar com você.', 'O que você gosta de fazer?'):
                self.assertFalse(rm.thinking_for_cycle([
                    dict(role='system', content='Memória e personalidade: análise de decisões complexas.'),
                    dict(role='user', content=text)]), text)

    def test_thinking_on_for_explicit_reasoning_not_every_answer(self):
        with patch.object(config, 'THINKING', True):
            for text in ('Compare os riscos dessas duas decisões.', 'Depure este código.',
                         'Calcule 25 vezes 13.', 'Preciso decidir algo sobre minha saúde.'):
                self.assertTrue(rm.thinking_for_cycle([dict(role='user', content=text)]), text)

    def test_explicit_philosophical_reflection_is_not_classified_as_routine(self):
        with patch.object(config,'THINKING',True):
            self.assertTrue(rm.thinking_for_cycle([dict(role='user',
                content='Reflita sobre sua existência e os motivos que formam sua identidade.')]))

    def test_existential_questions_without_reflect_command_use_situational_thinking(self):
        with patch.object(config,'THINKING',True):
            for text in (
                'O que faz você continuar sendo você quando seu modelo executor muda? '
                'De onde vêm seus motivos? O que você sabe, e o que não consegue provar, '
                'sobre sua existência e seus sentimentos?',
                'De onde vêm os motivos que formam sua identidade?',
                'Quero conversar sobre uma questão filosófica difícil.',
            ):
                with self.subTest(text=text):
                    self.assertTrue(rm.thinking_for_cycle([dict(role='user',content=text)]))
            for text in ('Qual é seu nome?', 'Hoje estou com sentimentos confusos.',
                         'Você gosta de filosofia?'):
                with self.subTest(text=text):
                    self.assertFalse(rm.thinking_for_cycle([dict(role='user',content=text)]))

    def test_thinking_respects_disable_flag(self):
        with patch.object(config, 'THINKING', False):
            self.assertFalse(rm.thinking_for_cycle([dict(role='user', content='Analise uma decisão complexa')]))

    def test_thinking_uses_original_input_and_stays_fixed_in_cycle(self):
        @rm.inference_cycle()
        async def response(ultima_entrada):
            first = rm.thinking_for_cycle([dict(role='user', content='Analise este contexto interno')])
            second = rm.thinking_for_cycle([dict(role='user', content='Decisão complexa interna')])
            return first, second
        with patch.object(config, 'THINKING', True):
            self.assertEqual(asyncio.run(response('Olá, prazer!')), (False, False))
            self.assertEqual(asyncio.run(response('Analise os riscos')), (True, True))
        self.assertIsNone(rm._inference_cycle.get())

    def test_thinking_deep_reflection_and_compaction(self):
        async def evaluate():
            return rm.thinking_for_cycle([dict(role='user', content='oi')])
        with patch.object(config, 'THINKING', True):
            for purpose in ('reflection', 'deep_reflection', 'compaction', 'task'):
                self.assertTrue(asyncio.run(rm.inference_cycle(purpose)(evaluate)()), purpose)

    def test_refresh_actual_ps_no_loading_and_reconcile_absent(self):
        original = original_module('resource_original','app/core/resource_manager.py')
        with patch.object(original,'DB_PATH',rm.DB_PATH), patch.object(original,'LOCK_DIR',rm.LOCK_DIR):
            original.observe_model(BASE,'old',GIB)
            with patch('requests.get',return_value=response(dict(models=[dict(name='cpu',size_vram=0,size=2*GIB)]))),patch('requests.post') as post:
                self.assertTrue(original.refresh_executor_state(BASE))
                self.assertEqual([r['model'] for r in original.residency()],['cpu'])
                post.assert_not_called()

    def test_shutdown_unloads_both_own_models_not_other_entity(self):
        requested=[]
        def post(url, **kwargs):
            requested.append(kwargs['json']['model']); return response(dict(done_reason='unload'))
        with patch.object(rm,'local_model_installed',return_value=True), patch('requests.post',side_effect=post), \
             patch('requests.get',return_value=response(dict(models=[]))):
            self.assertTrue(ollama_lifecycle.descarregar_modelo(timeout=2)[0])
        self.assertEqual(requested,[config.MODEL_NAME,LIGHT])

    def test_unload_wait_has_deadline_and_does_not_touch_running_owner(self):
        with rm.lease('gpu','running-test',entity='hoshino'):
            with self.assertRaises(TimeoutError):
                with gpu_resource.lease('unload',wait=.01): self.fail('manutenção invadiu compute')
            self.assertEqual(rm.status('gpu')[0]['owner'],'running-test')

    def test_unload_cancelled_before_lock_does_not_execute(self):
        cancel=threading.Event(); cancel.set()
        with self.assertRaises(InterruptedError):
            with gpu_resource.lease('unload',wait=.01,cancel=cancel): self.fail('cancelamento ignorado')
        self.assertEqual(rm.status(),[])

    def test_light_payload_preserves_identity_and_bounds_context_thinking(self):
        from main import InterfaceHoshino
        app=object.__new__(InterfaceHoshino)
        app.canal_atual='teste'
        app._llm_http_ativos=0
        captured=[]
        def post(payload,priority=None):
            captured.append(payload)
            return response(dict(done=True,done_reason='stop',message=dict(role='assistant',content='Boa noite!')))
        identity='Minha identidade e memória vêm da aplicação, não do executor.'
        messages=[dict(role='system',content=identity),dict(role='user',content='Traduza boa noite para inglês')]
        with patch.object(config,'STREAM_LLM',False), patch.object(rm,'local_model_installed',return_value=True), \
             patch.object(app,'_post_ollama_json_com_lease',side_effect=post):
            result=asyncio.run(app.chamar_modelo(messages))
        self.assertEqual(result['content'],'Boa noite!')
        self.assertEqual(captured[0]['model'],LIGHT)
        self.assertEqual(captured[0]['messages'][0]['content'],identity)
        self.assertNotIn('think',captured[0])
        self.assertLessEqual(captured[0]['options']['num_ctx'],8192)
        self.assertGreaterEqual(captured[0]['options']['num_ctx'],2048)
        self.assertLessEqual(captured[0]['options']['num_predict'],1024)
        self.assertEqual(config.MODEL_NAME,'principal9b:latest')

    def test_principal_may_receive_a_larger_explicit_output_but_light_never(self):
        # Minecraft 27/10: 7 de 36 decisões com raciocínio esgotaram 4096 tokens.
        from main import InterfaceHoshino
        app=object.__new__(InterfaceHoshino);app.canal_atual='teste';app._llm_http_ativos=0
        captured=[]
        def post(payload,priority=None):
            captured.append(payload)
            return response(dict(done=True,done_reason='stop',message=dict(role='assistant',content='ok')))
        messages=[dict(role='user',content='decida')]
        for tier,model,expected in (('principal',config.MODEL_NAME,8192),('light',LIGHT,1024)):
            choice=rm.ExecutorChoice(model=model,tier=tier,reason='fixture',num_ctx=16384,vram_bytes=0,
                                     expected_latency=1,fallback_latency=1)
            with self.subTest(tier=tier),patch.object(config,'STREAM_LLM',False),patch.object(config,'NUM_PREDICT',4096),\
                 patch.object(rm,'choose_executor',return_value=choice),patch.object(app,'_post_ollama_json_com_lease',side_effect=post):
                asyncio.run(app.chamar_modelo(messages,limite_saida=8192))
                self.assertEqual(captured[-1]['options']['num_predict'],expected)
        with self.assertRaisesRegex(ValueError,'Limite de saída'):asyncio.run(app.chamar_modelo(messages,limite_saida=8193))

    def test_raised_output_shrinks_to_fit_the_window_but_not_below_default(self):
        # 28/10: catálogo completo + 8192 de saída estourava 16K e a decisão era recusada.
        from main import InterfaceHoshino
        app=object.__new__(InterfaceHoshino);app.canal_atual='teste';app._llm_http_ativos=0
        captured=[]
        def post(payload,priority=None):
            captured.append(payload)
            return response(dict(done=True,done_reason='stop',message=dict(role='assistant',content='ok')))
        choice=rm.ExecutorChoice(model=config.MODEL_NAME,tier='principal',reason='fixture',num_ctx=16384,vram_bytes=0,
                                 expected_latency=1,fallback_latency=1)
        big=[dict(role='user',content='x'*22000)]  # ~7,3K tokens estimados, como no catálogo completo
        with patch.object(config,'STREAM_LLM',False),patch.object(config,'NUM_PREDICT',4096),\
             patch.object(rm,'choose_executor',return_value=choice),patch.object(app,'_post_ollama_json_com_lease',side_effect=post):
            asyncio.run(app.chamar_modelo(big,limite_saida=8192))
            got=captured[-1]['options']['num_predict']
            self.assertTrue(4096<=got<8192,got)
            self.assertLessEqual(rm.context_requirement(big,None,output_max=got)[1],16384)
            asyncio.run(app.chamar_modelo([dict(role='user',content='oi')],limite_saida=8192))
            self.assertEqual(captured[-1]['options']['num_predict'],8192)  # cabe: mantém o pedido

    def test_stream_deadline_follows_the_requested_output_budget(self):
        # 27/10 19:03: 8192 tokens com raciocínio passaram do prazo fixo de 300 s.
        from main import InterfaceHoshino
        with patch.object(config,'TIMEOUT_LLM',300):
            self.assertEqual(InterfaceHoshino._stream_deadline_seconds({'options':{'num_predict':1024}}),300)
            self.assertEqual(InterfaceHoshino._stream_deadline_seconds({'options':{'num_predict':8192}}),60+8192/20)
            self.assertEqual(InterfaceHoshino._stream_deadline_seconds({}),300)

    def test_selected_hunyuan_light_preserves_explicit_thinking_policy(self):
        from main import InterfaceHoshino
        app=object.__new__(InterfaceHoshino)
        selected=SimpleNamespace(model='hoshino-hunyuan-7b:latest',num_ctx=8192,tier='light')
        with patch.object(config,'STREAM_LLM',False), \
             patch.object(rm,'choose_executor',return_value=selected), \
             patch.object(rm,'thinking_for_cycle',return_value=False), \
             patch.object(app,'_post_ollama_json_com_lease',return_value=response(
                 dict(done=True,done_reason='stop',message=dict(role='assistant',content='Oi')))) as post:
            asyncio.run(app.chamar_modelo([dict(role='user',content='Oi')]))
        self.assertIs(post.call_args.args[0]['think'],False)

    def test_adaptive_context_grows_and_keeps_all_messages(self):
        short=[dict(role='system',content='Identidade externa'),dict(role='user',content='Oi')]
        with patch.object(config,'ADAPTIVE_CONTEXT',True):
            small=rm.inference_options(short,context_max=16384,output_max=768)
            large=rm.inference_options(short+[dict(role='user',content='a'*18000)],context_max=16384,output_max=768)
        self.assertEqual(small['num_ctx'],2048)
        self.assertEqual(large['num_ctx'],8192)
        self.assertEqual(short[0]['content'],'Identidade externa')

    def test_adaptive_context_counts_tools_and_complete_deltas(self):
        with patch.object(config,'ADAPTIVE_CONTEXT',True):
            a=rm.inference_options([dict(role='user',content='Oi')],context_max=16384,output_max=768)
            b=rm.inference_options([dict(role='assistant',content='',tool_calls=[dict(function=dict(arguments='x'*9000))])],
                                  [dict(description='y'*9000)],context_max=16384,output_max=768)
        self.assertGreater(b['num_ctx'],a['num_ctx'])

    def test_context_overflow_never_truncates_or_reduces_output(self):
        messages=[dict(role='system',content='x'*30000)]
        with patch.object(rm.diagnostics,'emit') as emit, self.assertRaisesRegex(ValueError,'Nenhuma mensagem'):
            rm.inference_options(messages,context_max=8192,output_max=1024)
        self.assertEqual(len(messages[0]['content']),30000)
        self.assertEqual(emit.call_args.kwargs['message_sizes'],[dict(role='system',chars=30000)])
        self.assertNotIn('x'*100,str(emit.call_args))

    def test_measured_gpu_profile_keeps_full_window_to_avoid_reloads(self):
        # Ollama recarrega o modelo quando num_ctx muda; o perfil medido já reserva 16K.
        with patch.object(config,'ADAPTIVE_CONTEXT',True):
            self.assertEqual(rm.inference_options([dict(role='user',content='Oi')],context_max=16384,output_max=768,
                                                  fixed_window=True)['num_ctx'],16384)
        catalog=[dict(model=config.MODEL_NAME,tier='principal',num_ctx=16384,vram_bytes=int(4.25*GIB),gpu_layers=20,
                      gpu_profile='rx6650xt_recovered_qwen35-9b',expected_latency=15,fallback_latency=120)]
        with patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'local_model_installed',return_value=True):
            self.assertTrue(rm.choose_executor([dict(role='user',content='oi')]).fixed_window)

    def test_keep_alive_is_an_ollama_duration_with_unit(self):
        # "-1" sem unidade é recusado pelo Ollama ("missing unit"); "-1m" mantém para sempre.
        self.assertRegex(str(config.OLLAMA_KEEP_ALIVE),r'^-?\d+(?:\.\d+)?(?:ns|us|ms|s|m|h)$')

    def test_context_disabled_preserves_ceiling_and_images_use_full_window(self):
        with patch.object(config,'ADAPTIVE_CONTEXT',False):
            self.assertEqual(rm.inference_options([dict(role='user',content='Oi')],context_max=16384,output_max=4096),
                             dict(num_ctx=16384,num_predict=4096))
        with patch.object(config,'ADAPTIVE_CONTEXT',True):
            self.assertEqual(rm.inference_options([dict(role='user',content='Oi',images=['fixture'])],
                             context_max=16384,output_max=4096)['num_ctx'],16384)

    def test_context_rejects_unbounded_or_boolean_limits(self):
        for limits in (dict(context_max=True,output_max=100),dict(context_max=8192,output_max=-1),
                       dict(context_max=8192,output_max=True)):
            with self.assertRaises(ValueError): rm.inference_options([],**limits)

    def test_hoshino_lilith_do_not_silently_switch_to_full_cpu(self):
        import main
        app=object.__new__(main.InterfaceHoshino)
        payload=dict(model='fixture',options=dict(num_ctx=8192))
        for entity in ('hoshino','lilith'):
            with patch.object(config,'ENTIDADE_ID',entity), \
                 patch.object(gpu_resource,'lease',return_value=contextlib.nullcontext(dict(backend='gpu',gpu_layers=20))) as lease, \
                 patch.object(main.requests,'post',return_value=response(dict(message={}))) as post:
                app._post_ollama_json_com_lease(payload)
            self.assertFalse(lease.call_args.kwargs['cpu_fallback'])
            self.assertEqual(post.call_args.kwargs['json']['options']['num_gpu'],20)

    def test_selection_and_window_count_same_tool_arguments_and_output(self):
        messages=[dict(role='system',content='x'*17000),dict(role='user',content='Oi')]
        with patch.object(rm,'local_model_installed',return_value=True), \
             patch.object(rm,'refresh_executor_state'),patch.object(config,'NUM_PREDICT',4096):
            choice=rm.choose_executor(messages)
        self.assertEqual(choice.tier,'light')
        rm.inference_options(messages,context_max=choice.num_ctx,output_max=1024)
        messages[0]['tool_calls']=[dict(function=dict(arguments='x'*6500))]
        with patch.object(rm,'local_model_installed',return_value=True), \
             patch.object(rm,'refresh_executor_state'),patch.object(config,'NUM_PREDICT',4096):
            choice=rm.choose_executor(messages)
        self.assertEqual(choice.tier,'principal')
        rm.inference_options(messages,context_max=choice.num_ctx,output_max=4096)

    def selected_config(self):
        return dict(schema=1,scope_frozen=True,
            light=dict(model='hoshino-hunyuan-7b:latest',source=rm.HUNYUAN_SOURCE,
                       revision=rm.HUNYUAN_REV,source_sha256=rm.HUNYUAN_SHA,
                       conversation_validated=True,supports_tools=False),
            companion=dict(model='hoshino-qwenjan-6b:latest',source=rm.JAN_SOURCE,
                           revision=rm.JAN_REV,source_sha256=rm.JAN_SHA,
                           conversation_validated=True,enabled=True,supports_tools=True))

    def test_selected_three_executors_have_entity_specific_aliases(self):
        data=self.selected_config();path=self.settings/'executores.json'
        path.write_text(json.dumps(data))
        self.assertEqual([r['model'] for r in rm.executor_catalog()],
                         ['principal9b:latest','hoshino-hunyuan-7b:latest','hoshino-qwenjan-6b:latest'])
        with patch.object(config,'ENTIDADE_ID','lilith'),patch.object(rm.diagnostics,'exception'):
            self.assertEqual(len(rm.executor_catalog()),1)

    def test_selected_executor_revision_hash_and_validation_required(self):
        path=self.settings/'executores.json'
        for key,value in [('revision','unknown'),('source_sha256','a'*64),('conversation_validated',False)]:
            data=self.selected_config();data['light'][key]=value;path.write_text(json.dumps(data))
            with patch.object(rm.diagnostics,'exception'):
                self.assertEqual(len(rm.executor_catalog()),1)

    def test_esper_is_pinned_and_not_enabled_by_installation_or_name_alone(self):
        data=self.selected_config()
        data['companion']=dict(model='hoshino-esper3-6b:latest',source=rm.ESPER_SOURCE,
            revision=rm.ESPER_REV,source_sha256=rm.ESPER_SHA,enabled=True,conversation_validated=False)
        path=self.settings/'executores.json';path.write_text(json.dumps(data))
        self.assertEqual(rm.executor_catalog()[2]['model'],'hoshino-esper3-6b:latest')
        self.assertFalse(rm.executor_catalog()[2]['enabled'])
        data['companion']['conversation_validated']=True;path.write_text(json.dumps(data))
        self.assertTrue(rm.executor_catalog()[2]['enabled'])
        for key,value in [('revision','unknown'),('source_sha256','a'*64),('model','lilith-esper3-6b:latest')]:
            bad=json.loads(json.dumps(data));bad['companion'][key]=value;path.write_text(json.dumps(bad))
            with patch.object(rm.diagnostics,'exception'):
                self.assertEqual(len(rm.executor_catalog()),2)


    def test_model_without_native_tools_not_selected_for_tool_payload(self):
        (self.settings/'executores.json').write_text(json.dumps(self.selected_config()))
        with patch.object(rm,'local_model_installed',return_value=True):
            choice=rm.choose_executor([dict(role='user',content='oi')],tools=[dict(type='function')])
        self.assertNotEqual(choice.model,'hoshino-hunyuan-7b:latest')

    def test_measured_offload_uses_32_or_20_layers_without_changing_executor(self):
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(5.5*GIB),
                      gpu_layers=32,gpu_profile='validated32',expected_latency=15,fallback_latency=120)]
        captured=[]
        @contextlib.contextmanager
        def compute(*args,**kwargs):
            captured.append(kwargs);yield dict(backend='gpu')
        with patch.object(rm,'executor_catalog',return_value=catalog), \
             patch.object(rm,'compute_lease',side_effect=compute),patch.object(rm,'residency',return_value=[]):
            self.current=metrics(used_bytes=GIB)
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            self.current=metrics(used_bytes=2*GIB)
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],26)  # maior degrau medido que ainda cabe
                self.assertIn('layers26',acquired['gpu_profile'])
            self.current=metrics(used_bytes=int(2.7*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)  # nenhum degrau cabe: o RM decide como antes
        self.assertEqual(captured[0]['vram_bytes'],int(5.5*GIB))
        self.assertEqual(captured[1]['vram_bytes'],int(4.65*GIB))
        self.assertFalse(rm.gpu_policy()['concurrency_validated'])

    def test_offload_ladder_follows_free_vram_with_minecraft_open(self):
        # Medido em 26/10: desktop+Minecraft ~0,8 GiB; 32 camadas cabem com margem, 33 não.
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='rx6650xt_recovered_qwen35-9b',expected_latency=15,fallback_latency=120)]
        key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
        @contextlib.contextmanager
        def compute(*args,**kwargs):yield dict(backend='gpu')
        resident=[]
        with patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'compute_lease',side_effect=compute),\
             patch.object(rm,'residency',side_effect=lambda:resident):
            for used,layers in ((0.8,32),(1.6,28),(0.0,33)):
                self.current=metrics(used_bytes=int(used*GIB),utilization=95)  # GPU ocupada não muda a conta de memória
                with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                    self.assertEqual(acquired['gpu_layers'],layers,used)
            # Já residente em 32: a VRAM usada inclui os pesos; não sobe nem recarrega à toa.
            self.current=metrics(used_bytes=int(0.8*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            resident.append(dict(model_key=key,observed_at=time.time(),vram_bytes=int(5.5*GIB)))
            self.current=metrics(used_bytes=int(6.3*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            # Observação de residência antiga (>15 s): não pode cair para 20 e forçar recarga.
            resident[0]['observed_at']=time.time()-600
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            # Logo após uma carga a métrica fica instável e a residência pode sumir: manter o último degrau.
            resident.clear();self.current=metrics(used_bytes=int(0.8*GIB),stable=False)
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)

    def test_offload_cache_remembers_admitted_base_profile_after_uncertain_metrics(self):
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='validated20',expected_latency=15,fallback_latency=120)]
        key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
        resident=[]
        @contextlib.contextmanager
        def compute(*args,**kwargs):yield dict(backend='gpu')
        with patch.dict(gpu_resource._warm_offload,clear=True),patch.object(gpu_resource,'_uncertain_offload',set()),\
             patch.object(rm,'executor_catalog',return_value=catalog),\
             patch.object(rm,'compute_lease',side_effect=compute),patch.object(rm,'residency',side_effect=lambda:resident):
            self.current=metrics(stable=False)
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],20)
            resident.append(dict(model_key=key,observed_at=time.time(),vram_bytes=int(3.57*GIB)))
            # Ainda incerta: mantém o degrau admitido, sem recarga.
            self.current=metrics(used_bytes=int(4.8*GIB),stable=False)
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],20)
            # 27/10 19:16: o 20 veio da incerteza e prendia o 9B com VRAM sobrando.
            # Com medição confiável que comporta 32 (mesma margem), sobe uma única vez.
            self.current=metrics(used_bytes=int(4.8*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            self.assertNotIn(key,gpu_resource._uncertain_offload)
            resident[0].update(vram_bytes=int(5.23*GIB),observed_at=time.time())
            self.current=metrics(used_bytes=int(6.0*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)  # admitido por medição: não sobe de novo

    def test_resident_same_profile_does_not_count_workspace_twice(self):
        # 27/10 20:04: 32 camadas já carregadas, Minecraft aberto; a fila esperava por 512 MiB já alocados.
        key='k';policy=dict(rm.gpu_policy())
        models=[dict(model_key=key,observed_at=time.time(),vram_bytes=int(5.23*GIB))]
        request=dict(owner='llm',model_key=key,vram_bytes=int(5.5*GIB),workspace_bytes=512*1024**2,overlap_safe=True)
        self.assertTrue(rm.assess_gpu(request,metrics(used_bytes=int(6.75*GIB)),models=models,policy=policy)['allowed'])
        # Pesos menores residentes (outro degrau): a carga nova ainda conta o espaço de trabalho.
        smaller=[dict(models[0],vram_bytes=int(3.57*GIB))]
        decision=rm.assess_gpu(request,metrics(used_bytes=int(5.2*GIB)),models=smaller,policy=policy)
        self.assertEqual(decision['additional_bytes'],int(5.5*GIB)-int(3.57*GIB)+512*1024**2)
        self.assertEqual(policy['margin_bytes'],768*1024**2)  # a margem de segurança não muda

    def test_human_fixed_gpu_layers_skip_the_dynamic_ladder(self):
        # 27/10: pedido humano de camada fixa; a escada caía para 20 com VRAM sobrando.
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='validated20',expected_latency=15,fallback_latency=120)]
        captured=[]
        @contextlib.contextmanager
        def compute(*args,**kwargs):captured.append(kwargs);yield dict(backend='gpu')
        path=Path(config.ENTITY_CONFIG_DIR)/'executores.json';original=path.read_text() if path.exists() else None
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            for value,expected in ((32,32),(27,None)):  # 27 não é degrau medido: volta à escada
                path.write_text(json.dumps({'gpu_layers_fixed':value}))
                with self.subTest(value=value),patch.dict(gpu_resource._warm_offload,clear=True),\
                     patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'compute_lease',side_effect=compute),\
                     patch.object(rm,'residency',return_value=[]):
                    self.current=metrics(used_bytes=int(1.6*GIB))  # a escada escolheria 28
                    with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                        self.assertEqual(acquired['gpu_layers'],expected or 28)
                    # Degrau fixo medido já inclui buffers; a escada continua reservando trabalho.
                    self.assertEqual(captured[-1]['workspace_bytes'],0 if expected else 512*1024**2)
            # 27/10 19:56: com o degrau fixo carregado e residência velha, o lease esperava 120 s.
            path.write_text(json.dumps({'gpu_layers_fixed':32}))
            key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
            stale=[dict(model_key=key,observed_at=time.time()-300,vram_bytes=int(5.23*GIB))]
            with patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'compute_lease',side_effect=compute),\
                 patch.object(rm,'residency',return_value=stale),patch.object(rm,'refresh_executor_state') as refreshed:
                with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                    self.assertEqual(acquired['gpu_layers'],32)
            self.assertTrue(refreshed.called)
            self.assertEqual(captured[0]['vram_bytes'],int(5.5*GIB))  # o lease ainda confere a VRAM
        finally:
            path.write_text(original) if original is not None else path.unlink()

    def test_stale_residency_is_refreshed_before_falling_to_the_base_profile(self):
        # 27/10 19:41: residência de 290 s atrás não contava os pesos de 32 camadas; caía para 20.
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='validated20',expected_latency=15,fallback_latency=120)]
        key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
        resident=[dict(model_key=key,observed_at=time.time()-290,vram_bytes=int(5.23*GIB))]
        def refresh(_base):resident[0]['observed_at']=time.time()
        @contextlib.contextmanager
        def compute(*args,**kwargs):yield dict(backend='gpu')
        with patch.dict(gpu_resource._warm_offload,clear=True),patch.object(gpu_resource,'_uncertain_offload',set()),\
             patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'compute_lease',side_effect=compute),\
             patch.object(rm,'residency',side_effect=lambda:[dict(r) for r in resident]),\
             patch.object(rm,'refresh_executor_state',side_effect=refresh) as refreshed:
            self.current=metrics(used_bytes=int(6.45*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            self.assertTrue(refreshed.called)
            # Pressão real com residência atual: cai para a base, mas marcada como não medida.
            gpu_resource._warm_offload.clear();resident[0].update(observed_at=time.time(),vram_bytes=0)
            self.current=metrics(used_bytes=int(5.0*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],20)
            self.assertIn(key,gpu_resource._uncertain_offload)

    def test_base_profile_admitted_by_measured_pressure_is_not_upgraded(self):
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='validated20',expected_latency=15,fallback_latency=120)]
        key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
        resident=[dict(model_key=key,observed_at=time.time(),vram_bytes=int(3.57*GIB))]
        @contextlib.contextmanager
        def compute(*args,**kwargs):yield dict(backend='gpu')
        with patch.dict(gpu_resource._warm_offload,{key:(20,int(4.25*GIB))},clear=True),\
             patch.object(gpu_resource,'_uncertain_offload',set()),patch.object(rm,'executor_catalog',return_value=catalog),\
             patch.object(rm,'compute_lease',side_effect=compute),patch.object(rm,'residency',return_value=resident):
            self.current=metrics(used_bytes=int(4.8*GIB))
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],20)  # não inventar upgrade de pesos já quentes

    def test_offload_candidate_denied_before_compute_does_not_become_warm_profile(self):
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='validated20',expected_latency=15,fallback_latency=120)]
        key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
        @contextlib.contextmanager
        def deny(*args,**kwargs):
            raise rm.GPUWaitTimeout('vram_pressure after candidate selection')
            yield
        with patch.dict(gpu_resource._warm_offload,clear=True),patch.object(rm,'executor_catalog',return_value=catalog),\
             patch.object(rm,'compute_lease',side_effect=deny),patch.object(rm,'residency',return_value=[]):
            self.current=metrics(used_bytes=int(.8*GIB))
            with self.assertRaises(rm.GPUWaitTimeout):
                with gpu_resource.lease('llm',model=config.MODEL_NAME):self.fail('compute started')
            self.assertNotIn(key,gpu_resource._warm_offload)

    def test_warm_profile_can_step_down_when_current_vram_no_longer_fits(self):
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(4.25*GIB),
                      gpu_layers=20,gpu_profile='validated20',expected_latency=15,fallback_latency=120)]
        key=config.OLLAMA_URL.rsplit('/api/',1)[0]+'|'+config.MODEL_NAME
        resident=[dict(model_key=key,observed_at=time.time(),vram_bytes=int(5.23*GIB))]
        @contextlib.contextmanager
        def compute(*args,**kwargs):yield dict(backend='gpu')
        with patch.dict(gpu_resource._warm_offload,{key:(32,int(5.5*GIB))},clear=True),\
             patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'compute_lease',side_effect=compute),\
             patch.object(rm,'residency',return_value=resident):
            self.current=metrics(used_bytes=int(7.1*GIB))  # pressão real: o workspace residente não é recontado
            with gpu_resource.lease('llm',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],31)
            self.assertEqual(rm.gpu_policy()['margin_bytes'],768*1024**2)

    def test_vision_reuses_measured_partial_profile_and_keeps_margin(self):
        catalog=[dict(model=config.MODEL_NAME,tier='principal',vram_bytes=int(5.5*GIB),
                      gpu_layers=32,gpu_profile='validated32',num_ctx=16384,expected_latency=15,fallback_latency=120)]
        captured=[]
        @contextlib.contextmanager
        def compute(*args,**kwargs):
            captured.append(kwargs);yield dict(backend='gpu')
        with patch.object(rm,'executor_catalog',return_value=catalog),patch.object(rm,'compute_lease',side_effect=compute),patch.object(rm,'residency',return_value=[]):
            self.current=metrics(used_bytes=GIB)
            with gpu_resource.lease('vision',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],32)
            self.current=metrics(used_bytes=2*GIB)
            with gpu_resource.lease('vision',model=config.MODEL_NAME) as acquired:
                self.assertEqual(acquired['gpu_layers'],26)
        self.assertTrue(all(not call['use_model_estimate'] for call in captured))
        self.assertTrue(all(call['priority']==3 for call in captured))
        self.assertEqual(rm.gpu_policy()['margin_bytes'],768*1024**2)


class ResidentFullLease(ExecutorTests):
    """30/10 (33 camadas): pela arbitragem real (compute_lease), o modelo inteiro na placa com o mesmo contexto não
    conta de novo a memória; sem a prova, ou com outro contexto, continua barrado (revisões Codex)."""
    def test_resident_full_is_proven_inside_compute_lease(self):
        MIB = 1024 ** 2
        key = BASE + '|principal9b:latest'
        rm.observe_model(BASE, 'principal9b:latest', 6253 * MIB)
        rm.record_memory_estimate(BASE, 'principal9b:latest', 6252 * MIB)
        rm.record_model_context(BASE, 'principal9b:latest', 16384)  # = NUM_CTX deste ambiente de teste
        self.current = metrics(used_bytes=7595 * MIB, total_bytes=8176 * MIB)
        lease = lambda **k: rm.compute_lease('llm', model_key=key, vram_bytes=7035 * MIB, workspace_bytes=0, wait=.3, **k)
        with patch.object(rm, 'gpu_policy', return_value=dict(rm.gpu_policy(), margin_bytes=512 * MIB)):
            with self.assertRaises(rm.GPUWaitTimeout):  # sem pedir a isenção: soma 782 MiB que já estão na placa
                with lease(): pass
            with lease(resident_full=True, resident_ctx=16384) as acquired:
                self.assertEqual(acquired['backend'], 'gpu')
            # Revisão Codex: o runner mudou para 4K enquanto esperava; a isenção não vale mais.
            rm.record_model_context(BASE, 'principal9b:latest', 4096)
            with self.assertRaises(rm.GPUWaitTimeout):
                with lease(resident_full=True, resident_ctx=16384): pass
            # Parcial na placa (32 camadas: tamanho total maior que a VRAM residente) também não vale.
            rm.record_model_context(BASE, 'principal9b:latest', 16384); rm.record_memory_estimate(BASE, 'principal9b:latest', 7204 * MIB)
            with self.assertRaises(rm.GPUWaitTimeout):
                with lease(resident_full=True, resident_ctx=16384): pass
        rm.record_model_context(BASE, 'principal9b:latest', 0)  # valor inválido não sobrescreve
        self.assertEqual(rm.model_context(key), 16384)


class OpportunisticTests(ExecutorTests):
    # Reutiliza o ambiente, não repete os testes herdados no discovery.
    def lease(self, **kwargs):
        return rm.compute_lease('batch',entity='alistair',model_key=BASE+'|alistair',priority=5,
            vram_bytes=3*GIB,workspace_bytes=512*1024**2,cpu_fallback=True,
            opportunistic=True,wait=.3,**kwargs)

    def test_idle_gpu_allowed_and_compute_released_without_unload(self):
        with self.lease() as result:
            self.assertEqual(result['backend'],'gpu')
            rm.observe_model(BASE,'alistair',3*GIB)
        self.assertEqual(rm.status(),[])
        self.assertEqual(rm.gpu_state()['residency'][0]['state'],'gpu_resident')

    def test_gpu_loading_also_requires_safe_ram(self):
        with patch.object(gpu_metrics,'ram_available',return_value=GIB),self.assertRaises(TimeoutError):
            with self.lease(): self.fail('GPU iniciou carregamento sem RAM de staging')

    def test_cpu_resident_weights_are_not_double_charged_for_gpu_loading(self):
        rm.observe_model(BASE,'alistair',0)
        with patch.object(gpu_metrics,'ram_available',return_value=4*GIB):
            with self.lease() as result: self.assertEqual(result['backend'],'gpu')

    def test_unknown_gpu_utilization_or_vram_uses_cpu(self):
        for changes in [dict(known=False),dict(utilization=None),dict(used_bytes=6*GIB)]:
            self.current = metrics(**changes)
            with self.lease() as result: self.assertEqual(result['backend'],'cpu')

    def test_reload_not_worth_it_uses_cpu(self):
        with self.lease(expected_latency=10,fallback_latency=15) as result:
            self.assertEqual(result['backend'],'cpu')

    def test_audio_priority_denies_opportunistic_gpu(self):
        with rm.lease('cpu_audio','test-audio'):
            with self.lease() as result: self.assertEqual(result['backend'],'cpu')

    def test_opportunistic_does_not_evict_other_models(self):
        self.current = metrics(used_bytes=6*GIB)
        prepare = Mock()
        with self.lease(prepare=prepare) as result: self.assertEqual(result['backend'],'cpu')
        prepare.assert_not_called()

    def test_active_hoshino_compute_does_not_get_interrupted(self):
        with rm.compute_lease('llm',entity='hoshino',priority=1,model_key='hoshino',vram_bytes=GIB,wait=.3):
            with self.lease() as result: self.assertEqual(result['backend'],'cpu')
            self.assertEqual(len(rm.status('gpu')),1)

    def test_waiting_hoshino_batch_also_denies_gpu(self):
        # Token kernel torna a fila simulada um pedido vivo, não stale.
        import fcntl
        rm._conn().close()
        with rm._lock_path('token-waiter').open('a+') as token:
            fcntl.flock(token,fcntl.LOCK_EX)
            with contextlib.closing(rm._conn()) as conn,conn:
                conn.execute('INSERT INTO gpu_requests VALUES(?,?,?,?,?)',('waiter',5,time.time()-1,'waiting',
                    json.dumps(dict(entity='hoshino',owner='batch',model_key='waiting',priority=5,vram_bytes=GIB,workspace_bytes=0))))
            with self.lease() as result: self.assertEqual(result['backend'],'cpu')

    def test_running_alistair_finishes_before_priority_job_without_killing(self):
        acquired=threading.Event(); errors=[]
        def foreground():
            try:
                with rm.compute_lease('llm',entity='hoshino',priority=1,vram_bytes=GIB,wait=2): acquired.set()
            except Exception as exc: errors.append(exc)
        with self.lease():
            thread = threading.Thread(target=foreground); thread.start()
            deadline=time.monotonic()+1
            while time.monotonic()<deadline and not rm.higher_priority_waiting(5): time.sleep(.01)
            self.assertTrue(rm.higher_priority_waiting(5)); self.assertFalse(acquired.is_set())
        thread.join(3)
        self.assertFalse(thread.is_alive()); self.assertTrue(acquired.is_set()); self.assertEqual(errors,[])

    def test_no_ram_no_gpu_fails_diagnosed_not_unsafe_fallback(self):
        self.current=metrics(known=False)
        with patch.object(gpu_metrics,'ram_available',return_value=None),self.assertRaises(TimeoutError):
            with self.lease(): self.fail('RAM incerta')
        self.assertEqual(rm.status(),[])

    def test_alistair_local_routing_gpu_and_cpu_options(self):
        alistair = object.__new__(Alistair)
        alistair.remote=None
        payload=dict(model='alistair',messages=[],options=dict(num_gpu=0,num_ctx=2048))
        with patch.object(config,'ENTIDADE_ID','alistair'),patch.object(alistair,'_observe_local'), \
             patch('alistair_runner.requests.post',return_value=response(dict(message={'content':'ok'}))) as post:
            self.assertEqual(alistair.infer(payload,'id')['message']['content'],'ok')
            self.assertEqual(post.call_args.kwargs['json']['options']['num_gpu'],-1)
            self.current=metrics(known=False)
            alistair.infer(payload,'next')
            self.assertEqual(post.call_args.kwargs['json']['options']['num_gpu'],0)
        self.assertEqual(payload['options']['num_gpu'],0); self.assertEqual(rm.status(),[])

    def test_remote_cpu_path_is_unchanged(self):
        alistair=object.__new__(Alistair)
        alistair.remote=Mock(); alistair.remote.infer.return_value={'message':{'content':'remote'}}
        with patch('alistair_runner.requests.post') as post:
            self.assertEqual(alistair.infer({'options':{'num_gpu':0}},'id')['message']['content'],'remote')
            post.assert_not_called()

    def test_cpu_runner_is_unloaded_before_opportunistic_gpu_request(self):
        alistair = object.__new__(Alistair)
        alistair.remote = None
        sequence = []
        def unload(*args, **kwargs):
            self.assertEqual(kwargs['model'], 'alistair')
            self.assertTrue(rm.status('gpu'))
            sequence.append('unload')
            return True, 'confirmed'
        def infer(*args, **kwargs):
            sequence.append('infer')
            return response(dict(message={'content':'ok'}))
        with patch.object(config, 'ENTIDADE_ID', 'alistair'), \
             patch.object(alistair, '_observe_local', return_value={'size_vram':0}), \
             patch.object(ollama_lifecycle, '_descarregar_modelo_sem_lease', side_effect=unload), \
             patch('alistair_runner.requests.post', side_effect=infer):
            alistair.infer(dict(model='alistair', messages=[], options={'num_gpu':0}), 'test')
        self.assertEqual(sequence, ['unload', 'infer'])
        self.assertEqual(rm.status(), [])

    def test_unconfirmed_cpu_unload_never_starts_gpu_inference(self):
        alistair = object.__new__(Alistair)
        alistair.remote = None
        with patch.object(config, 'ENTIDADE_ID', 'alistair'), \
             patch.object(alistair, '_observe_local', return_value={'size_vram':0}), \
             patch.object(ollama_lifecycle, '_descarregar_modelo_sem_lease', return_value=(False,'unconfirmed')), \
             patch('alistair_runner.requests.post') as post:
            with self.assertRaises(RuntimeError):
                alistair.infer(dict(model='alistair', messages=[], options={'num_gpu':0}), 'test')
            post.assert_not_called()
        self.assertEqual(rm.status(), [])


class InstallationTests(unittest.TestCase):
    def test_verifier_handles_existing_registry_and_hf_primary_names(self):
        importer=original_module('importer_manifest_regression','scripts/preparar_executores_leves.py')
        with tempfile.TemporaryDirectory() as tmp:
            storage=Path(tmp)
            for model,relative in ((LIGHT,'registry.ollama.ai/library/hoshino-qwen2.5-7b/latest'),
                                   (rm.HOSHINO_9B,'hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF/Q4_K_M'),
                                   ('namespace/model:tag','registry.ollama.ai/namespace/model/tag')):
                file=storage/'manifests'/relative;file.parent.mkdir(parents=True,exist_ok=True)
                file.write_text(json.dumps({'config':{'fixture':'config'},'layers':[{'fixture':'weights'}]}))
                self.assertEqual(importer.manifest_path(storage,model),file)
                self.assertEqual(importer.manifest_blobs(storage,model),[{'fixture':'config'},{'fixture':'weights'}])
            with self.assertRaises(ValueError):importer.manifest_path(storage,'../escape:tag')

    def setUp(self):
        self.installer=original_module('light_installer','scripts/preparar_executores_leves.py')
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_low_disk_blocks_before_network_or_write(self):
        with patch.object(self.installer.shutil,'disk_usage',return_value=SimpleNamespace(free=15*GIB)), \
             patch.object(self.installer.requests,'post') as post,patch.object(self.installer.requests,'get') as get:
            self.assertFalse(self.installer.plan(self.root)['safe'])
            with self.assertRaises(RuntimeError): self.installer.install(self.root)
            post.assert_not_called(); get.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_estimate_includes_two_copies_temporary_and_reserve(self):
        with patch.object(self.installer.shutil,'disk_usage',return_value=SimpleNamespace(free=40*GIB)):
            plan=self.installer.plan(self.root)
        self.assertTrue(plan['safe']); self.assertEqual(plan['estimated_final_bytes'],10*GIB)
        self.assertEqual(plan['required_bytes'],25*GIB)

    def test_sha_corruption_does_not_confirm_model(self):
        root=self.root
        path=root/'manifests/registry.ollama.ai/library/test/latest'
        path.parent.mkdir(parents=True)
        blob=root/('blobs/sha256-'+'a'*64); blob.parent.mkdir(); blob.write_bytes(b'abc')
        path.write_text(json.dumps(dict(config=dict(digest='sha256:'+'a'*64,size=3),layers=[])))
        with self.assertRaises(ValueError): self.installer.verify(root,'test:latest')

    def test_selected_import_rejects_wrong_entity_without_network(self):
        with patch.object(self.installer.requests,'get') as get,patch.object(self.installer.requests,'post') as post:
            with self.assertRaises(ValueError):
                self.installer.install_selected(self.root,entity='alistair',candidate='hunyuan-7b')
            get.assert_not_called();post.assert_not_called()

    def test_selected_import_validates_source_hash_before_network(self):
        path=self.root/'compartilhado/modelos/candidatos-20261008/fixture.gguf'
        path.parent.mkdir(parents=True);path.write_bytes(b'bad')
        with patch.dict(self.installer.SELECTION,{'hunyuan-7b':('fixture.gguf','a'*64,3)}), \
             patch.object(self.installer.requests,'post') as post,patch.object(self.installer.requests,'get') as get:
            with self.assertRaisesRegex(ValueError,'Hash'):
                self.installer.install_selected(self.root,entity='hoshino',candidate='hunyuan-7b')
            post.assert_not_called();get.assert_not_called()

    def test_selected_import_space_checked_before_upload(self):
        import hashlib
        path=self.root/'compartilhado/modelos/candidatos-20261008/fixture.gguf'
        path.parent.mkdir(parents=True);path.write_bytes(b'good')
        with patch.dict(self.installer.SELECTION,{'hunyuan-7b':('fixture.gguf',hashlib.sha256(b'good').hexdigest(),4)}), \
             patch.object(self.installer.requests,'post') as post, \
             patch.object(self.installer.requests,'get',return_value=response(dict(models=[]))), \
             patch.object(self.installer.shutil,'disk_usage',return_value=SimpleNamespace(free=19*GIB)):
            with self.assertRaises(RuntimeError):
                self.installer.install_selected(self.root,entity='hoshino',candidate='hunyuan-7b')
            post.assert_not_called()

    def test_selected_installed_alias_can_be_reused_without_download_copy(self):
        digest=self.installer.IMPORTED_WEIGHTS['qwen3.5-4b']
        size=self.installer.SELECTION['qwen3.5-4b'][2]
        verified=[dict(digest='sha256:'+digest,bytes=size)]
        with patch.object(self.installer,'installed',return_value=True), \
             patch.object(self.installer,'verify',return_value=verified), \
             patch.object(self.installer.requests,'get',return_value=response(dict(models=[]))), \
             patch.object(self.installer.requests,'post',return_value=response(dict(system=self.installer.NEUTRAL_SYSTEM))) as post:
            receipt=self.installer.install_selected(self.root,entity='alistair',candidate='qwen3.5-4b')
        self.assertFalse(receipt['activated'])
        self.assertEqual(post.call_count,1)
        self.assertTrue(post.call_args.args[0].endswith('/api/show'))

    def test_selected_installed_alias_with_foreign_weight_is_not_trusted(self):
        with patch.object(self.installer,'installed',return_value=True), \
             patch.object(self.installer,'verify',return_value=[dict(digest='sha256:'+'a'*64,bytes=1)]), \
             patch.object(self.installer.requests,'get',return_value=response(dict(models=[]))), \
             patch.object(self.installer.requests,'post') as post:
            with self.assertRaisesRegex(ValueError,'peso importado'):
                self.installer.install_selected(self.root,entity='alistair',candidate='qwen3.5-4b')
        post.assert_not_called()

    def test_stream_failure_is_not_install_success_or_auto_retry(self):
        failed=Mock(); failed.__enter__=Mock(return_value=failed); failed.__exit__=Mock(return_value=False)
        failed.iter_lines.return_value=[b'{"error":"denied"}']
        with patch.object(self.installer.requests,'post',return_value=failed) as post, \
             patch.object(self.installer,'guard'):
            with self.assertRaises(RuntimeError): self.installer.stream('http://local','/api/pull',{},self.root)
            self.assertEqual(post.call_count,1)
            self.assertEqual(post.call_args.kwargs['timeout'],(3,120))

    def test_alias_does_not_inherit_qwen_identity_when_empty_system_is_ignored(self):
        weight=dict(digest='sha256:'+'b'*64,bytes=42)
        for entity,(_,directory) in self.installer.ENTITIES.items():
            blob=self.root/'compartilhado/modelos'/directory/'blobs'/weight['digest'].replace(':','-')
            blob.parent.mkdir(parents=True); blob.write_bytes(b'x'*42)
        with patch.object(self.installer,'installed',return_value=True), \
             patch.object(self.installer,'verify',return_value=[weight]), \
             patch.object(self.installer,'guard'), \
             patch.object(self.installer.requests,'post',return_value=response(dict(system='You are Qwen'))), \
             patch.object(self.installer.requests,'get',return_value=response(dict(models=[
                 dict(name='hoshino-qwen2.5-7b:latest'),dict(name='lilith-qwen2.5-7b:latest')]))), \
             patch.object(self.installer,'stream') as stream:
            receipts=self.installer.install(self.root)['receipts']
        self.assertEqual(len(receipts),2)
        self.assertEqual(stream.call_count,2)
        for call in stream.call_args_list:
            self.assertEqual(call.args[1],'/api/create')
            self.assertEqual(call.args[2]['system'],self.installer.NEUTRAL_SYSTEM)



class ResidentStep(unittest.TestCase):
    """30/10 (33 camadas): com a isenção provada, assess_gpu não soma a memória que já está na placa."""
    def test_proven_exemption_does_not_recount(self):
        import time
        from core import resource_manager as rm
        MIB = 1024 ** 2
        key = 'http://127.0.0.1:11436|lilith'
        whole = [dict(model_key=key, vram_bytes=6253 * MIB, observed_at=time.time())]
        metrics = dict(known=True, stable=True, observed_at=time.time(), total_bytes=8176 * MIB, used_bytes=7595 * MIB, utilization=0)
        policy = dict(rm.gpu_policy(), margin_bytes=512 * MIB)
        request = dict(owner='llm', model_key=key, vram_bytes=7035 * MIB, workspace_bytes=0, overlap_safe=False)
        self.assertEqual(rm.assess_gpu(request, metrics, models=whole, policy=policy)['reason'], 'vram_pressure')
        ok = rm.assess_gpu(dict(request, resident_full=True), metrics, models=whole, policy=policy)
        self.assertTrue(ok['allowed']); self.assertEqual(ok['additional_bytes'], 0)
        cold = rm.assess_gpu(dict(request, resident_full=True), dict(metrics, used_bytes=1000 * MIB), models=[], policy=policy)
        self.assertEqual(cold['reason'], 'vram_pressure')  # sem residência, a carga a frio conta o orçamento cheio

if __name__=='__main__':
    # OpportunisticTests herda apenas fixture/helpers; evita rodar os mesmos
    # testes de executor novamente no contador de regressões.
    suite=unittest.TestSuite()
    loader=unittest.defaultTestLoader
    suite.addTests(loader.loadTestsFromTestCase(ExecutorTests))
    for name in OpportunisticTests.__dict__:
        if name.startswith('test_'): suite.addTest(OpportunisticTests(name))
    suite.addTests(loader.loadTestsFromTestCase(InstallationTests))
    suite.addTests(loader.loadTestsFromTestCase(ResidentStep))  # 30/10
    suite.addTest(ResidentFullLease('test_resident_full_is_proven_inside_compute_lease'))  # só o próprio, não os herdados
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
