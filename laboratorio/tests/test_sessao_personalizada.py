import json
import tempfile
import threading
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from laboratorio import sessao_personalizada as custom,treinos_unificados as lab

class CustomSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.data=dict(starts_at='2026-10-22T23:00',ends_at='2026-10-23T12:00',evaluation_minutes=30)
        self.start,self.end,_=custom.bounds(self.data)
        # 05/11: o personalizado treina três originais (9B Hoshino, 9B Lilith, 4B Alistair) = 6 etapas.
        self.tasks=[dict(model='qwen35-9b',entity='hoshino',action='train',minutes=90)]*6
        self.plan=dict(allowed=True,blockers=[],tasks=self.tasks,window_minutes=780,
                       fingerprint='fixed',starts_at=self.start,ends_at=self.end)
        self.sup=SimpleNamespace(lock=threading.RLock(),closing=False,laboratory_maintenance=False,
            laboratory_home=self.home,authorize_night=Mock(return_value={'id':'123'}))

    def test_timezone_and_13_hours(self):
        self.assertEqual(self.end-self.start,780*60)
        self.assertEqual(custom.datetime.fromtimestamp(self.start,custom.ZONE).hour,23)

    def test_backwards_and_seconds_refused(self):
        for end in ('2026-10-22T22:00','2026-10-23T12:00:01'):
            with self.assertRaises(ValueError):custom.bounds(dict(self.data,ends_at=end))

    def test_invalid_custom_budgets(self):
        for window,evaluation in [(119,30),(1081,30),(780,14),(780,91),(120,30)]:
            with self.assertRaises(ValueError):lab.default_cycle_plan(self.home,nightly=True,custom=True,
                window_minutes=window,evaluation_minutes_custom=evaluation)

    def test_gate_failure_still_blocks(self):
        with patch.object(lab,'measured_preset',return_value=None):
            p=lab.default_cycle_plan(self.home,nightly=True,custom=True,window_minutes=780)
        self.assertFalse(p['allowed']);self.assertEqual(len(p['blockers']),3)
        self.assertEqual(p['train_minutes_per_model'],90)
        self.assertEqual(p['reserve_minutes'],780-3*(90+30))

    def test_incomplete_tasks_never_allowed(self):
        with patch.object(custom,'build_plan',return_value=dict(allowed=True,blockers=[],tasks=[])),\
             patch.object(custom,'fingerprint',return_value='fixed'),patch.object(custom.time,'time',return_value=self.start-1):
            self.assertFalse(custom.preview(self.home,self.data)['allowed'])

    def test_late_preview_blocks(self):
        with patch.object(custom,'build_plan',return_value=dict(allowed=True,blockers=[],tasks=self.tasks)),\
             patch.object(custom,'fingerprint',return_value='fixed'),patch.object(custom.time,'time',return_value=self.start+1):
            self.assertFalse(custom.preview(self.home,self.data)['allowed'])

    def schedule(self):
        with patch.object(custom,'preview',return_value=self.plan):
            return custom.schedule(self.sup,dict(self.data,confirm='AGENDAR_TRES_ORIGINAIS'))

    def test_schedule_requires_confirmation(self):
        with self.assertRaises(ValueError):custom.schedule(self.sup,self.data)

    def test_durable_once_only(self):
        row=self.schedule();self.assertEqual(json.loads(custom.path(self.home).read_text())['id'],row['id'])
        with self.assertRaises(ValueError):self.schedule()
        self.sup.authorize_night.assert_not_called()

    def test_cancel_does_not_start(self):
        self.schedule();custom.cancel(self.sup,{'confirm':True})
        self.assertEqual(json.loads(custom.path(self.home).read_text())['state'],'cancelled')
        self.sup.authorize_night.assert_not_called()

    def test_future_tick_does_nothing(self):
        self.schedule()
        with patch.object(custom.time,'time',return_value=self.start-1):custom.tick(self.sup)
        self.assertEqual(json.loads(custom.path(self.home).read_text())['state'],'scheduled')

    def test_missed_window_does_not_retry(self):
        self.schedule()
        with patch.object(custom.time,'time',return_value=self.start+61):custom.tick(self.sup);custom.tick(self.sup)
        self.assertEqual(json.loads(custom.path(self.home).read_text())['state'],'blocked')
        self.sup.authorize_night.assert_not_called()

    def test_uncertain_attempt_is_never_replayed(self):
        row=self.schedule();row['state']='attempting';lab._write_json(custom.path(self.home),row)
        custom.tick(self.sup);self.sup.authorize_night.assert_not_called()

    def test_gate_blocks_registration(self):
        with patch.object(custom,'preview',return_value=dict(self.plan,allowed=False,blockers=['quality'])):
            with self.assertRaisesRegex(ValueError,'quality'):custom.schedule(self.sup,dict(self.data,confirm='AGENDAR_TRES_ORIGINAIS'))
        self.assertFalse(custom.path(self.home).exists())

    def running_context(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch.object(custom.time,'time',return_value=self.start+1))
        stack.enter_context(patch.object(lab,'_busy',return_value=None))
        stack.enter_context(patch.object(lab,'night_status',return_value={'state':'completed'}))
        stack.enter_context(patch.object(custom,'build_plan',return_value=self.plan))
        stack.enter_context(patch.object(custom,'fingerprint',return_value='fixed'))
        core=SimpleNamespace(resource_manager=SimpleNamespace(status=lambda:[]),job_bus=SimpleNamespace(status=lambda **kw:[]))
        stack.enter_context(patch.dict(sys.modules,{'core':core}))
        return stack

    def test_success_once_with_absolute_stop_margin(self):
        self.schedule()
        with self.running_context():custom.tick(self.sup);custom.tick(self.sup)
        self.sup.authorize_night.assert_called_once()
        data=self.sup.authorize_night.call_args.args[0]
        self.assertEqual(data['absolute_deadline'],self.end-600)
        self.assertEqual(json.loads(custom.path(self.home).read_text())['session_id'],'123')

    def test_timeout_never_retries(self):
        self.schedule();self.sup.authorize_night.side_effect=TimeoutError('uncertain')
        with self.running_context():custom.tick(self.sup);custom.tick(self.sup)
        self.sup.authorize_night.assert_called_once()
        self.assertEqual(json.loads(custom.path(self.home).read_text())['state'],'blocked')

    def test_hash_divergence_blocks(self):
        self.schedule()
        with self.running_context(),patch.object(custom,'fingerprint',return_value='changed'):custom.tick(self.sup)
        self.sup.authorize_night.assert_not_called()

    def test_durable_active_job_blocks(self):
        self.schedule();lab._write_json(lab._registry(self.home)/'jobs'/'a.json',{'state':'running'})
        with self.running_context():custom.tick(self.sup)
        self.sup.authorize_night.assert_not_called()

    def test_rescheduled_window_has_eleven_hours(self):
        start,end,minutes=custom.bounds(dict(starts_at='2026-10-23T23:00',ends_at='2026-10-24T10:00'))
        self.assertEqual(end-start,11*3600);self.assertEqual(minutes,660)

    def test_new_experiment_does_not_reuse_or_approve_discarded_candidates(self):
        for entity,rels in lab.DATASETS.items():
            for rel in rels:
                p=self.home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}\n'*10)
        with patch.object(lab,'measured_preset',return_value={'preset':{'rank':4,'head_cpu':True}}):
            fresh=lab.default_cycle_plan(self.home,nightly=True,custom=True,window_minutes=660)
            legacy=lab.default_cycle_plan(self.home,nightly=True)
        self.assertTrue(fresh['allowed']);self.assertEqual(len(fresh['tasks']),6)
        self.assertEqual({(t['model'],t['entity']) for t in fresh['tasks']},{('qwen35-9b','hoshino'),('qwen35-9b','lilith'),('alistair-4b','alistair')})
        self.assertEqual(fresh['train_minutes_per_model'],90);self.assertEqual(fresh['reserve_minutes'],660-3*(90+30))
        self.assertFalse(fresh['quality_approved']);self.assertFalse(fresh['automatic_promotion'])
        self.assertFalse(legacy['allowed'])
        self.assertFalse(any(t.get('checkpoint') or t.get('candidate') for t in fresh['tasks']))
        self.assertEqual([t['candidate_from_task'] for t in fresh['tasks'] if t['action']=='evaluate'],list(range(0,6,2)))
        self.assertEqual([t['options']['max_steps'] for t in fresh['tasks'] if t['action']=='train'],[30]*3)

    def test_physical_pressure_blocks_fresh_training(self):
        evidence=self.home/'evidence';evidence.mkdir()
        (evidence/'hardware_metrics.json').write_text(json.dumps({'child_exit_code':0,'pressure':['thermal']}))
        task=dict(model='yi-6b',entity='hoshino',action='train',minutes=57,options={'checkpoint_steps':50})
        with patch.object(lab,'measured_preset',return_value={'evidence':str(evidence),'preset':{'head_cpu':True}}),\
             patch.object(lab,'benchmark_result',return_value={'cancelled':False}):
            result=custom.physical_readiness(self.home,dict(tasks=[task]*7,blockers=[]))
        self.assertFalse(result['allowed']);self.assertTrue(any('física' in b for b in result['blockers']))

    def test_disk_projection_gate_blocks(self):
        evidence=self.home/'evidence';evidence.mkdir()
        (evidence/'hardware_metrics.json').write_text(json.dumps({'child_exit_code':0,'pressure':[]}))
        task=dict(model='yi-6b',entity='hoshino',action='train',minutes=57,options={'checkpoint_steps':50})
        with patch.object(lab,'measured_preset',return_value={'evidence':str(evidence),'preset':{'head_cpu':True}}),\
             patch.object(lab,'benchmark_result',return_value={'cancelled':False}),\
             patch.object(lab,'checkpoint_storage_projection',return_value=20*1024**3),\
             patch.object(custom.shutil,'disk_usage',return_value=SimpleNamespace(free=30*1024**3)):
            result=custom.physical_readiness(self.home,dict(tasks=[task]*14,blockers=[]))
        self.assertFalse(result['allowed']);self.assertTrue(any('Disco' in b for b in result['blockers']))

if __name__=='__main__':unittest.main()
