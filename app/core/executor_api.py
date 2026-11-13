"""Executor por API (pedido humano, 07/11/2026): "o projeto também deve aceitar API" e "uma parte que deixa o usuário
adicionar, remover, alterar e quem usa qual API".

Opcional e desligado por padrão. Cada entidade usa o modelo local (Ollama) ou uma das APIs cadastradas na Central (aba
Modelos). Com API, as chamadas vão para uma API compatível com a da OpenAI, sem reservar a GPU. Entrada e saída ficam
no formato do Ollama, então o resto do ciclo (ferramentas, travas, revisor) não muda. Falhou (cota, rede, erro):
quem chama volta para o modelo local. A escolha vale na hora, sem reiniciar.

- Cadastro e escolha: compartilhado/config/executor_api.json
  {"apis": {"gemini-1": {"nome": "Gemini", "provedor": "gemini", "modelo": "gemini-flash-latest"}},
   "entidades": {"lilith": "gemini-1"}}
- Chaves: compartilhado/config/teste_api.env, uma linha por API (APIKEY_GEMINI_1=...). Nunca voltam para a tela.
  Compatível com GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY salvas à mão.
- Privacidade: com API ligada, conversas e memórias daquela entidade saem do PC. No plano gratuito do Gemini, o
  Google pode usar o conteúdo. Por isso só liga por escolha humana, entidade por entidade.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import config

ARQUIVO_ESCOLHA = Path(config.RAIZ) / "compartilhado" / "config" / "executor_api.json"
ARQUIVO_CHAVE = Path(config.RAIZ) / "compartilhado" / "config" / "teste_api.env"
ENTIDADES = ("hoshino", "lilith", "alistair")
PROVEDORES = {
    "gemini": dict(rotulo="Google Gemini (AI Studio)",
                   url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                   chave="GEMINI_API_KEY", modelo="gemini-flash-latest", intervalo=6.5),
    "groq": dict(rotulo="Groq", url="https://api.groq.com/openai/v1/chat/completions",
                 chave="GROQ_API_KEY", modelo="openai/gpt-oss-120b", intervalo=2.5),
    "openrouter": dict(rotulo="OpenRouter", url="https://openrouter.ai/api/v1/chat/completions",
                       chave="OPENROUTER_API_KEY", modelo="", intervalo=3.5),
    "personalizado": dict(rotulo="Outra (compatível com OpenAI)", url="", chave="", modelo="", intervalo=1.0),
}
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class APIIndisponivel(RuntimeError):
    """A API não respondeu como devia; quem chama volta para o modelo local."""


# ------------------------------------------------------------------ cadastro (lido a cada uso: vale na hora)
def carregar(arquivo: Path | None = None) -> dict:
    """Cadastro normalizado {"apis": {...}, "entidades": {...}}. Arquivo ausente ou inválido = nada cadastrado."""
    try:
        dados = json.loads((arquivo or ARQUIVO_ESCOLHA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    apis = {}
    for ident, api in (dados.get("apis") or {}).items() if isinstance(dados, dict) else ():
        if isinstance(api, dict) and _ID.match(str(ident)) and api.get("provedor") in PROVEDORES:
            apis[ident] = dict(nome=str(api.get("nome") or ident)[:60], provedor=api["provedor"],
                               url=str(api.get("url") or "")[:300], modelo=str(api.get("modelo") or "")[:120])
    entidades = {e: (dados.get("entidades") or {}).get(e) if isinstance(dados, dict) else None for e in ENTIDADES}
    entidades = {e: (i if i in apis else None) for e, i in entidades.items()}
    return dict(apis=apis, entidades=entidades)


def gravar(cadastro: dict, arquivo: Path | None = None) -> None:
    alvo = arquivo or ARQUIVO_ESCOLHA
    alvo.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".executor_api.", dir=str(alvo.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dict(apis=cadastro["apis"], entidades=cadastro["entidades"]), f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, alvo)


def url_de(api: dict) -> str:
    return api.get("url") or PROVEDORES[api["provedor"]]["url"]


def modelo_de(api: dict) -> str:
    return api.get("modelo") or PROVEDORES[api["provedor"]]["modelo"]


def escolha(entidade: str | None = None, arquivo: Path | None = None) -> dict:
    """API que a entidade usa ({} = modelo local). Nunca levanta exceção."""
    cadastro = carregar(arquivo)
    ident = cadastro["entidades"].get(entidade or config.ENTIDADE_ID)
    api = cadastro["apis"].get(ident) if ident else None
    if not api or not url_de(api) or not modelo_de(api):
        return {}
    return dict(id=ident, nome=api["nome"], provedor=api["provedor"], url=url_de(api), modelo=modelo_de(api))


def ativo(entidade: str | None = None) -> bool:
    return bool(escolha(entidade))


# ------------------------------------------------------------------ chaves (só gravar; nunca mostrar)
def _var(ident: str) -> str:
    return "APIKEY_" + re.sub(r"[^A-Z0-9]", "_", ident.upper())


def _linhas(arquivo: Path) -> list[str]:
    try:
        return arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _ler_var(nome: str, arquivo: Path) -> str:
    if not nome:
        return ""
    if os.environ.get(nome):
        return os.environ[nome].strip()
    for linha in _linhas(arquivo):
        if linha.strip().startswith(nome + "="):
            return linha.split("=", 1)[1].strip().strip("\"'")
    return ""


def chave_de(ident: str, provedor: str, arquivo: Path | None = None) -> str:
    """Chave da API: a própria (APIKEY_<ID>) ou, se não houver, a do provedor salva à mão (GEMINI_API_KEY...)."""
    arquivo = arquivo or ARQUIVO_CHAVE
    return _ler_var(_var(ident), arquivo) or _ler_var(PROVEDORES[provedor]["chave"], arquivo)


def guardar_chave(ident: str, chave: str | None, arquivo: Path | None = None) -> None:
    """Grava (ou, com None, remove) a chave da API. Arquivo só do usuário (600)."""
    arquivo = arquivo or ARQUIVO_CHAVE
    nome = _var(ident)
    linhas = [l for l in _linhas(arquivo) if not l.strip().startswith(nome + "=")]
    if chave:
        if re.search(r"\s", chave) or len(chave) > 400:
            raise ValueError("Chave inválida (tem espaço ou é longa demais).")
        linhas.append(f"{nome}={chave}")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".chaves.", dir=str(arquivo.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + ("\n" if linhas else ""))
    os.chmod(tmp, 0o600)
    os.replace(tmp, arquivo)


# ------------------------------------------------------------------ formato Ollama ⇄ OpenAI
def para_openai(mensagens: list[dict]) -> list[dict]:
    """Mensagens no formato do Ollama → formato OpenAI (ids das chamadas de ferramenta casados em ordem)."""
    saida, pendentes, contador = [], [], 0
    for m in mensagens:
        papel = m.get("role")
        if papel == "assistant" and m.get("tool_calls"):
            chamadas = []
            for ch in m["tool_calls"]:
                f = ch.get("function") or {}
                contador += 1
                ident = ch.get("id") or f"call_{contador}"
                args = f.get("arguments")
                chamada = {"id": ident, "type": "function", "function": {
                    "name": f.get("name", ""),
                    "arguments": args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False)}}
                if ch.get("extra_content"):  # 08/11: a assinatura de pensamento do Gemini volta junto (senão: HTTP 400)
                    chamada["extra_content"] = ch["extra_content"]
                chamadas.append(chamada)
                pendentes.append((ident, f.get("name", "")))
            saida.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": chamadas})
        elif papel == "tool":
            nome = m.get("tool_name") or m.get("name") or ""
            idx = next((i for i, (_, n) in enumerate(pendentes) if n == nome), 0 if pendentes else None)
            ident = pendentes.pop(idx)[0] if idx is not None else f"call_orfa_{contador}"
            saida.append({"role": "tool", "tool_call_id": ident, "content": str(m.get("content") or "")})
        else:
            saida.append({"role": papel or "user", "content": str(m.get("content") or "")})
    return saida


def do_openai(mensagem: dict) -> dict:
    """Resposta OpenAI → mensagem no formato do Ollama (argumentos como dicionário)."""
    chamadas = []
    for ch in mensagem.get("tool_calls") or []:
        f = ch.get("function") or {}
        try:
            args = json.loads(f.get("arguments") or "{}")
        except (TypeError, ValueError):
            args = {}
        chamada = {"function": {"name": f.get("name", ""), "arguments": args}}
        # 08/11 (prova de teto): o Gemini exige que a assinatura de pensamento (extra_content.google.thought_signature)
        # volte no passo seguinte, junto do resultado da ferramenta; sem ela: "Function call is missing a thought_signature".
        if ch.get("id"):
            chamada["id"] = ch["id"]
        if ch.get("extra_content"):
            chamada["extra_content"] = ch["extra_content"]
        chamadas.append(chamada)
    out = {"role": "assistant", "content": mensagem.get("content") or ""}
    if chamadas:
        out["tool_calls"] = chamadas
    return out


# ------------------------------------------------------------------ chamada
class Cliente:
    def __init__(self, provedor: str = "gemini", modelo: str | None = None, *, url: str | None = None,
                 ident: str | None = None, arquivo_chave: Path | None = None):
        self.cfg = dict(PROVEDORES[provedor])
        self.provedor = provedor
        self.modelo = modelo or self.cfg["modelo"]
        self.url = url or self.cfg["url"]
        self.ident = ident or provedor
        self.arquivo_chave = arquivo_chave
        self.trava = threading.Lock()
        self.ultimo = 0.0
        if not self.url or not self.modelo:
            raise APIIndisponivel("API sem endereço ou sem modelo")

    def pedido(self, corpo: dict) -> dict:
        pedido = {"model": self.modelo, "messages": para_openai(corpo.get("messages") or [])}
        if corpo.get("tools"):
            pedido["tools"] = corpo["tools"]
        formato = corpo.get("format")
        if isinstance(formato, dict):
            pedido["response_format"] = {"type": "json_schema", "json_schema": {"name": "saida", "schema": formato}}
        elif formato == "json":
            pedido["response_format"] = {"type": "json_object"}
        opcoes = corpo.get("options") or {}
        for de in ("temperature", "top_p"):
            if de in opcoes:
                pedido[de] = opcoes[de]
        if opcoes.get("num_predict"):
            pedido["max_tokens"] = int(opcoes["num_predict"]) + 2048  # o modelo externo pode pensar antes
        return pedido

    def chat(self, corpo: dict, *, tentativas: int = 4, limite_s: float = 180.0) -> dict:
        """Uma chamada no formato do Ollama. Devolve a ``message``; falha vira ``APIIndisponivel``."""
        chave = chave_de(self.ident, self.provedor, self.arquivo_chave)  # lida a cada vez: troca vale na hora
        if not chave and self.provedor != "personalizado":
            raise APIIndisponivel("API sem chave salva")
        dados = json.dumps(self.pedido(corpo), ensure_ascii=False).encode()
        cabecalho = {"Content-Type": "application/json"}
        if chave:
            cabecalho["Authorization"] = "Bearer " + chave
        espera = 8.0
        for tentativa in range(tentativas):
            with self.trava:  # respeita o limite por minuto do plano gratuito
                falta = float(self.cfg["intervalo"]) - (time.monotonic() - self.ultimo)
                if falta > 0:
                    time.sleep(falta)
                self.ultimo = time.monotonic()
            try:
                with urllib.request.urlopen(urllib.request.Request(self.url, dados, cabecalho), timeout=limite_s) as r:
                    resposta = json.load(r)
                return do_openai(resposta["choices"][0]["message"])
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503) and tentativa + 1 < tentativas:
                    time.sleep(float(exc.headers.get("Retry-After") or espera))
                    espera *= 2
                    continue
                raise APIIndisponivel(f"HTTP {exc.code}: {exc.read(300).decode('utf-8', 'replace')}") from None
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, ValueError) as exc:
                raise APIIndisponivel(f"{type(exc).__name__}: {str(exc)[:200]}") from None
        raise APIIndisponivel("sem resposta depois das tentativas")


LIMITE_ENTIDADE_S = 40.0
# 07/11 (teste real): modelo aposentado (404) era tentado de novo a cada chamada. Erro permanente pausa a API por
# alguns minutos; a última situação de cada API fica num arquivo que a Central mostra na lista.
PAUSA_ERRO_PERMANENTE_S = 600.0
ARQUIVO_SITUACAO = Path(config.RAIZ) / "compartilhado" / "runtime" / "executor_api_situacao.json"
_PAUSAS: dict[str, tuple[float, str]] = {}
_CLIENTES: dict[tuple, Cliente] = {}
_TRAVA = threading.Lock()


def chat(payload: dict, entidade: str | None = None) -> dict:
    """Chamada da entidade pela API escolhida para ela. Levanta ``APIIndisponivel`` se não der."""
    e = escolha(entidade)
    if not e:
        raise APIIndisponivel("esta entidade usa o modelo local")
    with _TRAVA:
        chave = (e["id"], e["provedor"], e["url"], e["modelo"])
        cliente = _CLIENTES.get(chave)
        if cliente is None:
            cliente = _CLIENTES[chave] = Cliente(e["provedor"], e["modelo"], url=e["url"], ident=e["id"])
    # 07/11 (teste real): com 180 s e nova tentativa, a chamada da Lilith ficou presa mais de 3 minutos; ela não saiu ao
    # dormir e o encerramento da Central ficou bloqueado. Na entidade: uma tentativa, 40 s, e o resto é o modelo local.
    marca = f'{e["id"]}|{e["url"]}|{e["modelo"]}'  # trocar o modelo na Central libera na hora
    pausa = _PAUSAS.get(marca)
    if pausa and time.monotonic() < pausa[0]:
        raise APIIndisponivel("API pausada: " + pausa[1])
    try:
        resposta = cliente.chat(payload, tentativas=1, limite_s=LIMITE_ENTIDADE_S)
    except APIIndisponivel as exc:
        texto = str(exc)
        if re.match(r"HTTP (400|401|403|404)\b", texto):  # sem chave não pausa: salvar a chave vale na hora
            _PAUSAS[marca] = (time.monotonic() + PAUSA_ERRO_PERMANENTE_S, texto[:160])
        _situacao(e["id"], "erro", texto)
        raise
    _PAUSAS.pop(marca, None)
    _situacao(e["id"], "ok", "")
    return resposta


def _situacao(ident: str, estado: str, detalhe: str) -> None:
    """Última situação de cada API (para a Central mostrar). Falha aqui nunca derruba a chamada."""
    try:
        try:
            dados = json.loads(ARQUIVO_SITUACAO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dados = {}
        dados[ident] = dict(estado=estado, detalhe=detalhe[:200], quando=time.strftime("%d/%m %H:%M"),
                            entidade=config.ENTIDADE_ID)
        ARQUIVO_SITUACAO.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".situacao.", dir=str(ARQUIVO_SITUACAO.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        os.replace(tmp, ARQUIVO_SITUACAO)
    except OSError:
        pass


def situacao() -> dict:
    try:
        return json.loads(ARQUIVO_SITUACAO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ler_chave(nome: str, arquivo: Path | None = None) -> str:
    """Compatibilidade (provas): chave do provedor salva à mão."""
    valor = _ler_var(nome, arquivo or ARQUIVO_CHAVE)
    if not valor:
        raise APIIndisponivel(f"chave {nome} não encontrada")
    return valor
