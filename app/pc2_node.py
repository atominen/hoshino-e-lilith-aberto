"""Executor CPU portátil: só inferência, sem mente ou execução de ferramentas."""
from __future__ import annotations
import argparse
import collections
import copy
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, ProxyHandler

import pc2_protocol as protocol
from core.work_queue import WorkQueue


def memory():
    try:
        values = {line.split(":", 1)[0]: int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith(("MemTotal:", "MemAvailable:"))}
        return {"total_bytes": values["MemTotal"], "available_bytes": values["MemAvailable"]}
    except (OSError, ValueError, KeyError):
        return {"total_bytes": None, "available_bytes": None}


class Engine:
    """Daemon próprio, porta dedicada. Só encerra o grupo criado por esta instância."""
    def __init__(self, root, settings):
        self.root, self.settings = Path(root), settings
        self.process = None
        self.lock = threading.RLock()
        self.opener = build_opener(ProxyHandler({}))
        self.base = f"http://127.0.0.1:{settings.get('ollama_port', 11438)}"

    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                return
            port = int(self.settings.get("ollama_port", 11438))
            if port != 11438:
                raise ValueError("O pacote usa porta Ollama isolada 11438.")
            with socket.socket() as check:
                check.bind(("127.0.0.1", port))  # Não reutilizar ou matar daemon de outro programa.
            executable = self.root / "engine/bin/ollama"
            guard = self.root / "child_guard.py"
            if not executable.is_file() or not guard.is_file():
                raise RuntimeError("Motor portátil ou proteção de subprocesso ausente.")
            env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11438", "OLLAMA_MODELS": str(self.root / "models"),
                   "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NO_CLOUD": "1",
                   "OLLAMA_CONTEXT_LENGTH": "4096", "OMP_NUM_THREADS": "2", "OLLAMA_DEBUG": "0",
                   "CUDA_VISIBLE_DEVICES": "-1", "HIP_VISIBLE_DEVICES": "-1", "ROCR_VISIBLE_DEVICES": "-1",
                   "LD_LIBRARY_PATH": str(self.root / "engine/lib/ollama")}
            self.process = subprocess.Popen([sys.executable, str(guard), str(os.getpid()), str(executable), "serve"],
                    cwd=self.root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Motor CPU encerrou durante a inicialização; verifique compatibilidade do Linux.")
            try:
                self.query("/api/version", timeout=1)
                return
            except Exception:
                time.sleep(.2)
        self.close()
        raise RuntimeError("Motor CPU não respondeu na porta dedicada.")

    def query(self, target, value=None, timeout=5):
        request = Request(self.base + target, data=None if value is None else protocol.encode(value),
                          headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=timeout) as response:
            raw = response.read(protocol.MAX_RESPONSE + 1)
            if len(raw) > protocol.MAX_RESPONSE:
                raise ValueError("Resposta do motor excedeu o limite.")
            return json.loads(raw)

    def info(self):
        if not self.process or self.process.poll() is not None:
            return {"alive": False, "model_available": False, "warm": False}
        names = [entry.get("name") for entry in self.query("/api/tags").get("models", [])]
        resident = [entry for entry in self.query("/api/ps").get("models", []) if entry.get("name") == protocol.MODEL]
        if any(entry.get("size_vram") != 0 for entry in resident):
            raise RuntimeError("Residência exclusivamente CPU não confirmada.")
        return {"alive": True, "model_available": protocol.MODEL in names, "warm": bool(resident)}

    def infer(self, value, cancel):
        if cancel.is_set():
            raise RuntimeError("Inferência cancelada.")
        self.start()
        if cancel.is_set():
            raise RuntimeError("Inferência cancelada.")
        return self.query("/api/chat", value, timeout=600)

    def close(self):
        with self.lock:
            process = self.process
            if not process or process.poll() is not None:
                return
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                process.wait(5)
                return
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(5)


class Node:
    def __init__(self, engine, secret, *, allowed_clients=("127.0.0.1",), mem_probe=memory, queue_size=2):
        if len(secret) != 32:
            raise ValueError("Chave LAN deve conter 32 bytes aleatórios.")
        self.engine, self.secret = engine, secret
        self.allowed_clients = {protocol.lan_ip(client) for client in allowed_clients}
        self.mem_probe = mem_probe
        self.pending = WorkQueue(maxsize=queue_size)
        self.lock = threading.RLock()
        self.jobs, self.nonces = {}, {}
        self.samples = collections.deque(maxlen=20)
        self.closing = False
        self.thread = threading.Thread(target=self.run, name="pc2-serial-inference", daemon=True)
        self.thread.start()

    def authorize(self, address, method, target, headers, body):
        if address not in self.allowed_clients or headers.get("Origin"):
            raise ValueError("Origem não autorizada.")
        nonce = protocol.verify(self.secret, method, target, headers, body)
        with self.lock:
            now = time.time()
            self.nonces = {n: at for n, at in self.nonces.items() if now - at < 120}
            if nonce in self.nonces or len(self.nonces) >= 2048:
                raise ValueError("Pedido repetido ou limite de autenticação atingido.")
            self.nonces[nonce] = now

    def prune(self):
        now = time.time()
        finished = sorted((j for j in self.jobs.values() if j["status"] not in {"queued", "running"}), key=lambda j: j["updated_at"])
        for job in finished:
            if now - job["updated_at"] > 900 or len(self.jobs) >= 32:
                self.jobs.pop(job["id"], None)

    def submit(self, value):
        if not isinstance(value, dict) or set(value) != {"id", "payload"}:
            raise ValueError("Pedido inválido.")
        identifier = protocol.request_id(value["id"])
        payload = protocol.payload(value["payload"])
        digest = hashlib.sha256(protocol.encode(payload)).hexdigest()
        with self.lock:
            if self.closing:
                raise RuntimeError("Executor encerrando.")
            self.prune()
            if identifier in self.jobs:
                if self.jobs[identifier]["digest"] != digest:
                    raise ValueError("Id já utilizado com outro pedido.")
                return self.get(identifier)
            if self.pending.full():
                raise RuntimeError("Fila do PC2 cheia; nenhum pedido novo foi aceito.")
            at = time.time()
            self.jobs[identifier] = {"id": identifier, "digest": digest, "payload": payload, "status": "queued",
                    "cancel": threading.Event(), "result": None, "error": None, "created_at": at, "updated_at": at}
            self.pending.put(identifier, block=False)
            return self.get(identifier)

    def get(self, identifier):
        protocol.request_id(identifier)
        with self.lock:
            if identifier not in self.jobs:
                raise KeyError("Pedido não encontrado ou cache expirado.")
            return copy.deepcopy({k: self.jobs[identifier][k] for k in ("id", "status", "result", "error", "created_at", "updated_at")})

    def cancel(self, identifier):
        self.get(identifier)
        with self.lock:
            job = self.jobs[identifier]
            if job["status"] not in {"queued", "running"}:
                return self.get(identifier)
            job["cancel"].set()
            removed = self.pending.discard(lambda item: item == identifier)
            if removed:
                job.update(status="interrupted", payload=None, error="Cancelado na fila.", updated_at=time.time())
            running = job["status"] == "running"
        if running:
            self.engine.close()  # Daemon/grupo próprios; nunca fecha o Ollama de outro programa.
        return self.get(identifier)

    def health(self):
        with self.lock:
            samples = list(self.samples)
            pending = self.pending.qsize()
            running = sum(j["status"] == "running" for j in self.jobs.values())
        return {"version": protocol.VERSION, "executor": "athlon", "entity": "alistair", "capabilities": ["llm"],
                "model": protocol.MODEL, "num_ctx": protocol.MAX_CONTEXT, "num_predict": protocol.MAX_TOKENS,
                "threads": 2, "parallelism": 1, "queue": pending, "active": running,
                "memory": self.mem_probe(), "engine": self.engine.info(), "observed_at": time.time(),
                "samples": samples, "mind_home": "pc_principal", "executes_tools": False}

    def run(self):
        while True:
            identifier = self.pending.get()
            if identifier is None:
                self.pending.task_done()
                return
            with self.lock:
                job = self.jobs[identifier]
                job.update(status="running", updated_at=time.time())
            began = time.monotonic()
            try:
                if job["cancel"].is_set():
                    raise RuntimeError("Cancelado antes de iniciar.")
                state = self.engine.info()
                available = self.mem_probe().get("available_bytes")
                required = (1 if state.get("warm") else 5) * 1024 ** 3
                if available is None or available < required:
                    raise RuntimeError("RAM disponível insuficiente/não observada; inferência não iniciada.")
                answer = self.engine.infer(job["payload"], job["cancel"])
                message = answer.get("message") if isinstance(answer, dict) else None
                if not isinstance(message, dict) or message.get("role") != "assistant" or not (message.get("content") or message.get("tool_calls")):
                    raise RuntimeError("Motor não produziu resposta final/ações válidas.")
                if len(protocol.encode(answer)) > protocol.MAX_RESPONSE:
                    raise RuntimeError("Resposta fora do limite.")
                duration = round(time.monotonic() - began, 3)
                with self.lock:
                    if job["cancel"].is_set():
                        raise RuntimeError("Resposta descartada após cancelamento.")
                    job.update(status="done", result=answer, updated_at=time.time())
                    self.samples.append({"seconds": duration, "observed_at": time.time(),
                                         "eval_count": answer.get("eval_count"), "includes_queue_and_load": False})
            except Exception as exc:
                with self.lock:
                    job.update(status="interrupted" if job["cancel"].is_set() else "error", error=str(exc)[:300], updated_at=time.time())
            finally:
                with self.lock:
                    job["payload"] = None  # Prompts só existem em RAM durante fila/inferência.
                self.pending.task_done()

    def close(self):
        with self.lock:
            self.closing = True
            identifiers = list(self.jobs)
        for identifier in identifiers:
            self.cancel(identifier)
        self.pending.join()
        if self.thread.is_alive():
            self.pending.put(None)
            self.thread.join(10)
        self.engine.close()


def make_server(node, address="127.0.0.1", port=8770):
    address = protocol.lan_ip(address)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # Nenhum prompt, chave ou corpo de pedido em log.

        def reply(self, code, value):
            body = protocol.encode(value)
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def route(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= protocol.MAX_BODY or self.headers.get("Transfer-Encoding"):
                    self.reply(413, {"error": "Pedido excede o limite."})
                    return
                body = self.rfile.read(size)
                try:
                    node.authorize(self.client_address[0], self.command, self.path, self.headers, body)
                except ValueError:
                    self.reply(403, {"error": "Assinatura/origem inválida; confira a chave e o relógio dos PCs."})
                    return
                url = urlsplit(self.path)
                if self.command == "GET" and url.path == "/api/health":
                    self.reply(200, node.health())
                elif self.command == "GET" and url.path == "/api/job":
                    self.reply(200, node.get(parse_qs(url.query).get("id", [""])[0]))
                elif self.command == "POST" and url.path == "/api/infer":
                    self.reply(202, node.submit(json.loads(body)))
                elif self.command == "POST" and url.path == "/api/cancel":
                    self.reply(200, node.cancel(json.loads(body).get("id", "")))
                else:
                    self.reply(404, {"error": "Não há execução de comandos/arquivos/ferramentas neste executor."})
            except (ValueError, TypeError):
                self.reply(400, {"error": "Pedido fora do contrato ou id conflitante."})
            except KeyError:
                self.reply(404, {"error": "Pedido desconhecido/expirado."})
            except RuntimeError as exc:
                self.reply(503, {"error": str(exc)[:300]})
            except Exception:
                self.reply(500, {"error": "Falha não confirmada; consulte estado pelo id antes de repetir."})

        do_GET = route
        do_POST = route

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        block_on_close = False
        def __init__(self, *args):
            self.slots = threading.BoundedSemaphore(8)
            super().__init__(*args)

        def process_request(self, request, address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, address)
            except BaseException:
                self.slots.release()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                self.slots.release()
    return Server((address, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="worker.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    settings = json.loads((root / args.config).read_text())
    if settings.get("configured") is not True:
        raise SystemExit("Execute configurar_pc2.py antes de iniciar. Nenhum servidor foi exposto.")
    secret_path = root / settings["token_file"]
    if secret_path.stat().st_mode & 0o077:
        raise SystemExit("A chave LAN deve ser privada (permissão 600).")
    secret = bytes.fromhex(secret_path.read_text().strip())
    protocol.lan_ip(settings["bind"])
    if not settings.get("allowed_clients") or len(secret) != 32:
        raise SystemExit("Configuração LAN incompleta.")
    for client in settings["allowed_clients"]:
        protocol.lan_ip(client)
    engine = Engine(root, settings)
    node = server = None
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        engine.start()
        node = Node(engine, secret, allowed_clients=settings["allowed_clients"])
        server = make_server(node, settings["bind"], settings.get("port", 8770))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print("Executor de Alistair ativo. Memória e ferramentas continuam no PC principal.", flush=True)
        while not stop.wait(1):
            pass
    finally:
        if server:
            server.shutdown()
        if node:
            node.close()
        else:
            engine.close()
        if server:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
