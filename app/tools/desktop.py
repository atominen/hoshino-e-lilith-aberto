"""Controle do desktop Linux.

A Hoshino pode abrir aplicativos, focar janelas e manipular mouse/teclado.
A visão continua sendo feita por `tools.vision`: este módulo só executa ações.

Preferência:
  1. PyAutoGUI, quando disponível;
  2. xdotool, quando disponível (X11).

Nenhum comando de shell arbitrário é exposto aqui. O conjunto de ações é pequeno
propositalmente: abrir, focar, clicar, mover, digitar, teclas, atalhos, rolagem,
esperar e fechar uma janela. Para instalação/configuração de sistema, use
`tools.apps`/`tools.terminal`, que possuem as guardas de risco já existentes.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

DISPONIVEL = False
MOTIVO = ""
_BACKEND = ""
_pyautogui = None

try:
    import pyautogui as _pyautogui  # type: ignore
    _pyautogui.FAILSAFE = True
    _pyautogui.PAUSE = 0.08
    DISPONIVEL = True
    _BACKEND = "pyautogui"
except Exception as exc:  # noqa: BLE001
    MOTIVO = str(exc)
    if shutil.which("xdotool"):
        DISPONIVEL = True
        _BACKEND = "xdotool"


CHAVES = {
    "enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape",
    "tab": "Tab", "space": "space", "backspace": "BackSpace", "delete": "Delete",
    "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
    "left": "Left", "right": "Right", "up": "Up", "down": "Down",
    "ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "super",
    "win": "super", "meta": "super",
}


def estado() -> str:
    if not DISPONIVEL:
        return "desktop indisponível: instale pyautogui ou xdotool."
    sessao = os.environ.get("XDG_SESSION_TYPE", "desconhecida")
    return f"desktop disponível via {_BACKEND}; sessão={sessao}"


def _validar_xy(x, y):
    if x is None or y is None:
        raise ValueError("x e y são obrigatórios para esta ação")
    return int(x), int(y)


def _normalizar_chave(chave: str) -> str:
    c = (chave or "").strip().lower()
    if not c:
        raise ValueError("tecla vazia")
    return CHAVES.get(c, chave)


def _janelas_xdotool(padrao: str = "") -> list[dict]:
    if not shutil.which("xdotool"):
        return []
    args = ["xdotool", "search", "--name", padrao or ".*", "getwindowname"]
    # xdotool não aceita getwindowname nessa forma para múltiplas janelas de
    # maneira confiável; fazemos IDs primeiro e depois nome.
    proc = subprocess.run(["xdotool", "search", "--name", padrao or ".*"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    itens = []
    for raw in proc.stdout.splitlines():
        wid = raw.strip()
        if not wid:
            continue
        nome = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True,
                              text=True).stdout.strip()
        itens.append({"id": wid, "titulo": nome})
    return itens


def listar_janelas() -> str:
    if _BACKEND == "xdotool":
        janelas = _janelas_xdotool()
        if not janelas:
            return "Nenhuma janela encontrada pelo xdotool."
        return "Janelas:\n" + "\n".join(f"- {j['id']}: {j['titulo']}" for j in janelas[:80])
    # wmctrl é opcional; serve para diagnóstico mesmo usando pyautogui.
    if shutil.which("wmctrl"):
        p = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
        return p.stdout.strip() or "Nenhuma janela listada."
    return "PyAutoGUI controla mouse/teclado, mas não enumera janelas. Instale wmctrl para listar títulos."


def focar_janela(titulo: str) -> str:
    alvo = (titulo or "").strip()
    if not alvo:
        return "Erro: informe parte do título da janela."
    if _BACKEND == "xdotool":
        p = subprocess.run(["xdotool", "search", "--name", alvo],
                           capture_output=True, text=True)
        wid = (p.stdout.splitlines() or [""])[0].strip()
        if not wid:
            return f"Nenhuma janela com '{alvo}'."
        r = subprocess.run(["xdotool", "windowactivate", "--sync", wid],
                           capture_output=True, text=True)
        return f"Janela ativada: {wid}" if r.returncode == 0 else r.stderr.strip()
    if shutil.which("wmctrl"):
        p = subprocess.run(["wmctrl", "-a", alvo], capture_output=True, text=True)
        return f"Janela ativada: {alvo}" if p.returncode == 0 else p.stderr.strip()
    return "Não tenho backend de foco de janela instalado. Instale xdotool ou wmctrl."


def abrir_url(url: str) -> str:
    alvo = (url or "").strip()
    if not re.match(r"^(https?|ftp|discord|spotify):", alvo, re.I):
        return "Erro: URL deve começar com http://, https://, ftp://, discord: ou spotify:."
    try:
        subprocess.Popen(["xdg-open", alvo], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return f"Pedido de abrir URL enviado: {alvo}. A página ainda não foi verificada."
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui abrir a URL: {exc}"


def _resolver_desktop(nome: str) -> list[str] | None:
    termo = (nome or "").strip().casefold()
    if not termo:
        return None
    candidatos = []
    diretorios = [Path.home() / ".local/share/applications", Path.home() / ".local/share/flatpak/exports/share/applications", Path("/usr/share/applications"), Path("/var/lib/flatpak/exports/share/applications")]
    for base in diretorios:
        if not base.is_dir():
            continue
        for arq in base.glob("*.desktop"):
            try:
                linhas = arq.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            nome_entry = ""
            exec_entry = ""
            no_display = False
            for linha in linhas:
                if linha.startswith("Name=") and not nome_entry:
                    nome_entry = linha[5:].strip()
                elif linha.startswith("Exec=") and not exec_entry:
                    exec_entry = linha[5:].strip()
                elif linha.strip() == "NoDisplay=true":
                    no_display = True
            if no_display or not exec_entry or not nome_entry:
                continue
            ne = nome_entry.casefold()
            stem = arq.stem.casefold()
            if termo == ne or termo == stem or termo in ne or ne in termo:
                # Remove campos de substituição do desktop entry. Não usa shell.
                exec_entry = re.sub(r"\s%[fFuUdDnNickvm]", "", exec_entry)
                try:
                    partes = __import__('shlex').split(exec_entry)
                except ValueError:
                    continue
                if partes:
                    candidatos.append((0 if termo == ne else 1, partes))
    if not candidatos:
        return None
    candidatos.sort(key=lambda x: x[0])
    return candidatos[0][1]


def abrir_pasta(caminho: str) -> str:
    alvo = (caminho or "").strip()
    if not alvo:
        return "Erro: informe o caminho da pasta."
    caminho_real = Path(os.path.expanduser(alvo)).resolve(strict=False)
    if not caminho_real.exists():
        return f"A pasta não existe: {caminho_real}"
    if not caminho_real.is_dir():
        return f"Não é uma pasta: {caminho_real}"
    try:
        subprocess.Popen(["xdg-open", str(caminho_real)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return f"Pedido de abrir pasta enviado: {caminho_real}. A janela ainda não foi verificada."
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui abrir a pasta '{caminho_real}': {exc}"


def abrir_aplicativo(aplicativo: str, argumentos: str = "") -> str:
    nome = (aplicativo or "").strip()
    if not nome:
        return "Erro: informe o aplicativo."
    partes = nome.split()
    candidato = partes[0]
    # Atalhos úteis e previsíveis.
    aliases = {
        "navegador": "xdg-open https://www.google.com",
        "browser": "xdg-open https://www.google.com",
        "spotify": "spotify",
        "firefox": "firefox",
        "discord": "discord",
        "steam": "steam",
    }
    if candidato.lower() in aliases and aliases[candidato.lower()] == "xdg-open https://www.google.com":
        return abrir_url("https://www.google.com")
    comando = aliases.get(candidato.lower(), candidato)
    if comando in ("spotify", "firefox", "discord", "steam") and not shutil.which(comando):
        resolvido = _resolver_desktop(nome)
        flatpak_ids = {
            "spotify": "com.spotify.Client",
            "discord": "com.discordapp.Discord",
            "steam": "com.valvesoftware.Steam",
        }
        appid = flatpak_ids.get(comando)
        if resolvido:
            partes = resolvido  # Native desktop entry pode estar fora do PATH (/usr/games).
        elif appid and shutil.which("flatpak"):
            comando = "flatpak"
            partes = ["flatpak", "run", appid]
        else:
            return f"O aplicativo '{nome}' não foi encontrado."
    else:
        partes = comando.split()
        if not shutil.which(partes[0]):
            resolvido = _resolver_desktop(nome)
            if resolvido:
                partes = resolvido
    if argumentos:
        # Argumentos são passados como uma linha simples apenas para abrir o app;
        # não são um shell, portanto não há | && etc. interpretados aqui.
        import shlex
        partes.extend(shlex.split(argumentos))
    try:
        subprocess.Popen(partes, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return f"Pedido de abrir aplicativo enviado: {nome}. A janela ainda não foi verificada."
    except FileNotFoundError:
        return f"Não encontrei o executável '{partes[0]}'."
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui abrir '{nome}': {exc}"


def acao(acao: str, x=None, y=None, texto: str = "", tecla: str = "",
         teclas=None, segundos: float = 0.3, titulo_janela: str = "",
         cliques: int = 1, quantidade: int = 3) -> str:
    if not DISPONIVEL:
        return estado()
    nome = (acao or "").strip().lower()
    if titulo_janela:
        resultado = focar_janela(titulo_janela)
        if resultado.startswith("Nenhuma") or resultado.startswith("Não tenho"):
            return resultado
    try:
        if nome == "mover":
            xx, yy = _validar_xy(x, y)
            if _BACKEND == "pyautogui":
                _pyautogui.moveTo(xx, yy, duration=0.15)
            else:
                subprocess.run(["xdotool", "mousemove", str(xx), str(yy)], check=True)
            return f"Mouse em ({xx}, {yy})."
        if nome in ("clicar", "duplo_clique"):
            xx, yy = _validar_xy(x, y)
            q = 2 if nome == "duplo_clique" else max(1, int(cliques))
            if _BACKEND == "pyautogui":
                _pyautogui.click(xx, yy, clicks=q, interval=0.08)
            else:
                for _ in range(q):
                    subprocess.run(["xdotool", "mousemove", str(xx), str(yy), "click", "1"], check=True)
            return f"Clique executado em ({xx}, {yy})."
        if nome == "botao_direito":
            xx, yy = _validar_xy(x, y)
            if _BACKEND == "pyautogui":
                _pyautogui.rightClick(xx, yy)
            else:
                subprocess.run(["xdotool", "mousemove", str(xx), str(yy), "click", "3"], check=True)
            return f"Clique direito em ({xx}, {yy})."
        if nome == "rolar":
            q = int(quantidade)
            if _BACKEND == "pyautogui":
                _pyautogui.scroll(q)
            else:
                subprocess.run(["xdotool", "click", "4" if q > 0 else "5"], check=True)
                for _ in range(max(1, abs(q) - 1)):
                    subprocess.run(["xdotool", "click", "4" if q > 0 else "5"], check=True)
            return f"Rolagem: {q}."
        if nome == "digitar":
            if not texto:
                return "Erro: informe o texto."
            if _BACKEND == "pyautogui":
                # PyAutoGUI cobre bem teclas ASCII; para texto Unicode (PT-BR,
                # acentos, caminhos etc.) usamos o clipboard quando disponível.
                if any(ord(ch) > 127 for ch in texto):
                    colador = shutil.which("xclip") or shutil.which("xsel")
                    if colador:
                        if colador.endswith("xclip"):
                            subprocess.run([colador, "-selection", "clipboard"],
                                           input=texto, text=True, check=True)
                        else:
                            subprocess.run([colador, "--clipboard", "--input"],
                                           input=texto, text=True, check=True)
                        _pyautogui.hotkey("ctrl", "v")
                    else:
                        _pyautogui.write(texto, interval=0.005)
                else:
                    _pyautogui.write(texto, interval=0.005)
            else:
                subprocess.run(["xdotool", "type", "--delay", "5", texto], check=True)
            return "Texto digitado."
        if nome == "pressionar":
            k = _normalizar_chave(tecla)
            if _BACKEND == "pyautogui":
                _pyautogui.press(k)
            else:
                subprocess.run(["xdotool", "key", k], check=True)
            return f"Tecla pressionada: {tecla}."
        if nome == "atalho":
            sequencia = teclas or []
            if not sequencia:
                return "Erro: informe teclas."
            norm = [_normalizar_chave(k) for k in sequencia]
            if _BACKEND == "pyautogui":
                _pyautogui.hotkey(*norm)
            else:
                subprocess.run(["xdotool", "key", "+".join(norm)], check=True)
            return f"Atalho executado: {' + '.join(sequencia)}."
        if nome == "esperar":
            espera = max(0.0, min(float(0.3 if segundos is None else segundos), 30.0))
            time.sleep(espera)
            return f"Esperei {espera:.1f}s."
        if nome == "fechar_janela":
            if _BACKEND == "xdotool" and titulo_janela:
                p = subprocess.run(["xdotool", "search", "--name", titulo_janela],
                                   capture_output=True, text=True)
                wid = (p.stdout.splitlines() or [""])[0].strip()
                if not wid:
                    return f"Nenhuma janela com '{titulo_janela}'."
                subprocess.run(["xdotool", "windowclose", wid], check=True)
                return f"Janela fechada: {titulo_janela}."
            if _BACKEND == "pyautogui":
                _pyautogui.hotkey("alt", "f4")
                return "Janela ativa fechada com Alt+F4."
            return "Não consegui fechar a janela."
        return f"Erro: ação de desktop desconhecida: {acao}"
    except Exception as exc:  # noqa: BLE001
        return f"Falha na ação de desktop '{acao}': {type(exc).__name__}: {exc}"
