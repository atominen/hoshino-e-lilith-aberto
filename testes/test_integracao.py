"""
Teste de integração da v6 — sem Ollama, sem GPU, sem interface.

O Ollama vira um roteiro de respostas e a TUI vira stub, então dá para verificar o
comportamento que realmente importa, incluindo as regressões que motivaram esta
versão:

  * o ciclo pensa -> usa ferramenta -> vê o resultado -> responde;
  * tick sem pressão nenhuma não chega a chamar o modelo;
  * **o escriba guarda "eu sou o Gustavo, seu criador" sozinho** — foi exatamente
    isto que falhou no banco real da v5, com a tabela de memória em zero;
  * vontade de falar sem âncora termina em silêncio, antes de gerar texto;
  * lembrete vencido gera fala e é marcado como entregue;
  * oferta de criar lembrete NÃO é tratada como alucinação (falso positivo real);
  * compactação resgata os fatos antes de descartar o texto;
  * internet desligada recusa a ferramenta e aparece no prompt;
  * emoção acesa muda a pressão dos impulsos;
  * partida de xadrez anda sozinha nos ticks.

    python3 testes/test_integracao.py
"""
import asyncio
import os
import sys
import tempfile
import types
from datetime import datetime, timedelta
from unittest.mock import patch

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

TMP = tempfile.mkdtemp(prefix="hoshino_v6_")


# ----------------------------------------------------------------- stubs
class _Widget:
    def __init__(self, *a, **k):
        self.text = ""
        self.border_title = ""
        self.linhas = []

    def write(self, texto):
        self.linhas.append(str(texto))

    def focus(self):
        pass


class _App:
    def __init__(self, *a, **k):
        pass

    def set_interval(self, *a, **k):
        pass

    def set_timer(self, *a, **k):
        pass

    def run(self):
        pass


def _modulo(nome, **atributos):
    m = types.ModuleType(nome)
    for chave, valor in atributos.items():
        setattr(m, chave, valor)
    sys.modules[nome] = m
    return m


_modulo("textual")
_modulo("textual.app", App=_App, ComposeResult=object)
_modulo("textual.binding", Binding=lambda *a, **k: None)
_modulo("textual.containers", Horizontal=_Widget, Vertical=_Widget)
_modulo("textual.widgets", Header=_Widget, Footer=_Widget, RichLog=_Widget, TextArea=_Widget)
_modulo("mss")
_modulo("pygame")
_modulo("edge_tts")

# Ambiente falso e controlável.
AMBIENTE = {"janela_ativa": "terminal — Hoshino", "janelas": ["terminal — Hoshino"],
            "midia": {}, "ociosidade_x11": 5.0}
_modulo("tools.sensors", estado=lambda: dict(AMBIENTE),
        descrever=lambda d=None: "na frente: Hoshino",
        get_system_state=lambda: "na frente: Hoshino",
        janela_ativa=lambda: AMBIENTE["janela_ativa"], janelas=lambda: AMBIENTE["janelas"],
        midia=lambda: AMBIENTE["midia"], ociosidade_x11=lambda: AMBIENTE["ociosidade_x11"],
        carga=lambda: {}, tem=lambda p: False)

# Ollama falso: devolve o próximo item do roteiro a cada chamada.
ROTEIRO, CHAMADAS = [], []


class _Resposta:
    def __init__(self, dados):
        self._dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": self._dados, "done": True}


def _post_falso(url, json=None, timeout=None, **kwargs):
    CHAMADAS.append(json)
    if not ROTEIRO:
        return _Resposta({"role": "assistant", "content": "(roteiro vazio)"})
    return _Resposta(ROTEIRO.pop(0))


import requests  # noqa: E402

requests.post = _post_falso

import config  # noqa: E402

config.DB_PATH = os.path.join(TMP, "teste.db")
config.OFICINA_DIR = os.path.join(TMP, "workspace")
config.JOBS_DIR = os.path.join(TMP, "jobs")
config.RUNTIME_DIR = TMP
config.EVENT_LOG_DIR = os.path.join(TMP, "eventos")
config.ESTADO_MENTE = os.path.join(TMP, "mente.json")
config.BUS_DIR = os.path.join(TMP, "bus")
config.ENTREGA_SAIDA = os.path.join(TMP, "entregas", "saida")
config.ENTREGA_ENTRADA = os.path.join(TMP, "entregas", "entrada")
config.VOZ_ATIVA = False
config.MIC_ATIVO = False

from memory.sqlite import init_db  # noqa: E402

init_db.DB_PATH = config.DB_PATH
init_db.init_database(verbose=False)

from memory import knowledge_store as saber  # noqa: E402
from tools import agenda, terminal, workspace  # noqa: E402

agenda.DB_PATH = saber.DB_PATH = config.DB_PATH
terminal.JOBS_DIR = config.JOBS_DIR
workspace.OFICINA = __import__("pathlib").Path(config.OFICINA_DIR)

from core import rede  # noqa: E402

rede.ARQUIVO = os.path.join(TMP, "rede.json")

import main  # noqa: E402

main.speak = lambda *a, **k: asyncio.sleep(0)

from core import bd, compaction, dispatch, kernel, user_modes  # noqa: E402
from mind import affect, drives, emotions, night_reflection, personality, scribe  # noqa: E402
from social import people  # noqa: E402

ok, falhas = 0, []


def checar(descricao, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {descricao}")
    else:
        falhas.append(f"{descricao} {detalhe}")
        print(f"  FALHA {descricao} {detalhe}")


def nova_app():
    app = main.InterfaceHoshino()
    app.sys_log = _Widget()
    app.chat_log = _Widget()
    app.entrada = _Widget()
    return app


def rodar(corrotina):
    return asyncio.run(corrotina)


def painel(app):
    return "\n".join(app.sys_log.linhas)


def conversa(app):
    return "\n".join(app.chat_log.linhas)


# ================================================================== casos
print("\n== A. Ciclo multi-passo com ferramenta ==")
ROTEIRO[:] = [
    {"role": "assistant", "tool_calls": [
        {"function": {"name": "execute_command",
                      "arguments": {"command": "echo funcionou-de-verdade"}}}]},
    {"role": "assistant", "content": "O comando devolveu funcionou-de-verdade."},
]
CHAMADAS.clear()
app = nova_app()
app.ultima_entrada = "roda um echo aí"
app.messages.append({"role": "user", "content": "roda um echo aí"})
rodar(app.responder(""))
checar("chamou o modelo duas vezes (ferramenta + conclusão)", len(CHAMADAS) >= 2,
       f"foram {len(CHAMADAS)}")
checar("o resultado real do comando voltou para o modelo",
       any("funcionou-de-verdade" in str(c) for c in CHAMADAS))
checar("resposta final foi publicada", "funcionou-de-verdade" in conversa(app))

print("\n== B. Tick calmo não chega a chamar o modelo ==")
CHAMADAS.clear()
app = nova_app()
app.ultima_interacao = datetime.now()
rodar(app.batimento())
checar("nenhuma chamada ao modelo num tick sem pressão", not CHAMADAS,
       f"houve {len(CHAMADAS)}")
checar("a situação foi montada mesmo assim", bool(app.situacao))
checar("os impulsos foram calculados", bool(app.pressoes))

print("\n== C. O escriba guarda sozinho quem é a pessoa (regressão da v5) ==")
CHAMADAS.clear()
ROTEIRO[:] = [{"role": "assistant", "content": "Prazer. Então foi você que me montou aqui."}]
app = nova_app()
app.ultima_entrada = "eu sou gustavo rosa nunes seu criador nessa instalação"
app.messages.append({"role": "user", "content": app.ultima_entrada})
rodar(app.responder(""))
fatos = bd.consultar("SELECT content FROM memories WHERE status='active'")
texto_fatos = " ".join(f["content"] for f in fatos).lower()
checar("gravou o nome sem o modelo pedir", "gustavo" in texto_fatos,
       f"memórias: {texto_fatos[:120]}")
checar("gravou que ela é responsável pela existência dela",
       "responsável por eu existir" in texto_fatos)
checar("a pessoa passou a ter nome", (app.pessoa or {}).get("nome", "").startswith("Gustavo"),
       str((app.pessoa or {}).get("nome")))
checar("o papel de criador foi registrado", (app.pessoa or {}).get("papel") == "criador",
       str((app.pessoa or {}).get("papel")))
respondidas = bd.um("SELECT COUNT(*) AS n FROM curiosities WHERE origem='origem' "
                    "AND status='respondida'")
checar("o objetivo de origem avançou", respondidas and respondidas["n"] >= 1)

print("\n== D. Vontade de falar sem âncora termina em silêncio ==")
bd.executar("UPDATE curiosities SET status='respondida' WHERE status='aberta'")
CHAMADAS.clear()
app = nova_app()
app.ultima_interacao = datetime.now() - timedelta(minutes=40)
AMBIENTE["ociosidade_x11"] = 30.0
rodar(app.batimento())
falou = "Hoshino (por iniciativa)" in conversa(app)
checar("não falou sem ter assunto concreto", not falou)
checar("o painel explica o motivo do silêncio",
       "quieta" in painel(app).lower() or "nada concreto" in painel(app).lower())

print("\n== E. Com curiosidade aberta, ela puxa assunto (e só então chama o modelo) ==")
scribe.curiosidade_nova("O que ele faz da vida quando não está no computador?",
                        sobre="Gustavo", origem="pessoa", urgencia=0.9)
ROTEIRO[:] = [{"role": "assistant",
               "content": "Uma coisa que eu não sei: o que você faz da vida fora daqui?"}]
CHAMADAS.clear()
app = nova_app()
# Esta fixture avalia iniciativa de conversa, não revisão noturna.
# De madrugada, a revisão usava o primeiro item do roteiro destinado à fala.
# Seu contrato permanece exercitado separadamente em test_reflexao_noturna.
app.ultima_interacao = datetime.now() - timedelta(minutes=45)
app.ultima_fala_autonoma = None
# O teste de iniciativa não deve depender do relógio real da suíte.
_horario_silencio_anterior = config.HORARIO_SILENCIO
config.HORARIO_SILENCIO = (0, 0)
try:
    with patch.object(night_reflection, 'horario_noturno', return_value=False):
        rodar(app.batimento())
finally:
    config.HORARIO_SILENCIO = _horario_silencio_anterior
checar("desta vez ela falou por iniciativa", "por iniciativa" in conversa(app),
       conversa(app)[-160:]+"\n"+painel(app)[-1400:])
checar("a fala citou o que a motivou", "vida" in conversa(app).lower())
checar("o roteiro de conversa não foi consumido por uma revisão noturna", len(CHAMADAS) == 1,
       f"foram {len(CHAMADAS)} chamadas")

print("\n== F. Oferta de lembrete não é alucinação; afirmação falsa é ==")
from core import autonomy  # noqa: E402

pergunta_ok, _ = autonomy.checar_afirmacoes_de_agenda(
    "Quer que eu crie um lembrete de hidratação antes de você dormir?")
afirmacao_ok, _ = autonomy.checar_afirmacoes_de_agenda("Seus 3 lembretes de hoje já venceram.")
checar("oferta passa (era falso positivo no log real)", pergunta_ok)
checar("afirmação falsa é barrada", not afirmacao_ok)

print("\n== G. Lembrete vencido: ela avisa e marca como entregue ==")
agenda.criar_lembrete("beber água", "agora")
bd.executar("UPDATE reminders SET due_at = ? WHERE status='pending'",
            ((datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds"),))
ROTEIRO[:] = [{"role": "assistant", "content": "Passou da hora de beber água."}]
CHAMADAS.clear()
app = nova_app()
app.ultima_interacao = datetime.now()
rodar(app.batimento())
checar("avisou do lembrete", "água" in conversa(app).lower(), conversa(app)[-120:])
pendentes = bd.um("SELECT COUNT(*) AS n FROM reminders WHERE status='pending'")
checar("o lembrete foi marcado como entregue", pendentes and pendentes["n"] == 0,
       f"pendentes={pendentes}")

print("\n== H. Modo silencioso engaveta até lembrete ==")
agenda.criar_lembrete("alongar", "agora")
bd.executar("UPDATE reminders SET due_at = ? WHERE status='pending'",
            ((datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds"),))
CHAMADAS.clear()
app = nova_app()
user_modes.definir_silencioso(True)
app.ultima_interacao = datetime.now()
rodar(app.batimento())
user_modes.definir_silencioso(False)
checar("não falou em modo silencioso", "por iniciativa" not in conversa(app))
checar("nem chamou o modelo", not CHAMADAS, f"{len(CHAMADAS)} chamadas")
bd.executar("UPDATE reminders SET status='done' WHERE status='pending'")

print("\n== I. Compactação resgata fatos antes de descartar texto ==")
app = nova_app()
app.messages = []
for i in range(14):
    app.messages.append({"role": "user",
                         "_origem": main.scribe.origem_entrada(app.pessoa, 'tui'),
                         "content": (f"mensagem {i} de enchimento " + "x" * 400
                                     + (" minha placa de video é uma rx 6650 xt"
                                        if i == 1 else ""))})
    app.messages.append({"role": "assistant", "content": "ok " + "y" * 300})
antes = compaction.tamanho(app.messages)
config.CONTEXTO_MAX_TOKENS = 8192
saida_anterior = config.NUM_PREDICT
config.NUM_PREDICT = 1024  # Reserva coerente com a janela da fixture offline.
# 07/11: uma entidade com janela de 8K monta o prompt compacto; a fixture montava o completo (janela maior) e só
# depois reduzia a janela. Com o bloco [FATOS] o completo deixou de caber junto do resumo e da última troca.
app.prompt_sistema = main.prompting.montar_prompt_sistema()
ROTEIRO[:] = [{"role": "assistant",
               "content": "FATOS: a placa é uma rx 6650 xt\nCOMBINADOS: —\n"
                          "EM ABERTO: —\nCLIMA: conversa longa"}]
rodar(app.compactar_se_precisar())
depois = compaction.tamanho(app.messages)
checar("o histórico encolheu", depois < antes, f"{antes} -> {depois}")
checar("o resumo entrou no lugar", any(compaction.CABECALHO in str(m.get("content", ""))
                                       for m in app.messages))
props = saber.propriedades_de((app.pessoa or {}).get('nome','usuário'))
checar("o fato durável foi resgatado para a memória permanente",
       "6650" in props.lower(), props[:120])
checar("a compactação ficou registrada", "compactei" in painel(app) or
       bd.um("SELECT COUNT(*) AS n FROM context_summaries")["n"] >= 1)
config.CONTEXTO_MAX_TOKENS = config.NUM_CTX
config.NUM_PREDICT = saida_anterior

print("\n== J. Internet desligada: ferramenta recusa e ela sabe disso ==")
from tools import web  # noqa: E402

rede.desligar("teste", por="suite")
resultado = web.web_search("qualquer coisa")
checar("a busca recusa com motivo legível", resultado.startswith("REDE_DESLIGADA"),
       resultado[:80])
checar("o prompt avisa que está sem rede", "SEM INTERNET" in rede.bloco_para_prompt())
checar("ferramenta de web some da lista quando não há rede",
       "web_search" not in {e["function"]["name"]
                            for e in dispatch.esquemas("pesquisa na internet")})
checar("localhost continua liberado", rede.permitido("http://localhost:11434"))
rede.ligar("fim do teste", por="suite")
checar("religou", rede.ativa())

print("\n== K. Emoção acesa muda a pressão dos impulsos ==")
situacao_base = {"segundos_ociosos": 2000, "usuario_presente": True,
                 "curiosidades_abertas": 1, "humor": affect.estado(), "novidades": 0,
                 "episodios_sem_refletir": 2}
drives.satisfazer("conexao", datetime.now() - timedelta(hours=2))
antes_conexao = drives.avaliar(situacao_base)["conexao"]["pressao"]
affect.apreciar("maltrato", motivo="teste de raiva")
depois_conexao = drives.avaliar(situacao_base)["conexao"]["pressao"]
checar("com raiva ela quer menos puxar assunto", depois_conexao < antes_conexao,
       f"{antes_conexao} -> {depois_conexao}")
checar("a raiva ficou registrada com causa",
       "teste de raiva" in emotions.o_que_me_causa("raiva"))
affect.apreciar("elogio", motivo="teste de alegria")
checar("elogio acende alegria", emotions.intensidade_de("alegria") > 0.2)

print("\n== L. Xadrez: ferramenta começa a partida e o tick faz ela andar ==")
inicio = dispatch.executar("jogar_xadrez", {"oponente": "Pepino"})
checar("a partida começou", dispatch.PARTIDA["atual"] is not None, inicio[:60])
lances_antes = len(dispatch.PARTIDA["atual"].lances)
app = nova_app()
rodar(app.avancar_partida())
checar("o tick avançou a partida sem travar nada",
       len(dispatch.PARTIDA["atual"].lances) > lances_antes)
checar("as ferramentas de xadrez aparecem com partida em andamento",
       "lance_xadrez" in {e["function"]["name"] for e in dispatch.esquemas("oi")})
dispatch.executar("parar_partida", {})
checar("a partida encerrada saiu do lugar", dispatch.PARTIDA["atual"] is None)

print("\n== M. Personalidade se forma a partir do comportamento ==")
antes_traco = personality.traco("curiosidade")
for _ in range(6):
    scribe.pos_turno("tanto faz", "Por que você faz assim? Fiquei curiosa.")
depois_traco = personality.traco("curiosidade")
checar("perguntar empurra o traço de curiosidade", depois_traco > antes_traco,
       f"{antes_traco:.3f} -> {depois_traco:.3f}")
checar("o traço só entra no prompt com evidência suficiente",
       ("curiosidade" in personality.bloco_personalidade())
       == (bd.um("SELECT evidencias FROM traits WHERE nome='curiosidade'")["evidencias"]
           >= config.EVIDENCIAS_PARA_CONSOLIDAR))

print("\n== N. Ferramentas entram por relevância, não todas de uma vez ==")
nucleo = dispatch.esquemas("oi tudo bem")
tudo = dispatch.esquemas(todos=True)
checar("o núcleo é bem menor que o total", len(nucleo) < len(tudo) / 2,
       f"{len(nucleo)} de {len(tudo)}")
checar("falar de xadrez traz as ferramentas de xadrez",
       "jogar_xadrez" in {e["function"]["name"] for e in dispatch.esquemas("bora jogar xadrez")})
checar("falar de arquivo traz as de entrega",
       "entregar_arquivo" in {e["function"]["name"]
                              for e in dispatch.esquemas("me manda esse arquivo")})
checar("todo esquema tem handler",
       not ({e["function"]["name"] for e in tudo} - set(dispatch.HANDLERS)))

# ================================================================== fim
print(f"\n{'=' * 60}")
print(f"{ok} verificações passaram, {len(falhas)} falharam")
for f in falhas:
    print(f"  - {f}")
sys.exit(1 if falhas else 0)
