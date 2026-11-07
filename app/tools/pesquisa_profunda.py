"""Pesquisa profunda (pedido humano 06/11).

Uma busca simples devolve três resumos de buscador, e a entidade inventava o resto ("The Boxer" virou
"uma boxeadora"). Aqui ela lê as fontes de verdade:
- duas buscas (a pergunta e uma variação), fontes de sites diferentes;
- lê até ``fontes`` páginas e tira de cada uma o trecho que mais fala da pergunta;
- guarda até 3 imagens das próprias fontes (a imagem de capa da página) como anexos do chat
  (``compartilhado/anexos_chat``), que a Central mostra quando a resposta traz a marca ``[[imagem:ID]]``;
- devolve as fontes numeradas com os links, para ela citar [1], [2] e pôr os links no fim.

Respeita a chave da internet (core.rede) em cada leitura, com os mesmos limites de tamanho e tempo da web.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import config
from core import rede
from tools import web

MAX_FONTES = 8
MAX_IMAGENS = 3
MAX_IMAGEM_BYTES = 4 * 1024 ** 2
TRECHO = 1400
_META_IMG = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\'][^>]*>', re.I)
_CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)
_TITULO = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)
_STOP = set('a o os as de da do das dos e é em um uma para por com que qual quais como sobre the of and to in'.split())


def pasta_anexos(root=None) -> Path:
    return Path(root or config.RAIZ) / 'compartilhado/anexos_chat'


def _buscar(query, n):
    if web.DDGS is None:
        raise RuntimeError('busca indisponível: falta o pacote ddgs')
    with web.DDGS() as ddgs:
        return list(ddgs.text(query=query, max_results=n))


def _baixar(url, limite, *, aceitar):
    requests = web._requests()
    if not requests:
        raise RuntimeError('falta o pacote requests')
    resposta = requests.get(url, headers=web.CABECALHO, timeout=web.TIMEOUT, stream=True)
    resposta.raise_for_status()
    tipo = resposta.headers.get('Content-Type', '')
    if not aceitar(tipo):
        raise ValueError(f'conteúdo {tipo or "desconhecido"}')
    partes, lidos = [], 0
    for pedaco in resposta.iter_content(chunk_size=64 * 1024):
        if pedaco:
            partes.append(pedaco); lidos += len(pedaco)
            if lidos > limite:
                break
    return b''.join(partes)[:limite], resposta.url, tipo


def _palavras(texto):
    return {w for w in re.findall(r'\w{3,}', (texto or '').casefold()) if w not in _STOP}


def trecho_relevante(texto, pergunta, limite=TRECHO):
    """Parágrafos que mais citam as palavras da pergunta, na ordem original, até o limite."""
    chaves = _palavras(pergunta)
    paragrafos = [p.strip() for p in re.split(r'\n\s*\n|\n', texto or '') if len(p.strip()) > 40]
    if not paragrafos:
        return (texto or '').strip()[:limite]
    pontos = [(sum(1 for w in _palavras(p) if w in chaves), i) for i, p in enumerate(paragrafos)]
    escolhidos, total = set(), 0
    for _, i in sorted(pontos, key=lambda x: (-x[0], x[1])):
        if total >= limite:
            break
        escolhidos.add(i); total += len(paragrafos[i]) + 1
    if not any(n for n, _ in pontos):
        escolhidos = set(range(min(3, len(paragrafos))))
    return '\n'.join(paragrafos[i] for i in sorted(escolhidos))[:limite]


def _sem_acento(texto):
    import unicodedata
    texto = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return " ".join(re.findall(r"\w+", "".join(c for c in texto if not unicodedata.combining(c))))


_INICIO_DE_FRASE = {"qual", "quem", "quando", "onde", "como", "o", "a", "os", "as", "que", "pesquise", "pesquisa"}


def termos_chave(pergunta: str) -> list[str]:
    """Nomes que a resposta precisa tratar: o que está entre aspas e sequências de palavras com inicial maiúscula
    (títulos, autores). 07/11: a busca por um mangá que não existe trouxe páginas de outra obra, e a resposta tratou
    essas páginas como se fossem sobre o título pedido."""
    termos = [t.strip() for t in re.findall(r"[\"'“”‘’«]([^\"'“”‘’»]{3,80})[\"'“”‘’»]", pergunta or "")]
    for m in re.finditer(r"(?:[A-ZÀ-Ý][\wÀ-ÿ-]+)(?:\s+(?:d[eoa]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ-]+)*", pergunta or ""):
        nome = m.group(0).strip()
        if len(nome) >= 4 and _sem_acento(nome) not in _INICIO_DE_FRASE:
            termos.append(nome)
    vistos, saida = set(), []
    for t in termos:
        chave = _sem_acento(t)
        if chave and chave not in vistos and not any(chave in v for v in vistos):
            vistos.add(chave); saida.append(t)
    return saida[:4]


def imagem_da_pagina(html_text, base):
    for tag in _META_IMG.findall(html_text or ''):
        m = _CONTENT.search(tag)
        if m:
            url = urljoin(base, m.group(1).strip())
            if url.startswith(('http://', 'https://')):
                return url
    return None


def guardar_imagem(data, *, origem, pagina, titulo, root=None):
    """Valida e reduz a imagem (JPEG até 1024 px) e guarda como anexo do chat. Devolve o ID ou None."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.width * img.height > 40_000_000 or min(img.size) < 48:
            return None
        img = img.convert('RGB')
        img.thumbnail((1024, 1024))
        saida = io.BytesIO(); img.save(saida, format='JPEG', quality=82)
    except Exception:  # noqa: BLE001 - imagem quebrada não derruba a pesquisa
        return None
    jpeg = saida.getvalue()
    ident = hashlib.sha256(jpeg).hexdigest()[:12]
    pasta = pasta_anexos(root)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f'{ident}.jpg').write_bytes(jpeg)
    (pasta / f'{ident}.json').write_text(json.dumps(dict(origem=origem, pagina=pagina, titulo=titulo,
                                                        guardado=time.time()), ensure_ascii=False))
    for antigo in sorted(pasta.glob('*.jpg'), key=lambda p: p.stat().st_mtime)[:-200]:  # últimos 200
        antigo.unlink(missing_ok=True); antigo.with_suffix('.json').unlink(missing_ok=True)
    return ident


def pesquisar(pergunta, fontes=5, *, buscar=_buscar, baixar=_baixar, root=None) -> str:
    pergunta = (pergunta or '').strip()
    if not pergunta:
        return 'Erro: diga o que pesquisar.'
    pode, recusa = rede.exigir(f"pesquisar a fundo '{pergunta[:60]}'")
    if not pode:
        return recusa
    fontes = max(2, min(int(fontes or 5), MAX_FONTES))
    resultados, vistos, dominios = [], set(), {}
    for consulta in (pergunta, pergunta + ' explicação detalhada'):
        try:
            achados = buscar(consulta, 8)
        except Exception as exc:  # noqa: BLE001
            if not resultados:
                return f'Erro na pesquisa: {type(exc).__name__}: {exc}'
            achados = []
        for r in achados:
            link = (r.get('href') or '').strip()
            if not link.startswith(('http://', 'https://')) or link in vistos:
                continue
            vistos.add(link)
            dominio = urlsplit(link).netloc.removeprefix('www.')
            dominios[dominio] = dominios.get(dominio, 0) + 1
            if dominios[dominio] <= 2:  # no máximo duas páginas do mesmo site
                resultados.append(r)
    if not resultados:
        return f"Nenhum resultado para '{pergunta}'."
    lidas, imagens = [], []
    for r in resultados:
        if len(lidas) >= fontes:
            break
        link = r['href']
        ok, _ = rede.exigir(f'ler {link[:70]}', url=link)
        if not ok:
            continue
        try:
            bruto, final, _ = baixar(link, web.MAX_BYTES, aceitar=lambda t: 'html' in t or 'text' in t)
        except Exception:  # noqa: BLE001 - fonte fora do ar: segue para a próxima
            continue
        texto_html = bruto.decode('utf-8', errors='replace')
        achado = _TITULO.search(texto_html)
        titulo = r.get('title') or (achado.group(1).strip() if achado else link)
        trecho = trecho_relevante(web._extrair_texto(texto_html), pergunta)
        if len(trecho) < 80:
            continue
        lidas.append(dict(n=len(lidas) + 1, titulo=' '.join(str(titulo).split())[:140], link=final or link, trecho=trecho))
        img = imagem_da_pagina(texto_html, final or link)
        if img and len(imagens) < MAX_IMAGENS:
            try:
                dados, _, _ = baixar(img, MAX_IMAGEM_BYTES, aceitar=lambda t: t.startswith('image/'))
                ident = guardar_imagem(dados, origem=img, pagina=final or link, titulo=lidas[-1]['titulo'], root=root)
                if ident:
                    imagens.append((ident, lidas[-1]['n'], lidas[-1]['titulo']))
            except Exception:  # noqa: BLE001
                pass
    if not lidas:
        return 'Falha: achei resultados, mas não consegui ler nenhuma das páginas agora.'
    blocos = [f'PESQUISA PROFUNDA: {pergunta}', f'Fontes lidas: {len(lidas)} (de {len(resultados)} encontradas).', '']
    termos = termos_chave(pergunta)
    citam = 0
    for f in lidas:
        texto = _sem_acento(f['titulo'] + ' ' + f['trecho'])
        faltam = [t for t in termos if _sem_acento(t) not in texto]
        citam += not faltam
        aviso = f" ⚠ não cita {', '.join(repr(t) for t in faltam)}: pode ser sobre outra coisa" if faltam and termos else ''
        blocos += [f"[{f['n']}] {f['titulo']} — {f['link']}{aviso}", f"Trecho: {f['trecho']}", '']
    if termos and not citam:
        blocos += [f"ATENÇÃO: nenhuma fonte cita {', '.join(repr(t) for t in termos)}. Provavelmente não achei o que foi "
                   "pedido; diga isso em vez de responder com o que as fontes falam de outra coisa.", '']
    if imagens:
        blocos.append('Imagens das fontes (para mostrar uma, escreva a marca exata na resposta, perto do assunto):')
        blocos += [f'[[imagem:{i}]] (da fonte [{n}] {t})' for i, n, t in imagens]
        blocos.append('')
    blocos.append('Como responder: com as suas palavras, só o que os trechos dizem; cite [1], [2] e liste os links no fim. '
                  'Fonte que fala de outra coisa (outro título, outra pessoa) não vale. '
                  'Se as fontes discordam ou não cobrem algo, diga isso em vez de completar.')
    return '\n'.join(blocos)
