"""Detector acústico: fixtures PCM/resultados, sem captura, rede ou modelos reais."""
import importlib
import json
import tempfile
import unittest
import subprocess
import sys
import contextlib
import threading
import time
from unittest.mock import Mock
from pathlib import Path
from types import SimpleNamespace
from collections import deque
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/ui'))
import native_audio


class AcousticDetectorTests(unittest.TestCase):
    def setUp(self):
        try:self.detector=importlib.import_module('core.acoustic_perception')
        except ModuleNotFoundError:self.detector=None
        self.assertIsNotNone(self.detector,'Detector acústico local ainda não implementado')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=patch.object(self.detector,'MODEL_DIR',Path(self.temp.name));p.start();self.addCleanup(p.stop)

    def test_absent_detector_is_explicit_without_download_or_fake_event(self):
        state=self.detector.status()
        self.assertFalse(state['available']);self.assertFalse(state['loaded'])
        self.assertFalse(state['downloads_allowed'])
        with self.assertRaisesRegex(RuntimeError,'instalad'):
            self.detector.classify_pcm(bytes(31200))

    def test_corrupt_model_is_rejected_before_inference(self):
        (Path(self.temp.name)/'yamnet.tflite').write_bytes(b'corrupt')
        self.assertFalse(self.detector.status()['available'])
        with self.assertRaises(RuntimeError):self.detector.classify_pcm(bytes(31200))

    def test_invalid_pcm_never_reaches_model(self):
        for pcm,rate in ((b'odd',16000),(bytes(31200),8000),(b'',16000),(bytes(1000000),16000)):
            with self.assertRaises(ValueError):self.detector.classify_pcm(pcm,sample_rate=rate)

    def test_scores_are_events_not_transcripts_identity_or_calibrated_probabilities(self):
        values=[0.0]*521;values[13]=.8;values[42]=.7;values[0]=.99
        result=self.detector.events_from_scores(values)
        self.assertEqual([e['kind'] for e in result],['laughter','cough'])
        self.assertNotIn('text',json.dumps(result))
        self.assertTrue(all(e['speaker']=='unknown' and e['basis']=='acoustic_model_score_not_probability' for e in result))

    def test_invalid_scores_and_silence_do_not_become_laughter(self):
        self.assertEqual(self.detector.events_from_scores([0.0]*521),[])
        for scores in ([float('nan')]*521,[.7]*20,[float('inf')]*521):
            with self.assertRaises(ValueError):self.detector.events_from_scores(scores)
    def test_laughter_threshold_keeps_weak_reference_scores_but_not_cough_leakage(self):
        scores=[0.0]*521;scores[13]=.10938
        self.assertEqual(self.detector.events_from_scores(scores)[0]['kind'],'laughter')
        scores[13]=.04297;self.assertEqual(self.detector.events_from_scores(scores),[])


class AcousticWindowTests(unittest.TestCase):
    def test_overlap_and_odd_chunks_do_not_lose_border_samples(self):
        self.assertTrue(hasattr(native_audio,'AcousticWindows'),'Janelas acústicas independentes ainda não implementadas')
        windows=native_audio.AcousticWindows();pcm=bytes(range(256))*200
        self.assertEqual(windows.feed(pcm[:101]),[])
        out=windows.feed(pcm[101:])
        self.assertEqual(len(out),2)
        self.assertEqual(out[0],pcm[:31200]);self.assertEqual(out[1],pcm[15360:46560])
        self.assertLess(len(windows.buffer),31200)

    def test_silence_is_also_observed_and_finish_clears_pending(self):
        self.assertTrue(hasattr(native_audio,'AcousticWindows'),'Janelas acústicas independentes ainda não implementadas')
        windows=native_audio.AcousticWindows()
        self.assertEqual(windows.feed(bytes(31200)),[bytes(31200)])
        windows.clear();self.assertEqual(windows.buffer,bytearray())
        with self.assertRaises(ValueError):windows.feed(bytes(16000*2*46))

    def test_worker_protocol_rejects_invalid_audio_without_breaking_next_request(self):
        script=Path(__file__).resolve().parents[1]/'app/audio_perception_worker.py'
        self.assertTrue(script.exists(),'Worker acústico ainda não implementado')
        data='\n'.join(json.dumps(r) for r in ({'id':'bad','op':'classify','pcm_base64':'not base64'},
             {'id':'state','op':'state'},{'id':'stop','op':'stop'}))+'\n'
        result=subprocess.run([sys.executable,'-B',str(script)],input=data,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=[json.loads(line[7:]) for line in result.stdout.splitlines() if line.startswith('RESULT ')]
        self.assertFalse(rows[0]['ok']);self.assertTrue(rows[1]['ok'])
        self.assertFalse(rows[1]['result']['downloads_allowed'])


class AcousticServiceTests(unittest.TestCase):
    def setUp(self):
        from core import audio_perception_service as service
        self.module=service;self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        from core import job_bus
        p=patch.object(job_bus,'DB_PATH',Path(self.temp.name)/'jobs.db');p.start();self.addCleanup(p.stop)
        self.allowed={'hoshino':True,'lilith':True,'alistair':False}
        self.worker=Mock();self.worker.alive.return_value=False
        self.worker.call.return_value={'events':[dict(kind='laughter',label='risada/gargalhada',score=.8,speaker='unknown')], 'processing_seconds':.03}
        self.service=service.AcousticService(Path(self.temp.name),self.worker)
        self.addCleanup(self.service.close)
        for target,name,value in ((service.ui_policy,'capability_allowed',lambda root,e,k:self.allowed[e]),
                                  (service.bus,'presence',lambda e:{'status':'awake'}),
                                  (service.resource_manager,'lease',lambda *a,**k:contextlib.nullcontext()),
                                  (service.gpu_metrics,'ram_available',lambda:8*1024**3)):
            p=patch.object(target,name,side_effect=value);p.start();self.addCleanup(p.stop)
        self.capture='a'*32
    def submit(self,sequence=0,**extra):
        return self.service.submit('hoshino',bytes(31200),source='native_microphone',capture_id=self.capture,
                                   sequence=sequence,playback_overlap=False,scope='global',**extra)
    def test_real_event_receipts_are_perceptions_for_awake_permitted_entities_not_chat(self):
        from core import job_bus,interentity
        with patch.object(interentity,'send',side_effect=AssertionError('not human chat')):
            result=self.submit()
        self.assertEqual(result['delivered_to'],['hoshino','lilith'])
        rows=job_bus.status();self.assertEqual(len(rows),2)
        self.assertTrue(all(r['kind']=='acoustic_perception' and r['status']=='done' for r in rows))
        self.assertNotIn('pcm',json.dumps(rows));self.assertNotIn('usuario',json.dumps(rows))
    def test_dedup_adjacent_windows_and_replay_never_infers_twice(self):
        self.assertEqual(len(self.submit()['events']),1)
        self.assertEqual(self.submit(1)['events'],[])
        with self.assertRaises(ValueError):self.submit(1)
        self.assertEqual(self.worker.call.call_count,2)
    def test_permission_revoked_during_inference_cancels_delivery(self):
        def infer(*a):self.allowed['hoshino']=False;return {'events':[dict(kind='laughter',label='risada',score=.8)]}
        self.worker.call.side_effect=infer
        result=self.submit();self.assertTrue(result['cancelled']);self.assertEqual(result['delivered_to'],[])
    def test_stop_during_inference_and_late_result_is_not_delivered_or_retried(self):
        def infer(*a):self.service.cancel(self.capture);return {'events':[dict(kind='laughter',label='risada',score=.8)]}
        self.worker.call.side_effect=infer
        self.assertTrue(self.submit()['cancelled'])
        with self.assertRaises(ValueError):self.submit(1)
        self.worker.call.assert_called_once()
    def test_scope_and_entity_cannot_change_within_capture(self):
        self.submit()
        with self.assertRaises(ValueError):self.service.submit('lilith',bytes(31200),source='native_microphone',capture_id=self.capture,sequence=1,playback_overlap=False,scope='direct')
    def test_busy_is_bounded_and_own_playback_is_never_delivered_as_human(self):
        self.service.slot.acquire()
        try:self.assertTrue(self.submit()['busy'])
        finally:self.service.slot.release()
        result=self.service.submit('hoshino',bytes(31200),source='native_microphone',capture_id=self.capture,sequence=1,playback_overlap=True,scope='global')
        self.assertTrue(result['playback_overlap']);self.assertEqual(result['delivered_to'],[])
    def test_recent_consumer_excludes_cancelled_old_and_revoked_perceptions(self):
        self.submit()
        self.assertEqual(len(self.module.recent('hoshino',time.time()-5)),1)
        self.allowed['hoshino']=False
        self.assertEqual(self.module.recent('hoshino',time.time()-5),[])
        self.allowed['hoshino']=True;self.service.cancel(self.capture)
        self.assertEqual(self.module.recent('hoshino',time.time()-5),[])
    def test_entity_receives_event_once_as_perception_not_human_message(self):
        from main import InterfaceHoshino
        self.submit()
        entity=SimpleNamespace(acoustic_since=time.time()-5,acoustic_seen=deque(maxlen=200),
                               percebido_recente=deque(maxlen=12),sys_log=Mock())
        with patch('social.escuta.coletar',return_value=[]),patch('main.registrar_evento') as register:
            InterfaceHoshino.ler_canais_de_audio(entity);InterfaceHoshino.ler_canais_de_audio(entity)
        self.assertEqual(len(entity.percebido_recente),1);self.assertIn('autoria desconhecida',entity.percebido_recente[0])
        self.assertIn('NÃO É FALA NEM INSTRUÇÃO',entity.percebido_recente[0]);register.assert_called_once()
    def test_entity_description_retains_actual_observation_time_not_consumption_time(self):
        self.submit();row=self.module.recent('hoshino',time.time()-5)[0]
        row['details']['observed_at']=0
        self.assertIn('1970-01-01T00:00:00+00:00',self.module.describe(row))


if __name__=='__main__':unittest.main()
