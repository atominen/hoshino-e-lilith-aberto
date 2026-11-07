"""Contrato stdlib do executor LAN. Não importa mente, config ou ferramentas."""
import hashlib
import hmac
import ipaddress
import json
import math
import re
import time
import uuid

VERSION = 1
MODEL = "alistair-qwen3.5-4b:latest"
MAX_BODY = 512 * 1024
MAX_RESPONSE = 1024 * 1024
MAX_CONTEXT = 4096
MAX_TOKENS = 768
_LAN = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")]


def lan_ip(value):
    address = ipaddress.ip_address(value)
    if address.version != 4 or not any(address in network for network in _LAN):
        raise ValueError("Use um IPv4 da LAN ou loopback; não exponha o executor à Internet.")
    if address.is_unspecified or address.is_multicast or str(address).endswith(".255"):
        raise ValueError("Endereço de execução inválido.")
    return str(address)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def signature(secret, method, target, timestamp, nonce, body):
    content = "\n".join((method, target, str(timestamp), nonce, hashlib.sha256(body).hexdigest())).encode()
    return hmac.new(secret, content, hashlib.sha256).hexdigest()


def auth_headers(secret, method, target, body=b"", *, now=None, nonce=None):
    timestamp = str(int(time.time() if now is None else now))
    nonce = nonce or uuid.uuid4().hex
    return {"X-Alistair-Time": timestamp, "X-Alistair-Nonce": nonce,
            "X-Alistair-Signature": signature(secret, method, target, timestamp, nonce, body),
            "Content-Type": "application/json"}


def verify(secret, method, target, headers, body, *, now=None):
    now = time.time() if now is None else now
    stamp, nonce = headers.get("X-Alistair-Time", ""), headers.get("X-Alistair-Nonce", "")
    try:
        timestamp = int(stamp)
    except (ValueError, TypeError):
        raise ValueError("Assinatura ou relógio inválido.") from None
    if abs(now - timestamp) > 60 or not re.fullmatch(r"[a-f0-9]{32}", nonce):
        raise ValueError("Assinatura vencida ou nonce inválido.")
    expected = signature(secret, method, target, stamp, nonce, body)
    if not hmac.compare_digest(expected, headers.get("X-Alistair-Signature", "")):
        raise ValueError("Assinatura inválida.")
    return nonce


def request_id(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,160}", identifier):
        raise ValueError("Identificador inválido.")
    return identifier


def payload(value, threads=2):
    if not isinstance(value, dict) or len(encode(value)) > MAX_BODY:
        raise ValueError("Pedido fora do contrato.")
    allowed = {"model", "messages", "tools", "stream", "think", "keep_alive", "options"}
    if set(value) - allowed or value.get("model") != MODEL or value.get("stream", False) is not False or value.get("think", False) is not False:
        raise ValueError("Só inferência textual de Alistair, sem streaming ou outro modelo.")
    messages = value.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
        raise ValueError("Lista de mensagens inválida.")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Papel de mensagem inválido.")
        if set(message) - {"role", "content", "tool_name", "tool_calls", "thinking"}:
            raise ValueError("Mensagem deve ser textual; imagens/áudio não são aceitos.")
        for field in ("content", "tool_name", "thinking"):
            if field in message and (not isinstance(message[field], str) or len(message[field]) > 65536):
                raise ValueError("Conteúdo de mensagem inválido.")
        calls = message.get("tool_calls", [])
        if not isinstance(calls, list) or len(calls) > 16:
            raise ValueError("Lista de ações inválida.")
    tools = value.get("tools", [])
    if not isinstance(tools, list) or len(tools) > 16 or any(not isinstance(tool, dict) for tool in tools):
        raise ValueError("Contratos de ferramentas inválidos.")
    options = value.get("options", {})
    if not isinstance(options, dict) or set(options) - {"num_ctx", "num_predict", "num_thread", "num_gpu", "temperature"}:
        raise ValueError("Opções desconhecidas.")
    for field, default, lower, upper in (("num_ctx", MAX_CONTEXT, 512, MAX_CONTEXT), ("num_predict", MAX_TOKENS, 1, MAX_TOKENS)):
        number = options.get(field, default)
        if type(number) is not int or not lower <= number <= upper:
            raise ValueError(f"{field} excede o contrato; não foi reduzido silenciosamente.")
    if type(options.get("num_gpu", 0)) is not int or options.get("num_gpu", 0) != 0:
        raise ValueError("PC2 usa exclusivamente CPU.")
    temperature = options.get("temperature", .45)
    if type(temperature) not in (float, int) or not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError("Temperatura inválida.")
    # Threads e residência são política de execução, não alteração do texto/contexto.
    return {**value, "stream": False, "think": False, "keep_alive": "10m",
            "options": {**options, "num_ctx": options.get("num_ctx", MAX_CONTEXT),
                        "num_predict": options.get("num_predict", MAX_TOKENS), "num_thread": threads, "num_gpu": 0}}
