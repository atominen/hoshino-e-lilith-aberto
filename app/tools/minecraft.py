"""Cliente local da ponte Minecraft/Mineflayer.

A Hoshino conversa com um processo Node separado por HTTP em localhost.
Isto mantém a integração Minecraft fora do processo principal Python e evita
misturar o loop do Mineflayer com o loop da interface Textual.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict
import time
import uuid

import requests
from core import diagnostics
import config

HOST = config.MINECRAFT_BRIDGE_URL
TIMEOUT = float(os.environ.get("HOSHINO_MINECRAFT_TIMEOUT", "12"))
BRIDGE_PROTOCOL_REQUIRED = 3
READ_ONLY_ACTIONS = frozenset({'state', 'inventory', 'find_blocks', 'players', 'recipes','furnace_state'})


def _saude_objeto() -> tuple[dict | None, str]:
    """Lê a saúde em formato estruturado, sem aceitar uma API desconhecida."""
    try:
        r = requests.get(f"{HOST}/health", timeout=2.0)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None, "a ponte devolveu saúde em formato inválido"
        return data, ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _ponte_compativel() -> tuple[dict | None, str]:
    """Exige protocolo conhecido antes de qualquer RPC que altere ou leia o jogo."""
    health, erro = _saude_objeto()
    if health is None:
        return None, "[PONTE MINECRAFT INDISPONÍVEL]\n" + json.dumps(
            {"erro": erro, "required_protocol": BRIDGE_PROTOCOL_REQUIRED}, ensure_ascii=False)
    protocolo = health.get("protocol")
    if not isinstance(protocolo, int) or protocolo < BRIDGE_PROTOCOL_REQUIRED:
        return None, "[PONTE MINECRAFT INCOMPATÍVEL]\n" + json.dumps(
            {"bridge_health": health, "required_protocol": BRIDGE_PROTOCOL_REQUIRED,
             "received_protocol": protocolo}, ensure_ascii=False, indent=2)
    return health, ""


def _resposta_da_ponte(exc: Exception) -> str:
    """Primeira linha do erro que a ponte devolveu (sem o rastro técnico), quando houver corpo JSON."""
    resp = getattr(exc, "response", None)
    try:
        corpo = resp.json() if resp is not None else None
    except Exception:  # noqa: BLE001
        return ""
    erro = str((corpo or {}).get("erro") or "").strip() if isinstance(corpo, dict) else ""
    return erro.splitlines()[0].removeprefix("Error: ")[:400] if erro else ""


def _rpc(action: str, args: Dict[str, Any] | None = None, timeout: float | None = None) -> str:
    """Chama a ponte e registra início/fim para diagnóstico."""
    from core import ui_policy
    if action not in {'stop','disconnect'} and not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'minecraft'):
        return 'ACESSO_BLOQUEADO: Minecraft foi desativado na Central.'
    request_id = f"mc-{uuid.uuid4().hex}"
    started = time.monotonic()
    diagnostics.emit("minecraft.rpc.start", action=action, request_id=request_id, args=args or {})
    health, recusa = _ponte_compativel()
    if health is None:
        diagnostics.emit("minecraft.rpc.blocked", level="ERROR", action=action,
                         request_id=request_id, reason="bridge_incompatible")
        return recusa
    try:
        context = diagnostics.current_turn_context()
        expected_session = (health.get('state') or {}).get('sessionId')
        r = requests.post(
            f"{HOST}/rpc",
            json={"action": action, "args": args or {}, "request_id": request_id,
                  "parent_id": context.get('tool_id') or context.get('turn_id'),
                  "turn_id": context.get('turn_id'), "entity_id": config.ENTIDADE_ID,
                  "session_id": expected_session},
            timeout=TIMEOUT if timeout is None else timeout,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as exc:
        diagnostics.exception("minecraft.rpc.error", exc, action=action, request_id=request_id, elapsed_ms=int((time.monotonic()-started)*1000))
        if action not in READ_ONLY_ACTIONS:
            # 30/10: o texto do servidor ("Server refused to place ...: the block is still air") ficava fora do
            # recibo e ela tentava de novo no mesmo lugar. Continua incerto (o ACK pode se perder); o fato aparece.
            detalhe = _resposta_da_ponte(exc)
            return (f"RESULTADO_INCERTO: Minecraft {action}; pedido {request_id} enviado sem recibo. Verifique o estado antes de repetir."
                    + (f" A ponte respondeu: {detalhe}" if detalhe else ""))
        return (
            "Minecraft indisponível: não consegui falar com a ponte Mineflayer. "
            "Verifique o estado da ponte. "
            f"Detalhe: {exc}"
        )
    except (ValueError, json.JSONDecodeError) as exc:
        diagnostics.exception("minecraft.rpc.invalid_json", exc, action=action, request_id=request_id)
        if action not in READ_ONLY_ACTIONS:
            return f"RESULTADO_INCERTO: Minecraft {action}; recibo inválido do pedido {request_id}. Verifique o estado antes de repetir."
        return f"Minecraft: resposta inválida da ponte: {exc}"

    if not isinstance(data, dict):
        return (f"RESULTADO_INCERTO: Minecraft {action}; recibo inválido do pedido {request_id}." if action not in READ_ONLY_ACTIONS
                else 'Minecraft: resposta inválida da ponte.')
    if data.get('request_id') is not None and data['request_id'] != request_id:
        diagnostics.emit('minecraft.rpc.receipt_mismatch', level='ERROR', action=action, request_id=request_id)
        return (f'RESULTADO_INCERTO: recibo de outro pedido Minecraft; esperado {request_id}. Verifique antes de repetir.'
                if action not in READ_ONLY_ACTIONS else 'Minecraft: recibo não corresponde ao pedido.')

    foreign = ((data.get('entity_id') is not None and data['entity_id'] != config.ENTIDADE_ID) or
               (data.get('parent_id') is not None and data['parent_id'] != (context.get('tool_id') or context.get('turn_id'))) or
               (action != 'connect' and expected_session is not None and data.get('session_id') is not None and data['session_id'] != expected_session))
    if foreign:
        diagnostics.emit('minecraft.rpc.receipt_mismatch', level='ERROR', action=action, request_id=request_id,
                         expected_session=expected_session, receipt_session=data.get('session_id'))
        return ('RESULTADO_INCERTO: recibo Minecraft de outra entidade/sessão/origem; verifique antes de repetir.'
                if action not in READ_ONLY_ACTIONS else 'Minecraft: recibo de outra entidade/sessão/origem.')
    elapsed = int((time.monotonic()-started)*1000)
    if not data.get("ok"):
        erro = str(data.get("erro", "erro desconhecido"))
        diagnostics.emit("minecraft.rpc.end", level="ERROR", action=action, request_id=request_id, ok=False, elapsed_ms=elapsed, error=erro)
        no_effect={('craft','craft_preconditions','preflight','not_started'),
                   ('equip','equip_preconditions','preflight','not_started'),
                   ('place_block','place_preconditions','preflight','not_started'),
                   ('use_item','use_preconditions','preflight','not_started'),
                   # 30/10: sem o item ou sem o jogador por perto; nada foi jogado.
                   ('toss','toss_preconditions','preflight','not_started'),
                   ('explore','explore_preconditions','preflight','not_started'),
                   # 30/10: inventário cheio, conferido sem sair do lugar nem mudar o inventário.
                   ('collect','collect_inventory_full','verified','not_applied'),
                   ('attack','attack_preconditions','preflight','not_started'),
                   *((a,'furnace_preconditions','preflight','not_started') for a in ('furnace_state','furnace_put','furnace_take')),
                   *((a,'harvest_preconditions','preflight','not_started') for a in ('collect','dig')),
                   # 30/10: o bloco na coordenada não é o esperado (estação dela substituída); nada foi quebrado.
                   ('dig','dig_preconditions','preflight','not_started'),
                   # Objetivo limpo pela ponte e posição conferida: sem movimento, nem tardio.
                   ('goto','goto_no_path','verified','not_applied'),
                   ('collect','collect_no_path','verified','not_applied')}
        # 30/10: reflexo de sobrevivência em andamento; a ponte recusou antes de começar qualquer ação.
        reflex_busy=(data.get('code'),data.get('phase'),data.get('effect_state'))==('reflex_busy','preflight','not_started')
        if (((action,data.get('code'),data.get('phase'),data.get('effect_state')) in no_effect or reflex_busy)
                and data.get('request_id')==request_id
                and data.get('entity_id')==config.ENTIDADE_ID and 'parent_id' in data
                and data['parent_id']==(context.get('tool_id') or context.get('turn_id'))
                and isinstance(expected_session,str) and expected_session and data.get('session_id')==expected_session):
            return f'ERRO_PRECONDICAO_MINECRAFT: {action} sem efeito no mundo. Reveja o plano com estes dados: '+json.dumps(
                {'erro':erro,'detalhes':data.get('details')},ensure_ascii=False)
        return ("RESULTADO_INCERTO: Minecraft " + action + '; ' + erro + '; verifique antes de repetir.'
                if action not in READ_ONLY_ACTIONS else "Minecraft: " + erro)
    result = data.get("resultado")
    # Projeção operacional privada, somente depois de validar a autoria do recibo.
    # Falha de observabilidade não transforma uma ação confirmada em retry.
    try:
        from core import activity_context
        snapshot = result.get('state') if isinstance(result, dict) and action == 'connect' else result if action == 'state' else None
        if snapshot is not None:
            activity_context.observe_minecraft(snapshot, session_id=data.get('session_id') or snapshot.get('sessionId'), request_id=request_id)
    except Exception as exc:
        diagnostics.exception('activity.minecraft_projection_failed', exc, request_id=request_id)
    diagnostics.emit("minecraft.rpc.end", action=action, request_id=request_id, ok=True, elapsed_ms=elapsed,
                     result=result, tool_id=context.get('tool_id'), parent_id=data.get('parent_id'),
                     entity=config.ENTIDADE_ID, bridge_session_id=data.get('session_id'))
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result or "OK")


def ponte_saude() -> str:
    """Consulta a ponte sem alterar a sessão do bot. O protocolo identifica ponte antiga."""
    started = time.monotonic()
    try:
        data, erro = _saude_objeto()
        if data is None:
            raise RuntimeError(erro)
        diagnostics.emit("minecraft.bridge.health", ok=True, elapsed_ms=int((time.monotonic()-started)*1000), health=data)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        diagnostics.exception("minecraft.bridge.health_error", exc, elapsed_ms=int((time.monotonic()-started)*1000))
        return json.dumps({"ok": False, "erro": str(exc)}, ensure_ascii=False)


def manual() -> str:
    return """MANUAL MINECRAFT DA HOSHINO

Eu controlo o Minecraft por uma interface estruturada Mineflayer, não por captura de tela.
A tela do jogo NÃO faz parte desta interface.

Princípio de decisão:
1. consultar minecraft_estado quando precisar conhecer a situação;
2. formular o próximo objetivo ou subobjetivo;
3. escolher a ferramenta Minecraft apropriada;
4. executar uma ação;
5. consultar o estado novamente se a ação mudar o mundo;
6. se falhar, analisar o erro e tentar uma abordagem diferente.

CAPACIDADES:
minecraft_descobrir_lan  descobre mundos Java abertos para LAN sem alterar nada
minecraft_conectar_lan   descobre automaticamente um mundo LAN e conecta
minecraft_conectar       conecta ao servidor/local world configurado
minecraft_desconectar    encerra a conexão
minecraft_estado         estado completo resumido: posição, dimensão, HP, fome, inventário, entidades próximas
minecraft_inventario     inventário agrupado por item
minecraft_chat           fala no chat do Minecraft
minecraft_procurar_bloco encontra posições próximas de um tipo de bloco
minecraft_ir_para        navega usando pathfinder até coordenadas
minecraft_parar          para a navegação atual
minecraft_minerar        quebra um bloco em coordenadas
minecraft_coletar        encontra e coleta blocos de um tipo usando pathfinder + ferramenta
minecraft_craft           procura receita e fabrica um item
                        usa bancada ao alcance (até4 blocos) quando necessária
minecraft_receitas        ingredientes, resultado e necessidade de bancada
minecraft_forno           estado/processar/retirar em forno ao alcance (até4 blocos)
                        processar deposita materiais; ainda não significa fundição concluída
                        aguarde/consulte estado e retire somente saída do seu próprio processamento
minecraft_equipar         equipa um item na mão/armadura
minecraft_atacar          ataca uma entidade próxima de acordo com o alvo
minecraft_colocar_bloco   coloca um bloco usando um bloco de referência e uma face
minecraft_usar_item       usa/ativa o item da mão
minecraft_jogar_item      joga um item no chão ou entrega a um jogador próximo (para=nome)
minecraft_explorar        anda numa direção procurando um mob e para assim que o vê
minecraft_seguir_jogador segue um jogador conhecido

REGRAS:
- Não use observar_tela para operar o Minecraft.
- Informação estruturada do mundo tem prioridade sobre percepção visual.
- Não repita uma ação que falhou sem mudar a abordagem ou verificar o estado.
- Para tarefas longas, trabalhe em subobjetivos e verifique o resultado entre eles.
- Não assuma que possui um item: consulte o inventário.
- Não assuma que uma navegação terminou: consulte o resultado/estado.
- Se o usuário já abriu um mundo para LAN, prefira descobrir/conectar à LAN em vez de iniciar outro servidor.
- Você pode decidir sozinha qual destas ferramentas usar quando a meta exigir.
- Depois de conectar, consulte minecraft_estado; conexão HTTP ou spawn isolado não é evidência suficiente de disponibilidade contínua.
""".strip()



def descobrir_lan(timeout: float = 2.5) -> str:
    """Escuta o anúncio multicast de um mundo Minecraft Java aberto para LAN."""
    import socket
    import time

    group = "224.0.2.60"
    port = 4445
    encontrados = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", port))
        except OSError:
            sock.bind(("0.0.0.0", port))
        mreq = socket.inet_aton(group) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(0.25)
        limite = time.monotonic() + max(0.5, float(timeout))
        while time.monotonic() < limite:
            try:
                pacote, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                texto = pacote.decode("utf-8", "strict")
            except UnicodeDecodeError:
                continue
            anuncio = re.fullmatch(r'\[MOTD\](.*?)\[/MOTD\]\[AD\]([0-9]{1,5})\[/AD\]', texto, re.S)
            if anuncio is None:
                continue
            motd, porta = anuncio.group(1), int(anuncio.group(2))
            if not 1 <= porta <= 65535:
                continue
            item = {"motd": motd, "host": addr[0], "port": porta, "descoberto_em": time.time()}
            if not any(x["host"] == item["host"] and x["port"] == item["port"] for x in encontrados):
                encontrados.append(item)
    except OSError as exc:
        diagnostics.exception("minecraft.lan_discovery.error", exc, group=group, port=port)
        return json.dumps({"ok": False, "erro": str(exc), "mundos": []}, ensure_ascii=False)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    encontrados.sort(key=lambda x: (x["host"], x["port"]))
    diagnostics.emit("minecraft.lan_discovery", timeout=timeout, mundos=encontrados)
    return json.dumps({"ok": True, "mundos": encontrados}, ensure_ascii=False, indent=2)


def conectar_lan(username: str | None = None, version: str = "1.16.5", auth: str = "offline",
                 timeout: float = 3.0) -> str:
    """Descobre o mundo LAN e conecta automaticamente ao primeiro anúncio disponível."""
    descoberto = descobrir_lan(timeout)
    try:
        obj = json.loads(descoberto)
    except Exception:
        obj = None
    if not isinstance(obj, dict) or not obj.get("mundos"):
        return "[MINECRAFT LAN NÃO ENCONTRADO]\n" + descoberto
    mundos = obj["mundos"]
    alvo = mundos[-1]
    diagnostics.emit("minecraft.lan_connect.selected", host=alvo.get("host"), port=alvo.get("port"), motd=alvo.get("motd"))
    resultado = conectar(alvo["host"], int(alvo["port"]), username or config.MINECRAFT_USERNAME, version, auth)
    return f"[MINECRAFT LAN SELECIONADO {alvo['host']}:{alvo['port']}]\n" + resultado

def conectar(host: str = "127.0.0.1", port: int = 25565, username: str | None = None,
             version: str = "1.16.5", auth: str = "offline") -> str:
    """Solicita a conexão e faz uma segunda leitura do estado antes de afirmar sucesso."""
    health_raw = ponte_saude()
    try:
        health = json.loads(health_raw)
    except Exception:
        health = None
    if isinstance(health,dict) and health.get('ok') is False:
        # Conectar é um pedido explícito de uso. A dependência pertence ao app,
        # não exige um segundo lançador nem uma ação de jogo feita pelo assistente.
        from tools import minecraft_launcher
        startup=minecraft_launcher.iniciar_ponte()
        diagnostics.emit('minecraft.bridge.on_demand',detail=startup)
        health_raw=ponte_saude()
        try:health=json.loads(health_raw)
        except Exception:health=None
    protocolo = health.get("protocol") if isinstance(health, dict) else None
    # A ponte anterior não expunha ``protocol`` e confirmava conexões antes de
    # o bot estar realmente pronto. Ausência também é incompatibilidade: nunca
    # devemos enviar ações a uma API cuja versão não conseguimos identificar.
    if not isinstance(protocolo, int) or protocolo < BRIDGE_PROTOCOL_REQUIRED:
        diagnostico = {"bridge_health": health, "required_protocol": BRIDGE_PROTOCOL_REQUIRED,
                       "received_protocol": protocolo}
        diagnostics.emit("minecraft.connection.unverified", level="ERROR", reason="bridge_protocol_incompativel", **diagnostico)
        return "[CONEXÃO MINECRAFT NÃO VERIFICADA — PONTE DESATUALIZADA]\n" + json.dumps(diagnostico, ensure_ascii=False, indent=2)

    resultado = _rpc("connect", {
        "host": host, "port": int(port), "username": username or config.MINECRAFT_USERNAME,
        "version": version, "auth": auth,
    }, timeout=20)

    try:
        obj = json.loads(resultado)
    except Exception:
        obj = None

    # A ponte nova já entrega verified=true/false. Mesmo assim, sempre consultamos
    # o estado imediatamente depois: isso protege contra ponte antiga, conexão que
    # caiu logo após spawn ou qualquer resposta textual prematura.
    estado_raw = _rpc("state", timeout=5)
    try:
        estado = json.loads(estado_raw)
    except Exception:
        estado = None

    verified = bool(isinstance(obj, dict) and obj.get("verified") is True)
    verified_state = bool(isinstance(estado, dict) and estado.get("connected") is True and
                          (estado.get("verified") is True or estado.get("connectionState") == "ready"))

    pacote = {"bridge_health": health if health is not None else health_raw,
              "resposta_conectar": obj if obj is not None else resultado,
              "estado_imediato": estado if estado is not None else estado_raw,
              "verified_by_connect": verified,
              "verified_by_state": verified_state}
    if verified and verified_state:
        diagnostics.emit("minecraft.connection.verified", host=host, port=int(port), username=username,
                          version=version, state=estado)
        return "[CONEXÃO MINECRAFT VERIFICADA]\n" + json.dumps(pacote, ensure_ascii=False, indent=2)

    diagnostics.emit("minecraft.connection.unverified", level="ERROR", host=host, port=int(port),
                      username=username, version=version, connect_result=pacote["resposta_conectar"],
                      state=pacote["estado_imediato"])
    return "[CONEXÃO MINECRAFT NÃO VERIFICADA]\n" + json.dumps(pacote, ensure_ascii=False, indent=2)


def desconectar() -> str:
    return _rpc("disconnect")


def estado(itens: list | None = None) -> str:
    # Com itens, a ponte acrescenta a percepção: entorno útil e análise das receitas.
    if itens:
        return _rpc("state", {"perception": [str(i) for i in itens][:6]})
    return _rpc("state")


def inventario() -> str:
    return _rpc("inventory")


def chat(texto: str) -> str:
    return _rpc("chat", {"text": texto})


def procurar_bloco(nome: str, max_distance: int = 64, quantidade: int = 16) -> str:
    return _rpc("find_blocks", {
        "name": nome, "maxDistance": int(max_distance), "count": int(quantidade),
    })


def ir_para(x: float, y: float, z: float, distancia: float = 1.0) -> str:
    return _rpc("goto", {"x": float(x), "y": float(y), "z": float(z), "range": float(distancia)}, timeout=60)


def parar() -> str:
    return _rpc("stop")


def minerar(x: float, y: float, z: float, ignorar_olhar: bool = False, esperado: str = "") -> str:
    return _rpc("dig", {
        "x": float(x), "y": float(y), "z": float(z), "forceLook": "ignore" if ignorar_olhar else True,
        **({"expect": str(esperado).strip()} if str(esperado or "").strip() else {}),
    }, timeout=45)


def coletar(nome: str, quantidade: int = 1, max_distance: int = 64) -> str:
    return _rpc("collect", {
        "name": nome, "count": int(quantidade), "maxDistance": int(max_distance),
    }, timeout=90)


def craft(nome: str, quantidade: int = 1) -> str:
    return _rpc("craft", {"name": nome, "count": int(quantidade)}, timeout=60)


def receitas(nome: str) -> str:
    return _rpc('recipes',{'name':str(nome)})


def forno(acao: str='estado',entrada: str='',combustivel: str='coal',quantidade: int=1,quantidade_combustivel: int=1) -> str:
    actions={'estado':'furnace_state','processar':'furnace_put','retirar':'furnace_take'}
    if acao not in actions:return 'Ação inválida: use estado, processar ou retirar.'
    args=dict(input=entrada,fuel=combustivel,count=int(quantidade),fuelCount=int(quantidade_combustivel)) if acao=='processar' else {}
    return _rpc(actions[acao],args)


def equipar(nome: str, destino: str = "hand") -> str:
    return _rpc("equip", {"name": nome, "destination": destino})


def atacar(alvo: str = "", max_distance: float = 16.0, entidade_id: int | None = None, perseguir: bool = False,
           quantidade: int = 1) -> str:
    args: Dict[str, Any] = {"target": alvo, "maxDistance": float(max_distance)}
    if entidade_id is not None:
        args["entityId"] = int(entidade_id)
    count = max(1, min(8, int(quantidade or 1)))
    if perseguir:  # a ponte persegue por até 30 s por animal; a morte vem do evento do servidor
        args["hunt"] = True
        args["count"] = count
    return _rpc("attack", args, timeout=15 + 30 * count if perseguir else None)


def colocar_bloco(x: float | None = None, y: float | None = None, z: float | None = None, face: str = "up", nome: str = "") -> str:
    # Sem coordenadas, a ponte escolhe chão sólido livre ao lado da entidade; com nome, equipa o item antes.
    extra = {"name": nome} if nome else {}
    if x is None or y is None or z is None:
        return _rpc("place_block", extra)
    return _rpc("place_block", {"x": float(x), "y": float(y), "z": float(z), "face": face, **extra})


def jogar_item(nome: str, quantidade: int = 1, para: str = "") -> str:
    """30/10 (pedido humano): joga o item no chão ou, com `para`, anda até perto do jogador e joga para ele."""
    args = {"name": str(nome or "").strip(), "count": max(1, min(64, int(quantidade or 1)))}
    if str(para or "").strip():
        args["toPlayer"] = str(para).strip()
    return _rpc("toss", args, timeout=45)


def explorar(direcao: str, procurar, blocos: int = 40) -> str:
    """30/10 (pedido humano): anda até `blocos` numa direção e para assim que vê o que procura (até 24 blocos)."""
    alvos = [procurar] if isinstance(procurar, str) else list(procurar or [])
    return _rpc("explore", {"direction": str(direcao or "").strip().lower(), "lookFor": [str(a) for a in alvos][:12],  # revisão Codex: 6 deixava salmão/ovelha de fora
                            "blocks": max(8, min(64, int(blocos or 40)))}, timeout=60)


def usar_item(nome: str = "") -> str:
    return _rpc("use_item", {"name": nome} if nome else {}, timeout=20 if nome else None)


def seguir_jogador(nome: str, distancia: float = 2.0) -> str:
    return _rpc("follow", {"username": nome, "distance": float(distancia)})
