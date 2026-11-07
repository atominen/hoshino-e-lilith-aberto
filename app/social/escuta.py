"""
Ouvidos — escutar várias fontes ao mesmo tempo sem confundir quem falou o quê.

O problema que este arquivo resolve: um microfone só não é ouvir. Numa chamada
do Discord enquanto joga, existem coisas diferentes acontecendo em paralelo — a
sua voz, a voz de quem está na chamada, o som do jogo — e tratar tudo como uma
pista única transforma isso em sopa. Cada canal aqui é uma porta separada, com
uma **origem** carimbada em cada frase: `[discord/voz] vamos jogar depois?` é
uma informação diferente de `[microfone] vamos jogar depois?`, mesmo com o
texto idêntico, porque quem falou muda o que ela deve fazer.

No Linux (PulseAudio/PipeWire, que é o caso do Mint), uma fonte `.monitor`
normalmente representa toda uma saída: Discord, jogo e outros programas podem
estar misturados nela. Separar um aplicativo exige uma fonte dedicada realmente
configurada; a descoberta de fontes não cria esse isolamento. Por isso uma
pista como 'Discord' não é convertida automaticamente no monitor genérico.

**Perceber não é responder.** Cada canal tem um nível de atenção:

    ativa    -> ela lê e isso pode virar assunto/ação
    passiva  -> ela transcreve e guarda, mas não age por causa disso
    ignorar  -> não escuta (o canal existe, está desligado)

O jogo normalmente é `passiva`: serve de contexto ("ele está no meio de uma
partida"), não de pedido. A chamada do Discord costuma ser `ativa`.

**Consentimento.** Escutar uma chamada grava outras pessoas. Nada aqui começa
sozinho: um canal só passa a escutar quando alguém manda, e `estado()` sempre
mostra o que está aberto, para não existir escuta que a pessoa não sabe que
está acontecendo. O que foi ouvido vive numa janela curta em memória e não vai
para a memória permanente por conta própria.
"""
import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import ui_policy

ATENCOES = ("ativa", "passiva", "ignorar")

# Canais abertos: nome -> {transcritor, dispositivo, atencao, desde}
_CANAIS = {}
# Janela curta do que foi ouvido, com origem. Não é memória permanente.
_OUVIDO = deque(maxlen=400)
_TRAVA = threading.Lock()
_CENTRAL_CURSOR=0
_CENTRAL_INSTANCE=''

def _central():return os.environ.get('HOSHINO_CENTRAL_LISTENING')=='1'

def _call(action=None,**data):
    from core.central_audio_client import call
    return call(config.RAIZ,config.ENTIDADE_ID,action,**data)

def _remote_state():
    state=_call()
    rows=state['channels']
    if not rows:return 'Não estou escutando nenhum canal de áudio.'
    return '\n'.join(f"{r['channel']}: {r['source']['label']} | {r['attention']} | {r['status']}"+
        ((' | '+r['error']) if r.get('error') else '') for r in rows)


# ----------------------------------------------------------------- descoberta
def fontes_do_sistema() -> list:
    """Fontes de áudio reais desta máquina, via `pactl`.

    Devolve dicts com nome técnico (o que vai no --device), um rótulo legível e
    se é um monitor (som que SAI do computador) ou uma entrada (microfone).
    """
    if _central():
        return [dict(dispositivo=s['id'],rotulo=s['label'],monitor=s['kind']!='microphone') for s in _call()['sources']]
    if not shutil.which("pactl"):
        return []
    try:
        saida = subprocess.run(["pactl", "list", "sources", "short"],
                               capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return []

    fontes = []
    for linha in saida.splitlines():
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        nome = partes[1]
        monitor = nome.endswith(".monitor")
        fontes.append({
            "dispositivo": nome,
            "monitor": monitor,
            "rotulo": _rotular(nome, monitor),
        })
    return fontes


def _rotular(nome: str, monitor: bool) -> str:
    n = nome.lower()
    if "usb" in n and not monitor:
        return "microfone USB"
    if not monitor:
        return "microfone"
    if "hdmi" in n:
        return "som que sai pelo HDMI"
    return "som que sai pelas caixas/fone"


def sugerir_dispositivo(pista: str) -> str:
    """Traduz uma pista humana ('o som do jogo', 'meu microfone') na fonte real.

    Sem isto, usar a escuta exigiria decorar nomes como
    `alsa_output.pci-0000_03_00.1.hdmi-stereo.monitor`, que ninguém decora.
    """
    pista = (pista or "").strip().lower()
    fontes = fontes_do_sistema()
    if not fontes:
        return ""
    # nome técnico exato passa direto
    for f in fontes:
        if pista == f["dispositivo"].lower():
            return f["dispositivo"]
    aplicativos = _aplicativos_na_pista(pista)
    if aplicativos is not None:
        # Um monitor de HDMI/caixas é uma mistura de saída, não o Discord ou
        # jogo. Somente um endpoint cujo nome corresponde à pista é candidato.
        for f in fontes:
            if f["monitor"] and any(a in f["dispositivo"].casefold() for a in aplicativos):
                return f["dispositivo"]
        return ""
    # 'fone' faz parte de 'microfone': a pista de entrada tem precedência.
    quer_monitor = "microfone" not in pista and any(p in pista for p in
                       ("jogo", "discord", "sistema", "saida", "saída", "alto-falante",
                        "caixa", "fone", "som", "app", "programa", "chamada"))
    for f in fontes:
        if f["monitor"] == quer_monitor:
            return f["dispositivo"]
    return fontes[0]["dispositivo"]


def _aplicativos_na_pista(pista: str):
    """None = pista de dispositivo; set vazio = app não especificado."""
    grupos = {
        "discord": ("discord",), "minecraft": ("minecraft",),
        "firefox": ("firefox",), "spotify": ("spotify",),
        "jogo": ("minecraft", "jogo", "game"), "game": ("minecraft", "jogo", "game"),
        "chamada": ("discord", "chamada", "call", "zoom", "teams"),
    }
    candidatos = set()
    for palavra, nomes in grupos.items():
        if palavra in pista:
            candidatos.update(nomes)
    if candidatos:
        return candidatos
    if any(p in pista for p in ("app", "aplicativo", "programa")):
        return set()
    return None


# --------------------------------------------------------------- abrir/fechar
def ouvir(canal: str, pista: str = "", atencao: str = "ativa") -> str:
    """Abre um canal de escuta. `pista` é de onde vem o som; `canal` é o nome
    pelo qual ela vai se referir a isso depois."""
    if _central():
        try:
            sources=_call()['sources'];hint=str(pista).strip().casefold()
            selected=[s for s in sources if s['id'].casefold()==hint]
            if not selected:selected=[s for s in sources if hint and hint in s['label'].casefold()]
            if len(selected)!=1:return 'Escolha a fonte exata por listar_fontes_audio; nenhum monitor genérico foi substituído.'
            _call('open',channel=canal,source_id=selected[0]['id'],attention=atencao)
            return _remote_state()
        except (OSError,ValueError,RuntimeError) as exc:return str(exc)
    if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'ambient'):
        return 'ACESSO_BLOQUEADO: ouvir o ambiente foi desativado na Central.'
    canal = (canal or "").strip().lower()
    if not canal:
        return "Erro: dê um nome ao canal (ex: discord, jogo, microfone)."
    if atencao not in ATENCOES:
        return f"Erro: atenção deve ser uma de {', '.join(ATENCOES)}."
    with _TRAVA:
        if canal in _CANAIS:
            return f"O canal '{canal}' já está aberto."

    dispositivo = sugerir_dispositivo(pista) if pista else ""
    if pista and not dispositivo:
        if _aplicativos_na_pista(pista.casefold()) is not None:
            return ("Não encontrei uma fonte dedicada para esse aplicativo. Um monitor "
                    "genérico mistura o som de vários programas e não permite atribuir "
                    "a fala ao Discord/jogo. Escolha uma fonte real pelo nome exato ou "
                    "configure uma captura isolada; nenhum canal foi aberto.")
        return ("Não consegui listar as fontes de áudio (o `pactl` não respondeu). "
                "Sem isso só dá para usar o microfone padrão: tente sem indicar a fonte.")

    try:
        from tools import transcricao
        t = transcricao.Transcritor(dispositivo=dispositivo, origem=canal)
        if not t.pronto():
            return f"Não dá para escutar ainda — {t.diagnostico()}"
        resultado = t.iniciar_escuta()
    except Exception as e:  # noqa: BLE001
        return f"Não consegui abrir o canal '{canal}': {type(e).__name__}: {e}"

    if not t.escutando:
        return f"Não consegui abrir o canal '{canal}': {resultado}"

    with _TRAVA:
        _CANAIS[canal] = {"transcritor": t, "dispositivo": dispositivo or "(microfone padrão)",
                          "atencao": atencao, "desde": datetime.now()}
    return (f"Escutando '{canal}' em {dispositivo or 'microfone padrão'} "
            f"(atenção {atencao}). Para parar: parar_de_ouvir('{canal}').")


def parar_de_ouvir(canal: str = "") -> str:
    """Fecha um canal, ou todos se nenhum for dito."""
    if _central():
        try:_call('stop',channel=canal);return _remote_state()
        except (OSError,ValueError,RuntimeError) as exc:return str(exc)
    canal = (canal or "").strip().lower()
    with _TRAVA:
        alvos = [canal] if canal else list(_CANAIS)
        if canal and canal not in _CANAIS:
            return f"O canal '{canal}' não está aberto."
        fechados = []
        for nome in alvos:
            dados = _CANAIS.pop(nome, None)
            if dados:
                try:
                    dados["transcritor"].parar_escuta()
                except Exception:  # noqa: BLE001
                    pass
                fechados.append(nome)
    return f"Parei de escutar: {', '.join(fechados)}." if fechados else "Não havia nada aberto."


def mudar_atencao(canal: str, atencao: str) -> str:
    """Muda o quanto ela leva um canal a sério, sem fechar e reabrir."""
    if _central():
        try:_call('attention',channel=canal,attention=atencao);return _remote_state()
        except (OSError,ValueError,RuntimeError) as exc:return str(exc)
    canal = (canal or "").strip().lower()
    if atencao not in ATENCOES:
        return f"Erro: atenção deve ser uma de {', '.join(ATENCOES)}."
    with _TRAVA:
        if canal not in _CANAIS:
            return f"O canal '{canal}' não está aberto."
        _CANAIS[canal]["atencao"] = atencao
    return f"Canal '{canal}' agora é de atenção {atencao}."


# ------------------------------------------------------------------- consumo
def coletar() -> list:
    """Puxa o que chegou em todos os canais desde a última vez.

    Chamado pelo laço principal a cada batimento. Devolve só o que é de atenção
    `ativa` — o resto fica guardado e continua consultável, mas não vira evento
    que a faz agir. É aqui que 'perceber ≠ responder' deixa de ser frase e vira
    comportamento.
    """
    if _central():
        global _CENTRAL_CURSOR,_CENTRAL_INSTANCE
        result=_call(events='1',after=_CENTRAL_CURSOR)
        if _CENTRAL_INSTANCE and result['instance']!=_CENTRAL_INSTANCE:result=_call(events='1',after=0)
        _CENTRAL_INSTANCE=result['instance'];_CENTRAL_CURSOR=result['cursor'];active=[]
        for row in result['items']:
            item=dict(canal=row['channel'],origem=row['origin'],texto=row['text'],atencao=row['attention'],
                quando=datetime.fromisoformat(row['observed_at']).astimezone().replace(tzinfo=None),
                source_id=row['source_id'],receipt=row['asr_id'],speaker='desconhecido')
            _OUVIDO.append(item)
            if row['attention']=='ativa':active.append(item)
        return active
    if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'ambient'):
        parar_de_ouvir()
        return []
    novos = []
    with _TRAVA:
        canais = list(_CANAIS.items())
    for nome, dados in canais:
        if dados["atencao"] == "ignorar":
            continue
        t = dados["transcritor"]
        while True:
            item = t.pegar()
            if not item:
                break
            registro = {"canal": nome, "origem": item.get("origem", nome),
                        "texto": item.get("texto", ""),
                        "quando": item.get("quando") or datetime.now(),
                        "atencao": dados["atencao"]}
            _OUVIDO.append(registro)
            if dados["atencao"] == "ativa":
                novos.append(registro)
    return novos


def o_que_ouvi(canal: str = "", minutos: int = 10, limite: int = 20) -> str:
    """O que foi ouvido recentemente, com a origem de cada frase."""
    if _central():
        try:coletar()
        except (OSError,ValueError,RuntimeError) as exc:return str(exc)
    canal = (canal or "").strip().lower()
    corte = datetime.now() - timedelta(minutes=max(1, minutos))
    itens = [r for r in _OUVIDO
             if r["quando"] >= corte and (not canal or r["canal"] == canal)]
    if not itens:
        onde = f" em '{canal}'" if canal else ""
        return f"Não ouvi nada{onde} nos últimos {minutos} minutos."
    linhas = [f"[{r['quando']:%H:%M}] [{r['origem']}] {r['texto']}"
              for r in itens[-limite:]]
    return "\n".join(linhas)


def estado() -> str:
    """O que está sendo escutado agora. Existe para que nunca haja escuta
    silenciosa: se algum canal está aberto, isto diz qual."""
    if _central():
        try:return _remote_state()
        except (OSError,ValueError,RuntimeError) as exc:return str(exc)
    with _TRAVA:
        if not _CANAIS:
            return "Não estou escutando nenhum canal de áudio."
        linhas = []
        for nome, d in sorted(_CANAIS.items()):
            desde = d["desde"].strftime("%H:%M")
            linhas.append(f"- {nome}: {d['dispositivo']} | atenção {d['atencao']} | desde {desde}")
    return "Escutando agora:\n" + "\n".join(linhas)


def canais_abertos() -> list:
    if _central():return [r['channel'] for r in _call()['channels']]
    with _TRAVA:
        return sorted(_CANAIS)


def listar_fontes() -> str:
    """Mostra as fontes de áudio reais desta máquina, para escolher uma."""
    if _central():
        try:
            return '\n'.join(f"{s['label']} | {s['kind']} | ID: {s['id']}" for s in _call()['sources']) or 'Nenhuma fonte disponível.'
        except (OSError,ValueError,RuntimeError) as exc:return str(exc)
    fontes = fontes_do_sistema()
    if not fontes:
        return ("Não consegui listar as fontes de áudio. No Linux isso vem do "
                "`pactl` (pacote pulseaudio-utils). Sem ele, dá para escutar só "
                "o microfone padrão.")
    linhas = []
    for f in fontes:
        tipo = "som que sai do PC" if f["monitor"] else "entrada"
        linhas.append(f"- {f['rotulo']} ({tipo})\n    {f['dispositivo']}")
    return ("Fontes de áudio desta máquina:\n" + "\n".join(linhas) +
            "\n\nUm monitor de saída pode misturar vários programas. Para atribuir "
            "áudio ao Discord ou jogo é necessária uma fonte dedicada configurada; "
            "listar as fontes não cria captura isolada por aplicativo.")
