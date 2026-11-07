"""
Teste manual (não faz parte da suíte oficial) para o sistema de diretiva
sustentada e os outros ajustes desta sessão. Roda isolado, sem tocar no banco
real — mesmo padrão de testes/test_hoshino.py.
"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

TMP = tempfile.mkdtemp(prefix="hoshino_teste_diretiva_")
import config  # noqa: E402
config.DB_PATH = os.path.join(TMP, "teste.db")

from memory.sqlite import init_db  # noqa: E402
init_db.DB_PATH = config.DB_PATH
init_db.init_database(verbose=False)

from tools import agenda  # noqa: E402
agenda.DB_PATH = config.DB_PATH
from mind import strategies  # noqa: E402
from core import kernel  # noqa: E402

falhas = []


def checar(nome, condicao):
    status = "OK" if condicao else "FALHOU"
    if not condicao:
        falhas.append(nome)
    print(f"[{status}] {nome}")


# --- 1. _semelhanca: o caso real do docstring ------------------------------
sim = agenda._semelhanca(
    "Lembrar de beber água",
    "Lembrar de beber água regularmente para manter a hidratação adequada.")
checar(f"_semelhanca('beber água' x variante longa) = {sim:.2f} >= 0.8", sim >= 0.8)

# --- 2. add_goal comum + dedup ----------------------------------------------
r1 = agenda.add_goal("Lembrar de beber água")
checar(f"add_goal cria objetivo comum: {r1!r}", r1.startswith("Objetivo ["))
r2 = agenda.add_goal("Lembrar de beber água regularmente para manter a hidratação adequada.")
checar(f"add_goal detecta duplicado: {r2!r}", "equivalente" in r2)

# --- 3. add_goal sustentado: validação --------------------------------------
erro_sem_acao = agenda.add_goal("fica jogando até eu voltar", sustentar=True, enquanto="ausente")
checar(f"add_goal sustentado sem acao dá erro: {erro_sem_acao!r}",
       erro_sem_acao.startswith("Erro"))
erro_enquanto = agenda.add_goal("teste", sustentar=True, enquanto="nunca", acao="jogar")
checar(f"add_goal com enquanto inválido dá erro: {erro_enquanto!r}",
       erro_enquanto.startswith("Erro"))

# --- 4. add_goal sustentado: caso real do bug -------------------------------
r3 = agenda.add_goal("fica jogando xadrez até eu voltar", sustentar=True,
                     enquanto="ausente", acao="jogar")
checar(f"add_goal cria diretiva sustentada: {r3!r}",
       r3.startswith("Objetivo [") and "diretiva contínua" in r3)

# --- 5. diretiva_ativa respeita a condição 'ausente' ------------------------
d_presente = agenda.diretiva_ativa(usuario_presente=True)
checar("diretiva_ativa(presente=True) não dispara diretiva 'ausente'", d_presente is None)
d_ausente = agenda.diretiva_ativa(usuario_presente=False)
checar("diretiva_ativa(presente=False) encontra a diretiva de xadrez",
       d_ausente is not None and d_ausente["acao"] == "jogar")

# --- 6. kernel.deliberar(): dispara 'jogar' quando ausente e sem partida ----
situacao = {"usuario_presente": False, "eventos": []}
from mind import drives  # noqa: E402
pressoes = {nome: {"pressao": 0.0, "acao": acao, "refratario": 1.0, "emocao": 1.0}
           for nome, (_, acao) in drives.IMPULSOS.items()}  # tudo baixo de propósito
estado = {"modo_silencioso": False, "ultima_fala": None, "ultima_acao_interna": None,
         "acoes_na_hora": 0, "xadrez_disponivel": True, "partida_em_andamento": False}
decisao = kernel.deliberar(situacao, pressoes, estado)
checar(f"kernel dispara 'jogar' por diretiva mesmo com pressões zeradas: {decisao}",
       decisao["tipo"] == "jogar")

# --- 7. kernel.deliberar(): NÃO redispara se já tem partida em andamento ---
estado["partida_em_andamento"] = True
decisao2 = kernel.deliberar(situacao, pressoes, estado)
checar(f"kernel não redispara 'jogar' com partida em andamento: {decisao2}",
       decisao2["tipo"] != "jogar")

# --- 8. concluir_diretivas: usuário volta = diretiva 'ausente' se fecha -----
concluidas = agenda.concluir_diretivas("ausente")
checar(f"concluir_diretivas('ausente') fecha a diretiva de xadrez: {concluidas}",
       len(concluidas) == 1)
d_depois = agenda.diretiva_ativa(usuario_presente=False)
checar("depois de concluída, diretiva não aparece mais", d_depois is None)

# --- 9. proximo_objetivo_novo(): objetivo nunca tentado entra na fila ------
agenda.add_goal("estudar abertura de xadrez", prioridade=1)
agenda.add_goal("aprender a assar pão", prioridade=4)
novo = strategies.proximo_objetivo_novo()
checar(f"proximo_objetivo_novo() pega o de prioridade 1: {novo}",
       novo is not None and "abertura" in novo["description"])

# --- 10. list_goals mostra diretiva contínua -------------------------------
agenda.add_goal("continua pesquisando sobre xadrez enquanto eu não tô",
                sustentar=True, enquanto="sempre", acao="investigar")
listagem = agenda.list_goals()
checar("list_goals sinaliza diretiva contínua no texto", "diretiva contínua" in listagem)

print()
if falhas:
    print(f"FALHAS ({len(falhas)}): " + ", ".join(falhas))
    sys.exit(1)
print(f"Todos os {10} blocos passaram.")
