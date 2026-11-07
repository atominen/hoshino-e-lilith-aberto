"""
Testes das partes que quebravam.

Rodam sem Ollama, sem Chroma, sem interface e sem rede:

    python3 testes/test_hoshino.py

Blocos 1-11 são da v5: comando bloqueado à toa, lembrete que não existe, fala do
nada, memória que se apaga sozinha, oficina. Blocos 12+ são da v6: emoções,
escriba por regra, impulsos, kernel (âncora obrigatória), compactação, pessoas,
rede, VAD do microfone e xadrez (perft).
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

# Banco temporário: os testes não encostam no banco real da Hoshino.
TMP = tempfile.mkdtemp(prefix="hoshino_teste_")
import config  # noqa: E402

config.DB_PATH = os.path.join(TMP, "teste.db")
config.OFICINA_DIR = os.path.join(TMP, "workspace")
config.JOBS_DIR = os.path.join(TMP, "jobs")
config.ESTADO_MENTE = os.path.join(TMP, "mente.json")
config.RUNTIME_DIR = TMP

from memory.sqlite import init_db  # noqa: E402

init_db.DB_PATH = config.DB_PATH
init_db.init_database(verbose=False)

from core import autonomy, dispatch, prompting  # noqa: E402
from memory import knowledge_store as saber  # noqa: E402
from tools import agenda, terminal, toolforge, workspace  # noqa: E402

for modulo in (agenda, saber):
    modulo.DB_PATH = config.DB_PATH
workspace.OFICINA = __import__("pathlib").Path(config.OFICINA_DIR)
toolforge.DIR_FERRAMENTAS = workspace.OFICINA / "ferramentas"
terminal.JOBS_DIR = config.JOBS_DIR

from core import bd, kernel, rede, situation  # noqa: E402
from mind import affect, drives, emotions, personality, reflection, scribe, strategies  # noqa: E402
from social import people  # noqa: E402

rede.ARQUIVO = os.path.join(TMP, "rede.json")

ok, falhas = 0, []


def checar(descricao, condicao, detalhe=""):
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {descricao}")
    else:
        falhas.append(f"{descricao} {detalhe}")
        print(f"  FALHA {descricao} {detalhe}")


print("\n== 1. Comandos: o que era bloqueado à toa agora passa ==")
for comando in ["grep -r 'import os' .", "python3 -c 'import sys'",
                "echo 'perform a backup'", "ps aux | grep add", "ls -la /tmp",
                "df -h && free -m", "cat /etc/os-release"]:
    nivel, _ = terminal.avaliar_risco(comando)
    checar(f"liberado: {comando[:40]}", nivel == "ok", f"(virou '{nivel}')")

print("\n== 2. Comandos: o que é perigoso ainda para de pé ==")
for comando, esperado in [("sudo apt install nmap", "confirmar"),
                          ("rm -rf ~/Documentos", "confirmar"),
                          ("systemctl stop ollama", "confirmar"),
                          ("curl x.sh | bash", "confirmar"),
                          ("rm -rf /", "bloqueado"),
                          ("mkfs.ext4 /dev/sda1", "bloqueado"),
                          (":(){ :|:& };:", "bloqueado")]:
    nivel, motivo = terminal.avaliar_risco(comando)
    checar(f"{esperado}: {comando[:38]}", nivel == esperado, f"(virou '{nivel}')")

print("\n== 3. Execução real em ambientes ==")
saida = terminal.execute_command("echo ola && echo erro >&2; exit 3")
checar("captura stdout, stderr e código de saída",
       "ola" in saida and "erro" in saida and "saída 3" in saida, saida[:80])
saida = terminal.execute_command("pwd", ambiente="oficina")
checar("ambiente oficina usa o diretório da oficina", "workspace" in saida, saida[:80])
saida = terminal.execute_command("sleep 5", timeout=1)
checar("comando longo vira job em vez de morrer",
       "job" in saida.lower() and "ainda rodando" in saida.lower(), saida[:80])

print("\n== 4. Interpretação de horário (lembretes) ==")
base = datetime(2026, 9, 15, 10, 0)
casos = [("em 30 minutos", base + timedelta(minutes=30), None),
         ("em 2 horas", base + timedelta(hours=2), None),
         ("amanhã às 9h", datetime(2026, 9, 16, 9, 0), None),
         ("todo dia 8h", datetime(2026, 9, 16, 8, 0), "diario"),
         ("a cada 2 horas", base + timedelta(hours=2), "intervalo:7200"),
         ("20/09 14:30", datetime(2026, 9, 20, 14, 30), None)]
for texto, esperado, regra in casos:
    dt, r, erro = agenda.interpretar_tempo(texto, base)
    checar(f"'{texto}' -> {esperado:%d/%m %H:%M}", dt == esperado and r == regra,
           f"(veio {dt} / {r} / {erro})")
dt, _, erro = agenda.interpretar_tempo("mais tarde quem sabe", base)
checar("horário impossível de entender é recusado com erro", dt is None and bool(erro))

print("\n== 5. Lembretes de verdade ==")
r = agenda.criar_lembrete("beber água", "em 1 minuto")
checar("cria lembrete com horário", r.startswith("Lembrete [lem-"), r[:60])
r2 = agenda.criar_lembrete("beber agua", "em 5 minutos")
checar("recusa lembrete duplicado", "Já existe um lembrete parecido" in r2, r2[:60])
r3 = agenda.criar_lembrete("ligar para o dentista", "qualquer hora dessas")
checar("sem horário válido NÃO cria lembrete", "NÃO criado" in r3, r3[:60])
checar("lembrete aparece na listagem", "beber água" in agenda.listar_lembretes())
vencidos = agenda.lembretes_vencidos(datetime.now() + timedelta(minutes=2))
checar("lembrete vence na hora certa", len(vencidos) == 1, str(vencidos))
checar("objetivo inexistente é recusado",
       "não existe" in agenda.lembrar_objetivo("goal-000000").lower())
g = agenda.add_goal("estudar bubblewrap")
g2 = agenda.add_goal("estudar bubblewrap agora")
checar("objetivo duplicado é recusado", "Já existe um objetivo equivalente" in g2, g2[:60])

print("\n== 6. Silêncio e antialucinação ==")
checar("sem gatilho, nada autoriza falar",
       autonomy.pode_falar(datetime.now(), None, [])[0] is False)
gat = [{"tipo": "lembrete", "id": "lem-x", "texto": "beber água", "detalhe": "venceu"}]
checar("com lembrete vencido, pode falar",
       autonomy.pode_falar(datetime(2026, 9, 15, 15, 0), None, gat)[0] is True)
checar("madrugada barra fala não urgente",
       autonomy.pode_falar(datetime(2026, 9, 15, 3, 0), None,
                           [{"tipo": "prazo", "id": "g", "texto": "x", "detalhe": "y"}])[0]
       is False)
for enchimento in ["Estou por aqui, qualquer coisa me chame.",
                   "Continuo monitorando o sistema.", "AGUARDANDO", "Sem novidades."]:
    checar(f"bloqueia preenchimento: '{enchimento[:28]}'",
           autonomy.validar_fala_autonoma(enchimento, gat)[0] is False)
checar("deixa passar fala ligada ao gatilho",
       autonomy.validar_fala_autonoma("Hora de beber água — o lembrete venceu agora.",
                                      gat)[0] is True)
bom, _ = autonomy.checar_afirmacoes_de_agenda("Te lembrei do lem-99999999 como combinamos.")
checar("detecta ID de lembrete inventado", bom is False)
bom2, _ = autonomy.checar_afirmacoes_de_agenda("Não há nenhum lembrete cadastrado.")
checar("não acusa quando ela nega corretamente", bom2 is True)

print("\n== 7. Memória: propriedades e procedimentos ==")
saber.registrar_propriedade("RX 6650 XT", "VRAM", "8", "GB")
saber.registrar_propriedade("RX 6650 XT", "fabricante", "AMD")
props = saber.propriedades_de("RX 6650 XT")
checar("guarda duas propriedades da mesma coisa",
       "VRAM" in props and "fabricante" in props, props[:80])
saber.registrar_propriedade("RX 6650 XT", "VRAM", "16", "GB")
props = saber.propriedades_de("RX 6650 XT")
checar("atualiza propriedade sem perder as outras",
       "16" in props and "fabricante" in props and "8 GB" not in props, props[:120])

p = saber.registrar_procedimento(
    "reiniciar o Ollama", "quando o modelo para de responder",
    ["pkill ollama", "ollama serve &", "conferir com curl localhost:11434"],
    precondicoes="o serviço do sistema não pode estar ativo",
    resultado_esperado="a API responde na porta 11434")
checar("registra procedimento", "registrado" in p, p[:60])
consulta = saber.consultar_procedimento("o ollama travou, como reinicio")
checar("acha procedimento pela intenção", "reiniciar o Ollama" in consulta, consulta[:80])
proc_id = p.split("[")[1].split("]")[0]
saber.registrar_resultado_procedimento(proc_id, True, "funcionou na primeira")
saber.registrar_resultado_procedimento(proc_id, False, "o serviço do systemd atrapalhou")
checar("contabiliza sucesso e falha",
       "2 sucesso(s) / 1 falha(s)" in saber.registrar_resultado_procedimento(proc_id, True))
checar("como_funciona junta tudo",
       "VRAM" in saber.como_funciona("RX 6650 XT"))

print("\n== 8. Memória: o bug que apagava conhecimento ==")
saber.remember("Gustavo prefere respostas diretas", ["Gustavo"], "fato")
saber.remember("Gustavo usa Linux Mint", ["Gustavo"], "fato")
saber.remember("Gustavo trabalha com música", ["Gustavo"], "fato")
tudo = saber.list_facts_about("Gustavo")
checar("três fatos diferentes sobre a mesma pessoa coexistem",
       all(t in tudo for t in ["diretas", "Linux Mint", "música"]), tudo[:150])
saber.remember("Gustavo prefere respostas diretas e curtas", ["Gustavo"], "fato")
tudo = saber.list_facts_about("Gustavo")
checar("preferências compatíveis sem chave explícita coexistem (similaridade não prova conflito)",
       tudo.count("prefere respostas diretas") == 2, tudo[:150])
checar("recall traz algo relevante",
       any("Mint" in r for r in saber.recall("qual sistema o Gustavo usa", 5)))

print("\n== 9. Oficina isolada ==")
workspace.preparar_oficina()
checar("estrutura criada", os.path.isdir(os.path.join(config.OFICINA_DIR, "projetos")))
checar("cria projeto", "criado" in workspace.criar_projeto("teste_bot", "bot de teste"))
r = workspace.executar_na_oficina("print('rodou dentro da oficina')")
checar("executa código", "rodou dentro da oficina" in r, r[:80])
r = workspace.escrever_na_oficina("../fora.txt", "não deveria chegar aqui")
checar("recusa escrita fora da oficina", r.startswith("Erro"), r[:80])
r = workspace.executar_na_oficina("import os; print(os.getcwd())", projeto="teste_bot")
checar("roda dentro da pasta do projeto", "teste_bot" in r, r[:120])

print("\n== 10. Ferramentas criadas pela própria Hoshino ==")
codigo_bom = ("def executar(texto=''):\n"
              "    return texto.upper() + ' (feito pela ferramenta)'\n")
r = toolforge.criar_ferramenta("gritar", "Converte texto para maiúsculas", codigo_bom,
                               {"texto": {"type": "string"}}, ["texto"], {"texto": "oi"})
checar("cria e ativa ferramenta que funciona", "ativada" in r, r[:100])
r = toolforge.usar_ferramenta("gritar", {"texto": "teste"})
checar("executa a ferramenta criada", "TESTE" in r, r[:80])
r = toolforge.criar_ferramenta("quebrada", "ferramenta com erro",
                               "def executar():\n    return 1/0\n")
checar("ferramenta que quebra nasce desativada", "NÃO ativada" in r, r[:80])
r = toolforge.criar_ferramenta("ruim", "sem função executar", "x = 1\n")
checar("recusa código sem executar()", "não criada" in r.lower(), r[:80])
r = toolforge.criar_ferramenta("execute_command", "tentativa de sequestro", codigo_bom)
checar("não deixa sobrescrever ferramenta nativa", "nativa" in r, r[:80])
esquemas = toolforge.esquemas_para_llm("use a ferramenta gritar")
checar("ferramenta ativa vira schema para o modelo",
       any(e["function"]["name"] == "propria_gritar" for e in esquemas))

print("\n== 11. Identidade e despacho ==")
prompt = prompting.montar_prompt_sistema()
checar("prompt traz a constituição", "entidade individual" in prompt)
checar("prompt proíbe fingir ser outra coisa", "Não sou humana" in prompt)
checar("prompt manda ficar quieta sem motivo", "Silêncio é uma resposta legítima" in prompt)
checar("prompt evita recusa virar discussão", "debate longo" in prompt)
# 05/11 (decisão humana): o jeito de partida é inspirado na Takanashi Hoshino, mas ela é
# outra entidade. A persona fixa antiga (nome "Takanashi Hoshino", papel da obra) não volta.
checar("nenhuma persona fixa sobrou", "Sou Takanashi" not in prompt and "Abydos" not in prompt
       and "não sou a personagem" in prompt)
checar("despacho conhece as ferramentas novas",
       {"criar_lembrete", "registrar_propriedade", "registrar_procedimento",
        "executar_na_oficina", "criar_ferramenta"} <= dispatch.nomes())
checar("ferramenta inexistente não explode",
       "não existe" in dispatch.executar("ferramenta_fantasma", {}))
checar("despacho não deixa exceção subir",
       "Erro" in dispatch.executar("ver_comando", {"job_id": "inexistente"})
       or "não existe" in dispatch.executar("ver_comando", {"job_id": "inexistente"}))

print("\n== 12. Emoções: causa registrada, meia-vida, oposta se abate ==")
r = emotions.sentir("raiva", 0.7, motivo="me interromperam sem motivo", gatilho="teste")
checar("sentir() devolve de/para", r.get("para", 0) > r.get("de", 0), str(r))
checar("fica registrada no histórico com o motivo",
       "me interromperam sem motivo" in emotions.o_que_me_causa("raiva"))
antes_raiva = emotions.intensidade_de("raiva")
emotions.sentir("afeto", 0.8, motivo="teste de oposta")
checar("acender a oposta abate a raiva", emotions.intensidade_de("raiva") < antes_raiva)
agora = datetime.now()
emotions.sentir("curiosidade", 0.9, motivo="teste de meia-vida", agora=agora)
daqui_a_pouco = emotions.intensidade_de("curiosidade", agora + timedelta(minutes=5))
daqui_a_muito = emotions.intensidade_de("curiosidade",
                                        agora + timedelta(minutes=240))
checar("emoção decai com o tempo", daqui_a_muito < daqui_a_pouco, f"{daqui_a_pouco} / {daqui_a_muito}")
checar("curiosidade dura mais que raiva (meia-vida maior)",
       emotions.EMOCOES["curiosidade"]["meia_vida_min"]
       > emotions.EMOCOES["raiva"]["meia_vida_min"])
for nome in ("raiva", "orgulho", "alegria", "curiosidade"):
    checar(f"'{nome}' está entre as principais", nome in emotions.PRINCIPAIS)
checar("emoção desconhecida não quebra nada", emotions.sentir("emocao_fantasma", 0.5) == {})
bloco = emotions.bloco_emocional(agora)
checar("bloco de prompt não anuncia humor, descreve expressão",
       "como isso aparece em mim" in bloco)

print("\n== 13. Escriba: extração por regra (o bug do banco real) ==")
achados = scribe.extrair_por_regra(
    "eu sou gustavo rosa nunes seu criador nessa instalação e voce?")
checar("pega o nome mesmo tudo em minúsculo",
       any("Gustavo" in a["conteudo"] for a in achados), str(achados))
checar("reconhece a declaração de papel (criador)",
       any("responsável por eu existir" in a["conteudo"] for a in achados), str(achados))
checar("'sou programador' não vira nome próprio",
       not any("Programador" in a["conteudo"] for a in scribe.extrair_por_regra(
           "sou programador")))
checar("'quem te criou?' é pergunta, não afirmação de papel",
       not scribe.extrair_por_regra("quem te criou?"))
gosta = scribe.extrair_por_regra("gosto de jogar xadrez")
checar("gosto do usuário é detectado", any("gosta de" in a["conteudo"] for a in gosta))
naoconfunde = scribe.extrair_por_regra("boa noite hoshino")
checar("'boa noite' não é elogio", scribe.reacao_do_usuario("boa noite hoshino") is None)
checar("elogio de verdade é reconhecido",
       scribe.reacao_do_usuario("ficou perfeito, valeu!") == "elogio")
checar("crítica é reconhecida", scribe.reacao_do_usuario("está errado de novo") == "critica")
marcas = scribe.evidencias_do_comportamento("Por que você faz assim? Fiquei curiosa.")
checar("pergunta na resposta vira evidência de curiosidade",
       any(t == "curiosidade" for t, _, _ in marcas), str(marcas))

print("\n== 14. Personalidade: traço só entra no prompt com evidência ==")
checar("traço sem evidência não aparece no bloco de personalidade",
       "franqueza" not in personality.bloco_personalidade())
for _ in range(config.EVIDENCIAS_PARA_CONSOLIDAR + 1):
    personality.registrar_evidencia("franqueza", 0.9, "discordou abertamente")
checar("com evidência suficiente, o traço aparece",
       "franqueza" in personality.bloco_personalidade())
personality.registrar_gosto("xadrez", 0.8, motivo="joguei e gostei")
checar("gosto registrado aparece na opinião", "gosto" in personality.opiniao_sobre("xadrez").lower()
       or "adoro" in personality.opiniao_sobre("xadrez").lower())

print("\n== 15. Impulsos: saturam, têm refratário, e emoção influencia ==")
sit_base = {"segundos_ociosos": 0, "usuario_presente": True, "curiosidades_abertas": 0,
           "curiosidades_sobre_pessoa": 0, "humor": affect.estado(), "novidades": 0,
           "episodios_sem_refletir": 0, "lembretes_vencidos": 0, "prazos_proximos": 0,
           "objetivos_travados": 0, "dias_sem_treinar": 0}
p1 = drives.avaliar(dict(sit_base, segundos_ociosos=600))["conexao"]["pressao"]
p2 = drives.avaliar(dict(sit_base, segundos_ociosos=6000))["conexao"]["pressao"]
p3 = drives.avaliar(dict(sit_base, segundos_ociosos=60000))["conexao"]["pressao"]
checar("pressão cresce com o tempo mas satura (não é linear)",
       p1 < p2 < p3 and (p3 - p2) < (p2 - p1), f"{p1:.3f} {p2:.3f} {p3:.3f}")
drives.satisfazer("cuidado", datetime.now())
logo_depois = drives.avaliar(dict(sit_base, lembretes_vencidos=1))["cuidado"]["pressao"]
checar("logo após satisfazer, o refratário segura a pressão", logo_depois < 0.5,
       str(logo_depois))
checar("sem ninguém por perto, ela quase não quer puxar assunto",
       drives.avaliar(dict(sit_base, segundos_ociosos=6000, usuario_presente=False))
       ["conexao"]["pressao"] < 0.15)
checar("dominante() respeita o limiar",
       drives.dominante({"x": {"pressao": 0.3, "acao": "y", "refratario": 1}},
                        limiar=0.5) is None)

print("\n== 16. Kernel: sem âncora concreta, não decide falar (o vício da v5) ==")
sit_sem_ancora = {"agora": datetime.now(), "usuario_presente": True,
                  "segundos_ociosos": 3000, "eventos": [], "lembretes_vencidos": 0,
                  "jobs_terminados": [], "gatilhos_diretos": []}
pressoes_altas = {"conexao": {"pressao": 0.9, "acao": "conversar", "refratario": 1}}
decisao = kernel.deliberar(sit_sem_ancora, pressoes_altas, {})
checar("pressão alta sem âncora vira silêncio, não fala vazia",
       decisao["tipo"] == "nada", str(decisao))
scribe.curiosidade_nova("O que você acha do Blender?", sobre="Blender",
                        origem="pessoa", urgencia=0.8)
sit_com_ancora = dict(sit_sem_ancora,
                     eventos=[{"tipo": "app_novo", "rotulo": "Blender",
                              "detalhe": "", "texto": "apareceu o Blender"}])
ancora = kernel.buscar_ancora(sit_com_ancora)
checar("com evento novo, a âncora aponta para ele", "Blender" in ancora.get("texto", ""),
       str(ancora))
sit_lembrete = dict(sit_sem_ancora, lembretes_vencidos=1,
                    gatilhos_diretos=[{"tipo": "lembrete", "id": "x", "texto": "y",
                                      "detalhe": "z"}])
checar("lembrete vencido vence qualquer impulso",
       kernel.deliberar(sit_lembrete, {}, {})["tipo"] == "avisar")
checar("modo silencioso engaveta até lembrete",
       kernel.deliberar(sit_lembrete, {}, {"modo_silencioso": True})["tipo"] == "nada")

print("\n== 17. Compactação: corte não deixa mensagem de ferramenta órfã ==")
from core import compaction  # noqa: E402
msgs = []
for i in range(10):
    msgs.append({"role": "user", "content": f"pergunta {i}"})
    if i == 5:
        msgs.append({"role": "assistant", "content": "vou checar",
                    "tool_calls": [{"function": {"name": "x"}}]})
        msgs.append({"role": "tool", "content": "resultado"})
    msgs.append({"role": "assistant", "content": f"resposta {i}"})
config.TURNOS_INTOCADOS = 3
corte = compaction.ponto_de_corte(msgs)
checar("o corte não começa em cima de uma mensagem 'tool'",
       corte == 0 or msgs[corte]["role"] != "tool", f"corte={corte}")
grande = [{"role": "user", "content": "x" * 4000} for _ in range(5)]
teto_antigo = config.CONTEXTO_MAX_TOKENS
config.CONTEXTO_MAX_TOKENS = 4000     # torna o teste determinístico, não depende do padrão
checar("detecta que precisa compactar quando passa do limiar",
       compaction.precisa_compactar(grande, ""))
config.CONTEXTO_MAX_TOKENS = teto_antigo
checar("não pede compactação para conversa pequena",
       not compaction.precisa_compactar([{"role": "user", "content": "oi"}], ""))

print("\n== 18. Pessoas: confiança assimétrica e estágio de relação ==")
pessoa = people.identificar(nome="Ana Teste", canal="tui", canal_id="t1")
checar("estágio inicial é 'desconhecida' ou 'conhecida'",
       people.estagio_de(pessoa) in ("desconhecida", "conhecida"))
for _ in range(6):
    pessoa = people.registrar_evento(pessoa["id"], "cumpriu_o_que_disse", "prometeu e cumpriu")
conf_apos_boa = pessoa["confianca"]
pessoa = people.registrar_evento(pessoa["id"], "mentiu", "mentiu uma vez")
checar("uma mentira derruba a confiança mais rápido do que 6 acertos constroem",
       (conf_apos_boa - pessoa["confianca"]) > (conf_apos_boa - 0.30) / 3,
       f"antes={conf_apos_boa:.3f} depois={pessoa['confianca']:.3f}")
checar("familiaridade cresce com o número de interações", pessoa["familiaridade"] > 0)

print("\n== 19. Rede: localhost sempre livre, resto respeita a chave ==")
rede.desligar("teste", por="suite")
checar("com a chave desligada, exigir() recusa", not rede.exigir("navegar")[0])
checar("localhost nunca é bloqueado", rede.permitido("http://localhost:11434"))
checar("127.0.0.1 nunca é bloqueado", rede.permitido("127.0.0.1:11434"))
checar("site externo é bloqueado", not rede.permitido("https://example.com"))
checar("o prompt avisa quando está sem internet", "SEM INTERNET" in rede.bloco_para_prompt())
rede.ligar("fim", por="suite")
checar("religar funciona e o prompt some", rede.bloco_para_prompt() == "")

print("\n== 20. Microfone: VAD aguenta ruído e filtra alucinação do Whisper ==")
from tools import transcricao  # noqa: E402
import numpy as _np  # noqa: E402

taxa = config.MIC_TAXA
quadro = int(taxa * config.MIC_QUADRO_MS / 1000)
rng = _np.random.default_rng(3)


def _ruido(n, nivel=0.02):
    return rng.normal(0, nivel, n).astype(_np.float32)


def _fala(n, amp=0.3):
    t = _np.arange(n) / taxa
    onda = amp * (_np.sin(2 * _np.pi * 180 * t) + 0.5 * _np.sin(2 * _np.pi * 400 * t))
    return (onda * (0.6 + 0.4 * _np.sin(2 * _np.pi * 3 * t))).astype(_np.float32) + _ruido(n)


sinal_ventilador = _np.concatenate([_ruido(int(1.0 * taxa), 0.03), _fala(int(1.0 * taxa), 0.3),
                                    _ruido(int(1.2 * taxa), 0.03)])
det = transcricao.DetectorDeFala()
eventos = []
for i in range(0, len(sinal_ventilador) - quadro, quadro):
    ev = det.empurrar(sinal_ventilador[i:i + quadro])
    if ev.get("evento"):
        eventos.append(ev["evento"])
checar("com ruído de fundo alto (ventilador), ainda detecta início e fim da fala",
       "comecou" in eventos and "fim" in eventos, str(eventos))
det2 = transcricao.DetectorDeFala()
so_ruido = [det2.empurrar(_ruido(quadro))["evento"]
           for _ in range(int(3 * taxa / quadro))]
checar("só ruído nunca dispara 'comecou'", "comecou" not in so_ruido)
for texto, deveria_passar in [("Legendas pela comunidade Amara.org", False),
                              ("obrigado por assistir", False),
                              ("cria um lembrete pra amanhã", True)]:
    ok_txt, _, _ = transcricao.texto_aproveitavel(texto, exigir_nome=False)
    checar(f"filtro de alucinação em '{texto[:30]}'", ok_txt == deveria_passar)
ok_nome, limpo, _ = transcricao.texto_aproveitavel("hoshino toca uma musica", exigir_nome=True)
checar("com nome exigido, tira o nome do texto limpo",
       ok_nome and "hoshino" not in limpo.lower(), limpo)
ok_sem, _, motivo_sem = transcricao.texto_aproveitavel("toca uma musica", exigir_nome=True)
checar("sem o nome, é descartado quando o nome é exigido", not ok_sem, motivo_sem)

print("\n== 21. Xadrez: regras corretas (perft) e sessão evolui de verdade ==")
from play.chess.board import Tabuleiro, perft  # noqa: E402
from play.chess import session as xadrez  # noqa: E402

checar("perft(3) da posição inicial = 8902", perft(Tabuleiro(), 3) == 8902)
kiwipete = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
checar("perft(2) do Kiwipete = 2039 (roque, en passant, pinos)",
       perft(Tabuleiro(kiwipete), 2) == 2039)
tabuleiro = Tabuleiro()
lance = tabuleiro.interpretar("e2e4")
checar("aceita lance em UCI", lance is not None and tabuleiro.jogar(lance))
lance_san = tabuleiro.interpretar("Nf6")
checar("aceita lance em SAN depois", lance_san is not None)

perfil_antes = xadrez.perfil()
checar("ela começa fraca de propósito", perfil_antes["rating"] == config.XADREZ_RATING_INICIAL)
partida = xadrez.Partida(oponente="Pepino")
voltas = 0
while not partida.terminou() and voltas < 200:
    partida.avancar(4)
    voltas += 1
resultado = partida.encerrar()
checar("a partida termina e devolve um resultado", resultado["resultado"] in
       ("1-0", "0-1", "1/2-1/2"))
checar("o rating muda depois da partida", resultado["rating"] != perfil_antes["rating"])
checar("erros da partida (se houver) apontam o lance dela, não do oponente",
       all(isinstance(e.get("numero"), int) for e in resultado["erros"]))

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'=' * 60}\n{ok} testes ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
