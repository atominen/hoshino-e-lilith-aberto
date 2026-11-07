"""Intermediário de 2B (29/10, pedido humano): um "if inteligente" na CPU, só onde a regra não alcança.

Hoje faz uma coisa: dizer se a anotação nova de uma entidade SÓ REPETE conclusão/plano das anteriores (pensamento
em círculo). Avaliado com notas reais da Lilith: regra 0/27, 2B com exemplos ~21–23/25 com 1–2 alarmes falsos
(compartilhado/runtime/ensaios/intermediario-20261029/). Por isso o aviso é suave e mostra a prova, e travas por
regra (erro do compilador mudou, arquivo alterado) vêm antes do modelo. Nunca planeja, decide ou fala pela entidade.

Roda numa instância Ollama própria, só CPU (sem VRAM da entidade), subida pela própria entidade no boot quando
HOSHINO_INTERMEDIARIO_URL está configurado. Qualquer falha devolve None: as regras continuam valendo sozinhas.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from urllib.parse import urlsplit

import config

EXEMPLOS = (
    "Exemplo A (só repete):\nAnteriores: [1] A porta não abre porque falta a chave vermelha; preciso procurar no "
    "porão.\nNova: Já sei que a porta precisa da chave vermelha, vou procurar no porão.\n→ so_repete=true\n\n"
    "Exemplo B (traz novidade):\nAnteriores: [1] A porta não abre porque falta a chave vermelha; preciso procurar "
    "no porão.\nNova: Achei a chave no porão, mas ela é azul; a porta continua trancada e mostra um código 4-7.\n"
    "→ so_repete=false\n")
SISTEMA_REPETICAO = (
    "Você ajuda uma programadora a perceber quando ela está andando em círculos. Diga se a anotação nova SÓ "
    "REPETE uma conclusão ou um plano já presente nas anteriores (mesmo com outras palavras), sem fato novo. "
    "Fato novo do compilador, nova causa ou novo resultado conta como novidade.\n\n" + EXEMPLOS)

# 30/10: no Minecraft os comentários vinham vazios e a mesma tentativa variava só nos argumentos (4 colocações
# recusadas perto do spawn, coordenadas diferentes): a regra de chamada idêntica não pega e não havia texto para
# comparar. Cada registro leva a anotação (pode estar vazia), a ação e o resultado observado.
EXEMPLOS_TENTATIVA = (
    "Exemplo A (só repete):\nAnteriores: [1] anotação: (vazia) | ação: abrir_porta {\"porta\": \"norte\"} | "
    "resultado (recusado): trancada, falta a chave vermelha\nNova: anotação: vou tentar com mais força | ação: "
    "abrir_porta {\"porta\": \"norte\", \"forca\": 10} | resultado (recusado): trancada, falta a chave vermelha\n"
    "→ so_repete=true\n\n"
    "Exemplo B (traz novidade):\nAnteriores: [1] anotação: (vazia) | ação: abrir_porta {\"porta\": \"norte\"} | "
    "resultado (recusado): trancada, falta a chave vermelha\nNova: anotação: preciso da chave | ação: "
    "procurar {\"lugar\": \"porão\"} | resultado (sucesso): achou a chave vermelha\n→ so_repete=false\n")
SISTEMA_TENTATIVA = (
    "Você ajuda uma agente a perceber quando está tentando a mesma coisa sem mudar nada. Cada registro tem a "
    "anotação dela (pode estar vazia), a ação e o resultado observado. Diga se a tentativa nova SÓ REPETE a "
    "abordagem de uma anterior que não avançou, com o mesmo resultado ou o mesmo motivo de recusa, sem fato novo "
    "(outros argumentos com o mesmo motivo de falha contam como repetição). Agir sobre a causa da falha, outra "
    "ação com outro objetivo ou um resultado novo contam como novidade.\n\n" + EXEMPLOS_TENTATIVA)


def ativo() -> bool:
    return bool(config.INTERMEDIARIO_URL)


def _porta_aberta(url: str) -> bool:
    partes = urlsplit(url)
    try:
        with socket.create_connection((partes.hostname, partes.port or 80), timeout=0.4):
            return True
    except OSError:
        return False


def iniciar() -> str:
    """Sobe a instância só CPU do intermediário se ela não estiver no ar (idempotente; não mata nada).
    Nunca levanta exceção: o intermediário é opcional e não pode impedir a entidade de iniciar."""
    try:
        return _iniciar()
    except Exception as exc:  # noqa: BLE001
        return f"intermediário não iniciado: {type(exc).__name__}: {exc}"


def _iniciar() -> str:
    if not ativo():
        return "intermediário desligado"
    if _porta_aberta(config.INTERMEDIARIO_URL):
        return "intermediário já no ar"
    executavel = shutil.which("ollama")
    if not executavel or not os.path.isdir(config.INTERMEDIARIO_MODELOS_DIR):
        return "intermediário indisponível (ollama ou pasta do modelo ausente)"
    log_dir = os.path.join(config.SHARED_RUNTIME_DIR, "ollama", "intermediario")
    os.makedirs(log_dir, exist_ok=True)
    partes = urlsplit(config.INTERMEDIARIO_URL)
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith(("OLLAMA_", "LLAMA_ARG_"))}
    ambiente.update(OLLAMA_HOST=f"{partes.hostname}:{partes.port}", OLLAMA_MODELS=config.INTERMEDIARIO_MODELOS_DIR,
                    OLLAMA_NOPRUNE="1", OLLAMA_VULKAN="0",
                    # Só CPU: a VRAM é da entidade.
                    ROCR_VISIBLE_DEVICES="-1", HIP_VISIBLE_DEVICES="-1", GGML_VK_VISIBLE_DEVICES="-1",
                    CUDA_VISIBLE_DEVICES="-1")
    with open(os.path.join(log_dir, "server.log"), "a", encoding="utf-8") as log:
        processo = subprocess.Popen([executavel, "serve"], stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, env=ambiente, start_new_session=True, close_fds=True)
    return f"intermediário iniciado (pid={processo.pid}, só CPU)"


# 30/10 (revisão Codex): estouros de tempo seguidos pausam o intermediário por um tempo, em vez de cada decisão
# esperar o timeout de novo; a próxima consulta depois da pausa tenta outra vez. Recusa de conexão e resposta fora
# do formato são instantâneas e não pausam.
_FALHAS_PARA_PAUSAR = 3
_PAUSA_S = 300.0
_falhas_seguidas = 0
_pausado_ate = 0.0


def _chat(sistema: str, usuario: str, esquema: dict, timeout: float, num_predict: int = 40,
          info: dict | None = None) -> dict | None:
    body = {"model": config.INTERMEDIARIO_MODELO, "stream": False, "think": False, "format": esquema,
            "keep_alive": "30m", "messages": [{"role": "system", "content": sistema},
                                              {"role": "user", "content": usuario}],
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": num_predict, "num_gpu": 0}}
    try:
        pedido = urllib.request.Request(config.INTERMEDIARIO_URL.rstrip("/") + "/api/chat", json.dumps(body).encode(),
                                        {"Content-Type": "application/json"})
        with urllib.request.urlopen(pedido, timeout=timeout) as r:
            envelope = json.load(r)
        if info is not None:
            info.update({k: envelope.get(k) for k in ("done_reason", "eval_count", "prompt_eval_count")})
        return json.loads(envelope["message"]["content"] or "{}")
    except Exception as exc:  # noqa: BLE001 — fora do ar, lento ou resposta quebrada: sem aviso, as regras seguem
        if info is not None:
            # URLError traz a causa em .reason (às vezes só texto); HTTPError traz o status em .code.
            motivo = getattr(exc, "reason", None)
            info["falha"] = type(motivo if isinstance(motivo, BaseException) else exc).__name__
            if isinstance(getattr(exc, "code", None), int):
                info["http_status"] = exc.code
        return None


def _so_repete(tipo: str, sistema: str, texto: str, timeout: float | None) -> bool | None:
    global _falhas_seguidas, _pausado_ate
    inicio = time.monotonic()
    if inicio < _pausado_ate:
        return None
    info: dict = {}
    r = _chat(sistema, texto, {"type": "object", "properties": {"so_repete": {"type": "boolean"}},
                               "required": ["so_repete"]},
              timeout if timeout is not None else config.INTERMEDIARIO_TIMEOUT, info=info)
    # Revisão Codex 29/10: 'true', '42' ou {"so_repete": "false"} não podem virar exceção nem aviso.
    resposta = r["so_repete"] if isinstance(r, dict) and isinstance(r.get("so_repete"), bool) else None
    if resposta is None:
        info.setdefault("falha", "resposta_fora_do_formato")
    if info.get("falha") in ("TimeoutError", "timeout"):
        _falhas_seguidas += 1
        if _falhas_seguidas >= _FALHAS_PARA_PAUSAR:
            _pausado_ate, _falhas_seguidas = time.monotonic() + _PAUSA_S, 0
            info["pausado_s"] = _PAUSA_S
    else:
        _falhas_seguidas = 0
    try:  # 30/10: cada consulta fica medida (sem isto não dava para saber se o intermediário ajuda)
        from core import diagnostics
        diagnostics.emit("intermediario.consulta", tipo=tipo, modelo=config.INTERMEDIARIO_MODELO, resposta=resposta,
                         elapsed_ms=int((time.monotonic() - inicio) * 1000), texto_chars=len(texto), **info)
    except Exception:  # noqa: BLE001
        pass
    return resposta


def repeticao(anteriores: list[str], nova: str, timeout: float | None = None) -> bool | None:
    """True se a nota nova só repete as anteriores; None se não deu para saber."""
    if not ativo() or not anteriores or not nova.strip():
        return None
    texto = ("Anotações anteriores:\n" + "\n".join(f"[{i + 1}] {a[:600]}" for i, a in enumerate(anteriores))
             + f"\n\nAnotação nova:\n{nova[:600]}")
    return _so_repete("nota", SISTEMA_REPETICAO, texto, timeout)


def descrever_tentativa(evento: dict) -> str:
    """Anotação + ação + resultado de um evento do Minecraft, numa linha curta (o motivo da recusa costuma estar no
    fim da saída: guarda começo e fim)."""
    args = json.dumps(evento.get("arguments") or {}, ensure_ascii=False, sort_keys=True)[:200]
    saida = " ".join(str(evento.get("output") or "").split())
    if len(saida) > 320:
        saida = saida[:150] + " … " + saida[-170:]
    nota = " ".join(str(evento.get("comment") or "").split())[:300]
    return (f"anotação: {nota or '(vazia)'} | ação: {evento.get('tool')} {args} | "
            f"resultado ({evento.get('status')}): {saida}")


def tentativa_repetida(anteriores: list[str], nova: str, timeout: float | None = None) -> bool | None:
    """True se a tentativa nova (descrever_tentativa) só repete a abordagem de uma anterior sem avanço."""
    if not ativo() or not anteriores or not nova.strip():
        return None
    texto = ("Tentativas anteriores:\n" + "\n".join(f"[{i + 1}] {a[:1000]}" for i, a in enumerate(anteriores))
             + f"\n\nTentativa nova:\n{nova[:1000]}")
    return _so_repete("tentativa", SISTEMA_TENTATIVA, texto, timeout)


def aviso_minecraft(cp: dict) -> str | None:
    """Minecraft (29/10): só depois de 2+ decisões seguidas sem progresso observado (cp['no_progress'], regra do
    próprio ciclo) compara a tentativa mais recente (anotação + ação + resultado, 30/10) com as anteriores desse
    trecho. Os reflexos de sobrevivência continuam por regra (minecraft_cognition); isto não decide nem age, só
    mostra a prova."""
    try:
        if not ativo() or not config.INTERMEDIARIO_MINECRAFT:
            return None
        sem_progresso = int(cp.get("no_progress") or 0)
        eventos = cp.get("events") or []
        trecho = [descrever_tentativa(e) for e in eventos[-sem_progresso:] if e.get("tool")] if sem_progresso else []
        # Chave pelo conteúdo (29/10: com a lista de eventos cheia em 128, a chave por tamanho repetia e o 2B
        # não era consultado num trecho novo; ao vivo ele dizia "repete" e o aviso não aparecia).
        import hashlib
        chave = hashlib.sha256(json.dumps([sem_progresso, trecho], ensure_ascii=False).encode()).hexdigest()[:16]
        cache = cp.get("intermediario_mc") or {}
        if cache.get("chave") == chave:
            return cache.get("aviso")
        aviso = None
        if sem_progresso >= 2:
            if len(trecho) >= 2:
                nova, anteriores = trecho[-1], trecho[:-1][-4:]
                julgamento = tentativa_repetida(anteriores, nova)
                if julgamento is None:
                    return None  # falha não é avaliação: sem cache, a próxima decisão tenta de novo
                if julgamento:
                    import difflib
                    parecida = max(anteriores, key=lambda a: difflib.SequenceMatcher(
                        None, nova[:400].lower(), a[:400].lower()).ratio())
                    # O modelo só diz sim/não; a tentativa citada é a mais parecida pelo texto (regra), e o aviso
                    # diz isso em vez de apresentá-la como a prova do modelo (revisão Codex 30/10).
                    aviso = (f"O intermediário acha que sua última tentativa só repete a abordagem de uma anterior "
                             f"deste trecho de {sem_progresso} decisões sem progresso. A mais parecida pelo texto: "
                             f"\"{parecida[:260]}\". Se há algo novo, ignore este aviso.")
                    try:
                        from core import diagnostics
                        diagnostics.emit("intermediario.aviso", ambiente="minecraft", sem_progresso=sem_progresso,
                                         tentativa=nova[:300])
                    except Exception:  # noqa: BLE001
                        pass
        cp["intermediario_mc"] = {"chave": chave, "sem_progresso": sem_progresso, "aviso": aviso}
        return aviso
    except Exception:  # noqa: BLE001 — opcional: nunca derruba a decisão
        return None


def descarregar() -> None:
    """Libera a RAM do modelo ao dormir (o processo fica, como a instância da entidade)."""
    if ativo() and _porta_aberta(config.INTERMEDIARIO_URL):
        try:
            pedido = urllib.request.Request(config.INTERMEDIARIO_URL.rstrip("/") + "/api/generate",
                                            json.dumps({"model": config.INTERMEDIARIO_MODELO, "keep_alive": 0}).encode(),
                                            {"Content-Type": "application/json"})
            urllib.request.urlopen(pedido, timeout=5).close()
        except Exception:  # noqa: BLE001
            pass
