"""Automação de navegador controlada pela Hoshino.

É uma camada complementar ao controle visual do desktop:
- desktop.py controla a interface por mouse/teclado;
- browser.py controla DOM/texto do navegador quando isso é mais confiável.

Não expõe JavaScript arbitrário, shell ou acesso livre ao filesystem.
Usa um perfil persistente próprio em workspace/browser_profile, portanto login
feito nesse navegador controlado pela Hoshino não depende do navegador pessoal.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import concurrent.futures
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config
from tools import workspace

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hoshino-browser")
_WORKER = threading.local()
_BROWSER_CALL_TIMEOUT = float(os.environ.get("HOSHINO_BROWSER_CALL_TIMEOUT", "25"))
_BROWSER_NAV_TIMEOUT_MS = int(os.environ.get("HOSHINO_BROWSER_NAV_TIMEOUT_MS", "20000"))
_BROWSER_DOM_TIMEOUT_MS = int(os.environ.get("HOSHINO_BROWSER_DOM_TIMEOUT_MS", "5000"))
_STATE = {
    "playwright": None,
    "context": None,
    "page_ids": {},
    "pages": {},
    "next_page_id": 1,
    "active_page_id": None,
}


def _paths() -> tuple[Path, Path]:
    raiz = Path(config.OFICINA_DIR)
    return raiz / "browser_profile", raiz / "browser-browsers"


class BrowserOutcomeUncertain(TimeoutError):
    """O worker começou; timeout não confirma cancelamento nem ausência de efeito."""


def _failure(action, exc):
    if isinstance(exc, BrowserOutcomeUncertain):
        return f"RESULTADO_INCERTO: {action}: {exc}; não repetir automaticamente."
    if _browser_closed(exc):
        return (f"Falha {action}: o navegador foi fechado (janela fechada ou processo encerrado). "
                "A sessão foi descartada; browser_abrir abre um navegador novo.")
    return f"Falha {action}: {type(exc).__name__}: {exc}"


def _browser_closed(exc) -> bool:
    """06/11: a pessoa fechou a janela do navegador controlado; o Playwright só devolve TargetClosedError."""
    return type(exc).__name__ == "TargetClosedError" or "has been closed" in str(exc)


def _reset_session() -> None:
    """Esquece a sessão morta (no fio do Playwright) para a próxima chamada abrir outra.

    Os IDs de aba continuam crescendo: uma aba nova nunca herda o nome de uma aba que sumiu."""
    ctx, pw = _STATE["context"], _STATE["playwright"]
    _STATE.update(context=None, playwright=None, page_ids={}, pages={}, active_page_id=None, closed=False)
    for closer in (getattr(ctx, "close", None), getattr(pw, "stop", None)):
        try:
            if closer:
                closer()
        except Exception:  # noqa: BLE001 - a sessão já estava morta
            pass


def _run(fn, timeout: float | None = None):
    """Executa uma ação do navegador com limite de tempo.

    Uma ação de ambiente não pode segurar o fio da conversa indefinidamente.
    Se exceder o limite, devolvemos erro explícito para a cognição em vez de
    deixar a fila de mensagens presa.
    """
    # Playwright permanece no seu único fio. _get_context é chamado dentro
    # desse fio: reenfileirá-lo e aguardar a mesma fila causa deadlock.
    if getattr(_WORKER, 'active', False):
        return fn()
    limite = _BROWSER_CALL_TIMEOUT if timeout is None else float(timeout)
    def owned():
        _WORKER.active = True
        try:
            return fn()
        finally:
            _WORKER.active = False
    future = _EXECUTOR.submit(owned)
    try:
        return future.result(timeout=limite)
    except concurrent.futures.TimeoutError as exc:
        if future.done():
            return future.result()  # preserva exceção própria do worker
        if not future.cancel():
            raise BrowserOutcomeUncertain(
                f"Prazo de {limite:.1f}s excedido; worker já iniciou e pode produzir efeito"
            ) from exc
        raise TimeoutError(
            f"Ação do navegador excedeu {limite:.1f}s na fila e foi cancelada antes de iniciar."
        ) from exc


def _installed_executable_options(chromium, cache: Path) -> dict:
    """Reutiliza o engine instalado; o perfil continua próprio da entidade.

    O SDK determina a revisão exata. Não redireciona configuração explícita,
    não escolhe outra revisão e não instala nada durante uma abertura.
    """
    expected = Path(chromium.executable_path)
    if expected.is_file() or 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
        return {}
    # Compatibilidade com preparar(), que instala no cache da entidade.
    # O padrão do SDK usa o cache compartilhado do usuário primeiro.
    for parent in expected.parents:
        if parent.name.startswith('chromium-'):
            candidate = cache / parent.name / expected.relative_to(parent)
            if candidate.is_file():
                return {'executable_path': str(candidate)}
            break
    return {}


def _get_context():
    def inner():
        if _STATE["context"] is not None and _STATE.get("closed"):
            _reset_session()
        if _STATE["context"] is not None:
            return _STATE["context"]
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright não está instalado. Instale `playwright` no venv da Hoshino."
            ) from exc
        profile, cache = _paths()
        profile.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        pw = sync_playwright().start()
        try:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=False,
                viewport=None,
                **_installed_executable_options(pw.chromium, cache),
            )
        except Exception:
            pw.stop()
            raise
        try:
            ctx.set_default_timeout(_BROWSER_DOM_TIMEOUT_MS)
            ctx.set_default_navigation_timeout(_BROWSER_NAV_TIMEOUT_MS)
        except Exception:
            pass
        _STATE["playwright"] = pw
        _STATE["context"] = ctx
        _STATE["closed"] = False
        on = getattr(ctx, "on", None)
        if on:  # janela fechada pela pessoa: a próxima chamada reabre em vez de falhar para sempre
            on("close", lambda *_: _STATE.__setitem__("closed", True))
        return ctx
    return _run(inner)


def _register_page(page) -> str:
    """Dá uma identidade estável à página durante a sessão da Hoshino."""
    key = id(page)
    existing = _STATE["page_ids"].get(key)
    if existing:
        _STATE["pages"][existing] = page
        return existing
    page_id = f"aba-{_STATE['next_page_id']:02d}"
    _STATE["next_page_id"] += 1
    _STATE["page_ids"][key] = page_id
    _STATE["pages"][page_id] = page
    _STATE["active_page_id"] = page_id
    return page_id


def _limpar_paginas_fechadas(ctx) -> None:
    atuais = {id(p) for p in ctx.pages}
    for page_id, page in list(_STATE["pages"].items()):
        if id(page) not in atuais:
            _STATE["pages"].pop(page_id, None)
            _STATE["page_ids"].pop(id(page), None)
            if _STATE["active_page_id"] == page_id:
                _STATE["active_page_id"] = None
    if _STATE["active_page_id"] is None and ctx.pages:
        _STATE["active_page_id"] = _register_page(ctx.pages[-1])


def preparar() -> str:
    """Instala a biblioteca/Chromium usando o Python atual da Hoshino."""
    profile, cache = _paths()
    profile.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    try:
        import playwright  # noqa: F401
    except ImportError:
        # O browser é uma capacidade do próprio processo da Hoshino, então o
        # pacote precisa entrar no Python atual/venv do projeto, não no venv da
        # oficina. O Chromium continua fora dele, no cache dedicado.
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright>=1.59"],
                capture_output=True, text=True, timeout=900,
            )
        except subprocess.TimeoutExpired:
            return "A instalação de Playwright passou de 15 minutos."
        if r.returncode != 0:
            return "Falha ao instalar Playwright:\n" + (r.stderr or r.stdout).strip()[-1200:]
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)
    try:
        p = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=900, env=env,
        )
    except subprocess.TimeoutExpired:
        return "A instalação do Chromium do Playwright passou de 15 minutos."
    if p.returncode != 0:
        return ("Falha ao instalar Chromium para a Hoshino:\n" +
                (p.stderr or p.stdout).strip()[-1200:])
    return f"Navegador preparado. Perfil: {profile}. Cache: {cache}."


def estado() -> str:
    try:
        def inner():
            try:
                import playwright  # noqa: F401
            except ImportError:
                return "browser: Playwright não instalado"
            aberto = _STATE["context"] is not None
            ativo = _STATE.get("active_page_id") or "nenhuma"
            return (f"browser: Playwright disponível; sessão={'aberta' if aberto else 'fechada'}; "
                    f"aba_ativa={ativo}")
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return f"browser indisponível: {type(exc).__name__}: {exc}"


def abrir(url: str = "", nova_aba: bool = True, aba: str = "") -> str:
    alvo = (url or "about:blank").strip()
    from urllib.parse import urlsplit, unquote
    from core import entity_access
    parsed=urlsplit(alvo)
    if parsed.scheme=='file' and not entity_access.permitted(unquote(parsed.path)):
        return 'ACESSO_BLOQUEADO: página local de outra entidade.'

    def navegar():
        ctx = _get_context()
        paginas = ctx.pages
        if nova_aba or not paginas:
            page = ctx.new_page()
        else:
            page = _page(ctx, None, aba)
        resposta = page.goto(alvo, wait_until="commit", timeout=_BROWSER_NAV_TIMEOUT_MS)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=_BROWSER_DOM_TIMEOUT_MS)
        except Exception:
            # O compromisso de navegação já ocorreu. Uma página pode continuar
            # carregando sem que isso impeça a Hoshino de observar seu estado.
            pass
        page_id = _register_page(page)
        titulo = page.title() or "(sem título)"
        status = getattr(resposta, "status", None)
        # 06/11: "404 Not Found" voltava como "Navegador aberto" e contava como sucesso; a Lilith montou
        # youtube.com/@<nome falado> e seguiu sem perceber que o endereço não existia.
        if type(status) is int and status >= 400:
            inicio = "Não existe" if status in (404, 410) else "Falha"
            return (f"{inicio}: a página respondeu HTTP {status} ({titulo}) | {page.url} | aba={page_id}. "
                    "Se o endereço foi montado a partir de um nome, ele não foi confirmado: procure antes "
                    "(busca do próprio site, como https://www.youtube.com/results?search_query=nome, ou web_search) "
                    "e abra pelo resultado.")
        return f"Navegador aberto: {titulo} | {page.url} | aba={page_id}"

    def inner():
        try:
            return navegar()
        except Exception as exc:  # noqa: BLE001
            if not _browser_closed(exc):
                raise
            # A janela foi fechada antes de navegar: nada aconteceu nesta tentativa; uma sessão nova, uma vez.
            _reset_session()
            return navegar()
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao abrir navegador", exc)


def paginas() -> str:
    def inner():
        ctx = _get_context()
        _limpar_paginas_fechadas(ctx)
        linhas = []
        for i, page in enumerate(ctx.pages):
            page_id = _register_page(page)
            try:
                titulo = page.title()
            except Exception:
                titulo = "(sem título)"
            linhas.append(f"[{page_id}] (índice={i}) {titulo or '(sem título)'} | {page.url}")
        return "Abas:\n" + "\n".join(linhas) if linhas else "Nenhuma aba aberta."
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao listar abas", exc)


def _page(ctx, indice: int | None = None, aba: str = ""):
    _limpar_paginas_fechadas(ctx)
    if aba:
        page = _STATE["pages"].get(aba)
        if page is None:
            abertas = ", ".join(_STATE["pages"]) or "nenhuma"
            raise ValueError(f"aba '{aba}' não existe nesta sessão; abas abertas: {abertas}")
        _STATE["active_page_id"] = aba
        return page
    paginas_atuais = ctx.pages
    if not paginas_atuais:
        raise ValueError("nenhuma aba aberta")
    if indice is None:
        ativo = _STATE.get("active_page_id")
        if ativo in _STATE["pages"]:
            return _STATE["pages"][ativo]
        page = paginas_atuais[-1]
    else:
        i = max(0, min(int(indice), len(paginas_atuais) - 1))
        page = paginas_atuais[i]
    _STATE["active_page_id"] = _register_page(page)
    return page


def info(indice: int | None = None, aba: str = "", max_chars: int = 7000) -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        texto = page.locator("body").inner_text(timeout=10000)
        if len(texto) > max_chars:
            texto = texto[:max_chars] + "\n...[truncado]"
        page_id = _register_page(page)
        # Leitura fixa do viewport, sem expor JavaScript arbitrário ao modelo.
        viewport = page.evaluate('() => ({x: window.scrollX, y: window.scrollY, height: window.innerHeight, total: document.documentElement.scrollHeight})')
        return (f"Aba: {page_id}\nTítulo: {page.title()}\nURL: {page.url}\n"
                f"Viewport: x={viewport['x']}, y={viewport['y']}, altura={viewport['height']}, total={viewport['total']}\n\n{texto}")
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao ler página", exc)


def _locator(page, alvo: str, tipo: str):
    tipo = (tipo or "texto").lower()
    if not alvo:
        raise ValueError("alvo vazio")
    if tipo == "css":
        return page.locator(alvo).first
    if tipo == "role":
        if ":" not in alvo:
            raise ValueError("role exige 'papel:nome', por exemplo 'button:Play'")
        papel, nome = alvo.split(":", 1)
        return page.get_by_role(papel.strip(), name=nome.strip(), exact=False).first
    if tipo == "label":
        return page.get_by_label(alvo, exact=False).first
    return page.get_by_text(alvo, exact=False).first


def clicar(alvo: str, tipo: str = "texto", indice: int | None = None, aba: str = "") -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        loc = _locator(page, alvo, tipo)
        loc.scroll_into_view_if_needed()
        loc.click(timeout=15000)
        page_id = _register_page(page)
        return f"Clique no navegador executado: {alvo} | aba={page_id}"
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao clicar no navegador", exc)


def preencher(alvo: str, texto: str, tipo: str = "css", indice: int | None = None, aba: str = "") -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        loc = _locator(page, alvo, tipo)
        loc.scroll_into_view_if_needed()
        loc.fill(texto)
        page_id = _register_page(page)
        return f"Campo preenchido: {alvo} | aba={page_id}"
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao preencher navegador", exc)


def pressionar(tecla: str, alvo: str = "", tipo: str = "css", indice: int | None = None, aba: str = "") -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        if alvo:
            _locator(page, alvo, tipo).press(tecla)
        else:
            page.keyboard.press(tecla)
        page_id = _register_page(page)
        return f"Tecla no navegador: {tecla} | aba={page_id}"
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao pressionar no navegador", exc)


def rolar(pixels: int = 700, indice: int | None = None, aba: str = "") -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        page.mouse.wheel(0, int(pixels))
        page_id = _register_page(page)
        return f"Rolagem de {int(pixels)} px executada | aba={page_id}."
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao rolar navegador", exc)


def _navegar_historico(acao: str, indice: int | None = None, aba: str = "") -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        if acao == "voltar":
            page.go_back(wait_until="commit", timeout=_BROWSER_NAV_TIMEOUT_MS)
        elif acao == "avancar":
            page.go_forward(wait_until="commit", timeout=_BROWSER_NAV_TIMEOUT_MS)
        else:
            page.reload(wait_until="commit", timeout=_BROWSER_NAV_TIMEOUT_MS)
        page_id = _register_page(page)
        return f"{acao.capitalize()} concluído | aba={page_id} | título={page.title()} | url={page.url}"
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure(f"ao {acao} no navegador", exc)


def voltar(indice: int | None = None, aba: str = "") -> str:
    return _navegar_historico("voltar", indice, aba)


def avancar(indice: int | None = None, aba: str = "") -> str:
    return _navegar_historico("avancar", indice, aba)


def recarregar(indice: int | None = None, aba: str = "") -> str:
    return _navegar_historico("recarregar", indice, aba)


def screenshot(nome: str = "browser.png", indice: int | None = None, aba: str = "") -> str:
    def inner():
        page = _page(_get_context(), indice, aba)
        destino = Path(config.OFICINA_DIR) / "tmp" / Path(nome).name
        destino.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(destino), full_page=False)
        return f"Screenshot salvo em {destino}."
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao capturar navegador", exc)


def fechar(indice: int | None = None, aba: str = "") -> str:
    def inner():
        ctx = _STATE["context"]
        if ctx is None:
            return "Navegador já está fechado."
        if indice is None:
            ctx.close()
            _STATE["context"] = None
            if _STATE["playwright"] is not None:
                _STATE["playwright"].stop()
            _STATE["playwright"] = None
            return "Sessão do navegador fechada."
        page = _page(ctx, indice, aba)
        page_id = _register_page(page)
        page.close()
        _limpar_paginas_fechadas(ctx)
        return f"Aba {page_id} fechada."
    try:
        return _run(inner)
    except Exception as exc:  # noqa: BLE001
        return _failure("ao fechar navegador", exc)


@atexit.register
def _cleanup():
    try:
        _run(lambda: fechar(None))
    except Exception:
        pass
