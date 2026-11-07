"""Fatos locais com prazo, sem sondas/modelos nem memórias reais nos testes."""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import world_state as world, situation
from tools import sensors


class FactsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = world.Store(Path(temp.name) / "world.db")
        self.now = time.time()

    def observe(self, value, **kwargs):
        return self.store.observe("desktop.active_window", value, source="probe", observed_at=self.now, **kwargs)

    def test_read_and_import_do_not_create_database(self):
        self.assertFalse(self.store.snapshot()["available"])
        self.assertFalse(self.store.path.exists())

    def test_observation_has_source_expiry_and_confidence(self):
        self.observe("Editor", ttl=20, confidence=.9)
        fact = self.store.snapshot(now=self.now + 1)["facts"][0]
        self.assertEqual((fact["source"], fact["expires_at"], fact["confidence"]), ("probe", self.now + 20, .9))
        self.assertTrue(fact["known"])

    def test_expiration_and_future_are_not_facts(self):
        self.observe("Editor", ttl=20)
        self.assertEqual(world.fresh_values(self.store.snapshot(now=self.now + 20)), {})
        self.assertEqual(world.fresh_values(self.store.snapshot(now=self.now - 3)), {})

    def test_none_is_unknown_not_false_or_zero(self):
        self.observe(None)
        fact = self.store.snapshot()["facts"][0]
        self.assertEqual(fact["confidence"], 0)
        self.assertTrue(fact["fresh"])
        self.assertFalse(fact["known"])

    def test_empty_collection_is_known_and_zero_confidence_is_unknown(self):
        self.store.observe("central.resources", [], source="central")
        self.assertEqual(world.fresh_values(self.store.snapshot())["central.resources"], [])
        self.observe("suposição", confidence=0)
        self.assertNotIn("desktop.active_window", world.fresh_values(self.store.snapshot()))

    def test_invalid_time_and_confidence(self):
        for args in ({"ttl": 0}, {"ttl": 301}, {"ttl": float("nan")}, {"confidence": -1}, {"confidence": 2}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.observe("X", **args)
        for at in (-1, self.now + 60, float("inf")):
            with self.assertRaises(ValueError):
                self.store.observe("desktop.media", {}, source="x", observed_at=at)

    def test_no_private_interpretations_or_unregistered_keys(self):
        for key in ("mind.feelings", "entity.memory", "unknown"):
            with self.assertRaises(ValueError):
                self.store.observe(key, "x", source="test")
        with self.assertRaises(ValueError):
            self.observe("X", basis="interpretation")

    def test_bad_origin_and_nonfinite_payload(self):
        with self.assertRaises(ValueError):
            self.store.observe("desktop.media", {}, source="../bad")
        with self.assertRaises(ValueError):
            self.observe(float("nan"))
        with self.assertRaises(ValueError):
            self.observe("x" * 32769)

    def test_late_probe_does_not_overwrite(self):
        self.observe("new")
        self.assertFalse(self.store.observe("desktop.active_window", "old", source="probe", observed_at=self.now - 5))
        self.assertEqual(world.fresh_values(self.store.snapshot())["desktop.active_window"], "new")

    def test_same_fact_renews_ttl_without_event(self):
        self.observe("X", ttl=5)
        self.assertFalse(self.store.observe("desktop.active_window", "X", source="probe", observed_at=self.now + 1, ttl=30))
        state = self.store.snapshot(now=self.now + 10, since=0)
        self.assertTrue(state["facts"][0]["known"])
        self.assertEqual(len(state["events"]), 1)

    def test_deduplication_and_events_change(self):
        self.observe("X")
        self.assertFalse(self.observe("X"))
        self.store.observe("desktop.active_window", "Y", source="probe", observed_at=self.now + 1)
        events = self.store.snapshot(since=0)["events"]
        self.assertEqual([e["kind"] for e in events], ["baseline", "changed"])

    def test_tick_metrics_are_not_cognitive_events(self):
        for key in ("system.load1", "desktop.idle_seconds"):
            self.store.observe(key, 1, source="probe")
            self.store.observe(key, 2, source="probe")
        self.assertEqual(self.store.snapshot(since=0)["events"], [])

    def test_cursor_does_not_skip_paginated_events_and_gap_is_explicit(self):
        with patch.object(world, "MAX_EVENTS", 4):
            for i in range(7):
                self.store.observe("desktop.media", {"track": i}, source="x")
        first = self.store.snapshot(since=0, limit=2)
        self.assertTrue(first["event_gap"])
        second = self.store.snapshot(since=first["next_event_id"], limit=2)
        self.assertEqual(len(first["events"] + second["events"]), 4)
        self.assertEqual(second["next_event_id"], first["last_event_id"])

    def test_conflicting_sources_are_unknown_not_highest_confidence_wins(self):
        self.observe("Editor", confidence=.5)
        self.store.observe("desktop.active_window", "Browser", source="other", confidence=1)
        self.assertNotIn("desktop.active_window", world.fresh_values(self.store.snapshot()))
        self.assertEqual(len(self.store.snapshot()["facts"]), 2)

    def test_matching_sources_are_usable(self):
        self.observe("Editor")
        self.store.observe("desktop.active_window", "Editor", source="other")
        self.assertEqual(world.fresh_values(self.store.snapshot())["desktop.active_window"], "Editor")

    def test_concurrent_publishers(self):
        failures = []
        def publish(i):
            try:
                self.store.observe("desktop.active_window", str(i), source="source" + str(i))
            except Exception as exc:
                failures.append(exc)
        threads = [threading.Thread(target=publish, args=(i,)) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(self.store.snapshot()["facts"]), 12)

    def test_no_per_entity_sensor_copy_when_monitor_is_live(self):
        self.store.observe("collector.health", {"running": True}, source="central", basis="service_state")
        self.observe("Editor")
        probe = Mock(side_effect=AssertionError("deveria reutilizar estado"))
        with patch.object(world, "default_path", return_value=self.store.path):
            self.assertEqual(world.sensors_or_local(probe)["janela_ativa"], "Editor")
        probe.assert_not_called()

    def test_stopped_or_expired_monitor_uses_local_fallback(self):
        for health in ({"running": False}, {"running": True}):
            self.store.observe("collector.health", health, source="central", observed_at=self.now - 31)
            with patch.object(world, "default_path", return_value=self.store.path):
                self.assertEqual(world.sensors_or_local(lambda: {"local": True}), {"local": True})

    def test_no_guess_active_window_from_open_windows(self):
        with patch.object(sensors, "janela_ativa", return_value=""), patch.object(sensors, "janelas", return_value=["Browser"]), patch.object(sensors, "midia", return_value={}), patch.object(sensors, "ociosidade_x11", return_value=-1), patch.object(sensors, "carga", return_value={}):
            self.assertEqual(sensors.estado()["janela_ativa"], "")

    def test_monitor_uses_fixed_read_only_local_endpoints_and_whitelists(self):
        from core import interentity, resource_manager, job_bus
        audio = SimpleNamespace(asr=SimpleNamespace(alive=lambda: False), tts=SimpleNamespace(alive=lambda: False), pending=SimpleNamespace(qsize=lambda: 0))
        monitor = world.Monitor(audio, self.store)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"models":[]}'
        with patch.object(sensors, "estado", return_value={"janela_ativa": "", "ociosidade_x11": -1}), patch.object(interentity, "presence", return_value={"entities": [{"entity_id": "hoshino", "status": "sleeping", "detail": "private"}]}), patch.object(resource_manager, "status", return_value=[]), patch.object(job_bus, "status", return_value=[{"id": "job", "kind": "image", "entity": "hoshino", "status": "done", "details": {"prompt": "private"}}]), patch.object(world, "urlopen", return_value=response) as http:
            state = monitor.collect()
        self.assertEqual([call.args[0] for call in http.call_args_list], ["http://127.0.0.1:11435/api/ps", "http://127.0.0.1:11436/api/ps", "http://127.0.0.1:11437/api/ps"])
        self.assertNotIn("private", json.dumps(state))
        self.assertNotIn("desktop.active_window", world.fresh_values(state))
        self.assertNotIn("desktop.idle_seconds", world.fresh_values(state))

    def test_monitor_close_without_start_has_no_writes(self):
        self.assertTrue(world.Monitor(None, self.store).close())
        self.assertFalse(self.store.path.exists())

    def test_failed_probes_are_unknown_and_not_empty_success(self):
        from core import interentity, resource_manager, job_bus
        monitor = world.Monitor(None, self.store)
        with patch.object(sensors, "estado", side_effect=OSError), patch.object(interentity, "presence", side_effect=OSError), patch.object(resource_manager, "status", side_effect=OSError), patch.object(job_bus, "status", side_effect=OSError), patch.object(world, "urlopen", side_effect=OSError):
            state = monitor.collect()
        values = world.fresh_values(state)
        for key in ("desktop.active_window", "desktop.media", "central.resources", "central.jobs", "audio.activity"):
            self.assertNotIn(key, values)
        self.assertIn("audio", values["collector.health"]["failed_sources"])
        self.assertTrue(all(node["models"] is None for node in values["models.residency"]))

    def test_close_error_does_not_block_other_shutdown(self):
        monitor = world.Monitor(None, self.store)
        monitor.thread = Mock()
        monitor.thread.is_alive.return_value = False
        with patch.object(self.store, "observe", side_effect=OSError):
            self.assertTrue(monitor.close())
        self.assertEqual(monitor.last_error, "OSError")

    def test_shutdown_marks_collector_stopped_without_models(self):
        monitor = world.Monitor(None, self.store, interval=1)
        called = threading.Event()
        def fake_collect():
            self.store.observe("collector.health", {"running": True}, source="central")
            called.set()
        with patch.object(monitor, "collect", side_effect=fake_collect):
            monitor.start()
            self.assertTrue(called.wait(5))
            self.assertTrue(monitor.close())
        self.assertFalse(world.fresh_values(self.store.snapshot())["collector.health"]["running"])
        with self.assertRaises(RuntimeError):
            monitor.start()


class PrivateInterpretationTests(unittest.TestCase):
    def interpret(self, sensor, interaction=None, previous=None):
        now = datetime.now()
        with patch.object(situation, "_memoria_curta", return_value=previous or {}), patch.object(situation, "_gravar_memoria_curta"), patch.object(situation, "_pendencias", return_value={}):
            return situation.atualizar(sensor, interaction, now)

    def test_no_input_or_interaction_is_unknown(self):
        state = self.interpret({})
        self.assertIsNone(state["usuario_presente"])
        self.assertEqual(state["eventos"], [])
        self.assertIn("desconhecida", situation.descrever(state))

    def test_stale_interaction_without_input_does_not_prove_absence(self):
        self.assertIsNone(self.interpret({}, datetime.now() - timedelta(days=1))["usuario_presente"])

    def test_same_facts_can_have_distinct_private_interpretations(self):
        facts = {"ociosidade_x11": -1, "world_state": {"source": "shared_factual", "last_event_id": 1}}
        hoshino = self.interpret(facts, datetime.now())
        lilith = self.interpret(facts)
        self.assertTrue(hoshino["usuario_presente"])
        self.assertIsNone(lilith["usuario_presente"])
        self.assertEqual(hoshino["world_state"], lilith["world_state"])
        self.assertFalse(hoshino["interpretacao_presenca"]["presenca_fisica_confirmada"])

    def test_input_inactivity_is_only_a_private_inference(self):
        state = self.interpret({"ociosidade_x11": 1000}, previous={"presente": True})
        # Sem entrada não prova ausência física nem autoriza uma diretiva 'ausente'.
        self.assertIsNone(state["usuario_presente"])
        self.assertEqual(state['interpretacao_presenca']['base'], 'inatividade_de_entrada')
        self.assertFalse(any(e['tipo'] in {'sumiu', 'voltou'} for e in state['eventos']))
        self.assertNotIn("não está no computador", situation.descrever(state))
        from tools import agenda
        with patch.object(agenda, 'objetivos_sustentados', return_value=[{'enquanto': 'ausente'}]):
            self.assertIsNone(agenda.diretiva_ativa(state['usuario_presente']))

    def test_recent_human_interaction_wins_over_keyboard_idle(self):
        state = self.interpret({'ociosidade_x11': 7200}, datetime.now())
        self.assertTrue(state['usuario_presente'])
        self.assertEqual(state['interpretacao_presenca']['base'], 'interacao_recente_com_entidade')

    def test_unknown_presence_does_not_activate_away_only_directive(self):
        from tools import agenda
        away = {"id": "test", "enquanto": "ausente"}
        with patch.object(agenda, "objetivos_sustentados", return_value=[away]):
            self.assertIsNone(agenda.diretiva_ativa(None))
            self.assertIsNone(agenda.diretiva_ativa(True))
            self.assertEqual(agenda.diretiva_ativa(False), away)

    def test_focus_recovery_is_baseline_not_invented_novelty(self):
        with patch.object(situation, "ja_viu", return_value=False):
            state = self.interpret({"janela_ativa": "Novo programa"}, previous={"app_observation_known": False})
        self.assertEqual(state["eventos"], [])
        self.assertEqual(state["novidades"], 0)

    def test_unknown_focus_closes_old_activity_session(self):
        previous = {"app": "Browser", "sessao": {"rotulo": "Browser", "inicio": "2026-10-06T01:00:00"}}
        with patch.object(situation, "_fechar_sessao") as close:
            state = self.interpret({}, previous=previous)
        close.assert_called_once()
        self.assertEqual(state["minutos_na_atividade"], 0)


class ActivityClockTests(unittest.TestCase):
    def setUp(self):
        self.stored = {}
        self.closed = []
        self.now = datetime(2026, 10, 9, 12)
        for name, kwargs in (
            ('_memoria_curta', {'side_effect': lambda: json.loads(json.dumps(self.stored))}),
            ('_gravar_memoria_curta', {'side_effect': self.save}),
            ('_pendencias', {'return_value': {}}), ('ja_viu', {'return_value': True}),
            ('_fechar_sessao', {'side_effect': lambda session, end: self.closed.append((dict(session), end))}),
        ):
            patcher = patch.object(situation, name, **kwargs)
            patcher.start(); self.addCleanup(patcher.stop)

    def save(self, value):
        self.stored = json.loads(json.dumps(value)); return True

    def observe(self, seconds, mono, app='Firefox'):
        return situation.atualizar({'janela_ativa': app}, agora=self.now+timedelta(seconds=seconds), monotonic_now=mono)

    def test_continuous_observation_counts_monotonic_not_wall_clock(self):
        self.observe(0, 100)
        state = self.observe(30, 130)
        self.assertEqual(self.stored['sessao']['duracao_observada_seg'], 30.)
        state = self.observe(40, 150)  # wall clock +10s, monotonic +20s
        self.assertEqual(self.stored['sessao']['duracao_observada_seg'], 50.)
        self.observe(50, 160, 'Steam')
        self.assertEqual(self.closed[-1][0]['duracao_observada_seg'], 60.)
        self.assertEqual(state['minutos_na_atividade'], 0)

    def test_fresh_reset_accumulates_observed_silence_without_inventing_human_presence(self):
        self.observe(0, 100, '')
        for seconds in range(30, 901, 30):
            state = self.observe(seconds, 100+seconds, '')
        self.assertEqual(state['segundos_sem_interacao_observados'], 900)
        self.assertEqual(state['segundos_ociosos'], 0)
        self.assertFalse(state['ultima_interacao_conhecida'])
        self.assertIsNone(state['usuario_presente'])
        self.assertFalse(state['interpretacao_presenca']['presenca_fisica_confirmada'])
        self.assertEqual(state['eventos'], [])

    def test_observed_silence_is_independent_of_window_changes_and_recovers_from_real_interaction(self):
        self.observe(0, 100)
        self.observe(30, 130, 'Steam')
        state = self.observe(60, 160, '')
        self.assertEqual(state['segundos_sem_interacao_observados'], 60)
        state = situation.atualizar({}, ultima_interacao=self.now+timedelta(seconds=65),
            agora=self.now+timedelta(seconds=70), monotonic_now=170)
        self.assertEqual(state['segundos_sem_interacao_observados'], 5)
        self.assertEqual(state['segundos_ociosos'], 5)
        self.assertTrue(state['ultima_interacao_conhecida'])

    def test_observed_silence_does_not_include_restart_suspend_or_regressed_clock(self):
        for seconds, mono, epoch in ((3600, 160, situation._OBSERVATION_EPOCH),
                                     (60, 90, situation._OBSERVATION_EPOCH),
                                     (60, 160, 'another-process')):
            with self.subTest(seconds=seconds, mono=mono, epoch=epoch):
                self.stored = {}
                self.observe(0, 100)
                self.observe(30, 130)
                with patch.object(situation, '_OBSERVATION_EPOCH', epoch):
                    state = self.observe(seconds, mono)
                self.assertEqual(state['segundos_sem_interacao_observados'], 0)

    def test_invalid_human_interaction_does_not_unlock_observed_silence_fallback(self):
        self.observe(0, 100)
        state = situation.atualizar({}, ultima_interacao=self.now+timedelta(days=1),
            agora=self.now+timedelta(seconds=30), monotonic_now=130)
        self.assertEqual(state['segundos_sem_interacao_observados'], 0)
        self.assertFalse(state['ultima_interacao_conhecida'])

    def test_restart_same_app_is_baseline_and_does_not_claim_sleep_interval(self):
        self.observe(0, 100)
        self.observe(60, 160)
        with patch.object(situation, '_OBSERVATION_EPOCH', 'another-process'):
            state = self.observe(3600, 20)
        self.assertEqual(state['minutos_na_atividade'], 0)
        self.assertEqual(state['eventos'], [])
        self.assertEqual(self.closed[-1][0]['duracao_observada_seg'], 60.)
        self.assertNotEqual(self.closed[-1][1], self.now+timedelta(hours=1))

    def test_gap_and_changed_app_do_not_invent_events_during_suspend(self):
        self.observe(0, 100)
        self.observe(60, 160)
        state = self.observe(3600, 161, 'Steam')  # CLOCK_MONOTONIC may exclude suspend
        self.assertEqual(state['eventos'], [])
        self.assertEqual(state['novidades'], 0)
        self.assertEqual(state['minutos_na_atividade'], 0)
        self.assertEqual(self.closed[-1][0]['duracao_observada_seg'], 60.)

    def test_legacy_session_without_last_observation_does_not_invent_hours(self):
        self.stored = {'app': 'Firefox', 'sessao': {'rotulo': 'Firefox', 'inicio': '2026-10-08T12:00:00'}}
        state = self.observe(0, 100)
        self.assertEqual(state['minutos_na_atividade'], 0)
        self.assertEqual(state['eventos'], [])

    def test_invalid_or_regressed_monotonic_time_rebases_conservatively(self):
        self.observe(0, 100)
        state = self.observe(30, 90)
        self.assertEqual(state['minutos_na_atividade'], 0)
        self.assertEqual(self.stored['sessao']['duracao_observada_seg'], 0.)

    def test_closing_activity_persists_only_observed_duration_in_existing_table(self):
        from core import bd
        from memory.sqlite import init_db
        import config
        with tempfile.TemporaryDirectory() as folder, patch.object(config, 'DB_PATH', str(Path(folder)/'activity.db')), \
             patch.object(init_db, 'DB_PATH', config.DB_PATH), \
             patch.object(situation, '_fechar_sessao', wraps=self._real_close):
            init_db.init_database(verbose=False)
            self.observe(0, 100)
            self.observe(60, 160)
            self.observe(61, 161, 'Steam')
            row = bd.um('SELECT * FROM activity_sessions')
            self.assertEqual(row['duracao_seg'], 61)
            self.assertEqual(row['inicio'], '2026-10-09T12:00:00')
            self.assertEqual(row['fim'], '2026-10-09T12:01:01')

    def test_repeated_close_after_crash_does_not_duplicate_activity(self):
        from core import bd
        from memory.sqlite import init_db
        import config
        with tempfile.TemporaryDirectory() as folder, patch.object(config, 'DB_PATH', str(Path(folder)/'activity.db')), \
             patch.object(init_db, 'DB_PATH', config.DB_PATH):
            init_db.init_database(verbose=False)
            self.observe(0, 100)
            self.observe(60, 160)
            pending = dict(self.stored['sessao'])
            self._real_close(pending, self.now+timedelta(seconds=60))
            self._real_close(pending, self.now+timedelta(seconds=60))
            self.assertEqual(bd.um('SELECT count(*) AS n FROM activity_sessions')['n'], 1)

    def test_database_failure_does_not_forget_unclosed_session(self):
        self.observe(0, 100)
        self.observe(60, 160)
        previous = json.loads(json.dumps(self.stored))
        with patch.object(situation, '_fechar_sessao', wraps=self._real_close), \
             patch.object(situation.bd, 'executar', side_effect=sqlite3.OperationalError('database locked')) as write:
            with self.assertRaises(sqlite3.OperationalError):
                self.observe(61, 161, 'Steam')
        self.assertTrue(write.call_args.kwargs['strict'])
        self.assertEqual(self.stored, previous)

    # Capturada antes do patch de setUp, nunca escreve em banco real.
    _real_close = staticmethod(situation._fechar_sessao)


if __name__ == "__main__":
    unittest.main()
