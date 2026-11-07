import base64
import io
import os
import sys
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# Importação tolerante, como em memory/vector/chroma_store.py: main.py importa
# este módulo no topo, então um `import mss` seco aqui derrubava a Hoshino
# inteira numa máquina sem o pacote — a visão é uma capacidade a menos, não um
# motivo para ela não abrir.
DISPONIVEL = False
ERRO_IMPORT = ""
try:
    import mss
    from PIL import Image

    DISPONIVEL = True
except Exception as e:  # noqa: BLE001
    ERRO_IMPORT = str(e)


def _indisponivel() -> str:
    return (f"Visão indisponível: falta pacote ({ERRO_IMPORT}). "
            f"Instale com: pip install mss Pillow")

# Largura máxima do print antes de mandar pro modelo. Qwen3.5 é multimodal nativo,
# mas uma imagem em resolução cheia consome muito contexto/VRAM à toa — para
# descrever uma tela, 1280px de largura já é mais que suficiente.
MAX_WIDTH = 1280
JPEG_QUALITY = 70

# Anexo vindo de canal externo (Discord, por ex.): reconheço pela extensão da
# URL. Não é tratamento de imagem de verdade (sem checar magic bytes), mas
# cobre o caso real — anexo de chat quase sempre chega com extensão certa.
EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
ANEXO_MAX_BYTES = 8 * 1024 * 1024   # 8 MB: além disso eu nem baixo
EXTENSOES_TEXTO = (".txt", ".md", ".rst", ".csv", ".json", ".jsonl", ".yaml", ".yml",
                   ".toml", ".ini", ".cfg", ".log", ".py", ".js", ".ts", ".html", ".xml")
ANEXO_TEXTO_MAX_BYTES = 96 * 1024
ANEXO_TEXTO_MAX_CHARS = 12000


def parece_imagem(url: str) -> bool:
    caminho = (url or "").split("?", 1)[0].lower()
    return caminho.endswith(EXTENSOES_IMAGEM)


def parece_texto(url: str) -> bool:
    """Reconhece anexos textuais que podem entrar diretamente no contexto."""
    caminho = (url or "").split("?", 1)[0].lower()
    return caminho.endswith(EXTENSOES_TEXTO)


def baixar_texto_url(url: str) -> str:
    """Baixa um anexo textual pequeno sem executar nem interpretar seu conteúdo.

    O limite em bytes protege a máquina de downloads grandes; o limite em
    caracteres protege a janela de contexto do modelo. Arquivos binários e
    formatos opacos continuam só como metadado para não virar lixo no prompt.
    """
    from core import rede
    pode, recusa = rede.exigir(f"baixar anexo de texto de {url[:70]}", url=url)
    if not pode:
        raise PermissionError(recusa)
    resposta = requests.get(url, stream=True, timeout=15)
    resposta.raise_for_status()
    tamanho = int(resposta.headers.get("Content-Length") or 0)
    if tamanho > ANEXO_TEXTO_MAX_BYTES:
        raise ValueError(f"anexo tem {tamanho // 1024} KB, acima do limite de "
                         f"{ANEXO_TEXTO_MAX_BYTES // 1024} KB")
    partes, total = [], 0
    for pedaco in resposta.iter_content(chunk_size=16 * 1024):
        if not pedaco:
            continue
        total += len(pedaco)
        if total > ANEXO_TEXTO_MAX_BYTES:
            raise ValueError(f"anexo passou de {ANEXO_TEXTO_MAX_BYTES // 1024} KB durante o download")
        partes.append(pedaco)
    bruto = b"".join(partes)
    if b"\x00" in bruto[:4096]:
        raise ValueError("o anexo parece binário")
    texto = bruto.decode("utf-8", "replace")
    if len(texto) > ANEXO_TEXTO_MAX_CHARS:
        return texto[:ANEXO_TEXTO_MAX_CHARS] + "\n[... anexo cortado para caber no contexto]"
    return texto or "(anexo de texto vazio)"


def baixar_imagem_url(url: str) -> str:
    """Baixa uma imagem de uma URL externa (anexo de Discord, por ex.) e devolve
    em base64 já redimensionada — mesmo tratamento da captura de tela, para não
    estourar contexto/VRAM com uma imagem em resolução cheia. Levanta exceção se
    não der: quem chama decide o que dizer sobre o anexo que não abriu."""
    # Passa pela chave da internet como web.py e entrega.py já faziam. Sem isto,
    # desligar a rede não desligava de verdade: um anexo de imagem continuava
    # sendo baixado de fora, que é justamente o que core/rede.py promete impedir.
    from core import rede
    pode, recusa = rede.exigir(f"baixar imagem de {url[:70]}", url=url)
    if not pode:
        raise PermissionError(recusa)

    if not DISPONIVEL:
        raise RuntimeError(_indisponivel())

    resposta = requests.get(url, timeout=15)
    resposta.raise_for_status()
    bruto = resposta.content
    if len(bruto) > ANEXO_MAX_BYTES:
        raise ValueError(f"imagem tem {len(bruto) // 1024} KB, acima do limite de "
                         f"{ANEXO_MAX_BYTES // 1024} KB")
    img = Image.open(io.BytesIO(bruto)).convert("RGB")
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img = img.resize((MAX_WIDTH, int(img.height * ratio)))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _capturar_tela_base64() -> str:
    """Tira um print do monitor principal, redimensiona e devolve em base64 (JPEG)."""
    with mss.mss() as sct:
        # monitors[0] é a união de todos os monitores; monitors[1] é o principal.
        # Em setup com múltiplos monitores, troque para monitors[0] se quiser tudo.
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img = img.resize((MAX_WIDTH, int(img.height * ratio)))

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def observar_tela(pergunta: str = None) -> str:
    """Captura a tela atual e pede para o próprio modelo (visão nativa do Qwen3.5)
    descrever o que está vendo, ou responder a uma pergunta específica sobre o
    conteúdo visual. Roda como uma chamada isolada ao Ollama: a imagem não entra
    no histórico principal da conversa, só o texto de volta entra."""
    if not DISPONIVEL:
        return _indisponivel()

    try:
        img_b64 = _capturar_tela_base64()
    except Exception as e:
        return f"Erro ao capturar a tela: {e}"

    prompt = (pergunta or "").strip() or "Descreva objetivamente o que está sendo exibido na tela agora."

    payload = {
        "model": config.MODEL_NAME,
        "stream": False,
        # Thinking fica desligado aqui de propósito: isto roda a cada ~15 min
        # (INTERVALO_MIN_OLHAR_TELA) como uma descrição rápida de tela, não uma
        # fala pensada — raciocínio extra só atrasaria sem ganho real.
        "think": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "messages": [
            {"role": "user", "content": prompt, "images": [img_b64]}
        ],
    }

    try:
        return _consultar(payload)
    except requests.exceptions.ConnectionError:
        return "Erro: não consegui falar com o Ollama (ele está rodando em 127.0.0.1:11435?)."
    except Exception as e:
        return f"Erro ao consultar o modelo de visão: {e}"


def observar_imagem(caminho: str, pergunta: str = None) -> str:
    """Descreve uma imagem local explicitamente recebida pela Hoshino."""
    if not DISPONIVEL:
        return _indisponivel()
    try:
        img = Image.open(caminho).convert("RGB")
        if img.width > MAX_WIDTH:
            proporcao = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, int(img.height * proporcao)))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        imagem = base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        return f"Erro ao abrir a imagem recebida: {exc}"
    payload = {
        "model": config.MODEL_NAME, "stream": False, "think": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "messages": [{"role": "user", "content": (pergunta or "Descreva objetivamente esta imagem recebida.").strip(),
                      "images": [imagem]}],
    }
    try:
        return _consultar(payload)
    except Exception as exc:  # noqa: BLE001
        return f"Erro ao consultar o modelo de visão: {exc}"


def _consultar(payload):
    """Mesmo daemon/lease, perfil parcial aprovado e fases de latência separadas."""
    from core import gpu_resource,resource_manager,diagnostics
    begin=time.monotonic()
    profile=next((e for e in resource_manager.executor_catalog() if e['model']==payload['model']),None)
    # Reutiliza a janela/perfil medidos, não inventa carga GPU total para visão.
    # 30/10: 256 tokens cortavam a descrição de uma página inteira (Wikipédia, 1749×956) e a visão devolvia
    # "resposta incompleta"; 1024 cabem em ~40 s a 25 tokens/s.
    options=dict(payload.get('options',{}),num_ctx=profile['num_ctx'] if profile else config.NUM_CTX,
                 num_predict=1024)
    payload=dict(payload,options=options)
    with gpu_resource.lease('vision',model=payload['model'],cpu_fallback=True) as acquired:
        admitted=time.monotonic()
        diagnostics.emit('vision.admitted',backend=acquired['backend'],model=payload['model'],
                         queue_seconds=admitted-begin,gpu_layers=acquired.get('gpu_layers'),
                         context_tokens=options['num_ctx'])
        try:
            # Imagem grande (~15 s no projetor da CPU) + 1024 tokens passavam de 60 s.
            response=requests.post(config.OLLAMA_URL,json=gpu_resource.routed_payload(payload,acquired),timeout=(3,120))
            response.raise_for_status();data=response.json()
            complete=data.get('done') is True and data.get('done_reason','stop')=='stop'
            diagnostics.emit('vision.completed',backend=acquired['backend'],model=payload['model'],
                queue_seconds=admitted-begin,http_seconds=time.monotonic()-admitted,
                load_seconds=data.get('load_duration',0)/1e9,prompt_seconds=data.get('prompt_eval_duration',0)/1e9,
                eval_seconds=data.get('eval_duration',0)/1e9,complete=complete,
                prompt_eval_count=data.get('prompt_eval_count'),eval_count=data.get('eval_count'))
            if not complete or data.get('error'):
                return 'Erro: visão retornou resposta incompleta; não é uma observação confirmada.'
            return str(data.get('message',{}).get('content','')).strip() or 'Erro: visão sem descrição confirmada.'
        except Exception as exc:
            diagnostics.emit('vision.failed',level='ERROR',backend=acquired['backend'],
                             queue_seconds=admitted-begin,http_seconds=time.monotonic()-admitted,
                             error_type=type(exc).__name__)
            raise
