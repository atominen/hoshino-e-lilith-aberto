"""
Compactação de contexto.

O corte antigo era por número de mensagens: passou de 30, joga fora as mais
antigas. Dois problemas. Primeiro, 30 mensagens curtas e 30 mensagens com saída de
comando colada dentro não ocupam nem de longe o mesmo espaço — o teto real é
token, não turno. Segundo, e pior: o que saía, saía. Se a pessoa contou uma coisa
importante no começo da conversa e a conversa esticou, aquilo simplesmente deixava
de existir.

Aqui a compactação tem três etapas:

1. **Resgate.** Antes de qualquer coisa, o trecho que vai sair passa pelo escriba.
   O que for durável (nome, combinado, propriedade, preferência) vira memória
   permanente. Isso torna a compactação segura: perder o texto não é perder o fato.
2. **Resumo rolante.** O trecho vira um resumo estruturado, e o resumo anterior
   entra junto na hora de resumir de novo — então a décima compactação ainda
   carrega o que aconteceu na primeira, comprimido.
3. **Corte limpo.** Os últimos turnos ficam intocados, e o corte nunca deixa
   resultado de ferramenta órfão (uma mensagem `tool` sem a chamada que a gerou
   confunde o modelo e alguns servidores recusam).
"""
import os
import sys
import hashlib
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import bd  # noqa: E402

CABECALHO = "[RESUMO DO QUE JÁ CONVERSAMOS — comprimido, mas é história real]"


def tamanho(mensagens: list, extra: str = "") -> int:
    total = config.estimar_tokens(extra)
    for m in mensagens or []:
        total += config.estimar_tokens(str(m.get("content", "")))
        for chamada in m.get("tool_calls") or []:
            total += config.estimar_tokens(str(chamada))
    return total


def precisa_compactar(mensagens: list, extra: str = "") -> bool:
    teto = config.CONTEXTO_MAX_TOKENS * config.LIMIAR_COMPACTACAO
    return tamanho(mensagens, extra) > teto


def ponto_de_corte(mensagens: list, turnos_intocados=None) -> int:
    """Índice até onde compactar, preservando os últimos turnos e sem órfãos."""
    if not mensagens:
        return 0
    # Um "turno" começa numa mensagem do usuário.
    inicios = [i for i, m in enumerate(mensagens) if m.get("role") == "user"]
    preservar = config.TURNOS_INTOCADOS if turnos_intocados is None else max(1,int(turnos_intocados))
    if len(inicios) <= preservar:
        return 0
    corte = inicios[-preservar]
    # Não começar o histórico restante com resultado de ferramenta solto.
    while corte < len(mensagens) and mensagens[corte].get("role") in ("tool", "assistant"):
        corte += 1
    return corte if corte < len(mensagens) else 0


def transcrever(mensagens: list) -> str:
    from core import diagnostics
    linhas = []
    for m in mensagens:
        # Owner-only tool results may be used in the current inference, but
        # never become a public conversation summary or persisted cache.
        m = diagnostics._redact(m, truncate=False)
        papel = {"user": "Pessoa", "assistant": config.ENTIDADE_NOME,
                 "tool": "[ferramenta]", "system": "[contexto]"}.get(m.get("role"), "?")
        if m.get('role') == 'user' and isinstance(m.get('_origem'), dict):
            import json
            origem = m['_origem']
            papel = f"{origem.get('autor_nome', origem.get('autor_id', 'Pessoa'))} [origem={json.dumps(origem, ensure_ascii=False)}]"
        conteudo = str(m.get("content", "")).strip()
        if not conteudo:
            continue
        linhas.append(f"{papel}: {conteudo}")
    return "\n".join(linhas)


PROMPT = """[ESTOU COMPRIMINDO MINHA PRÓPRIA MEMÓRIA DE CURTO PRAZO]

Comprimo o trecho abaixo sem perder o que muda o futuro.

{anterior}

TRECHO A COMPRIMIR:
{trecho}

Devolva exatamente estas quatro seções, sem nada além delas:

FATOS: o que ficou sabido sobre a pessoa, a máquina ou o mundo (uma linha cada)
COMBINADOS: o que foi decidido, prometido ou pedido explicitamente
EM ABERTO: o que ficou pendente, sem resposta ou pela metade
CLIMA: uma linha sobre como foi a conversa e como a pessoa estava

Preservo a autoria e o sujeito de cada declaração. Uma entidade não é o usuário.
Declarações são fatos informados por sua fonte, não verificação externa;
hipóteses, interpretações e reflexões continuam incertas. Não renomeio autores.
Sou específica: nomes, números, decisões. Corto cortesia, corto repetição, corto
o que não servir daqui a uma semana. Seção vazia leva "—"."""


def _prefixo_fio(chave_conversa):
    # Escopo no ID da tabela existente: nenhum banco/coluna/migração mental.
    # Resumos legados sem destinatário não são atribuídos cegamente a um fio.
    wire = json.dumps([config.ENTIDADE_ID, chave_conversa], ensure_ascii=False, separators=(',', ':'))
    return 'res-fio-'+hashlib.sha256(wire.encode()).hexdigest()+'-'


def ultimo_resumo(chave_conversa=None) -> str:
    if chave_conversa is None:
        linha = bd.um("SELECT resumo FROM context_summaries WHERE id NOT LIKE 'daily-%' "
                      "ORDER BY created_at DESC, rowid DESC LIMIT 1")
    else:
        linha = bd.um("SELECT resumo FROM context_summaries WHERE id LIKE ? "
                      "ORDER BY created_at DESC, rowid DESC LIMIT 1", (_prefixo_fio(chave_conversa)+'%',))
    return linha["resumo"] if linha else ""


def prompt_resumo(mensagens: list, *, chave_conversa=None) -> str:
    anterior = ultimo_resumo(chave_conversa)
    bloco = (f"RESUMO ANTERIOR (mantenha o que ainda vale):\n{anterior}\n"
             if anterior else "")
    trecho = transcrever(mensagens)
    # O orçamento de inferência existente valida a entrada completa. Se não
    # couber, o controller diagnostica e preserva o histórico, em vez de resumir
    # só o começo e descartar a parte nunca apresentada ao modelo.
    return PROMPT.format(anterior=bloco, trecho=trecho)


def resgatar_duraveis(mensagens: list, nome_usuario: str = "usuário") -> int:
    """Salva o que for permanente antes de o texto sumir. Não depende do modelo."""
    from mind import scribe
    salvos = 0
    for m in mensagens:
        if m.get("role") != "user":
            continue
        # Histórico legado sem autoria não é reclassificado como fato humano.
        origem = m.get('_origem')
        if not isinstance(origem, dict):
            continue
        achados = scribe.extrair_por_regra(str(m.get("content", "")), origem=origem)
        salvos += len(scribe.registrar_achados(achados, nome_usuario))
    return salvos


def aplicar(resumo: str, mensagens_compactadas: list, tokens_antes: int,
            fatos_salvos: int = 0, *, chave_conversa=None) -> str:
    """Guarda o resumo e devolve o bloco que entra no lugar do trecho removido."""
    resumo = (resumo or "").strip()
    if len(resumo) > config.RESUMO_MAX_CHARS:
        raise ValueError('COMPACTION_SUMMARY_TOO_LARGE: histórico preservado; resumo não truncado.')
    if not resumo:
        return ""
    faixa = ""
    if mensagens_compactadas:
        faixa = f"{len(mensagens_compactadas)} mensagens"
    bd.executar(
        "INSERT INTO context_summaries (id, created_at, faixa, mensagens, tokens_antes, "
        "resumo, fatos_extraidos) VALUES (?,?,?,?,?,?,?)",
        (bd.novo_id(_prefixo_fio(chave_conversa) if chave_conversa is not None else "res", 8),
         bd.agora(), faixa, len(mensagens_compactadas),
         tokens_antes, resumo, fatos_salvos), strict=True)
    return f"{CABECALHO}\n{resumo}"


def historico(limite: int = 5) -> str:
    linhas = bd.consultar("SELECT created_at, mensagens, tokens_antes, fatos_extraidos "
                          "FROM context_summaries ORDER BY created_at DESC LIMIT ?", (limite,))
    if not linhas:
        return "Nenhuma compactação ainda."
    return "\n".join(
        f"- {l['created_at'][:16]}: {l['mensagens']} mensagens (~{l['tokens_antes']} tokens) "
        f"-> resumo, {l['fatos_extraidos']} fato(s) salvos na memória" for l in linhas)


def estado_do_contexto(mensagens: list, extra: str = "") -> str:
    atual = tamanho(mensagens, extra)
    teto = config.CONTEXTO_MAX_TOKENS
    pct = 100 * atual / max(1, teto)
    return f"contexto ~{atual}/{teto} tokens ({pct:.0f}%)"


def activity_projection(messages, tools, *, context_max, output_max):
    """Projeção explícita de recibos já persistidos; não corta a identidade.

    A fonte integral de cada tool message está no episódio privado apontado por
    receipt_id. Mantém pares completos e mede mensagens + schemas + saída/folga
    com a mesma função usada pelo executor, antes de qualquer nova inferência.
    """
    from copy import deepcopy
    from core import resource_manager
    work, schemas = deepcopy(messages), deepcopy(tools)
    def fits():
        return resource_manager.context_requirement(work,schemas,output_max=output_max)[1] <= context_max
    if fits():
        return work, schemas
    projected = 0
    for size in (1200, 500, 160):
        for index, original in enumerate(messages):
            if original.get('role') != 'tool':
                continue
            receipt = original.get('_receipt_id')
            if not receipt:
                continue  # Sem fonte durável, não afirmar que o conteúdo foi preservado.
            text = str(original.get('content',''))
            if len(text) <= size:
                continue
            work[index]['content'] = json.dumps(dict(
                projection='trecho de resultado; não é o resultado completo',
                receipt_id=receipt, total_chars=len(text),
                sha256=hashlib.sha256(text.encode()).hexdigest(),
                excerpt=text[:size], omitted_chars=len(text)-size,
                retrieve='minha_atividade(operacao=ler_resultado, recibo=receipt_id, inicio=..., limite=...)'),
                ensure_ascii=False)
            projected += 1
        if fits():
            break
    # A própria seleção de capacidades pode ser grande. Descoberta permanece
    # disponível; os schemas omitidos não viram ferramentas secretas executáveis.
    # 05/11: antes saía sempre o maior esquema, e numa atividade de programação com 16K saía justamente
    # executar_na_oficina. Agora saem primeiro as ferramentas fora das capacidades declaradas, depois as
    # secundárias delas e só por último o núcleo de cada capacidade; dentro de cada grupo, a maior primeiro.
    omitted=[]
    from core import initiative
    try:
        declared=[c for c in (initiative.activity().get('capacidades') or []) if c in initiative.GROUPS]
    except Exception:  # noqa: BLE001 — sem ponto de retomada legível, vale só o tamanho
        declared=[]
    activity_tools=set().union(*[initiative.GROUPS[c] for c in declared]) if declared else set()
    essential=set().union(*[initiative.ESSENCIAIS.get(c,set()) for c in declared]) if declared else set()
    def keep_rank(schema):
        name=schema['function']['name']
        return 2 if name in essential else 1 if name in activity_tools else 0
    while not fits() and schemas:
        removable=[s for s in schemas if s['function']['name'] not in {'minha_atividade','manual_habilidades'}]
        if not removable:
            break
        item=min(removable,key=lambda s:(keep_rank(s),-len(json.dumps(s,ensure_ascii=False))))
        schemas.remove(item);omitted.append(item['function']['name'])
    if not fits():
        raise ValueError('ACTIVITY_CONTEXT_BUDGET: identidade e fontes preservadas; nenhuma inferência foi enviada.')
    from core import diagnostics
    diagnostics.emit('initiative.context_projected', projected_results=projected,
                     omitted_tool_schemas=omitted, messages_removed=0, identity_preserved=True,
                     required_tokens=resource_manager.context_requirement(work,schemas,output_max=output_max)[1])
    return work, schemas
