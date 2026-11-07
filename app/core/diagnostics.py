"""Diagnóstico estruturado da Hoshino.

Objetivo: conseguir responder "o que aconteceu?" sem depender de um terminal
aberto no momento do erro.

São mantidos dois formatos por dia:
- JSONL: eventos estruturados, fáceis de pesquisar por request_id, ferramenta,
  processo ou sessão.
- LOG: versão humana do mesmo fluxo.

O exportador também coleta um snapshot do ambiente, processos, portas,
Ollama, Node/npm, Python, áudio, sessão gráfica e Minecraft quando possível.
Segredos são redigidos antes de entrar no pacote.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import traceback
import warnings
import contextvars
import functools
import contextlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import config

_LOCK = threading.RLock()
_LOGGERS: dict[str, logging.Logger] = {}
SENSIVE = {
    "token", "password", "senha", "secret", "authorization", "cookie",
    "access_token", "refresh_token", "api_key", "apikey", "bot_token",
    "client_secret", "private_key", "authorization_code",
    "speech_key", "subscription-key", "subscription_key", "xi-api-key",
}
TRACE = os.environ.get("HOSHINO_DIAGNOSTICS_TRACE", "0") == "1"
MAX_TEXT = int(os.environ.get("HOSHINO_DIAGNOSTICS_MAX_TEXT", "1000"))
_HOOKS_INSTALLED = False
_LOG_CAPTURE_INSTALLED = False
_TRACE_RUNTIME = False
SESSION_ID = os.environ.get("HOSHINO_DIAGNOSTIC_SESSION", "") or __import__("uuid").uuid4().hex[:12]
_SEQ = 0
_TURN_CONTEXT = contextvars.ContextVar("hoshino_turn_context", default={})


def _dirs() -> tuple[Path, Path, Path]:
    from core import history
    raiz = Path(config.RUNTIME_DIR) / "diagnostics"
    raiz.mkdir(parents=True, exist_ok=True)
    hoje = history.local_now().date().isoformat()
    return raiz, raiz / f"hoshino_{hoje}.jsonl", raiz / f"hoshino_{hoje}.log"


def _hash(value: Any) -> str:
    raw = str(value).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:16]


@functools.lru_cache(maxsize=1)
def _speech_secret_env_names():
    names = {'AZURE_SPEECH_KEY', 'ELEVENLABS_API_KEY'}
    try:
        path = Path(config.RAIZ)/'compartilhado/config/audio.json'
        settings = json.loads(path.read_text())
        for provider in ('azure','elevenlabs'):
            supplied = settings.get(provider,{})
            name = supplied.get('key_env') if isinstance(supplied,dict) else None
            if isinstance(name,str) and re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):
                names.add(name)
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    return frozenset(names)  # Só nomes; valores secretos nunca entram no cache.


def _redact(value: Any, key: str = "", *, truncate=True) -> Any:
    secret_name = key.casefold() in {n.casefold() for n in _speech_secret_env_names()}
    if not secret_name and key in {'estimated_tokens', 'required_tokens', 'context_tokens',
                                   'output_tokens', 'prompt_tokens'} and type(value) is int and value >= 0:
        return value  # Contagens conhecidas não são credenciais; strings continuam redigidas.
    if key and (any(s in key.lower() for s in SENSIVE) or secret_name):
        return "[REDACTED]"
    if isinstance(value, dict):
        if value.get('tool_name',value.get('name',value.get('tool',value.get('nome'))))=='diario':
            value={k:('[PRIVATE_DIARY]' if k in {'content','arguments','args','resultado','result','output','error','texto','text'} else v) for k,v in value.items()}
        return {str(k): _redact(v, str(k),truncate=truncate) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact(v, key,truncate=truncate) for v in value]
    if isinstance(value, str):
        value=re.sub(r'(?m)^\s*DIARIO:.*$', 'DIARIO: [PRIVATE_DIARY]',value)
        for name in _speech_secret_env_names():
            secret = os.environ.get(name)
            if secret:
                value = value.replace(secret,'[REDACTED]')
        # Redige padrões comuns de credenciais que aparecem dentro de strings.
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", value)
        value = re.sub(r"(?i)((?:token|password|senha|api[_-]?key|secret)\s*[=:]\s*)[^\s,;]+",
                       r"\1[REDACTED]", value)
        if truncate and not TRACE and len(value) > MAX_TEXT:
            return {"len": len(value), "sha256_16": _hash(value), "sample": value[:180]}
        return value[:MAX_TEXT] if truncate and len(value) > MAX_TEXT else value
    return value


def _logger() -> logging.Logger:
    from core import history
    hoje = history.local_now().date().isoformat()
    if hoje in _LOGGERS:
        return _LOGGERS[hoje]
    _, _, text_path = _dirs()
    logger = logging.getLogger(f"hoshino.diagnostics.{hoje}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.FileHandler(text_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    _LOGGERS[hoje] = logger
    return logger


def emit(event: str, level: str = "INFO", **data: Any) -> dict:
    """Registra um evento correlacionado; o diagnóstico nunca pode parar Hoshino."""
    # Importação tardia preserva a configuração/isolamento do runtime antes do
    # primeiro evento. O módulo histórico não deve ser inicializado pelo import
    # do diagnóstico no bootstrap.
    from core import history
    global _SEQ
    ctx = _TURN_CONTEXT.get() or {}
    for key in ('entity', 'author_id', 'input_ids', 'input_sources', 'tool_id', 'llm_request_id', 'audio_id', 'stream_id', 'conversation_session_id'):
        if key in ctx and key not in data:
            data[key] = ctx[key]
    if ctx.get("turn_id") and "turn_id" not in data:
        data["turn_id"] = ctx["turn_id"]
    if ctx.get("conversation") and "conversation" not in data:
        data["conversation"] = ctx["conversation"]
    if ctx.get("turn_kind") and "turn_kind" not in data:
        data["turn_kind"] = ctx["turn_kind"]
    with _LOCK:
        _SEQ += 1
        seq = _SEQ
    record = {
        "ts": history.utc_timestamp(),
        "seq": seq,
        "level": level.upper(),
        "event": event,
        "pid": os.getpid(),
        "session_id": SESSION_ID,
        "turn_id": ctx.get("turn_id", ""),
        "data": _redact(data),
    }
    record['diagnostic_id'] = 'diag-'+_hash((record['session_id'],record['pid'],record['seq'],record['ts']))
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
    with _LOCK:
        try:
            _, jsonl_path, _ = _dirs()
            with jsonl_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            _logger().log(getattr(logging, level.upper(), logging.INFO),
                          f"{event} | {json.dumps(record['data'], ensure_ascii=False, default=str)}")
        except OSError as exc:
            # Inclusive falha ao criar a pasta. Sem recursão para outro logger.
            try:
                sys.stderr.write(json.dumps({"event": "diagnostics.write_failed", "error": str(exc),
                                              "record": record}, ensure_ascii=False, default=str) + "\n")
            except OSError:
                pass
    # Espelha toda a trilha operacional em SQLite para pesquisa pela própria Hoshino.
    try:
        history.event(event, severity=level.upper(), component="diagnostics",
                      data={**_redact(data,truncate=False),'_diagnostic_id':record['diagnostic_id']},
                      turn_id=ctx.get("turn_id", ""), session_id=SESSION_ID, timestamp=record['ts'])
    except Exception:
        pass
    return record


def current_turn_id() -> str:
    return str((_TURN_CONTEXT.get() or {}).get("turn_id", ""))

def current_turn_context() -> dict:
    return dict(_TURN_CONTEXT.get() or {})


@contextlib.contextmanager
def context(**fields):
    """Refina o contexto existente, inclusive em threads, sem coletor paralelo."""
    token = _TURN_CONTEXT.set({**current_turn_context(), **fields})
    try:
        yield
    finally:
        _TURN_CONTEXT.reset(token)

def with_turn_context(func):
    """Correlaciona toda a execução de uma resposta em um turn_id único."""
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        import uuid, time
        turn_id = kwargs.get("turn_id") or f"turn-{uuid.uuid4().hex[:12]}"
        chave = kwargs.get("chave_conversa")
        canal = kwargs.get("canal_lote", "") or getattr(self, "canal_atual", "")
        autonoma = kwargs.get("prompt_interno") is not None
        sources = kwargs.pop('origens_entrada', [])
        for source in sources:
            source.setdefault('turn_id', turn_id)
        ctx = {"turn_id": turn_id, "conversation": repr(chave) if chave is not None else "",
               "channel": str(canal), "turn_kind": "autonomo" if autonoma else "conversa",
               "entity": config.ENTIDADE_ID, "input_sources": sources,
               "input_ids": [s['message_id'] for s in sources if s.get('message_id')],
               "author_id": sources[-1].get('autor_id') if sources else None}
        token = _TURN_CONTEXT.set(ctx)
        started = time.monotonic()
        emit("conversation.turn_context_started", **ctx)
        try:
            result = await func(self, *args, **kwargs)
            status = result.get('status', 'unconfirmed') if isinstance(result, dict) else 'unconfirmed'
            emit("conversation.turn_context_finished", status=status, elapsed_ms=int((time.monotonic()-started)*1000), **ctx)
            return result
        except Exception as exc:
            emit("conversation.turn_context_finished", level="ERROR", status="exception",
                 elapsed_ms=int((time.monotonic()-started)*1000), error_type=type(exc).__name__,
                 error=str(exc), **ctx)
            raise
        finally:
            _TURN_CONTEXT.reset(token)
    return wrapper

def exception(event: str, exc: BaseException, **data: Any) -> None:
    emit(event, level="ERROR", error_type=type(exc).__name__, error=str(exc),
         traceback=traceback.format_exc(limit=20), **data)


def persistence_failure(operation: str, target, exc: BaseException, *, retry_safe=False,
                        committed=False, **data) -> dict:
    """Mesmo diagnóstico existente, com campos estáveis para falhas de aprendizado."""
    return emit("persistence.failed", level="ERROR", operation=operation,
                entity=config.ENTIDADE_ID, target=str(target), error_type=type(exc).__name__,
                error=str(exc), retry_safe=bool(retry_safe), committed=bool(committed), **data)


def trace_enabled() -> bool:
    return bool(TRACE or _TRACE_RUNTIME)


def definir_trace(ativo: bool) -> dict:
    """Ativa/desativa captura diagnóstica profunda em tempo de execução.

    O modo profundo registra conteúdo visível de mensagens e resultados, sempre
    passando pela redação de segredos. Nunca registra o campo privado ``thinking``.
    """
    global _TRACE_RUNTIME
    _TRACE_RUNTIME = bool(ativo)
    emit("diagnostics.trace", ativo=_TRACE_RUNTIME)
    return {"ativo": _TRACE_RUNTIME, "session_id": SESSION_ID}


def content_meta(text: str | None, preview_chars: int = 320) -> dict:
    text = text or ""
    dados = {"len": len(text), "sha256_16": _hash(text)}
    if text:
        dados["preview"] = _redact(text[:preview_chars])
    if trace_enabled():
        dados["sample"] = _redact(text[:MAX_TEXT * 4])
    return dados


def tool_start(name: str, args: dict, request_id: str) -> None:
    if name=='diario':args={k:v for k,v in args.items() if k in {'operacao','id','destinatario'}}
    emit("tool.start", tool=name, request_id=request_id, args=args,
         trace=trace_enabled())


def tool_end(name: str, result: str, request_id: str, ok: bool,
             elapsed_ms: int, **extra: Any) -> None:
    emit("tool.end", level="INFO" if ok else "ERROR", tool=name,
         request_id=request_id, ok=ok, elapsed_ms=elapsed_ms,
         result=({'private':True,'len':len(result)} if name=='diario' else content_meta(result)), **extra)


def _messages_meta(messages: list | None) -> list[dict]:
    saida = []
    for i, message in enumerate(messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", ""))
        content = message.get("content", "")
        if message.get('tool_name')=='diario':content='[PRIVATE_DIARY]'
        item = {
            "index": i,
            "role": role,
            "content": content_meta(str(content)) if content is not None else content_meta(""),
            "has_images": bool(message.get("images")),
            "image_count": len(message.get("images") or []) if isinstance(message.get("images"), list) else 0,
            "tool_name": message.get("tool_name"),
        }
        saida.append(item)
    return saida


def llm_start(request_id: str, model: str, messages: list, tools: list | None,
              payload: dict) -> None:
    tool_context = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") or {}
        tool_context.append({
            "name": str(fn.get("name", "")),
            "description": str(fn.get("description", ""))[:220],
            "required": list((fn.get("parameters") or {}).get("required") or []),
        })
    system_blocks = []
    for i, m in enumerate(messages or []):
        if isinstance(m, dict) and m.get("role") == "system":
            c = str(m.get("content", ""))
            system_blocks.append({"index": i, "chars": len(c), "sha256_16": _hash(c),
                                  "header": c.strip().splitlines()[0][:160] if c.strip() else ""})
    dados = {
        "request_id": request_id, "model": model,
        "message_count": len(messages or []), "tool_count": len(tools or []),
        "content_chars": sum(len(str(m.get("content", ""))) for m in (messages or []) if isinstance(m, dict)),
        "ctx": ((payload.get("options") or {}).get("num_ctx")),
        "thinking": payload.get("think"),
        "messages": _messages_meta(messages),
        "tools": [str(t.get("function", {}).get("name", "")) for t in (tools or []) if isinstance(t, dict)],
        "tool_context": tool_context,
        "system_blocks": system_blocks,
        "last_user": content_meta(next((str(m.get("content", "")) for m in reversed(messages or [])
                                         if isinstance(m, dict) and m.get("role") == "user"), ""), 500),
    }
    if trace_enabled():
        dados["messages_trace"] = [_redact(m) for m in (messages or []) if isinstance(m, dict)]
    emit("llm.start", **dados)


def llm_end(request_id: str, message: dict, elapsed_ms: int, ok: bool = True,
            status: int | None = None, error: str = "") -> None:
    content = str((message or {}).get("content", ""))
    thinking = str((message or {}).get("thinking", ""))
    calls = (message or {}).get("tool_calls") or []
    dados = {
        "request_id": request_id, "ok": ok, "status": status, "elapsed_ms": elapsed_ms,
        "content": content_meta(content, 600),
        "thinking": {"len": len(thinking), "sha256_16": _hash(thinking)},
        "thinking_chars": len(thinking),
        "tool_call_count": len(calls),
        "tool_calls": [_redact(c.get("function", {})) for c in calls if isinstance(c, dict)],
        "error": error,
    }
    if trace_enabled():
        dados["content_trace"] = _redact(content)
    emit("llm.end", level="INFO" if ok else "ERROR", **dados)


def ui(action: str, **data: Any) -> None:
    emit("ui", action=action, **data)


def cognitive(stage: str, **data: Any) -> None:
    emit(f"cognition.{stage}", **data)




class _DiagnosticsLogHandler(logging.Handler):
    """Captura warnings/erros de bibliotecas que usam logging padrão sem duplicar o logger próprio."""
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("hoshino.diagnostics"):
            return
        try:
            payload = {
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info:
                payload["exception"] = self.format(record)
            emit("python.logging", level=record.levelname, **payload)
        except Exception:
            pass


def install_logging_capture() -> None:
    global _LOG_CAPTURE_INSTALLED
    if _LOG_CAPTURE_INSTALLED:
        return
    _LOG_CAPTURE_INSTALLED = True
    root = logging.getLogger()
    handler = _DiagnosticsLogHandler(level=logging.WARNING)
    root.addHandler(handler)


def install_exception_hooks() -> None:
    """Captura exceções não tratadas do processo principal, threads e warnings."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True

    previous_sys = sys.excepthook
    previous_thread = getattr(threading, "excepthook", None)
    previous_warning = warnings.showwarning

    def excepthook(exc_type, exc, tb):
        try:
            emit("process.unhandled_exception", level="ERROR",
                 error_type=getattr(exc_type, "__name__", str(exc_type)),
                 error=str(exc), traceback="".join(traceback.format_tb(tb)))
        finally:
            previous_sys(exc_type, exc, tb)

    def thread_hook(args):
        try:
            emit("thread.unhandled_exception", level="ERROR",
                 thread=getattr(args.thread, "name", ""),
                 error_type=getattr(args.exc_type, "__name__", str(args.exc_type)),
                 error=str(args.exc_value), traceback="".join(traceback.format_tb(args.exc_traceback)))
        finally:
            if previous_thread:
                previous_thread(args)

    def warning_hook(message, category, filename, lineno, file=None, line=None):
        try:
            emit("python.warning", level="WARNING", category=getattr(category, "__name__", str(category)),
                 message=str(message), filename=filename, lineno=lineno)
        finally:
            previous_warning(message, category, filename, lineno, file=file, line=line)

    sys.excepthook = excepthook
    install_logging_capture()
    if hasattr(threading, "excepthook"):
        threading.excepthook = thread_hook
    warnings.showwarning = warning_hook


def install_asyncio_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Registra tarefas/callbacks assíncronos que escaparam do fluxo normal."""
    def handler(current_loop, context):
        emit("asyncio.unhandled", level="ERROR",
             message=str(context.get("message", "")),
             exception=repr(context.get("exception")) if context.get("exception") else "",
             task=repr(context.get("task") or context.get("future")),
             handle=repr(context.get("handle")))
        current_loop.default_exception_handler(context)
    loop.set_exception_handler(handler)


def _run(cmd: list[str], timeout: int = 5) -> dict:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"returncode": p.returncode, "stdout": _redact(p.stdout.strip()),
                "stderr": _redact(p.stderr.strip())}
    except Exception as exc:  # noqa: BLE001
        return {"error_type": type(exc).__name__, "error": str(exc)}


def _shell(command: str, timeout: int = 5) -> dict:
    return _run(["bash", "-lc", command], timeout)


def _python_environment() -> dict:
    result: dict[str, Any] = {"python_executable": sys.executable, "python_version": sys.version}
    result["pip_freeze"] = _run([sys.executable, "-m", "pip", "freeze"], 15)
    result["sound_devices"] = _run([sys.executable, "-c",
        "import sounddevice as s; print(s.query_devices())"], 10)
    return result


def iniciar_sessao_diagnostico(rotulo: str = "") -> dict:
    """Inicia uma captura correlacionada para um teste/ocorrência."""
    global SESSION_ID
    import uuid
    SESSION_ID = uuid.uuid4().hex[:12]
    definir_trace(True)
    emit("diagnostics.session_start", label=rotulo, session_id=SESSION_ID)
    return {"session_id": SESSION_ID, "trace": True, "label": rotulo}


def encerrar_sessao_diagnostico(exportar: bool = False) -> dict:
    resultado = {"session_id": SESSION_ID, "trace": trace_enabled()}
    emit("diagnostics.session_end", session_id=SESSION_ID)
    if exportar:
        resultado["pacote"] = package_diagnosis()
    definir_trace(False)
    return resultado


def registrar_decisao(tool: str, args: dict, step: int, max_steps: int,
                      dominio: str = "", complexidade: str = "",
                      precondicoes: list[str] | None = None,
                      verificacoes: dict | None = None,
                      tarefa: dict | None = None,
                      intencao: dict | None = None) -> None:
    """Registra a ação escolhida sem armazenar cadeia de pensamento privada."""
    emit("cognition.tool_selected", tool=tool, args=args, step=step, max_steps=max_steps,
         dominio=dominio, complexidade=complexidade,
         precondicoes=precondicoes or [], verificacoes=verificacoes or {},
         tarefa=tarefa or {}, intencao=intencao or {})


def collect_diagnostics() -> dict:
    """Coleta o máximo útil possível sem exigir que cada ferramenta esteja instalada."""
    import_config = f"import sys; sys.path.insert(0, {str(config.CODIGO_DIR)!r}); import config,requests; "
    snapshot: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "session_id": SESSION_ID,
        "trace_diagnostico": trace_enabled(),
        "turn_context": current_turn_context(),
        "ollama_url": str(getattr(config, "OLLAMA_URL", "")),
        "cwd": os.getcwd(),
        "session_type": os.environ.get("XDG_SESSION_TYPE", ""),
        "display": bool(os.environ.get("DISPLAY")),
        "wayland_display": bool(os.environ.get("WAYLAND_DISPLAY")),
        "python": _run([sys.executable, "--version"]),
        "platform": _run(["uname", "-a"]),
        "os_release": _run(["bash", "-lc", "cat /etc/os-release"]),
        "uptime": _run(["uptime"]),
        "journal_user_tail": _run(["bash", "-lc", "journalctl --user -b --no-pager -n 250 2>/dev/null || true"], 8),
        "network_summary": _shell("ip -brief address 2>/dev/null; ip route 2>/dev/null | head -30", 5),
        "free": _run(["free", "-h"]),
        "df": _run(["df", "-h", str(config.RAIZ)]),
        "processes": _shell("ps -eo pid,ppid,stat,etime,%cpu,%mem,cmd --sort=pid | grep -E '([h]oshino|[n]ode|[j]ava|[o]llama)' || true", 8),
        "ports": _shell("ss -lntp 2>/dev/null | grep -E ':25565|:8765|:11434|:11435' || true", 5),
        "node": _run(["node", "--version"]),
        "npm": _run(["npm", "--version"]),
        "npm_minecraft": _run(["npm", "--prefix", str(config.MINECRAFT_DIR), "ls", "--depth=0"], 15),
        "ollama_tags": _run([sys.executable, "-c", import_config + "from urllib.parse import urlsplit,urlunsplit; p=urlsplit(config.OLLAMA_URL); b=urlunsplit((p.scheme,p.netloc,p.path.rsplit('/api/',1)[0] if '/api/' in p.path else p.path,'','')); print(requests.get(b+'/api/tags',timeout=4).text)"], 7),
        "ollama_ps": _run([sys.executable, "-c", import_config + "from urllib.parse import urlsplit,urlunsplit; p=urlsplit(config.OLLAMA_URL); b=urlunsplit((p.scheme,p.netloc,p.path.rsplit('/api/',1)[0] if '/api/' in p.path else p.path,'','')); print(requests.get(b+'/api/ps',timeout=4).text)"], 7),
        "bridge_health": _run(["bash", "-lc", "curl -sS --max-time 3 http://127.0.0.1:8765/health || true"], 6),
        "gpu": {
            "rocm_smi": _run(["bash", "-lc", "command -v rocm-smi >/dev/null && rocm-smi || true"], 8),
            "radeon": _run(["bash", "-lc", "command -v radeontop >/dev/null && timeout 2 radeontop -d - -l 1 || true"], 8),
            "pci": _shell("lspci | grep -Ei 'vga|3d|display|amd|radeon' || true", 5),
        },
        "desktop": _shell("command -v xdotool >/dev/null && { xdotool getactivewindow getwindowname 2>/dev/null || true; } || true", 5),
        "python_environment": _python_environment(),
    }
    try:
        from core import progress as _progress
        snapshot["execution_progress"] = _progress.snapshot()
    except Exception as exc:  # noqa: BLE001
        snapshot["execution_progress_error"] = str(exc)
    try:
        import config as _config
        snapshot["config"] = {
            "entidade": _config.ENTIDADE_ID,
            "entity_dir": str(_config.ENTIDADE_DIR),
            "code_dir": str(_config.CODIGO_DIR),
            "model": _config.MODEL_NAME,
            "num_ctx": _config.NUM_CTX,
            "thinking": _config.THINKING,
            "timeout_llm": _config.TIMEOUT_LLM,
            "stream_llm": _config.STREAM_LLM,
            "max_tool_steps": _config.MAX_PASSOS_FERRAMENTA,
            "max_task_steps": _config.MAX_PASSOS_TAREFA_LONGA,
            "mic_ativo": _config.MIC_ATIVO,
            "mic_modo": _config.MIC_MODO,
            "mic_ptt": _config.MIC_PTT_ATALHO,
        }
    except Exception as exc:  # noqa: BLE001
        snapshot["config_error"] = str(exc)
    return snapshot


def _scrub_log_text(text: str) -> str:
    """Sanitiza logs existentes sem destruir seu valor diagnóstico."""
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:token|password|senha|api[_-]?key|secret|authorization|cookie)\s*[=:]\s*)[^\s,;]+",
                  r"\1[REDACTED]", text)
    return text


def _add_text_file(z, base_runtime: Path, path: Path, arcname: str) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    z.writestr(arcname, _scrub_log_text(text))


def _history_session_rows(session_id: str) -> tuple[list[dict], list[dict]]:
    db_path = Path(getattr(config, "RUNTIME_DIR", ".")) / "history.sqlite3"
    if not db_path.exists():
        return [], []
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        messages = [dict(r) for r in conn.execute(
            "SELECT id,ts,direction,role,channel,channel_target,person_id,person_name,content,metadata,turn_id,session_id "
            "FROM messages WHERE session_id=? ORDER BY rowid ASC", (session_id,)).fetchall()]
        events = [dict(r) for r in conn.execute(
            "SELECT id,ts,kind,severity,component,message,data,turn_id,session_id "
            "FROM events WHERE session_id=? ORDER BY rowid ASC", (session_id,)).fetchall()]
        conn.close()
        for row in messages:
            row["content"] = _redact(row.get("content", ""))
            try: row["metadata"] = _redact(json.loads(row.get("metadata") or "{}"))
            except Exception: row["metadata"] = row.get("metadata", "")
        for row in events:
            try: row["data"] = _redact(json.loads(row.get("data") or "{}"))
            except Exception: row["data"] = row.get("data", "")
            row["message"] = _redact(row.get("message", ""))
        return messages, events
    except Exception as exc:
        emit("diagnostics.history_export_error", level="WARNING", error_type=type(exc).__name__, error=str(exc))
        return [], []

def package_diagnosis(output_path: str | None = None) -> str:
    """Cria pacote diagnóstico autocontido e sanitizado."""
    import zipfile

    raiz, _, _ = _dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(output_path) if output_path else Path(config.ENTREGA_SAIDA) / f"diagnostico_hoshino_{stamp}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)

    snapshot = collect_diagnostics()
    emit("diagnostics.collect_start", files_expected=True)
    snap_text = json.dumps(_redact(snapshot), ensure_ascii=False, indent=2, default=str)

    runtime_root = Path(config.RUNTIME_DIR)
    candidates = [
        runtime_root / "event_log",
        runtime_root / "minecraft",
        runtime_root / "bus",
        runtime_root / "jobs",
        raiz,
    ]
    included = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("snapshot.json", snap_text)
        z.writestr("diagnostic_session.json", json.dumps({"session_id": SESSION_ID, "trace": trace_enabled(),
                                                             "turn_context": current_turn_context()}, ensure_ascii=False, indent=2))
        session_messages, session_events = _history_session_rows(SESSION_ID)
        z.writestr("history/session_summary.json", json.dumps({
            "session_id": SESSION_ID, "messages": len(session_messages), "events": len(session_events),
            "first_message": session_messages[0]["ts"] if session_messages else None,
            "last_message": session_messages[-1]["ts"] if session_messages else None,
        }, ensure_ascii=False, indent=2))
        z.writestr("history/session_messages.jsonl", "".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in session_messages))
        z.writestr("history/session_events.jsonl", "".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in session_events))
        z.writestr("diagnostics/session_timeline.jsonl", "".join(
            json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in session_events
        ))
        included += 6
        for base in candidates:
            if not base.exists():
                continue
            for p in base.rglob("*"):
                try:
                    if not p.is_file() or p.stat().st_size > 8 * 1024 * 1024:
                        continue
                except OSError:
                    continue
                low_name = p.name.lower()
                low_path = str(p).lower()
                if low_name.endswith((".env", ".db", ".sqlite", ".sqlite3", ".key", ".pem")):
                    continue
                if any(part in low_path for part in ("/memory/", "/chroma/")):
                    continue
                try:
                    rel = p.relative_to(runtime_root)
                    arc = str(Path("runtime") / rel)
                    _add_text_file(z, runtime_root, p, arc)
                    included += 1
                except (OSError, ValueError):
                    continue

        # Incluir informações do Node e config do projeto sem o node_modules enorme.
        package_json = Path(config.MINECRAFT_DIR) / "package.json"
        if package_json.exists():
            _add_text_file(z, runtime_root, package_json, "project/minecraft/package.json")
            included += 1
        readmes = [
            config.RAIZ / "README.md",
            config.RAIZ / "LEIA-ME-V14-DIAGNOSTICO-JULGAMENTO.md",
            config.RAIZ / "LEIA-ME-V13-DIAGNOSTICO.md",
            config.RAIZ / "LEIA-ME-V12-MINECRAFT-LAN.md",
            config.RAIZ / "LEIA-ME-V11-MINECRAFT-ATALHOS.md",
        ]
        for p in readmes:
            if p.exists():
                _add_text_file(z, runtime_root, p, f"project/{p.name}")
                included += 1

    emit("diagnostics.package_created", path=str(out), bytes=out.stat().st_size, files=included)
    return str(out)
