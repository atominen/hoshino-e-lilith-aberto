"""AIRI/Neuro adaptados: fila limitada, contrato e recibos sem efeitos reais."""
import queue
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from core.work_queue import WorkQueue
from core.action_window import ActionWindow

TOOL = {"function": {"name": "send", "parameters": {"type": "object", "properties": {
    "target": {"type": "string", "enum": ["hoshino", "lilith"]},
    "text": {"type": "string", "minLength": 1, "maxLength": 10},
    "wake": {"type": "boolean"}}, "required": ["target", "text"]}}}


class QueueTests(unittest.TestCase):
    def test_priority_fifo_and_join(self):
        q = WorkQueue(4)
        q.put("tts1")
        q.put("asr", priority="critical")
        q.put("tts2")
        self.assertEqual([q.get() for _ in range(3)], ["asr", "tts1", "tts2"])
        for _ in range(3): q.task_done()
        q.join()

    def test_aging_prevents_starvation(self):
        now = [0]
        q = WorkQueue(clock=lambda: now[0])
        q.put("old", priority="low")
        now[0] = 301
        q.put("new", priority="critical")
        self.assertEqual(q.get(), "old")

    def test_cancel_pending_does_not_cancel_active(self):
        q = WorkQueue(2)
        q.put("active")
        self.assertEqual(q.get(), "active")
        q.put("pending")
        self.assertEqual(q.discard(lambda _: True), ["pending"])
        self.assertEqual(q.unfinished_tasks, 1)
        q.task_done()
        q.join()

    def test_bound_and_invalid_priority(self):
        q = WorkQueue(1)
        q.put("one")
        with self.assertRaises(queue.Full): q.put_nowait("two")
        for value in [None, True, "missing", float("nan"), float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                q.put("x", block=False, priority=value)

    def test_discard_unblocks_producer(self):
        q = WorkQueue(1)
        q.put("one")
        thread = threading.Thread(target=lambda: q.put("two", timeout=1))
        thread.start()
        q.discard(lambda item: item == "one")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(q.get(), "two")
        q.task_done()
        q.join()


class WindowTests(unittest.TestCase):
    def window(self): return ActionWindow().add(TOOL).register()

    def test_state_lifecycle_and_frozen_contract(self):
        w = self.window()
        with self.assertRaises(ValueError): w.add(TOOL)
        w.end()
        with self.assertRaises(ValueError): w.execute("id", "send", {}, lambda *_: None)

    def test_validation_prevents_execution(self):
        for args in [{}, {"target": "alien", "text": "hi"}, {"target": "lilith", "text": ""},
                     {"target": "lilith", "text": "hi", "wake": 1},
                     {"target": "lilith", "text": "hi", "extra": "x"}, "hi"]:
            with self.subTest(args=args):
                calls = []
                result = self.window().execute("id", "send", args, lambda *_: calls.append(1))
                self.assertFalse(result["ok"])
                self.assertEqual(calls, [])

    def test_duplicate_concurrent_ids_execute_once(self):
        w, calls = self.window(), []
        args = {"target": "hoshino", "text": "hi"}
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda _: w.execute("id", "send", args, lambda *_: calls.append(1)), range(20)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(r == results[0] for r in results))
        with self.assertRaises(ValueError): w.execute("id", "send", {**args, "text": "changed"}, lambda *_: None)

    def test_exception_is_correlated_failure_not_success(self):
        def fail(*_): raise RuntimeError("test error")
        result = self.window().execute("id", "send", {"target": "lilith", "text": "hi"}, fail)
        self.assertFalse(result["ok"])
        self.assertEqual(result["action_id"], "id")


if __name__ == "__main__": unittest.main()
