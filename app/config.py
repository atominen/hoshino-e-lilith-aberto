"""
Configuração central da Hoshino.

Todo caminho é absoluto, ancorado na pasta do projeto: antes cada módulo tinha o
seu `DB_PATH` relativo e ela gravava num banco vazio sempre que rodava um comando
de outro diretório.
"""
import os
from pathlib import Path
from entity_paths import carregar_entidade

CODIGO_DIR = Path(__file__).resolve().parent
RAIZ = CODIGO_DIR.parent if CODIGO_DIR.name == "app" else CODIGO_DIR
ENTIDADE_ID = os.environ.get("HOSHINO_ENTIDADE", "hoshino")
_entidade = carregar_entidade(RAIZ, ENTIDADE_ID)
ENTIDADE_NOME = _entidade.nome
ENTIDADE_DIR = _entidade.raiz
COMPARTILHADO_DIR = RAIZ / "compartilhado"
MODELOS_DIR = COMPARTILHADO_DIR / "modelos"
SHARED_RUNTIME_DIR = str(COMPARTILHADO_DIR / "runtime")
MINECRAFT_DIR = COMPARTILHADO_DIR / "servicos" / "minecraft"
MEMORY_DIR = _entidade.memory
ENTITY_CONFIG_DIR = _entidade.config


def _carregar_configuracao_local() -> None:
    """Carrega defaults da entidade sem sobrescrever variáveis já exportadas."""
    candidatos = [ENTITY_CONFIG_DIR / f"{ENTIDADE_ID}.env"]
    if ENTIDADE_ID == "hoshino":
        candidatos.append(ENTITY_CONFIG_DIR / "hoshino_v32.env")
    arquivo = next((p for p in candidatos if p.is_file()), None)
    if arquivo is None:
        return
    try:
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave, valor = chave.strip(), valor.strip()
            if not chave or not chave.replace("_", "").isalnum():
                continue
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {"'", '"'}:
                valor = valor[1:-1]
            os.environ.setdefault(chave, valor)
    except OSError:
        pass


_carregar_configuracao_local()

# Experiência local; registros novos do histórico usam UTC. Não converte legado.
LOCAL_TIMEZONE = os.environ.get("HOSHINO_TIMEZONE", "America/Sao_Paulo")

# Pontes distintas para que uma entidade não controle o bot da outra.
MINECRAFT_BRIDGE_PORT = int(os.environ.get("HOSHINO_MC_BRIDGE_PORT", "8766" if ENTIDADE_ID == "lilith" else "8765"))
MINECRAFT_BRIDGE_URL = os.environ.get("HOSHINO_MINECRAFT_BRIDGE", f"http://127.0.0.1:{MINECRAFT_BRIDGE_PORT}").rstrip("/")

# ---------------------------------------------------------------- modelo
_OLLAMA_PORT = {'hoshino':11435,'lilith':11436,'alistair':11437}[ENTIDADE_ID]
OLLAMA_URL = os.environ.get("HOSHINO_OLLAMA_URL", f"http://127.0.0.1:{_OLLAMA_PORT}/api/chat")
MODEL_NAME = os.environ.get(
    "HOSHINO_MODEL",
    {'hoshino':"hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M",
     'lilith':"lilith-qwen3.5-9b:latest", 'alistair':"alistair-qwen3.5-4b:latest"}[ENTIDADE_ID],
)
# Contexto máximo enviado ao Ollama.
# Altere este número para aumentar/diminuir o contexto da Hoshino.
# Exemplos: 8192, 16384, 32768.
# Também pode ser definido sem editar este arquivo com:
#   export HOSHINO_CONTEXT_TOKENS=16384
CONTEXTO_LLM_TOKENS = int(os.environ.get("HOSHINO_CONTEXT_TOKENS", os.environ.get("HOSHINO_NUM_CTX", "16384")))
# Alias mantido para o restante do projeto.
NUM_CTX = CONTEXTO_LLM_TOKENS
# NUM_CTX continua sendo o teto configurado, não uma janela alocada em todo pedido.
ADAPTIVE_CONTEXT = os.environ.get("HOSHINO_ADAPTIVE_CONTEXT", "1") != "0"
# Só os custos do roteamento; não habilita concorrência nem muda perfis físicos.
DYNAMIC_RESOURCE_PROFILES = os.environ.get("HOSHINO_DYNAMIC_RESOURCE_PROFILES", "1") != "0"
TIMEOUT_LLM = int(os.environ.get("HOSHINO_TIMEOUT_LLM", "300"))
MAX_PASSOS_FERRAMENTA = int(os.environ.get("HOSHINO_MAX_PASSOS_FERRAMENTA", "10"))
# Chamadas simultâneas são limitadas para proteger a máquina. Ações que alteram
# estado continuam seriais no executor da interface.
MAX_FERRAMENTAS_PARALELAS = int(os.environ.get("HOSHINO_MAX_FERRAMENTAS_PARALELAS", "6"))

# "Thinking" nativo do Ollama (suportado pela família Qwen3, e presumivelmente
# por qwen3.5): o modelo separa o raciocínio num campo próprio (message.thinking)
# em vez de vazar <think>...</think> dentro do content. Mais barato de tratar e
# mais confiável do que o regex de limpar_raciocinio() em main.py — que continua
# ativo como rede de segurança, porque alguns builds ainda vazam a tag mesmo com
# a flag ligada. Esta opção permite o modo; o Resource Manager escolhe por
# ciclo, desligado em conversa comum e ligado para raciocínio/reflexão/tarefas.
# Desligue com HOSHINO_THINKING=0 se o modelo não respeitar a
# flag direito (teste com `ollama run qwen3.5:9b --think "teste"` primeiro).
THINKING = os.environ.get("HOSHINO_THINKING", "1") != "0"

# Teto de tokens gerados por chamada (pensamento + resposta juntos). Sem isto o
# Ollama usa o padrão do próprio modelo — que para alguns pulls do Qwen3.5 é
# baixo o bastante para o "thinking" sozinho consumir o orçamento inteiro,
# deixando `content` vazio mesmo com o raciocínio correto. Se isto acontecer de
# novo mesmo com o teto alto, o problema está noutro lugar (ver retry em
# ciclo_de_ferramentas, main.py).
NUM_PREDICT = int(os.environ.get("HOSHINO_NUM_PREDICT", "4096"))
# Streaming do Ollama permite observar progresso sem gerar inputs artificiais.
STREAM_LLM = os.environ.get("HOSHINO_STREAM_LLM", "1") != "0"
# Teto separado para tarefas longas. O limite normal continua valendo para
# conversas curtas e loops acidentais.
MAX_PASSOS_TAREFA_LONGA = int(os.environ.get("HOSHINO_MAX_PASSOS_TAREFA_LONGA", "128"))
# Projeto de programação ("Projeto: ..."): passos por ativação; "continue" retoma do checkpoint.
MAX_PASSOS_PROJETO = int(os.environ.get("HOSHINO_MAX_PASSOS_PROJETO", "60"))
# Saída por decisão no modo projeto (pedido humano 29/10, com 32K): 4096 cortava o raciocínio no meio da tool call.
PROJETO_SAIDA = int(os.environ.get("HOSHINO_PROJETO_SAIDA", "8192"))
# Intermediário 2B só CPU (29/10, pedido humano; core/intermediario.py). Vazio = desligado.
INTERMEDIARIO_URL = os.environ.get("HOSHINO_INTERMEDIARIO_URL", "")
INTERMEDIARIO_MODELO = os.environ.get("HOSHINO_INTERMEDIARIO_MODELO", "qwen3.5:2b-q4_K_M")
INTERMEDIARIO_MODELOS_DIR = os.environ.get("HOSHINO_INTERMEDIARIO_MODELOS_DIR",
                                           str(COMPARTILHADO_DIR / "modelos" / "ollama-intermediario"))
INTERMEDIARIO_TIMEOUT = float(os.environ.get("HOSHINO_INTERMEDIARIO_TIMEOUT", "10"))
# 30/10: no Minecraft o 2B deu 58/98 alarmes falsos (sem travas) com ação+resultado; fica desligado até o detector ser
# refeito (assinatura por regra + modelo só na equivalência incerta). "1" liga para ensaio.
INTERMEDIARIO_MINECRAFT = os.environ.get("HOSHINO_INTERMEDIARIO_MINECRAFT", "0") == "1"
# Revisor de memória (07/11, pedido humano; mind/revisor_memoria.py): segunda chamada que confere cada anotação do
# escriba antes de guardar. "entidade" = o mesmo modelo dela (55/59 e 19/20 na avaliação); "intermediario" = o 2B só
# CPU (descartava tudo); "desligado" = grava como antes.
REVISOR_MEMORIA = os.environ.get("HOSHINO_REVISOR_MEMORIA", "entidade")
# Amostragem das respostas (07/11, pedido humano): "qwen" = recomendação da Qwen (sem raciocínio 0,7/0,8/20, com
# raciocínio 0,6/0,95/20); "padrao" = o padrão do Ollama (0,8/0,9/40), como era antes.
AMOSTRAGEM = os.environ.get("HOSHINO_AMOSTRAGEM", "qwen")
# Pergunta de fato liga o raciocínio (07/11, pedido humano: "o problema não é o tempo"). "0" volta ao de antes.
RACIOCINIO_EM_FATOS = os.environ.get("HOSHINO_RACIOCINIO_EM_FATOS", "1") == "1"
MAX_CICLOS_SEM_PROGRESSO = int(os.environ.get("HOSHINO_MAX_CICLOS_SEM_PROGRESSO", "6"))
PROGRESS_UI_SEGUNDOS = float(os.environ.get("HOSHINO_PROGRESS_UI_SEGUNDOS", "1"))
PROGRESS_SEM_EVENTO_AVISO = float(os.environ.get("HOSHINO_PROGRESS_SEM_EVENTO_AVISO", "45"))
PROGRESS_SNAPSHOT_RETENTION = float(os.environ.get("HOSHINO_PROGRESS_SNAPSHOT_RETENTION", "4"))

# Quanto tempo o Ollama mantém o modelo carregado na VRAM entre chamadas. Ela é
# chamada de forma esparsa (só quando decide falar ou agir), então sem isto o
# Ollama descarrega pelo padrão dele e recarrega do zero na próxima vez — atraso
# perceptível numa GPU de VRAM limitada como a RX 6650 XT. "-1m" (duração negativa:
# o Ollama exige unidade) mantém o modelo
# quente enquanto a entidade está acordada: dormir descarrega explicitamente e o
# gerenciador de recursos libera pesos ociosos quando outra carga precisa da GPU.
OLLAMA_KEEP_ALIVE = os.environ.get("HOSHINO_KEEP_ALIVE", "-1m")
# Ciclo de vida do daemon: limites curtos no boot/encerramento evitam que a
# interface fique presa indefinidamente quando o serviço local está indisponível.
OLLAMA_STARTUP_TIMEOUT = float(os.environ.get("HOSHINO_OLLAMA_STARTUP_TIMEOUT", "3.5"))
OLLAMA_RESTART_WAIT = float(os.environ.get("HOSHINO_OLLAMA_RESTART_WAIT", "15"))
OLLAMA_SHUTDOWN_TIMEOUT = float(os.environ.get("HOSHINO_OLLAMA_SHUTDOWN_TIMEOUT", "10"))

# ---------------------------------------------------------------- contexto
# Compactação automática: quando a conversa passa do limiar do contexto máximo,
# o trecho mais antigo vira um resumo estruturado e sai do histórico — mas antes
# passa pelo escriba, para que nada durável se perca junto.
CONTEXTO_MAX_TOKENS = int(os.environ.get("HOSHINO_CTX_MAX", str(NUM_CTX)))
LIMIAR_COMPACTACAO = 0.70        # compacta ao passar de 70% do teto
TURNOS_INTOCADOS = 6             # últimos turnos nunca são compactados
CHARS_POR_TOKEN = 3.6            # estimativa para português; conservadora
RESUMO_MAX_CHARS = 1800

# ---------------------------------------------------------------- caminhos
DB_PATH = str(MEMORY_DIR / "sqlite" / f"{ENTIDADE_ID}.db")
VECTOR_DIR = str(MEMORY_DIR / "vector" / "db")
SELF_MODEL_PATH = str(_entidade.identity / "self_model.json")
CONSTITUICAO_PATH = str(_entidade.identity / "constitution.json")
VERSOES_DIR = str(_entidade.identity / "versions")
RUNTIME_DIR = str(_entidade.runtime)
HUGGINGFACE_CACHE_DIR = str(MODELOS_DIR / "huggingface")
os.environ.setdefault("HF_HOME", HUGGINGFACE_CACHE_DIR)
# Daemon Ollama exclusivo da Hoshino: não misture o armazenamento do projeto
# com ~/.ollama nem com outro serviço do sistema.
OLLAMA_MODELS_DIR = os.environ.get("HOSHINO_OLLAMA_MODELS", str(MODELOS_DIR / ("ollama" if ENTIDADE_ID=='hoshino' else 'ollama-'+ENTIDADE_ID)))
OLLAMA_HOST = os.environ.get("HOSHINO_OLLAMA_HOST", f"127.0.0.1:{_OLLAMA_PORT}")
MINECRAFT_USERNAME = os.environ.get("HOSHINO_MINECRAFT_USERNAME", f"{ENTIDADE_NOME}MC")
JOBS_DIR = str(_entidade.runtime / "jobs")
EVENT_LOG_DIR = str(_entidade.runtime / "event_log")
ESTADO_MENTE = str(_entidade.runtime / "estado_mente.json")
BUS_DIR = str(_entidade.runtime / "bus")
ENTREGA_SAIDA = str(_entidade.runtime / "entregas" / "saida")
ENTREGA_ENTRADA = str(_entidade.runtime / "entregas" / "entrada")
OFICINA_DIR = str(_entidade.workspace)
VENV_PROJETO = str(COMPARTILHADO_DIR / "ambientes" / "principal")
VENV_VOZ = str(COMPARTILHADO_DIR / "ambientes" / "voz")

# ---------------------------------------------------------------- execução
# Conversa contínua: espera curta para agrupar mensagens enviadas em sequência.
# A ideia é deixar a pessoa terminar um pensamento antes de Hoshino responder.
DEBOUNCE_CONVERSA_MS = int(os.environ.get("HOSHINO_DEBOUNCE_MS", "900"))
MAX_MENSAGENS_LOTE = int(os.environ.get("HOSHINO_MAX_MENSAGENS_LOTE", "8"))

TIMEOUT_COMANDO_PADRAO = 30
TIMEOUT_COMANDO_MAX = 900
LIMITE_SAIDA_CHARS = 8000
TIMEOUT_OFICINA_PADRAO = 30
MEMORIA_MAX_OFICINA_MB = 2048
CPU_MAX_OFICINA_SEG = 60
ARQUIVO_MAX_OFICINA_MB = 256
TAMANHO_MAX_DOWNLOAD_MB = 100

# ---------------------------------------------------------------- ritmo
HEARTBEAT_SEGUNDOS = int(os.environ.get("HOSHINO_HEARTBEAT_SEGUNDOS", "8"))
SILENCIO_POR_PADRAO = True
HORARIO_SILENCIO = (0, 7)
FALAR_VOZ_AUTONOMO = os.environ.get("HOSHINO_FALAR_VOZ_AUTONOMO", "1") != "0"
# Entrada falada pode receber resposta falada; entrada escrita fica em texto por padrão.
FALAR_VOZ_TEXTO = os.environ.get("HOSHINO_FALAR_VOZ_TEXTO", "0") != "0"

# Quanto tempo entre falas espontâneas. Lembrete vencido fura a fila; "puxar
# assunto" é o mais contido de todos.
INTERVALO_MIN_FALA_AUTONOMA = 600        # piso geral: 10 min
INTERVALO_INICIATIVA_SOCIAL = 1500       # puxar assunto: 25 min
OCIOSO_PARA_INICIATIVA = 240             # só puxa assunto após 4 min de silêncio
AUSENTE_APOS = 1800                      # 30 min: interação deixa de ser recente; não prova ausência

# Ação interna (pesquisar, refletir, jogar) não interrompe ninguém, então é mais
# solta que a fala — mas ainda tem limite para não ocupar a GPU o dia inteiro.
# Afrouxado a pedido: ela ficava tempo demais sem iniciativa própria.
INTERVALO_MIN_ACAO_INTERNA = int(os.environ.get("HOSHINO_INTERVALO_ACAO_INTERNA", "60"))
ACOES_INTERNAS_POR_HORA = int(os.environ.get("HOSHINO_ACOES_INTERNAS_HORA", "36"))
INTERVALO_MIN_OLHAR_TELA = 900           # ela só se serve da tela a cada 15 min

# Quanto a presença da pessoa no computador reduz a pressão de ócio (o impulso
# que leva a jogar xadrez, investigar algo etc. quando não está acontecendo
# nada). 1.0 = nenhuma diferença entre presente e ausente; quanto menor, mais
# ela se contém enquanto a pessoa está por perto. Subido de 0.35 pra 0.55 a
# pedido — ela ainda se contém um pouco com a pessoa ali, mas bem menos.
OCIO_FATOR_PRESENTE = 0.55
# Quanto tempo depois de decidir jogar/explorar por tédio até o impulso de ócio
# poder disparar de novo (fora de diretiva sustentada, que não usa isto — ver
# tools/agenda.diretiva_ativa). Descido de 1800s (30 min) pra 900 (15 min) a
# pedido — ela retoma iniciativa própria bem mais rápido quando não tem nada
# acontecendo.
OCIO_REFRATARIO_SEGUNDOS = 900

# Oportunidade de deliberação PRIVADA, não gatilho de fala nem emoção imposta.
# Um tick calmo continua gratuito. A escolha pode ser não fazer nada.
INICIATIVA_INATIVIDADE_SEGUNDOS = 120
INICIATIVA_INTERVALO_SEGUNDOS = 300
INICIATIVA_CONTINUACAO_SEGUNDOS = 60
INICIATIVA_MAX_PASSOS = 8
INICIATIVA_MAX_FERRAMENTAS = 12
INICIATIVA_ORCAMENTO_SEGUNDOS = 240

# Despertar (pedido humano 06/11): ao acordar, ela se localiza e manda UMA mensagem
# no chat, sem precisar de âncora nem de presença confirmada. Oferecido uma vez por
# processo, entre o atraso e o fim da janela; some se a pessoa falar primeiro.
DESPERTAR_ATIVO = os.environ.get("HOSHINO_DESPERTAR", "1") != "0"
DESPERTAR_ATRASO_SEGUNDOS = int(os.environ.get("HOSHINO_DESPERTAR_ATRASO", "20"))
DESPERTAR_JANELA_SEGUNDOS = int(os.environ.get("HOSHINO_DESPERTAR_JANELA", "900"))

# ---------------------------------------------------------------- mente
TAXA_APRENDIZADO_TRACO = 0.02    # traços mudam devagar, e só com evidência
EVIDENCIAS_PARA_CONSOLIDAR = 8   # evidências antes de o traço entrar no prompt
MEIA_VIDA_HUMOR_MIN = 45         # humor volta à linha de base em ~45 min
REFLEXAO_A_CADA_EPISODIOS = 12   # ciclo de reflexão (Generative Agents)
REFLEXAO_INTERVALO_MIN = 60
# Janela da reflexão longa diária. O período atravessa meia-noite por padrão.
REFLEXAO_NOTURNA_INICIO = int(os.environ.get("HOSHINO_REFLEXAO_NOTURNA_INICIO", "22"))
REFLEXAO_NOTURNA_FIM = int(os.environ.get("HOSHINO_REFLEXAO_NOTURNA_FIM", "6"))
REFLEXAO_NOTURNA_MAX_CHARS = int(os.environ.get("HOSHINO_REFLEXAO_NOTURNA_MAX_CHARS", "20000"))
MAX_CURIOSIDADES_ABERTAS = 12
# Pressão necessária para ela agir sozinha. Tentei baixar isto de 0.65 pra 0.55
# a pedido, mas quebrava o teste de regressão ("tick calmo não chama o modelo":
# com 4 curiosidades abertas a pressão de curiosidade já bate 0.58, calibrada
# de propósito pra ficar abaixo de 0.65) — ou seja, 0.55 fazia ela agir em
# situação que o teste diz explicitamente que ainda é "calma". Mantive 0.65 e
# apostei em ACOES_INTERNAS_POR_HORA/INTERVALO_MIN_ACAO_INTERNA (mais frequência
# quando ELA já decide agir) e na diretiva sustentada (que nem passa por este
# limiar) pra dar mais liberdade sem violar esse invariante.
LIMIAR_IMPULSO_ACAO = 0.65
# Pressão para ela puxar assunto. Não precisa ser alto porque o guarda de verdade
# é outro: sem âncora concreta (pergunta em aberto, novidade real) a decisão de
# falar nem acontece. Com 0.62 e uma pergunta guardada, ela puxa assunto por volta
# de 30 min de silêncio; sem nada guardado, perto de 45.
LIMIAR_IMPULSO_FALA = 0.62

# ---------------------------------------------------------------- memória
RECALL_EPISODIOS = 3
RECALL_CONHECIMENTO = 5
PESOS_RECALL = {
    "similaridade": 0.55,
    "recencia": 0.15,
    "confianca": 0.20,
    "uso": 0.10,
}

# ---------------------------------------------------------------- jogo
XADREZ_TEMPO_LANCE_MS = 1200      # tempo de cálculo por lance dela
XADREZ_LANCES_POR_TICK = 2        # a partida corre sem travar a interface
XADREZ_RATING_INICIAL = 800       # começa fraca de propósito: evolução medível

# ---------------------------------------------------------------- rede
# A chave real fica em runtime/rede.json (ver core/rede.py). Isto é só o padrão
# do primeiro boot: HOSHINO_OFFLINE=1 começa sem internet.
INTERNET_PADRAO = os.environ.get("HOSHINO_OFFLINE", "0") != "1"

# ---------------------------------------------------------------- microfone
MIC_ATIVO = os.environ.get("HOSHINO_MIC", "1") != "0"
MIC_MODO = os.environ.get("HOSHINO_MIC_MODO", "segurar")   # aberto | segurar
MIC_DISPOSITIVO = os.environ.get("HOSHINO_MIC_DISPOSITIVO", "")  # vazio = padrão do SO
MIC_PTT_ATALHO = os.environ.get("HOSHINO_MIC_PTT", "<ctrl>+<shift>+space")
MIC_TAXA = 16000                 # Whisper trabalha em 16 kHz
MIC_QUADRO_MS = 30               # tamanho do quadro de análise
FALA_MIN_MS = 400                # abaixo disso é tosse, clique, batida na mesa
FALA_MAX_SEG = 45                # corta sozinho se alguém falar sem parar
VAD_SILENCIO_MS = 900            # silêncio que encerra a fala
VAD_FATOR_RUIDO = 3.2            # limiar = ruído de fundo medido x isto
VAD_QUADROS_INICIO = 3           # quadros acima do limiar para considerar que começou
MIC_GANHO_MAX = 12.0             # teto da normalização (microfone ruim, fala baixa)
MIC_EXIGIR_NOME = os.environ.get("HOSHINO_MIC_NOME", "0") == "1"  # só ouve se chamarem
MIC_PALAVRAS_MIN = 2             # transcrição com menos palavras é descartada
TRANSCRITOR = os.environ.get("HOSHINO_TRANSCRITOR", "faster")  # auto|faster|whisper|vosk
WHISPER_MODELO = os.environ.get("HOSHINO_WHISPER", "large-v3")
WHISPER_IDIOMA = "pt"
WHISPER_BEAM_SIZE = int(os.environ.get("HOSHINO_WHISPER_BEAM", "3"))
WHISPER_PRELOAD = os.environ.get("HOSHINO_WHISPER_PRELOAD", "1") != "0"
# Palavras que o modelo escuta melhor quando sabe que podem aparecer.
VOCABULARIO = [ENTIDADE_NOME, "Ollama", "oficina", "lembrete", "xadrez"]

# Conversa de voz de alta qualidade. O ASR fica na CPU para preservar a VRAM
# para o Qwen; a diarização trabalha em janelas e distingue no máximo dois
# oradores sem presumir seus nomes.
AUDIO_CONTINUO = os.environ.get("HOSHINO_AUDIO_CONTINUO", "1") != "0"
AUDIO_MAX_ORADORES = int(os.environ.get("HOSHINO_AUDIO_MAX_ORADORES", "2"))
AUDIO_JANELA_SEG = float(os.environ.get("HOSHINO_AUDIO_JANELA_SEG", "8"))
AUDIO_SILENCIO_FLUSH_SEG = float(os.environ.get("HOSHINO_AUDIO_FLUSH_SEG", "1.2"))
AUDIO_DIARIZACAO = os.environ.get("HOSHINO_AUDIO_DIARIZACAO", "0") != "0"
AUDIO_DIARIZACAO_MODELO = os.environ.get(
    "HOSHINO_AUDIO_DIARIZACAO_MODELO", "pyannote/speaker-diarization-community-1")
AUDIO_DEVICE = os.environ.get("HOSHINO_AUDIO_DEVICE", "cpu")
AUDIO_COMPUTE_TYPE = os.environ.get("HOSHINO_AUDIO_COMPUTE", "int8")
HOSHINO_HF_TOKEN = os.environ.get("HOSHINO_HF_TOKEN", "")

# ---------------------------------------------------------------- voz local
# Backend local de voz; padrão: Kokoro em CPU. Outros backends permanecem opcionais por compatibilidade.
TTS_BACKEND = os.environ.get("HOSHINO_TTS_BACKEND", "kokoro")
TTS_MODEL = os.environ.get("HOSHINO_TTS_MODEL", "hexgrad/Kokoro-82M")
TTS_DESIGN_MODEL = ""
TTS_DEVICE = os.environ.get("HOSHINO_TTS_DEVICE", "cpu")
TTS_VOICE = os.environ.get("HOSHINO_TTS_VOICE", "pf_dora")
TTS_SPEED = float(os.environ.get("HOSHINO_TTS_SPEED", "1.0"))
TTS_REFERENCE = os.environ.get(
    "HOSHINO_TTS_REFERENCE",
    os.path.join(RUNTIME_DIR, "voice", f"{ENTIDADE_ID}_reference.wav"))
TTS_REFERENCE_TEXT = os.environ.get(
    "HOSHINO_TTS_REFERENCE_TEXT",
    f"Eu sou a {ENTIDADE_NOME}. Eu falo com naturalidade e presto atenção ao que está acontecendo.")
TTS_DESIGN_DESCRIPTION = os.environ.get(
    "HOSHINO_TTS_DESIGN_DESCRIPTION",
    "voz feminina jovem, natural, brasileira, clara e suave, fala conversacional, "
    "timbre caloroso, articulação nítida, ritmo espontâneo, sem voz infantilizada")
TTS_DESIGN_TEXT = os.environ.get(
    "HOSHINO_TTS_DESIGN_TEXT",
    TTS_REFERENCE_TEXT)
TTS_XVECTOR_ONLY = os.environ.get("HOSHINO_TTS_XVECTOR_ONLY", "0") == "1"
TTS_KEEP_LOADED = os.environ.get("HOSHINO_TTS_KEEP_LOADED", "1") != "0"

# ---------------------------------------------------------------- imagem local
# Qwen-Image 2.1 Q6_K via stable-diffusion.cpp/Vulkan.
# Os pesos permanecem na RAM; a GPU executa o trabalho de difusão.
IMAGE_MODEL_ID = os.environ.get(
    "HOSHINO_IMAGE_MODEL", "Qwen-Image-2.1-Q6_K")

IMAGE_RUNTIME_DIR = RUNTIME_DIR

_IMAGE_DIR = os.path.join(
    str(MODELOS_DIR), "imagem", "qwen-image-2.1")

IMAGE_DIFFUSION_MODEL = os.environ.get(
    "HOSHINO_IMAGE_DIFFUSION_MODEL",
    os.path.join(_IMAGE_DIR, "qwen_image_2.1-Q6_K.gguf"))

IMAGE_LLM_MODEL = os.environ.get(
    "HOSHINO_IMAGE_LLM_MODEL",
    os.path.join(_IMAGE_DIR, "Qwen3-VL-8B-Instruct-Q5_K_M.gguf"))

IMAGE_VAE_MODEL = os.environ.get(
    "HOSHINO_IMAGE_VAE_MODEL",
    os.path.join(_IMAGE_DIR, "qwen_image_2.1_vae_bf16.safetensors"))

# Alias mantido para compatibilidade com código/diagnósticos antigos.
IMAGE_MODEL_FILE = os.path.basename(IMAGE_DIFFUSION_MODEL)

IMAGE_OUTPUT_DIR = os.environ.get(
    "HOSHINO_IMAGE_OUTPUT_DIR", os.path.join(IMAGE_RUNTIME_DIR, "imagens"))

IMAGE_DEVICE = os.environ.get("HOSHINO_IMAGE_DEVICE", "vulkan0")
IMAGE_SD_CLI = os.environ.get(
    "HOSHINO_IMAGE_SD_CLI",
    str(COMPARTILHADO_DIR / "servicos/stable-diffusion.cpp/build/bin/sd-cli"))

# Encoders e VAE calculam na CPU; difusão usa Vulkan com pesos na RAM.
IMAGE_BACKEND = os.environ.get(
    "HOSHINO_IMAGE_BACKEND", "te=cpu,diffusion=vulkan0,vae=cpu")
IMAGE_PARAMS_BACKEND = os.environ.get(
    "HOSHINO_IMAGE_PARAMS_BACKEND", "te=cpu,diffusion=cpu,vae=cpu")
IMAGE_MAX_VRAM_GIB = float(
    os.environ.get("HOSHINO_IMAGE_MAX_VRAM_GIB", "7.0"))

IMAGE_SAMPLER = os.environ.get("HOSHINO_IMAGE_SAMPLER", "euler")
IMAGE_TIMEOUT = int(os.environ.get("HOSHINO_IMAGE_TIMEOUT", "900"))
IMAGE_STEPS = int(os.environ.get("HOSHINO_IMAGE_STEPS", "16"))
IMAGE_CFG = float(os.environ.get("HOSHINO_IMAGE_CFG", "1.0"))
IMAGE_WIDTH = int(os.environ.get("HOSHINO_IMAGE_WIDTH", "768"))
IMAGE_HEIGHT = int(os.environ.get("HOSHINO_IMAGE_HEIGHT", "768"))
IMAGE_KEEP_LOADED = os.environ.get("HOSHINO_IMAGE_KEEP_LOADED", "0") != "0"

# ---------------------------------------------------------------- voz
# VOZ continua existindo como nome lógico para compatibilidade de integrações antigas;
# a implementação padrão é local e CPU quando TTS_BACKEND=kokoro.
VOZ = os.environ.get("HOSHINO_VOZ", f"{ENTIDADE_NOME}-local")
VOZ_ATIVA = os.environ.get("HOSHINO_VOZ_ATIVA", "1") != "0"


def garantir_pastas():
    for p in (RUNTIME_DIR, HUGGINGFACE_CACHE_DIR, JOBS_DIR, EVENT_LOG_DIR, OFICINA_DIR, VERSOES_DIR,
              BUS_DIR, ENTREGA_SAIDA, ENTREGA_ENTRADA):
        Path(p).mkdir(parents=True, exist_ok=True)


def estimar_tokens(texto: str) -> int:
    """Estimativa barata, sem tokenizer. Erra para mais, que é o lado seguro."""
    return int(len(texto or "") / CHARS_POR_TOKEN) + 1
