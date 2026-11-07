"""Contratos da central: fixtures temporárias, sem serviços/voz/GPU reais."""
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from core import central_control as cc, interentity as bus, resource_manager as rm, job_bus
from core.audio_service import AudioService

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('control_launcher',ROOT/'iniciar_entidades.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


class CentralControlTests(unittest.TestCase):
    def test_xbox_model_limits_match_ui_save_and_applied_status_without_network(self):
        from core import alistair_execution as execution,xbox_alistair as xbox
        model=self.install('alistair');xbox.write_json(execution.path(self.root),dict(destination='xbox'))
        before=self.control.model_settings('alistair')
        self.assertEqual(before['context_max'],8192);self.assertEqual(before['context_step'],256)
        self.assertIn('sincronizado',before['impact_note'])
        xbox.write_json(xbox.state_path(self.root),dict(state='sleeping',pending=None,context=8192,model_limits=dict(context=8192,output=768)))
        with patch.object(xbox,'Portal')as portal:
            self.control.save_model(dict(entity='alistair',model=model,context=4096,output=512,revision=before['revision']))
            status=self.control.alistair_execution()['model_limits']
        portal.assert_not_called();self.assertEqual(status['configured'],dict(context=4096,output=512))
        self.assertEqual(status['applied'],dict(context=8192,output=768));self.assertTrue(status['pending'])
        xbox.write_json(xbox.state_path(self.root),dict(state='sleeping',pending=None,context=4096,model_limits=dict(context=4096,output=512)))
        self.assertFalse(self.control.alistair_execution()['model_limits']['pending'])

    def test_xbox_invalid_steps_and_pending_inference_refuse_model_save(self):
        from core import alistair_execution as execution,xbox_alistair as xbox
        model=self.install('alistair');xbox.write_json(execution.path(self.root),dict(destination='xbox'))
        status=self.control.model_settings('alistair');path=self.control.env_path('alistair');before=path.read_bytes()
        data=dict(entity='alistair',model=model,context=4097,output=512,revision=status['revision'])
        with self.assertRaisesRegex(ValueError,'passos'):self.control.save_model(data)
        self.assertEqual(path.read_bytes(),before)
        xbox.write_json(xbox.state_path(self.root),dict(state='blocked',pending=dict(operation='infer',id='fixture')))
        with self.assertRaisesRegex(ValueError,'pendente'):self.control.save_model(data|dict(context=4096))
        self.assertEqual(path.read_bytes(),before)

    def test_local_alistair_context_does_not_gain_xbox_step_restriction(self):
        model=self.install('alistair');status=self.control.model_settings('alistair')
        self.assertEqual(status['context_step'],1)
        self.assertTrue(self.control.save_model(dict(entity='alistair',model=model,context=4097,output=512,revision=status['revision']))['saved'])

    def test_alistair_destination_get_is_local_no_secret_or_start(self):
        from core import xbox_alistair as xbox
        xbox.save_secret(self.root,'fixture-user','fixture-password')
        xbox.write_json(xbox.state_path(self.root),{'state':'ready','observed_at':time.time()-100})
        with patch.object(xbox,'Portal')as portal:
            result=self.control.alistair_execution()
        portal.assert_not_called();self.assertFalse(result['xbox']['fresh'])
        self.assertNotIn('fixture-password',json.dumps(result));self.assertNotIn('fixture-user',json.dumps(result))
        self.assertFalse(bus.pending_wake_requests())

    def test_alistair_destination_save_requires_sleep_revision_and_preserves_pc2(self):
        from core import alistair_execution as execution
        old=self.root/'compartilhado/config/alistair_pc2.json';old.write_text('{"enabled":false,"preserve":"pc2"}')
        before=old.read_bytes();status=self.control.alistair_execution();settings=status['settings']
        data=dict(settings=settings,revision=status['revision'])
        job_bus.publish('active','alistair','running',kind='llm_speech')
        with self.assertRaisesRegex(ValueError,'ativo'):self.control.save_alistair_execution(data)
        job_bus.publish('active','alistair','done',kind='llm_speech')
        out=self.control.save_alistair_execution(data);self.assertTrue(out['saved']);self.assertEqual(old.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'mudou'):self.control.save_alistair_execution(data)
        self.assertEqual(execution.destination(self.root),'local')

    def test_alistair_uncertain_operation_blocks_destination_change(self):
        from core import xbox_alistair as xbox
        status=self.control.alistair_execution()
        xbox.write_json(xbox.state_path(self.root),{'state':'blocked','pending':{'operation':'infer','id':'fixture'}})
        with self.assertRaisesRegex(ValueError,'pendente'):
            self.control.save_alistair_execution(dict(settings=status['settings'],revision=status['revision']))

    def test_long_node_maintenance_keeps_entity_lock_not_global_supervisor_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        with self.control.idle_entity('alistair',long_operation=True):
            def check_supervisor():
                with self.supervisor.lock:return True
            with ThreadPoolExecutor(max_workers=1)as executor:
                self.assertTrue(executor.submit(check_supervisor).result(timeout=1))
            with self.assertRaisesRegex(ValueError,'ativa'):
                with self.control.idle_entity('alistair'):pass

    def test_global_shortcut_save_preserves_other_settings_and_rejects_typing_keys(self):
        before=self.control.microphone()
        result=self.control.save_microphone({'settings':{'hotkey_enabled':True,'hotkey':'Ctrl+Alt+Space'},'revision':before['revision']})
        actual=self.control.microphone();self.assertTrue(actual['settings']['hotkey_enabled'])
        self.assertEqual(actual['settings']['mode'],before['settings']['mode'])
        self.control.save_microphone({'settings':{'output_volume':32},'revision':result['revision']})
        actual=self.control.microphone();self.assertEqual(actual['settings']['hotkey'],'Ctrl+Alt+Space')
        for hotkey in ('a','Enter','F8, F9','Ctrl+Ctrl+a','Ctrl','$(echo hi)',''):
            with self.subTest(hotkey=hotkey),self.assertRaises(ValueError):
                self.control.save_microphone({'settings':{'hotkey':hotkey},'revision':actual['revision']})
        self.assertEqual(self.control.microphone()['revision'],actual['revision'])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        for entity in cc.ENTITIES:
            base=self.root/'entidades'/entity
            for folder in ('config','runtime','memory/sqlite','identity','workspace'): (base/folder).mkdir(parents=True,exist_ok=True)
            (base/'entidade.json').write_text(json.dumps(dict(id=entity,nome=entity.capitalize(),status='ativa')))
            (base/'config'/(entity+'.env')).write_text('# mantenha este comentário\nHOSHINO_MODEL="'+cc.MODEL_DEFAULTS[entity]+'"\nDESCONHECIDO="preservar"\n')
        for obj,name,filename in [(bus,'DB_PATH','bus.db'),(rm,'DB_PATH','rm.db'),(job_bus,'DB_PATH','jobs.db')]:
            p=patch.object(obj,name,self.root/filename);p.start();self.addCleanup(p.stop)
        p=patch.object(launcher,'ROOT',self.root);p.start();self.addCleanup(p.stop)
        self.audio=AudioService(self.root);self.addCleanup(self.audio.close)
        self.supervisor=launcher.Supervisor();self.control=cc.Control(self.root,self.supervisor,self.audio)
        path=self.root/'compartilhado/config/audio.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(backend='qwen3_tts',python='python',voices_ready=True,
                                        preferred_provider='azure',unknown={'preserve':True},
                                        voices={'hoshino':{'id':'Serena'},'lilith':{'id':'Vivian'}},
                                        azure={'enabled':False},elevenlabs={'enabled':False,'voices':{'hoshino':'chosen-h','lilith':'chosen-l'}})))
        self.audio.settings=self.audio._settings()

    def install(self,entity):
        model=cc.MODEL_DEFAULTS[entity];name,tag=model.rsplit(':',1)
        parts=name.split('/') if '/' in name else ['registry.ollama.ai','library',name]
        storage=self.root/'compartilhado/modelos'/cc.STORES[entity];blob=b'fixture-not-a-model';digest=hashlib.sha256(blob).hexdigest()
        (storage/'blobs').mkdir(parents=True);(storage/'blobs'/('sha256-'+digest)).write_bytes(blob)
        path=storage/'manifests'/Path(*parts)/tag;path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'config':{'digest':'sha256:'+digest,'size':len(blob)},'layers':[]}))
        return model

    def model_data(self):
        model=self.install('hoshino');return dict(entity='hoshino',model=model,context=8192,output=4096,revision=self.control.model_settings('hoshino')['revision'])

    def test_version_selection_pins_all_entities_without_wake_memory_or_stable_promotion(self):
        from laboratorio import recuperacao_modelos as r,treinos_unificados as lab
        from core import neural9b_modes as modes
        for entity in cc.ENTITIES:
            model='alistair-4b' if entity=='alistair' else 'qwen35-9b'
            row=dict(entity=entity,model_id=model,kind='trained',ref='fixture-job',source_sha256='a'*64,
                alias=entity+'-trained:latest',manifest_sha256='b'*64,ready=True,experimental=True,quality_approved=False)
            data=dict(entity=entity,model_id=model,kind='trained',ref='fixture-job',revision='catalog',experimental_consent=True)
            env=self.control.env_path(entity).read_bytes()
            with patch.object(r,'find_version',return_value=row),patch.object(lab,'_busy',return_value=None):
                out=self.control.change_model_version(data)
            self.assertTrue(out['saved']);self.assertFalse(out['quality_approved']);self.assertTrue(out['experimental'])
            self.assertEqual(modes.selected_version(self.root,entity,model)['source_sha256'],'a'*64)
            self.assertEqual(env,self.control.env_path(entity).read_bytes())
            self.assertFalse((self.root/f'entidades/{entity}/memory/sqlite/{entity}.db').exists())
        self.assertEqual(len(modes.read_document(self.root)['executor_versions']),3)
        self.assertFalse(bus.pending_wake_requests())

    def test_version_selection_refuses_unready_busy_and_unconsented_without_write(self):
        from laboratorio import recuperacao_modelos as r,treinos_unificados as lab
        from core import neural9b_modes as modes
        data=dict(entity='hoshino',model_id='qwen35-9b',kind='trained',ref='fixture',revision='catalog',experimental_consent=False)
        row=dict(experimental=True,ready=False)
        with patch.object(r,'find_version',return_value=row),patch.object(lab,'_busy',return_value=None):
            with self.assertRaisesRegex(ValueError,'experimental'):self.control.change_model_version(data)
            with self.assertRaisesRegex(ValueError,'Prepare'):self.control.change_model_version(data|{'experimental_consent':True})
            job_bus.publish('active','hoshino','running',kind='llm_speech')
            with self.assertRaisesRegex(ValueError,'ativo'):self.control.change_model_version(data)
        self.assertFalse(modes.path(self.root).exists())

    def test_version_prepare_reconciles_durable_job_not_compact_jobs_list(self):
        from laboratorio import recuperacao_modelos as r,treinos_unificados as lab
        data=dict(entity='hoshino',model_id='qwen35-9b',kind='trained',ref='fixture',revision='catalog',experimental_consent=True)
        row=dict(experimental=True,ready=False,source_sha256='a'*64)
        path=lab._job_file(self.root/'laboratorio-local','a'*16);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(dict(id='a'*16,entity='hoshino',action='recover',state='failed',
            plan=dict(source_sha256='a'*64))))
        with patch.object(r,'find_version',return_value=row),patch.object(lab,'_busy',return_value=None),\
             patch.object(lab,'start',side_effect=AssertionError('Não repetir preparação incerta')):
            with self.assertRaisesRegex(ValueError,'anterior'):self.control.change_model_version(data,prepare=True)

    def feedback_data(self,entity='hoshino',text='Gostei deste assunto.',**metadata):
        sent=bus.send(entity,'usuario',text,metadata=metadata)
        return dict(entity=entity,message_id=sent['id'],decision='liked',note='Boa resposta.',
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),expected_revision=None)

    def test_chat_feedback_all_entities_persistent_without_memory_wake_or_training(self):
        for entity in cc.ENTITIES:
            data=self.feedback_data(entity,turn_id='rated-turn-'+entity)
            out=self.control.save_chat_feedback(data)
            self.assertTrue(out['verified']);self.assertFalse(out['training_started'])
            row=bus.user_conversation(entity)[0];meta=json.loads(row['metadata'])
            self.assertEqual(meta['turn_id'],'rated-turn-'+entity)
            self.assertEqual(meta['human_feedback']['entity'],entity)
            self.assertEqual(meta['human_feedback']['message_id'],row['id'])
            self.assertIsNone(row['read_at']);self.assertFalse(bus.pending_wake_requests())
            feedback=bus.human_feedback_for_turn(entity,'rated-turn-'+entity,row['text'])
            self.assertEqual(feedback['decision'],'liked')
            self.assertEqual(feedback['purpose'],'quality_feedback_not_training_approval')
            self.assertFalse((self.root/f'entidades/{entity}/memory/sqlite/{entity}.db').exists())

    def test_chat_feedback_refuses_foreign_sender_private_and_changed_text(self):
        data=self.feedback_data()
        for update in ({'entity':'lilith'},{'text_sha256':'0'*64},{'extra':'forged'}):
            with self.assertRaises(ValueError):self.control.save_chat_feedback(data|update)
        for metadata in ({'private':True},{'kind':'diary'}):
            with self.assertRaises(ValueError):self.control.save_chat_feedback(self.feedback_data(**metadata))
        user=bus.send('usuario','hoshino','entrada humana')
        with self.assertRaises(ValueError):self.control.save_chat_feedback(data|{'message_id':user['id']})
        forged=bus.send('hoshino','usuario','teste',metadata={'human_feedback':{'decision':'liked'}})
        self.assertNotIn('human_feedback',json.loads(bus.user_conversation('hoshino')[-1]['metadata']))

    def test_chat_feedback_revision_clear_and_ambiguous_correlation(self):
        data=self.feedback_data(turn_id='same-turn');first=self.control.save_chat_feedback(data)
        with self.assertRaises(ValueError):self.control.save_chat_feedback(data)
        second=self.control.save_chat_feedback(data|{'decision':'disliked','expected_revision':first['feedback']['revision']})
        self.assertEqual(second['feedback']['decision'],'disliked')
        clear=self.control.save_chat_feedback(data|{'decision':'clear','expected_revision':second['feedback']['revision']})
        self.assertEqual(clear['feedback']['decision'],'clear')
        self.assertIsNone(bus.human_feedback_for_turn('hoshino','same-turn','Gostei deste assunto.'))
        self.control.save_chat_feedback(data|{'expected_revision':clear['feedback']['revision']})
        bus.send('hoshino','usuario','Gostei deste assunto.',metadata={'turn_id':'same-turn'})
        self.assertIsNone(bus.human_feedback_for_turn('hoshino','same-turn','Gostei deste assunto.'))

    def test_chat_feedback_redacts_notes_limits_and_does_not_leak_to_other_entity(self):
        data=self.feedback_data(turn_id='secret-turn')
        for note in ([], 'x'*601):
            with self.assertRaises(ValueError):self.control.save_chat_feedback(data|{'note':note})
        with patch.dict(os.environ,{'EXAMPLE_API_KEY':'sensitive-feedback-key'}):
            out=self.control.save_chat_feedback(data|{'note':'Não repita sensitive-feedback-key'})
        self.assertNotIn('sensitive-feedback-key',json.dumps(out))
        self.assertIsNone(bus.human_feedback_for_turn('lilith','secret-turn','Gostei deste assunto.'))

    def test_chat_feedback_http_auth_and_state_target_hash(self):
        data=self.feedback_data()
        server,token=launcher.make_server(self.supervisor,0,self.audio)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/control/chat/feedback'
            with self.assertRaises(HTTPError) as denied:urlopen(Request(url,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}))
            self.assertEqual(denied.exception.code,403)
            with urlopen(Request(url,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})) as response:
                self.assertTrue(json.load(response)['verified'])
            view=self.supervisor.state('hoshino',daily=True)
            row=next(m for m in view['conversation'] if m['id']==data['message_id'])
            self.assertEqual(row['feedback_target']['text_sha256'],data['text_sha256'])
            self.assertIsNotNone(row['feedback_target']['expected_revision'])
        finally:server.shutdown();server.server_close();thread.join(timeout=3)

    def test_config_preserves_unknown_comment_backup_and_revision(self):
        data=self.model_data();old=self.control.env_path('hoshino').read_text()
        result=self.control.save_model(data);self.assertTrue(result['saved']);self.assertEqual(result['apply'],'requires_sleep_wake')
        new=self.control.env_path('hoshino').read_text();self.assertIn('# mantenha',new);self.assertIn('DESCONHECIDO="preservar"',new)
        backups=list(self.control.env_path('hoshino').parent.glob('*.backup-*'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),old)
        with self.assertRaises(ValueError):self.control.save_model(data)

    def test_gpu_layers_choice_uses_measured_steps_and_executor_revision(self):
        # 06/11 (pedido humano): divisão GPU/CPU do 9B escolhida na aba Modelos.
        data=self.model_data();path=self.root/'entidades/hoshino/config/executores.json'
        path.write_text(json.dumps({'schema':1,'scope_frozen':True,'gpu_layers_fixed':32,'outro':'preservar'}))
        layers=self.control.model_settings('hoshino')['gpu_layers']
        self.assertEqual((layers['fixed'],layers['total']),(32,33));self.assertIn(20,layers['measured'])
        for value in (27,0,34,'32',True):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.control.save_model(data|dict(gpu_layers=value,layers_revision=layers['revision']))
        with self.assertRaises(ValueError):self.control.save_model(data|dict(gpu_layers=26))
        with self.assertRaises(ValueError):self.control.save_model(data|dict(gpu_layers=26,layers_revision='0'*64))
        self.assertTrue(self.control.save_model(data|dict(gpu_layers=26,layers_revision=layers['revision']))['saved'])
        doc=json.loads(path.read_text());self.assertEqual((doc['gpu_layers_fixed'],doc['outro']),(26,'preservar'))
        self.assertIn('7 na CPU',doc['gpu_layers_fixed_reason'])
        status=self.control.model_settings('hoshino')
        self.control.save_model(dict(data,revision=status['revision'],gpu_layers=None,layers_revision=status['gpu_layers']['revision']))
        self.assertNotIn('gpu_layers_fixed',json.loads(path.read_text()))
        self.assertIsNone(self.control.model_settings('alistair')['gpu_layers'])
        self.assertEqual(self.control.model_settings('hoshino')['prompt_identity']['mode'],'completo')

    def gpu_alert_fixture(self, *, used_mib_over=182, waited=30, rows=None, users=None, now=None):
        """06/11: Lilith acordada, 9B inteiro na placa (33 camadas, 32K) e a margem sem espaço."""
        from core import gpu_metrics, vram_guard
        now = time.time() if now is None else now
        cfg = self.root / 'entidades/lilith/config'
        (cfg / 'executores.json').write_text(json.dumps({'schema': 1, 'gpu_layers_fixed': 33}))
        (cfg / 'lilith.env').write_text('HOSHINO_CONTEXT_TOKENS=32768\n')
        total, margin, mib = 8573157376, 512 * 1024 ** 2, 1024 ** 2
        limit = min(gpu_metrics.HARD_LIMIT, total)
        key = 'http://127.0.0.1:11436|lilith-trained:latest'
        request = dict(owner='llm', entity='lilith', model_key=key, priority=2, vram_bytes=7376606330, workspace_bytes=0,
                       resident_full=True, resident_ctx=32768, overlap_safe=True)
        if rows is None:
            rows = [dict(token='t-1', priority=2, enqueued_at=now - waited, state='waiting', request=request)]
        state = dict(metrics=dict(known=True, stable=True, observed_at=now, total_bytes=total,
                                  used_bytes=limit - margin + used_mib_over * mib, utilization=1,
                                  device='/sys/class/drm/card0/device'),
                     policy=dict(margin_bytes=margin, concurrency_validated=False, max_compute=2, max_utilization=55.0),
                     queue=rows, compute=[], residency=[dict(model_key=key, model='lilith-trained:latest',
                                                              vram_bytes=6558444420, observed_at=now)])
        users = users if users is not None else [
            dict(pid=11, name='llama-server', cmd='/x/compartilhado/modelos/ollama-lilith/blobs/sha256-a', vram_bytes=7389 * mib, kind='modelo'),
            dict(pid=12, name='cinnamon', cmd='cinnamon', vram_bytes=168 * mib, kind='sistema'),
            dict(pid=13, name='firefox-bin', cmd='firefox', vram_bytes=144 * mib, kind='app'),
            dict(pid=14, name='kclock', cmd='kclock', vram_bytes=48 * mib, kind='app')]
        for target, name, value in ((rm, 'gpu_state', lambda: state),
                                    (vram_guard, 'gpu_users', lambda **k: [dict(u) for u in users])):
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
        return state, request

    def test_gpu_alert_names_deficit_apps_and_measured_layer_step(self):
        # 06/11 (pedido humano): alerta na tela quando a entidade fica sem VRAM (Lilith 33 camadas + Firefox).
        bus.register('lilith', 'awake')
        state, request = self.gpu_alert_fixture(waited=10)
        self.assertEqual(self.control.gpu_alerts()['alerts'], [])  # 10 s: o RM ainda pode resolver sozinho
        state['queue'][0]['enqueued_at'] = time.time() - 30
        alert, = self.control.gpu_alerts()['alerts']
        self.assertEqual((alert['entity'], alert['missing_mib'], alert['suggested_layers']), ('lilith', 182, 32))
        self.assertEqual(alert['close_apps'], ['Firefox', 'KClock'])
        for part in ('Lilith não consegue usar a GPU', 'faltam 182 MiB', 'modelo da Lilith 7.389 MiB', 'Firefox 144 MiB',
                     'escolha 32 camadas na GPU na aba Modelos', 'feche Firefox e KClock'):
            self.assertIn(part, alert['text'])
        self.assertFalse(alert['message_waiting'])
        self.assertNotIn('cmd', json.dumps(alert)); self.assertNotIn('blobs', json.dumps(alert))
        # Mensagem humana na fila: o alerta diz que ela espera; a chave continua a mesma.
        state['queue'].append(dict(token='t-2', priority=1, enqueued_at=time.time() - 5, state='waiting', request=dict(request, priority=1)))
        again, = self.control.gpu_alerts()['alerts']
        self.assertTrue(again['message_waiting']); self.assertIn('Sua mensagem está esperando', again['text'])
        self.assertEqual(again['key'], alert['key'])
        # Espera de 120 s expirou e a fila esvaziou: o alerta continua entre tentativas e lembra da mensagem.
        state['queue'].clear()
        between, = self.control.gpu_alerts()['alerts']
        self.assertTrue(between['message_missed']); self.assertIn('ficou sem resposta', between['text'])
        # Firefox fechado: a VRAM que faltava apareceu e o alerta some sem ninguém dispensar.
        state['metrics']['used_bytes'] -= 200 * 1024 ** 2
        self.assertEqual(self.control.gpu_alerts()['alerts'], [])

    def test_vram_margin_is_chosen_in_settings_and_offered_by_the_alert(self):
        # 06/11 (pedido humano): "alargar o limite de VRAM" = escolher a margem que fica livre na placa.
        from core import gpu_metrics
        path = self.root / 'compartilhado/config/gpu.json'
        path.write_text(json.dumps({'margin_bytes': 512 * 1024 ** 2, 'close_last_app_on_pressure': True}))
        metrics = dict(known=True, stable=True, observed_at=time.time(), total_bytes=8573157376, used_bytes=99 * 1024 ** 2)
        with patch.object(rm.config, 'RAIZ', self.root), patch.object(gpu_metrics, 'snapshot', return_value=metrics):
            state = self.control.vram_settings()
            self.assertEqual((state['margin_mib'], state['minimum_mib'], state['total_mib']), (512, 128, 8176))
            self.assertEqual(state['usable_mib'], 8176 - 512)
            for bad in (100, 512.0, '256', None, 2048):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    self.control.save_vram(dict(margin_mib=bad, revision=state['revision']))
            with self.assertRaises(ValueError):
                self.control.save_vram(dict(margin_mib=256, revision='0' * 64))
            saved = self.control.save_vram(dict(margin_mib=256, revision=state['revision']))
            self.assertEqual((saved['margin_mib'], saved['usable_mib']), (256, 8176 - 256))
            doc = json.loads(path.read_text())
            self.assertEqual(doc, {'margin_bytes': 256 * 1024 ** 2, 'close_last_app_on_pressure': True})
            self.assertEqual(rm.gpu_policy()['margin_bytes'], 256 * 1024 ** 2)  # vale no próximo pedido de GPU
        # O alerta sugere baixar a margem quando isso sozinho cobre o que falta (182 MiB de 512).
        bus.register('lilith', 'awake')
        self.gpu_alert_fixture()
        alert, = self.control.gpu_alerts()['alerts']
        self.assertIn('baixe a margem de VRAM em Configurações para 256 MiB', alert['text'])

    def test_gpu_alert_clears_on_gpu_or_sleep_and_points_to_peer_model(self):
        bus.register('lilith', 'awake')
        state, request = self.gpu_alert_fixture()
        self.assertEqual(len(self.control.gpu_alerts()['alerts']), 1)
        state['compute'].append(dict(entity='lilith', resource='gpu'))  # conseguiu a GPU
        self.assertEqual(self.control.gpu_alerts()['alerts'], [])
        state['compute'].clear()
        self.assertEqual(len(self.control.gpu_alerts()['alerts']), 1)
        bus.register('lilith', 'sleeping')
        self.assertEqual(self.control.gpu_alerts()['alerts'], [])
        # Com o modelo de outra entidade na placa a troca cooperativa tem prazo: só alerta perto dos 120 s.
        bus.register('lilith', 'awake'); mib = 1024 ** 2
        peer = dict(model_key='http://127.0.0.1:11435|hoshino:latest', model='hoshino:latest', vram_bytes=6 * 1024 ** 3, observed_at=time.time())
        state['residency'].append(peer)
        users = [dict(pid=21, name='llama-server', cmd='/x/compartilhado/modelos/ollama/blobs/sha256-b', vram_bytes=6000 * mib, kind='modelo')]
        state, request = self.gpu_alert_fixture(users=users, waited=60)
        state['residency'].append(peer)
        self.assertEqual(self.control.gpu_alerts()['alerts'], [])
        state['queue'][0]['enqueued_at'] = time.time() - 110
        alert, = self.control.gpu_alerts()['alerts']
        self.assertIn('faça a Hoshino dormir (o modelo dela ocupa 6.000 MiB)', alert['text'])
        # Falha de leitura nunca derruba o poller da Central.
        with patch.object(rm, 'gpu_state', side_effect=sqlite3.OperationalError('locked')):
            self.assertEqual(self.control.gpu_alerts(), dict(alerts=[], unavailable='OperationalError'))

    def test_clipboard_copies_are_saved_without_button_and_read_by_entities(self):
        # 06/11 (pedido humano): o que for copiado fica guardado sozinho na área compartilhada.
        from core import area_transferencia as area, dispatch
        out = self.control.clipboard_capture('texto', 'Canal: Games EduUu\nhttps://www.youtube.com/@GamesEduUu'.encode())
        self.assertTrue(out['saved'])
        self.assertTrue(self.control.clipboard_capture('texto', 'Canal: Games EduUu\nhttps://www.youtube.com/@GamesEduUu'.encode())['duplicate'])
        png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + (2).to_bytes(4, 'big') + (3).to_bytes(4, 'big') + b'resto')
        image = self.control.clipboard_capture('imagem', png)
        for kind, data in (('texto', b'\xff\xfe'), ('texto', b'   '), ('imagem', b'nao-png'), ('audio', b'x'),
                           ('texto', b'a' * (1024 ** 2 + 1))):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.control.clipboard_capture(kind, data)
        state = self.control.clipboard_capture_state()
        self.assertEqual(state['count'], 2); self.assertIn('imagem 2x3', state['latest'][0])
        self.assertTrue(Path(state['folder']).is_relative_to(self.root / 'compartilhado'))
        listed = area.listar(self.root)
        self.assertIn('Cópias guardadas: 2', listed); self.assertIn('Games EduUu', listed)
        self.assertIn('https://www.youtube.com/@GamesEduUu', area.ler(self.root, out['id']))
        inbox = self.root / 'inbox'
        seen = area.ler(self.root, '', inbox=inbox)  # vazio = a última, que é a imagem
        self.assertIn('observar_imagem_recebida', seen); self.assertEqual(len(list(inbox.glob('*-copiado-*.png'))), 1)
        self.assertTrue(area.ler(self.root, 'nao-existe').startswith('Não existe'))
        # Retenção: só as mais novas ficam, e os arquivos antigos saem junto.
        with patch.object(area, 'MAX_ITEMS', 3):
            for n in range(5):
                area.save(self.root, 'texto', f'cópia {n}'.encode())
        self.assertEqual([r['preview'] for r in area.items(self.root)], ['cópia 4', 'cópia 3', 'cópia 2'])
        self.assertEqual(len(list((area.folder(self.root) / 'itens').iterdir())), 3)
        # A entidade recebe a ferramenta quando fala da cópia; o grupo "Ler arquivos" pode desligá-la.
        names = {e['function']['name'] for e in dispatch.esquemas('dá uma olhada no que eu copiei')}
        self.assertIn('area_de_transferencia', names)
        from core import ui_policy
        self.assertEqual(ui_policy.requirements('area_de_transferencia'), {'read'})
        # Desligado em Configurações: nada é gravado.
        settings = self.control.ui_settings()
        self.control.save_ui(dict(revision=settings['revision'], settings={'clipboard_auto': False}))
        with self.assertRaisesRegex(ValueError, 'desligado'):
            self.control.clipboard_capture('texto', b'nova')

    def test_pc2_panel_port_needs_lan_ip_host_and_pairing_code(self):
        # 06/11 (pedido humano): o painel do PC2 fala com esta Central pela rede local; o cérebro fica aqui.
        import ipaddress
        from core import central_rede as rede
        self.assertTrue(rede.client_allowed('10.0.0.5', ['10.0.0.0/24']))
        self.assertFalse(rede.client_allowed('10.0.1.5', ['10.0.0.0/24']))
        self.assertFalse(rede.client_allowed('8.8.8.8', []))
        with self.assertRaises(ValueError):rede.networks(['8.8.8.0/24'])
        with self.assertRaises(ValueError):rede.save(self.root, enabled=True, allowed=['0.0.0.0/0'])
        rede.save(self.root, enabled=True, allowed=[])
        code = rede.token(self.root)
        self.assertEqual(rede.token(self.root), code)  # fixo entre aberturas da Central
        self.assertEqual(oct((self.root / rede.TOKEN).stat().st_mode & 0o777), '0o600')
        server, local_token = launcher.make_server(self.supervisor, 0, self.audio); self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start(); self.addCleanup(server.shutdown)
        loopback = (ipaddress.IPv4Network('127.0.0.0/8'),)
        with patch.object(rede, 'PRIVATE', rede.PRIVATE + loopback):  # o teste usa loopback no lugar da LAN
            lan = launcher.make_lan_server(server, dict(enabled=True, port=0, allowed=['127.0.0.0/8'], bind='127.0.0.1'), code)
            self.addCleanup(lan.server_close)
            threading.Thread(target=lan.serve_forever, daemon=True).start(); self.addCleanup(lan.shutdown)
            def call(srv, path, secret, host=None, data=None):
                req = Request(f'http://127.0.0.1:{srv.server_port}/api/{path}', data=data,
                              headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json',
                                       'Host': host or f'127.0.0.1:{srv.server_port}'})
                try:
                    with urlopen(req, timeout=5) as r: return r.status, json.load(r)
                except HTTPError as exc: return exc.code, None
            self.assertEqual(call(lan, 'control/entities', code)[0], 200)
            self.assertEqual(call(lan, 'control/entities', local_token)[0], 403)  # credencial local não vale na rede
            self.assertEqual(call(lan, 'control/entities', code, host='evil.example:80')[0], 403)
            self.assertEqual(call(lan, 'control/rede', code)[0], 403)  # o PC2 não lê o código...
            self.assertEqual(call(lan, 'control/rede', code, data=b'{"enabled": false}')[0], 403)  # ...nem desliga
            status, state = call(server, 'control/rede', local_token)
            self.assertEqual((status, state['enabled'], state['code'], state['active']), (200, True, code, True))
            with patch.object(rede, 'client_allowed', return_value=False):
                self.assertEqual(call(lan, 'control/entities', code)[0], 403)
            # Salvar aplica na hora (antes só ao reabrir a Central): porta nova com o código novo; o antigo cai.
            real = launcher.make_lan_server
            def loopback_lan(local, settings=None, token=None):
                return real(local, dict(enabled=True, port=0, allowed=['127.0.0.0/8'], bind='127.0.0.1'), token)
            with patch.object(launcher, 'make_lan_server', loopback_lan):
                status, saved = call(server, 'control/rede', local_token, data=b'{"enabled": true, "regenerate": true}')
            new_lan = server.lan_server; self.addCleanup(new_lan.server_close); self.addCleanup(new_lan.shutdown)
            self.assertIsNot(new_lan, lan); self.assertTrue(saved['active']); self.assertNotEqual(saved['code'], code)
            self.assertEqual(call(new_lan, 'control/entities', saved['code'])[0], 200)
            self.assertEqual(call(new_lan, 'control/entities', code)[0], 403)
            status, off = call(server, 'control/rede', local_token, data=b'{"enabled": false}')
            self.assertEqual((status, off['active'], off['code']), (200, False, None))
            self.assertIsNone(getattr(server, 'lan_server', None))

    def test_pc2_and_light_desktop_installers_parse_and_refuse_bad_input_offline(self):
        # Sem rede, sudo ou apt: só sintaxe e as recusas antes de qualquer efeito.
        for script in ('instalar_painel_pc2.sh', 'instalar_desktop_leve.sh'):
            self.assertEqual(subprocess.run(['bash', '-n', str(ROOT / 'scripts' / script)]).returncode, 0, script)
        env = {'PATH': os.environ['PATH'], 'HOME': str(self.root), 'HOSHINO_PAINEL_DIR': str(self.root / 'painel')}
        for args in ([], ['10.0.0.102'], ['8.8.8.8', 'codigo'], ['127.0.0.1', 'codigo'], ['10.0.0.102', 'codigo', '80']):
            with self.subTest(args=args):
                r = subprocess.run(['bash', str(ROOT / 'scripts/instalar_painel_pc2.sh'), *args], env=env,
                                   capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode, 2, r.stderr); self.assertNotIn('Traceback', r.stderr)
        self.assertFalse((self.root / 'painel').exists())
        text = (ROOT / 'scripts/instalar_painel_pc2.sh').read_text()
        self.assertIn('/api/control/gpu-alerts', text); self.assertNotIn('reset --hard', text)

    def test_pc2_body_commands_need_panel_permission_and_are_never_replayed(self):
        # 06/11 (pedido humano): comandos das entidades rodam no PC2 pelo painel de lá.
        from core import pc2_remoto as pc2
        clock = [1000.0]
        now = lambda: clock[0]
        self.assertIn('painel do PC2 está fechado', pc2.executar(self.root, 'lilith', 'ls', now=now))
        pc2.proximo(self.root, permitido=False, now=clock[0])
        self.assertIn('permissão', pc2.executar(self.root, 'lilith', 'ls', now=now))
        self.assertIsNone(pc2.proximo(self.root, permitido=False, now=clock[0]))
        # Painel permitido: a entidade enfileira; o painel pega, roda e devolve (simulado no "sleep").
        pc2.proximo(self.root, permitido=True, now=clock[0])
        def panel_tick(_):
            clock[0] += 0.5
            job = pc2.proximo(self.root, permitido=True, now=clock[0])
            if job:
                self.assertEqual((job['comando'], job['entidade']), ('uname -n', 'lilith'))
                pc2.concluir(self.root, job['id'], 0, 'gutavo2-A320M-DX\n', now=clock[0])
        out = pc2.executar(self.root, 'lilith', 'uname -n', timeout=5, sleep=panel_tick, now=now)
        self.assertTrue(out.startswith('[PC2 | uname -n | saída 0]'), out); self.assertIn('gutavo2', out)
        with self.assertRaisesRegex(ValueError, 'não está em execução'):
            pc2.concluir(self.root, 'pc2-' + 'f' * 10, 0, '')
        # Pedido que ninguém pega expira sem executar; pego e não concluído fica incerto (nunca reenvia).
        clock[0] += 1; pc2.proximo(self.root, permitido=True, now=clock[0])
        out = pc2.executar(self.root, 'lilith', 'sleep 1', timeout=2, sleep=lambda _: clock.__setitem__(0, clock[0] + 1), now=now)
        self.assertIn('NÃO foi executado', out)
        pc2.proximo(self.root, permitido=True, now=clock[0])
        def claim_only(_):
            clock[0] += 1.0
            pc2.proximo(self.root, permitido=True, now=clock[0])
        out = pc2.executar(self.root, 'lilith', 'sleep 999', timeout=2, sleep=claim_only, now=now)
        self.assertTrue(out.startswith('RESULTADO_INCERTO'), out)
        ident = out.split('id=')[-1].rstrip('.')
        self.assertEqual(pc2.consultar(self.root, ident)['status'], 'executando')

    def test_pc2_command_tool_guards_risk_reads_exit_code_and_is_offered_when_pc2_is_mentioned(self):
        from core import dispatch, pc2_remoto, ui_policy
        handler = dispatch.HANDLERS['executar_no_pc2']
        with patch.object(pc2_remoto, 'executar', side_effect=AssertionError('não deve sair do PC1')):
            self.assertTrue(handler({'comando': 'rm -rf /'}, None).startswith('BLOQUEADO'))
            self.assertEqual(handler({'comando': '  '}, None), 'Erro: comando vazio.')
        cases = (('[PC2 | ls | saída 0]\narquivo', 'success'), ('[PC2 | ls x | saída 2]\nnão existe', 'error'),
                 ('Falha: o painel do PC2 está fechado agora', 'error'),
                 ('RESULTADO_INCERTO: o comando pc2-1 começou', 'uncertain'))
        for n, (text, status) in enumerate(cases):  # comandos distintos: incerto bloqueia repetir o mesmo
            with self.subTest(text=text), patch.object(pc2_remoto, 'executar', return_value=text):
                result = dispatch.executar_resultado('executar_no_pc2', {'comando': f'ls {n}'})
                self.assertEqual(result['status'], status); self.assertFalse(result['requires_verification'])
        self.assertEqual(ui_policy.requirements('executar_no_pc2'), {'code'})
        names = {e['function']['name'] for e in dispatch.esquemas('roda um ls lá no pc2 pra mim')}
        self.assertIn('executar_no_pc2', names)

    def test_pc2_screen_open_and_origin_follow_where_the_person_asked(self):
        # 06/11 (pedido humano): ver a tela e abrir coisas onde a pessoa pediu (PC1 ou PC2).
        from core import pc2_remoto as pc2, dispatch
        clock = [2000.0]; now = lambda: clock[0]
        pc2.proximo(self.root, permitido=True, permitido_tela=False, now=clock[0])
        self.assertIn('vejam a tela', pc2.capturar_tela(self.root, 'hoshino', now=now)[1])
        png = b'\x89PNG\r\n\x1a\n' + b'0' * 64
        def panel(_):
            clock[0] += 0.5
            job = pc2.proximo(self.root, permitido=False, permitido_tela=True, now=clock[0])
            if job:
                self.assertEqual(job['tipo'], 'tela')
                pc2.guardar_tela(self.root, job['id'], png)
        pc2.proximo(self.root, permitido=False, permitido_tela=True, now=clock[0])
        path, err = pc2.capturar_tela(self.root, 'hoshino', sleep=panel, now=now)
        self.assertIsNone(err); self.assertEqual(Path(path).read_bytes(), png)
        self.assertTrue(Path(path).is_relative_to(self.root / 'compartilhado/runtime/pc2_telas'))
        with self.assertRaisesRegex(ValueError, 'não está em execução'):
            pc2.guardar_tela(self.root, 'pc2-naoexiste', png)
        # Shell não roda com só a permissão de tela; a de tela não deixa rodar comando.
        self.assertIn('abram e executem', pc2.executar(self.root, 'hoshino', 'ls', now=now))
        # Abrir: endereço vai para o navegador padrão; app pelo nome; nada de texto livre.
        with patch.object(pc2, 'executar', side_effect=lambda root, ent, cmd, t, **kw: cmd):
            self.assertEqual(pc2.abrir(self.root, 'lilith', 'https://www.youtube.com/watch?v=abc'),
                             "xdg-open 'https://www.youtube.com/watch?v=abc'")  # entre aspas: nada vira comando
            self.assertIn('setsid -f firefox', pc2.abrir(self.root, 'lilith', 'firefox'))
            self.assertTrue(pc2.abrir(self.root, 'lilith', 'rm -rf ~; firefox').startswith('Erro'))
        # observar_tela sem máquina olha onde a pessoa escreveu; com maquina=pc1, a tela local.
        vision = type('V', (), {'observar_imagem': staticmethod(lambda c, q: f'imagem {Path(c).name}: {q}'),
                                'observar_tela': staticmethod(lambda q: 'tela do PC1')})
        with patch.object(dispatch, '_visao', return_value=vision), \
             patch.object(pc2, 'capturar_tela', return_value=(path, None)):
            token = pc2.ORIGEM_TURNO.set('pc2')
            try:
                self.assertTrue(dispatch.HANDLERS['observar_tela']({}, None).startswith('[tela do PC2]'))
                self.assertEqual(dispatch.HANDLERS['observar_tela']({'maquina': 'pc1'}, None), 'tela do PC1')
            finally:
                pc2.ORIGEM_TURNO.reset(token)
            self.assertEqual(dispatch.HANDLERS['observar_tela']({}, None), 'tela do PC1')
        self.assertIn('PC2', pc2.contexto_origem('pc2')); self.assertIn('PC1', pc2.contexto_origem('pc1'))
        self.assertEqual(pc2.contexto_origem(None), '')
        # Continuação: ferramentas usadas há pouco voltam; "tela" e "vídeo" chamam as certas.
        self.assertTrue({'navegador', 'web'} <= dispatch.grupos_das_ferramentas(['browser_info', 'web_search']))
        for text, tool in (('pode dar uma olhada na minha tela?', 'observar_tela'),
                           ('abre o último vídeo do canal', 'browser_clicar')):
            with self.subTest(text=text):
                self.assertIn(tool, {e['function']['name'] for e in dispatch.esquemas(text)})
        names = {e['function']['name'] for e in dispatch.esquemas('pode me dizer mais detalhes?', grupos_extras={'web'})}
        self.assertIn('fetch_page', names)

    def test_pc2_senses_reach_the_entities_and_only_the_lan_panel_can_send_them(self):
        from core import pc2_remoto as pc2, world_state
        store = world_state.Store(self.root / 'world.sqlite3')
        pc2.guardar_sentidos(dict(janela_ativa='YouTube — Mozilla Firefox', janelas=['Terminal', 'YouTube — Mozilla Firefox'],
                                  ociosidade_x11=3.0, midia={}, load1=0.4, extra='ignorado'), store=store)
        state = store.snapshot()
        values = world_state.fresh_values(state)
        self.assertEqual(pc2.sentidos(values)['janela_ativa'], 'YouTube — Mozilla Firefox')
        store.observe('collector.health', {'running': True}, source='central', ttl=30)
        store.observe('desktop.active_window', 'Terminal - Claude', source='central', ttl=30)
        store.observe('desktop.idle_seconds', 600.0, source='central', ttl=30)
        view = world_state.sensor_view(store.snapshot())
        self.assertEqual((view['maquina_em_uso'], view['janela_ativa'], view['janela_ativa_pc1']),
                         ('PC2', 'YouTube — Mozilla Firefox', 'Terminal - Claude'))
        self.assertIn('PC2 (painel da pessoa)', pc2.descrever(view['pc2']))
        self.assertNotIn('extra', json.dumps(values))
        # Rotas do corpo remoto: só a porta da rede; a cópia registra de qual PC veio.
        server, local_token = launcher.make_server(self.supervisor, 0, self.audio); self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start(); self.addCleanup(server.shutdown)
        def post(srv, path, secret, data, *, raw=False, host=None):
            req = Request(f'http://127.0.0.1:{srv.server_port}/api/{path}', data=data if raw else json.dumps(data).encode(),
                          headers={'Authorization': 'Bearer ' + secret, 'Host': host or f'127.0.0.1:{srv.server_port}',
                                   'Content-Type': 'application/octet-stream' if raw else 'application/json'})
            try:
                with urlopen(req, timeout=5) as r: return r.status, json.load(r)
            except HTTPError as exc: return exc.code, None
        self.assertEqual(post(server, 'control/pc2/proximo', local_token, {'permitido': True})[0], 403)
        import ipaddress
        from core import central_rede as rede
        code = rede.token(self.root)
        with patch.object(rede, 'PRIVATE', rede.PRIVATE + (ipaddress.IPv4Network('127.0.0.0/8'),)):
            lan = launcher.make_lan_server(server, dict(enabled=True, port=0, allowed=['127.0.0.0/8'], bind='127.0.0.1'), code)
            self.addCleanup(lan.server_close)
            threading.Thread(target=lan.serve_forever, daemon=True).start(); self.addCleanup(lan.shutdown)
            self.assertEqual(post(lan, 'control/pc2/proximo', code, {'permitido': True}), (200, {'comando': None}))
            self.assertEqual(post(lan, 'control/pc2/proximo', code, {'permitido': True, 'x': 1})[0], 400)
            with patch.object(world_state, 'default_path', return_value=self.root / 'world.sqlite3'):
                status, saved = post(lan, 'control/pc2/sentidos', code, {'estado': {'janela_ativa': 'Barrier'}})
            self.assertEqual((status, saved['saved']), (200, True))
            status, copied = post(lan, 'control/clipboard?kind=texto', code, 'copiado no PC2'.encode(), raw=True)
            sent_lan = post(lan, 'send', code, {'entity': 'lilith', 'text': 'abre o youtube aqui'})
            sent_local = post(server, 'send', local_token, {'entity': 'lilith', 'text': 'abre o youtube aqui no pc1'})
        self.assertEqual(status, 200)
        self.assertEqual((sent_lan[0], sent_local[0]), (200, 200))
        origins = [m['metadata'].get('origem_maquina') for m in bus.inbox('lilith', limit=10)]
        self.assertEqual(origins[-2:], ['pc2', 'pc1'])
        from core import area_transferencia as area
        self.assertEqual(area.items(self.root)[0]['origem'], 'pc2')
        self.assertIn('copiado no PC2', area.describe(area.items(self.root)[0]))

    def test_deep_research_reads_sources_cites_links_and_attaches_source_images(self):
        # 06/11 (pedido humano): pesquisa profunda com fontes lidas, links e imagens das fontes. Sem rede.
        import io as _io
        from PIL import Image
        from core import rede, audio_text, dispatch
        from tools import pesquisa_profunda as pp
        buf = _io.BytesIO(); Image.new('RGB', (640, 360), (40, 90, 160)).save(buf, format='PNG'); capa = buf.getvalue()
        paginas = {
            'https://pt.wikipedia.org/wiki/The_Boxer': ('<html><head><title>The Boxer – Wikipédia</title>'
                '<meta property="og:image" content="/capa.png"></head><body><nav>menu</nav><p>The Boxer é um manhwa sul-coreano '
                'escrito e ilustrado por Jung Ji-Hoon, publicado no Naver Webtoon de 2019 a 2023.</p>'
                '<p>O protagonista Yu é um garoto de talento extraordinário para o boxe, treinado por K.</p></body></html>'),
            'https://exemplo.com/boxer-anime': ('<html><body><p>A adaptação para anime de The Boxer foi anunciada; '
                'o manhwa de Jung Ji-Hoon acompanha Yu e seus adversários.</p></body></html>'),
            'https://pt.wikipedia.org/capa.png': capa,
        }
        def baixar(url, limite, *, aceitar):
            data = paginas[url]
            tipo = 'image/png' if isinstance(data, bytes) else 'text/html'
            if not aceitar(tipo): raise ValueError(tipo)
            return (data if isinstance(data, bytes) else data.encode()), url, tipo
        busca = lambda q, n: [dict(title='The Boxer (manhwa)', href='https://pt.wikipedia.org/wiki/The_Boxer'),
                              dict(title='Anime de The Boxer', href='https://exemplo.com/boxer-anime'),
                              dict(title='Fora do ar', href='https://fora.example/x')]
        with patch.object(rede, 'exigir', return_value=(True, '')):
            out = pp.pesquisar('o que é o manhwa The Boxer', 5, buscar=busca,
                               baixar=lambda u, l, aceitar: baixar(u, l, aceitar=aceitar), root=self.root)
        self.assertIn('[1] The Boxer (manhwa) — https://pt.wikipedia.org/wiki/The_Boxer', out)
        self.assertIn('[2] Anime de The Boxer — https://exemplo.com/boxer-anime', out)
        self.assertIn('garoto de talento extraordinário', out); self.assertNotIn('menu', out)
        ident = re.search(r'\[\[imagem:([0-9a-f]{12})\]\] \(da fonte \[1\]', out).group(1)
        self.assertTrue((pp.pasta_anexos(self.root) / f'{ident}.jpg').is_file())
        self.assertIn('cite [1], [2]', out)
        with patch.object(rede, 'exigir', return_value=(False, 'Internet desligada.')):
            self.assertEqual(pp.pesquisar('qualquer coisa', buscar=busca, root=self.root), 'Internet desligada.')
        self.assertNotIn('imagem', audio_text.clean_for_speech(f'Olha a capa [[imagem:{ident}]] aqui.'))
        names = {e['function']['name'] for e in dispatch.esquemas('pesquisa a fundo sobre the boxer com fontes')}
        self.assertIn('pesquisa_profunda', names)
        # A Central entrega a imagem anexada (local ou PC2); ID fora do formato não lê nada do disco.
        server, local_token = launcher.make_server(self.supervisor, 0, self.audio); self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start(); self.addCleanup(server.shutdown)
        def get(path):
            req = Request(f'http://127.0.0.1:{server.server_port}/api/{path}',
                          headers={'Authorization': 'Bearer ' + local_token, 'Host': f'127.0.0.1:{server.server_port}'})
            try:
                with urlopen(req, timeout=5) as r: return r.status, r.headers.get('Content-Type'), r.read()
            except HTTPError as exc: return exc.code, None, b''
        status, tipo, data = get(f'control/anexo?id={ident}')
        self.assertEqual((status, tipo), (200, 'image/jpeg')); self.assertTrue(data.startswith(b'\xff\xd8'))
        self.assertEqual(get('control/anexo?id=../../etc/passwd')[0], 400)
        self.assertEqual(get('control/anexo?id=' + 'f' * 12)[0], 404)

    def test_activity_tab_lists_quick_pc1_commands_and_pc2_requests_with_output(self):
        # 06/11 (pedido humano): "Comandos e saída" ficava sempre vazia (só jobs em segundo plano apareciam).
        from tools import terminal
        from core import pc2_remoto
        runtime = self.control.paths('lilith').runtime
        meta = dict(id='job-abc12345', entity='lilith', comando='g++ main.cpp -o main', ambiente='oficina',
                    cwd='/oficina', inicio='2026-11-06T20:36:09')
        with patch.object(terminal, 'config', create=True), patch('config.RUNTIME_DIR', str(runtime)):
            terminal._registrar_recente(meta, 1, 'main.cpp:3: erro: falta ;')
        pc2_remoto.proximo(self.root, permitido=True)
        ident = pc2_remoto.enfileirar(self.root, 'lilith', 'uname -n', 10)
        job = pc2_remoto.proximo(self.root, permitido=True)
        pc2_remoto.concluir(self.root, job['id'], 0, 'gutavo2\n')
        pc2_remoto.enfileirar(self.root, 'hoshino', 'ls', 10)  # de outra entidade: não aparece
        items = self.control.commands('lilith')['items']
        by_id = {r['id']: r for r in items}
        self.assertEqual((by_id['job-abc12345']['onde'], by_id['job-abc12345']['status'], by_id['job-abc12345']['codigo']),
                         ('PC1', 'falhou', 1))
        self.assertIn('falta ;', by_id['job-abc12345']['output'])
        self.assertEqual((by_id[ident]['onde'], by_id[ident]['output'], by_id[ident]['codigo']), ('PC2', 'gutavo2\n', 0))
        self.assertEqual(len(items), 2)
        # Eventos recentes: rotina escondida por padrão; rotina=1 mostra.
        folder = runtime / 'diagnostics'; folder.mkdir(parents=True, exist_ok=True)
        lines = [dict(ts='2026-11-06T23:00:0%d+00:00' % i, event=e, level='INFO', data=dict(entity='lilith', **d))
                 for i, (e, d) in enumerate([('cognition.autonomy_decision', {'tipo': 'nada'}), ('gpu.app_close_skipped', {}),
                                             ('cognition.autonomy_decision', {'tipo': 'explorar'}), ('tool.end', {'tool': 'web_search'})])]
        (folder / 'hoshino_2026-11-06.jsonl').write_text('\n'.join(json.dumps(l) for l in lines) + '\n')
        shown = [r['event'] for r in self.control.activity('lilith', {})['items']]
        self.assertEqual(sorted(shown), ['cognition.autonomy_decision', 'tool.end'])
        self.assertEqual(len(self.control.activity('lilith', {'rotina': '1'})['items']), 4)

    def test_invalid_context_output_and_shell_model_rejected(self):
        data=self.model_data()
        for value in (0,-1,20000,True,'8192',None):
            with self.assertRaises(ValueError):self.control.save_model(data|dict(context=value))
        with self.assertRaises(ValueError):self.control.save_model(data|dict(output=9000))
        with self.assertRaises(ValueError):self.control.save_model(data|dict(model='$(touch /tmp/pwn)'))

    def test_output_without_prompt_room_rejected_without_config_write(self):
        data=self.model_data();path=self.control.env_path('hoshino');before=path.read_bytes()
        for output in (2048,2047,1537):
            with self.subTest(output=output),self.assertRaisesRegex(ValueError,'entrada'):
                self.control.save_model(data|dict(context=2048,output=output))
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(path.parent.glob('*.backup-*')),[])
        self.assertTrue(self.control.save_model(data|dict(context=2048,output=1536))['saved'])

    def test_active_entity_refuses_model_change(self):
        data=self.model_data();bus.register('hoshino','awake')
        with self.assertRaises(ValueError):self.control.save_model(data)

    def test_active_job_refuses_model_change(self):
        data=self.model_data();job_bus.publish('active','hoshino','running',kind='llm_speech')
        with self.assertRaises(ValueError):self.control.save_model(data)

    def test_external_entity_lock_refuses_model_change(self):
        data=self.model_data();import fcntl
        with (self.root/'entidades/hoshino/runtime/entity.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with self.assertRaises(ValueError):self.control.save_model(data)

    def test_no_cross_entity_alias_or_missing_model(self):
        data=self.model_data();self.assertFalse(self.control.model_settings('lilith')['options'])
        with self.assertRaises(ValueError):self.control.save_model(data|dict(entity='lilith'))

    def test_key_never_returned_or_accepted(self):
        with patch.dict(os.environ,{'ELEVENLABS_API_KEY':'SECRET_SENTINEL','DISCORD_TOKEN':'OTHER_SECRET'}):
            output=json.dumps(self.control.audio_settings());self.assertNotIn('SECRET_SENTINEL',output)
            self.assertTrue(self.control.audio_settings()['providers']['elevenlabs']['key_configured'])
            self.assertNotIn('OTHER_SECRET',json.dumps(cc.redact({'output':'OTHER_SECRET'})))
            with self.assertRaises(ValueError):self.control.save_audio(dict(api_key='SECRET_SENTINEL'))

    def test_resources_cache_is_a_plan_not_fake_actual_usage_or_secret_environment(self):
        with patch.object(rm.config,'RAIZ',self.root),patch.dict(os.environ,{'ELEVENLABS_API_KEY':'CACHE_SECRET_SENTINEL'}):
            out=self.control.system()
        cache=out['ram_prompt_cache']
        self.assertEqual(cache['state'],'planned_not_verified')
        self.assertEqual(cache['apply'],'next_managed_daemon_boot')
        self.assertIsNone(cache['used_bytes'])
        self.assertFalse(cache['swap_in_budget'])
        self.assertLessEqual(cache['aggregate_mib'],8192)
        self.assertNotIn('CACHE_SECRET_SENTINEL',json.dumps(out))

    def test_resource_profile_observations_are_bounded_metadata_not_live_state_or_diary(self):
        folder=self.control.paths('hoshino').runtime/'diagnostics';folder.mkdir(exist_ok=True)
        events=[dict(event='private.note',data=dict(text='PRIVATE_SENTINEL')),
            dict(event='executor.selected',data=dict(entity='hoshino',resource_profile=dict(id=[]))),
            dict(event='executor.selected',ts='2026-10-24T12:00:00Z',data=dict(entity='hoshino',model='primary',tier='principal',
                prompt='PRIVATE_SENTINEL',resource_profile=dict(id='shared',reason='other_entity_demand',
                requested='shared',held=False,extra='PRIVATE_SENTINEL'))),
            dict(event='executor.selected',data=dict(entity='lilith',resource_profile=dict(id='quality')))]
        (folder/'fixture.jsonl').write_text('\n'.join(json.dumps(r) for r in events)+'\n')
        with patch.object(rm._profile_controller,'choose',side_effect=AssertionError('read only')):
            out=self.control.system()['resource_profiles']
        self.assertEqual(out['state'],'last_observed_not_live')
        self.assertEqual(out['observations']['hoshino']['id'],'shared')
        self.assertIsNone(out['observations']['lilith'])
        self.assertEqual(len(out['available']),6)
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(out))

    def test_provider_switch_without_quota_preserves_unknown(self):
        data=dict(preferred_provider='elevenlabs',enabled=True,voices={'hoshino':'chosen-h','lilith':'chosen-l'},revision=self.control.audio_settings()['revision'])
        with patch('core.tts_router.urlopen',side_effect=AssertionError('quota forbidden')):
            result=self.control.save_audio(data)
        self.assertFalse(result['quota_used']);self.assertTrue(self.audio.settings['unknown']['preserve'])
        self.assertFalse(self.audio.settings['azure']['enabled']);self.assertTrue(self.audio.settings['elevenlabs']['enabled'])

    def test_switch_audio_during_pending_rejected(self):
        self.audio.cancels['busy']=threading.Event()
        with self.assertRaises(ValueError):self.control.save_audio(dict(preferred_provider='qwen3_tts',enabled=False,revision=self.control.audio_settings()['revision']))
        self.audio.cancels.clear()

    def test_invalid_azure_voice(self):
        with self.assertRaises(ValueError):self.control.save_audio(dict(preferred_provider='azure',enabled=True,voices={'hoshino':'en-US-voice'},revision=self.control.audio_settings()['revision']))

    def test_memory_read_only_filters_and_zero_provenance(self):
        path=self.root/'entidades/lilith/memory/sqlite/lilith.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE memories (id TEXT,type TEXT,content TEXT,source TEXT,confidence REAL,links TEXT)')
            db.execute('INSERT INTO memories VALUES (?,?,?,?,?,?)',('mem-a','hipotese','Gustavo joga','usuario',0.0,json.dumps([{'author_id':'gustavo','turn_id':'turn-a'}])))
        db.close()
        before=path.read_bytes();out=self.control.memory('lilith',{'type':'hipotese','author':'gustavo','turn':'turn-a'})
        self.assertEqual(len(out['items']),1);self.assertEqual(out['items'][0]['confianca'],0.0);self.assertEqual(path.read_bytes(),before)
        self.assertEqual(self.control.memory('hoshino',{})['items'],[])
        self.assertEqual(self.control.memory('lilith',{'type':'fato'})['items'],[])

    def test_memory_inspector_never_imports_mutable_vector_store(self):
        with patch.dict(sys.modules,{'memory.knowledge_store':None,'memory.vector.chroma_store':None}):
            self.assertEqual(self.control.memory('lilith',{})['items'],[])

    def test_activity_correlation_private_thought_and_secret_hidden(self):
        folder=self.root/'entidades/hoshino/runtime/diagnostics';folder.mkdir()
        (folder/'day.jsonl').write_text(json.dumps(dict(ts='2026-10-07T10:00:00',event='llm.start',level='INFO',data={'entity':'hoshino','turn_id':'t1','request_id':'r1','thinking':'private','api_key':'secret'}))+'\n')
        out=self.control.activity('hoshino',{'turn':'t1'});self.assertEqual(len(out['items']),1)
        self.assertNotIn('private',json.dumps(out));self.assertNotIn('"secret"',json.dumps(out));self.assertFalse(out['global_causal_order'])

    def test_activity_shared_logger_authorship_and_explicit_mirror_dedup(self):
        folder=self.root/'entidades/hoshino/runtime/diagnostics';folder.mkdir()
        record=dict(ts='2026-10-07T10:00:00',event='central.config_saved',level='INFO',diagnostic_id='diag-fixture',data={'entity':'lilith'})
        (folder/'day.jsonl').write_text(json.dumps(record)+'\n')
        db=sqlite3.connect(self.root/'entidades/hoshino/runtime/history.sqlite3')
        try:
            db.execute('CREATE TABLE events (id TEXT,ts TEXT,kind TEXT,severity TEXT,data TEXT,turn_id TEXT)')
            db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',('mirror',record['ts'],record['event'],'INFO',json.dumps({'entity':'lilith','_diagnostic_id':'diag-fixture'}),'turn-fixture'));db.commit()
        finally:db.close()
        self.assertEqual(len(self.control.activity('lilith',{})['items']),1)
        self.assertEqual(self.control.activity('hoshino',{})['items'],[])

    def test_command_tail_is_bounded_redacted_and_honest_combined(self):
        jobs=self.root/'entidades/hoshino/runtime/jobs';jobs.mkdir()
        (jobs/'job-a.json').write_text(json.dumps(dict(id='job-a',entity='hoshino',comando='echo hello',codigo=None,status='rodando')))
        (jobs/'job-a.log').write_text('a'*40000+'\napi_key=supersecret')
        row=self.control.commands('hoshino')['items'][0];self.assertLess(len(row['output']),33000);self.assertNotIn('supersecret',row['output']);self.assertIn('combinados',row['stream']);self.assertIsNone(row['codigo'])

    def test_activity_orders_and_filters_mixed_utc_and_legacy_without_rewriting(self):
        folder=self.root/'entidades/hoshino/runtime/diagnostics';folder.mkdir()
        records=[dict(ts='2026-10-09T23:50:00',event='legacy',level='INFO',data={'entity':'hoshino'}),
                 dict(ts='2026-10-10T02:45:00+00:00',event='earlier',level='INFO',data={'entity':'hoshino'}),
                 dict(ts='2026-10-10T03:05:00+00:00',event='later',level='INFO',data={'entity':'hoshino'})]
        path=folder/'day.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in records));before=path.read_bytes()
        with patch.object(cc.history.config,'LOCAL_TIMEZONE','America/Sao_Paulo',create=True):
            out=self.control.activity('hoshino',{})
            self.assertEqual([r['event'] for r in out['items']],['later','legacy','earlier'])
            self.assertTrue(out['legacy_timezone_unknown']);self.assertFalse(out['global_causal_order'])
            filtered=self.control.activity('hoshino',{'since':'2026-10-10T02:48:00Z','until':'2026-10-10T03:00:00Z'})
        self.assertEqual([r['event'] for r in filtered['items']],['legacy'])
        self.assertFalse(filtered['items'][0]['timestamp']['timezone_known'])
        self.assertEqual(path.read_bytes(),before)

    def test_activity_invalid_time_filter_rejected_not_empty_success(self):
        for key in ('since','until'):
            with self.assertRaisesRegex(ValueError,'temporal'):
                self.control.activity('hoshino',{key:'amanhã'})

    def test_overlay_default_disabled_and_config_validated(self):
        current=self.control.ui_settings();self.assertFalse(current['settings']['overlay_enabled'])
        self.control.save_ui(dict(revision=current['revision'],settings={'reduced_motion':True}))
        self.assertTrue(self.control.ui_settings()['settings']['reduced_motion'])
        current=self.control.ui_settings()
        with self.assertRaises(ValueError):self.control.save_ui(dict(revision=current['revision'],settings={'reduced_motion':'true'}))
        with self.assertRaises(ValueError):self.control.save_ui(dict(revision=current['revision'],settings={'balloon_seconds':100}))
        self.control.save_ui(dict(revision=current['revision'],settings={'positions':{'lilith':[10,20]}}));self.assertEqual(self.control.ui_settings()['settings']['positions']['lilith'],[10,20])

    def test_orb_styles_isolation_validation_and_existing_fields_preserved(self):
        style={'mode':'energy','base_color':'#123456','mood_tint':True,'image_path':''}
        before=self.control.ui_settings()
        self.control.save_ui(dict(revision=before['revision'],settings={'orb_styles':{'hoshino':style}}))
        after=self.control.ui_settings();self.assertEqual(after['settings']['orb_styles'],{'hoshino':style});self.assertEqual(after['settings']['overlay_enabled'],before['settings']['overlay_enabled'])
        for change in ({'mode':'remote'},{'base_color':'red;evil'},{'mood_tint':1},{'image_path':'https://example.com/a.png'},{'image_path':'/tmp/missing-visual-file.png'},{'unknown':True}):
            with self.assertRaises(ValueError):self.control.save_ui(dict(revision=after['revision'],settings={'orb_styles':{'hoshino':style|change}}))
        self.assertEqual(self.control.ui_settings(),after)

    def test_capability_catalog_is_entity_scoped_without_import_dispatch(self):
        with patch.dict(sys.modules,{'core.dispatch':None}):
            main=self.control.capabilities('hoshino');alistair=self.control.capabilities('alistair')
        names={t['name'] for tools in main['groups'].values() for t in tools};self.assertIn('gerar_imagem',names);self.assertIn('minecraft_conectar',names)
        names={t['name'] for tools in alistair['groups'].values() for t in tools}
        self.assertEqual(names,{'central_estado','entidades_historico','entidades_enviar_mensagem','entidades_acordar','usuario_forma_de_tratamento'})

    def test_symlink_config_refused(self):
        data=self.model_data();path=self.control.env_path('hoshino');original=path.read_text();path.unlink();other=path.with_name('outside.env');other.write_text(original);path.symlink_to(other)
        with self.assertRaises(ValueError):self.control.save_model(data)
        self.assertEqual(other.read_text(),original)

    def test_import_validates_space_chunks_hash_and_does_not_activate(self):
        content=b'GGUF\x03\x00\x00\x00fixture';sha=hashlib.sha256(content).hexdigest()
        with patch.object(cc.shutil,'disk_usage',return_value=Mock(free=20*1024**3)):
            job=self.control.begin_import(dict(entity='lilith',name='existing.gguf',size=len(content),sha256=sha))
            with self.assertRaises(ValueError):self.control.import_chunk(job['id'],1,content)
            self.control.import_chunk(job['id'],0,content)
            with self.assertRaises(ValueError):self.control.import_chunk(job['id'],0,content)
            result=self.control.finish_import(job['id'])
        self.assertEqual(Path(result['path']).read_bytes(),content);self.assertTrue(result['verified']);self.assertFalse(result['compatible_executor'])
        self.assertFalse(self.control.model_settings('lilith')['options'])
        with self.assertRaises(ValueError):self.control.begin_import(dict(entity='lilith',name='existing.gguf',size=len(content)))

    def test_import_bad_magic_and_hash_stay_staging(self):
        content=b'GGUF\x03\x00\x00\x00fixture'
        with patch.object(cc.shutil,'disk_usage',return_value=Mock(free=20*1024**3)):
            for name,raw,sha in [('bad.gguf',b'NOTAmodel!',None),('wrong.gguf',content,'0'*64)]:
                job=self.control.begin_import(dict(name=name,size=len(raw),sha256=sha));self.control.import_chunk(job['id'],0,raw)
                with self.assertRaises(ValueError):self.control.finish_import(job['id'])
                self.assertFalse(self.control.transfers[job['id']]['target'].exists())
                self.assertTrue(self.control.transfers[job['id']]['part'].exists());self.control.cancel_transfer(job['id'])

    def test_import_disk_reserve_and_path_rejected(self):
        with patch.object(cc.shutil,'disk_usage',return_value=Mock(free=3*1024**3)):
            with self.assertRaises(ValueError):self.control.begin_import(dict(name='file.gguf',size=100))
        for name in ('../evil.gguf','/tmp/file.gguf','x;touch.gguf','file.bin'):
            with self.assertRaises(ValueError):self.control.begin_import(dict(name=name,size=100))

    def test_cancel_only_owned_partial_and_keeps_existing_weights(self):
        self.install('hoshino');weights=self.control.models('hoshino')[0]['files'][0]['path'];original=Path(weights).read_bytes()
        with patch.object(cc.shutil,'disk_usage',return_value=Mock(free=20*1024**3)):
            job=self.control.begin_import(dict(name='cancel.gguf',size=20));self.control.import_chunk(job['id'],0,b'GGUF1234')
            part=self.control.transfers[job['id']]['part'];self.control.cancel_transfer(job['id']);self.assertFalse(part.exists())
        self.assertEqual(Path(weights).read_bytes(),original)
        with self.assertRaises(ValueError):self.control.cancel_transfer('foreign')

    def test_export_verified_copy_retains_original(self):
        self.install('hoshino');row=self.control.model_files()['items'][0];original=Path(row['path']).read_bytes()
        with patch.object(cc.shutil,'disk_usage',return_value=Mock(free=20*1024**3)):
            result=self.control.export_file(dict(entity='hoshino',id=row['id']));self.assertFalse(result['verified'])
            self.control.transfer_threads[-1].join(3)
        self.assertEqual(self.control.transfers[result['id']]['state'],'done');self.assertEqual(Path(result['path']).read_bytes(),original)
        self.assertEqual(Path(row['path']).read_bytes(),original)

    def test_annotate_after_terminal_does_not_revive_or_adopt_pid(self):
        job_bus.publish('audio-fixture','hoshino','running',kind='audio_tts');job_bus.publish('audio-fixture','hoshino','done',kind='audio_tts')
        before=job_bus.get('audio-fixture');job_bus.annotate('audio-fixture','hoshino',playback_event='started')
        after=job_bus.get('audio-fixture');self.assertEqual(after['status'],'done');self.assertEqual(after['pid'],before['pid']);self.assertEqual(after['details']['playback_event'],'started')
        with self.assertRaises(ValueError):job_bus.annotate('audio-fixture','lilith',playback_event='cancelled')

    def test_finished_synthesis_can_request_playback_cancel_only_same_entity(self):
        for entity in ('hoshino','lilith'):
            job_bus.publish('audio-'+entity,entity,'done',kind='audio_tts',playback_owner=self.audio.playback_owner,
                            chunks=[dict(index=0,duration_seconds=1)])
            self.audio.playback_event(entity,'audio-'+entity,'started',0,'native')
        self.audio.interrupt_entity('hoshino')
        self.assertTrue(job_bus.get('audio-hoshino')['details']['playback_cancel_at'])
        self.assertNotIn('playback_cancel_at',job_bus.get('audio-lilith')['details']);self.assertEqual(job_bus.get('audio-hoshino')['status'],'done')

    def test_social_event_is_authored_durable_dedup_not_emotion_write(self):
        data=dict(entity='lilith',interaction='carinho',submission_id='social-fixture-1')
        first=self.control.social(data);second=self.control.social(data);self.assertEqual(first['id'],second['id'])
        message=bus.inbox('lilith')[0];self.assertEqual(message['sender'],'usuario');self.assertEqual(message['metadata']['source'],'overlay_social')
        self.assertFalse((self.root/'entidades/lilith/runtime/estado_psicologico.json').exists())

    def test_focus_explicit_bounded_and_unknown_after_restart(self):
        self.assertFalse(self.control.focus_state()['known']);self.control.focus(dict(client_id='focus-fixture',focused=False));self.assertFalse(self.control.focus_state()['focused'])
        self.control.focus(dict(client_id='focus-other',focused=True));self.assertTrue(self.control.focus_state()['focused'])
        with self.assertRaises(ValueError):self.control.focus(dict(client_id='bad',focused='true'))
        self.control.focus(dict(client_id='focus-fixture',focused=False,closed=True));self.control.focus(dict(client_id='focus-other',focused=False,closed=True))
        self.assertEqual(self.control.focus_state()['basis'],'explicit_pagehide');self.assertFalse(self.control.focus_state()['focused'])

    def test_overlay_disabled_never_starts_process(self):
        with patch('subprocess.Popen',side_effect=AssertionError('should not launch')):
            with self.assertRaises(ValueError):self.control.start_overlay()

    def test_overlay_orb_state_position_and_separate_assets(self):
        spec=importlib.util.spec_from_file_location('overlay_test',ROOT/'app/ui/overlay.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.clamp_position(2000,-30,(0,0,1920,1080)),(1832,0))
        self.assertLessEqual(len(module.balloon_text({'text':'x'*1000})),205)
        self.assertEqual(module.display_state('lilith',{'presence':[{'entity_id':'lilith','status':'sleeping'}]}),'sleeping')
        colors=[]
        for entity in cc.ENTITIES:
            data=json.loads((ROOT/'app/ui/assets'/entity/'orb.json').read_text());self.assertEqual(data['entity'],entity);colors.append(data['color'])
        self.assertEqual(len(set(colors)),3)

    def test_overlay_process_failure_does_not_shutdown_supervisor(self):
        self.control.overlay_process=Mock();self.control.overlay_process.poll.return_value=1
        out=self.control.overlay_state();self.assertFalse(out['process_alive']);self.assertFalse(self.supervisor.closing)

    def test_overlay_new_request_reads_rotated_local_endpoint_once(self):
        spec=importlib.util.spec_from_file_location('overlay_restart_test',ROOT/'app/ui/overlay.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        folder=self.root/'compartilhado/runtime/launcher';folder.mkdir(parents=True);link=folder/'central.url'
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'{"ok":true}'
        with patch.object(module,'urlopen',return_value=response) as opened:
            for port,token in [(23456,'old-fixture'),(23457,'new-fixture')]:
                link.write_text(f'http://127.0.0.1:{port}/#{token}');module.api(self.root,'sleep',{'entity':'lilith'})
                request=opened.call_args.args[0];self.assertEqual(request.full_url,f'http://127.0.0.1:{port}/api/sleep')
                self.assertEqual(request.get_header('Authorization'),'Bearer '+token)
            self.assertEqual(opened.call_count,2)  # Um pedido por clique, sem retry.
        link.write_text('https://external.invalid/#fixture-secret')
        with patch.object(module,'urlopen',side_effect=AssertionError('sem rede')):
            with self.assertRaises(ValueError):module.api(self.root,'control/overlay')

    def test_overlay_rejects_response_from_previous_session_without_retry(self):
        spec=importlib.util.spec_from_file_location('overlay_stale_test',ROOT/'app/ui/overlay.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        folder=self.root/'compartilhado/runtime/launcher';folder.mkdir(parents=True);link=folder/'central.url';link.write_text('http://127.0.0.1:23456/#old-fixture')
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        def read(*a):link.write_text('http://127.0.0.1:23457/#new-fixture');return b'{"accepted":true}'
        response.read.side_effect=read
        with patch.object(module,'urlopen',return_value=response) as opened:
            with self.assertRaises(ValueError):module.api(self.root,'sleep',{'entity':'lilith'})
            self.assertEqual(opened.call_count,1)

    def test_native_overlay_smoke_offscreen_closing_keeps_fixture_backend(self):
        calls=[];settings={'overlay_enabled':True}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                calls.append(self.path)
                out={'presence':[{'entity_id':e,'status':'sleeping'} for e in cc.ENTITIES],
                     'jobs':[],'replies':{},'interface':{'revision':'fixture','settings':settings},'central_focus':{}}
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(out).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            folder=self.root/'compartilhado/runtime/launcher';folder.mkdir(parents=True);(folder/'central.url').write_text(f'http://127.0.0.1:{server.server_port}/#fixture-token')
            result=subprocess.run(['/usr/bin/python3',str(ROOT/'app/ui/overlay.py'),'--root',str(self.root),'--smoke-seconds','2'],
                                  env={'PATH':os.environ['PATH'],'XDG_CONFIG_HOME':str(self.root),'XDG_CACHE_HOME':str(self.root),'QT_QPA_PLATFORM':'offscreen','QT_OPENGL':'software'},capture_output=True,text=True,timeout=12)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('"orbs": 3',result.stdout)
            print('OVERLAY_METRICS '+result.stdout.strip())
            self.assertEqual(json.loads(result.stdout)['frame_intervals_ms'],dict.fromkeys(cc.ENTITIES,66))
            settings['reduced_motion']=True
            result=subprocess.run(['/usr/bin/python3',str(ROOT/'app/ui/overlay.py'),'--root',str(self.root),'--smoke-seconds','2'],
                                  env={'PATH':os.environ['PATH'],'XDG_CONFIG_HOME':str(self.root),'XDG_CACHE_HOME':str(self.root),'QT_QPA_PLATFORM':'offscreen','QT_OPENGL':'software'},capture_output=True,text=True,timeout=12)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['frame_intervals_ms'],dict.fromkeys(cc.ENTITIES,0))
            self.assertTrue(calls);self.assertTrue(thread.is_alive());self.assertFalse(self.supervisor.closing)
        finally:server.shutdown();server.server_close();thread.join(3)

    def test_confidence_filter_invalid_is_rejected(self):
        # Mesmo sem dados, filtros não podem aceitar NaN ou valores fora de 0–1.
        for value in ('nan','-1','2','oops'):
            with self.assertRaises(ValueError):self.control.memory('lilith',{'confidence':value})

    def test_attachment_scoped_no_overwrite_no_auto_send(self):
        result=self.control.attachment('lilith','draft.txt',b'arquivo de teste')
        self.assertTrue(Path(result['path']).is_relative_to(self.root/'entidades/lilith/runtime/entregas/entrada'))
        self.assertEqual(Path(result['path']).read_bytes(),b'arquivo de teste');self.assertFalse(result['message_sent']);self.assertEqual(bus.inbox('lilith'),[])
        second=self.control.attachment('lilith','draft.txt',b'segundo');self.assertNotEqual(result['path'],second['path'])
        for name in ('discord.env','.env','../escape','api_token.txt'):
            with self.assertRaises(ValueError):self.control.attachment('lilith',name,b'test')

    def test_clipboard_preview_is_scoped_and_obeys_import_setting(self):
        result = self.control.attachment('lilith', 'clipboard-texto.txt', 'trecho copiado'.encode())
        name = result['name']
        self.assertFalse(result['message_sent'])
        from tools import entrega
        with patch.object(entrega.config, 'ENTREGA_ENTRADA', str(Path(result['path']).parent)):
            self.assertNotIn(name, entrega.novidades_na_entrada())
            self.assertEqual(entrega.ler_recebido(name), 'trecho copiado')
        self.assertEqual(self.control.clipboard_attachment('lilith', name),
                         (b'trecho copiado', 'text/plain; charset=utf-8'))
        with patch.object(cc.history, 'DB', self.control.paths('lilith').runtime / 'history.sqlite3'):
            cc.history.message('in', 'user', 'Leia o anexo ' + name + '.', channel='localhub')
        rows = self.control.timeline('lilith', {'q': 'TRECHO COPIADO'})['items']
        self.assertEqual(len(rows), 1)
        self.assertIn(name, rows[0]['content'])
        self.assertEqual(self.control.timeline('hoshino', {'q': 'TRECHO COPIADO'})['items'], [])
        for entity, invalid in [('hoshino', name), ('lilith', '../' + name)]:
            with self.assertRaises(ValueError):
                self.control.clipboard_attachment(entity, invalid)
        with self.assertRaises(ValueError):
            self.control.attachment('lilith', 'clipboard-print.png', b'not a PNG')
        before = self.control.ui_settings()
        self.control.save_ui(dict(revision=before['revision'], settings={'clipboard_import': False, 'timeline_page_size': 25}))
        self.assertEqual(self.control.timeline('lilith', {})['page_size'], 25)
        with self.assertRaises(ValueError):
            self.control.attachment('lilith', 'clipboard-texto.txt', b'blocked')
        self.assertEqual(self.control.clipboard_attachment('lilith', name)[0], b'trecho copiado')

    def test_http_auth_readonly_routes_and_voice_confirmation(self):
        self.install('hoshino');server,token=launcher.make_server(self.supervisor,0,self.audio)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(HTTPError):urlopen(base+'/api/control/models')
            with self.assertRaises(HTTPError):urlopen(base+'/api/control/timeline?entity=hoshino')
            copied = self.control.attachment('hoshino', 'clipboard-texto.txt', b'clipboard fixture')
            preview = base+'/api/control/clipboard-attachment?entity=hoshino&name='+copied['name']
            with self.assertRaises(HTTPError):urlopen(preview)
            headers = {'Authorization':'Bearer '+token}
            with urlopen(Request(preview, headers=headers)) as response:
                self.assertEqual(response.read(), b'clipboard fixture')
                self.assertEqual(response.headers.get_content_type(), 'text/plain')
            timeline = Request(base+'/api/control/timeline?entity=hoshino', headers=headers)
            with urlopen(timeline) as response:
                self.assertEqual(json.load(response)['entity'], 'hoshino')
            request=Request(base+'/api/control/models?entity=hoshino',headers={'Authorization':'Bearer '+token})
            self.assertEqual(json.load(urlopen(request))['entity'],'hoshino')
            request=Request(base+'/api/audio/test',data=b'{"entity":"hoshino"}',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with self.assertRaises(HTTPError):urlopen(request)
            self.assertIsNone(self.audio.thread)
            callback=Mock();server.request_shutdown=callback
            request=Request(base+'/api/control/shutdown',data=b'{"confirm":true}',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            result=json.load(urlopen(request));self.assertTrue(result['accepted']);self.assertFalse(result['verified']);callback.assert_called_once()
        finally:server.shutdown();server.server_close();thread.join(3)


if __name__=='__main__':unittest.main()
