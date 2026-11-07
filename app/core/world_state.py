"""Fatos compartilhados com origem/validade, sem memória ou interpretação mental.

Leituras não criam banco e não coletam dispositivos. Só o monitor central publica
sondas baratas. Importar/consultar este módulo nunca carrega um modelo.
"""
from __future__ import annotations
import json
import math
import os
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

import config
from core.sqlite_runtime import open_initialized

KEYS = frozenset({"desktop.active_window", "desktop.media", "desktop.idle_seconds",
                 "system.load1", "system.memory_used_pct", "system.disk_free_gb", "system.cpu_count",
                 "central.presence", "central.jobs", "central.resources", "audio.activity",
                 "models.residency", "collector.health",
                 # 06/11: sentidos do PC2, enviados pelo painel da Central que roda lá (core/pc2_remoto).
                 "pc2.desktop.active_window", "pc2.desktop.windows", "pc2.desktop.media", "pc2.desktop.idle_seconds",
                 "pc2.system.load1", "pc2.system.memory_used_pct", "pc2.system.disk_free_gb", "pc2.panel.online"})
MAX_EVENTS = 5000


def default_path():
    return Path(config.SHARED_RUNTIME_DIR) / "world_state.sqlite3"


class Store:
    def __init__(self, path=None):
        self.path = Path(path or default_path())

    def _write(self):
        db = open_initialized(self.path, """
            CREATE TABLE IF NOT EXISTS facts (
                key TEXT NOT NULL, source TEXT NOT NULL, value TEXT NOT NULL,
                observed_at REAL NOT NULL, expires_at REAL NOT NULL,
                confidence REAL NOT NULL, basis TEXT NOT NULL,
                PRIMARY KEY(key,source));
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL,
                source TEXT NOT NULL, value TEXT NOT NULL, observed_at REAL NOT NULL,
                kind TEXT NOT NULL);
        """)
        db.row_factory = sqlite3.Row
        return db

    def observe(self, key, value, *, source, ttl=30, observed_at=None, confidence=1, basis="measurement"):
        now = time.time()
        at = now if observed_at is None else float(observed_at)
        ttl, confidence = float(ttl), float(confidence)
        if key not in KEYS or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", str(source)):
            raise ValueError("Chave/origem de fato inválida.")
        if basis not in {"measurement", "service_state"}:
            raise ValueError("Interpretações não pertencem ao estado factual compartilhado.")
        if (not all(math.isfinite(n) for n in (at, ttl, confidence)) or not 0 <= at <= now + 2
                or not 0 < ttl <= 300 or not 0 <= confidence <= 1):
            raise ValueError("Tempo/validade/confiança inválidos.")
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode()) > 32768:
            raise ValueError("Fato excede o tamanho permitido.")
        confidence = 0 if value is None else confidence
        with closing(self._write()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM facts WHERE key=? AND source=?", (key, source)).fetchone()
            if old and old["observed_at"] > at:
                return False  # Uma sonda atrasada não substitui observação mais nova.
            if old and old["observed_at"] == at and old["value"] == encoded:
                return False
            # Carga/ociosidade mudam continuamente; não viram eventos cognitivos.
            changed = not old or old["value"] != encoded
            local = key.removeprefix("pc2.")
            if changed and (not local.startswith(("system.", "panel.")) and local != "desktop.idle_seconds"):
                db.execute("INSERT INTO events(key,source,value,observed_at,kind) VALUES(?,?,?,?,?)",
                           (key, source, encoded, at, "baseline" if old is None else "changed"))
            db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?) ON CONFLICT(key,source) DO UPDATE SET "
                       "value=excluded.value,observed_at=excluded.observed_at,expires_at=excluded.expires_at,"
                       "confidence=excluded.confidence,basis=excluded.basis",
                       (key, source, encoded, at, at + ttl, confidence, basis))
            db.execute("DELETE FROM events WHERE id < COALESCE((SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?),0)",
                       (MAX_EVENTS - 1,))
        return changed

    def snapshot(self, now=None, since=None, limit=100):
        now = time.time() if now is None else float(now)
        if not math.isfinite(now):
            raise ValueError("Instante inválido.")
        empty = {"available": False, "as_of": now, "facts": [], "events": [], "last_event_id": 0}
        if not self.path.is_file():
            return empty
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN")
                rows = db.execute("SELECT * FROM facts ORDER BY key,source").fetchall()
                last = db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
                first = db.execute("SELECT COALESCE(MIN(id),0) FROM events").fetchone()[0]
                events = []
                if since is not None:
                    if int(since) < 0:
                        raise ValueError("Cursor inválido.")
                    for row in db.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?",
                                          (int(since), max(1, min(100, int(limit))))):
                        events.append({**dict(row), "value": json.loads(row["value"])})
            facts = []
            for row in rows:
                item = dict(row)
                item["value"] = json.loads(item["value"])
                item["fresh"] = item["observed_at"] <= now + 2 and now < item["expires_at"]
                item["known"] = item["fresh"] and item["value"] is not None and item["confidence"] > 0
                facts.append(item)
            return {"available": True, "as_of": now, "facts": facts, "events": events, "last_event_id": last,
                    "next_event_id": events[-1]["id"] if events else int(since or 0),
                    "event_gap": since is not None and int(since) < first - 1}
        except sqlite3.Error:
            return {**empty, "error": "Estado compartilhado indisponível."}


def snapshot(**kwargs):
    return Store().snapshot(**kwargs)


def fresh_values(state):
    """Sem escolher um vencedor arbitrário quando sondas vigentes discordam."""
    result, conflicting = {}, set()
    for fact in state.get("facts", []):
        key = fact["key"]
        if not fact["known"] or key in conflicting:
            continue
        if key in result and result[key] != fact["value"]:
            result.pop(key)
            conflicting.add(key)
        else:
            result[key] = fact["value"]
    return result


def sensor_view(state=None):
    state = snapshot() if state is None else state
    health = fresh_values(state).get("collector.health")
    if not health or not health.get("running"):
        return None  # Nunca usar o retrato anterior como se ainda fosse atual.
    values = fresh_values(state)
    mapping = {"desktop.active_window": "janela_ativa", "desktop.media": "midia",
               "desktop.idle_seconds": "ociosidade_x11", "system.load1": "load1",
               "system.memory_used_pct": "memoria_usada_pct", "system.disk_free_gb": "disco_livre_gb"}
    result = {target: values[key] for key, target in mapping.items() if key in values}
    result.update(janelas=[], world_state={"source": "shared_factual", "last_event_id": state["last_event_id"]})
    from core import pc2_remoto
    pc2 = pc2_remoto.sentidos(values)
    if pc2:
        result["pc2"] = pc2
        idle1, idle2 = result.get("ociosidade_x11"), pc2.get("ociosidade_x11")
        usa_pc2 = isinstance(idle2, (int, float)) and idle2 >= 0 and (
            not isinstance(idle1, (int, float)) or idle1 < 0 or idle2 < idle1)
        if usa_pc2:
            # A pessoa está mexendo no PC2 (Barrier/painel): é lá o "na frente" e o tempo parado que valem.
            result.update(janela_ativa=pc2.get("janela_ativa") or result.get("janela_ativa"),
                          janelas=pc2.get("janelas") or [], ociosidade_x11=idle2, maquina_em_uso="PC2",
                          janela_ativa_pc1=values.get("desktop.active_window"))
        else:
            result["maquina_em_uso"] = "PC1"
    return result


def sensors_or_local(local_probe):
    view = sensor_view()
    return view if view is not None else local_probe()


def brief():
    state = snapshot()
    values = fresh_values(state)
    return {"available": state["available"], "last_event_id": state["last_event_id"],
            "fresh_facts": {k: values[k] for k in ("desktop.active_window", "system.load1", "system.memory_used_pct",
                                                "central.resources", "models.residency") if k in values},
            "boundary": "Observações do ambiente; sentimentos/interpretações são privados de cada entidade."}


class Monitor:
    """Um coletor barato da central, separado do loop de presença e dos modelos."""
    def __init__(self, audio, store=None, interval=10):
        if not 1 <= interval <= 15:
            raise ValueError("Intervalo do coletor inválido.")
        self.audio, self.store = audio, store or Store()
        self.interval = interval
        self.stop = threading.Event()
        self.thread = None
        self.last_error = ""

    def collect(self):
        from tools import sensors
        from core import interentity, resource_manager, job_bus
        failed = []
        measured_at = {}

        def probe(name, fn):
            try:
                return fn()
            except Exception:
                failed.append(name)
                return None
            finally:
                measured_at[name] = time.time()

        sensor = probe("desktop_system", sensors.estado) or {}
        idle = sensor.get("ociosidade_x11")
        idle = idle if isinstance(idle, (int, float)) and math.isfinite(idle) and idle >= 0 else None
        observations = {
            "desktop.active_window": sensor.get("janela_ativa") or None,
            "desktop.media": sensor.get("midia") or None,
            "desktop.idle_seconds": idle,
            "system.load1": sensor.get("load1"), "system.memory_used_pct": sensor.get("memoria_usada_pct"),
            "system.disk_free_gb": sensor.get("disco_livre_gb"), "system.cpu_count": os.cpu_count(),
        }
        presence = probe("presence", interentity.presence)
        observations["central.presence"] = [{"entity": p["entity_id"], "status": p["status"]}
                                            for p in presence["entities"]] if presence is not None else None
        jobs = probe("jobs", job_bus.status)
        observations["central.jobs"] = [{k: j[k] for k in ("id", "kind", "entity", "status")}
                                        for j in jobs] if jobs is not None else None
        resources = probe("resources", resource_manager.status)
        observations["central.resources"] = [{k: r[k] for k in ("resource", "owner", "entity", "pid")}
                                             for r in resources] if resources is not None else None
        activity = probe("audio", lambda: {"asr_worker_alive": self.audio.asr.alive(),
                    "tts_worker_alive": self.audio.tts.alive(), "queue": self.audio.pending.qsize()})
        observations["audio.activity"] = activity
        residency = []
        for entity, port in (("hoshino", 11435), ("lilith", 11436), ("alistair", 11437)):
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/ps", timeout=1) as response:
                    data = json.loads(response.read(32769))
                models = [{"name": m.get("name") or m.get("model"), "size_vram": m.get("size_vram")}
                          for m in data.get("models", [])]
                residency.append({"entity": entity, "reachable": True, "models": models})
            except Exception:
                residency.append({"entity": entity, "reachable": False, "models": None})
        observations["models.residency"] = residency
        measured_at["models"] = time.time()
        observations["collector.health"] = {"running": True, "failed_sources": failed}
        measured_at["collector"] = time.time()
        origins = {"central.presence": "presence", "central.jobs": "jobs", "central.resources": "resources",
                   "audio.activity": "audio", "models.residency": "models", "collector.health": "collector"}
        for key, value in observations.items():
            self.store.observe(key, value, source="central", ttl=30,
                               observed_at=measured_at[origins.get(key, "desktop_system")],
                               basis="service_state" if key.startswith(("central.", "audio.", "models.", "collector.")) else "measurement")
        return self.store.snapshot()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        if self.stop.is_set():
            raise RuntimeError("Coletor encerrado não pode ser reiniciado.")
        def run():
            while not self.stop.is_set():
                try:
                    self.collect()
                    self.last_error = ""
                except Exception as exc:
                    self.last_error = type(exc).__name__
                self.stop.wait(self.interval)
        self.thread = threading.Thread(target=run, name="shared-world-monitor", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(40)
        if self.thread is not None and not self.thread.is_alive():
            try:
                self.store.observe("collector.health", {"running": False, "failed_sources": []}, source="central", ttl=30,
                                   basis="service_state")
            except Exception as exc:
                self.last_error = type(exc).__name__  # Telemetria não impede o encerramento do áudio.
        return self.thread is None or not self.thread.is_alive()
