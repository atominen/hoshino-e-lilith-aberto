"""Regressões offline: dados temporários, sem LLM, GPU ou microfone reais."""
import asyncio
import importlib.util
import json
import multiprocessing
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import config
from core import interentity as bus, resource_manager as resources

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("central_launcher", ROOT / "iniciar_entidades.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def hold_resource(db, locks, ready):
    resources.DB_PATH, resources.LOCK_DIR = Path(db), Path(locks)
    with resources.lease("gpu", "child", wait=1):
        ready.set()
        time.sleep(30)


def read_daily_after_restart(database, output):
    bus.DB_PATH=Path(database)
    with patch.object(bus,'_agora',return_value='2026-10-10T12:00:00Z'):
        view=bus.daily_conversation('lilith',day='2026-10-09')
        output.put((view['chat_session']['id'],[m['id'] for m in view['conversation']],view['chat_read_only']))


class CentralTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        label_patch=patch('core.chat_identity.display_name',return_value='Usuário')
        label_patch.start();self.addCleanup(label_patch.stop)
        for obj, name, value in [(bus, "DB_PATH", self.base / "messages.db"),
                                 (resources, "DB_PATH", self.base / "resources.db"),
                                 (launcher.job_bus, "DB_PATH", self.base / "jobs.db"),
                                 (resources, "LOCK_DIR", self.base / "locks")]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_offline_delivery_is_persistent_and_not_read_on_queue(self):
        sent = bus.send("hoshino", "lilith", "leia quando acordar")
        self.assertFalse(sent["wake_requested"])
        self.assertEqual(bus.pending_wake_requests(), [])
        self.assertIsNone(bus.inbox("lilith")[0]["read_at"])
        self.assertFalse(bus.mark_read(sent["id"], "hoshino"))
        self.assertEqual(len(bus.inbox("lilith")), 1)
        bus.mark_read(sent["id"], "lilith")
        self.assertEqual(bus.inbox("lilith"), [])
        self.assertEqual(bus.conversation("hoshino", "lilith")[0]["text"], "leia quando acordar")

    def test_absent_recipient_can_be_woken(self):
        sent = bus.send("hoshino", "lilith", "preciso de você", wake=True)
        self.assertTrue(sent["wake_requested"])
        self.assertEqual(bus.pending_wake_requests()[0]["message_id"], sent["id"])

    def test_validation(self):
        for sender, recipient in [("desconhecido", "lilith"), ("hoshino", "hoshino"), ("usuario", "../other")]:
            with self.assertRaises(ValueError):
                bus.send(sender, recipient, "oi")
        with self.assertRaises(ValueError):
            bus.send("hoshino", "lilith", "x" * 12001)
        self.assertFalse(bus.conversation("hoshino", "lilith"))

    def test_daily_midnight_reply_and_retry_keep_original_session(self):
        with patch.object(bus, '_agora', return_value='2026-10-10T02:59:59+00:00'):
            old = bus.daily_session('hoshino')
            first = bus.send('usuario', 'hoshino', 'continue a tarefa',
                             conversation_session_id=old['id'], dedupe_key='central:hoshino:abcdefgh')
            parent = bus.inbox('hoshino')[0]
        with patch.object(bus, '_agora', return_value='2026-10-10T03:00:01+00:00'):
            current = bus.daily_session('hoshino')
            self.assertNotEqual(old['id'], current['id'])
            retry = bus.send('usuario', 'hoshino', 'continue a tarefa',
                             conversation_session_id=old['id'], dedupe_key='central:hoshino:abcdefgh')
            self.assertEqual(first['id'], retry['id'])
            with self.assertRaises(ValueError):
                bus.send('usuario', 'hoshino', 'outra mensagem', conversation_session_id=old['id'])
            token = bus.processing_message.set(parent)
            try:
                reply = bus.send('hoshino', 'usuario', 'a tarefa continua')
            finally:
                bus.processing_message.reset(token)
            today = bus.daily_conversation('hoshino')
            archive = bus.daily_conversation('hoshino', session_id=old['id'])
            self.assertEqual(today['conversation'], [])
            self.assertTrue(archive['chat_read_only'])
            self.assertEqual([m['id'] for m in archive['conversation']], [first['id'], reply['id']])
            self.assertEqual(archive['conversation'][1]['metadata']['reply_to'], first['id'])
            self.assertEqual(bus.peek('hoshino')[0]['id'], first['id'])  # vista não confirma leitura
            self.assertEqual(bus.pending_wake_requests(), [])

    def test_daily_identity_restart_and_metadata_cannot_be_forged(self):
        with patch.object(bus, '_agora', return_value='2026-10-10T02:00:00Z'):
            ids = []
            for entity in bus.ENTITIES:
                session = bus.daily_session(entity)
                ids.append(session['id'])
                bus.send('usuario', entity, 'oi '+entity, metadata={'conversation_session': {'id':'forged'}})
                bus.send(entity, 'usuario', 'olá')
                self.assertEqual(len(bus.daily_conversation(entity)['conversation']), 2)
            self.assertEqual(len(set(ids)), 3)
            # Todas as operações fecham a conexão; reabrir não migra registros.
            with bus._transaction() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM entity_messages').fetchone()[0], 6)
            self.assertEqual(bus.daily_session('hoshino')['id'], ids[0])
            row = bus.daily_conversation('hoshino')['conversation'][0]
            self.assertEqual(row['metadata']['conversation_session']['id'], ids[0])
            with self.assertRaises(ValueError):
                bus.daily_conversation('lilith', session_id=ids[0])

    def test_daily_legacy_is_read_only_and_late_reply_follows_human_parent(self):
        with bus._transaction() as conn:
            conn.execute('INSERT INTO entity_messages(id,sender,recipient,text,metadata,created_at) VALUES(?,?,?,?,?,?)',
                         ('legacy-human', 'usuario', 'lilith', 'origem antiga', '{}', '2026-10-09T23:59:00'))
            conn.execute('INSERT INTO entity_messages(id,sender,recipient,text,metadata,created_at) VALUES(?,?,?,?,?,?)',
                         ('legacy-reply', 'lilith', 'usuario', 'resposta depois', '{"reply_to":"legacy-human"}', '2026-10-10T03:01:00Z'))
            before = [tuple(r) for r in conn.execute('SELECT * FROM entity_messages')]
        with patch.object(bus, '_agora', return_value='2026-10-10T12:00:00Z'):
            view = bus.daily_conversation('lilith', day='2026-10-09')
            self.assertEqual([m['id'] for m in view['conversation']], ['legacy-human','legacy-reply'])
            self.assertFalse(view['conversation'][0]['time']['timezone_known'])
            self.assertEqual(view['conversation'][1]['session_origin'], 'derived_legacy_parent')
            self.assertTrue(view['chat_read_only'])
        with bus._transaction() as conn:
            self.assertEqual(before, [tuple(r) for r in conn.execute('SELECT * FROM entity_messages')])

    def test_daily_pagination_snapshot_search_and_foreign_parent(self):
        with patch.object(bus, '_agora', return_value='2026-10-09T12:00:00Z'):
            sent = [bus.send('usuario', 'hoshino', 'Assunto colher '+str(i)) for i in range(7)]
            foreign = bus.send('usuario', 'lilith', 'conversa privada')
            token = bus.processing_message.set(bus.inbox('lilith')[0])
            try: bus.send('hoshino', 'usuario', 'não herdar conversa estrangeira')
            finally: bus.processing_message.reset(token)
            first = bus.daily_conversation('hoshino', limit=3, query='COLHER')
            bus.send('usuario', 'hoshino', 'colher nova')
            second = bus.daily_conversation('hoshino', limit=3, query='colher',
                                           before=first['page']['next_before'], upper=first['page']['upper'])
            third = bus.daily_conversation('hoshino', limit=3, query='colher',
                                          before=second['page']['next_before'], upper=first['page']['upper'])
            ids = [m['id'] for page in (third,second,first) for m in page['conversation']]
            self.assertEqual(ids, [m['id'] for m in sent])
            self.assertNotIn(foreign['id'], ids)
            self.assertFalse(third['page']['has_more'])
            self.assertEqual(first['day_summary']['message_count'], 8)
            self.assertFalse(first['day_summary']['semantic_summary_available'])
            for invalid in ('2026-02-30', 'not-a-date'):
                with self.assertRaises(ValueError):bus.daily_conversation('hoshino', day=invalid)
            for kwargs in ({'limit':0},{'before':-1},{'upper':-1},{'limit':501}):
                with self.assertRaises(ValueError):bus.daily_conversation('hoshino', **kwargs)

    def test_daily_timezone_and_non_main_channels_stay_separate(self):
        with patch.object(bus, '_agora', return_value='2026-10-10T02:30:00Z'), \
             patch.object(config, 'LOCAL_TIMEZONE', 'America/Sao_Paulo'):
            self.assertEqual(bus.daily_session('lilith')['local_date'], '2026-10-09')
            bus.send('hoshino', 'lilith', 'privada', metadata={'conversation_session':bus.daily_session('lilith')})
            self.assertEqual(bus.daily_conversation('lilith')['conversation'], [])
            private = bus.inbox('lilith')[0]
            self.assertNotIn('conversation_session', private['metadata'])
            bus.send('alistair', 'usuario', 'aviso sobre Lilith', metadata={'entity_context':'lilith'})
            item = bus.daily_conversation('lilith')['conversation'][0]
            self.assertEqual(item['sender'], 'alistair')
            self.assertEqual(item['conversation_session']['entity'], 'lilith')
        with patch.object(config, 'LOCAL_TIMEZONE', 'Etc/UTC'), \
             patch.object(bus, '_agora', return_value='2026-10-10T02:30:00Z'):
            self.assertEqual(bus.daily_session('lilith')['local_date'], '2026-10-10')

    def test_daily_restart_in_new_process_and_pending_inbox_preserved(self):
        with patch.object(bus,'_agora',return_value='2026-10-09T12:00:00Z'):
            sent=bus.send('usuario','lilith','leia depois de acordar')
            session=bus.daily_session('lilith')['id']
            bus.request_sleep('lilith')
        ctx=multiprocessing.get_context('fork');output=ctx.Queue()
        child=ctx.Process(target=read_daily_after_restart,args=(str(bus.DB_PATH),output));child.start()
        try:
            self.assertEqual(output.get(timeout=5),(session,[sent['id']],True))
            child.join(5);self.assertEqual(child.exitcode,0)
        finally:
            if child.is_alive():child.terminate();child.join(5)
            output.close();output.join_thread()
        self.assertEqual(bus.peek('lilith')[0]['id'],sent['id']);self.assertTrue(bus.sleep_requested('lilith'))

    def test_daily_stream_carries_input_session_without_exposing_private_reasoning(self):
        from core import speech_stream
        with patch.object(bus,'_agora',return_value='2026-10-10T02:59:59Z'):
            bus.send('usuario','hoshino','olá');parent=bus.inbox('hoshino')[0]
            expected=bus.daily_session('hoshino')['id']
        token=bus.processing_message.set(parent)
        try:
            with patch.object(bus,'_agora',return_value='2026-10-10T03:00:01Z'):
                stream=speech_stream.SpeechStream('hoshino','localhub');stream.push('Uma frase estável. Próxima')
                self.assertEqual(launcher.job_bus.get(stream.id,'hoshino')['status'],'running')
                stream.finish('Uma frase estável. Próxima frase.')
            job=launcher.job_bus.get(stream.id,'hoshino')
            self.assertEqual(job['details']['conversation_session_id'],expected)
            self.assertEqual(job['details']['sentences'],['Uma frase estável.','Próxima frase.'])
            self.assertEqual(job['status'],'done')
        finally:bus.processing_message.reset(token)

    def test_daily_view_load_is_bounded_and_measured_without_real_data(self):
        # 2.000 envelopes no mesmo SQLite temporário; não simula inferência.
        with patch.object(bus,'_agora',return_value='2026-10-09T12:00:00Z'):
            session=bus.daily_session('hoshino')
            metadata=json.dumps({'conversation_session':session})
            with bus._transaction() as conn:
                conn.executemany('INSERT INTO entity_messages(id,sender,recipient,text,metadata,created_at) VALUES(?,?,?,?,?,?)',
                                 ((f'load-{i}','usuario','hoshino',f'fixture {i}',metadata,'2026-10-09T12:00:00Z') for i in range(2000)))
            started=time.perf_counter();view=bus.daily_conversation('hoshino');elapsed=time.perf_counter()-started
            self.assertEqual(len(view['conversation']),100);self.assertEqual(view['day_summary']['message_count'],2000)
            self.assertTrue(view['page']['has_more']);self.assertEqual(view['conversation'][-1]['id'],'load-1999')
            print('DAILY_VIEW_METRICS',json.dumps({'temporary_sqlite':True,'envelopes':2000,'rendered':100,'query_seconds':round(elapsed,6)}))

    def test_reply_idempotency_and_loop_bound(self):
        bus.send("hoshino", "lilith", "oi")
        parent = bus.inbox("lilith")[0]
        token = bus.processing_message.set(parent)
        try:
            first = bus.send("lilith", "hoshino", "resposta")
            again = bus.send("lilith", "hoshino", "tentativa após interrupção")
            self.assertEqual(first["id"], again["id"])
            parent["metadata"]["hops"] = bus.MAX_AUTO_HOPS
            with self.assertRaises(ValueError):
                bus.send("lilith", "hoshino", "não deve realimentar")
        finally:
            bus.processing_message.reset(token)
        self.assertEqual(len(bus.conversation("hoshino", "lilith")), 2)

    def test_concurrent_writes(self):
        errors = []
        def send(i):
            try:
                bus.send("hoshino", "lilith", str(i))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=send, args=(i,)) for i in range(15)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(bus.inbox("lilith")), 15)

    def test_long_job_does_not_disappear_after_expiration(self):
        with resources.lease("gpu", "imagem") as token:
            conn = resources._conn()
            conn.execute("UPDATE leases SET expires_at=0 WHERE token=?", (token,))
            conn.commit()
            conn.close()
            self.assertEqual(len(resources.status("gpu")), 1)
            with self.assertRaises(TimeoutError):
                with resources.lease("gpu", "llm", wait=0):
                    pass
        self.assertEqual(resources.status(), [])

    def test_crashed_process_releases_lock(self):
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        child = ctx.Process(target=hold_resource, args=(str(resources.DB_PATH), str(resources.LOCK_DIR), ready))
        child.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaises(TimeoutError):
                with resources.lease("gpu", "parent", wait=0):
                    pass
        finally:
            child.terminate()
            child.join(5)
        self.assertEqual(resources.status(), [])
        with resources.lease("gpu", "recovered", wait=0):
            self.assertEqual(resources.status()[0]["owner"], "recovered")

    def test_supervisor_does_not_ack_wake_before_ready(self):
        supervisor = launcher.Supervisor()
        request = bus.wake("hoshino", "lilith")
        with patch.object(supervisor, "start") as start:
            supervisor.tick()
            start.assert_called_once_with('lilith', requester='hoshino', reason='despertar solicitado',
                                          source='pedido', reference=request['id'])
        self.assertEqual(bus.pending_wake_requests()[0]["id"], request["id"])
        bus.register("lilith", "awake", os.getpid())
        supervisor.tick()
        self.assertEqual(bus.pending_wake_requests(), [])

    def _boot_without_real_services(self, arguments):
        supervisor = Mock()
        supervisor.shutdown.return_value = {"status": "complete"}
        server = Mock(server_port=8769)
        stopped = Mock()
        stopped.wait.return_value = True
        with patch.object(launcher, "ROOT", self.base), \
             patch.object(launcher.sys, "argv", ["iniciar_entidades.py", "--no-browser", *arguments]), \
             patch.object(launcher, "Supervisor", return_value=supervisor), \
             patch.object(launcher, "make_server", return_value=(server, "fixture-only")), \
             patch.object(launcher.world_state, "Monitor"), \
             patch.object(launcher.threading, "Thread"), \
             patch.object(launcher.threading, "Event", return_value=stopped), \
             patch.object(launcher.signal, "signal"):
            self.assertEqual(launcher.main(), 0)
        server.shutdown.assert_called_once_with()
        return supervisor.start.call_args_list

    def test_central_boot_does_not_wake_any_entity_implicitly(self):
        self.assertEqual(self._boot_without_real_services([]), [])

    def test_central_boot_preserves_explicit_entity_selection(self):
        for entity in launcher.ENTIDADES:
            with self.subTest(entity=entity):
                calls = self._boot_without_real_services(["--entity", entity])
                self.assertEqual([call.args[0] for call in calls], [entity])
        for group in ("ambas", "todas"):
            with self.subTest(group=group):
                calls = self._boot_without_real_services(["--entity", group])
                self.assertEqual([call.args[0] for call in calls], list(launcher.ENTIDADES))

    def test_sleep_is_request_not_false_process_termination(self):
        bus.register("hoshino", "awake", os.getpid())
        bus.request_sleep("hoshino")
        self.assertTrue(bus.sleep_requested("hoshino"))
        self.assertEqual(bus.presence("hoshino")["status"], "awake")

    def test_new_wake_during_shutdown_is_not_lost_behind_old_requests(self):
        for _ in range(25):
            bus.wake("usuario", "hoshino")
        bus.register("hoshino", "awake", os.getpid())
        bus.request_sleep("hoshino")
        message = bus.send("usuario", "hoshino", "acorde depois de encerrar", wake=True)
        self.assertTrue(message["wake_requested"])
        launcher.Supervisor().tick()
        pending = bus.pending_wake_requests()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["message_id"], message["id"])

    def test_gpu_residency_preserves_current_model_and_unloads_peer(self):
        gpu_spec = importlib.util.spec_from_file_location("gpu_under_test", ROOT / "app/core/gpu_resource.py")
        gpu = importlib.util.module_from_spec(gpu_spec)
        gpu_spec.loader.exec_module(gpu)
        current = config.OLLAMA_URL.rsplit("/api/", 1)[0]
        peer = "http://127.0.0.1:11436" if current.endswith("11435") else "http://127.0.0.1:11435"
        models = {current: [config.MODEL_NAME], peer: ["peer-model"]}
        stopped = []
        def response(body):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
        def get(url, **kwargs):
            self.assertNotIn("11434", url)
            return response({"models": [{"name": m} for m in models.get(url.removesuffix("/api/ps"), [])]})
        def post(url, json, **kwargs):
            self.assertEqual(json["keep_alive"], 0)
            models[url.removesuffix("/api/generate")].remove(json["model"])
            stopped.append(json["model"])
            return response({"done": True})
        fake = SimpleNamespace(get=get, post=post, ConnectionError=ConnectionError)
        from core import gpu_metrics
        def metrics():
            return dict(known=True,stable=True,source='mock',observed_at=time.time(),total_bytes=8*1024**3,
                        used_bytes=int(sum((1 if m==config.MODEL_NAME else 6.5)*1024**3 for ms in models.values() for m in ms)),utilization=0)
        original_get = get
        def sized_get(url,**kwargs):
            r = original_get(url,**kwargs)
            # Par com 6,5 GiB: pressão real mesmo sem recontar o workspace do modelo já residente (27/10).
            return response({'models':[dict(m,size_vram=int((1 if m['name']==config.MODEL_NAME else 6.5)*1024**3)) for m in r.json()['models']]})
        fake.get = sized_get
        policy = resources.gpu_policy()
        # 30/10: margem fixa no teste; o gpu.json da máquina pode estar em 512 MiB (pedido humano, 33 camadas).
        policy.update(sticky_seconds=0,interactive_grace_seconds=0,margin_bytes=768*1024**2)
        with patch.object(gpu,"requests",fake), patch.object(gpu_metrics,'snapshot',side_effect=metrics), patch.object(resources,'gpu_policy',return_value=policy):
            with gpu.lease("llm"):
                self.assertEqual(models[current], [config.MODEL_NAME])
                self.assertEqual(models[peer], [])
            with gpu.lease("image") as acquired:
                self.assertEqual(models[current], [config.MODEL_NAME])
                self.assertLess(acquired['vram_budget_bytes'],7*1024**3)
                self.assertLessEqual(metrics()['used_bytes']+acquired['vram_budget_bytes']+policy['margin_bytes'],8*1024**3)
        self.assertEqual(stopped, ["peer-model"])
        self.assertEqual(resources.status(), [])

    def test_gpu_unload_failure_releases_lock_and_fails_closed(self):
        gpu_spec = importlib.util.spec_from_file_location("gpu_failure_test", ROOT / "app/core/gpu_resource.py")
        gpu = importlib.util.module_from_spec(gpu_spec)
        gpu_spec.loader.exec_module(gpu)
        with patch.object(gpu, "prepare_residency", side_effect=RuntimeError("unload não confirmado")):
            with self.assertRaises(RuntimeError):
                with gpu.lease("image"):
                    self.fail("não deve iniciar a geração")
        self.assertEqual(resources.status(), [])

    def test_directional_relations_do_not_merge_with_human_names(self):
        from memory.sqlite import init_db
        from social import people
        init_db.init_database(verbose=False)
        human = people.identificar(nome="Lilith", canal="discord", canal_id="human-1")
        entity = people.identificar(nome="Lilith", canal="interentidades", canal_id="lilith")
        self.assertNotEqual(human["id"], entity["id"])
        self.assertTrue(people.pode_usar_ferramenta("entidades_enviar_mensagem", canal="interentidades")[0])
        self.assertFalse(people.pode_usar_ferramenta("execute_command", canal="interentidades")[0])
        self.assertTrue(people.pode_usar_ferramenta("workspace", canal="localhub")[0])

    def test_http_auth_and_persistent_send(self):
        server, token = launcher.make_server(launcher.Supervisor(), 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/api/state")
            self.assertEqual(error.exception.code, 403)
            data = json.dumps({"entity": "lilith", "text": "teste HTTP"}).encode()
            headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
            with urlopen(Request(base + "/api/send", data=data, headers=headers)) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(bus.inbox("lilith")[0]["sender"], "usuario")
            headers["Origin"] = "https://exemplo.invalid"
            with self.assertRaises(HTTPError):
                urlopen(Request(base + "/api/send", data=data, headers=headers))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def test_daily_http_archive_rejection_retry_and_legacy_api(self):
        audio = Mock()
        supervisor = launcher.Supervisor()
        server, token = launcher.make_server(supervisor, 0, audio)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        headers = {'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        def request(path, data=None):
            with urlopen(Request(base+'/api/'+path,headers=headers,
                                 data=json.dumps(data).encode() if data is not None else None)) as response:
                return json.load(response)
        try:
            with patch.object(bus,'_agora',return_value='2026-10-10T02:59:00Z'), \
                 patch.object(resources,'gpu_state',return_value={}), \
                 patch.object(launcher.world_state,'snapshot',return_value={}), \
                 patch.object(launcher.capability_router.Router,'status',return_value={}):
                current = request('state?entity=lilith&daily=1')
                old = current['chat_session']['id']
                data = dict(entity='lilith',text='apresentação',submission_id='abcdefgh123',conversation_session_id=old)
                first = request('send',data)
                self.assertNotIn('chat_session',request('state?entity=lilith'))
                with patch.object(bus,'_agora',return_value='2026-10-10T03:01:00Z'):
                    retry = request('send',data)
                    self.assertEqual(first['id'],retry['id'])
                    with self.assertRaises(HTTPError) as error:
                        request('send',dict(data,submission_id='another123',text='nova'))
                    self.assertEqual(error.exception.code,400)
                    view = request('state?entity=lilith&daily=1&day=2026-10-09&q=apresenta')
                    self.assertTrue(view['chat_read_only']);self.assertEqual(view['conversation'][0]['id'],first['id'])
                    self.assertEqual(view['conversation'][0]['metadata']['submission_id'],'abcdefgh123')
                    self.assertEqual(len(request('state?entity=lilith')['conversation']),1)
                    with self.assertRaises(HTTPError):request('state?entity=lilith&daily=1&before=-1')
                audio.interrupt_entity.assert_not_called()
                self.assertEqual(len(bus.peek('lilith')),1)
        finally:
            server.shutdown();server.server_close();thread.join(5)

    def test_image_preview_is_authorized_and_scoped_to_entity(self):
        from PIL import Image
        directory = self.base / "entidades/hoshino/runtime/imagens"
        directory.mkdir(parents=True)
        image = directory / "test.png"
        Image.new("RGB", (8, 8), "white").save(image)
        launcher.job_bus.publish("preview", "hoshino", "done", path=str(image))
        launcher.job_bus.publish("outside", "hoshino", "done", path=str(self.base / "private.png"))
        server, token = launcher.make_server(launcher.Supervisor(), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.object(launcher, "ROOT", self.base):
                with self.assertRaises(HTTPError) as denied:
                    urlopen(base + "/api/image?id=preview")
                self.assertEqual(denied.exception.code, 403)
                headers = {"Authorization": "Bearer " + token}
                with urlopen(Request(base + "/api/image?id=preview", headers=headers)) as r:
                    self.assertEqual(r.headers["Content-Type"], "image/png")
                    self.assertEqual(r.read(), image.read_bytes())
                with self.assertRaises(HTTPError) as outside:
                    urlopen(Request(base + "/api/image?id=outside", headers=headers))
                self.assertEqual(outside.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def test_world_and_routing_are_authenticated_read_only_and_lazy(self):
        from core import world_state
        path = self.base / "shared-world.db"
        with patch.object(world_state, "default_path", return_value=path), patch.object(world_state.Monitor, "collect", side_effect=AssertionError("consulta não coleta")):
            server, token = launcher.make_server(launcher.Supervisor(), 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            headers = {"Authorization": "Bearer " + token}
            try:
                for endpoint in ("world", "routing"):
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(base + "/api/" + endpoint)
                    self.assertEqual(denied.exception.code, 403)
                with urlopen(Request(base + "/api/world?since=0", headers=headers)) as response:
                    self.assertFalse(json.load(response)["available"])
                self.assertFalse(path.exists())
                with urlopen(Request(base + "/api/routing?entity=lilith&capability=tts", headers=headers)) as response:
                    plan = json.load(response)
                    self.assertEqual(plan["executor"], "pc_principal")
                    self.assertFalse(plan["execution_migrated"])
                with urlopen(Request(base + "/api/state?entity=hoshino", headers=headers)) as response:
                    state = json.load(response)
                    self.assertFalse(state["world"]["available"])
                    self.assertFalse(state["routing"]["cloud_enabled"])
                # Não há rota HTTP para injetar fatos nem ativar/alugar cloud.
                with self.assertRaises(HTTPError) as denied:
                    urlopen(Request(base + "/api/world", data=b'{"entity":"hoshino","value":"inventado"}', headers=headers))
                self.assertEqual(denied.exception.code, 404)
                self.assertFalse(path.exists())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)

    def test_headless_reply_routes_to_private_channel(self):
        from memory.sqlite import init_db
        init_db.init_database(verbose=False)
        import main
        config.MIC_ATIVO = False
        config.HEARTBEAT_SEGUNDOS = 3600
        config.DEBOUNCE_CONVERSA_MS = 1
        bus.send("lilith", "hoshino", "mensagem de teste")
        status = SimpleNamespace(ok=True, recuperado=False, model="mock", detalhe="teste")
        async def exercise():
            with patch.object(main.ollama_lifecycle, "inicializar", return_value=status), \
                 patch.object(main.ollama_lifecycle, "encerrar", return_value=True), \
                 patch.object(main.scribe, "pos_turno", return_value={"fatos": []}), \
                 patch.object(main, "salvar_episodio"):
                app = main.InterfaceHoshino()
                app.extrair_memoria = AsyncMock()
                app.atualizar_pessoa = Mock()
                app.contexto_do_turno = Mock(return_value="contexto de teste")
                async def respond(*args, **kwargs):
                    # O worker já reivindicou a mensagem; inbox só oferece itens
                    # disponíveis. peek continua mostrando leitura/estado reais.
                    entrada = bus.peek("hoshino")[0]
                    self.assertIsNone(entrada["read_at"])
                    self.assertEqual(entrada['metadata']['processing']['status'], 'processing')
                    app.publicar("resposta real do roteamento, modelo simulado", [], False, {},
                                 canal=kwargs["canal_lote"], responder_para=kwargs["responder_para"],
                                 chave_conversa=kwargs["chave_conversa"])
                    return {'status':'answered'}
                app.responder = respond
                async with app.run_test() as pilot:
                    self.assertIsNone(app.ultima_interacao)
                    await app.ler_interentidades()
                    self.assertIsNone(app.ultima_interacao)  # Mensagem de Lilith não é presença humana.
                    await asyncio.gather(*list(app._workers_por_chave.values()))
                    self.assertEqual(bus.inbox("hoshino"), [])
                    self.assertEqual(bus.inbox("lilith")[0]["sender"], "hoshino")
                    self.assertFalse(bus.pending_wake_requests())
                    bus.request_sleep("hoshino")
                    await app.ciclo_canal_local()
                self.assertEqual(bus.presence("hoshino")["status"], "sleeping")
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
