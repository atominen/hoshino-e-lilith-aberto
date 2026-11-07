"""Cliente LAN opcional. Sem proxies, ferramentas remotas ou fallback ambíguo."""
import copy
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, ProxyHandler

import pc2_protocol as protocol


class RemoteUnavailable(RuntimeError):
    """Nenhuma inferência foi aceita: fallback local é permitido."""


class RemotePending(RuntimeError):
    """Aceitação/encerramento incerto: consultar o mesmo id, sem duplicar."""


class Client:
    def __init__(self, url, secret, *, timeout=600, poll_interval=.5):
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Executor precisa de endereço HTTP IPv4 da LAN sem credenciais na URL.")
        protocol.lan_ip(parsed.hostname)
        if parsed.port is None or not 1 <= parsed.port <= 65535 or len(secret) != 32:
            raise ValueError("Porta/chave LAN inválida.")
        self.url, self.secret = url.rstrip("/"), secret
        self.timeout, self.poll_interval = timeout, poll_interval
        self.opener = build_opener(ProxyHandler({}))
        self.pending = {}

    def request(self, method, target, value=None):
        body = b"" if value is None else protocol.encode(value)
        request = Request(self.url + target, data=None if method == "GET" else body,
                          method=method, headers=protocol.auth_headers(self.secret, method, target, body))
        with self.opener.open(request, timeout=5) as response:
            raw = response.read(protocol.MAX_RESPONSE + 1)
            if len(raw) > protocol.MAX_RESPONSE:
                raise RemotePending("Resposta LAN excedeu o limite.")
            return json.loads(raw)

    def health(self):
        value = self.request("GET", "/api/health")
        if value.get("version") != protocol.VERSION or value.get("model") != protocol.MODEL or value.get("entity") != "alistair" or value.get("executes_tools") is not False:
            raise ValueError("Executor incompatível.")
        return value

    def ready(self):
        try:
            return self.health().get("engine", {}).get("model_available") is True
        except (OSError, URLError):
            return False

    def infer(self, identifier, value):
        protocol.request_id(identifier)
        # Mantém o payload aceito durante um retry; o snapshot pode ter mudado.
        resuming = identifier in self.pending
        if not resuming:
            if not self.ready():
                raise RemoteUnavailable("PC2 não está disponível; nenhum pedido enviado.")
            if len(self.pending) >= 32:
                raise RemotePending("Há pedidos LAN sem término confirmado.")
            self.pending[identifier] = copy.deepcopy(protocol.payload(value))
        payload = self.pending[identifier]
        deadline = time.monotonic() + self.timeout
        try:
            job = self.request("POST", "/api/infer", {"id": identifier, "payload": payload})
        except HTTPError as exc:
            if exc.code == 503 and not resuming:
                # Só a rota de admissão devolve 503 antes de aceitar um novo id.
                self.pending.pop(identifier, None)
                raise RemoteUnavailable("Fila PC2 recusou o pedido antes da aceitação.") from exc
            raise RemotePending("Contrato LAN recusado; não houve fallback automático.") from exc
        except (OSError, URLError, ValueError):
            job = None  # Corpo pode ter chegado; consultar id antes de repetir.
        while time.monotonic() < deadline:
            if job and job.get("status") == "done":
                self.pending.pop(identifier, None)
                return job["result"]
            if job and job.get("status") in {"error", "interrupted"}:
                self.pending.pop(identifier, None)
                raise RemoteUnavailable("Inferência PC2 terminou sem resultado: " + str(job.get("error", ""))[:200])
            time.sleep(self.poll_interval)
            try:
                job = self.request("GET", "/api/job?id=" + quote(identifier, safe=""))
            except (OSError, URLError, ValueError):
                job = None
        # Um timeout não é conclusão nem autorização para executar em paralelo.
        try:
            job = self.request("POST", "/api/cancel", {"id": identifier})
            if job.get("status") in {"error", "interrupted"}:
                self.pending.pop(identifier, None)
                raise RemoteUnavailable("Cancelamento PC2 confirmado; fallback local permitido.")
        except RemoteUnavailable:
            raise
        except (OSError, URLError, ValueError):
            pass
        raise RemotePending("PC2 sem término confirmado; mensagem permanece pendente.")


def configured(root):
    from core import alistair_execution
    destination = alistair_execution.destination(root)
    if destination == 'xbox':
        from core.xbox_alistair import Client as XboxClient
        return XboxClient(root)
    if destination == 'local':
        return None
    path = Path(root) / "compartilhado/config/alistair_pc2.json"
    if not path.is_file():
        raise ValueError('Configure o PC2 antes de selecionar esse destino.')
    settings = json.loads(path.read_text())
    if settings.get("enabled") is not True:
        raise ValueError('PC2 não está habilitado/pareado. O caminho original foi preservado.')
    key = Path(settings["key_file"]).expanduser()
    if key.stat().st_mode & 0o077:
        raise ValueError("Chave LAN do PC principal deve ter permissão 600.")
    client = Client(settings["url"], bytes.fromhex(key.read_text().strip()))
    client.strict = alistair_execution.path(root).exists()
    return client
