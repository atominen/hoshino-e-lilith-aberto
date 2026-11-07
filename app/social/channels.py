"""
Canais — como ela existe fora do terminal.

Você vai montar um Discord para ela. Em vez de enfiar `discord.py` dentro do laço
principal (que aí trava a TUI quando a rede cai, e obriga a Hoshino a ter o token
na memória), a ponte é um barramento de arquivos:

    runtime/bus/entrada/*.json   mensagens chegando de fora
    runtime/bus/saida/*.json     respostas dela esperando entrega
    runtime/bus/<canal>.vivo     o adaptador escreve aqui a cada ciclo

O adaptador do Discord roda em outro processo, com o token dele, e só escreve e lê
arquivos. Se o bot cair, ela continua viva no terminal. Se ela cair, o bot acumula
mensagens e ela responde quando voltar. Nenhum dos dois derruba o outro, e
qualquer canal novo (Telegram, um webhook, um app seu) fala a mesma língua sem
tocar no código dela.

Escrita atômica: grava `.tmp` e renomeia, então o outro processo nunca lê metade
de um arquivo.
"""
import json
import os
import sys
import time
import uuid
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402

ENTRADA = "entrada"
SAIDA = "saida"


def _pasta(qual: str) -> str:
    caminho = os.path.join(config.BUS_DIR, qual)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _gravar_json(destino: str, dados: dict) -> bool:
    try:
        tmp = destino + '.' + uuid.uuid4().hex + '.tmp'
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        os.replace(tmp, destino)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ entrada
def publicar_entrada(canal: str, texto: str, autor: str = "", autor_id: str = "",
                     responder_para: str = "", anexos=None, source_id: str = "") -> str:
    """Chamado pelo adaptador externo (o bot do Discord) ao receber mensagem."""
    from core import ui_policy
    if canal=='discord' and not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
        raise PermissionError('Discord desativado na Central; entrada não gravada.')
    msg_id = f"in-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    if source_id:
        msg_id = 'in-src-' + hashlib.sha256((canal+':'+str(source_id)).encode()).hexdigest()
        if os.path.isfile(os.path.join(_pasta(ENTRADA), msg_id+'.json')):
            return msg_id  # tombstone confirmado preserva dedup após reinício
    dados = {"id": msg_id, "canal": canal, "texto": (texto or "")[:6000],
             "autor": autor[:60], "autor_id": str(autor_id)[:60],
             "responder_para": str(responder_para)[:80],
             "anexos": anexos or [], "ts": datetime.now().isoformat(timespec="microseconds"),
             "source_id": str(source_id), "processing": {"status":"queued"}}
    if not _gravar_json(os.path.join(_pasta(ENTRADA), msg_id + ".json"), dados):
        raise OSError('entrada do canal não pôde ser persistida')
    return msg_id


def receber(limite: int = 5, consumir: bool = True, excluir_ids=()) -> list:
    """Lê e consome as mensagens que chegaram. O arquivo é removido ao ser lido."""
    pasta = _pasta(ENTRADA)
    mensagens = []
    try:
        arquivos = sorted((f for f in os.listdir(pasta) if f.endswith(".json")),
                          key=lambda f:(os.stat(os.path.join(pasta,f)).st_mtime_ns,f))
    except OSError:
        return []
    for nome in arquivos:
        if len(mensagens) >= limite:
            break
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if not isinstance(dados,dict) or not isinstance(dados.get('id'),str):
                raise ValueError('envelope inválido')
            from core import ui_policy
            if dados.get('canal')=='discord' and not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
                continue  # Guardar pendentes, sem consumir enquanto desativado.
            if not consumir and (dados.get('id') in excluir_ids or
                                 dados.get('processing',{}).get('status','queued')!='queued'):
                continue
            mensagens.append(dados)
            if consumir:
                os.remove(caminho)
        except (OSError, ValueError):
            if not consumir:
                from core import diagnostics
                diagnostics.emit('channel.invalid_envelope', level='ERROR', file=caminho)
                continue  # preserve para diagnóstico, não destrua entrada inválida
            try:
                os.remove(caminho)
            except OSError:
                pass
    return mensagens


def entrada_estado(msg_id: str, status: str, reason: str = '') -> None:
    if status not in {'processing','answered','superseded','failed','uncertain'}:
        raise ValueError('estado inválido')
    _envelope_estado(ENTRADA, msg_id, 'processing',
                     dict(status=status, reason=reason, auto_retry=False,
                          timestamp=datetime.now().isoformat(timespec='microseconds')))


def _envelope_estado(pasta, msg_id, field, value):
    if os.path.basename(msg_id)!=msg_id or not msg_id.startswith(('in-','out-')):
        raise ValueError('ID do canal inválido')
    caminho = os.path.join(_pasta(pasta), msg_id+'.json')
    with open(caminho, encoding='utf-8') as stream:
        dados = json.load(stream)
    dados[field] = value
    if not _gravar_json(caminho, dados):
        raise OSError('estado de entrega não pôde ser persistido')


def saida_estado(msg_id: str, **delivery):
    _envelope_estado(SAIDA, msg_id, 'delivery', delivery)


# -------------------------------------------------------------------- saída
def enviar(canal: str, destino: str, texto: str, anexo: str = "") -> str:
    """Ela responde num canal externo. O adaptador entrega."""
    from core import ui_policy
    if canal=='discord' and not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
        raise PermissionError('Discord desativado na Central; saída não gravada.')
    msg_id = f"out-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    dados = {"id": msg_id, "canal": canal, "destino": str(destino), "texto": texto or "",
             "anexo": anexo or "", "ts": datetime.now().isoformat(timespec="seconds")}
    if not _gravar_json(os.path.join(_pasta(SAIDA), msg_id + ".json"), dados):
        raise OSError('resposta do canal não pôde ser persistida')
    return msg_id


def pendentes_de_saida(canal: str = "", limite: int = 20) -> list:
    """Chamado pelo adaptador externo para saber o que entregar."""
    pasta = _pasta(SAIDA)
    saida = []
    try:
        arquivos = sorted(f for f in os.listdir(pasta) if f.endswith(".json"))
    except OSError:
        return []
    for nome in arquivos:
        if len(saida) >= limite:
            break
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, json.JSONDecodeError):
            try:
                os.remove(caminho)
            except OSError:
                pass
            continue
        if canal and dados.get("canal") != canal:
            continue
        if dados.get('delivery',{}).get('status') in {'sending','uncertain'}:
            continue  # não repetir um POST cujo efeito é desconhecido
        saida.append(dados)
    return saida


def confirmar_entrega(msg_id: str) -> bool:
    try:
        os.remove(os.path.join(_pasta(SAIDA), msg_id + ".json"))
        return True
    except OSError:
        return False


# ------------------------------------------------------------------- estado
def marcar_vivo(canal: str) -> None:
    """O adaptador avisa que está de pé."""
    try:
        os.makedirs(config.BUS_DIR, exist_ok=True)
        with open(os.path.join(config.BUS_DIR, f"{canal}.vivo"), "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat(timespec="seconds"))
    except OSError:
        pass


def canais_ativos(tolerancia_seg: int = 120) -> list:
    """Quais canais deram sinal de vida recentemente."""
    ativos = []
    try:
        for nome in os.listdir(config.BUS_DIR):
            if not nome.endswith(".vivo"):
                continue
            caminho = os.path.join(config.BUS_DIR, nome)
            if time.time() - os.path.getmtime(caminho) <= tolerancia_seg:
                ativos.append(nome[:-5])
    except OSError:
        pass
    return ativos


def resumo() -> str:
    ativos = canais_ativos()
    entrada = len(os.listdir(_pasta(ENTRADA))) if os.path.isdir(_pasta(ENTRADA)) else 0
    saida = len(pendentes_de_saida())
    if not ativos and not entrada and not saida:
        return "Só o terminal por enquanto."
    return (f"canais ativos: {', '.join(ativos) or 'nenhum'} | "
            f"{entrada} entrando, {saida} esperando entrega")
