"""Interpretação operacional curta de pedidos em português.

Não tenta substituir o LLM. Ela extrai sinais estáveis que o controlador pode
usar para selecionar capacidades, preencher contexto e detectar ambiguidades.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


@dataclass(frozen=True)
class Intent:
    acao: str = "conversar"
    dominio: str = "geral"
    ferramenta_principal: str = ""
    ferramentas_suporte: tuple[str, ...] = ()
    alvo: str = ""
    parametros_sugeridos: dict = field(default_factory=dict)
    confianca: float = 0.0
    ambiguo: bool = False


def _tem(t: str, *padroes: str) -> bool:
    return any(re.search(p, t) for p in padroes)


def contem_expressao_matematica(texto: str) -> bool:
    """Versões, endereços/máscaras e datas são dados, não operações aritméticas."""
    value=normalizar(texto)
    value=re.sub(r'\b\d+(?:\.\d+){2,}(?:/\d+)?\b',' ',value)
    value=re.sub(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b',' ',value)
    return bool(re.search(r'(?<![\w./])\d+(?:[.,]\d+)?\s*[+\-*/%]\s*\d+(?:[.,]\d+)?(?![\w./])',value))


def execucao_proibida(texto: str) -> bool:
    """Negação explícita de toda execução neste pedido, não de uma ação isolada."""
    return bool(re.search(r'(?:^|[.!?;\n])\s*nao\s+(?:execute\s+acoes|use\s+ferramentas|execute\s+ferramentas)\b',
                          normalizar(texto)))


def interpretar(texto: str) -> Intent:
    t = normalizar(texto)
    if execucao_proibida(texto):
        return Intent(confianca=1.0)

    # A final reply to the human is not delivery to another entity. Resolve
    # only an explicit, unambiguous request; composing remains the LLM's job.
    send = r'\b(?:mande|manda|envie|envia|diga|cumprimente)\b'
    social = r'\b(?:oi|ola|mensagem|recado|apresente|cumprimente)\b'
    # Quoted speech/code is data, not a command from the current interlocutor.
    action_text=re.sub(r'```.*?```|`[^`]*`|"[^"]*"|“[^”]*”|\x27[^\x27]*\x27',' ',t,flags=re.S)
    blocked = _tem(action_text, r'\b(?:nao|nem|sem)\s+(?:mande|manda|envie|envia|enviar|mandar|diga|cumprimente)\b',
                   r'\b(?:rascunho|exemplo|hipotetic|explique|significa)\w*\b',
                   r'\b(?:caso|quando)\b|\bse\b(?!\s+apresente\b)',
                   r'^\s*(?:escreva|redija|componha|simule|imagine|traduza|leia|analise|o que|como)\b',
                   r'\b(?:que|disse|dizia)\s+(?:mande|manda|envie|envia|diga)\b')
    if re.search(send,action_text) and re.search(social,t) and not blocked and not _tem(action_text,r'\bdiscord\b'):
        names=r'(?:hoshino|lilith|alistair)'
        targets=re.findall(r'\b(?:para|pra|pro|ao|a|com)\s+(?:o\s+|a\s+)?('+names+r')\b',action_text)
        if not targets:
            targets=re.findall(r'\bso existe (?:um|uma)\s+('+names+r')\b',action_text)
        if not targets:
            routing=re.sub(r'\b(?:e\s+)?se\s+apresente\s+'+names+r'\b','',action_text)
            targets=re.findall(send+r'[^.!?\n]{0,60}?\b('+names+r')\b',routing)
        ambiguous=_tem(t,r'\b'+names+r'\s+(?:ou|e)\s+'+names+r'\b')
        if len(set(targets))==1 and not ambiguous:
            target=targets[0]
            return Intent('enviar_mensagem_entidade','interentidades','entidades_enviar_mensagem',
                          alvo=target,parametros_sugeridos={'entidade':target},confianca=.98)

    if (_tem(t,r'\b(?:veja|olhe|observe|identifique|descreva)\b.*\b(?:imagem recebida|anexo)\b')
            and not _tem(t,r'\b(?:nao|sem|nem)\s+(?:veja|olhe|observe|identifique|descreva)\b')):
        nomes = re.findall(r'(?<![\w/])([\w.-]+\.(?:png|jpe?g|gif|webp|bmp))\b',str(texto),re.I)
        return Intent('observar_imagem_recebida','arquivos','observar_imagem_recebida',
                      parametros_sugeridos={'nome':nomes[0]} if len(nomes)==1 else {},confianca=.97)

    texto_copiado = re.search(r'(?im)^leia o anexo ([0-9a-f]{12}-clipboard-texto\.txt)\.?\s*$', str(texto))
    if texto_copiado:
        return Intent('ler_recebido', 'arquivos', 'ler_recebido',
                      parametros_sugeridos={'nome': texto_copiado[1]}, confianca=.97)

    # ---- interação / microfone / silêncio
    if _tem(t, r"\b(?:mude|altere|defina|configure|troque)\b.*\b(?:atalho|tecla)\b.*\b(?:microfone|mic)\b",
            r"\b(?:atalho|tecla)\b.*\b(?:microfone|mic)\b"):
        m = re.search(r"(?:para|como|em)\s+(.+)$", t)
        atalho = m.group(1).strip(" .,:;") if m else ""
        return Intent("definir_atalho_microfone", "microfone", "definir_atalho_microfone",
                       ("estado_microfone",), parametros_sugeridos={"atalho": atalho} if atalho else {},
                       alvo=atalho, confianca=0.98)
    if _tem(t, r"\b(?:fica|fique|entre|ative|ativa)\b.*\b(?:silencio|silêncio|quieta)\b",
            r"\b(?:pare|nao fale|não fale)\b.*\b(?:sozinha|espontaneamente|por conta própria|por conta propria)\b"):
        return Intent("ativar_silencio", "interacao", "definir_modo_silencioso",
                       (), parametros_sugeridos={"silencioso": True}, confianca=0.98)
    if _tem(t, r"\b(?:pode|volte a|retome|desative|desliga|desligue)\b.*\b(?:falar|silencio|silêncio)\b",
            r"\b(?:fale|fala)\b.*\b(?:de novo|novamente)\b"):
        return Intent("desativar_silencio", "interacao", "definir_modo_silencioso",
                       (), parametros_sugeridos={"silencioso": False}, confianca=0.98)

    # ---- controle explícito do fio de tarefa
    if _tem(t, r"^(?:continue|continuar|retome|retomar|prossiga|prosseguir)\b") and _tem(t, r"\b(?:tarefa|trabalho|anterior|pendente|estava fazendo|estávamos fazendo)\b"):
        return Intent("retomar_tarefa", "tarefa", "", (), confianca=0.99)

    # ---- conexões e estado Minecraft
    if _tem(t, r"\b(conecte|conectar|entrar|entre)\b.*\b(minecraft|lan)\b", r"\bminecraft\b.*\b(lan|conect)"):
        explicit=bool(re.search(r'\bporta\s*:?\s*\d{2,5}\b|\b\d+(?:\.\d+){3}:\d{2,5}\b',t))
        return Intent("conectar_minecraft", "minecraft", "minecraft_conectar" if explicit else "minecraft_conectar_lan",
                       ("minecraft_iniciar_ponte", "minecraft_estado") if explicit else ("minecraft_iniciar_ponte", "minecraft_descobrir_lan", "minecraft_estado"),
                       confianca=0.98)
    if _tem(t, r"\b(minecraft)\b") and _tem(t, r"\b(estado|situacao|situação|posicao|posição|inventario|inventário)\b"):
        ferramenta = "minecraft_inventario" if _tem(t, r"inventario|inventário") else "minecraft_estado"
        return Intent("consultar_minecraft", "minecraft", ferramenta,
                       ("minecraft_estado",), confianca=0.95)
    if _tem(t, r"\b(mine|minerar|minere|minera|quebrar|quebre)\b"):
        alvo = ""
        m = re.search(r"\b(?:mine|minere|minerar|quebre|quebrar)\s+(?:a|o|um|uma)?\s*([a-zà-ÿ0-9_ -]+?)(?=\s+(?:perto|aqui|ali|em|no|na|com)\b|$)", t)
        if m:
            alvo = m.group(1).strip()
        params = {"nome": alvo} if alvo else {}
        return Intent("minerar_minecraft", "minecraft", "minecraft_minerar",
                       ("minecraft_estado", "minecraft_procurar_bloco", "minecraft_parar"),
                       alvo=alvo, parametros_sugeridos=params, confianca=0.96)
    if _tem(t, r"\b(coletar|colete|pegar|pegue)\b") and _tem(t, r"\b(pedra|bloco|minerio|min[ée]rio|item)"):
        return Intent("coletar_minecraft", "minecraft", "minecraft_coletar",
                       ("minecraft_estado", "minecraft_procurar_bloco"), confianca=0.93)
    if _tem(t, r"\b(craft|craftar|fabricar|fabrique)\b"):
        return Intent("craft_minecraft", "minecraft", "minecraft_craft",
                       ("minecraft_estado", "minecraft_inventario"), confianca=0.96)
    if _tem(t, r"\b(ir para|va para|andar ate|andar até|navegar|seguir)\b") and _tem(t, r"\bminecraft\b"):
        return Intent("navegar_minecraft", "minecraft", "minecraft_ir_para",
                       ("minecraft_estado", "minecraft_parar"), confianca=0.93)
    if _tem(t, r"\b(atacar|ataque|matar|mate)\b") and _tem(t, r"\bminecraft\b"):
        return Intent("atacar_minecraft", "minecraft", "minecraft_atacar",
                       ("minecraft_estado", "minecraft_parar"), confianca=0.94)

    # ---- Discord / comunicação
    if (_tem(t, r"\b(discord)\b", r"\b(mensagem|dm)\b") and _tem(t, r"\b(enviar|mande|manda|mandar|responder|responda|falar|fale)\b")
            and (_tem(t,r'\bdiscord\b') or not _tem(t,r'\b(?:hoshino|lilith|alistair)\b'))):
        alvo = ""
        mensagem = ""
        m = re.search(r"\b(?:para|pro|pra|com)\s+(.+?)(?=\s+(?:no|pelo)\s+discord\b|\s+(?:dizendo|falando|com a mensagem)\b|$)", t)
        if m:
            alvo = m.group(1).strip(" ,.;:")
            alvo = re.sub(r"^(?:o|a|os|as)\s+", "", alvo).strip()
        mm = re.search(r"\b(?:dizendo|falando|com a mensagem)\s+(.+)$", t)
        if mm:
            mensagem = mm.group(1).strip()
        params = {}
        if alvo:
            params["destino"] = alvo
        if mensagem:
            params["texto"] = mensagem
        return Intent("enviar_mensagem", "comunicacao", "discord_enviar",
                       ("discord_localizar_usuario", "discord_contatos", "discord_estado"),
                       alvo=alvo, parametros_sugeridos=params, confianca=0.97)
    if _tem(t, r"\b(iniciar|ligar|abrir)\b.*\bdiscord\b"):
        return Intent("iniciar_discord", "comunicacao", "iniciar_discord", ("discord_diagnostico", "discord_estado"), confianca=0.97)
    pedido_discord = _tem(t, r"\b(?:qual|como|consulte|consultar|verifique|verificar|mostre|mostrar|confira)\b[^.!?\n]*\bdiscord\b|\bdiscord\b[^.!?\n]*\?|^(?:estado|diagnostico)\b[^.!?\n]*\bdiscord\b")
    if pedido_discord and _tem(t, r"\b(estado|diagnostico|diagnóstico|online|offline|funcionando)\b"):
        return Intent("consultar_discord", "comunicacao", "discord_estado", ("discord_diagnostico",), confianca=0.95)

    # ---- criação de ferramenta própria
    if _tem(t, r"\b(?:crie|criar|desenvolva|desenvolver|monte|montar)\b.*\b(?:ferramenta|tool)\b"):
        return Intent("criar_ferramenta", "oficina", "criar_ferramenta",
                       ("estado_da_oficina", "listar_ferramentas", "escrever_na_oficina", "executar_na_oficina"),
                       confianca=0.98)

    # Corrigir um arquivo precede a execução pedida para depois da correção.
    # Não interpretar "corrija X.py; depois rode" como apenas rodar X.py.
    if (_tem(t,r'\b(?:corrija|corrigir)\b')
            and _tem(t,r'\b(?:arquivo|script|codigo)\b|\.(?:py|txt|md|html|json|csv)\b')
            and not _tem(t,r'\b(?:nao|sem|nem)\s+(?:corrija|corrigir)\b')):
        return Intent('corrigir_arquivo','arquivo','workspace',(),confianca=.97)

    # ---- execução de arquivo/programa
    if _tem(t, r"\b(?:execute|executar|rode|rodar|inicie|iniciar)\b") and _tem(
        t, r"\b(?:arquivo|programa|script|python|\.py\b|\.sh\b|comando)\b"):
        m = re.search(r"(?:arquivo|programa|script)\s+([~./\w-]+(?:\.\w+)?)", t)
        comando = m.group(1).strip() if m else ""
        return Intent("executar_programa", "sistema", "execute_command",
                       ("list_files", "read_file"), parametros_sugeridos={"command": comando} if comando else {},
                       alvo=comando, confianca=0.96)

    # ---- pastas: capacidade específica para não confundir mkdir com write_file
    if _tem(t, r"\b(?:crie|criar|criado|cria|faça|faca|fazer)\b") and _tem(t, r"\b(?:pasta|pastas|diretorio|diretório|diretorios|diretórios)\b"):
        return Intent("criar_pasta", "arquivo", "make_directory", ("list_files",), confianca=0.99)

    # ---- arquivos
    if _tem(t, r"\b(crie|criar|escreva|escrever|editar|edite|alterar|modificar|salvar)\b") and _tem(t, r"\b(arquivo|txt|pdf|documento)\b"):
        return Intent("escrever_arquivo", "arquivo", "write_file", ("read_file", "list_files"), confianca=0.97)
    if _tem(t, r"\b(?:leia|ler|leio|ver|veja)\b") and _tem(t, r"\b(?:resultado|saida|saída|arquivo|txt|pdf|documento|conteudo|conteúdo)\b"):
        return Intent("ler_arquivo", "arquivo", "read_file", ("list_files",), confianca=0.96)
    if _tem(t, r"\b(baixar|baixe|download)\b"):
        return Intent("baixar_arquivo", "arquivo", "baixar_arquivo", ("web_search", "fetch_page"), confianca=0.95)
    if (_tem(t, r"\b(entregue|entregar|envie|enviar|mandar|manda|mande)\b")
            and _tem(t, r"\b(arquivo|documento)\b|\.(?:json|csv|py|txt|md|png|zip)\b")
            and not _tem(t,r'\b(?:nao|sem|nem)\s+(?:entregue|entregar|envie|enviar|mande|mandar)\b')):
        return Intent("entregar_arquivo", "arquivo", "entregar_arquivo", ("listar_entregues",), confianca=0.96)

    # ---- agenda
    if _tem(t, r"\b(me lembra|me lembre|lembrar|lembrete|crie um lembrete)\b"):
        return Intent("criar_lembrete", "agenda", "criar_lembrete", ("listar_lembretes",), confianca=0.98)
    if _tem(t, r"\b(cancelar|cancele)\b") and _tem(t, r"\b(lembrete|agenda)\b"):
        return Intent("cancelar_lembrete", "agenda", "cancelar_lembrete", ("listar_lembretes",), confianca=0.98)

    # ---- memória
    if _tem(t, r"\b(lembre|lembrar|guarde|guardar|anote|anotar|registre|registrar)\b") and _tem(t, r"\b(isso|isto|informacao|informação|fato|regra|preferencia|preferência|nome)\b"):
        return Intent("guardar_memoria", "memoria", "registrar_conhecimento", ("consultar_conhecimento",), confianca=0.93)
    if _tem(t, r"\b(o que voce sabe|o que você sabe|lembra de|tem na memoria|tem na memória|sabe sobre)\b"):
        return Intent("consultar_memoria", "memoria", "consultar_conhecimento", ("como_funciona", "propriedades_de"), confianca=0.95)

    # ---- web / pesquisa
    if _tem(t, r"\b(pesquise|pesquisar|pesquisa|procure|procurar|busque|buscar|descobrir|investigar)\b"):
        return Intent("pesquisar", "pesquisa", "web_search", ("fetch_page",), confianca=0.93)

    # ---- continuidade dentro de uma aba
    if (_tem(t, r"\b(?:role|rolar)\b") and
            _tem(t, r"\b(?:aba|pagina|navegador)\b") and
            not _tem(t, r"\bnao\s+(?:role|rolar)\b")):
        tab = re.search(r"\baba-\d+\b", t)
        amount = re.search(r"\b(\d+)\s*pixels\b", t)
        pixels = int(amount.group(1)) if amount else 700
        if _tem(t, r"\b(?:para\s+)?cima\b"):
            pixels = -pixels
        params = {'pixels': pixels}
        if tab:
            params['aba'] = tab.group(0)
        return Intent('browser_rolar', 'navegador', 'browser_rolar',
                      ('browser_info', 'browser_abas'), parametros_sugeridos=params,
                      confianca=0.96)
    if _tem(t, r"\b(?:volte|voltar|retroceda|retroceder)\b") and _tem(t, r"\b(?:aba|pagina|página|navegador)\b"):
        return Intent("browser_voltar", "navegador", "browser_voltar",
                       ("browser_info", "browser_abas"), confianca=0.96)
    if _tem(t, r"\b(?:avance|avançar|avancar|prossiga|prosseguir)\b") and _tem(t, r"\b(?:aba|pagina|página|navegador)\b"):
        return Intent("browser_avancar", "navegador", "browser_avancar",
                       ("browser_info", "browser_abas"), confianca=0.96)
    if _tem(t, r"\b(?:recarregue|recarregar|atualize|atualizar)\b") and _tem(t, r"\b(?:aba|pagina|página|navegador)\b"):
        return Intent("browser_recarregar", "navegador", "browser_recarregar",
                       ("browser_info", "browser_abas"), confianca=0.96)
    if _tem(t, r"\b(?:clique|clicar|preencha|preencher|digite|digitar|pressione|pressionar)\b") and _tem(t, r"\b(?:aba|site|pagina|página|navegador)\b"):
        return Intent("browser_interacao", "navegador", "browser_clicar",
                       ("browser_info", "browser_abas", "browser_preencher", "browser_tecla"),
                       confianca=0.92)

    if _tem(t, r"\b(?:teste|testar|teste minha|verifique)\b.*\b(?:voz|audio|áudio)\b",
            r"\b(?:testar|teste)\b.*\b(?:minha voz|voz da hoshino)\b"):
        return Intent("testar_voz", "voz", "testar_voz", ("estado_voz",), confianca=0.97)

    # ---- navegador / sites
    mesma_aba = _tem(t, r"\b(?:mesma|essa|esta|atual)\s+aba\b", r"\bnessa\s+aba\b", r"\bna\s+aba\s+atual\b")
    if _tem(t, r"\b(abra|abrir|abre|vai|vá|navegue|navegar)\b") and _tem(t, r"(youtube|wikipedia|google|duckduckgo|github|openstreetmap|google maps|maps\.google|https?://|www\.)"):
        m = re.search(r"(https?://\S+|www\.\S+)", t)
        if m:
            url = m.group(1).rstrip(".,;)")
        elif "google maps" in t or "maps.google" in t:
            local = re.search(r"(?:google maps|maps\.google(?:\.com)?)(?:\s+(?:em|para|por|de)\s+)(.+)$", t)
            if local:
                from urllib.parse import quote_plus
                url = "https://www.google.com/maps/search/" + quote_plus(local.group(1).strip(" .,:;"))
            else:
                url = "https://www.google.com/maps/"
        else:
            sites = {
                "youtube": "https://www.youtube.com/",
                "wikipedia": "https://pt.wikipedia.org/",
                "google": "https://www.google.com/",
                "duckduckgo": "https://duckduckgo.com/",
                "github": "https://github.com/",
                "openstreetmap": "https://www.openstreetmap.org/",
            }
            url = next((u for nome, u in sites.items() if nome in t), "")
        return Intent("abrir_site", "navegador", "browser_abrir", ("browser_abas", "browser_info"),
                       alvo=url, parametros_sugeridos={"url": url, "nova_aba": not mesma_aba} if url else {}, confianca=0.96)

    # ---- desktop / pasta
    if _tem(t,r'\b(?:foque|focar|foca)\s+(?:a\s+)?janela\b') and not _tem(t,r'\b(?:nao|sem)\s+(?:foque|focar|foca)\b'):
        return Intent('focar_janela','ambiente','focar_janela',(),confianca=.97)
    if _tem(t,r'\b(?:observe|observar|olhe|veja)\s+(?:a\s+)?tela\b') and not _tem(t,r'\b(?:nao|sem)\s+(?:observe|observar|olhe|veja)\b'):
        return Intent('observar_tela','ambiente','observar_tela',(),confianca=.97)
    if _tem(t, r"\b(abre|abra|abrir)\b") and _tem(t, r"\b(pasta|diretorio|diretório)\b"):
        m = re.search(r"\b(?:pasta|diretorio|diretório)\s+(.+)$", t)
        caminho = m.group(1).strip().strip('"') if m else ""
        return Intent("abrir_pasta", "ambiente", "abrir_pasta", ("estado_desktop",),
                       alvo=caminho, parametros_sugeridos={"caminho": caminho} if caminho else {}, confianca=0.95)
    if _tem(t, r"\b(abre|abra|abrir|execute|executar)\b") and _tem(t, r"\b(aplicativo|app|programa|firefox|chrome|steam|discord|spotify|vlc|gimp|krita|calculadora|calculator|terminal)\b"):
        app = ""
        m = re.search(r"\b(firefox|chrome|steam|discord|spotify|vlc|gimp|krita|calculadora|calculator|terminal)\b", t)
        if m:
            app = m.group(1)
        return Intent("abrir_aplicativo", "ambiente", "abrir_aplicativo", ("estado_desktop",),
                       alvo=app, parametros_sugeridos={"aplicativo": app} if app else {}, confianca=0.96)
    desktop_afirmativo = re.sub(r'\b(?:nao|sem|nem)\s+(?:clica|clique|clicar|digite|digitar|pressione|pressionar)\b','',t)
    if _tem(desktop_afirmativo, r"\b(clica|clique|clicar|digite|digitar|pressione|pressionar|teclado|mouse)\b"):
        return Intent("acao_desktop", "ambiente", "acao_desktop", ("estado_desktop", "listar_janelas"), confianca=0.92)

    return Intent()
