"""Regressões V27 para tarefas longas estruturadas por marcos."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from core import task_state  # noqa: E402


ROTEIRO = "\n\n".join(
    [
        f"ETAPA {n} — MARCO {n}\n\nFaça a ação {n} e verifique o resultado antes de avançar."
        for n in range(1, 21)
    ]
)

checks = []


def ok(desc, cond):
    checks.append((desc, bool(cond)))
    print("  ok   " + desc if cond else "  FALHA " + desc)


partes = task_state.decompor(ROTEIRO)
ok("roteiro de 20 etapas vira 20 marcos", len(partes) == 20)
ok("cada marco preserva seu cabeçalho", all(re.match(r"^ETAPA\s+\d+\b", p) for p in partes))
ok("ordem dos marcos é preservada", [re.search(r"ETAPA\s+(\d+)", p).group(1) for p in partes] == [str(i) for i in range(1, 21)])

# Não acople o tamanho do orçamento longo ao limite normal de 10 passos.
main_txt = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
ok("verificação de tarefa longa usa o orçamento dinâmico", "if passo + 1 < limite_passos:" in main_txt)
ok("saída vazia em tarefa pendente pede nova rodada", '"empty_final_pending_task"' in main_txt)
ok("heartbeat não envia input sintético", "ENTRADA REAL AGUARDANDO" in (ROOT / "app" / "core" / "progress.py").read_text(encoding="utf-8"))

print(f"{sum(v for _, v in checks)} verificações ok, {sum(not v for _, v in checks)} falha(s)")
raise SystemExit(0 if all(v for _, v in checks) else 1)
