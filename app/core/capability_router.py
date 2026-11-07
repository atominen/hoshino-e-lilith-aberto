"""Planejador por capacidade: quatro destinos, local-first, sem executor remoto.

Nenhuma função aqui aluga máquinas, chama endpoints remotos ou transmite contexto.
Previsões/cotações devem ser medidas e recentes; ausência não vira custo zero.
"""
from __future__ import annotations
import json
import math
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from zoneinfo import ZoneInfo
import config
from core import world_state
from core.sqlite_runtime import open_initialized

DESTINATIONS = {"pc_principal", "athlon", "cloud_leve", "cloud_normal"}
CAPABILITIES = {"llm", "tts", "asr", "image"}


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError("Valor monetário inválido.")
        return result
    except InvalidOperation as exc:
        raise ValueError("Valor monetário inválido.") from exc


def micros(value):
    return int((money(value) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


class BudgetLedger:
    """Reservas locais prospectivas, não extrato nem proteção do provedor.

Os dois níveis/fornecedores disputam o mesmo total diário. A integração real
deverá contabilizar taxas e períodos que cruzem meia-noite, reconciliar faturas
e confirmar a parada do provedor; este ledger não executa essas operações.
"""
    def __init__(self, path=None):
        self.path = Path(path or Path(config.SHARED_RUNTIME_DIR) / "cloud_budget.sqlite3")

    @staticmethod
    def day():
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()

    def _conn(self):
        return open_initialized(self.path, "CREATE TABLE IF NOT EXISTS budget (id TEXT PRIMARY KEY, day TEXT NOT NULL, "
                                "amount INTEGER NOT NULL, status TEXT NOT NULL, context TEXT NOT NULL);")

    def total(self, day=None):
        if not self.path.is_file():
            return Decimal(0)
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            result = db.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE day=? AND status IN ('reserved','settled')",
                                (day or self.day(),)).fetchone()[0]
        return Decimal(result) / 1_000_000

    def reserve(self, amount_brl, ceiling_brl="24.00", context="", day=None):
        amount = micros(amount_brl)
        ceiling = int((money(ceiling_brl) * 1_000_000).to_integral_value(rounding=ROUND_FLOOR))
        if amount <= 0 or len(str(context)) > 200:
            raise ValueError("Reserva inválida.")
        identifier, day = "budget-" + uuid.uuid4().hex, day or self.day()
        with closing(self._conn()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT COALESCE(SUM(amount),0) FROM budget WHERE day=? AND status IN ('reserved','settled')", (day,)).fetchone()[0]
            if total + amount > ceiling:
                raise ValueError("Orçamento diário global insuficiente.")
            db.execute("INSERT INTO budget VALUES(?,?,?,?,?)", (identifier, day, amount, "reserved", str(context)))
        return identifier

    def settle(self, identifier, actual_brl):
        # Registrar custo real acima da previsão é obrigatório, nunca apagá-lo.
        amount = micros(actual_brl)
        with closing(self._conn()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT amount,status FROM budget WHERE id=?", (identifier,)).fetchone()
            if row is None or row[1] not in {"reserved", "settled"}:
                raise ValueError("Reserva desconhecida/encerrada.")
            if row[1] == "settled" and row[0] != amount:
                raise ValueError("Liquidação já registrada com outro valor.")
            db.execute("UPDATE budget SET amount=?,status='settled' WHERE id=?", (amount, identifier))

    def cancel(self, identifier):
        with closing(self._conn()) as db, db:
            result = db.execute("UPDATE budget SET status='cancelled' WHERE id=? AND status='reserved'", (identifier,))
            return result.rowcount == 1


def fresh(at, now, ttl):
    try:
        return all(math.isfinite(float(v)) for v in (at, now, ttl)) and 0 <= float(now) - float(at) <= ttl
    except (TypeError, ValueError):
        return False


class Router:
    def __init__(self, settings=None):
        if settings is None:
            path = Path(config.RAIZ) / "compartilhado/config/capacidades.json"
            settings = json.loads(path.read_text(encoding="utf-8"))
        self.settings = settings
        nodes = settings.get("executors", [])
        self.nodes = {n["id"]: n for n in nodes}
        if len(nodes) != 4 or set(self.nodes) != DESTINATIONS or not self.nodes["pc_principal"].get("enabled"):
            raise ValueError("O roteador exige PC principal, Athlon, cloud leve e cloud normal; fallback local obrigatório.")
        if settings.get("mode") != "plan_only":
            raise ValueError("Executor remoto ainda não implementado; só planejamento é permitido.")
        classes = {"pc_principal": "local", "athlon": "local", "cloud_leve": "leve", "cloud_normal": "normal"}
        if any(n.get("class") != classes[name] for name, n in self.nodes.items()):
            raise ValueError("As duas classes cloud não podem ser trocadas ou ampliadas.")
        local = self.nodes["pc_principal"]
        if not CAPABILITIES.issubset(local.get("capabilities", [])) or not {"hoshino", "lilith", "alistair"}.issubset(local.get("entities", [])):
            raise ValueError("PC principal precisa cobrir todas as capacidades e entidades.")

    def assess_offer(self, node, offer, *, now=None, committed_brl=None, duration_seconds=1200, essential=False):
        now = time.time() if now is None else float(now)
        if not math.isfinite(now):
            raise ValueError("Instante inválido.")
        cloud = self.settings["cloud"]
        if not cloud.get("enabled") or not node.get("enabled"):
            raise ValueError("Cloud desativada.")
        fx = cloud.get("fx") or {}
        if not fresh(fx.get("observed_at"), now, 3600) or not fx.get("source"):
            raise ValueError("Câmbio ausente ou vencido; valores históricos do anexo não são usados.")
        if not fresh(offer.get("observed_at"), now, 120) or offer.get("provider") not in cloud["providers"]:
            raise ValueError("Oferta ausente, vencida ou fornecedor não configurado.")
        if offer.get("all_costs_included") is not True:
            raise ValueError("Custos associados não foram informados.")
        for field in ("vram_gib", "ram_gib"):
            value = offer.get(field)
            if value is None or not math.isfinite(float(value)) or float(value) < node["min_" + field]:
                raise ValueError("Memória da oferta insuficiente ou não verificada.")
        duration_seconds = float(duration_seconds)
        if not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 86400:
            raise ValueError("Duração inválida.")
        rate = money(offer.get("total_usd_h")) * money(fx.get("usd_to_brl"))
        if rate <= 0 or rate > money(cloud["light_max_brl_h" if node["class"] == "leve" else "normal_max_brl_h"]):
            raise ValueError("Preço por hora excede o teto da classe ou é inválido.")
        if committed_brl is None:
            raise ValueError("Contabilidade diária não foi confirmada.")
        commitment = money(committed_brl)
        projected = rate * money(duration_seconds) / 3600
        if commitment + projected > money(cloud["daily_brl"]):
            raise ValueError("Orçamento diário global insuficiente.")
        if not essential and commitment + projected > money(cloud["soft_daily_brl"]):
            raise ValueError("Limite operacional diário atingido.")
        return {"provider": offer["provider"], "hourly_brl": str(rate), "reservation_brl": str(projected.quantize(Decimal(".000001"), rounding=ROUND_CEILING)),
                "below_light_preference": node["class"] == "leve" and rate < money(cloud["light_preferred_brl_h"])}

    def plan(self, capability, entity, *, state=None, telemetry=None, committed_brl=None, now=None):
        if capability not in CAPABILITIES or entity not in {"hoshino", "lilith", "alistair"}:
            raise ValueError("Capacidade/entidade inválida.")
        if capability == "tts" and entity == "alistair":
            raise ValueError("Alistair não tem voz.")
        now = time.time() if now is None else float(now)
        if not math.isfinite(now):
            raise ValueError("Instante inválido.")
        values = world_state.fresh_values(world_state.snapshot() if state is None else state)
        resource = "gpu" if capability == "image" or capability == "llm" and entity != "alistair" else "alistair_cpu" if capability == "llm" else "cpu_audio"
        busy = any(r["resource"] == resource for r in values.get("central.resources", []))
        choice = {"mode": "plan_only", "executor": "pc_principal", "capability": capability, "entity": entity,
                  "local_state": "queue" if busy else "not_observed_busy" if "central.resources" in values else "unknown",
                  "reason": "Fallback local obrigatório; execução atual permanece local.", "rejected": {}, "execution_migrated": False}
        telemetry = telemetry or {}
        def latency(measurement):
            value = measurement.get("predicted_seconds")
            if (not fresh(measurement.get("observed_at"), now, 30)
                    or measurement.get("prediction_basis") != "measured"
                    or measurement.get("includes_queue_and_load") is not True
                    or value is None or not math.isfinite(float(value)) or float(value) <= 0):
                raise ValueError("Latência recente com fila/carregamento não medida.")
            return float(value)
        try:
            local_time = latency(telemetry.get("pc_principal", {}))
        except (ValueError, TypeError):
            local_time = None
        scored = []
        for name in ("athlon", "cloud_leve", "cloud_normal"):
            node, measurement = self.nodes[name], telemetry.get(name, {})
            try:
                if not node.get("enabled"):
                    raise ValueError("Destino não configurado/ativado.")
                if entity not in node["entities"] or capability not in node["capabilities"]:
                    raise ValueError("Capacidade/entidade incompatível.")
                if measurement.get("available") is not True or not fresh(measurement.get("observed_at"), now, 30):
                    raise ValueError("Executor sem sinal recente de saúde.")
                estimated = latency(measurement)
                if local_time is None and not busy:
                    raise ValueError("Sem comparação medida que justifique sair do PC principal.")
                score = float(estimated)
                price = None
                if node["class"] != "local":
                    price = self.assess_offer(node, measurement.get("offer", {}), now=now, committed_brl=committed_brl,
                                              duration_seconds=max(1200, score))
                if local_time is not None and (not math.isfinite(float(local_time)) or score >= float(local_time) * .8):
                    raise ValueError("Ganho medido insuficiente; local-first evita oscilações.")
                # Residência desempata, mas não inventa um desconto de latência:
                # carregamento/fila já estão incluídos na previsão medida.
                scored.append((0 if node["class"] in {"local", "leve"} else 1, score,
                               0 if measurement.get("model_warm") is True else 1, name, price))
            except (ValueError, TypeError, KeyError) as exc:
                choice["rejected"][name] = str(exc)
        if scored:
            _, score, _, name, price = min(scored)
            choice.update(executor=name, reason="Alternativa proposta por medidas recentes; nenhuma execução foi transferida.",
                          predicted_seconds=round(score, 3), quote=price)
        return choice

    def status(self, entity="hoshino"):
        cloud = self.settings["cloud"]
        return {"mode": "plan_only", "execution": "local", "cloud_enabled": cloud["enabled"],
                "providers": cloud["providers"], "destinations": [{"id": n["id"], "enabled": n["enabled"]} for n in self.nodes.values()],
                "limits_brl": {k: cloud[k] for k in ("daily_brl", "soft_daily_brl", "light_preferred_brl_h", "light_max_brl_h", "normal_max_brl_h")},
                "plan": self.plan("llm", entity), "billing_connected": False, "provisioning_implemented": False}
