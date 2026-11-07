"""Estado efemero de execucao para observabilidade da Hoshino.

O progresso aqui e separado do raciocinio do modelo e nao gera novos inputs.
A interface apenas observa o worker ativo e apresenta eventos operacionais:
LLM, ferramenta, fila, verificacao e termino.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, asdict


@dataclass
class ProgressState:
    run_id: str
    status: str = "idle"
    phase: str = "idle"
    label: str = ""
    channel: str = "tui"
    task_id: str = ""
    task_step: int = 0
    task_total: int = 0
    llm_request_id: str = ""
    llm_step: int = 0
    llm_max_steps: int = 0
    tool: str = ""
    started_at: float = 0.0
    last_activity_at: float = 0.0
    last_event: str = ""
    stream_chunks: int = 0
    content_chars: int = 0
    thinking_chars: int = 0
    tool_calls: int = 0
    no_progress_cycles: int = 0
    no_progress_limit: int = 0
    error: str = ""
    model: str = ""
    num_ctx: int = 0
    thinking_enabled: bool = False
    streaming_enabled: bool = False
    available_tools: tuple[str, ...] = ()
    cognitive_action: str = ""
    cognitive_target: str = ""
    next_need: str = ""
    context_messages: int = 0
    ollama_api: str = "desconhecido"
    model_state: str = "desconhecido"


_lock = threading.RLock()
_ativo: ProgressState | None = None
_ultimo: dict | None = None
_ultimo_at: float = 0.0
_modelo_nome = ""
_num_ctx = 0
_thinking_enabled = False
_streaming_enabled = False
_ollama_api = "desconhecido"
_model_state = "desconhecido"


def iniciar(label: str = "", channel: str = "tui", task_id: str = "",
            task_step: int = 0, task_total: int = 0, model: str = "",
            num_ctx: int = 0, thinking_enabled: bool | None = None,
            streaming_enabled: bool | None = None, available_tools=None) -> str:
    global _ativo
    agora = time.monotonic()
    run_id = f"run-{uuid.uuid4().hex[:10]}"
    with _lock:
        _ativo = ProgressState(
            run_id=run_id,
            status="running",
            phase="preparando",
            label=label,
            channel=channel,
            task_id=task_id,
            task_step=int(task_step or 0),
            task_total=int(task_total or 0),
            started_at=agora,
            last_activity_at=agora,
            last_event="iniciando",
            model=str(model or ""),
            num_ctx=int(num_ctx or 0),
            thinking_enabled=bool(thinking_enabled) if thinking_enabled is not None else False,
            streaming_enabled=bool(streaming_enabled) if streaming_enabled is not None else False,
            available_tools=tuple(str(x) for x in (available_tools or []) if str(x).strip()),
            ollama_api=_ollama_api,
            model_state=_model_state,
        )
    return run_id


def _atualizar(agora: bool = True, **kwargs) -> None:
    with _lock:
        if _ativo is None:
            return
        for chave, valor in kwargs.items():
            if hasattr(_ativo, chave):
                setattr(_ativo, chave, valor)
        if agora:
            _ativo.last_activity_at = time.monotonic()


def ativo_id() -> str:
    with _lock:
        return _ativo.run_id if _ativo is not None else ""


def configurar_modelo(model: str, num_ctx: int, thinking_enabled: bool, streaming_enabled: bool) -> None:
    global _modelo_nome, _num_ctx, _thinking_enabled, _streaming_enabled
    _modelo_nome = str(model or "")
    _num_ctx = int(num_ctx or 0)
    _thinking_enabled = bool(thinking_enabled)
    _streaming_enabled = bool(streaming_enabled)
    _atualizar(model=_modelo_nome, num_ctx=_num_ctx,
               thinking_enabled=_thinking_enabled, streaming_enabled=_streaming_enabled)


def ollama_status(api: str | None = None, model_state: str | None = None) -> None:
    global _ollama_api, _model_state
    if api is not None:
        _ollama_api = str(api or "desconhecido")
    if model_state is not None:
        _model_state = str(model_state or "desconhecido")
    _atualizar(ollama_api=_ollama_api, model_state=_model_state)

def ferramentas_disponiveis(nomes) -> None:
    _atualizar(available_tools=tuple(str(x) for x in (nomes or []) if str(x).strip()))


def contexto(messages: int = 0) -> None:
    _atualizar(context_messages=max(0, int(messages or 0)))


def cognicao(action: str = "", target: str = "", next_need: str = "") -> None:
    """Registra somente o estado cognitivo operacional, nunca cadeia de pensamento."""
    _atualizar(cognitive_action=str(action or ""), cognitive_target=str(target or ""),
               next_need=str(next_need or ""), phase="deliberando")


def llm_inicio(request_id: str, step: int = 0, max_steps: int = 0, thinking_enabled: bool | None = None) -> None:
    with _lock:
        global _ativo
        if _ativo is None:
            iniciar(label="chamada LLM")
        _atualizar(phase="llm", status="running", llm_request_id=request_id,
                   llm_step=int(step or 0), llm_max_steps=int(max_steps or 0),
                   thinking_enabled=(bool(thinking_enabled) if thinking_enabled is not None else _ativo.thinking_enabled),
                   tool="modelo", last_event="LLM gerando; aguardando decisão/resultado")


def llm_chunk(content_chars: int = 0, thinking_chars: int = 0, chunks: int = 1) -> None:
    with _lock:
        if _ativo is None:
            return
        _ativo.stream_chunks += int(chunks or 0)
        _ativo.content_chars += int(content_chars or 0)
        _ativo.thinking_chars += int(thinking_chars or 0)
    _atualizar(phase="llm", last_event="fragmento recebido")


def ferramenta_inicio(nome: str) -> None:
    with _lock:
        if _ativo is None:
            return
        _ativo.tool_calls += 1
    _atualizar(phase="ferramenta", tool=str(nome or ""),
               last_event=f"executando {nome}")


def ferramenta_fim(nome: str, ok: bool | None = None) -> None:
    detalhe = "ok" if ok is True else "falhou" if ok is False else "retorno recebido"
    _atualizar(phase="verificando", tool=str(nome or ""),
               last_event=f"{nome}: {detalhe}")


def etapa(step: int = 0, total: int = 0, label: str = "") -> None:
    _atualizar(task_step=int(step or 0), task_total=int(total or 0),
               phase="planejando" if not label else label,
               last_event=label or "etapa atualizada")


def mensagem(evento: str, phase: str = "trabalhando") -> None:
    _atualizar(phase=phase, last_event=str(evento or "atividade"))


def progresso_sem_avanco(ciclos: int, limite: int) -> None:
    """Expõe um possível travamento sem enviar qualquer input sintético ao LLM."""
    _atualizar(no_progress_cycles=max(0, int(ciclos or 0)),
               no_progress_limit=max(0, int(limite or 0)),
               last_event=(f"sem avanço {ciclos}/{limite}" if limite else "sem avanço"),
               phase="recuperando" if ciclos else "trabalhando")


def finalizar(status: str = "concluido", erro: str = "") -> None:
    global _ativo, _ultimo, _ultimo_at
    with _lock:
        if _ativo is None:
            return
        _ativo.status = status
        _ativo.phase = "finalizado" if status == "concluido" else "interrompido"
        _ativo.error = str(erro or "")
        _ativo.last_event = "concluído" if status == "concluido" else status
        _ativo.last_activity_at = time.monotonic()
        # Mantém um snapshot curto para a UI mostrar como a rodada terminou.
        _encerrado = asdict(_ativo)
        _ultimo = _encerrado
        _ultimo_at = time.monotonic()
        _ativo = None


def snapshot() -> dict:
    with _lock:
        if _ativo is not None:
            estado = asdict(_ativo)
        else:
            retention = 4.0
            try:
                from config import PROGRESS_SNAPSHOT_RETENTION
                retention = float(PROGRESS_SNAPSHOT_RETENTION)
            except Exception:
                pass
            if _ultimo is not None and time.monotonic() - _ultimo_at <= retention:
                estado = dict(_ultimo)
            else:
                estado = {
                    "status": "idle",
                    "model": _modelo_nome,
                    "num_ctx": _num_ctx,
                    "thinking_enabled": _thinking_enabled,
                    "streaming_enabled": _streaming_enabled,
                    "ollama_api": _ollama_api,
                    "model_state": _model_state,
                }
    if not estado:
        return {"status": "idle", "model": _modelo_nome, "ollama_api": _ollama_api, "model_state": _model_state}
    agora = time.monotonic()
    estado["elapsed_s"] = max(0.0, agora - float(agora if estado.get("started_at") is None else estado["started_at"]))
    estado["silence_s"] = max(0.0, agora - float(agora if estado.get("last_activity_at") is None else estado["last_activity_at"]))
    return estado


def limpar() -> None:
    global _ativo, _ultimo, _ultimo_at
    with _lock:
        _ativo = None
        _ultimo = None
        _ultimo_at = 0.0


def render(pending_inputs: int = 0, active_workers: int = 0) -> str:
    estado = snapshot()
    try:
        from config import PROGRESS_SEM_EVENTO_AVISO
        aviso_sem_evento = float(PROGRESS_SEM_EVENTO_AVISO)
    except Exception:
        aviso_sem_evento = 45.0
    if estado.get("status") == "idle":
        fila = f" | entradas aguardando: {pending_inputs}" if pending_inputs else ""
        api = str(estado.get("ollama_api") or "?").upper()
        model = str(estado.get("model") or _modelo_nome or "?")
        model_state = str(estado.get("model_state") or "desconhecido").upper()
        return f"● OCIOSA | Ollama={api} | modelo={model} [{model_state}] | nenhum trabalho ativo" + fila

    status = "▶ TRABALHANDO" if estado.get("status") == "running" else "■ " + str(estado.get("status", "")).upper()
    elapsed = float(estado.get("elapsed_s") or 0)
    silencio = float(estado.get("silence_s") or 0)
    fase = str(estado.get("phase") or "atividade")
    modelo = str(estado.get("model") or "?")
    ctx = int(estado.get("num_ctx") or 0)
    think = "ON" if estado.get("thinking_enabled") else "OFF"
    stream = "ON" if estado.get("streaming_enabled") else "OFF"
    api = str(estado.get("ollama_api") or "?").upper()
    model_state = str(estado.get("model_state") or "desconhecido").upper()

    linha1 = f"{status} | {elapsed:.0f}s | fase={fase} | Ollama={api} | modelo={modelo} [{model_state}]"
    thinking_chars = int(estado.get("thinking_chars") or 0)
    thinking_state = f"ATIVO/{thinking_chars}c" if estado.get("phase") == "llm" and think == "ON" else ("ligado" if think == "ON" else "desligado")
    linha2 = (f"ctx={ctx or '?'} | contexto={int(estado.get('context_messages') or 0)} msgs | "
              f"pensando={thinking_state} | stream={stream} | ciclo LLM={estado.get('llm_step', 0)}/{estado.get('llm_max_steps', 0) or '?'}")
    if estado.get("task_total"):
        linha3 = f"tarefa={estado.get('task_step', 0)}/{estado.get('task_total')} | id={str(estado.get('task_id') or '')[:14]}"
    else:
        linha3 = "tarefa=nenhuma"

    acao_cognitiva = str(estado.get("cognitive_action") or "decidir")
    alvo_cognitivo = str(estado.get("cognitive_target") or "")[:100]
    proxima_necessidade = str(estado.get("next_need") or "")[:120]
    linha4a = f"deliberação={acao_cognitiva}" + (f" | alvo={alvo_cognitivo}" if alvo_cognitivo else "")
    if proxima_necessidade:
        linha4a += f" | próxima={proxima_necessidade}"
    tool = str(estado.get("tool") or "nenhuma")
    disponiveis = list(estado.get("available_tools") or ())
    if len(disponiveis) > 5:
        disponiveis = disponiveis[:5] + [f"+{len(estado.get('available_tools') or ()) - 5}"]
    linha4 = f"{linha4a} | usando={tool} | disponíveis={', '.join(disponiveis) if disponiveis else '—'}"

    chunks = int(estado.get("stream_chunks") or 0)
    thinking_chars = int(estado.get("thinking_chars") or 0)
    content_chars = int(estado.get("content_chars") or 0)
    if estado.get("no_progress_limit"):
        sem_avanco = f"sem avanço={estado.get('no_progress_cycles', 0)}/{estado.get('no_progress_limit')}"
    else:
        sem_avanco = "sem avanço=0"
    if pending_inputs:
        entradas = f" | ENTRADA REAL AGUARDANDO={pending_inputs}"
    else:
        entradas = ""
    linha5 = (f"atividade: {estado.get('last_event') or 'atividade'} | stream={chunks} frag | "
              f"pensamento recebido={thinking_chars}c | saída={content_chars}c | {sem_avanco}{entradas}")
    if silencio >= aviso_sem_evento:
        linha5 += f" | sem evento={silencio:.0f}s"
    if active_workers > 1:
        linha5 += f" | workers={active_workers}"
    return "\n".join((linha1, linha2, linha3, linha4, linha5))


__all__ = [
    "iniciar", "ativo_id", "llm_inicio", "llm_chunk", "ferramenta_inicio", "ferramenta_fim",
    "etapa", "mensagem", "configurar_modelo", "ollama_status", "ferramentas_disponiveis", "contexto", "cognicao", "progresso_sem_avanco", "finalizar", "snapshot", "limpar", "render",
]
