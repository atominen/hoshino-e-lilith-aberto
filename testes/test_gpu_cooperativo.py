"""Fila real com locks/SQLite temporários; métricas AMD e daemons simulados."""
import contextlib
import importlib.util
import json
import multiprocessing
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import resource_manager as rm, gpu_metrics, gpu_resource, job_bus
from tools import image_gen

GIB=1024**3
ROOT=Path(__file__).resolve().parents[1]
POLICY=dict(margin_bytes=768*1024**2,concurrency_validated=False,max_compute=2,
            max_utilization=55,sticky_seconds=90,interactive_grace_seconds=0,ram_margin_bytes=2*GIB)


def module(name, file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file)
    result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def metrics(**overrides):
    return dict(known=True,stable=True,total_bytes=8*GIB,used_bytes=0,utilization=0,
                observed_at=time.time(),**overrides) if not overrides else {
        **metrics(),**overrides}


def request(**overrides):
    return dict(owner='llm',model_key='a',vram_bytes=GIB,workspace_bytes=0,
        overlap_safe=True,**overrides) if not overrides else {**request(),**overrides}


def child_compute(ready):
    with rm.compute_lease('llm',vram_bytes=GIB,workspace_bytes=0,wait=1):
        ready.set()
        threading.Event().wait(10)


class RamPromptCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ram-prompt-cache-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root/'compartilhado/config'
        self.folder.mkdir(parents=True)
        self.policy_path = self.folder/'gpu.json'
        p = patch.object(rm.config, 'RAIZ', self.root)
        p.start(); self.addCleanup(p.stop)
        self.memory = dict(total_bytes=31*GIB, available_bytes=22*GIB)

    def plan(self, memory=None):
        return rm.ram_prompt_cache_plan(memory=self.memory if memory is None else memory)

    def configure(self, fields):
        self.policy_path.write_text(json.dumps({'concurrency_validated':False, 'ram_prompt_cache':fields}))

    def test_default_is_aggregate_not_eight_gib_for_every_runner(self):
        plan = self.plan()
        self.assertEqual(plan['per_entity_mib'], dict(hoshino=3584, lilith=3584, alistair=1024))
        self.assertEqual(plan['aggregate_mib'], 8192)
        self.assertLessEqual(sum(plan['per_entity_mib'].values()), plan['budget_mib'])
        self.assertIsNone(plan['used_bytes'])
        self.assertEqual(plan['state'], 'planned_not_verified')

    def test_zero_is_a_valid_cache_limit_and_does_not_change_model_offload(self):
        self.configure(dict(budget_mib=8192, per_entity_mib=dict(hoshino=0,lilith=4096,alistair=1024)))
        plan = self.plan()
        self.assertEqual(plan['per_entity_mib']['hoshino'], 0)
        env = rm.ram_prompt_cache_environment('hoshino', {}, plan=plan)
        self.assertEqual(env['LLAMA_ARG_CACHE_RAM'], '0')
        self.assertNotIn('num_gpu', env)
        self.configure(dict(budget_mib=0, per_entity_mib=dict(hoshino=0,lilith=0,alistair=0)))
        self.assertEqual(self.plan()['aggregate_mib'], 0)

    def test_invalid_or_unlimited_configuration_disables_cache_instead_of_crashing(self):
        for value in (-1, True, '8192', None, float('inf')):
            with self.subTest(value=value):
                self.configure(dict(budget_mib=value, per_entity_mib=dict(hoshino=3584,lilith=3584,alistair=1024)))
                plan = self.plan()
                self.assertFalse(plan['valid'])
                self.assertEqual(plan['aggregate_mib'], 0)
        self.policy_path.write_text('{invalid-json')
        self.assertFalse(self.plan()['valid'])
        for text in ('[]','null','true'):
            with self.subTest(document=text):
                self.policy_path.write_text(text)
                self.assertFalse(self.plan()['valid'])
                self.assertEqual(self.plan()['aggregate_mib'],0)
                self.assertFalse(rm.gpu_policy()['concurrency_validated'])

    def test_combined_allocations_must_fit_and_unknown_fields_are_not_rewritten(self):
        self.configure(dict(budget_mib=8192, per_entity_mib=dict(hoshino=8192,lilith=8192,alistair=1024)))
        before = self.policy_path.read_bytes()
        self.assertFalse(self.plan()['valid'])
        self.assertEqual(self.plan()['aggregate_mib'], 0)
        self.assertEqual(self.policy_path.read_bytes(), before)

    def test_small_or_uncertain_ram_does_not_use_swap_to_enable_cache(self):
        for memory in ({}, dict(total_bytes=None, available_bytes=None),
                       dict(total_bytes=31*GIB, available_bytes=2*GIB, swap_free=100*GIB)):
            with self.subTest(memory=memory):
                self.assertEqual(self.plan(memory)['aggregate_mib'], 0)
        plan = self.plan(dict(total_bytes=12*GIB, available_bytes=10*GIB))
        self.assertLessEqual(plan['aggregate_mib']*1024**2, 4*GIB)

    def test_headroom_bounds_the_combined_caps_not_each_share_separately(self):
        plan=self.plan(dict(total_bytes=31*GIB,available_bytes=7*GIB))
        self.assertLessEqual(plan['aggregate_mib'],1024)
        self.assertEqual(plan['reason'],'ram_headroom_limited')
        self.assertLessEqual(plan['per_entity_mib']['hoshino'],3584)

    def test_ram_total_probe_does_not_add_swap_or_guess_unreadable_capacity(self):
        path=self.root/'meminfo';path.write_text('MemTotal: 12582912 kB\nSwapTotal: 8388608 kB\n')
        self.assertEqual(gpu_metrics.ram_total(path),12*GIB)
        path.write_text('MemTotal: invalid kB\n');self.assertIsNone(gpu_metrics.ram_total(path))
        path.write_text('SwapTotal: 8388608 kB\n');self.assertIsNone(gpu_metrics.ram_total(path))
        self.assertIsNone(gpu_metrics.ram_total(self.root/'absent'))

    def test_environment_clamps_inherited_limit_and_never_returns_secrets(self):
        plan = self.plan()
        for value, expected in (('0','0'), ('256','256'), ('999999','3584'), ('-1','3584'), ('invalid','3584')):
            inherited = dict(LLAMA_ARG_CACHE_RAM=value, OLLAMA_MAX_LOADED_MODELS='5',
                             OLLAMA_NUM_PARALLEL='4', ELEVENLABS_API_KEY='unit-test-secret')
            before = dict(inherited)
            with self.subTest(value=value):
                env = rm.ram_prompt_cache_environment('hoshino', inherited, plan=plan)
                self.assertEqual(env['LLAMA_ARG_CACHE_RAM'], expected)
                self.assertEqual(env['OLLAMA_MAX_LOADED_MODELS'], '1')
                self.assertEqual(env['OLLAMA_NUM_PARALLEL'], '1')
                self.assertNotIn('ELEVENLABS_API_KEY', env)
                self.assertEqual(inherited, before)
        with self.assertRaises(ValueError):
            rm.ram_prompt_cache_environment('unknown', {}, plan=plan)

    def test_legacy_probe_boot_applies_same_bounded_cache_environment(self):
        probe = module('cache_probe_boot', 'scripts/preparar_tres_modelos.py')
        healthy = Mock()
        proc = Mock()
        proc.poll.return_value = None
        with patch.object(probe, 'ROOT', self.root), \
             patch.object(probe.requests, 'get', side_effect=[probe.requests.ConnectionError(), healthy]), \
             patch.object(probe.subprocess, 'Popen', return_value=proc) as start, \
             patch.object(gpu_metrics, 'ram_total', return_value=31*GIB), \
             patch.object(gpu_metrics, 'ram_available', return_value=22*GIB), \
             patch.dict(os.environ, {'LLAMA_ARG_CACHE_RAM':'999999', 'OLLAMA_NUM_PARALLEL':'4'}):
            self.assertEqual(probe.ensure_daemon('hoshino', 11435), 'http://127.0.0.1:11435')
        env = start.call_args.kwargs['env']
        self.assertEqual(env['LLAMA_ARG_CACHE_RAM'], '3584')
        self.assertEqual(env['OLLAMA_MAX_LOADED_MODELS'], '1')
        self.assertEqual(env['OLLAMA_NUM_PARALLEL'], '1')
        self.assertEqual(env['OLLAMA_MODELS'], str(self.root/'compartilhado/modelos/ollama'))

    def test_legacy_probe_leaves_live_daemon_untouched_and_rejects_foreign_endpoint(self):
        probe = module('cache_probe_live', 'scripts/preparar_tres_modelos.py')
        with patch.object(probe.requests, 'get', return_value=Mock()) as get, \
             patch.object(probe.subprocess, 'Popen') as start, \
             patch.object(rm, 'ram_prompt_cache_environment') as cache_env:
            self.assertEqual(probe.ensure_daemon('lilith', 11436), 'http://127.0.0.1:11436')
            start.assert_not_called()
            cache_env.assert_not_called()
            get.reset_mock()
            for entity, port in (('lilith',11435), ('foreign',11438)):
                with self.subTest(entity=entity, port=port), self.assertRaises(ValueError):
                    probe.ensure_daemon(entity,port)
            get.assert_not_called()


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='gpu-cooperative-test-')
        self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.current=metrics(); self.policy=dict(POLICY); self.events=[]
        for obj,name,value in [(rm,'DB_PATH',self.root/'resources.db'),(rm,'LOCK_DIR',self.root/'locks'),
            (job_bus,'DB_PATH',self.root/'jobs.db')]:
            p=patch.object(obj,name,value); p.start(); self.addCleanup(p.stop)
        for obj,name,kwargs in [(gpu_metrics,'snapshot',dict(side_effect=lambda:{**self.current,'observed_at':time.time()})),
            (gpu_metrics,'ram_available',dict(return_value=31*GIB)),
            (rm,'gpu_policy',dict(side_effect=lambda:self.policy)),
            (rm.diagnostics,'emit',dict(side_effect=lambda *a,**k:self.events.append((a,k))))]:
            p=patch.object(obj,name,**kwargs); p.start(); self.addCleanup(p.stop)
        self.errors=[]; self.threads=[]
        self.addCleanup(self.join_threads)

    def join_threads(self):
        for thread,release in self.threads:
            release.set(); thread.join(3)
            self.assertFalse(thread.is_alive(),'Lease de teste ficou travado')

    def lease(self, **kwargs):
        return rm.compute_lease('llm',vram_bytes=GIB,workspace_bytes=0,wait=.2,**kwargs)

    def start_job(self, label, *, priority=1, release=None, order=None, **kwargs):
        entered=threading.Event(); release=release or threading.Event()
        def run():
            try:
                with rm.compute_lease('llm',priority=priority,model_key=label,vram_bytes=GIB,
                                      workspace_bytes=0,overlap_safe=True,wait=3,**kwargs):
                    if order is not None: order.append(label)
                    entered.set(); release.wait(3)
            except Exception as exc: self.errors.append(exc)
        thread=threading.Thread(target=run); thread.start(); self.threads.append((thread,release))
        return entered,release,thread

    def await_queue(self, count):
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            if len([r for r in rm.gpu_state()['queue'] if r['state']=='waiting'])>=count: return
            time.sleep(.01)
        self.fail('Pedidos não chegaram à fila')

    def test_hard_limit_margin_and_resident_weights(self):
        bad=request(vram_bytes=8*GIB)
        self.assertEqual(rm.assess_gpu(bad,metrics(total_bytes=16*GIB),policy=self.policy)['reason'],
                         'estimate_exceeds_hard_limit')
        big=request(vram_bytes=6*GIB,workspace_bytes=512*1024**2)
        self.assertFalse(rm.assess_gpu(big,metrics(used_bytes=2*GIB),policy=self.policy)['allowed'])
        resident=[dict(model_key='a',vram_bytes=6*GIB,observed_at=time.time())]
        fit=rm.assess_gpu(big,metrics(used_bytes=6*GIB),models=resident,policy=self.policy)
        # Mesmos pesos residentes: KV e buffers já alocados na carga, sem workspace recontado (27/10).
        self.assertTrue(fit['allowed']); self.assertEqual(fit['additional_bytes'],0)
        resident[0]['observed_at']-=60
        self.assertFalse(rm.assess_gpu(big,metrics(used_bytes=6*GIB),models=resident,policy=self.policy)['allowed'])

    def test_image_budget_adapts_to_desktop_usage_without_unsafe_admission(self):
        self.current=metrics(used_bytes=GIB)
        with rm.compute_lease('image',vram_bytes=7*GIB,workspace_bytes=0,flexible_min_bytes=4*GIB,wait=.2) as result:
            self.assertEqual(result['vram_budget_bytes'],int(6.25*GIB))
            self.assertLessEqual(self.current['used_bytes']+result['vram_budget_bytes']+self.policy['margin_bytes'],8*GIB)
            row=rm.gpu_state()['queue'][0]['request']
            self.assertEqual(row['requested_vram_bytes'],7*GIB)
            self.assertEqual(row['vram_bytes'],result['vram_budget_bytes'])
        self.current=metrics(used_bytes=5*GIB)
        with self.assertRaises(TimeoutError):
            with rm.compute_lease('image',vram_bytes=7*GIB,workspace_bytes=0,flexible_min_bytes=4*GIB,wait=.1):
                self.fail('Reduziu VRAM além do piso seguro')

    def test_unknown_stale_metrics_and_ram_fallback_are_safe(self):
        for value in (metrics(known=False),metrics(observed_at=time.time()-10)):
            self.assertEqual(rm.assess_gpu(request(),value,policy=self.policy)['reason'],'uncertain_vram')
        self.current=metrics(known=False)
        with self.lease(cpu_fallback=True) as result:
            self.assertEqual(result['backend'],'cpu'); self.assertEqual(rm.status()[0]['resource'],'cpu_llm')
        for available in (None,GIB):
            with patch.object(gpu_metrics,'ram_available',return_value=available),self.assertRaises(TimeoutError):
                with self.lease(cpu_fallback=True): self.fail('RAM desconhecida não pode permitir fallback')
        self.assertEqual(rm.status(),[]); self.assertEqual(rm.gpu_state()['queue'],[])

    def test_compute_release_preserves_residency_and_logs_duration(self):
        rm.observe_model('local','hot',0,used=True)
        with self.lease(model_key='local|hot',priority=0) as result:
            self.assertEqual(result['backend'],'gpu')
            self.assertEqual(rm.status('gpu')[0]['priority'],0)
        self.assertEqual(rm.status('gpu'),[])
        self.assertEqual(rm.residency()[0]['vram_bytes'],0)
        released=[k for a,k in self.events if a[0]=='gpu.compute_released'][0]
        self.assertIn('duration_seconds',released); self.assertIn('vram_before',released); self.assertIn('vram_after',released)

    def test_observed_reload_cost_preserves_vram_measurement(self):
        rm.observe_model('local','hot',2*GIB)
        observed=rm.residency()[0]['observed_at']; rm.record_reload('local','hot',31)
        row=rm.residency()[0]
        self.assertEqual(row['vram_bytes'],2*GIB); self.assertEqual(row['reload_seconds'],31)
        self.assertEqual(row['observed_at'],observed)
        rm.record_reload('local','new',9)
        row=next(r for r in rm.residency() if r['model']=='new')
        self.assertIsNone(row['vram_bytes']); self.assertEqual(row['observed_at'],0)

    def test_reported_model_size_avoids_unnecessary_cpu_without_dropping_margin(self):
        size=6004796292; rm.record_memory_estimate('local','qwen',size)
        self.current=metrics(used_bytes=850*1024**2)
        with rm.compute_lease('llm',model_key='local|qwen',use_model_estimate=True,cpu_fallback=True,wait=.2) as result:
            self.assertEqual(result['backend'],'gpu'); self.assertEqual(result['vram_budget_bytes'],size)
            self.assertLessEqual(self.current['used_bytes']+result['additional_bytes']+self.policy['margin_bytes'],8*GIB)

    def test_interactive_grace_cpu_fallback_reports_real_admission_reason(self):
        self.policy['interactive_grace_seconds'] = 30
        with self.lease(priority=1):
            pass
        args = dict(entity='alistair', model_key='local|alistair', priority=5,
                    vram_bytes=GIB, workspace_bytes=0, opportunistic=True,
                    cpu_fallback=True, wait=.2)
        with rm.compute_lease('batch', **args) as result:
            self.assertEqual(result['backend'], 'cpu')
            self.assertFalse(result['allowed'])
            self.assertEqual(result['reason'], 'interactive_grace')
        acquired = [data for event,data in self.events if event[0]=='gpu.compute_acquired'][-1]
        self.assertEqual(acquired['reason'], 'interactive_grace')
        self.assertEqual(acquired['fallback'], 'cpu')
        with contextlib.closing(rm._conn()) as conn, conn:
            conn.execute("UPDATE gpu_meta SET value=? WHERE name='interactive'", (time.time()-60,))
        with rm.compute_lease('batch', **args) as result:
            self.assertEqual(result['backend'], 'gpu')
            self.assertEqual(result['reason'], 'fits')
        self.assertEqual(rm.status(), [])

    def test_large_model_estimate_also_increases_cpu_ram_requirement(self):
        rm.record_memory_estimate('local','large',40*GIB)
        with self.assertRaises(TimeoutError):
            with rm.compute_lease('llm',model_key='local|large',use_model_estimate=True,cpu_fallback=True,wait=.1):
                self.fail('Modelo grande iniciou GPU/CPU sem memória suficiente')

    def test_reload_telemetry_failure_is_diagnosed_without_losing_response(self):
        with patch.object(rm,'_conn',side_effect=OSError('simulated disk')),patch.object(rm.diagnostics,'persistence_failure') as failure:
            self.assertFalse(rm.record_reload('local','test',8))
        self.assertEqual(failure.call_args.args[0],'gpu.record_reload')
        self.assertTrue(failure.call_args.kwargs['retry_safe'])

    def test_priority_fifo_does_not_steal_running_compute(self):
        order=[]; first,release,t=self.start_job('running',order=order)
        self.assertTrue(first.wait(1))
        low,lrelease,lt=self.start_job('batch',priority=5,order=order); self.await_queue(1)
        high,hrelease,ht=self.start_job('interactive',priority=1,order=order); self.await_queue(2)
        self.assertFalse(high.is_set()); self.assertFalse(low.is_set()); release.set()
        self.assertTrue(high.wait(1)); self.assertFalse(low.is_set()); hrelease.set()
        self.assertTrue(low.wait(1)); lrelease.set()
        for th in (t,lt,ht): th.join(2)
        self.assertEqual(order,['running','interactive','batch']); self.assertEqual(self.errors,[])

    def test_concurrency_requires_validation_capacity_and_stability(self):
        running=request(model_key='other',additional_bytes=GIB)
        self.assertEqual(rm.assess_gpu(request(),metrics(),[running],policy=self.policy)['reason'],
                         'serialize_for_stability')
        self.policy['concurrency_validated']=True
        self.assertTrue(rm.assess_gpu(request(),metrics(),[running],policy=self.policy)['allowed'])
        for bad in (metrics(stable=False),metrics(utilization=None),metrics(utilization=80),metrics(used_bytes=6*GIB)):
            self.assertFalse(rm.assess_gpu(request(),bad,[running],policy=self.policy)['allowed'])
        for active in ([request(owner='image')],[request(model_key='a')],[running,running]):
            self.assertFalse(rm.assess_gpu(request(),metrics(),active,policy=self.policy)['allowed'])
        entered,release,thread=self.start_job('one'); self.assertTrue(entered.wait(1))
        with self.lease(model_key='two',overlap_safe=True): self.assertEqual(len(rm.status('gpu')),2)
        release.set(); thread.join(1); self.assertEqual(self.errors,[])

    def test_legacy_exclusive_gpu_lock_is_respected(self):
        with rm.lease('gpu','legacy',wait=1),self.assertRaises(TimeoutError):
            with self.lease(): self.fail('Passou por lock exclusivo legado')

    def test_cpu_model_cannot_be_reconfigured_or_unloaded_while_generating(self):
        self.current=metrics(known=False)
        entered,release,thread=self.start_job('same',cpu_fallback=True); self.assertTrue(entered.wait(1))
        self.current=metrics()
        prepare=Mock()
        with self.assertRaisesRegex(TimeoutError,'same_model_busy_cpu'):
            with self.lease(model_key='same',prepare=prepare): self.fail('Modelo em CPU foi reconfigurado')
        prepare.assert_not_called()
        with self.assertRaises(TimeoutError):
            with rm.lease('gpu','unload',wait=.1): self.fail('Unloaded durante geração CPU')
        with self.lease(model_key='other',prepare=prepare): pass
        prepare.assert_not_called(); release.set(); thread.join(1)

    def test_gpu_model_cannot_fall_back_to_cpu_while_same_runner_generates(self):
        entered, release, thread = self.start_job('same')
        self.assertTrue(entered.wait(1))
        with self.assertRaisesRegex(TimeoutError, 'same_model_busy'):
            with self.lease(model_key='same', cpu_fallback=True):
                self.fail('Fallback CPU reconfigurou o runner ainda em GPU')
        self.assertEqual(len(rm.status('gpu')), 1)
        self.assertEqual(rm.status('cpu_llm'), [])
        release.set(); thread.join(1)
        with self.lease(model_key='same', cpu_fallback=True) as acquired:
            self.assertEqual(acquired['backend'], 'gpu')

    def test_crashed_compute_process_releases_kernel_token_without_ttl_guess(self):
        ctx=multiprocessing.get_context('fork'); ready=ctx.Event()
        child=ctx.Process(target=child_compute,args=(ready,)); child.start()
        try:
            self.assertTrue(ready.wait(2))
            with self.assertRaises(TimeoutError):
                with self.lease(): self.fail('Compute simultâneo ao filho')
        finally:
            child.terminate(); child.join(3)
        self.assertFalse(child.is_alive()); self.assertEqual(rm.status('gpu'),[])
        with self.lease(): pass

    def test_cancel_waiting_never_runs_or_leaves_queue(self):
        cancel=threading.Event(); cancel.set()
        self.assertTrue(issubclass(rm.GPUCancelledBeforeCompute,InterruptedError))
        with self.assertRaises(rm.GPUCancelledBeforeCompute):
            with self.lease(cancel=cancel): self.fail('Executou pedido cancelado')
        self.assertEqual(rm.gpu_state()['queue'],[])

    def test_interactive_cpu_audio_precedes_image_without_fake_gpu_compute(self):
        with rm.lease('cpu_audio','audio_tts'):
            self.assertTrue(rm.interactive_audio_active())
            self.assertTrue(rm.higher_priority_waiting(2,include_audio=True))
            self.assertFalse(rm.higher_priority_waiting(2))
            self.assertEqual(rm.status('gpu'),[])
            with self.assertRaises(TimeoutError):
                with rm.compute_lease('image',vram_bytes=GIB,workspace_bytes=0,wait=.1):
                    self.fail('Imagem começou durante áudio interativo')
        self.assertFalse(rm.interactive_audio_active())

    def test_live_lease_not_expired_and_abandoned_request_reconciles(self):
        with self.lease():
            with contextlib.closing(rm._conn()) as conn,conn:
                conn.execute('UPDATE leases SET expires_at=0')
            self.assertEqual(len(rm.status('gpu')),1)
        with contextlib.closing(rm._conn()) as conn,conn:
            conn.execute("INSERT INTO gpu_requests VALUES('dead',5,0,'waiting',?)",(json.dumps(request()),))
        with self.lease(): self.assertFalse(any(r['token']=='dead' for r in rm.gpu_state()['queue']))

    def test_existing_database_is_extended_without_losing_legacy_lease(self):
        with rm.lease('cpu_audio','existing',entity='lilith'):
            self.assertEqual(rm.status()[0]['owner'],'existing')
            with self.lease(): self.assertEqual(len(rm.status()),2)
            self.assertEqual(rm.status()[0]['entity'],'lilith')

    def test_image_cancellation_does_not_claim_resume_or_retry(self):
        job='image-interrupt'; image_gen._JOBS[job]={'status':'queued'}
        self.addCleanup(image_gen._JOBS.pop,job,None)
        job_bus.publish(job,image_gen.config.ENTIDADE_ID,'queued')
        with patch.object(image_gen.gpu_resource,'lease',side_effect=lambda *a,**k:contextlib.nullcontext()),\
             patch.object(image_gen,'_executar_sd',side_effect=image_gen.ImageYielded('sem retomada')) as run:
            image_gen._gerar_job(job,dict(destino=str(self.root/'partial.png')))
        run.assert_called_once(); persisted=job_bus.get(job)
        self.assertEqual(persisted['status'],'interrupted')
        self.assertFalse(persisted['details']['auto_retry']); self.assertFalse(persisted['details']['resume_supported'])

    def test_image_only_terminates_its_owned_child_and_waits_before_release(self):
        child=Mock(poll=Mock(return_value=None)); cli=self.root/'sd-cli'; cli.touch()
        p=dict(cfg=1,passos=1,largura=256,altura=256,prompt='test',destino=str(self.root/'test.png'),negative_prompt='',seed=1)
        with patch.object(image_gen,'_sd_cli',return_value=str(cli)),\
             patch.object(image_gen,'_modelos',return_value=dict(diffusion='d',vae='v',llm='l')),\
             patch.object(image_gen.subprocess,'Popen',return_value=child) as spawn,\
             patch.object(rm,'higher_priority_waiting',return_value=True),\
             patch.object(os,'kill') as kill, self.assertRaises(image_gen.ImageYielded):
            image_gen._executar_sd(p,self.root/'owned.log','job')
        child.terminate.assert_called_once(); child.wait.assert_called_once_with(timeout=5)
        child.kill.assert_not_called(); kill.assert_not_called(); spawn.assert_called_once()

    def test_granted_image_budget_reaches_vulkan_cli_without_changing_resolution(self):
        child=Mock(returncode=0,poll=Mock(return_value=0)); cli=self.root/'sd-cli'; cli.touch()
        p=dict(cfg=1,passos=16,largura=768,altura=768,prompt='test',destino=str(self.root/'test.png'),
               negative_prompt='',seed=1,gpu_vram_gib=6.25)
        with patch.object(image_gen,'_sd_cli',return_value=str(cli)),\
             patch.object(image_gen,'_modelos',return_value=dict(diffusion='d',vae='v',llm='l')),\
             patch.object(image_gen.subprocess,'Popen',return_value=child) as spawn:
            image_gen._executar_sd(p,self.root/'owned.log','job')
        cmd=spawn.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--max-vram')+1],'6.25')
        self.assertEqual(cmd[cmd.index('-W')+1],'768'); self.assertEqual(cmd[cmd.index('--steps')+1],'16')
        self.assertEqual(cmd[cmd.index('--backend')+1],image_gen.config.IMAGE_BACKEND)

    def test_turn_cancellation_context_prevents_queued_gpu_work(self):
        with gpu_resource.priority(1,cancel=lambda:True),self.assertRaises(InterruptedError):
            with gpu_resource.lease('llm'): self.fail('Executou geração de turno cancelado')
        self.assertIsNone(gpu_resource._cancellation.get())

    def residency_adapter(self, *, hot=False, pressure=True):
        adapter=module('gpu_resource_original_test','app/core/gpu_resource.py')
        base='http://127.0.0.1:11436'; present=[True]
        rm.observe_model(base,'peer',4*GIB)
        if not hot:
            with contextlib.closing(rm._conn()) as conn,conn:
                conn.execute('UPDATE gpu_residency SET last_used=0')
        self.current=metrics(used_bytes=4*GIB if pressure else 0)
        def get(url,**_kwargs):
            models=[dict(name='peer',size_vram=4*GIB)] if url.startswith(base) and present[0] else []
            return Mock(json=Mock(return_value={'models':models}))
        def post(*_args,**_kwargs):
            present[0]=False; self.current=metrics(); return Mock()
        scope=adapter._request.set(dict(owner='image',model_key='',vram_bytes=7*GIB,workspace_bytes=0,
            priority=4,expected_latency=120,fallback_latency=600))
        self.addCleanup(adapter._request.reset,scope)
        return adapter,get,post

    def test_hot_weights_sticky_and_no_unload_when_memory_fits(self):
        for hot,pressure in ((True,True),(False,False)):
            adapter,get,post=self.residency_adapter(hot=hot,pressure=pressure)
            with patch.object(adapter.requests,'get',side_effect=get),patch.object(adapter.requests,'post',side_effect=post) as unload:
                self.assertEqual(adapter.prepare_residency('image'),[])
                unload.assert_not_called()
            self.assertEqual(rm.residency()[0]['model'],'peer')

    def test_waiting_main_peer_can_release_idle_hot_weights_without_lowering_margin(self):
        adapter,get,post=self.residency_adapter(hot=True,pressure=True)
        adapter._request.get().update(owner='llm',priority=2,
            queue_started_monotonic=time.monotonic()-61,wait_budget_seconds=120)
        with patch.object(adapter.requests,'get',side_effect=get),\
             patch.object(adapter.requests,'post',side_effect=post) as unload:
            self.assertEqual(adapter.prepare_residency('llm'),['peer'])
        self.assertEqual(unload.call_args.kwargs['json']['keep_alive'],0)
        self.assertEqual(rm.gpu_policy()['margin_bytes'],POLICY['margin_bytes'])

    def test_hot_main_peer_is_not_evicted_before_fair_wait(self):
        adapter,get,post=self.residency_adapter(hot=True,pressure=True)
        adapter._request.get().update(owner='llm',priority=2,
            queue_started_monotonic=time.monotonic()-5,wait_budget_seconds=120)
        with patch.object(adapter.requests,'get',side_effect=get),\
             patch.object(adapter.requests,'post',side_effect=post) as unload:
            self.assertEqual(adapter.prepare_residency('llm'),[])
        unload.assert_not_called()

    def test_cold_weights_unloaded_only_for_pressure_and_verified_absence(self):
        adapter,get,post=self.residency_adapter()
        with patch.object(adapter.requests,'get',side_effect=get) as reads,patch.object(adapter.requests,'post',side_effect=post) as unload:
            self.assertEqual(adapter.prepare_residency('image'),['peer'])
        self.assertEqual(rm.residency(),[])
        self.assertTrue(all(':11434' not in call.args[0] for call in reads.call_args_list))
        self.assertEqual(unload.call_args.kwargs['json']['keep_alive'],0)

    def test_failed_unload_does_not_claim_memory_freed_or_leave_maintenance_lock(self):
        adapter,get,_post=self.residency_adapter()
        with patch.object(adapter.requests,'get',side_effect=get),patch.object(adapter.requests,'post',return_value=Mock()):
            with self.assertRaisesRegex(RuntimeError,'não liberou'):
                with self.lease(prepare=lambda:adapter.prepare_residency('image')): self.fail('unload não confirmado')
        self.assertEqual(len(rm.residency()),1); self.assertEqual(rm.gpu_state()['queue'],[])
        self.current=metrics()
        with self.lease(): pass

    def test_reload_cost_can_outweigh_eviction_benefit(self):
        adapter,get,post=self.residency_adapter()
        adapter._request.get()['fallback_latency']=125
        with patch.object(adapter.requests,'get',side_effect=get),patch.object(adapter.requests,'post',side_effect=post) as unload:
            self.assertEqual(adapter.prepare_residency('image'),[]); unload.assert_not_called()


class ProbesAndPolicyTests(unittest.TestCase):
    def test_amdgpu_probes_no_cuda_and_8_gib_hard_cap(self):
        probe=module('gpu_metrics_probe_test','app/core/gpu_metrics.py')
        with tempfile.TemporaryDirectory(prefix='amdgpu-fixture-') as tmp:
            root=Path(tmp); device=root/'card1/device'; device.mkdir(parents=True)
            for name,value in {'vendor':'0x1002','mem_info_vram_total':str(16*GIB),
                               'mem_info_vram_used':str(3*GIB),'gpu_busy_percent':'42'}.items():
                (device/name).write_text(value)
            result=probe.snapshot(root)
            self.assertTrue(result['known']); self.assertEqual(result['total_bytes'],8*GIB)
            self.assertEqual(result['used_bytes'],3*GIB); self.assertEqual(result['utilization'],42)
            (device/'mem_info_vram_used').write_text('uncertain')
            self.assertFalse(probe.snapshot(root)['known'])
            self.assertIsNone(probe.ram_available(root/'missing-meminfo'))

    def test_invalid_policy_cannot_enable_aggressive_concurrency(self):
        with tempfile.TemporaryDirectory(prefix='gpu-policy-') as tmp:
            root=Path(tmp); folder=root/'compartilhado/config'; folder.mkdir(parents=True)
            with patch.object(rm.config,'RAIZ',root):
                for val in ('oops',-1,float('nan'),None):
                    (folder/'gpu.json').write_text(json.dumps({'margin_bytes':val,'concurrency_validated':True}))
                    policy=rm.gpu_policy(); self.assertFalse(policy['concurrency_validated'])
                    self.assertGreaterEqual(policy['margin_bytes'],512*1024**2)
                (folder/'gpu.json').write_text(json.dumps({'concurrency_validated':'true'}))
                self.assertFalse(rm.gpu_policy()['concurrency_validated'])

    def test_margin_chosen_in_settings_goes_down_to_128_mib_floor(self):
        # 06/11 (pedido humano, desktop leve): a margem escolhida vale; abaixo de 128 MiB vira 128.
        with tempfile.TemporaryDirectory(prefix='gpu-policy-') as tmp:
            root=Path(tmp); folder=root/'compartilhado/config'; folder.mkdir(parents=True)
            with patch.object(rm.config,'RAIZ',root):
                for mib,expected in ((256,256),(128,128),(64,128),(4096,2048)):
                    (folder/'gpu.json').write_text(json.dumps({'margin_bytes':mib*1024**2}))
                    self.assertEqual(rm.gpu_policy()['margin_bytes'],expected*1024**2,mib)
        self.assertEqual(min(rm.MARGIN_OPTIONS_MIB)*1024**2,rm.MARGIN_MIN_BYTES)

    def test_cpu_payload_preserves_original_and_priority_classes(self):
        payload=dict(options={'temperature':.6})
        cpu=gpu_resource.routed_payload(payload,{'backend':'cpu'})
        self.assertEqual(cpu['options']['num_gpu'],0); self.assertNotIn('num_gpu',payload['options'])
        self.assertEqual([rm.PRIORITIES[n] for n in ('audio','llm','spontaneous','vision','image','batch')],list(range(6)))
        with gpu_resource.priority(5): self.assertEqual(gpu_resource._priority.get(),5)
        self.assertEqual(gpu_resource._priority.get(),1)

    def test_gpu_payload_overrides_cpu_default_and_preserves_partial_profile(self):
        payload = dict(options={'num_gpu':0, 'temperature':.6})
        gpu = gpu_resource.routed_payload(payload, {'backend':'gpu'})
        self.assertEqual(gpu['options']['num_gpu'], -1)
        partial = gpu_resource.routed_payload(payload, {'backend':'gpu', 'gpu_layers':20})
        self.assertEqual(partial['options']['num_gpu'], 20)
        self.assertEqual(payload['options']['num_gpu'], 0)

    def test_own_cpu_runner_unload_is_verified_before_gpu_use(self):
        adapter = module('gpu_adapter_cpu_profile', 'app/core/gpu_resource.py')
        base = adapter.config.OLLAMA_URL.rsplit('/api/',1)[0]
        model = 'own-cpu'
        row = dict(name=model, size_vram=0, size=7*GIB)
        request = dict(owner='llm', model_key=base+'|'+model, vram_bytes=5*GIB,
                       workspace_bytes=512*1024**2, priority=1, expected_latency=15,
                       fallback_latency=120, use_model_estimate=False)
        from core import ollama_lifecycle
        scope = adapter._request.set(request)
        try:
            get = lambda url, **k:Mock(json=Mock(return_value={'models':[row] if url.startswith(base) else []}))
            with patch.object(adapter.requests, 'get', side_effect=get), \
                 patch.object(ollama_lifecycle, '_descarregar_modelo_sem_lease', return_value=(True,'ok')) as unload:
                self.assertEqual(adapter.prepare_residency('llm'), [model])
                self.assertEqual(unload.call_args.kwargs['model'], model)
                self.assertEqual(request['vram_bytes'], 5*GIB)
            with patch.object(adapter.requests, 'get', side_effect=get), \
                 patch.object(ollama_lifecycle, '_descarregar_modelo_sem_lease', return_value=(False,'uncertain')):
                with self.assertRaisesRegex(RuntimeError, 'não confirmado'):
                    adapter.prepare_residency('llm')
        finally:
            adapter._request.reset(scope)



class VramGuardTests(unittest.TestCase):
    """Pedido humano 30/10: fechar o app aberto por último que ocupa a VRAM de que a entidade precisa."""
    MIB=1024**2
    PDEV='0000:03:00.0'

    def setUp(self):
        from core import vram_guard
        self.g=vram_guard
        self.tmp=tempfile.TemporaryDirectory(); self.proc=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.client=0
        self.make(1,0,1,'/sbin/init')
        self.make(2249,1,100,'/usr/bin/cinnamon',vram_mib=300)
        self.make(900,1,50,'/usr/local/lib/ollama/llama-server',vram_mib=6000)
        self.make(3000,2249,200,'/usr/lib/jvm/bin/java',vram_mib=1500)               # Minecraft, aberto antes
        self.make(4000,2249,400,'/usr/lib/firefox/firefox-bin',vram_mib=500,dup=True)  # Firefox, aberto por último
        self.make(4001,4000,401,'/usr/lib/firefox/firefox-bin',vram_mib=100)           # processo filho do Firefox
        self.make(4500,2249,450,'/usr/bin/gedit',vram_mib=20)                          # pequeno demais
        self.make(4600,2249,460,'/usr/bin/python3',vram_mib=800,cmd=str(ROOT/'app/main.py'))  # do projeto
        self.make(4700,2249,470,'/usr/bin/myterm',vram_mib=900)                        # terminal que não está na lista
        self.make(4701,4700,471,'/usr/bin/bash',tty=34816)                             # ... com shell aberto
        self.make(4800,2249,480,'/opt/editor/electron',vram_mib=900)
        self.make(4801,4800,481,'/opt/editor/electron',cmd='electron --type=renderer')
        self.make(4802,4801,482,'/usr/bin/node',cmd=str(ROOT/'scripts/x.js'))          # filho do projeto dentro do app
        self.make(4900,2249,490,'/usr/bin/semcwd',vram_mib=900,nocwd=True)             # /proc incompleto
        self.make(4950,2249,495,'/usr/bin/outra-placa',vram_mib=3000,pdev='0000:07:00.0')
        self.make(4960,2249,496,'/opt/ChatGPT/chatgpt',vram_mib=900)                   # app com agente sem terminal
        self.make(4961,4960,497,'/usr/lib/chatgpt/resources/codex',cmd='codex app-server')
        self.make(4970,2249,498,'/opt/outro/app',vram_mib=900)
        self.make(4971,4970,499,'/usr/bin/node',cmd='node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js')
        self.make(5000,2249,500,'/usr/bin/bash')                                       # esta sessão

    def make(self,pid,ppid,start,exe,vram_mib=None,dup=False,tty=0,cmd=None,nocwd=False,pdev=None):
        d=self.proc/str(pid); (d/'fdinfo').mkdir(parents=True)
        name=os.path.basename(exe)
        rest=['S',str(ppid),'0','0',str(tty)]+['0']*14+[str(start),'0','0']
        (d/'stat').write_text(f"{pid} ({name[:15]}) "+' '.join(rest)+"\n")
        (d/'comm').write_text(name[:15]+'\n'); (d/'cmdline').write_bytes((cmd or exe).encode()+b'\0')
        alvo=lambda path:str(self.proc/'_alvo'/path.lstrip('/'))  # a suíte só permite links dentro da pasta temporária
        os.symlink(alvo(exe),d/'exe')
        if not nocwd: os.symlink(alvo('/home/u'),d/'cwd')
        if vram_mib is not None:
            self.client+=1
            text=f"drm-pdev:\t{pdev or self.PDEV}\ndrm-client-id:\t{self.client}\ndrm-memory-vram:\t{vram_mib*1024} KiB\n"
            (d/'fdinfo'/'5').write_text(text)
            if dup: (d/'fdinfo'/'6').write_text(text)  # mesmo cliente em outro fd conta uma vez

    def decision(self,missing_mib):
        metrics=dict(known=True,total_bytes=8176*self.MIB,used_bytes=7000*self.MIB,device=str(self.proc/'_dev'/self.PDEV))
        policy=dict(margin_bytes=512*self.MIB)
        additional=(8176-7000-512+missing_mib)*self.MIB
        return dict(reason='vram_pressure',additional_bytes=additional),metrics,policy

    def kill_exits(self):
        calls=[]
        def kill(pid,sig):
            calls.append((pid,sig)); import shutil; shutil.rmtree(self.proc/str(pid))
        return kill,calls

    def test_groups_children_dedupes_fds_and_protects_whole_app(self):
        apps={a['name']:a for a in self.g.candidate_apps(self.proc,self.g.PROTECTED,self.PDEV,own_pid=5000)}
        # Fora: sessão gráfica, modelo, projeto, terminal com shell, app com filho do projeto, /proc incompleto,
        # outra placa, pequeno demais.
        self.assertEqual(set(apps),{'java','firefox-bin'})
        self.assertEqual(apps['firefox-bin']['pid'],4000)
        self.assertEqual(apps['firefox-bin']['vram_bytes'],600*self.MIB)
        self.assertEqual(self.g.candidate_apps(self.proc,self.g.PROTECTED,None,own_pid=5000),[])  # placa desconhecida
        # Ancestral do processo atual (o app que abriu a entidade) é protegido.
        self.make(5100,3000,600,'/usr/bin/bash'); self.make(5101,5100,601,'/usr/bin/python3')
        apps={a['name'] for a in self.g.candidate_apps(self.proc,self.g.PROTECTED,self.PDEV,own_pid=5101)}
        self.assertEqual(apps,{'firefox-bin'})
        # Revisão Codex: processo do usuário ilegível (stat sumiu, diretório ficou) → a varredura inteira é vetada.
        (self.proc/'4001'/'stat').unlink()
        with self.assertRaises(self.g.ProcInconclusive):
            self.g.candidate_apps(self.proc,self.g.PROTECTED,self.PDEV,own_pid=5000)
        on=dict(enabled=True,protected=self.g.PROTECTED)
        kill,calls=self.kill_exits()
        with patch.object(self.g,'settings',return_value=on), patch.object(self.g.os,'getpid',return_value=5000):
            self.assertIsNone(self.g.reclaim(dict(owner='llm'),*self.decision(400),proc_root=self.proc,kill=kill,notify=False))
        self.assertEqual(calls,[])

    def test_closes_newest_app_that_alone_frees_what_is_missing(self):
        import signal
        on=dict(enabled=True,protected=self.g.PROTECTED)
        with patch.object(self.g,'settings',return_value=on), patch.object(self.g.os,'getpid',return_value=5000):
            kill,calls=self.kill_exits(); request=dict(owner='llm')
            done=self.g.reclaim(request,*self.decision(400),proc_root=self.proc,kill=kill,notify=False,wait_seconds=.5)
            self.assertEqual(calls,[(4000,signal.SIGTERM)]); self.assertTrue(done['closed'])
            self.assertIsNone(self.g.reclaim(request,*self.decision(400),proc_root=self.proc,kill=kill,notify=False))
            self.assertEqual(len(calls),1)  # um app por pedido
            kill,calls=self.kill_exits()
            done=self.g.reclaim(dict(owner='vision'),*self.decision(1000),proc_root=self.proc,kill=kill,notify=False,wait_seconds=.5)
            self.assertEqual(calls,[(3000,signal.SIGTERM)])  # o Firefox já saiu; só o Minecraft libera 1000 MiB
            kill,calls=self.kill_exits()
            self.assertIsNone(self.g.reclaim(dict(owner='llm'),*self.decision(2500),proc_root=self.proc,kill=kill,notify=False))
            self.assertEqual(calls,[])  # 3000 MiB da outra placa não contam; nenhum app sozinho resolve

    def test_disabled_other_owners_tests_errors_and_unexited_app(self):
        on=dict(enabled=True,protected=self.g.PROTECTED)
        kill,calls=self.kill_exits()
        with patch.object(self.g,'settings',return_value=dict(on,enabled=False)):
            self.assertIsNone(self.g.reclaim(dict(owner='llm'),*self.decision(400),proc_root=self.proc,kill=kill,notify=False))
        with patch.object(self.g,'settings',return_value=on), patch.object(self.g.os,'getpid',return_value=5000):
            self.assertIsNone(self.g.reclaim(dict(owner='image'),*self.decision(400),proc_root=self.proc,kill=kill,notify=False))
            with patch.object(self.g,'_pidfd_open',side_effect=AssertionError('sinal real na suíte')):
                self.assertIsNone(self.g.reclaim(dict(owner='llm'),*self.decision(400),proc_root=self.proc,notify=False))
            ignored=[]
            done=self.g.reclaim(dict(owner='llm'),*self.decision(400),proc_root=self.proc,
                                kill=lambda pid,sig:ignored.append(pid),notify=False,wait_seconds=.3)
            self.assertEqual(ignored,[4000]); self.assertFalse(done['closed'])  # não força nem repete
            def refused(pid,sig): raise PermissionError('recusado')
            done=self.g.reclaim(dict(owner='llm'),*self.decision(400),proc_root=self.proc,kill=refused,notify=False)
            self.assertFalse(done['closed']); self.assertIn('PermissionError',done['error'])  # não propaga
        self.assertEqual(calls,[])

    def test_settings_read_from_gpu_json(self):
        with tempfile.TemporaryDirectory() as raiz:
            cfg=Path(raiz)/'compartilhado/config'; cfg.mkdir(parents=True)
            with patch.object(self.g.config,'RAIZ',Path(raiz)):
                self.assertFalse(self.g.settings()['enabled'])
                (cfg/'gpu.json').write_text(json.dumps(dict(close_last_app_on_pressure=True,protected_apps=['ChatGPT'])))
                got=self.g.settings()
                self.assertTrue(got['enabled']); self.assertIn('ChatGPT',got['protected']); self.assertIn('Xorg',got['protected'])

    def test_prepare_calls_guard_only_after_idle_weights_and_with_ram(self):
        from core import vram_guard
        adapter=module('gpu_resource_vram_guard','app/core/gpu_resource.py')  # a suíte troca a manutenção real por []
        request=dict(owner='llm',model_key='http://127.0.0.1:11436|m',vram_bytes=7*GIB,workspace_bytes=0,priority=1,
                     expected_latency=15,fallback_latency=120)
        scope=adapter._request.set(request)
        for row in rm.residency(): rm.forget_model(row['endpoint'],row['model'])  # sobras de outros testes
        try:
            empty=Mock(json=Mock(return_value={'models':[]}),raise_for_status=Mock())
            peer=Mock(json=Mock(return_value={'models':[dict(name='peer',size_vram=3*GIB,size=3*GIB)]}),raise_for_status=Mock())
            with patch.object(adapter.requests,'get',return_value=empty), \
                 patch.object(gpu_metrics,'snapshot',return_value=metrics(used_bytes=7*GIB)), \
                 patch.object(gpu_metrics,'ram_available',return_value=64*GIB), \
                 patch.object(rm,'gpu_policy',return_value=POLICY), \
                 patch.object(vram_guard,'reclaim') as reclaim:
                adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,1)
                self.assertIs(reclaim.call_args.args[0],request)
                self.assertEqual(reclaim.call_args.args[1]['reason'],'vram_pressure')
                reclaim.reset_mock()
                with patch.object(gpu_metrics,'snapshot',return_value=metrics(used_bytes=0)):
                    adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,0)  # cabe: não fecha nada
                with patch.object(gpu_metrics,'ram_available',return_value=1*GIB):
                    adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,0)  # sem RAM para carregar, fechar app não adianta
                # Revisão Codex: um modelo ocioso do projeto preservado (GPU ocupada) → não fecha app do usuário.
                with patch.object(adapter.requests,'get',return_value=peer), \
                     patch.object(gpu_metrics,'snapshot',return_value=metrics(used_bytes=7*GIB,utilization=95)):
                    adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,0)
                # Revisão Codex: daemon sem resposta com modelo ainda registrado na placa → não comprova, não fecha.
                for row in rm.residency(): rm.forget_model(row['endpoint'],row['model'])
                rm.observe_model('http://127.0.0.1:11437','peer',3*GIB)
                def get(url,**k):
                    if url.startswith('http://127.0.0.1:11437'): raise adapter.requests.ConnectionError('recusado')
                    return empty
                with patch.object(adapter.requests,'get',side_effect=get):
                    adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,0)
                rm.forget_model('http://127.0.0.1:11437','peer')
                rm.observe_model('http://127.0.0.1:11437','peer',None)  # VRAM desconhecida também veta
                with patch.object(adapter.requests,'get',side_effect=get):
                    adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,0)
                rm.forget_model('http://127.0.0.1:11437','peer')
                with patch.object(adapter.requests,'get',side_effect=get):
                    adapter.prepare_residency('llm')
                self.assertEqual(reclaim.call_count,1)  # sem modelo registrado, o daemon fora do ar não ocupa a placa
        finally:
            adapter._request.reset(scope)

if __name__=='__main__': unittest.main()
