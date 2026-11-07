"""Alistair/standby/imagem: somente arquivos temporários e respostas simuladas."""
import asyncio
import json
import multiprocessing
import os
if os.environ.get('HOSHINO_TEST_OFFLINE')!='1':
    raise SystemExit('Use testes/executar_isolado.py; este grupo exige isolamento de bancos/serviços.')
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import config
from alistair_runner import Alistair, conversation_system
from core import interentity as bus, job_bus, resource_manager
from tools import image_gen


ROOT = Path(__file__).resolve().parents[1]


def image_child_parent(queue):
    child = subprocess.Popen([sys.executable, "-I", str(ROOT / "scripts/image_child.py"),
                              str(os.getpid()), sys.executable, "-c", "import time; time.sleep(30)"])
    queue.put(child.pid)
    child.wait()


def response(message=None, models=None):
    return SimpleNamespace(raise_for_status=lambda: None,
                           json=lambda: {"message": message or {}, "models": models or []})


class StandbyTests(unittest.TestCase):
    def test_configured_identity_precedes_mechanical_state_without_rewriting_it(self):
        identity={'identity':{'name':'Alistair','self_concept':'Cuido da organização.'},
                  'personality':{'traits':['formal com naturalidade','ironia leve quando cabe']}}
        before=json.dumps(identity)
        system=conversation_system(identity,{'id':'fixture','sender':'usuario'}, {'status':'standby'},[],{})
        self.assertTrue(system.startswith('Eu sou Alistair. Cuido da organização.'))
        self.assertLess(system.index('formal com naturalidade'),system.index('ESTADO MECÂNICO'))
        self.assertIn('não trato meu nome como o nome de quem me chamou',system)
        self.assertNotIn('como um amigo',system);self.assertEqual(json.dumps(identity),before)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        identity = self.base / "self.json"
        identity.write_text(json.dumps({"nome": "Alistair"}))
        for obj, name, value in [
            (config, "RAIZ", self.base),
            (config, "DB_PATH", self.base / "mind.db"),
            (config, "SELF_MODEL_PATH", identity),
            (config, "IMAGE_OUTPUT_DIR", str(self.base / "images")),
            (bus, "DB_PATH", self.base / "bus.db"),
            (job_bus, "DB_PATH", self.base / "jobs.db"),
            (resource_manager, "DB_PATH", self.base / "resources.db"),
            (resource_manager, "LOCK_DIR", self.base / "locks"),
        ]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in [('alistair_runner.alistair_backend.configured', None),
                              ('core.activity_context.build', ({}, ''))]:
            p=patch(target,return_value=value);p.start();self.addCleanup(p.stop)
        self.alistair = Alistair()

    def test_observer_does_not_deliver_other_entity_mail(self):
        sent = bus.send("usuario", "hoshino", "oi")
        self.assertIsNone(bus.peek("hoshino")[0]["delivered_at"])
        job_bus.publish("image", "hoshino", "running")
        self.alistair.standby()
        queued = bus.peek("hoshino")[0]
        self.assertEqual(queued["id"], sent["id"])
        self.assertIsNone(queued["read_at"])
        self.assertIsNone(queued["delivered_at"])

    def test_standby_coalesces_and_keeps_own_authorship(self):
        job_bus.publish("image", "lilith", "queued")
        self.alistair.standby()
        job_bus.publish("image", "lilith", "running")
        bus.send("usuario", "lilith", "um")
        bus.send("usuario", "lilith", "dois")
        self.alistair.standby()
        self.alistair.standby()
        self.assertEqual(len(bus.peek("usuario")), 2)  # Um início e um aviso de mensagem guardada.
        job_bus.publish("image", "lilith", "done", path="resultado.png")
        self.alistair.standby()
        self.alistair.standby()
        messages = bus.user_conversation("lilith")
        notices = [m for m in messages if m["kind"] == "notification"]
        self.assertEqual(len(notices), 3)
        self.assertTrue(all(m["sender"] == "alistair" for m in notices))
        self.assertIsNone(bus.peek("lilith")[0]["read_at"])

    def test_old_terminal_jobs_do_not_cause_startup_spam(self):
        job_bus.publish("old", "hoshino", "done")
        with closing(job_bus._conn()) as db, db:
            db.execute("UPDATE jobs SET updated_at=?", (time.time() - 86400,))
        self.alistair.standby()
        self.assertEqual(bus.peek("usuario"), [])

    def test_empty_model_answer_is_not_persisted_as_success(self):
        message = {"id": "source", "sender": "usuario", "text": "oi"}
        with patch("alistair_runner.requests.post", return_value=response()):
            with self.assertRaises(RuntimeError):
                self.alistair.chat(message)
        with closing(sqlite3.connect(config.DB_PATH)) as db, db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM alistair_turns").fetchone()[0], 0)

    def test_failed_turn_remains_unread(self):
        sent = bus.send("usuario", "alistair", "oi")
        def fail(message):
            bus.request_sleep("alistair")
            raise RuntimeError("sem resposta")
        with patch.object(self.alistair, "load"), patch.object(self.alistair, "unload"), \
             patch.object(self.alistair, "chat", side_effect=fail):
            asyncio.run(self.alistair.run())
        self.assertEqual(bus.peek("alistair")[0]["id"], sent["id"])
        self.assertIsNone(bus.peek("alistair")[0]["read_at"])

    def test_chat_always_cpu_and_replay_has_no_second_inference(self):
        message = {"id": "source", "sender": "usuario", "text": "oi"}
        with patch("alistair_runner.requests.post", return_value=response({"role": "assistant", "content": "Olá."})) as post:
            self.assertEqual(self.alistair.chat(message), "Olá.")
            self.assertEqual(self.alistair.chat(message), "Olá.")
            self.assertEqual(post.call_count, 1)
            self.assertEqual(post.call_args.kwargs["json"]["options"]["num_gpu"], 0)

    def test_unload_requires_observed_absence(self):
        with patch("alistair_runner.requests.post", return_value=response()), \
             patch("alistair_runner.requests.get", return_value=response(models=[{"name": config.MODEL_NAME}])):
            with self.assertRaises(RuntimeError):
                self.alistair.unload()
        self.assertEqual(resource_manager.status(), [])

    def test_load_requires_observed_cpu_residency(self):
        with patch("alistair_runner.requests.post", return_value=response()), \
             patch("alistair_runner.requests.get", return_value=response(models=[{"name": config.MODEL_NAME, "size_vram": 0}])):
            self.alistair.load()
        with patch("alistair_runner.requests.post", return_value=response()), \
             patch("alistair_runner.requests.get", return_value=response(models=[{"name": config.MODEL_NAME, "size_vram": 100}])):
            with self.assertRaises(RuntimeError):
                self.alistair.load()
        self.assertEqual(resource_manager.status(), [])

    def test_job_terminal_state_and_entity_are_protected(self):
        job_bus.publish("image", "hoshino", "queued", steps=16)
        job_bus.publish("image", "hoshino", "running", step=2)
        with self.assertRaises(ValueError):
            job_bus.publish("image", "lilith", "running")
        with self.assertRaises(ValueError):
            job_bus.publish("image", "hoshino", "queued")
        job_bus.publish("image", "hoshino", "done", path="result.png")
        with self.assertRaises(ValueError):
            job_bus.publish("image", "hoshino", "running")
        self.assertEqual(job_bus.get("image")["details"]["steps"], 16)
        self.assertIsNone(job_bus.get("image", "lilith"))

    def test_durable_action_receipt_replays_without_second_effect(self):
        args = {"entidade": "lilith", "texto": "hello"}
        with patch.object(self.alistair, "call_tool", return_value={"id": "effect"}) as call:
            first = self.alistair._once("test-action", "entidades_enviar_mensagem", args)
            again = Alistair()._once("test-action", "entidades_enviar_mensagem", args)
            self.assertEqual(first, again)
            self.assertEqual(call.call_count, 1)
        with self.assertRaises(ValueError): self.alistair._once("test-action", "entidades_enviar_mensagem", {**args, "texto": "changed"})

    def test_uncertain_action_after_exception_never_repeats(self):
        with patch.object(self.alistair, "call_tool", side_effect=RuntimeError("effect uncertain")) as call:
            with self.assertRaises(RuntimeError): self.alistair._once("test-action", "entidades_acordar", {"entidade": "lilith"})
            with self.assertRaises(RuntimeError): self.alistair._once("test-action", "entidades_acordar", {"entidade": "lilith"})
            self.assertEqual(call.call_count, 1)

    def test_tool_contract_rejects_string_boolean_and_unknown_fields(self):
        incoming = {"id": "source", "sender": "usuario", "text": "say hi"}
        tool = {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "entidades_enviar_mensagem", "arguments": {"entidade": "lilith", "texto": "hi", "acordar": "true"}}}]}
        with patch.object(self.alistair, "infer", side_effect=[{"message": tool}, {"message": {"role": "assistant", "content": "Não executado."}}]), \
             patch.object(self.alistair, "call_tool") as call:
            self.alistair.chat(incoming)
            call.assert_not_called()

    def test_remote_pending_does_not_generate_local_answer_or_commit_turn(self):
        from core.alistair_backend import RemotePending
        incoming = {"id": "source", "sender": "usuario", "text": "hi"}
        self.alistair.remote = SimpleNamespace(infer=lambda *_: (_ for _ in ()).throw(RemotePending("unknown")))
        with patch("alistair_runner.requests.post") as post:
            with self.assertRaises(RemotePending): self.alistair.chat(incoming)
            post.assert_not_called()
        with closing(sqlite3.connect(self.alistair.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM alistair_turns").fetchone()[0], 0)

    def test_reused_pid_is_not_an_active_job(self):
        job_bus.publish("image", "hoshino", "running")
        with closing(job_bus._conn()) as db, db:
            db.execute("UPDATE jobs SET process_stamp='previous-execution'")
        self.assertEqual(job_bus.get("image")["status"], "interrupted")
        self.assertEqual(job_bus.status(active_only=True), [])

    def test_custom_does_not_silently_reduce_dimensions_or_steps(self):
        args = ("image", "", 1600, 2048, 75, 1, -1, "test", "personalizada")
        p = image_gen._normalizar_parametros(*args)
        self.assertEqual((p["largura"], p["altura"], p["passos"]), (1600, 2048, 75))
        for width in (0, 513, 4096, 768.5, True):
            with self.assertRaises(ValueError):
                image_gen._normalizar_parametros("image", "", width, 768, 16, 1, -1, "")
        with self.assertRaises(ValueError):
            image_gen._normalizar_parametros("image", "", None, 768, 16, 1, -1, "", "personalizada")
        with self.assertRaises(ValueError):
            image_gen._normalizar_parametros("image", "", 1024, None, None, 1, -1, "", "alto")

    def test_presets_are_explicit(self):
        p = image_gen._normalizar_parametros("image", "", None, None, None, None, -1, "", "médio")
        self.assertEqual((p["largura"], p["altura"], p["passos"]), (768, 768, 16))

    def test_progress_is_sampling_not_tensor_load_or_vae(self):
        job_bus.publish("image", config.ENTIDADE_ID, "running", phase="loading")
        p = {"passos": 16}
        image_gen._observar_log("\r |####| 16/16 - 2.00GB/s", p, "image", time.monotonic())
        self.assertEqual(job_bus.get("image")["details"]["step"], 0)
        image_gen._observar_log("\r |====>   | 2/16 - 12.50s/it", p, "image", time.monotonic())
        self.assertEqual(job_bus.get("image")["details"]["step"], 2)
        self.assertEqual(job_bus.get("image")["details"]["eta_seconds"], 175)
        image_gen._observar_log("sampling completed\n |====>   | 4/16 - 0.5s/it", p, "image", time.monotonic())
        self.assertEqual(job_bus.get("image")["details"]["step"], 2)
        self.assertIsNone(job_bus.get("image")["details"]["eta_seconds"])

    def test_image_status_survives_memory_catalog_loss(self):
        job_bus.publish("saved-image", config.ENTIDADE_ID, "done", path="image.png", steps=16)
        with patch.object(image_gen, "_JOBS", {}):
            self.assertIn("status=done", image_gen.disponibilidade("saved-image"))
            self.assertIn("path=image.png", image_gen.disponibilidade("saved-image"))

    def test_child_guard_executes_and_rejects_wrong_parent(self):
        args = [sys.executable, "-I", str(ROOT / "scripts/image_child.py")]
        good = subprocess.run([*args, str(os.getpid()), sys.executable, "-c", "print('guard-ok')"],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("guard-ok", good.stdout)
        wrong = subprocess.run([*args, "0", sys.executable, "-c", "print('must-not-run')"],
                               capture_output=True, text=True, timeout=5)
        self.assertEqual(wrong.returncode, 1)
        self.assertNotIn("must-not-run", wrong.stdout)

    def test_child_does_not_keep_running_after_worker_dies(self):
        ctx = multiprocessing.get_context("fork")
        queue = ctx.Queue()
        parent = ctx.Process(target=image_child_parent, args=(queue,))
        parent.start()
        child_pid = queue.get(timeout=5)
        try:
            # Espera pelo exec do helper, não apenas pela criação do processo.
            for _ in range(50):
                cmd = Path(f"/proc/{child_pid}/cmdline").read_bytes()
                if b"time.sleep" in cmd and b"image_child.py" not in cmd:
                    break
                time.sleep(0.02)
            else:
                self.fail("helper não executou o processo filho")
            parent.terminate()
            parent.join(5)
            for _ in range(50):
                if job_bus._process_stamp(child_pid) is None:
                    break
                time.sleep(0.02)
            self.assertIsNone(job_bus._process_stamp(child_pid), "filho permaneceu executando sem worker")
        finally:
            if parent.is_alive():
                parent.terminate()
                parent.join(5)
            if job_bus._process_stamp(child_pid) is not None:
                os.kill(child_pid, 15)  # Apenas o filho criado por este teste.
            queue.close()


if __name__ == "__main__":
    unittest.main()
