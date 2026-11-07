"""Executor e transporte LAN em loopback, motor simulado, nenhuma mente real."""
import copy
import json
import threading
import time
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import pc2_protocol as protocol
from pc2_node import Node, make_server
from core.alistair_backend import Client, RemotePending, RemoteUnavailable

SECRET = bytes(range(32))
PAYLOAD = {"model": protocol.MODEL, "messages": [{"role": "user", "content": "hi"}],
           "options": {"num_ctx": 1024, "num_predict": 32, "num_gpu": 0}}


class FakeEngine:
    def __init__(self):
        self.calls, self.running, self.max_running = 0, 0, 0
        self.block, self.started = threading.Event(), threading.Event()
        self.block.set()
        self.fail = False
    def info(self): return {"alive": True, "model_available": True, "warm": True}
    def infer(self, payload, cancel):
        self.calls += 1
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        self.started.set()
        try:
            if not self.block.wait(2): raise RuntimeError("test timed out")
            if self.fail: raise RuntimeError("simulated error")
            return {"message": {"role": "assistant", "content": "OK"}, "eval_count": 1}
        finally: self.running -= 1
    def close(self): self.block.set()


def wait(node, identifier):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = node.get(identifier)
        if value["status"] not in {"queued", "running"}: return value
        time.sleep(.005)
    raise AssertionError("job did not finish")


class ProtocolTests(unittest.TestCase):
    def test_private_lan_only(self):
        self.assertEqual(protocol.lan_ip("192.168.1.2"), "192.168.1.2")
        for address in ["0.0.0.0", "8.8.8.8", "::1", "example.com", "192.168.1.255"]:
            with self.subTest(address=address), self.assertRaises(ValueError): protocol.lan_ip(address)

    def test_auth_tamper_expiry(self):
        body = b"body"
        headers = protocol.auth_headers(SECRET, "POST", "/api/infer", body, now=100)
        protocol.verify(SECRET, "POST", "/api/infer", headers, body, now=101)
        for method, target, data, now in [("GET", "/api/infer", body, 101), ("POST", "/other", body, 101),
                                          ("POST", "/api/infer", b"changed", 101), ("POST", "/api/infer", body, 161)]:
            with self.assertRaises(ValueError): protocol.verify(SECRET, method, target, headers, data, now=now)

    def test_no_silent_token_context_reduction_gpu_or_images(self):
        for change in [{"num_ctx": 8192}, {"num_predict": 1000}, {"num_gpu": 1}, {"num_gpu": False}, {"temperature": float("nan")}, {"num_ctx": True}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                protocol.payload({**PAYLOAD, "options": {**PAYLOAD["options"], **change}})
        with self.assertRaises(ValueError): protocol.payload({**PAYLOAD, "messages": [{"role": "user", "content": "hi", "images": ["abc"]}]})
        self.assertEqual(protocol.payload(PAYLOAD)["options"]["num_thread"], 2)
        self.assertEqual(protocol.payload(PAYLOAD)["messages"], PAYLOAD["messages"])

    def test_client_rejects_public_proxy_credentials_and_urls(self):
        for url in ["https://192.168.1.2:8770", "http://8.8.8.8:8770", "http://a:b@192.168.1.2:8770", "http://192.168.1.2:8770/path", "http://192.168.1.2", "http://localhost:8770"]:
            with self.subTest(url=url), self.assertRaises(ValueError): Client(url, SECRET)


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.node = Node(self.engine, SECRET, mem_probe=lambda: {"available_bytes": 8 * 1024 ** 3})
        self.addCleanup(self.node.close)

    def test_idempotency_conflict_and_memory_only_prompts(self):
        request = {"id": "one", "payload": PAYLOAD}
        self.node.submit(request)
        result = wait(self.node, "one")
        self.assertEqual(self.node.submit(request), result)
        self.assertEqual(self.engine.calls, 1)
        self.assertIsNone(self.node.jobs["one"]["payload"])
        with self.assertRaises(ValueError): self.node.submit({"id": "one", "payload": {**PAYLOAD, "messages": [{"role": "user", "content": "different"}]}})

    def test_serial_bounded_queue_and_cancel_pending(self):
        self.engine.block.clear()
        self.node.submit({"id": "one", "payload": PAYLOAD})
        self.assertTrue(self.engine.started.wait(1))
        self.node.submit({"id": "two", "payload": PAYLOAD})
        self.node.submit({"id": "three", "payload": PAYLOAD})
        with self.assertRaises(RuntimeError): self.node.submit({"id": "four", "payload": PAYLOAD})
        self.assertEqual(self.node.cancel("two")["status"], "interrupted")
        self.engine.block.set()
        wait(self.node, "one"); wait(self.node, "three")
        self.assertEqual(self.engine.calls, 2)
        self.assertEqual(self.engine.max_running, 1)
        self.node.pending.join()

    def test_cancel_active_does_not_publish_result(self):
        self.engine.block.clear()
        self.node.submit({"id": "one", "payload": PAYLOAD})
        self.assertTrue(self.engine.started.wait(1))
        self.node.cancel("one")
        result = wait(self.node, "one")
        self.assertEqual(result["status"], "interrupted")
        self.assertIsNone(result["result"])

    def test_unknown_or_low_ram_not_zero_or_success(self):
        for available in [None, 0]:
            self.node.mem_probe = lambda: {"available_bytes": available}
            identifier = str(available)
            self.node.submit({"id": identifier, "payload": PAYLOAD})
            self.assertEqual(wait(self.node, identifier)["status"], "error")
        self.assertEqual(self.engine.calls, 0)

    def test_error_recovers_for_next_job(self):
        self.engine.fail = True
        self.node.submit({"id": "one", "payload": PAYLOAD})
        self.assertEqual(wait(self.node, "one")["status"], "error")
        self.engine.fail = False
        self.node.submit({"id": "two", "payload": PAYLOAD})
        self.assertEqual(wait(self.node, "two")["status"], "done")

    def test_replay_origin_and_other_ip_rejected(self):
        headers = protocol.auth_headers(SECRET, "GET", "/api/health")
        self.node.authorize("127.0.0.1", "GET", "/api/health", headers, b"")
        with self.assertRaises(ValueError): self.node.authorize("127.0.0.1", "GET", "/api/health", headers, b"")
        with self.assertRaises(ValueError): self.node.authorize("127.0.0.1", "GET", "/api/health", {**headers, "Origin": "http://evil"}, b"")
        with self.assertRaises(ValueError): self.node.authorize("192.168.1.2", "GET", "/api/health", headers, b"")

    def test_close_drains_and_rejects(self):
        self.engine.block.clear()
        self.node.submit({"id": "one", "payload": PAYLOAD})
        self.engine.started.wait(1)
        self.node.submit({"id": "two", "payload": PAYLOAD})
        self.node.close()
        self.assertFalse(self.node.thread.is_alive())
        self.assertEqual(self.node.pending.unfinished_tasks, 0)
        with self.assertRaises(RuntimeError): self.node.submit({"id": "three", "payload": PAYLOAD})

    def test_http_signed_inference_and_cancel(self):
        server = make_server(self.node, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = Client(f"http://127.0.0.1:{server.server_port}", SECRET, poll_interval=.01)
        self.assertTrue(client.ready())
        answer = client.infer("http-one", PAYLOAD)
        self.assertEqual(answer["message"]["content"], "OK")
        self.assertEqual(client.pending, {})
        with self.assertRaises(HTTPError) as error: client.request("POST", "/api/execute", {"command": "x"})
        self.assertEqual(error.exception.code, 404)


class ClientFailureTests(unittest.TestCase):
    def client(self): return Client("http://127.0.0.1:8770", SECRET, timeout=.03, poll_interval=.001)

    def test_unavailable_before_submit_allows_fallback(self):
        client = self.client()
        with patch.object(client, "ready", return_value=False), self.assertRaises(RemoteUnavailable): client.infer("one", PAYLOAD)
        self.assertEqual(client.pending, {})

    def test_ambiguous_failure_retains_id_and_payload(self):
        client = self.client()
        with patch.object(client, "ready", return_value=True), patch.object(client, "request", side_effect=URLError("timeout")):
            with self.assertRaises(RemotePending): client.infer("one", PAYLOAD)
        self.assertIn("one", client.pending)
        changed = {**PAYLOAD, "messages": [{"role": "user", "content": "new snapshot"}]}
        with patch.object(client, "request", return_value={"status": "done", "result": {"message": {"content": "OK"}}}) as request:
            client.infer("one", changed)
        self.assertEqual(request.call_args.args[2]["payload"]["messages"], PAYLOAD["messages"])

    def test_previous_acceptance_503_never_allows_blind_fallback(self):
        client = self.client()
        client.pending["one"] = protocol.payload(PAYLOAD)
        with patch.object(client, "request", side_effect=HTTPError("url", 503, "closing", {}, None)), self.assertRaises(RemotePending):
            client.infer("one", PAYLOAD)

    def test_confirmed_cancel_allows_fallback(self):
        client = self.client()
        def request(method, target, value=None):
            return {"status": "interrupted" if target == "/api/cancel" else "running"}
        with patch.object(client, "ready", return_value=True), patch.object(client, "request", side_effect=request), self.assertRaises(RemoteUnavailable):
            client.infer("one", PAYLOAD)
        self.assertEqual(client.pending, {})


if __name__ == "__main__": unittest.main()
