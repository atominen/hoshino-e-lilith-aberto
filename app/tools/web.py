"""
Web — pesquisa e leitura de página, com a chave de rede no caminho.

Mudanças em relação à versão anterior, que era três linhas felizes:

* **Respeita a chave da internet.** Toda entrada passa por `core.rede.exigir`.
  Desligada, devolve uma recusa legível em vez de um traceback de DNS.
* **Não morre por falta de pacote.** `ddgs` e `beautifulsoup4` viraram
  opcionais: sem eles, a busca avisa o que instalar e a leitura de página cai num
  extrator de HTML em Python puro, que é pior mas funciona.
* **Limites.** Timeout, teto de bytes baixados e truncagem por caracteres. Uma
  página de 40 MB não pode entupir a memória nem o contexto dela.
* **Resultado utilizável.** A busca devolve título, link e resumo em formato
  estável, e a leitura tenta recortar o corpo do texto em vez de despejar o menu
  do site inteiro.
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
try:
    from ddgs import DDGS
except Exception:
    try:
        from ddgs import DDGS
    except Exception:
        DDGS = None
from core import rede  # noqa: E402

TIMEOUT = 15
MAX_BYTES = 3 * 1024 * 1024        # 3 MB de HTML é muito mais que o suficiente
MAX_CHARS = 5000
CABECALHO = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Hoshino/6.0"}

_LIXO = re.compile(r"<(script|style|nav|footer|header|aside|form|noscript|svg)[^>]*>.*?"
                   r"</\1>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_ESPACOS = re.compile(r"[ \t\r\f\v]+")
_LINHAS = re.compile(r"\n{3,}")


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        return None


def web_search(query: str, max_results: int = 3) -> str:
    """Pesquisa na web. Recusa em silêncio educado quando a rede está desligada."""
    query = (query or "").strip()
    if not query:
        return "Erro: preciso de algo para pesquisar."
    pode, recusa = rede.exigir(f"pesquisar '{query[:60]}'")
    if not pode:
        return recusa

    if DDGS is None:
        return ("Busca indisponível: falta o pacote ddgs. "
                "Instale `ddgs>=9.16.0` no ambiente da Hoshino.")

    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(query=query, max_results=max(1, min(8, max_results))))
    except Exception as e:  # noqa: BLE001 — a biblioteca levanta de tudo
        return f"Erro na pesquisa: {type(e).__name__}: {e}"

    if not resultados:
        return f"Nenhum resultado para '{query}'."
    blocos = []
    for r in resultados:
        blocos.append(f"Título: {r.get('title', '(sem título)')}\n"
                      f"Link: {r.get('href', '')}\n"
                      f"Resumo: {(r.get('body') or '')[:400]}")
    return "\n\n".join(blocos)


def _extrair_texto(bruto: str) -> str:
    """Corpo da página. Usa BeautifulSoup quando existe; senão, regex honesta."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        limpo = _LIXO.sub(" ", bruto)
        limpo = _TAGS.sub("\n", limpo)
        limpo = html.unescape(limpo)
        limpo = _ESPACOS.sub(" ", limpo)
        return _LINHAS.sub("\n\n", limpo).strip()

    sopa = BeautifulSoup(bruto, "html.parser")
    for tag in sopa(["script", "style", "nav", "footer", "header", "aside", "form",
                     "noscript", "svg"]):
        tag.extract()
    # <article> e <main> costumam ser o texto de verdade; o resto é moldura.
    alvo = sopa.find("article") or sopa.find("main") or sopa
    return _LINHAS.sub("\n\n", alvo.get_text(separator="\n", strip=True))


def fetch_page(url: str, max_chars: int = MAX_CHARS) -> str:
    """Lê uma página e devolve o texto. Respeita a chave da internet."""
    url = (url or "").strip()
    if not url:
        return "Erro: preciso da URL."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    pode, recusa = rede.exigir(f"abrir {url[:70]}", url=url)
    if not pode:
        return recusa

    requests = _requests()
    if not requests:
        return "Não consigo acessar a web: falta o pacote requests (pip install requests)."

    try:
        resposta = requests.get(url, headers=CABECALHO, timeout=TIMEOUT, stream=True)
        resposta.raise_for_status()
        tipo = resposta.headers.get("Content-Type", "")
        if "html" not in tipo and "text" not in tipo and "json" not in tipo:
            return f"A URL devolveu {tipo or 'conteúdo binário'}, que eu não sei ler como texto."
        bruto, lidos = [], 0
        for pedaco in resposta.iter_content(chunk_size=64 * 1024, decode_unicode=False):
            if not pedaco:
                continue
            lidos += len(pedaco)
            bruto.append(pedaco)
            if lidos >= MAX_BYTES:
                break
        conteudo = b"".join(bruto).decode(resposta.encoding or "utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return f"Não consegui abrir {url}: {type(e).__name__}: {e}"

    texto = _extrair_texto(conteudo)
    if not texto.strip():
        return f"A página {url} abriu, mas não achei texto legível nela."
    if len(texto) > max_chars:
        texto = texto[:max_chars] + f"\n\n[...cortado; a página tem ~{len(texto)} caracteres]"
    return texto


def baixar(url: str, destino: str = "", nome: str = "") -> str:
    """Baixa um arquivo para a oficina dela, com teto de tamanho."""
    url = (url or "").strip()
    pode, recusa = rede.exigir(f"baixar {url[:70]}", url=url)
    if not pode:
        return recusa
    requests = _requests()
    if not requests:
        return "Não consigo baixar: falta o pacote requests."
    if not url.startswith(("http://", "https://")):
        return "Erro: só baixo de http(s)."

    pasta = destino or os.path.join(config.OFICINA_DIR, "baixados")
    os.makedirs(pasta, exist_ok=True)
    nome = (nome or os.path.basename(url.split("?")[0]) or "arquivo").replace("/", "_")[:80]
    caminho = os.path.join(pasta, nome)
    teto = config.TAMANHO_MAX_DOWNLOAD_MB * 1024 * 1024

    try:
        with requests.get(url, headers=CABECALHO, timeout=TIMEOUT, stream=True) as r:
            r.raise_for_status()
            declarado = int(r.headers.get("Content-Length") or 0)
            if declarado > teto:
                return (f"Recusei: o arquivo tem {declarado / 1048576:.1f} MB e meu teto é "
                        f"{config.TAMANHO_MAX_DOWNLOAD_MB} MB.")
            escritos = 0
            with open(caminho, "wb") as f:
                for pedaco in r.iter_content(chunk_size=256 * 1024):
                    if not pedaco:
                        continue
                    escritos += len(pedaco)
                    if escritos > teto:
                        f.close()
                        os.remove(caminho)
                        return (f"Abortei no meio: passou de "
                                f"{config.TAMANHO_MAX_DOWNLOAD_MB} MB.")
                    f.write(pedaco)
    except Exception as e:  # noqa: BLE001
        return f"Falhou o download de {url}: {type(e).__name__}: {e}"

    return f"Baixei para {caminho} ({escritos / 1024:.0f} KB)."
