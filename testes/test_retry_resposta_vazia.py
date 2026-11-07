"""Reproduz o bug real de campo: o Ollama devolve `thinking` com raciocínio de
verdade mas `content` vazio e `tool_calls` vazio — visto em produção em toda
resposta puramente textual de uma sessão (log: llm.end content.len=0 com
thinking.len>0, repetido). Antes disto, `ciclo_de_ferramentas` desistia direto
com a mensagem de "não consegui formular uma resposta". Agora tenta de novo,
pedindo texto direto e desligando o thinking, antes de desistir.
"""
import asyncio
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))
os.chdir(RAIZ)

TMP = tempfile.mkdtemp(prefix="retry_vazio_")
import config  # noqa: E402

config.DB_PATH = os.path.join(TMP, "t.db")
config.RUNTIME_DIR = TMP

import types as _types  # noqa: E402
for _mod, _attrs in [
    ("textual.app", {"App": object, "ComposeResult": object}),
    ("textual.binding", {"Binding": lambda *a, **k: None}),
    ("textual.containers", {"Horizontal": object, "Vertical": object}),
    ("textual.widgets", {"Footer": object, "Header": object, "RichLog": object, "TextArea": object}),
]:
    m = _types.ModuleType(_mod)
    for k, v in _attrs.items():
        setattr(m, k, v)
    sys.modules[_mod] = m
sys.modules["textual"] = _types.ModuleType("textual")

import main as H  # noqa: E402

ok, falhas = 0, []


def checar(desc, cond, det=""):
    global ok
    if cond:
        ok += 1
        print(f"  ok   {desc}")
    else:
        falhas.append(desc)
        print(f"  FALHA {desc} {det}")


class _W:
    def write(self, *a, **k): pass


def montar_app():
    app = H.InterfaceHoshino.__new__(H.InterfaceHoshino)
    app.sys_log = _W()
    app.chat_log = _W()
    return app


print("== Recupera quando a segunda tentativa vem preenchida ==")


async def t1():
    app = montar_app()
    chamadas = []

    async def chamar_falso(mensagens, ferramentas=None, forcar_sem_pensar=False):
        chamadas.append({"ferramentas": ferramentas, "forcar_sem_pensar": forcar_sem_pensar})
        if len(chamadas) == 1:
            # exatamente o padrão do log real: pensou, não respondeu, não chamou nada.
            return {"role": "assistant", "content": "",
                    "thinking": "A pessoa só quer conversa, não preciso de ferramenta.",
                    "tool_calls": []}
        return {"role": "assistant", "content": "Oi! Tudo bem por aqui.", "thinking": "", "tool_calls": []}

    app.chamar_modelo = chamar_falso
    conteudo, usadas = await app.ciclo_de_ferramentas(
        [{"role": "user", "content": "oi hoshino"}], [])

    checar("duas chamadas ao modelo (original + retry)", len(chamadas) == 2, str(len(chamadas)))
    checar("o retry pede sem pensar", chamadas[1]["forcar_sem_pensar"] is True)
    checar("o retry não recebe lista de ferramentas", chamadas[1]["ferramentas"] is None)
    checar("recupera o texto real, não a desculpa genérica",
           conteudo == "Oi! Tudo bem por aqui.", conteudo)

asyncio.run(t1())

print("== Ainda desiste com uma mensagem clara se o retry também vier vazio ==")


async def t2():
    app = montar_app()
    chamadas = []

    async def chamar_falso(mensagens, ferramentas=None, forcar_sem_pensar=False):
        chamadas.append(1)
        return {"role": "assistant", "content": "", "thinking": "pensando de novo sem concluir",
                "tool_calls": []}

    app.chamar_modelo = chamar_falso
    conteudo, usadas = await app.ciclo_de_ferramentas(
        [{"role": "user", "content": "oi"}], [])

    checar("tenta exatamente uma vez a mais, não entra em loop", len(chamadas) == 2, str(len(chamadas)))
    checar("mensagem de desistência é clara para a pessoa",
           "não consegui" in conteudo.lower(), conteudo)

asyncio.run(t2())

print("== Sem thinking nenhum, não tenta retry à toa (não é o mesmo sintoma) ==")


async def t3():
    app = montar_app()
    chamadas = []

    async def chamar_falso(mensagens, ferramentas=None, forcar_sem_pensar=False):
        chamadas.append(1)
        return {"role": "assistant", "content": "", "thinking": "", "tool_calls": []}

    app.chamar_modelo = chamar_falso
    conteudo, usadas = await app.ciclo_de_ferramentas(
        [{"role": "user", "content": "oi"}], [])

    checar("content e thinking vazios: uma chamada só, direto à desistência",
           len(chamadas) == 1, str(len(chamadas)))

asyncio.run(t3())

print("== num_predict explícito no payload (não fica no padrão do Ollama) ==")
checar("config.NUM_PREDICT existe e é positivo",
       hasattr(config, "NUM_PREDICT") and config.NUM_PREDICT > 0)

print()
print("=" * 58)
print(f"{ok} verificacoes ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
