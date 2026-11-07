"""
Sensores — o que está acontecendo na máquina agora.

A versão anterior devolvia uma string pronta ("Janelas: a, b | Mídia: c"), o que
basta para enfiar no prompt e não serve para mais nada: não dá para comparar dois
instantes, então não dá para perceber *mudança*, que é de onde vem qualquer
iniciativa que não seja chute.

Agora o estado é estruturado e comparável. Além disso:

* **Janela ativa**, não a lista inteira. Ter o Firefox aberto atrás não é sinal de
  nada; estar com o Firefox na frente há 40 minutos é.
* **Ociosidade real do X11** via `xprintidle`, quando existe. É a diferença entre
  "não me mandou mensagem" e "não está no computador" — e é o que evita ela puxar
  assunto com uma cadeira vazia.
* Tudo degrada em silêncio: sem `wmctrl`, sem `playerctl`, sem `xprintidle`, ela
  continua funcionando com menos informação em vez de quebrar.
"""
import os
import shlex
import shutil
import subprocess

_DISPONIVEL = {}


def tem(programa: str) -> bool:
    if programa not in _DISPONIVEL:
        _DISPONIVEL[programa] = shutil.which(programa) is not None
    return _DISPONIVEL[programa]


def _cmd(comando, timeout: int = 3) -> str:
    """Executa uma sonda local sem shell; strings mantêm compatibilidade legada."""
    try:
        argv = shlex.split(comando) if isinstance(comando, str) else list(comando)
        if not argv:
            return ""
        return subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL,
                                       timeout=timeout).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return ""


def janela_ativa() -> str:
    if tem("xdotool"):
        nome = _cmd("xdotool getactivewindow getwindowname")
        if nome:
            return nome[:120]
    if tem("xprop"):
        bruto = _cmd("xprop -root _NET_ACTIVE_WINDOW")
        if "0x" in bruto:
            wid = bruto.split()[-1]
            nome = _cmd(f"xprop -id {wid} WM_NAME")
            if '"' in nome:
                return nome.split('"', 1)[1].rsplit('"', 1)[0][:120]
    return ""


def janelas() -> list:
    if not tem("wmctrl"):
        return []
    saida = _cmd("wmctrl -l")
    nomes = []
    for linha in saida.splitlines():
        partes = linha.split(maxsplit=3)
        if len(partes) >= 4 and partes[3] not in ("Desktop", "Área de trabalho"):
            nomes.append(partes[3][:80])
    return nomes[-8:]


def midia() -> dict:
    if not tem("playerctl"):
        return {}
    bruto = _cmd("playerctl metadata --format "
                 "'{{status}}|{{title}}|{{artist}}|{{album}}'")
    if not bruto or "|" not in bruto:
        return {}
    partes = (bruto.split("|") + ["", "", "", ""])[:4]
    if partes[0].lower() not in ("playing", "tocando"):
        return {}
    return {"estado": partes[0], "titulo": partes[1][:80],
            "artista": partes[2][:60], "album": partes[3][:60]}


def ociosidade_x11() -> float:
    """Segundos sem teclado nem mouse. -1 quando não dá para saber."""
    if not tem("xprintidle"):
        return -1.0
    bruto = _cmd("xprintidle")
    try:
        return int(bruto) / 1000.0
    except (TypeError, ValueError):
        return -1.0


def carga() -> dict:
    dados = {}
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            dados["load1"] = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            linhas = {l.split(":")[0]: l for l in f}
        total = int(linhas["MemTotal"].split()[1])
        livre = int(linhas["MemAvailable"].split()[1])
        dados["memoria_usada_pct"] = round(100 * (1 - livre / total))
    except (OSError, KeyError, ValueError, IndexError, ZeroDivisionError):
        pass
    try:
        disco = os.statvfs("/")
        total_disco = disco.f_blocks * disco.f_frsize
        livre_disco = disco.f_bavail * disco.f_frsize
        if total_disco:
            dados["disco_usado_pct"] = round(100 * (1 - livre_disco / total_disco))
            dados["disco_livre_gb"] = round(livre_disco / (1024 ** 3), 1)
    except OSError:
        pass
    return dados


def estado() -> dict:
    """Retrato estruturado do ambiente neste instante."""
    ativa = janela_ativa()
    lista = janelas()
    # Uma janela aberta não comprova qual está em foco. Ausência fica desconhecida.
    return {
        "janela_ativa": ativa,
        "janelas": lista,
        "midia": midia(),
        "ociosidade_x11": ociosidade_x11(),
        **carga(),
    }


def descrever(dados: dict = None) -> str:
    """Uma linha legível — é o que vai para o prompt e para o log."""
    d = dados or estado()
    partes = []
    if d.get("janela_ativa"):
        partes.append(f"na frente: {d['janela_ativa']}")
    elif d.get("janelas"):
        partes.append(f"abertas: {', '.join(d['janelas'][-3:])}")
    else:
        partes.append("nenhuma janela detectada")
    m = d.get("midia") or {}
    if m.get("titulo"):
        partes.append(f"tocando: {m['titulo']}"
                      + (f" — {m['artista']}" if m.get("artista") else ""))
    if d.get("ociosidade_x11", -1) >= 60:
        partes.append(f"sem mexer no PC há {int(d['ociosidade_x11'] // 60)} min")
    return " | ".join(partes)


# Compatibilidade com o código antigo.
def get_system_state() -> str:
    return descrever()


def get_windows() -> str:
    return ", ".join(janelas()) or "Nenhuma janela detectada."


def get_media() -> str:
    m = midia()
    return f"{m['titulo']} por {m.get('artista', '?')}" if m else "Nada tocando"
