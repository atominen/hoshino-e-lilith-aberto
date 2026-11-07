"""Testes do estado de progresso e da prioridade de entrada real."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from core import progress


checks = []
def ok(desc, cond):
    checks.append((desc, bool(cond)))
    print("  ok   " + desc if cond else "  FALHA " + desc)

progress.limpar()
rid = progress.iniciar("teste longo", channel="tui", task_id="ct-1", task_step=2, task_total=20)
ok("criou run observável", rid.startswith("run-"))
ok("run ativo fica acessível", progress.ativo_id() == rid)
progress.ollama_status(api="online", model_state="carregado")
progress.llm_inicio("llm-1", step=3, max_steps=128)
progress.llm_chunk(content_chars=5, thinking_chars=7, chunks=2)
progress.ferramenta_inicio("execute_command")
progress.ferramenta_fim("execute_command", True)
progress.progresso_sem_avanco(2, 6)
s = progress.snapshot()
ok("conta fragmentos", s["stream_chunks"] == 2)
ok("conta caracteres de saída", s["content_chars"] == 5)
ok("conta ferramenta", s["tool_calls"] == 1)
ok("mostra ciclos sem avanço", s["no_progress_cycles"] == 2 and s["no_progress_limit"] == 6)
ok("mantém etapa da tarefa", s["task_step"] == 2 and s["task_total"] == 20)
texto = progress.render(pending_inputs=1, active_workers=1)
ok("mostra entrada real aguardando", "ENTRADA REAL AGUARDANDO=1" in texto)
ok("mostra watchdog no status", "sem avanço=2/6" in texto)
ok("mostra Ollama e estado do modelo", "Ollama=ONLINE" in texto and "[CARREGADO]" in texto)
ok("mostra decisão operacional sem expor raciocínio privado", "deliberação=" in texto and "executar write_file" not in texto)
progress.finalizar("interrompido", "watchdog")
ok("preserva término interrompido", progress.snapshot()["status"] == "interrompido")
progress.limpar()
progress.ollama_status(api="online", model_state="descarregado")
ok("finaliza e libera run ativo", progress.ativo_id() == "")
ok("volta a ociosa após limpar o snapshot", progress.render().startswith("● OCIOSA"))

print(f"{sum(v for _, v in checks)} verificações ok, {sum(not v for _, v in checks)} falha(s)")
raise SystemExit(0 if all(v for _, v in checks) else 1)
