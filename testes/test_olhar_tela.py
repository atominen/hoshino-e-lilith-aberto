"""A Hoshino olhando a tela por iniciativa propria.

`observar_tela` ja constava em kernel.INTERNAS e INTERVALO_MIN_OLHAR_TELA ja
existia no config, mas nada emitia a intencao e nada a executava: a capacidade
existia so na fiacao. Estes testes fixam o comportamento agora que ela fecha.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

TMP = tempfile.mkdtemp(prefix="hoshino_tela_")
import config  # noqa: E402

config.DB_PATH = os.path.join(TMP, "t.db")
config.RUNTIME_DIR = TMP
config.ESTADO_MENTE = os.path.join(TMP, "mente.json")

from memory.sqlite import init_db  # noqa: E402

init_db.DB_PATH = config.DB_PATH
init_db.init_database(verbose=False)

from core import bd, kernel, rede  # noqa: E402

bd.DB_PATH = config.DB_PATH
rede.ARQUIVO = os.path.join(TMP, "rede.json")

ok, falhas = 0, []


def checar(desc, cond, det=""):
    global ok
    if cond:
        ok += 1
        print(f"  ok   {desc}")
    else:
        falhas.append(desc)
        print(f"  FALHA {desc} {det}")


AGORA = datetime.now()
SITUACAO = {"agora": AGORA, "usuario_presente": True, "eventos": [],
            "lembretes_vencidos": 0}
# Curiosidade dominante e sem pergunta em aberto: o caso que antes evaporava.
PRESSOES = {n: {"nome": n, "pressao": p} for n, p in
            [("curiosidade", 0.9), ("ocio", 0.1), ("conexao", 0.1),
             ("coerencia", 0.1), ("competencia", 0.1)]}


def estado(ultima_olhada=None):
    return {"ultima_acao_interna": None, "acoes_na_hora": 0,
            "ultima_olhada": ultima_olhada}


print("== Olhar a tela por conta propria ==")

d = kernel.deliberar(SITUACAO, PRESSOES, estado())
checar("curiosa e sem alvo: decide olhar a tela", d["tipo"] == "observar_tela", d["tipo"])

d = kernel.deliberar(SITUACAO, PRESSOES, estado(AGORA - timedelta(minutes=3)))
checar("olhou ha 3 min: nao olha de novo", d["tipo"] == "nada", d["tipo"])

d = kernel.deliberar(SITUACAO, PRESSOES, estado(AGORA - timedelta(minutes=20)))
checar("passados 20 min: pode olhar de novo", d["tipo"] == "observar_tela", d["tipo"])

ausente = dict(SITUACAO, usuario_presente=False)
d = kernel.deliberar(ausente, PRESSOES, estado())
checar("pessoa ausente: nao faz sentido olhar", d["tipo"] == "nada", d["tipo"])

checar("olhar a tela nao interrompe ninguem",
       "observar_tela" in kernel.INTERNAS and "observar_tela" not in kernel.FALANTES)

# Pergunta em aberto continua tendo precedencia: olhar a tela e o ultimo recurso
# da curiosidade, nao o primeiro.
from mind import scribe  # noqa: E402

scribe.curiosidade_nova("Por que o disco encheu ontem?", sobre="sistema")
d = kernel.deliberar(SITUACAO, PRESSOES, estado())
checar("com pergunta em aberto, investigar vem antes de olhar",
       d["tipo"] == "investigar", d["tipo"])

print()
print("=" * 58)
print(f"{ok} verificacoes ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
