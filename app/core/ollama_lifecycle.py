"""Inicialização e encerramento seguros do Ollama da Hoshino.

Responsabilidades:
- verificar a API local e o modelo configurado;
- tentar recuperar o servidor quando a API não aceita conexão;
- nunca abrir um prompt interativo de sudo durante o boot;
- descarregar o modelo no encerramento sem desligar o servidor;
- oferecer um fallback de recuperação quando o servidor não está instalado como
  serviço, desde que não exista outra instância Ollama ativa.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import requests

try:
    import config
except Exception:  # pragma: no cover - import isolado
    config = None


@dataclass(frozen=True)
class OllamaStatus:
    ok: bool
    api_url: str
    model: str
    model_instalado: bool = False
    detalhe: str = ""
    recuperado: bool = False


_ATEEXIT_REGISTRADO = False
_ENCERRADO = False
_PROCESSO_GERENCIADO: subprocess.Popen | None = None


def _cfg(nome: str, padrao):
    return getattr(config, nome, padrao) if config is not None else padrao


def _base_url() -> str:
    alvo = str(_cfg("OLLAMA_URL", "http://127.0.0.1:11435/api/chat")).strip()
    parsed = urlsplit(alvo)
    if not parsed.scheme or not parsed.netloc:
        return "http://127.0.0.1:11435"
    caminho = parsed.path.rstrip("/")
    for sufixo in ("/api/chat", "/api/generate"):
        if caminho.endswith(sufixo):
            caminho = caminho[: -len(sufixo)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, caminho, "", "")).rstrip("/")


def _endpoint(nome: str) -> str:
    return f"{_base_url()}/api/{nome.lstrip('/')}"


def _modelo() -> str:
    return str(_cfg("MODEL_NAME", "hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M"))


def _host() -> str:
    return str(_cfg("OLLAMA_HOST", "127.0.0.1:11435")).strip()


def _modelos_dir() -> str:
    return str(_cfg("OLLAMA_MODELS_DIR", os.path.join(os.getcwd(), "models", "ollama")))


def _timeout() -> float:
    return float(_cfg("OLLAMA_STARTUP_TIMEOUT", 3.5))


def _restart_wait() -> float:
    return float(_cfg("OLLAMA_RESTART_WAIT", 15.0))


def _http_get(path: str, timeout: float | None = None):
    return requests.get(path, timeout=timeout or _timeout())


def _modelo_em_tags(payload: dict, modelo: str) -> bool:
    alvo = modelo.strip().lower()
    for item in payload.get("models", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("name") or item.get("model") or "").strip().lower()
        if nome == alvo:
            return True
        # Algumas versões podem devolver um nome com digest/variante. Aceitar
        # somente a mesma família com dois-pontos, sem considerar um nome vazio.
        if nome.startswith(alvo + "-"):
            return True
    return False


def verificar(timeout: float | None = None) -> OllamaStatus:
    """Verifica conectividade e presença do modelo configurado."""
    modelo = _modelo()
    url = str(_cfg("OLLAMA_URL", "http://127.0.0.1:11435/api/chat"))
    try:
        resposta = _http_get(_endpoint("tags"), timeout)
        resposta.raise_for_status()
        payload = resposta.json()
        instalado = _modelo_em_tags(payload, modelo)
        if not instalado:
            return OllamaStatus(False, url, modelo, False,
                                f"Ollama respondeu, mas o modelo '{modelo}' não está instalado.")
        return OllamaStatus(True, url, modelo, True, "API e modelo disponíveis.")
    except requests.RequestException as exc:
        return OllamaStatus(False, url, modelo, False,
                            f"não foi possível conectar ao Ollama: {type(exc).__name__}: {exc}")
    except (ValueError, TypeError, KeyError) as exc:
        return OllamaStatus(False, url, modelo, False,
                            f"Ollama respondeu de forma inválida: {type(exc).__name__}: {exc}")


def _comando_existe(comando: list[str]) -> bool:
    return bool(comando and shutil.which(comando[0]))


def _executar_restart(comando: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{comando!r}: {type(exc).__name__}: {exc}"
    if proc.returncode == 0:
        return True, " ".join(comando)
    erro = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
    return False, f"{' '.join(comando)} -> código {proc.returncode}: {erro[-300:]}"


def _servico_systemd_existe() -> bool:
    """Descobre se há uma unidade Ollama conhecida antes de usar fallback local."""
    for comando in (["systemctl", "--user", "list-unit-files", "ollama.service", "--no-legend"],
                    ["systemctl", "list-unit-files", "ollama.service", "--no-legend"]):
        if not _comando_existe(comando):
            continue
        try:
            proc = subprocess.run(comando, capture_output=True, text=True, timeout=4, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and "ollama.service" in (proc.stdout or ""):
            return True
    return False


def _reiniciar_por_systemd() -> tuple[bool, list[str]]:
    """Tenta serviços conhecidos sem jamais pedir senha de forma interativa."""
    tentativas = []
    comandos = [
        ["systemctl", "--user", "restart", "ollama"],
        ["sudo", "-n", "systemctl", "restart", "ollama"],
    ]
    tentou = False
    for comando in comandos:
        if not _comando_existe(comando):
            continue
        tentou = True
        ok, detalhe = _executar_restart(comando)
        tentativas.append(detalhe)
        if ok:
            return True, tentativas
    return tentou, tentativas


def _processo_ollama_do_usuario() -> bool:
    try:
        proc = subprocess.run(
            ["pgrep", "-u", str(os.getuid()), "-x", "ollama"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _iniciar_instancia_propria() -> str:
    """Fallback seguro quando não há serviço e nenhuma instância Ollama ativa."""
    global _PROCESSO_GERENCIADO
    if _host() not in {"127.0.0.1:11435", "127.0.0.1:11436", "127.0.0.1:11437"} and _processo_ollama_do_usuario():
        return "já existe um processo Ollama do usuário; não vou matar uma instância desconhecida."
    executavel = shutil.which("ollama")
    if not executavel:
        return "executável 'ollama' não encontrado."

    # Se qualquer serviço já ocupa o host/porta canônicos, não crie uma segunda
    # instância: aguarde apenas a API retornar.
    host_port = _host()
    try:
        host, porta_txt = host_port.rsplit(":", 1)
        porta = int(porta_txt)
        import socket
        with socket.create_connection((host, porta), timeout=0.4):
            return f"a porta do Ollama ({host_port}) já está ocupada; não vou iniciar outro daemon."
    except (ValueError, OSError):
        pass

    runtime = str(_cfg("SHARED_RUNTIME_DIR", _cfg("RUNTIME_DIR", os.getcwd())))
    entidade = str(_cfg("ENTIDADE_ID", "hoshino"))
    log_dir = os.path.join(runtime, "ollama", entidade)
    os.makedirs(_modelos_dir(), exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "server.log")
    log = None
    try:
        log = open(log_path, "a", encoding="utf-8")
        ambiente = os.environ.copy()
        ambiente["OLLAMA_HOST"] = _host()
        ambiente["OLLAMA_MODELS"] = _modelos_dir()
        from core import resource_manager, diagnostics
        cache = resource_manager.ram_prompt_cache_plan()
        cache_env = resource_manager.ram_prompt_cache_environment(entidade, ambiente, plan=cache)
        ambiente.update(cache_env)
        diagnostics.emit('cache.ram_environment_prepared', entity=entidade,
                         cap_mib=int(cache_env['LLAMA_ARG_CACHE_RAM']),
                         aggregate_mib=cache['aggregate_mib'], reason=cache['reason'],
                         state=cache['state'], apply=cache['apply'])
        # A preparação inicial já usa Vulkan; boot/recovery deve conservar
        # esse backend AMD. Não sobrescreve uma opção explícita do operador.
        from core import gpu_metrics
        if gpu_metrics.snapshot().get('known'):
            ambiente.setdefault('OLLAMA_VULKAN', '1')
        _PROCESSO_GERENCIADO = subprocess.Popen(
            [executavel, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=ambiente,
            start_new_session=True,
            close_fds=True,
        )
        return f"iniciada instância local gerenciada (pid={_PROCESSO_GERENCIADO.pid}, log={log_path})"
    except (OSError, ValueError) as exc:
        return f"falha ao iniciar 'ollama serve': {type(exc).__name__}: {exc}"
    finally:
        if log is not None:
            try:
                log.close()
            except Exception:
                pass


def _esperar_api(timeout_total: float | None = None) -> OllamaStatus:
    limite = _restart_wait() if timeout_total is None else float(timeout_total)
    inicio = time.monotonic()
    ultimo = None
    espera = 0.4
    while time.monotonic() - inicio <= limite:
        ultimo = verificar(timeout=min(_timeout(), 2.0))
        if ultimo.ok:
            return ultimo
        time.sleep(espera)
        espera = min(1.5, espera * 1.6)
    return ultimo or verificar(timeout=min(_timeout(), 2.0))


def recuperar() -> OllamaStatus:
    """Tenta recuperar a API sem bloquear indefinidamente nem alterar configuração."""
    atual = verificar()
    if atual.ok:
        return atual

    # Modelo ausente não é falha de conexão; reiniciar o servidor não criaria o modelo.
    if atual.detalhe and "não está instalado" in atual.detalhe:
        return atual

    # Reiniciar o serviço genérico derrubaria a outra entidade e não recuperaria
    # necessariamente o endpoint dedicado que falhou.
    possui_servico = _host() not in {"127.0.0.1:11435", "127.0.0.1:11436", "127.0.0.1:11437"} and _servico_systemd_existe()
    tentativas = []
    if possui_servico:
        _, tentativas = _reiniciar_por_systemd()
        recuperado = _esperar_api()
        if recuperado.ok:
            return OllamaStatus(True, recuperado.api_url, recuperado.model,
                                recuperado.model_instalado,
                                "Ollama recuperado por systemd.", True)

    # Se o endpoint canônico continua indisponível depois do restart, tente uma
    # instância gerenciada no MESMO host/porta. Ela só é criada quando a porta
    # ainda está livre; nunca matamos um processo Ollama desconhecido.
    detalhe_local = _iniciar_instancia_propria()
    if "iniciada instância local" in detalhe_local:
        recuperado = _esperar_api()
        if recuperado.ok:
            return OllamaStatus(True, recuperado.api_url, recuperado.model,
                                recuperado.model_instalado,
                                detalhe_local, True)

    detalhe = "; ".join(x for x in tentativas + [detalhe_local] if x)
    return OllamaStatus(False, atual.api_url, atual.model, atual.model_instalado,
                        f"recuperação do Ollama falhou: {detalhe or atual.detalhe}", False)


def inicializar() -> OllamaStatus:
    """Boot seguro da Hoshino: verifica e recupera o Ollama quando necessário."""
    global _ATEEXIT_REGISTRADO, _ENCERRADO
    _ENCERRADO = False
    if not _ATEEXIT_REGISTRADO:
        atexit.register(encerrar)
        _ATEEXIT_REGISTRADO = True

    status = verificar()
    if status.ok:
        return status
    return recuperar()


def _descarregar_via_chat(timeout: float | None = None, model=None) -> tuple[bool, str]:
    payload = {"model": model or _modelo(), "messages": [], "keep_alive": 0, "stream": False}
    try:
        resposta = requests.post(_endpoint("chat"), json=payload,
                                 timeout=timeout or 10.0)
        resposta.raise_for_status()
        try:
            body = resposta.json()
        except ValueError:
            body = {}
        motivo = body.get("done_reason") if isinstance(body, dict) else None
        return True, str(motivo or "unload solicitado")
    except requests.RequestException as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _modelo_carregado(model=None) -> bool | None:
    try:
        resposta = _http_get(_endpoint("ps"), timeout=min(_timeout(), 2.5))
        resposta.raise_for_status()
        payload = resposta.json()
        nomes = []
        for item in payload.get("models", []) if isinstance(payload, dict) else []:
            if isinstance(item, dict):
                nomes.append(str(item.get("name") or item.get("model") or "").strip().lower())
        return (model or _modelo()).lower() in nomes
    except Exception:
        return None


def descarregar_modelo(timeout: float | None = None) -> tuple[bool, str]:
    """Descarrega os executores desta entidade, sob a mesma manutenção."""
    from core import gpu_resource
    from core import resource_manager
    with gpu_resource.lease("unload"):
        results = []
        deadline = time.monotonic()+(10 if timeout is None else timeout)
        for executor in resource_manager.executor_catalog():
            # Catálogo antigo continua com apenas o principal.
            if executor['tier']!='principal' and not resource_manager.local_model_installed(executor['model']):
                continue
            remaining = deadline-time.monotonic()
            if remaining <= 0: return False, 'prazo de unload dos executores excedido'
            if executor['tier']=='principal':
                ok, detail = _descarregar_modelo_sem_lease(remaining)
            else:
                ok, detail = _descarregar_modelo_sem_lease(remaining, model=executor['model'])
            results.append(detail)
            if not ok: return False, '; '.join(results)
        return True, '; '.join(results)


def _descarregar_modelo_sem_lease(timeout: float | None = None, model=None) -> tuple[bool, str]:
    ok, detalhe = _descarregar_via_chat(timeout) if model is None else _descarregar_via_chat(timeout, model=model)
    if not ok:
        return False, detalhe

    # Confirmar quando a API oferece /api/ps. A confirmação pode não ser possível
    # em builds antigos; isso não transforma um unload aceito em falha falsa.
    limite = time.monotonic() + 3.0
    while time.monotonic() < limite:
        carregado = _modelo_carregado() if model is None else _modelo_carregado(model)
        if carregado is False:
            return True, detalhe
        if carregado is None:
            return False, f"{detalhe}; não foi possível confirmar a liberação do modelo"
        time.sleep(0.25)
    return False, f"{detalhe}; modelo ainda presente após o prazo de confirmação"


def encerrar() -> bool:
    """Encerramento idempotente: limpa o modelo, não mata o servidor Ollama."""
    global _ENCERRADO
    if _ENCERRADO:
        return True
    try:
        ok, _ = descarregar_modelo(timeout=float(_cfg("OLLAMA_SHUTDOWN_TIMEOUT", 10.0)))
        if ok:
            _ENCERRADO = True
        return ok
    except Exception:
        return False


__all__ = [
    "OllamaStatus",
    "verificar",
    "recuperar",
    "inicializar",
    "descarregar_modelo",
    "encerrar",
]
