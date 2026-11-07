"""Exercita o caminho real de um turno da Hoshino com Ollama e TUI simulados.

Nao testa o modelo; testa o codigo em volta dele: montagem do payload, ciclo de
ferramentas, publicacao, escriba, salvamento de episodio.
"""
import json
import os
import sys
import tempfile
import types
import asyncio

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
os.chdir(RAIZ)

TMP = tempfile.mkdtemp(prefix="e2e_")

# ---------------------------------------------------------------- stubs
def _stub(nome, **attrs):
    m = types.ModuleType(nome)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[nome] = m
    return m

class _W:
    def __init__(self, *a, **k): pass
    def write(self, *a, **k): pass
    def clear(self, *a, **k): pass
    def focus(self, *a, **k): pass
    def __getattr__(self, n): return lambda *a, **k: None

class _App:
    def __init__(self, *a, **k): pass
    def run(self): pass
    def query_one(self, *a, **k): return _W()
    def set_timer(self, *a, **k): return None
    def set_interval(self, *a, **k): return None
    def run_worker(self, *a, **k): return None
    def exit(self, *a, **k): return None

tx = _stub("textual")
_stub("textual.app", App=_App, ComposeResult=object)
_stub("textual.binding", Binding=lambda *a, **k: None)
_stub("textual.containers", Horizontal=_W, Vertical=_W)
_stub("textual.widgets", Footer=_W, Header=_W, RichLog=_W, TextArea=_W)

# ---------------------------------------------------------------- ollama falso
CHAMADAS = []
ROTEIRO = []

class _Resp:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return self._d

def fake_post(url, json=None, timeout=None, **k):
    CHAMADAS.append(json)
    if ROTEIRO:
        return _Resp({"message": ROTEIRO.pop(0), "done": True})
    return _Resp({"message": {"role": "assistant", "content": "ok."}, "done": True})

import requests
requests.post = fake_post

# ---------------------------------------------------------------- config isolado
import config
config.DB_PATH = os.path.join(TMP, "t.db")
config.RUNTIME_DIR = TMP
config.BUS_DIR = os.path.join(TMP, "bus")
config.JOBS_DIR = os.path.join(TMP, "jobs")
config.EVENT_LOG_DIR = os.path.join(TMP, "ev")
config.ESTADO_MENTE = os.path.join(TMP, "mente.json")
config.OFICINA_DIR = os.path.join(TMP, "of")
config.ENTREGA_SAIDA = os.path.join(TMP, "saida")
config.ENTREGA_ENTRADA = os.path.join(TMP, "entrada")
config.garantir_pastas()

from memory.sqlite import init_db
init_db.DB_PATH = config.DB_PATH
init_db.init_database(verbose=False)

from memory import knowledge_store as saber
from tools import agenda
for m in (agenda, saber):
    m.DB_PATH = config.DB_PATH

from core import rede
rede.ARQUIVO = os.path.join(TMP, "rede.json")

import main as H

ok, falhas = 0, []
def checar(desc, cond, det=""):
    global ok
    if cond:
        ok += 1; print(f"  ok   {desc}")
    else:
        falhas.append(desc); print(f"  FALHA {desc} {det}")

print("== E2E: payload do Ollama ==")

app = H.InterfaceHoshino.__new__(H.InterfaceHoshino)
app.sys_log = _W(); app.chat_log = _W()
app.saidas_recentes = __import__("collections").deque(maxlen=8)
app.confirmacao_pendente = None

print("== E2E: travas de turno ==")

async def t_travas():
    # Simula o caminho real: o turno segura sua trava de consolidação e a
    # chamada ao modelo ainda precisa poder obter uma trava própria.
    app.trava = asyncio.Lock()
    app.trava_modelo = asyncio.Lock()
    async with app.trava:
        ROTEIRO.clear(); CHAMADAS.clear()
        ROTEIRO.append({"role": "assistant", "content": "sem deadlock"})
        msg = await asyncio.wait_for(
            app.chamar_modelo([{ "role": "user", "content": "teste"}], None), timeout=0.5)
    checar("trava de turno não bloqueia a chamada ao modelo", msg.get("content") == "sem deadlock")

asyncio.run(t_travas())

print("== E2E: filas independentes por conversa ==")

async def t_filas_independentes():
    from collections import deque
    app.messages = []
    app._historicos_por_chave = {}
    app._revisoes_conversa = {}
    app._fila_conversa = deque()
    app._fila_chaves = {}
    app._workers_por_chave = {}
    app._travas_conversa = {}
    app._versao_fila_conversa = 0
    app.ultima_interacao = None
    app.canal_atual = "tui"
    app.ultima_entrada = ""
    app.contexto_do_turno = lambda *a, **k: ""
    iniciados, liberar = [], asyncio.Event()

    async def responder_falso(*args, **kwargs):
        iniciados.append(kwargs["chave_conversa"])
        await liberar.wait()

    app.responder = responder_falso
    antigo_debounce = config.DEBOUNCE_CONVERSA_MS
    config.DEBOUNCE_CONVERSA_MS = 1
    try:
        app.receber_de_pessoa("pergunta A", canal="discord", responder_para="a")
        app.receber_de_pessoa("pergunta B", canal="discord", responder_para="b")
        for _ in range(30):
            if len(iniciados) == 2:
                break
            await asyncio.sleep(0.01)
        checar("fios independentes iniciam sem esperar o outro", len(iniciados) == 2, str(iniciados))
        tarefas = list(app._workers_por_chave.values())
        liberar.set()
        await asyncio.gather(*tarefas)
    finally:
        config.DEBOUNCE_CONVERSA_MS = antigo_debounce

asyncio.run(t_filas_independentes())

print("== E2E: histórico por conversa ==")
app.messages = []
app._historicos_por_chave = {}
hist_tui = app._historico_da_conversa(("tui", "local", "criador"))
hist_discord = app._historico_da_conversa(("discord", "123", "outra_pessoa"))
hist_tui.append({"role": "user", "content": "assunto do TUI"})
hist_discord.append({"role": "user", "content": "assunto do Discord"})
checar("fios têm listas distintas", hist_tui is not hist_discord)
checar("Discord não vaza para o TUI", all("Discord" not in m["content"] for m in hist_tui))
checar("TUI não vaza para o Discord", all("TUI" not in m["content"] for m in hist_discord))

print("== E2E: evidências por conversa ==")
chave_a = ("discord", "a", "pessoa-a")
chave_b = ("discord", "b", "pessoa-b")
app._saidas_por_conversa = {}
app._saidas_da_conversa(chave_a).append(("ler_a", "resultado exclusivo A"))
app._saidas_da_conversa(chave_b).append(("ler_b", "resultado exclusivo B"))
saidas_a = list(app._saidas_da_conversa(chave_a))
saidas_b = list(app._saidas_da_conversa(chave_b))
checar("resultado do fio A não entra no fio B", saidas_a == [("ler_a", "resultado exclusivo A")] and
       saidas_b == [("ler_b", "resultado exclusivo B")], f"A={saidas_a}; B={saidas_b}")

async def t1():
    ROTEIRO.clear(); CHAMADAS.clear()
    ROTEIRO.append({"role": "assistant", "content": "oi"})
    msg = await app.chamar_modelo([{"role": "user", "content": "oi"}], None)
    p = CHAMADAS[0]
    checar("payload usa o modelo do config", p["model"] == config.MODEL_NAME)
    checar("payload manda janela adaptativa dentro do teto",
           512 <= p["options"]["num_ctx"] <= config.NUM_CTX)
    checar("janela reserva a saída configurada",
           p["options"]["num_ctx"] > p["options"]["num_predict"])
    checar("payload manda keep_alive", p.get("keep_alive") == config.OLLAMA_KEEP_ALIVE)
    checar("streaming do Ollama habilitado", p["stream"] is True)
    checar("devolve a mensagem", msg.get("content") == "oi")

asyncio.run(t1())


print("== E2E: streaming entrega fragmentos sem mudar o contrato da mensagem ==")

class _StreamResp:
    status_code = 200
    def raise_for_status(self): pass
    def iter_lines(self, decode_unicode=True):
        yield json.dumps({"message": {"content": "ola "}})
        yield json.dumps({"message": {"thinking": "meta "}})
        yield json.dumps({"message": {"content": "mundo"}, "done": True, "done_reason": "stop"})
    def close(self): pass

async def t_stream():
    ROTEIRO.clear(); CHAMADAS.clear()
    antigo = H.config.STREAM_LLM
    H.config.STREAM_LLM = True
    def fake_stream(url, json=None, timeout=None, **kwargs):
        CHAMADAS.append(json)
        return _StreamResp()
    import requests as _requests
    antigo_post = _requests.post
    _requests.post = fake_stream
    try:
        msg = await app.chamar_modelo([{"role": "user", "content": "stream"}])
    finally:
        _requests.post = antigo_post
        H.config.STREAM_LLM = antigo
    checar("streaming concatena conteúdo", msg.get("content") == "ola mundo", str(msg))
    checar("streaming conserva thinking separado", msg.get("thinking") == "meta", str(msg))
    checar("streaming envia stream=true", CHAMADAS and CHAMADAS[0].get("stream") is True)

asyncio.run(t_stream())


print("== E2E: streaming de tool call e argumentos fragmentados ==")

class _StreamToolResp:
    status_code = 200
    def raise_for_status(self): pass
    def iter_lines(self, decode_unicode=True):
        yield json.dumps({"message": {"tool_calls": [{"function": {"name": "execute_command", "arguments": "{\"command\":\"ec"}}]}})
        yield json.dumps({"message": {"tool_calls": [{"function": {"arguments": "ho hello\"}"}}]}, "done": True})
    def close(self): pass

async def t_stream_tool():
    import requests as _requests
    antigo_post = _requests.post
    antigo = H.config.STREAM_LLM
    H.config.STREAM_LLM = True
    def fake_stream_tool(url, json=None, timeout=None, **kwargs):
        return _StreamToolResp()
    _requests.post = fake_stream_tool
    try:
        msg = await app.chamar_modelo([{"role": "user", "content": "tool stream"}])
    finally:
        _requests.post = antigo_post
        H.config.STREAM_LLM = antigo
    chamadas = msg.get("tool_calls") or []
    args = (chamadas[0].get("function") or {}).get("arguments") if chamadas else None
    checar("streaming remonta tool call fragmentada", chamadas and chamadas[0]["function"]["name"] == "execute_command", str(msg))
    checar("streaming remonta argumentos JSON", isinstance(args, dict) and args.get("command") == "echo hello", str(msg))

asyncio.run(t_stream_tool())

print("== E2E: ciclo de ferramentas ==")

async def t2():
    ROTEIRO.clear(); CHAMADAS.clear()
    # 1o passo: modelo pede a hora. 2o: responde texto.
    ROTEIRO.append({"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "get_system_time", "arguments": {}}}]})
    ROTEIRO.append({"role": "assistant", "content": "agora eu sei a hora."})
    conteudo, usadas = await app.ciclo_de_ferramentas(
        [{"role": "user", "content": "que horas sao?"}], [])
    checar("a ferramenta foi executada", usadas == ["get_system_time"], str(usadas))
    checar("conteudo final volta", "hora" in conteudo.lower(), conteudo)
    # a 2a chamada deve conter a mensagem role=tool
    segunda = CHAMADAS[1]["messages"]
    tools_msgs = [m for m in segunda if m.get("role") == "tool"]
    checar("resultado da ferramenta entra como role=tool", len(tools_msgs) == 1)
    checar("mensagem tool tem tool_name", "tool_name" in tools_msgs[0])
    checar("thinking nao e reenviado", all("thinking" not in m for m in segunda))

asyncio.run(t2())

print("== E2E: argumentos em string JSON (modelo as vezes manda assim) ==")

async def t3():
    ROTEIRO.clear(); CHAMADAS.clear()
    ROTEIRO.append({"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "registrar_conhecimento",
                                                 "arguments": '{"conteudo":"Gustavo usa Linux Mint","entidades":["Gustavo"],"tipo":"fato"}'}}]})
    ROTEIRO.append({"role": "assistant", "content": "anotado."})
    conteudo, usadas = await app.ciclo_de_ferramentas(
        [{"role": "user", "content": "eu uso linux mint"}], [])
    checar("args em string JSON sao parseados", usadas == ["registrar_conhecimento"], str(usadas))
    achou = saber.list_facts_about("Gustavo")
    checar("o conhecimento chegou ao banco", "Linux Mint" in achou, achou[:120])

asyncio.run(t3())

print("== E2E: loop infinito de ferramenta tem freio ==")

async def t4():
    ROTEIRO.clear(); CHAMADAS.clear()
    for _ in range(20):
        ROTEIRO.append({"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": "get_system_time", "arguments": {}}}]})
    conteudo, usadas = await app.ciclo_de_ferramentas(
        [{"role": "user", "content": "loop"}], [])
    checar("para no MAX_PASSOS_FERRAMENTA",
           len(usadas) == config.MAX_PASSOS_FERRAMENTA, f"{len(usadas)} passos")
    checar("avisa que parou", "presa" in conteudo.lower() or "parei" in conteudo.lower(), conteudo[:80])

asyncio.run(t4())

print("== E2E: ferramenta inexistente nao derruba ==")

async def t5():
    ROTEIRO.clear(); CHAMADAS.clear()
    ROTEIRO.append({"role": "assistant", "content": "",
                    "tool_calls": [{"function": {"name": "ferramenta_que_nao_existe", "arguments": {}}}]})
    ROTEIRO.append({"role": "assistant", "content": "desisti dessa."})
    try:
        conteudo, usadas = await app.ciclo_de_ferramentas([{"role": "user", "content": "x"}], [])
        checar("nome invalido volta como erro tratado", True)
    except Exception as e:
        checar("nome invalido volta como erro tratado", False, repr(e))

asyncio.run(t5())

print()
print("=" * 58)
print(f"{ok} verificacoes ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
