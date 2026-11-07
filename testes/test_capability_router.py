"""Planejamento/budget isolados; nenhum provedor, transmissão ou cobrança."""
import copy
import json
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import config
from core import capability_router as routing


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((Path(config.RAIZ) / "compartilhado/config/capacidades.json").read_text())
        self.now = time.time()
        self.state = {"facts": [{"key": "central.resources", "value": [], "known": True}]}

    def enabled(self):
        settings = copy.deepcopy(self.settings)
        settings["cloud"]["enabled"] = True
        settings["cloud"]["fx"] = {"source": "fixture", "usd_to_brl": "5", "observed_at": self.now}
        for node in settings["executors"]:
            node["enabled"] = True
        return routing.Router(settings)

    def offer(self, **changes):
        return {"provider": "runpod", "total_usd_h": ".20", "vram_gib": 48, "ram_gib": 64,
                "all_costs_included": True, "observed_at": self.now, **changes}

    def telemetry(self, seconds=20, **changes):
        return {"available": True, "observed_at": self.now, "predicted_seconds": seconds,
                "prediction_basis": "measured", "includes_queue_and_load": True, **changes}

    def assess(self, router=None, level="cloud_leve", offer=None, **changes):
        router = router or self.enabled()
        return router.assess_offer(router.nodes[level], offer or self.offer(), now=self.now, **{"committed_brl": "0", **changes})

    def test_default_is_local_and_four_destinations_only(self):
        router = routing.Router(self.settings)
        for capability in routing.CAPABILITIES:
            for entity in ("hoshino", "lilith", "alistair"):
                if (capability, entity) == ("tts", "alistair"):
                    continue
                result = router.plan(capability, entity, state=self.state)
                self.assertEqual(result["executor"], "pc_principal")
                self.assertFalse(result["execution_migrated"])
        self.assertFalse(router.status()["cloud_enabled"])
        self.assertEqual(set(router.nodes), routing.DESTINATIONS)

    def test_no_extra_destinations_classes_or_real_executor_mode(self):
        for variant in ("extra", "classes", "execute", "missing", "fallback"):
            settings = copy.deepcopy(self.settings)
            if variant == "extra":
                settings["executors"].append({"id": "third_cloud"})
            elif variant == "classes":
                settings["executors"][-1]["class"] = "leve"
            elif variant == "execute":
                settings["mode"] = "execute"
            elif variant == "missing":
                settings["executors"].pop()
            else:
                settings["executors"][0]["capabilities"] = ["llm"]
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                routing.Router(settings)

    def test_invalid_entity_capability_and_alistair_voice(self):
        router = self.enabled()
        for cap, entity in (("other", "hoshino"), ("llm", "other"), ("tts", "alistair")):
            with self.assertRaises(ValueError):
                router.plan(cap, entity)

    def test_disabled_cloud_is_not_bypassed_by_available_telemetry(self):
        with self.assertRaisesRegex(ValueError, "desativada"):
            self.assess(routing.Router(self.settings))

    def test_no_historical_or_stale_exchange_rate(self):
        router = self.enabled()
        for fx in (None, {"source": "fixture", "usd_to_brl": "5", "observed_at": self.now - 3601}):
            router.settings["cloud"]["fx"] = fx
            with self.assertRaisesRegex(ValueError, "Câmbio"):
                self.assess(router)

    def test_stale_quote_unconfigured_vendor_missing_costs(self):
        for offer in (self.offer(observed_at=self.now - 121), self.offer(provider="unknown"), self.offer(all_costs_included=False)):
            with self.assertRaises(ValueError):
                self.assess(offer=offer)

    def test_vram_ram_verified_minimums(self):
        for level, offer in (("cloud_leve", self.offer(vram_gib=23)), ("cloud_normal", self.offer(vram_gib=47)), ("cloud_normal", self.offer(ram_gib=63)), ("cloud_leve", self.offer(vram_gib=None))):
            with self.subTest(level=level, offer=offer), self.assertRaises(ValueError):
                self.assess(level=level, offer=offer)

    def test_hourly_limits_have_exact_decimal_boundaries(self):
        for level, price, maximum in (("cloud_leve", ".30", "1.50"), ("cloud_normal", ".46", "2.30")):
            self.assertEqual(Decimal(self.assess(level=level, offer=self.offer(total_usd_h=price))["hourly_brl"]), Decimal(maximum))
            with self.assertRaises(ValueError):
                self.assess(level=level, offer=self.offer(total_usd_h=str(Decimal(price) + Decimal(".00000001"))))

    def test_no_unknown_accounting_is_assumed_zero(self):
        with self.assertRaisesRegex(ValueError, "Contabilidade"):
            self.assess(committed_brl=None)

    def test_soft_and_hard_daily_budget_are_global(self):
        with self.assertRaisesRegex(ValueError, "operacional"):
            self.assess(committed_brl="21.99")
        self.assess(committed_brl="21.99", essential=True)
        with self.assertRaisesRegex(ValueError, "global"):
            self.assess(level="cloud_normal", committed_brl="23.99", essential=True)

    def test_invalid_money_duration_or_time(self):
        for value in (None, "NaN", "Infinity", "-1", True):
            with self.assertRaises(ValueError):
                routing.money(value)
        for seconds in (0, -1, float("nan"), 86401):
            with self.assertRaises(ValueError):
                self.assess(duration_seconds=seconds)
        with self.assertRaises(ValueError):
            self.enabled().plan("llm", "hoshino", now=float("nan"))

    def test_busy_and_unknown_local_resource_are_distinct(self):
        router = self.enabled()
        result = router.plan("image", "hoshino", state={"facts": []})
        self.assertEqual(result["local_state"], "unknown")
        state = {"facts": [{"key": "central.resources", "value": [{"resource": "gpu"}], "known": True}]}
        self.assertEqual(router.plan("image", "hoshino", state=state)["local_state"], "queue")

    def test_no_unmeasured_remote_latency_or_no_local_comparison(self):
        router = self.enabled()
        for measurement in (self.telemetry(prediction_basis="guess"), self.telemetry(includes_queue_and_load=False), self.telemetry(observed_at=self.now - 31), self.telemetry()):
            result = router.plan("llm", "alistair", state=self.state, telemetry={"athlon": measurement}, now=self.now)
            self.assertEqual(result["executor"], "pc_principal")

    def test_stale_local_prediction_is_not_a_comparison(self):
        result = self.enabled().plan("llm", "alistair", state=self.state, telemetry={"pc_principal": self.telemetry(100, observed_at=self.now - 31), "athlon": self.telemetry(20)}, now=self.now)
        self.assertEqual(result["executor"], "pc_principal")

    def test_athlon_is_compatible_only_with_alistair_llm(self):
        telemetry = {"pc_principal": self.telemetry(100), "athlon": self.telemetry(20)}
        router = self.enabled()
        self.assertEqual(router.plan("llm", "alistair", state=self.state, telemetry=telemetry, now=self.now)["executor"], "athlon")
        self.assertEqual(router.plan("llm", "hoshino", state=self.state, telemetry=telemetry, now=self.now)["executor"], "pc_principal")

    def test_gain_threshold_avoids_small_fluctuations(self):
        telemetry = {"pc_principal": self.telemetry(100), "athlon": self.telemetry(80)}
        router = self.enabled()
        self.assertEqual(router.plan("llm", "alistair", state=self.state, telemetry=telemetry, now=self.now)["executor"], "pc_principal")
        telemetry["athlon"]["predicted_seconds"] = 79
        self.assertEqual(router.plan("llm", "alistair", state=self.state, telemetry=telemetry, now=self.now)["executor"], "athlon")

    def test_warm_state_does_not_erase_loading_and_queue_cost(self):
        telemetry = {"pc_principal": self.telemetry(100), "athlon": self.telemetry(100, model_warm=True)}
        result = self.enabled().plan("llm", "alistair", state=self.state, telemetry=telemetry, now=self.now)
        self.assertEqual(result["executor"], "pc_principal")

    def test_warm_flag_does_not_fabricate_measured_speed_gain(self):
        telemetry = {"pc_principal": self.telemetry(100), "athlon": self.telemetry(88, model_warm=True)}
        result = self.enabled().plan("llm", "alistair", state=self.state, telemetry=telemetry, now=self.now)
        self.assertEqual(result["executor"], "pc_principal")
        telemetry["athlon"]["predicted_seconds"] = 70
        result = self.enabled().plan("llm", "alistair", state=self.state, telemetry=telemetry, now=self.now)
        self.assertEqual(result["predicted_seconds"], 70)

    def test_light_before_normal_and_plan_never_transfers_execution(self):
        telemetry = {"pc_principal": self.telemetry(100), "cloud_leve": self.telemetry(30, offer=self.offer()), "cloud_normal": self.telemetry(20, offer=self.offer())}
        result = self.enabled().plan("llm", "hoshino", state=self.state, telemetry=telemetry, committed_brl="0", now=self.now)
        self.assertEqual(result["executor"], "cloud_leve")
        self.assertFalse(result["execution_migrated"])
        self.assertEqual(result["mode"], "plan_only")

    def test_unknown_budget_rejects_even_fast_cloud(self):
        telemetry = {"pc_principal": self.telemetry(100), "cloud_leve": self.telemetry(20, offer=self.offer())}
        result = self.enabled().plan("llm", "hoshino", state=self.state, telemetry=telemetry, now=self.now)
        self.assertEqual(result["executor"], "pc_principal")
        self.assertIn("Contabilidade", result["rejected"]["cloud_leve"])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.ledger = routing.BudgetLedger(Path(temp.name) / "budget.db")

    def test_read_does_not_create_database(self):
        self.assertEqual(self.ledger.total(), 0)
        self.assertFalse(self.ledger.path.exists())

    def test_reservations_from_vendors_share_daily_budget(self):
        self.ledger.reserve("12", context="runpod leve")
        self.ledger.reserve("12", context="gpulabs normal")
        with self.assertRaises(ValueError):
            self.ledger.reserve(".000001")
        self.assertEqual(self.ledger.total(), 24)

    def test_concurrent_reservations_cannot_overrun_budget(self):
        accepted, rejected = [], []
        def reserve():
            try:
                accepted.append(self.ledger.reserve("4"))
            except ValueError:
                rejected.append(True)
        threads = [threading.Thread(target=reserve) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual((len(accepted), len(rejected), self.ledger.total()), (6, 6, 24))

    def test_micro_unit_rounding_is_conservative(self):
        self.assertEqual(routing.micros(".0000001"), 1)
        with self.assertRaises(ValueError):
            self.ledger.reserve("24.0000001", ceiling_brl="24.0000009")

    def test_real_cost_over_estimate_is_recorded_and_blocks_next(self):
        identifier = self.ledger.reserve("1")
        self.ledger.settle(identifier, "25")
        self.assertEqual(self.ledger.total(), 25)
        with self.assertRaises(ValueError):
            self.ledger.reserve("1")

    def test_settle_idempotency_and_cancel_does_not_erase_final_cost(self):
        identifier = self.ledger.reserve("1")
        self.ledger.settle(identifier, "2")
        self.ledger.settle(identifier, "2")
        self.assertFalse(self.ledger.cancel(identifier))
        with self.assertRaises(ValueError):
            self.ledger.settle(identifier, "3")
        self.assertEqual(self.ledger.total(), 2)

    def test_cancelled_reservation_not_settled_or_counted(self):
        identifier = self.ledger.reserve("1")
        self.assertTrue(self.ledger.cancel(identifier))
        self.assertFalse(self.ledger.cancel(identifier))
        self.assertEqual(self.ledger.total(), 0)
        with self.assertRaises(ValueError):
            self.ledger.settle(identifier, "2")

    def test_day_buckets_are_separate(self):
        self.ledger.reserve("24", day="2026-10-06")
        self.ledger.reserve("24", day="2026-10-07")
        self.assertEqual(self.ledger.total("2026-10-06"), 24)
        self.assertEqual(self.ledger.total("2026-10-07"), 24)

    def test_two_simultaneous_different_settlements_do_not_overwrite(self):
        identifier = self.ledger.reserve("1")
        accepted, rejected = [], []
        def settle(value):
            try:
                self.ledger.settle(identifier, value)
                accepted.append(value)
            except ValueError:
                rejected.append(value)
        threads = [threading.Thread(target=settle, args=(value,)) for value in ("2", "3")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual((len(accepted), len(rejected)), (1, 1))
        self.assertEqual(self.ledger.total(), Decimal(accepted[0]))


if __name__ == "__main__":
    unittest.main()
