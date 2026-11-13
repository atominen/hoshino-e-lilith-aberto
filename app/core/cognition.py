"""Controle cognitivo operacional da Hoshino.

O LLM continua sendo o responsável pela linguagem e pelo raciocínio; este módulo
é o sistema de controle que evita que cada chamada comece do zero.

Ele mantém apenas estado operacional curto:
- objetivo e domínio;
- complexidade e critério de conclusão;
- passos de alto nível, sem registrar cadeia de pensamento privada;
- ferramentas já usadas;
- falhas classificadas;
- próxima necessidade (agir, verificar, mudar de estratégia ou perguntar).

A ideia é transformar "pensar mais" em um ciclo controlável: estado -> ação ->
resultado -> diagnóstico -> próxima ação.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from core import capabilities
from core import intent


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").casefold())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def argumentos_efeito(nome: str, args: dict) -> dict:
    efeito = dict(args or {})
    if nome == 'execute_command':
        # Controles de transporte não constituem outra tentativa/efeito.
        # Não normalizar o comando: espaços entre aspas e diretório importam.
        efeito={k:v for k,v in efeito.items() if k in {'command','ambiente','diretorio','entrada'}}
        efeito.setdefault('ambiente','sistema')
        efeito.setdefault('diretorio',None)
        efeito.setdefault('entrada',None)
    return efeito


def assinatura_chamada(nome: str, args: dict) -> str:
    import json
    return nome + "::" + json.dumps(argumentos_efeito(nome,args), ensure_ascii=False, sort_keys=True, default=str)


def classificar_erro(resultado) -> str:
    """Classifica estado mecânico; texto livre é apenas compatibilidade legada.

    Em execução normal, ``resultado`` é o contrato estruturado de ``dispatch``.
    A versão textual deliberadamente só reconhece marcadores inequívocos, para
    não transformar frases como ``não tenho nada registrado`` em sucesso.
    """
    if isinstance(resultado, dict):
        status = str(resultado.get("status", "unknown"))
        return {
            "success": "sucesso", "error": "erro", "permission": "permissao",
            "timeout": "timeout", "not_found": "nao_encontrado", "offline": "offline", "uncertain": "incerto", "pending": "pendente",
        }.get(status, "indefinido")
    t = normalizar(resultado)
    if not t:
        return "vazio"
    if t.startswith("confirmacao_necessaria") or t.startswith("confirmacao necessaria"):
        return "permissao"
    if t.startswith("rede_desligada") or t.startswith("sem internet"):
        return "offline"
    if t.startswith(("erro:", "erro ", "falha:", "falhou:", "exception:", "traceback")):
        return "erro"
    if t.startswith(("nao encontrei", "nao achei", "nao existe", "nao localizado", "usuario nao localizado")):
        return "nao_encontrado"
    if "[conexao minecraft nao verificada]" in t or "[conexao minecraft não verificada]" in t:
        return "erro"
    if "[conexao minecraft verificada]" in t or "[conexao minecraft confirmada]" in t:
        return "sucesso"
    # Saída textual legada não traz um contrato confiável. O chamador pode
    # tratá-la como sucesso operacional, mas nunca como prova semântica.
    return "indefinido"


def _resultado_info(resultado, nome: str) -> dict:
    """Normaliza resultado estruturado e mantém compatibilidade com testes legados."""
    if isinstance(resultado, dict):
        return resultado
    texto = str(resultado or "")
    classe = classificar_erro(texto)
    # Compatibilidade somente para chamadas antigas que ainda passam string.
    ok = classe not in {"erro", "permissao", "offline", "timeout", "nao_encontrado"}
    meta = capabilities.info(nome)
    return {
        "tool": nome, "ok": ok, "status": "success" if ok else "error",
        "output": texto, "mutates": meta.mutates,
        "requires_verification": bool(meta.requires_verification and ok),
        "verifier": meta.verifier, "verification_key": meta.verification_key,
        "verified": ("[CONEXÃO MINECRAFT VERIFICADA]" in texto),
    }

def _dominio(texto: str) -> str:
    """Classifica por palavras/frases com fronteiras para evitar falsos positivos.

    Ex.: ``interromper`` contém a sequência ``erro``, mas não significa
    depuração. Os padrões abaixo aceitam flexões sem casar substrings acidentais.
    """
    t = normalizar(texto)
    regras = (
        ("depuracao", r"\b(?:erro|bug|falha|trav\w*|quebr\w*|corrig\w*|consert\w*|debug|exception)\b"),
        ("pesquisa", r"\b(?:pesquis\w*|descobr\w*|compar\w*|investig\w*|procur\w*|busc\w*|estud\w*)\b"),
        ("arquivo", r"\b(?:arquiv\w*|past\w*|pdf|txt|document\w*|ler|escrev\w*|edit\w*|zip)\b"),
        ("comunicacao", r"\b(?:discord|mensag\w*|falar com|respond\w*|enviar para|contat\w*)\b"),
        ("ambiente", r"\b(?:tel\w*|janel\w*|aplicativ\w*|program\w*|computador|cpu|ram|gpu|audio|microfone)\b"),
        ("memoria", r"\b(?:memoria|lembr\w*|esquec\w*|guard\w*|record\w*|preferenc\w*|perfil)\b"),
        ("automacao", r"\b(?:automatiz\w*|continu\w*|enquanto|ate eu|periodic\w*|monitor\w*|vigiar)\b"),
        ("criacao", r"\b(?:criar|criando|gerar|gerando|desenhar|faz\w* um|codigo|script|projet\w*)\b"),
    )
    for nome, padrao in regras:
        if re.search(padrao, t):
            return nome
    return "geral"


def _complexidade(texto: str, ferramentas: list[str]) -> str:
    t = normalizar(texto)
    sinais = 0
    sinais += min(t.count(" e "), 2)
    sinais += len(re.findall(r"\b(depois|entao|então|primeiro|segundo|por fim|enquanto|até|ate)\b", t))
    sinais += len(re.findall(r"\b(arquivo|discord|internet|terminal|memoria|xadrez|tela)\b", t)) // 2
    if len(ferramentas) >= 8:
        sinais += 1
    if len(t) > 300:
        sinais += 1
    if sinais >= 5:
        return "alta"
    if sinais >= 2:
        return "media"
    return "baixa"


def _plano_base(dominio: str, texto: str) -> list[str]:
    base = {
        "depuracao": ["reproduzir ou observar", "isolar a causa", "corrigir", "testar novamente"],
        "pesquisa": ["definir a pergunta", "buscar evidência", "comparar fontes", "concluir"],
        "arquivo": ["localizar o alvo", "ler ou modificar", "verificar o resultado"],
        "comunicacao": ["identificar destinatário e contexto", "preparar mensagem", "enviar e conferir"],
        "ambiente": ["observar o estado real", "separar sinal de ruído", "agir só se houver motivo"],
        "memoria": ["consultar o registro real", "resolver conflitos", "atualizar apenas o necessário"],
        "automacao": ["definir condição de início", "executar sem bloquear", "observar resultado", "interromper na condição certa"],
        "criacao": ["definir resultado", "construir versão mínima", "testar", "refinar"],
        "geral": ["entender o objetivo", "verificar o que já existe", "agir", "verificar o resultado"],
    }
    return base.get(dominio, base["geral"])[:4]


@dataclass
class CognitiveFrame:
    objetivo: str
    dominio: str
    complexidade: str
    criterio: str = "resolver o pedido sem inventar estado ou resultado"
    fatos: list[str] = field(default_factory=list)
    lacunas: list[str] = field(default_factory=list)
    plano: list[str] = field(default_factory=list)
    concluidos: list[str] = field(default_factory=list)
    ferramentas_usadas: list[str] = field(default_factory=list)
    sequencia_ferramentas: list[str] = field(default_factory=list)
    falhas: list[dict] = field(default_factory=list)
    ultima_acao: str = ""
    proxima_necessidade: str = ""
    evidencias: list[str] = field(default_factory=list)
    verificacoes: dict[str, bool | None] = field(default_factory=dict)
    # 07/11 (teste de uso): aberturas que já deram certo neste turno, para não abrir a mesma página de novo.
    aberturas_feitas: dict[str, str] = field(default_factory=dict)
    iniciativa_requerida: bool = False
    acao: str = "conversar"
    ferramenta_sugerida: str = ""
    alvo: str = ""
    verificar_depois: bool = False
    verificador_pendente: str = ""
    chave_verificacao_pendente: str = ""
    resultado_incerto: bool = False
    resultado_pendente: bool = False
    resultados_ferramentas: list[dict] = field(default_factory=list)
    confianca_intencao: float = 0.0
    ferramentas_esperadas: tuple[str, ...] = ()
    parametros_sugeridos: dict = field(default_factory=dict)
    tarefa_id: str = ""
    tarefa_objetivo: str = ""
    etapas_pendentes: list[str] = field(default_factory=list)
    etapas_concluidas: list[str] = field(default_factory=list)
    activity_scope: str = ""
    activity_mode: str = ""
    activity_name: str = ""

    @property
    def multi_etapa(self) -> bool:
        """Uma tarefa persistente com pendências é multi-etapa mesmo quando a mensagem atual é curta."""
        if self.etapas_pendentes or self.etapas_concluidas:
            return True
        t = normalizar(self.objetivo)
        return bool(re.search(
            r"\b(primeiro|depois|em seguida|entao|então|por fim|depois disso|tambem|também)\b",
            t
        )) or bool(re.search(r"\b(e)\b", t) and len(re.findall(r"\b(?:abra|crie|edite|altere|execute|rode|mande|envie|pesquise|leia|feche|volte|continue|registre|mova|clique)\w*\b", t)) >= 2)

    def compacto(self) -> str:
        falhas = "; ".join(f"{f['ferramenta']}: {f['classe']}" for f in self.falhas[-3:]) or "nenhuma"
        concluidos = ", ".join(self.concluidos[-3:]) or "nenhum"
        prox = self.proxima_necessidade or (self.plano[0] if self.plano else "resolver objetivo")
        evid = "; ".join(self.evidencias[-5:]) or "nenhuma"
        pend_task = ", ".join(self.etapas_pendentes[:4]) or "nenhuma"
        done_task = ", ".join(self.etapas_concluidas[-3:]) or "nenhuma"
        return (
            f"objetivo={self.objetivo[:180]} | acao={self.acao} | ferramenta={self.ferramenta_sugerida or 'nenhuma'} | "
            f"confianca_intencao={self.confianca_intencao:.2f} | alvo={self.alvo[:100]} | "
            f"parametros={str(self.parametros_sugeridos)[:260]} | dominio={self.dominio} | complexidade={self.complexidade} | "
            f"proximo={prox[:180]} | concluidos={concluidos} | falhas={falhas} | "
            f"tarefa_id={self.tarefa_id or 'nenhuma'} | pendencias_tarefa={pend_task[:500]} | "
            f"etapas_tarefa_concluidas={done_task[:350]} | verificar={self.verificar_depois} | evidencias={evid[:500]}"
        )


def criar_frame(objetivo: str, ferramentas: list[dict] | list[str] | None = None,
                criterio: str = "", iniciativa_requerida: bool | None = None,
                tarefa: dict | None = None) -> CognitiveFrame:
    nomes = []
    for item in ferramentas or []:
        if isinstance(item, str):
            nomes.append(item)
        else:
            try:
                nomes.append(item["function"]["name"])
            except Exception:
                pass
    interpretacao = intent.interpretar(objetivo)
    dominio = interpretacao.dominio if interpretacao.confianca >= 0.85 else _dominio(objetivo)
    objetivo_norm = normalizar(objetivo)
    iniciativa = bool(re.search(r"\b(escolha|decida|decidir|sozinha|sozinho|por conta propria|por conta própria|explore|explorar|tente algo|qualquer coisa|alguma coisa|continue|continua|fica fazendo)\b", objetivo_norm)) if iniciativa_requerida is None else bool(iniciativa_requerida)
    tarefa = tarefa or {}
    frame = CognitiveFrame(
        objetivo=(objetivo or "").strip(),
        dominio=dominio,
        complexidade=_complexidade(objetivo, nomes),
        criterio=criterio or "resolver o pedido sem inventar estado ou resultado",
        plano=_plano_base(dominio, objetivo),
        iniciativa_requerida=iniciativa,
        acao=interpretacao.acao,
        ferramenta_sugerida=interpretacao.ferramenta_principal if interpretacao.confianca >= 0.85 else "",
        alvo=interpretacao.alvo,
        confianca_intencao=interpretacao.confianca,
        ferramentas_esperadas=tuple(
            x for x in (interpretacao.ferramenta_principal, *interpretacao.ferramentas_suporte)
            if x
        ) if interpretacao.confianca >= 0.85 else (),
        parametros_sugeridos=dict(interpretacao.parametros_sugeridos or {}),
        tarefa_id=str(tarefa.get("id") or ""),
        tarefa_objetivo=str(tarefa.get("objetivo") or ""),
        etapas_pendentes=[str(x) for x in tarefa.get("pendentes", [])],
        etapas_concluidas=[str(x) for x in tarefa.get("concluidas", [])],
    )
    if frame.etapas_pendentes:
        frame.plano = list(frame.etapas_pendentes)
        frame.proxima_necessidade = frame.etapas_pendentes[0]
    else:
        frame.proxima_necessidade = frame.plano[0] if frame.plano else "resolver objetivo"
    return frame


def registrar_ferramenta(frame: CognitiveFrame, nome: str, resultado) -> str:
    """Consolida um resultado sem reclassificar o texto livre da ferramenta."""
    info = _resultado_info(resultado, nome)
    if nome == 'diario':
        from core import diagnostics
        # Do not mutate the actual receipt delivered to the owner's inference.
        info = diagnostics._redact(dict(info,tool=nome),truncate=False)
    frame.sequencia_ferramentas.append(nome)
    if nome not in frame.ferramentas_usadas:
        frame.ferramentas_usadas.append(nome)
    frame.ultima_acao = nome
    frame.resultados_ferramentas.append(info)

    classe = classificar_erro(info)
    if classe == 'pendente':
        frame.resultado_pendente = True
        frame.verificar_depois = True
        frame.proxima_necessidade = 'acompanhar job em execução; não afirmar conclusão'
        return classe
    if classe not in ("sucesso", "indefinido"):
        frame.falhas.append({
            "ferramenta": nome, "classe": classe,
            "resumo": str(info.get("output", ""))[:180],
            "status": info.get("status", ""),
        })
        frame.verificar_depois = classe == 'incerto'
        frame.verificador_pendente = ""
        frame.chave_verificacao_pendente = ""
        if classe == 'incerto':
            frame.resultado_incerto = True
            frame.proxima_necessidade = 'resultado mutável incerto: verificar externamente; não repetir a ação'
        elif classe in ("nao_encontrado", "offline"):
            frame.proxima_necessidade = "mudar de fonte ou estratégia"
        elif classe == "timeout":
            frame.proxima_necessidade = "quebrar a tarefa ou acompanhar o job"
        elif classe == "permissao":
            frame.proxima_necessidade = "pedir/usar a autorização correta"
        else:
            frame.proxima_necessidade = "diagnosticar a causa antes de repetir"
        return classe

    if classe == "sucesso":
        frame.concluidos.append(nome)
        bruto = str(info.get("output", ""))
        frame.proxima_necessidade = (
            f"verificar com {info.get('verifier')}" if info.get("requires_verification") and info.get("verifier")
            else ("verificar dependências do resultado" if frame.complexidade != "baixa" else "finalizar")
        )

        if nome in {"minecraft_conectar", "minecraft_conectar_lan"}:
            if info.get("verified"):
                frame.evidencias.append("Minecraft: conexão verificada por marcador estruturado")
                frame.verificacoes["minecraft"] = True
            else:
                frame.evidencias.append("Minecraft: tentativa de conexão sem verificação estruturada")
                frame.verificacoes["minecraft"] = None
        elif nome == "minecraft_estado":
            if info.get("verified"):
                if frame.verificacoes.get("minecraft") is False:
                    frame.evidencias.append("CONTRADIÇÃO RESOLVIDA: estado atual confirma conexão Minecraft pronta")
                frame.evidencias.append("Minecraft: estado atual confirma conexão pronta")
                frame.verificacoes["minecraft"] = True
            else:
                if frame.verificacoes.get("minecraft") is True:
                    frame.evidencias.append("CONTRADIÇÃO: estado atual não confirma conexão Minecraft pronta")
                frame.evidencias.append("Minecraft: estado atual não confirmou conexão pronta")
                frame.verificacoes["minecraft"] = False
        else:
            frame.evidencias.append(f"{nome}: execução aceita pelo dispatcher (status=success)")

        # Um verificador declarado resolve apenas a pendência que ele é capaz de
        # verificar. Não existe mais uma lista global de nomes mágicos.
        if frame.chave_verificacao_pendente and info.get("verification_key") == frame.chave_verificacao_pendente:
            frame.verificar_depois = False
            frame.verificador_pendente = ""
            frame.chave_verificacao_pendente = ""
        elif frame.verificador_pendente and nome == frame.verificador_pendente:
            frame.verificar_depois = False
            frame.verificador_pendente = ""
            frame.chave_verificacao_pendente = ""

        if info.get("requires_verification"):
            frame.verificar_depois = True
            frame.verificador_pendente = str(info.get("verifier") or "")
            frame.chave_verificacao_pendente = str(info.get("verification_key") or "")
    return classe

def tentativa_verificada(frame: CognitiveFrame) -> bool:
    """Confirma tentativa operacional, nunca conclusão de uma meta aberta.

    Conservador: sem recibo verificado, leitura incidental/otimismo não conta.
    Mantém um falso negativo preferível a aprendizado de sucesso fictício.
    """
    results = frame.resultados_ferramentas
    if not results or frame.resultado_incerto or frame.resultado_pendente or frame.verificar_depois or frame.etapas_pendentes:
        return False
    if frame.ferramenta_sugerida and not any(r.get('tool') == frame.ferramenta_sugerida for r in results):
        return False
    return all(r.get('ok') is True and r.get('verified') is True for r in results)


def prompt_controle(frame: CognitiveFrame) -> str:
    """Retorna um controle curto para o próximo passo; não contém chain-of-thought."""
    return (
        "[CONTROLE COGNITIVO — estado operacional]\n"
        + frame.compacto()
        + "\nRegras operacionais: antes de agir, identifique o objetivo, o que já foi verificado, "
          "as pré-condições e o resultado observável esperado; consulte o estado real antes de "
          "ações que dependem dele; escolha a ferramenta que mais reduz a incerteza ou aproxima "
          "o objetivo; depois da ação, compare resultado e estado com o esperado. Não repita "
          "exatamente uma chamada que falhou sem que alguma condição tenha mudado. Se uma abordagem "
          "falhou, diagnostique e mude o caminho. Em tarefas abertas, você deve escolher deliberadamente "
          "um subobjetivo de baixo risco e executar uma ação concreta sem esperar uma instrução para "
          "cada passo. Não confunda tentativa com sucesso e não transforme uma resposta textual da "
          "própria ferramenta em prova quando existir um estado independente para conferir. Se duas "
          "fontes de estado entrarem em conflito, trate o estado observável mais recente como a fonte "
          "de verdade operacional, registre a contradição e corrija a conclusão. Se faltar informação "
          "essencial, pergunte objetivamente em vez de inventar."
    )


def deve_continuar(frame: CognitiveFrame) -> bool:
    """Retorna se o estado operacional ainda possui uma pendência real.

    Uma tarefa persistente ativa é a fonte de verdade para a conclusão do turno:
    se ainda existem etapas pendentes, uma resposta textual do modelo não pode
    encerrar o ciclo. O agente precisa voltar ao loop ação -> observação -> próximo passo.
    """
    if frame.resultado_incerto or frame.resultado_pendente:
        return False  # entregar a pendência, não gastar novos ciclos mutáveis
    if frame.verificacoes.get("minecraft") is False:
        return False
    if frame.tarefa_id and frame.etapas_pendentes:
        return True
    if frame.iniciativa_requerida and len(frame.ferramentas_usadas) < 2 and frame.dominio not in {"comunicacao"}:
        return True
    if frame.verificar_depois:
        return True
    if frame.proxima_necessidade.startswith(("diagnosticar", "mudar de", "quebrar a")):
        return bool(frame.falhas)
    return False

def nudge_continuacao(frame: CognitiveFrame) -> str:
    """Instrução operacional curta para impedir encerramento prematuro."""
    if frame.etapas_pendentes:
        pend = "; ".join(frame.etapas_pendentes[:5])
        return (
            "A tarefa persistente ainda não terminou. Não recomece e não trate esta mensagem como pedido isolado. "
            f"Próximas etapas pendentes: {pend}. Execute a próxima etapa agora e atualize o progresso."
        )
    if frame.verificador_pendente:
        return (f"A ação já foi executada, mas ainda falta a verificação declarada pela ferramenta: "
                f"{frame.verificador_pendente}. Execute-a antes de concluir.")
    if frame.verificacoes.get("minecraft") is True:
        return ("A conexão foi confirmada, mas ainda falta uma leitura independente do estado do Minecraft. "
                "Consulte minecraft_estado antes de concluir.")
    if frame.iniciativa_requerida and len(frame.ferramentas_usadas) < 2 and frame.dominio not in {"comunicacao"}:
        return ("Não encerre ainda. O pedido é deliberadamente aberto: escolha um subobjetivo "
                "razoável com base no estado real, use uma ferramenta disponível e depois verifique "
                "o resultado. Não espere uma instrução para cada passo.")
    return ("Continue o ciclo operacional: observe o resultado real, elimine incertezas e só finalize "
            "quando o critério de conclusão estiver sustentado por evidência.")



def precisa_verificacao_de_conclusao(texto: str, frame: CognitiveFrame) -> bool:
    """Guarda conservadora contra alegações externas sem evidência, inclusive quando há evidência conflitante."""
    t = normalizar(texto)
    def positive(pattern):
        return any(not re.search(r'\b(?:nao|nunca|sem)\s+(?:ter\s+)?$',t[max(0,m.start()-18):m.start()])
                   for m in re.finditer(pattern,t))
    if frame.etapas_pendentes and positive(r'\b(?:terminei|conclui|tudo pronto|todos os requisitos cumpridos)\b'):
        return True
    if positive(r'\b(?:testes (?:passaram|aprovados)|programa aprovado|contrato (?:validado|cumprido))\b'):
        if frame.etapas_pendentes or not any(r.get('tool') in {'execute_command','ver_comando'}
                                            and r.get('ok') for r in frame.resultados_ferramentas):
            return True
    if positive(r'\b(?:executei|rodei|testei)\b'):
        if not any(r.get('tool') in {'execute_command','ver_comando'} and (r.get('ok') or
            re.search(r'^\[[^\n]*\|\s*sa[ií]da\s+-?\d+\]',str(r.get('output','')),re.I))
            for r in frame.resultados_ferramentas): return True
    if positive(r'\b(?:entreguei|arquivo entregue)\b'):
        if not any(r.get('tool')=='entregar_arquivo' and r.get('ok') and r.get('verified')
                   for r in frame.resultados_ferramentas): return True
    if re.search(r"\b(conectei|entrei|estou dentro|estou conectada|conectada ao minecraft)\b", t):
        if frame.verificacoes.get("minecraft") is not True:
            return True

    if re.search(r"\b(enviei|mandei|mensagem enviada)\b.*\b(discord|andrews|canal)\b", t):
        if not any(r.get('tool') == 'discord_enviar' and r.get('ok') and
                   r.get('delivery_status') == 'delivered' for r in frame.resultados_ferramentas):
            return True

    if re.search(r"\b(baixei|download concluido|download feito)\b", t):
        if not any(r.get('ok') and r.get('tool') in {'baixar_arquivo', 'download', 'importar'}
                   for r in frame.resultados_ferramentas) or frame.verificar_depois:
            return True

    if re.search(r"\b(instalei|instalado com sucesso)\b", t):
        if not any(r.get('ok') and r.get('tool') in {'instalar_aplicativo', 'instalar_pacote', 'instalar_pacote_ia', 'instalar_pacote_oficina'}
                   for r in frame.resultados_ferramentas) or frame.verificar_depois:
            return True
    return False


def fatos_verificados(frame: CognitiveFrame) -> str:
    """Resumo de evidências observadas, sem expor cadeia de pensamento."""
    if not frame.evidencias:
        return "nenhuma evidência externa registrada neste ciclo"
    return "\n".join(f"- {x}" for x in frame.evidencias[-8:])
