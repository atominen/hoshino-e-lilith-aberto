"""
Estado persistente de tarefas de conversa.

A conversa continua sendo uma única corrente. Uma mensagem posterior que seja
claramente continuação retoma a tarefa anterior em vez de criar um turno cognitivo
sem memória operacional.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from core import bd, intent
import config

_SCHEMA_DONE = False
_LEGADOS_WORKSPACE = {"make_directory": "pasta", "read_file": "ler", "write_file": "salvar"}

_CONTINUACAO = re.compile(
    r"^(?:agora|depois(?: disso)?|em seguida|entao|e depois|tambem|também|"
    r"por fim|a seguir|continue|continuar|proximo|pr[oó]ximo|isso|nesse caso|"
    r"feito|ok[, ]+agora)\b",
    re.IGNORECASE,
)
_RETOMADA_EXPLICITA = re.compile(
    r"^(?:continue|continuar|retome|retomar|prossiga|prosseguir)"
    r"(?:\s+(?:a|o)?\s*(?:tarefa|trabalho)(?:\s+(?:anterior|pendente))?"
    r"(?:\s+(?:a|o)?\s*(?:esta|essa)\s+mensagem)?"
    r"|\s+(?:que\s+)?(?:estavamos|estávamos)\s+fazendo)?"
    r"(?:\s*,?\s*(?:nada\s+aconteceu|não\s+aconteceu|nao\s+aconteceu))?\s*$",
    re.IGNORECASE,
)
_CANCELAMENTO = re.compile(
    r"^(?:cancela|cancelar|pare|parar|para|esquece|deixa pra la|deixa pra lá|"
    r"abandona|abortar|nao quero mais|não quero mais)\b",
    re.IGNORECASE,
)
# 30/10: "depois de trocar…"/"depois que terminar" sem "e" antes marcam tempo dentro da frase, não uma etapa
# seguinte; "teste de velocidade depois de trocar para 33 camadas: como foi fabricar o arco?" virou tarefa de
# fabricar. Revisão Codex: "e depois de terminar me avise" continua sendo a etapa seguinte.
_SEPARADORES = re.compile(
    r"\s*(?:\s+(?:e\s+(?:logo\s+)?depois(?: disso)?|(?:logo\s+)?depois(?!\s+(?:de|do|da|dos|das|que)\b)(?: disso)?|"
    r"(?:e\s+)?(?:em seguida|por fim|a seguir|entao|então))\s+)",
    re.IGNORECASE,
)
_SINAIS_OPERACIONAIS = re.compile(
    r"\b(?:implemente|implementar|implementar-se|crie|criar|execute|executar|"
    r"rode|rodar|faça|fazer|gere|gerar|salve|salvar|leia|ler|"
    r"edite|editar|modifique|modificar|corrija|corrigir|adicione|adicionar|"
    r"calcule|calcular|role|sortear|sorteie|valide|validar|"
    r"verifique|verificar|confira|conferir|crie|construir|"
    r"produza|produzir)\b",
    re.IGNORECASE,
)
_PEDIDO = re.compile(r"\b(?:pode|podes|poderia|consegue|conseguiria|quero que|preciso que|gostaria que|"
                     r"por favor|vamos)\b", re.IGNORECASE)
# Pergunta sobre o que já aconteceu ou sobre a opinião dela: conversa, não ordem (30/10, "como foi fabricar o arco?").
_REFLEXAO = re.compile(
    r"\b(?:como (?:é que |e que )?foi|o que (?:(?:você|voce|vc) )?(?:achou|sentiu|aprendeu)|"
    r"(?:você |voce |vc )?gostou|como (?:(?:você|voce|vc) )?se sentiu|"
    r"foi (?:difícil|dificil|fácil|facil|divertido|bom|legal|cansativo))\b",
    re.IGNORECASE,
)

@dataclass
class TaskInfo:
    id: str
    chave: str
    objetivo: str
    status: str
    etapa_atual: int
    etapas: list[dict[str, Any]]
    ultima_acao: str = ""
    ultimo_resultado: str = ""
    workspace_root: str = ""
    known_paths: list[str] | None = None

def _schema():
    global _SCHEMA_DONE
    if _SCHEMA_DONE:
        return
    bd.executar(
        """CREATE TABLE IF NOT EXISTS conversation_tasks (
            id TEXT PRIMARY KEY,
            chave TEXT NOT NULL,
            objetivo TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            etapa_atual INTEGER DEFAULT 0,
            ultima_acao TEXT,
            ultimo_resultado TEXT,
            workspace_root TEXT DEFAULT '',
            known_paths TEXT DEFAULT '[]'
        )"""
    )
    bd.executar(
        """CREATE TABLE IF NOT EXISTS conversation_task_steps (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            ordem INTEGER NOT NULL,
            texto TEXT NOT NULL,
            ferramenta TEXT,
            ferramentas TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            resultado TEXT
        )"""
    )
    task_cols = {str(r.get("name")) for r in bd.consultar("PRAGMA table_info(conversation_tasks)")}
    if "workspace_root" not in task_cols:
        bd.executar("ALTER TABLE conversation_tasks ADD COLUMN workspace_root TEXT DEFAULT ''")
    if "known_paths" not in task_cols:
        bd.executar("ALTER TABLE conversation_tasks ADD COLUMN known_paths TEXT DEFAULT '[]'")
    cols = {str(r.get("name")) for r in bd.consultar("PRAGMA table_info(conversation_task_steps)")}
    if "ferramentas" not in cols:
        bd.executar("ALTER TABLE conversation_task_steps ADD COLUMN ferramentas TEXT DEFAULT ''")
    if "ferramentas_executadas" not in cols:
        bd.executar("ALTER TABLE conversation_task_steps ADD COLUMN ferramentas_executadas TEXT DEFAULT ''")
    _SCHEMA_DONE = True

def chave_texto(chave) -> str:
    if chave is None:
        return ""
    if isinstance(chave, (list, tuple)):
        return "::".join(str(x or "local") for x in chave)
    return str(chave)

def _intencao_da_etapa(texto: str):
    try:
        return intent.interpretar(texto)
    except Exception:
        return None

def _etapas_numeradas(texto: str) -> list[str]:
    """Reconhece um roteiro longo com cabeçalhos ETAPA N como marcos reais."""
    matches = list(re.finditer(r"^\s*ETAPA\s+\d+\b.*$", texto, re.IGNORECASE | re.MULTILINE))
    if len(matches) < 2:
        return []
    partes = []
    for idx, match in enumerate(matches):
        fim = matches[idx + 1].start() if idx + 1 < len(matches) else len(texto)
        bloco = texto[match.start():fim].strip()
        bloco = re.sub(r"^\s*=+\s*$", "", bloco, flags=re.MULTILINE).strip()
        if bloco:
            partes.append(bloco)
    return partes


def _secoes_numeradas(texto: str) -> list[str]:
    """Reconhece seções numeradas de nível superior e preserva seus bullets."""
    matches = list(
        re.finditer(
            r"^\s*(\d+)[.)]\s+.+$",
            str(texto or ""),
            re.MULTILINE,
        )
    )
    if len(matches) < 2:
        return []

    numeros = [int(m.group(1)) for m in matches]
    esperado = list(range(numeros[0], numeros[0] + len(numeros)))
    if numeros[0] != 1 or numeros != esperado:
        return []

    partes = []
    for idx, match in enumerate(matches):
        fim = matches[idx + 1].start() if idx + 1 < len(matches) else len(texto)
        bloco = texto[match.start():fim].strip()
        if bloco:
            partes.append(bloco)
    return partes


def _eh_prompt_estruturado(texto: str) -> bool:
    """Detecta pedidos longos formatados como roteiro/lista.

    Nesses casos, quebras semânticas como "depois" ou "em seguida" pertencem
    ao conteúdo da instrução e não devem criar etapas independentes.
    """
    linhas = [linha.strip() for linha in str(texto or "").splitlines() if linha.strip()]
    if len(linhas) < 6:
        return False

    marcadores = sum(
        bool(re.match(r"^(?:[-*•]|\d+[.)])\s+", linha))
        for linha in linhas
    )

    return marcadores >= 3


def decompor(texto: str) -> list[str]:
    """Divide tarefas em marcos, preservando roteiros estruturados inteiros."""
    texto = str(texto or "").strip()
    if not texto:
        return []

    numeradas = _etapas_numeradas(texto)
    if numeradas:
        return numeradas

    secoes = _secoes_numeradas(texto)
    if secoes:
        return secoes

    if _eh_prompt_estruturado(texto):
        return [texto]

    partes = [p.strip(" ,.;:-") for p in _SEPARADORES.split(texto) if p.strip()]
    return partes or [texto]

def _eh_pedido(trecho: str) -> bool:
    """Trecho depois da pergunta reflexiva que é ordem ou pedido; infinitivo no começo ainda é parte da pergunta."""
    trecho = trecho.strip(" ?")
    if not trecho or _REFLEXAO.match(trecho):
        return False
    trecho = re.sub(r"^por favor\b[ ,]*", "", trecho, flags=re.IGNORECASE)
    if not trecho or re.match(r"\w+(?:ar|er|ir|or)\b", trecho, re.IGNORECASE):
        return False
    if _PEDIDO.search(trecho) or _SINAIS_OPERACIONAIS.search(trecho):
        return True
    i = _intencao_da_etapa(trecho)
    return bool(i and i.confianca >= 0.88 and i.acao != "conversar")


def eh_pergunta_reflexiva(texto: str) -> bool:
    """Uma pergunta só, sobre o passado ou a opinião ("como foi fabricar o arco hoje?", "o que você achou?").

    O verbo dentro dela ("fabricar") não é pedido de fazer de novo. Mensagem com mais de uma frase que termina em
    pergunta só conta se não houver ordem antes ("faça o arco. como foi?" continua sendo tarefa).
    """
    t = re.sub(r"\s+", " ", str(texto or "").strip())
    if not t.endswith("?") or t.count("?") > 1:
        return False
    if len([f for f in re.split(r"(?<=[.!])\s+", t) if f.strip()]) != 1 or len(decompor(t)) > 1:
        return False  # "Crie um arquivo e depois me conte: como foi?" tem uma ordem antes
    # Revisão Codex: a pergunta começa pelo marcador ("…: em duas frases, como foi fabricar o arco?"); dentro de um
    # pedido ele não conta ("Pode fabricar um arco como foi combinado?").
    partes = [re.sub(r"^(?:e|então|entao|mas|agora)\s+", "", p.strip(), flags=re.IGNORECASE)
              for p in re.split(r"[,:;]\s*", t)]
    # Revisão Codex: a oração que abre com o marcador, não a última ("Como foi fabricar o arco hoje, Lilith?").
    inicio = next((n for n, p in enumerate(partes) if _REFLEXAO.match(p)), None)
    if inicio is None:
        return False
    # Pedido coordenado depois da pergunta continua valendo ("Como foi fabricar o arco e fabrique outro?"); um
    # infinitivo continua dentro da pergunta ("Como foi fabricar o arco e fazer a bancada?").
    coordenadas = re.split(r"\s+(?:e|mas|então|entao|ou)\s+", partes[inicio])[1:]
    if any(_eh_pedido(trecho) for trecho in [*coordenadas, *partes[inicio + 1:]]):
        return False
    # Um pedido antes da pergunta continua sendo pedido ("Pode fabricar um arco, como foi combinado?").
    antes = " ".join(partes[:inicio]).strip()
    if not antes:
        return True
    if _PEDIDO.search(antes) or _SINAIS_OPERACIONAIS.search(antes):
        return False
    i = _intencao_da_etapa(antes)
    return not (i and i.confianca >= 0.88 and i.acao != "conversar")


def eh_continuacao(texto: str) -> bool:
    t = str(texto or "").strip()
    if not t:
        return False
    if _CONTINUACAO.search(t):
        return True
    return False


def eh_comando_retomada(texto: str) -> bool:
    """Verdadeiro quando a mensagem só pede para retomar o trabalho anterior.

    Essa frase não é uma etapa nova. Ela é um comando de controle do fio: o
    controlador deve recuperar a próxima etapa pendente e entregá-la ao modelo.
    """
    return bool(_RETOMADA_EXPLICITA.fullmatch(str(texto or "").strip()))


def proxima_operacao(chave) -> dict[str, Any] | None:
    """Retorna exatamente a próxima operação atômica pendente."""
    tarefa = carregar(chave)
    if not tarefa:
        return None
    etapa = next((e for e in tarefa.etapas if e.get("status") == "pending"), None)
    if not etapa:
        return None
    operacoes = list(etapa.get("operacoes_lista") or [])
    executadas = set(etapa.get("ferramentas_executadas_lista") or [])
    restante = next((op for op in operacoes if str(op.get("id")) not in executadas), None)
    if not restante:
        return None
    restantes = [str(op["ferramenta"]) for op in operacoes if str(op.get("id")) not in executadas]
    return {
        "task_id": tarefa.id,
        "etapa_id": str(etapa.get("id") or ""),
        "etapa_ordem": int(etapa.get("ordem") or 0),
        "etapa": str(etapa.get("texto") or ""),
        "instrucao": str(restante.get("instrucao") or etapa.get("texto") or ""),
        "planejada": bool(restante.get("planejada", False)),
        "operacao": str(restante.get("operacao") or "") if restante.get("operacao") else "",
        "modo": str(restante.get("modo") or "") if restante.get("modo") else "",
        "operacao_id": str(restante.get("id") or ""),
        "ferramenta": str(restante.get("ferramenta") or ""),
        "job_id": str(restante.get("job_id") or ""),
        "restantes": restantes,
    }


def ferramentas_pendentes(chave) -> list[str]:
    """Nomes das operações ainda pendentes no marco atual."""
    op = proxima_operacao(chave)
    return list(op.get("restantes") or []) if op else []

def definir_operacoes(chave, operacoes: list[dict[str, Any]]) -> TaskInfo | None:
    """Substitui o plano operacional do marco atual por uma sequência validada."""
    _schema()
    tarefa = carregar(chave)
    if not tarefa:
        return None
    etapa = next((e for e in tarefa.etapas if e.get("status") == "pending"), None)
    if etapa is None:
        return tarefa
    operacoes = list(operacoes or [])
    obrigatorias = sequencia_correcao(str(etapa.get('texto') or ''))
    if obrigatorias:
        if not re.search(r'\b(?:calcule|calculadora|faça\s+(?:a\s+)?conta)\b',str(etapa.get('texto') or ''),re.I):
            operacoes=[op for op in operacoes if op.get('ferramenta')!='calcular']
        # A ordem explicitamente pedida não depende da paráfrase do planner.
        ordered=[]
        for required in obrigatorias:
            matching=next((op for op in operacoes if op.get('ferramenta')==required['ferramenta']
                           and str(op.get('operacao') or '')==str(required.get('operacao') or '')),None)
            ordered.append({**(matching or {}),**required})
        operacoes=ordered+[op for op in operacoes if not any(
            op.get('ferramenta')==r['ferramenta'] and str(op.get('operacao') or '')==str(r.get('operacao') or '')
            for r in obrigatorias)]
    normalizadas = []
    for idx, op in enumerate(operacoes or [], 1):
        nome = str(op.get("ferramenta") or op.get("tool") or "").strip()
        if not nome:
            continue
        normalizadas.append({
            "id": str(op.get("id") or f"op-{idx}"),
            "ferramenta": nome,
            "instrucao": str(op.get("instrucao") or etapa.get("texto") or "")[:2200],
            "planejada": True,
            **({"operacao": str(op.get("operacao") or "").strip()} if op.get("operacao") else {}),
            **({"modo": str(op.get("modo") or "").strip().casefold()} if op.get("modo") else {}),
        })
    if not normalizadas:
        return tarefa
    executadas = list(etapa.get("ferramentas_executadas_lista") or [])
    concluidas = [op for op in etapa.get('operacoes_lista', []) if op['id'] in executadas]
    pendente = next((op for op in etapa.get('operacoes_lista', []) if op['id'] not in executadas), None)
    if pendente and pendente.get('job_id'):
        # A ação já ocorreu. Replanejamento não pode apagar a consulta vinculada
        # e devolver o controlador ao comando original, repetindo seus efeitos.
        return tarefa
    if obrigatorias and pendente and ('::repair-' in str(pendente.get('id', '')) or pendente.get('correcao_preparada')):
        return tarefa  # conserva a correção já pendente, sem criar/remover tentativas
    registros = ([pendente.get('evidencia', {})]+pendente.get('tentativas', [])) if pendente else []
    reparar = (obrigatorias and tarefa.status == 'active' and pendente
               and not pendente.get('correcao_preparada')
               and pendente.get('ferramenta') == 'execute_command'
               and any(ev.get('processo_encerrado') and ev.get('status') == 'error' for ev in registros)
               and not any(ev.get('status') in {'uncertain', 'pending'} for ev in registros))
    if reparar:
        # Uma escrita bem-sucedida não prova que o programa corrigido funciona.
        # Abra outra leitura/correção após falha TERMINADA, conservando os IDs e
        # recibos antigos. Não libera retry de comando: o controlador mantém seu
        # bloqueio de efeitos/repetições e pode exigir retomada explícita.
        revisao = bd.novo_id('repair', 8)
        reparos = [{**op, 'id': str(op['id'])+'::'+revisao, 'planejada': True}
                   for op in obrigatorias if op['ferramenta'] == 'workspace']
        restantes = [op for op in etapa.get('operacoes_lista', [])
                     if op['id'] not in executadas and op['id'] != pendente['id']]
        pendente = {**pendente, 'planejada': True, 'correcao_preparada': True}
        plano = concluidas+reparos+[pendente]+restantes
        bd.executar('UPDATE conversation_task_steps SET ferramentas=? WHERE id=?',
                    (json.dumps(plano, ensure_ascii=False), etapa['id']))
        return carregar(chave)
    def contrato(op):
        return tuple(str(op.get(k) or '').strip() for k in ('ferramenta','operacao','modo','instrucao'))
    # IDs posicionais do planner (op-plan-1) não identificam uma nova ação
    # após replanejar. Preserve a definição/evidência das ações executadas,
    # sem reaplicá-las, e dê outro ID a contratos diferentes que colidam.
    plano = list(concluidas)
    usados = {str(op['id']) for op in plano}
    for op in normalizadas:
        if any(contrato(old) == contrato(op) or (obrigatorias and old.get('ferramenta')==op.get('ferramenta')
               and old.get('operacao')==op.get('operacao') and op.get('id','').startswith('op-contract-')) for old in concluidas):
            continue
        anterior = next((old for old in etapa.get('operacoes_lista', [])
                         if old['id'] not in executadas and contrato(old) == contrato(op)), None)
        if anterior:
            op = {**op, 'id': anterior['id'],
                  **({k: anterior[k] for k in ('evidencia', 'tentativas', 'correcao_preparada') if k in anterior})}
        if str(op['id']) in usados:
            op = {**op, 'id': bd.novo_id('op-replan', 8)}
        usados.add(str(op['id']))
        plano.append(op)
    normalizadas = plano
    executadas = [x for x in executadas if any(str(op['id']) == str(x) for op in concluidas)]
    bd.executar(
        "UPDATE conversation_task_steps SET ferramentas=?, ferramenta=?, ferramentas_executadas=? WHERE id=?",
        (
            json.dumps(normalizadas, ensure_ascii=False),
            normalizadas[0]["ferramenta"],
            json.dumps(executadas, ensure_ascii=False),
            etapa["id"],
        ),
    )
    return carregar(chave)


def concluir_etapa_sem_operacao(chave, observacao: str = "") -> TaskInfo | None:
    """Conclui um marco que o planejador verificou não exigir ferramenta."""
    _schema()
    tarefa = carregar(chave)
    if not tarefa:
        return None
    etapa = next((e for e in tarefa.etapas if e.get("status") == "pending"), None)
    if etapa is None:
        return tarefa
    bd.executar(
        "UPDATE conversation_task_steps SET status='done', resultado=? WHERE id=?",
        (str(observacao or "sem operação externa necessária")[:2000], etapa["id"]),
    )
    done_n = int((bd.um("SELECT COUNT(*) AS n FROM conversation_task_steps WHERE task_id=? AND status='done'", (tarefa.id,)) or {}).get("n", 0))
    pend_n = int((bd.um("SELECT COUNT(*) AS n FROM conversation_task_steps WHERE task_id=? AND status='pending'", (tarefa.id,)) or {}).get("n", 0))
    bd.executar(
        "UPDATE conversation_tasks SET status=?, updated_at=?, etapa_atual=?, ultima_acao=?, ultimo_resultado=? WHERE id=?",
        ("completed" if pend_n == 0 else "active", bd.agora(), done_n, "decisao_sem_ferramenta", str(observacao or "")[:2000], tarefa.id),
    )
    return carregar(chave)


def parece_tarefa(texto: str) -> bool:
    if intent.execucao_proibida(texto):
        return False
    partes = decompor(texto)
    if len(partes) > 1:
        return True

    t = re.sub(r"\s+", " ", str(texto or "").strip().lower())
    if eh_pergunta_reflexiva(t):
        return False
    t = re.sub(r'\b(?:nao|não|sem|nem)\s+(?:corrija|corrigir)\b', '', t)

    # A intenção pode ter confiança baixa em macroetapas escritas de forma
    # natural, mas verbos operacionais explícitos já demonstram que existe
    # trabalho a executar. Não exigimos chamada ao modelo para reconhecer isso.
    if _SINAIS_OPERACIONAIS.search(t):
        return True

    i = _intencao_da_etapa(texto)
    return bool(i and i.confianca >= 0.88 and i.acao != "conversar")

def _carregar_known_paths(tarefa_row) -> list[str]:
    bruto = tarefa_row.get("known_paths") or "[]"
    try:
        dados = json.loads(bruto)
    except (ValueError, TypeError):
        dados = []
    if not isinstance(dados, list):
        return []
    return [str(x) for x in dados if str(x).strip()][:50]


def _inferir_workspace_root(texto: str, known_paths: list[str] | None = None) -> str:
    """Descobre uma raiz explícita de trabalho e a fixa como caminho real.

    O modelo pode escrever "~/Área de Trabalho/...", "~/Desktop/..." ou
    variações com `_`. O núcleo resolve isso uma única vez e mantém a raiz
    canônica para todos os passos seguintes. Se nada explícito foi informado,
    não inventamos uma raiz.
    """
    known_paths = known_paths or []
    try:
        from tools import filesystem
    except Exception:
        filesystem = None

    # Primeiro, reaproveite caminhos já confirmados pela execução.
    for caminho in reversed(known_paths):
        try:
            p = Path(caminho).expanduser().resolve()
            if p.exists() and p.is_file():
                # Se já estivermos dentro de um diretório de teste conhecido,
                # use a raiz do projeto quando ela é reconhecível.
                partes = [x.casefold() for x in p.parts]
                for marcador in ("hoshino_teste", "hoshino_test", "teste_fogo"):
                    for idx, parte in enumerate(partes):
                        if marcador in parte:
                            return str(Path(*p.parts[:idx + 1]))
                return str(p.parent)
            return str(p if p.suffix == "" else p.parent)
        except Exception:
            continue

    bruto = str(texto or "").replace("\\", "/")
    if not bruto:
        return ""

    if re.search(r"\b(?:minha|minha própria)\s+workspace\b|\bworkspace\s+da\s+(?:hoshino|tarefa)\b", bruto, re.IGNORECASE):
        try:
            return str(Path(config.OFICINA_DIR).expanduser().resolve())
        except Exception:
            return str(config.OFICINA_DIR)

    # Variantes de Desktop/Área de Trabalho, com ou sem ~ ou /home/USER.
    padroes = [
        r"(?P<base>~|/home/[^\s/]+)/(?P<desk>Desktop|desktop|Área de Trabalho|Area de Trabalho|área de trabalho|area de trabalho|Área_de_Trabalho|Area_de_Trabalho|área_de_trabalho|area_de_trabalho)/(?P<rest>[^\n]+)",
        r"(?P<desk>Desktop|desktop|Área de Trabalho|Area de Trabalho|área de trabalho|area de trabalho|Área_de_Trabalho|Area_de_Trabalho|área_de_trabalho|area_de_trabalho)/(?P<rest>[^\n]+)",
    ]
    for padrao in padroes:
        m = re.search(padrao, bruto, re.IGNORECASE)
        if not m:
            continue
        desk = m.group("desk")
        rest = m.group("rest").strip().rstrip(".,;:)]}")
        # O último bloco pode ser um arquivo; só a pasta acima dele é a raiz.
        partes_rest = [x for x in rest.split("/") if x]
        if not partes_rest:
            continue
        # A raiz do workspace é o primeiro diretório após Desktop/Área de Trabalho.
        # O restante pertence ao arquivo/pasta interno da tarefa.
        candidato = f"~/{desk}/{partes_rest[0]}"
        try:
            alvo = filesystem.resolver_caminho(candidato) if filesystem else Path.home() / desk / partes_rest[0]
            return str(Path(alvo).resolve())
        except Exception:
            continue

    # Menos presuntivo: uma linha que declare explicitamente uma pasta do teste.
    m = re.search(r"(?:pasta|diret[óo]rio|workspace)[^\n]*?(?P<path>~[/\\][^\n]+|/home/[^\s/]+/[^\n]+)", bruto, re.IGNORECASE)
    if m and filesystem:
        try:
            alvo = filesystem.resolver_caminho(m.group("path").strip().rstrip(".,;:)]}"))
            return str(alvo)
        except Exception:
            pass
    return ""

def _salvar_known_path(tarefa: TaskInfo, caminho: str) -> None:
    caminho = str(caminho or "").strip()
    if not caminho:
        return
    atual = list(tarefa.known_paths or [])
    try:
        normal = str(Path(caminho).expanduser().resolve())
    except Exception:
        normal = caminho
    if normal not in atual:
        atual.append(normal)
    atual = atual[-50:]
    bd.executar("UPDATE conversation_tasks SET known_paths=?, workspace_root=?, updated_at=? WHERE id=?",
                (json.dumps(atual, ensure_ascii=False), tarefa.workspace_root or _inferir_workspace_root(tarefa.objetivo, atual), bd.agora(), tarefa.id))


def _ultimo_arquivo_conhecido(tarefa: TaskInfo) -> str:
    for caminho in reversed(tarefa.known_paths or []):
        try:
            p = Path(caminho)
            if p.suffix or p.is_file():
                return str(p)
        except Exception:
            pass
    return ""

def normalizar_argumentos_operacao(tarefa: TaskInfo, operacao: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Normaliza argumentos de workspace usando a raiz canônica da tarefa.

    Regra importante: uma tarefa possui UMA raiz. Caminhos absolutos fornecidos
    pelo modelo que escapam dessa raiz não podem criar uma segunda árvore de
    trabalho. O núcleo tenta recuperar um caminho equivalente conhecido; caso
    contrário, converte o alvo para relativo à raiz em vez de aceitar o caminho
    inventado.
    """
    resultado = dict(args or {})
    nome = str(operacao.get("ferramenta") or "").strip()
    if nome == 'ver_comando' and operacao.get('job_id'):
        resultado['job_id'] = operacao['job_id']
        return resultado
    if nome == 'entregar_arquivo':
        raw=str(resultado.get('caminho') or '')
        text=str(operacao.get('etapa') or operacao.get('instrucao') or '')
        quoted=[m.group(2) for m in re.finditer(r"([\"'`])([^\n]+?)\1",text)
                if re.search(r'\.(?:py|json|csv|txt|md|png|zip)$',m.group(2),re.I)]
        absolute=re.findall(r'(?<!\w)((?:/|~/)[^\s\"\'`]+\.(?:py|json|csv|txt|md|png|zip))\b',text,re.I)
        references=re.findall(r'(?<![\w/])([\w.-]+(?:/[\w.-]+)+\.(?:py|json|csv|txt|md|png|zip))\b',
                              text,re.I)
        from tools import filesystem
        candidates=[Path(p).expanduser().resolve() for p in (tarefa.known_paths or []) if Path(p).name==Path(raw).name]
        explicit=list(dict.fromkeys(quoted or absolute))
        if len(explicit)==1:
            resultado['caminho']=str(filesystem.resolver_caminho(explicit[0]))
        elif len(references)==1 and not re.search(r'[/~]',text.split(references[0])[0]):
            resultado['caminho']=str(filesystem.resolver_caminho(references[0]))
        elif len(set(candidates))==1:
            resultado['caminho']=str(candidates[0])
        else:
            resultado['caminho']=str(filesystem.resolver_caminho(raw))
        return resultado
    if nome != "workspace":
        return resultado
    subop = str(operacao.get("operacao") or resultado.get("operacao") or "ler").strip().casefold()
    modo_planejado = str(operacao.get("modo") or resultado.get("modo") or "").strip().casefold()
    aliases = {"abrir": "ler", "criar": "salvar", "acrescentar": "salvar", "editar": "salvar"}
    if subop == "criar" and not modo_planejado:
        modo_planejado = "substituir"
    elif subop == "acrescentar" and not modo_planejado:
        modo_planejado = "anexar"
    elif subop == "editar" and not modo_planejado:
        modo_planejado = "editar"
    subop = aliases.get(subop, subop)
    resultado["operacao"] = subop
    if subop == "salvar":
        resultado["modo"] = modo_planejado or "substituir"
    bruto = str(resultado.get("caminho") or "").strip()
    instrucao = str(operacao.get("instrucao") or operacao.get("etapa") or "").casefold()
    ultimo = _ultimo_arquivo_conhecido(tarefa)
    root = Path(tarefa.workspace_root).expanduser().resolve() if tarefa.workspace_root else None

    def dentro_da_raiz(candidato: Path) -> bool:
        if not root:
            return True
        return candidato == root or root in candidato.parents

    # A lista de caminhos conhecidos é evidência do sistema de arquivos, não
    # memória textual do modelo. Quando o modelo fornecer uma variante como
    # /home/user/Desktop/.../registro.txt, ~/Área de Trabalho/.../registro.txt
    # ou simplesmente registro.txt, o núcleo deve preferir o mesmo arquivo real
    # já confirmado pela tarefa. Isto elimina "sinônimos de caminho" como
    # estratégias artificialmente diferentes de uma mesma chamada.
    conhecidos_root = []
    if root:
        for conhecido in (tarefa.known_paths or []):
            try:
                p = Path(str(conhecido)).expanduser().resolve()
                if dentro_da_raiz(p):
                    conhecidos_root.append(p)
            except Exception:
                continue
    conhecidos_por_nome = {}
    for p in conhecidos_root:
        conhecidos_por_nome.setdefault(p.name.casefold(), []).append(p)

    try:
        from tools import filesystem
    except Exception:
        filesystem = None

    def relativo_seguro(valor: str) -> str:
        return str((root / valor.lstrip("/\\")).resolve()) if root else valor

    # Primeiro, se a referência textual aponta para um arquivo já confirmado,
    # use o caminho canônico conhecido antes de tentar interpretar aliases do SO.
    # Isso vale inclusive quando o modelo inventa outro /home/USUARIO/Desktop.
    nome_bruto = Path(bruto.replace("\\", "/")).name.casefold() if bruto else ""
    candidatos_nome = conhecidos_por_nome.get(nome_bruto, [])
    if root and candidatos_nome and subop in {"ler", "salvar"}:
        if len(candidatos_nome) == 1:
            resultado["caminho"] = str(candidatos_nome[0])
            bruto = resultado["caminho"]
    # Primeiro, caminhos relativos sempre pertencem ao workspace.
    elif bruto and root and not Path(bruto).expanduser().is_absolute():
        resultado["caminho"] = relativo_seguro(bruto)
        bruto = resultado["caminho"]
    elif bruto and filesystem:
        try:
            candidato = filesystem.resolver_caminho(bruto, base=str(root) if root else None)
            if dentro_da_raiz(candidato):
                resultado["caminho"] = str(candidato)
                bruto = str(candidato)
            elif root:
                # Recupera variações do mesmo workspace: /.../HOSHINO_TESTE_V2/x
                # -> root/x. Só fazemos isso quando o nome da raiz aparece no caminho.
                partes = list(candidato.parts)
                nome_root = root.name.casefold()
                indices = [i for i, parte in enumerate(partes) if parte.casefold() == nome_root]
                if indices:
                    idx = indices[-1]
                    resto = partes[idx + 1:]
                    resultado["caminho"] = str((root.joinpath(*resto)).resolve()) if resto else str(root)
                    bruto = resultado["caminho"]
                else:
                    # Caminho absoluto completamente estranho: descarte o prefixo e
                    # use apenas a referência de arquivo conhecida, quando houver.
                    nome = Path(bruto).name
                    conhecido = next((p for p in (tarefa.known_paths or [])
                                      if Path(p).name.casefold() == nome.casefold()), "")
                    if conhecido and dentro_da_raiz(Path(conhecido).resolve()):
                        resultado["caminho"] = str(Path(conhecido).resolve())
                    elif subop in {"pasta", "listar", "buscar"} and (not nome or nome_root in Path(bruto).parts):
                        resultado["caminho"] = str(root)
                    else:
                        # Não aceitar /home/gustavo/workspace/..., /workspace/... etc.
                        # como nova árvore. Preserve somente um nome simples dentro da raiz.
                        resultado["caminho"] = str((root / nome).resolve()) if nome else str(root)
        except Exception:
            if root and bruto:
                nome = Path(bruto).name
                resultado["caminho"] = str((root / nome).resolve()) if nome else str(root)

    # Para ler/salvar o arquivo de trabalho corrente, o caminho confirmado pela
    # execução tem prioridade quando a etapa não cita outro arquivo. Também
    # consideramos "editar" como leitura+escrita do mesmo alvo.
    if ultimo and subop in {"ler", "salvar"}:
        menciona_arquivo = bool(re.search(
            r"(?:~|/home/|/tmp/|[a-z]:[\\/]|\b[\w.-]+[/.]\w+)",
            instrucao.replace(" ", " "), re.IGNORECASE
        )) or bool(re.search(r"\b[\w.-]+\.(?:txt|md|py|html|json|csv|yaml|yml|log)\b", instrucao, re.IGNORECASE))
        explicito_mesmo = any(chave in instrucao for chave in (
            "arquivo anterior", "mesmo arquivo", "esse arquivo", "o arquivo anterior", "arquivo recém-criado", "arquivo recem-criado"
        ))
        try:
            if not bruto or explicito_mesmo or not menciona_arquivo:
                resultado["caminho"] = ultimo
        except Exception:
            resultado["caminho"] = ultimo

    if root and not resultado.get("caminho") and subop in {"listar", "buscar", "pasta"}:
        resultado["caminho"] = str(root)

    # Nunca devolva ao LLM um caminho absoluto fora da raiz quando a tarefa já
    # tem um workspace. Se houver uma única referência conhecida compatível, ela
    # é a última autoridade local para a operação de arquivo.
    if root and subop in {"ler", "salvar"} and conhecidos_root:
        try:
            candidato_final = Path(str(resultado.get("caminho") or "")).expanduser().resolve()
        except Exception:
            candidato_final = None
        if candidato_final is not None and not dentro_da_raiz(candidato_final):
            por_nome = conhecidos_por_nome.get(candidato_final.name.casefold(), [])
            if len(por_nome) == 1:
                resultado["caminho"] = str(por_nome[0])

    return resultado

def _novo_objetivo(texto: str, partes: list[str]) -> str:
    return texto.strip() if texto.strip() else (partes[0] if partes else "")

def _inferir_workspace_operacao(texto: str) -> str:
    """Infere a ação básica do editor de arquivos sem deixar o LLM escolher o tipo físico.

    A ordem é deliberada: operações de diretório/listagem têm prioridade quando o
    texto fala explicitamente de pasta; edição/anexação de arquivo preserva seu modo.
    """
    n = intent.normalizar(str(texto or ""))
    n = re.sub(r'\b(?:nao|sem|nem)\s+(?:corrija|corrigir)\b', '', n)
    fala_diretorio = bool(re.search(r"\b(?:pasta|pastas|diretorio|diretorios|conteudo da pasta)\b", n))
    fala_arquivo = bool(re.search(r"\b(?:arquivo|arquivos|documento|txt|html|python)\b|\.(?:py|txt|md|html|json|csv)\b", n))

    # O verbo vem antes da finalidade: salvar na pasta para verificar depois
    # não significa listar a pasta nem ler o arquivo.
    inicio = re.sub(r'^(?:agora|depois|por favor)[, ]+', '', n)
    if re.match(r'^(?:liste|listar|lista)\b', inicio):
        return 'listar'
    if re.match(r'^(?:abra|abre|abrir|leia|ler)\s+(?:(?:a|o|as|os|uma|um)\s+)?(?:pasta|pastas|diretorio|diretorios)\b', inicio):
        # "Abra a pasta e liste ... contém um arquivo Python" continua sendo
        # uma consulta de diretório; a palavra arquivo na finalidade não muda
        # o tipo do alvo nem autoriza ler o diretório como fonte.
        return 'listar'
    if fala_arquivo and re.match(r'^(?:salve|salva|salvar|escreva|escrever|crie|criar)\b', inicio):
        return 'salvar'
    if fala_arquivo and re.match(r'^(?:leia|ler|leitura|abra|abre|abrir)\b', inicio):
        return 'ler'
    if fala_diretorio and re.search(r"\b(?:liste|listar|lista|mostre|mostrar|conteudo|conteúdo|verifique|verificar|veja|examinar|examine)\b", n):
        return "listar"
    if re.search(r"\b(?:busque|buscar|procure|procurar|pesquise neste diretorio|pesquisar neste diretorio)\b", n):
        return "buscar"
    if fala_diretorio and not fala_arquivo and re.search(
        r"\b(?:crie|criar|fa[cç]a|fazer|mkdir|prepare|preparar)\b", n
    ):
        return "pasta"
    if re.search(r"\b(?:edite|editar|altere|alterar|modifique|modificar|corrija|corrigir)\b", n):
        return "salvar"
    if re.search(r"\b(?:acrescente|acrescentar|adicione|adicionar|anexe|anexar)\b", n):
        return "salvar"
    if re.search(r"\b(?:leia|ler|leitura|abra|abrir|veja|verifique|verificar|confirme|confirmar|inspecione|examinar|examine)\b", n):
        return "ler"
    if fala_diretorio and not fala_arquivo:
        return "pasta"
    return "salvar"


def _inferir_workspace_modo(texto: str) -> str:
    """Retorna o modo de salvar quando a operação é um trabalho de arquivo."""
    n = intent.normalizar(str(texto or ""))
    if re.search(r"\b(?:edite|editar|altere|alterar|modifique|modificar|substitua|substituir|troque|trocar)\b", n):
        return "editar"
    if re.search(r"\b(?:acrescente|acrescentar|adicione|adicionar|anexe|anexar|append)\b", n):
        return "anexar"
    return "substituir"


def pede_abertura_url(texto: str) -> bool:
    """Comando direto, não menção/negação/citação, de abrir uma URL explícita.

    Compartilhado com o contrato obrigatório do planner: pedir verificação
    depois de abrir uma página não transforma a ação em síntese textual.
    """
    n = intent.normalizar(str(texto or ""))
    return bool(re.search(
        r'(?:^|[.!?:;\n]\s+)(?:por favor,?\s+)?(?:abra|acesse)\s+'
        r'(?:(?:o site|a pagina|a url|o link)\s+)?https?://[^\s]+', n))


def _detectar_operacoes(texto: str) -> list[dict[str, Any]]:
    """Detecta somente a capacidade pública principal do marco.

    A sequência fina fica com o planejador. Para arquivos/pastas existe uma única
    capacidade pública (`workspace`) e a suboperação fica registrada na operação.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        return []
    sequencia=sequencia_correcao(bruto)
    if sequencia:
        return sequencia
    n = intent.normalizar(bruto)
    n = re.sub(r'\b(?:nao|sem|nem)\s+(?:corrija|corrigir)\b', '', n)
    tool = ""
    operacao = ""
    if re.search(r"\b(?:arquivo|arquivos|documento|txt|html|python|pasta|pastas|diretorio|diretorios)\b|\.(?:py|txt|md|html|json|csv)\b", n):
        # Só escolha workspace quando o marco realmente fala de filesystem.
        if re.search(r"\b(?:crie|criar|escreva|escrever|edite|editar|altere|alterar|modifique|modificar|corrija|corrigir|"
                     r"salve|salvar|adicione|adicionar|acrescente|acrescentar|leia|ler|"
                     r"verifique|verificar|liste|listar|busque|buscar|procure|procurar|pasta|pastas|diretorio|diretorios)\b", n):
            tool = "workspace"
            operacao = _inferir_workspace_operacao(bruto)
    if not tool and re.search(r'\b(?:gere|gerar|crie|criar)\b',n) and re.search(r'\bimagem\b',n):
        tool = 'gerar_imagem'
    if not tool and pede_abertura_url(bruto):
        tool = "browser_abrir"
    elif not tool and re.search(r"\b(?:pesquise|pesquisa|procure|buscar|busque|na internet|fontes diferentes|fontes confiaveis|fontes confiáveis)\b", n):
        tool = "web_search"
    elif not tool and re.search(r"\b(?:download|baixe|baixar|faca download|faça download)\b", n):
        tool = "baixar_arquivo"
    elif not tool and re.search(r"\b(?:abra|abrir|aberto|abre)\b", n) and re.search(
        r"\b(?:aplicativo|aplicativos|programa|programas|editor|calculadora|gerenciador|navegador|browser)\b", n
    ):
        tool = "abrir_aplicativo"
    elif not tool and re.search(r"\b(?:execute|executar|rodar|rode|run)\b", n) and re.search(
        r"\b(?:script|programa|ferramenta|comando|novamente|contra|execute-o|executeo)\b", n
    ):
        tool = "execute_command"
    elif not tool and re.search(r"\b(?:recarregue|recarregar|reload)\b", n):
        tool = "browser_recarregar"
    elif not tool and re.search(r"\b(?:volte|voltar|retroceda)\b", n):
        tool = "browser_voltar"
    elif not tool and re.search(r"\b(?:avance|avancar|avançar)\b", n):
        tool = "browser_avancar"
    elif not tool and re.search(r"\b(?:clique|clicar|clicando)\b", n):
        tool = "browser_clicar"
    elif not tool and re.search(r"\b(?:aba|abas|navegador|browser)\b", n) and re.search(
        r"\b(?:abra|abrir|use|escolha|retorne|identifique|descubra|navegue)\b", n
    ):
        tool = "browser_abas"
    elif not tool and re.search(r"\b(?:abra|abrir)\b", n) and re.search(r"\b(?:url|http|https|site|pagina|página)\b", n):
        tool = "browser_abrir"
    if not tool:
        i = _intencao_da_etapa(bruto)
        tool = str(getattr(i, "ferramenta_principal", "") or "") if i else ""
        if tool in {"make_directory", "read_file", "write_file"}:
            tool = "workspace"
            operacao = _inferir_workspace_operacao(bruto)
    if not tool:
        return []
    item = {"id": "op-1", "ferramenta": tool, "instrucao": bruto[:2200], "planejada": False}
    if tool == "workspace":
        item["operacao"] = operacao or "salvar"
        if item["operacao"] == "salvar":
            item["modo"] = _inferir_workspace_modo(bruto)
    return [item]


def sequencia_correcao(texto: str) -> list[dict]:
    """Barreiras do editor existente: ler -> corrigir -> executar se solicitado."""
    n=intent.normalizar(texto)
    if not re.search(r'\.(?:py|json|js|ts|txt|md)\b|\b(?:arquivo|programa|script)\b',n):
        return []
    correction=re.search(r'\b(?:corrija|corrigir|edite|editar)\b',n)
    if not correction or re.search(r'\b(?:nao|sem|nem)\s+$',n[:correction.start()]):
        return []
    result=[dict(id='op-contract-read',ferramenta='workspace',operacao='ler',instrucao=texto,planejada=False),
            dict(id='op-contract-write',ferramenta='workspace',operacao='salvar',
                 modo='editar' if correction.group() in {'edite','editar'} else 'substituir',instrucao=texto,planejada=False)]
    if re.search(r'\b(?:execute|executar|rode|rodar)\b',n) and not re.search(r'\b(?:nao|sem|nem)\s+(?:execute|executar|rode|rodar)\b',n):
        result.append(dict(id='op-contract-run',ferramenta='execute_command',instrucao=texto,planejada=False))
    return result

def _detectar_ferramentas(texto: str) -> list[str]:
    """Compatibilidade: devolve a capacidade inicial detectada."""
    return [str(op["ferramenta"]) for op in _detectar_operacoes(texto) if op.get("ferramenta")]

def _normalizar_operacoes(valores: list, texto_etapa: str) -> list[dict[str, Any]]:
    """Converte o formato legado (lista de nomes) para operações atômicas."""
    if not isinstance(valores, list):
        return []
    saida: list[dict[str, Any]] = []
    for idx, valor in enumerate(valores, 1):
        if isinstance(valor, dict):
            nome = str(valor.get("ferramenta") or valor.get("tool") or "").strip()
            if not nome:
                continue
            if nome in _LEGADOS_WORKSPACE:
                operacao = _LEGADOS_WORKSPACE[nome]
                nome = "workspace"
                valor = {**valor, "operacao": operacao}
                if operacao == "salvar" and not valor.get("modo"):
                    valor["modo"] = _inferir_workspace_modo(str(valor.get("instrucao") or texto_etapa))
            saida.append({
                "id": str(valor.get("id") or f"op-{idx}"),
                "ferramenta": nome,
                "instrucao": str(valor.get("instrucao") or texto_etapa or "")[:2200],
                "planejada": bool(valor.get("planejada", False)),
                **({'job_id': valor['job_id']} if nome == 'ver_comando'
                   and re.fullmatch(r'job-[a-f0-9]{8}', str(valor.get('job_id') or '')) else {}),
                **({"operacao": str(valor.get("operacao") or "").strip()} if valor.get("operacao") else {}),
                **({"modo": str(valor.get("modo") or "").strip().casefold()} if valor.get("modo") else {}),
                **({"evidencia": valor["evidencia"]} if isinstance(valor.get('evidencia'),dict) else {}),
                **({"tentativas": valor["tentativas"]} if isinstance(valor.get('tentativas'),list) else {}),
                **({"correcao_preparada": bool(valor["correcao_preparada"])} if 'correcao_preparada' in valor else {}),
            })
        elif str(valor).strip():
            nome = str(valor).strip()
            operacao_legada = _LEGADOS_WORKSPACE.get(nome)
            if operacao_legada:
                nome = "workspace"
            item = {
                "id": f"legacy-{idx}",
                "ferramenta": nome,
                "instrucao": str(texto_etapa or "")[:2200],
                "planejada": False,
            }
            if nome == "workspace":
                item["operacao"] = operacao_legada or _inferir_workspace_operacao(texto_etapa)
                if item["operacao"] == "salvar":
                    item["modo"] = _inferir_workspace_modo(texto_etapa)
            saida.append(item)
    return saida

def _adicionar_etapas(task_id: str, partes: list[str]) -> None:
    _schema()
    row = bd.um("SELECT COALESCE(MAX(ordem), -1) AS max_ordem FROM conversation_task_steps WHERE task_id = ?",
                (task_id,))
    ordem = int((row or {}).get("max_ordem", -1)) + 1
    for parte in partes:
        operacoes = _detectar_operacoes(parte)
        if not operacoes:
            ferramentas = _detectar_ferramentas(parte)
            operacoes = [
                {"id": f"op-{i+1}", "ferramenta": f, "instrucao": parte[:2200], "planejada": False}
                for i, f in enumerate(ferramentas)
            ]
        ferramenta = str(operacoes[0].get("ferramenta") or "") if operacoes else ""
        ferramentas_json = json.dumps(operacoes, ensure_ascii=False)
        bd.executar(
            "INSERT INTO conversation_task_steps "
            "(id, task_id, ordem, texto, ferramenta, ferramentas, status, resultado) VALUES (?,?,?,?,?,?,'pending','')",
            (bd.novo_id("cts", 8), task_id, ordem, parte, ferramenta, ferramentas_json)
        )
        ordem += 1

def _carregar_row(task_row, step_rows) -> TaskInfo:
    etapas = [dict(r) for r in step_rows]
    for etapa in etapas:
        bruto = etapa.get("ferramentas") or ""
        try:
            valores = json.loads(bruto) if bruto else []
        except (ValueError, TypeError):
            valores = []
        if not isinstance(valores, list):
            valores = []
        if not valores and etapa.get("ferramenta"):
            valores = [etapa["ferramenta"]]
        operacoes = _normalizar_operacoes(valores, str(etapa.get("texto") or ""))
        if etapa.get("ferramenta") in _LEGADOS_WORKSPACE:
            etapa["ferramenta"] = "workspace"  # adaptação em leitura, sem regravar dados antigos
        etapa["operacoes_lista"] = operacoes
        etapa["ferramentas_lista"] = [str(op["ferramenta"]) for op in operacoes if op.get("ferramenta")]
        bruto_exec = etapa.get("ferramentas_executadas") or ""
        try:
            executadas_brutas = json.loads(bruto_exec) if bruto_exec else []
        except (ValueError, TypeError):
            executadas_brutas = []
        executadas_brutas = executadas_brutas if isinstance(executadas_brutas, list) else []
        ids_validos = {str(op["id"]): str(op["id"]) for op in operacoes}
        ids = [str(v) for v in executadas_brutas if str(v) in ids_validos]
        # Compatibilidade com tarefas antigas que guardavam o nome da ferramenta.
        ocupados = set(ids)
        for bruto_exec_item in executadas_brutas:
            nome = str(bruto_exec_item).strip()
            if not nome or nome in ids_validos:
                continue
            operacao_legada = _LEGADOS_WORKSPACE.get(nome)
            if operacao_legada:
                nome = "workspace"
            candidato = next((op for op in operacoes
                              if op["ferramenta"] == nome and op["id"] not in ocupados
                              and (not operacao_legada or op.get("operacao") == operacao_legada)), None)
            if candidato:
                ids.append(str(candidato["id"]))
                ocupados.add(str(candidato["id"]))
        etapa["ferramentas_executadas_lista"] = ids
    return TaskInfo(
        id=task_row["id"],
        chave=task_row["chave"],
        objetivo=task_row["objetivo"],
        status=task_row["status"],
        etapa_atual=int(task_row.get("etapa_atual") or 0),
        etapas=etapas,
        ultima_acao=task_row.get("ultima_acao") or "",
        ultimo_resultado=task_row.get("ultimo_resultado") or "",
        workspace_root=str(task_row.get("workspace_root") or ""),
        known_paths=_carregar_known_paths(task_row),
    )

def carregar(chave, incluir_concluidas=True) -> TaskInfo | None:
    _schema()
    k = chave_texto(chave)
    row = bd.um(
        "SELECT * FROM conversation_tasks WHERE chave = ? AND status IN ('active','paused') "
        "ORDER BY updated_at DESC, rowid DESC LIMIT 1", (k,))
    if not row:
        return None
    filtro = "" if incluir_concluidas else " AND status = 'pending'"
    steps = bd.consultar(
        "SELECT * FROM conversation_task_steps WHERE task_id = ?" + filtro + " ORDER BY ordem, id",
        (row["id"],),
    )
    return _carregar_row(row, steps)

def carregar_ultimo(chave) -> TaskInfo | None:
    _schema()
    k = chave_texto(chave)
    row = bd.um(
        "SELECT * FROM conversation_tasks WHERE chave = ? AND status = 'paused' "
        "ORDER BY updated_at DESC, rowid DESC LIMIT 1", (k,))
    if not row:
        return None
    steps = bd.consultar(
        "SELECT * FROM conversation_task_steps WHERE task_id = ? ORDER BY ordem, id",
        (row["id"],),
    )
    return _carregar_row(row, steps)

def carregar_por_id(task_id: str) -> TaskInfo | None:
    """Observa o desfecho exato, inclusive completed; nunca reativa uma tarefa.

    carregar_ultimo continua reservado à retomada de paused. Misturar essas
    consultas fazia a apresentação usar o snapshot anterior à conclusão.
    """
    _schema()
    row = bd.um('SELECT * FROM conversation_tasks WHERE id=?', (str(task_id),))
    if not row:
        return None
    steps = bd.consultar('SELECT * FROM conversation_task_steps WHERE task_id=? ORDER BY ordem, id', (row['id'],))
    return _carregar_row(row, steps)

def pendencias(chave) -> list[dict]:
    _schema()
    tarefa = carregar(chave)
    return [e for e in (tarefa.etapas if tarefa else []) if e["status"] == "pending"]

def _reativar_recente(chave, texto: str):
    # Só uma tarefa pausada pode ser reativada. A frase de retomada é controle
    # do fio e nunca deve virar uma etapa operacional.
    ultimo = carregar_ultimo(chave)
    if not ultimo or ultimo.status != "paused":
        return None
    bd.executar(
        "UPDATE conversation_tasks SET status='active', updated_at=? WHERE id=?",
        (bd.agora(), ultimo.id)
    )
    return carregar(chave)

def _compativel_com_pendente(tarefa: TaskInfo, texto: str) -> bool:
    pend = next((e for e in tarefa.etapas if e["status"] == "pending"), None)
    if not pend:
        return False
    executadas = set(pend.get("ferramentas_executadas_lista") or [])
    atual = next((op for op in (pend.get("operacoes_lista") or [])
                  if str(op.get("id")) not in executadas), None)
    propostas = _detectar_operacoes(texto)
    if not atual or not propostas:
        return False
    proposta = propostas[0]
    if proposta.get("ferramenta") != atual.get("ferramenta"):
        return False
    if atual.get("ferramenta") == "workspace":
        # Nome público igual não basta: ler, substituir e anexar são ações
        # diferentes. A comparação antiga ainda esperava write_file/read_file.
        return (proposta.get("operacao") == atual.get("operacao")
                and proposta.get("modo", "") == atual.get("modo", ""))
    return True

def iniciar_ou_continuar(chave, texto: str) -> TaskInfo | None:
    _schema()
    texto = str(texto or "").strip()
    if not texto:
        return carregar(chave)

    if intent.execucao_proibida(texto):
        pausar(chave)  # Não vincular nem retomar tarefa anterior neste turno.
        return None

    if _CANCELAMENTO.search(texto):
        tarefa = carregar(chave)
        if tarefa:
            cancelar(chave)
        return None

    if eh_pergunta_reflexiva(texto):
        # 30/10 (revisão Codex): pergunta sobre o passado ou a opinião é conversa: não cria, não continua, não
        # reativa tarefa pausada nem acrescenta etapa ("Agora, como foi fabricar o arco?" virava etapa de fabricar).
        return None

    tarefa = carregar(chave)
    if eh_comando_retomada(texto):
        # "continue a tarefa anterior" é controle do fio, nunca uma etapa nova.
        # O erro antigo criava uma etapa genérica sem ferramenta e deixava o
        # roteador vendo apenas a palavra "continue", portanto o modelo não
        # recebia a capacidade necessária para realmente prosseguir.
        if tarefa:
            bd.executar("UPDATE conversation_tasks SET status='active', updated_at=? WHERE id=?",
                        (bd.agora(), tarefa.id))
            return carregar(chave)
        return _reativar_recente(chave, texto)

    if tarefa:
        # 29/10: projeto parado em pedir_decisao_humana — a mensagem seguinte é a resposta, não
        # tarefa nova (antes só "continue" retomava e o texto da resposta se perdia).
        from core import project_agent
        # Continuação com texto num projeto ("continue, deixei material…") também só reativa:
        # decompor criaria etapas e mudaria o objetivo, quebrando o checkpoint (goal_hash).
        if project_agent.aguardando_humano(tarefa) or (project_agent.is_project(tarefa.objetivo)
                                                       and eh_continuacao(texto)):
            bd.executar("UPDATE conversation_tasks SET status='active', updated_at=? WHERE id=?",
                        (bd.agora(), tarefa.id))
            return carregar(chave)
        # Uma continuação explícita entra na mesma tarefa. Uma nova tarefa
        # independente pausa a anterior em vez de destruí-la.
        if eh_continuacao(texto) or _compativel_com_pendente(tarefa, texto):
            # Se a pessoa apenas repete/precisa a ação que já está pendente,
            # atualizamos a descrição daquela etapa. Não duplicamos a etapa.
            if _compativel_com_pendente(tarefa, texto) and not eh_continuacao(texto):
                pend = next((e for e in tarefa.etapas if e["status"] == "pending"), None)
                if pend and texto.strip() and texto.strip().lower() != str(pend.get("texto") or "").strip().lower():
                    bd.executar("UPDATE conversation_task_steps SET texto=? WHERE id=?",
                                (texto[:1200], pend["id"]))
                bd.executar("UPDATE conversation_tasks SET status='active', updated_at=? WHERE id=?",
                            (bd.agora(), tarefa.id))
                return carregar(chave)
            partes = decompor(texto)
            intencoes = [_intencao_da_etapa(x) for x in partes]
            eh_marcador_sem_acao = (
                len(partes) == 1 and (not intencoes[0] or not intencoes[0].ferramenta_principal)
                and not parece_tarefa(texto)
            )
            if partes and not eh_marcador_sem_acao:
                _adicionar_etapas(tarefa.id, partes)
                objetivo = f"{tarefa.objetivo} → {texto}"
                # O armazenamento não é o orçamento do prompt. Cortar aqui
                # descartava requisitos originais em continuações longas.
                bd.executar(
                    "UPDATE conversation_tasks SET updated_at=?, objetivo=? WHERE id=?",
                    (bd.agora(), objetivo, tarefa.id)
                )
            return carregar(chave)
        # Uma ação claramente diferente não é engolida pela tarefa atual.
        if not parece_tarefa(texto):
            # Conversa lateral não é comando de pausa nem requisito da tarefa.
            # Este turno recebe None, mas o objetivo/etapas persistidos ficam
            # intactos. Cancelamento e nova tarefa explícita seguem separados.
            return None
        pausar(chave)
        # Continua abaixo e cria uma nova tarefa.
        tarefa = None

    if eh_continuacao(texto):
        reaberta = _reativar_recente(chave, texto)
        if reaberta:
            # A retomada pura já foi tratada acima. Aqui há uma instrução nova:
            # passe pelo mesmo caminho de continuação da tarefa ativa para
            # persistir a nova etapa, não devolver só o resultado antigo.
            return iniciar_ou_continuar(chave, texto)

    if not parece_tarefa(texto):
        return None

    partes = decompor(texto)
    if not partes:
        return None
    tid = bd.novo_id("ct", 10)
    agora = bd.agora()
    objetivo = _novo_objetivo(texto, partes)
    workspace_root = _inferir_workspace_root(objetivo)
    bd.executar(
        "INSERT INTO conversation_tasks "
        "(id,chave,objetivo,status,created_at,updated_at,etapa_atual,ultima_acao,ultimo_resultado,workspace_root,known_paths) "
        "VALUES (?,?,?,'active',?,?,?,?,?,?,?)",
        (tid, chave_texto(chave), objetivo, agora, agora, 0, "", "", workspace_root, "[]")
    )
    _adicionar_etapas(tid, partes)
    return carregar(chave)

@bd.atomico(None)
def registrar_ferramenta(chave, nome: str, status: str, resultado: str = "", operacao_id: str = "",
                        *, recibo: dict | None = None) -> TaskInfo | None:
    _schema()
    tarefa = carregar(chave)
    if not tarefa:
        return None
    alvo = next((e for e in tarefa.etapas if e.get("status") == "pending"), None)
    if alvo is None:
        return tarefa

    operacoes = list(alvo.get("operacoes_lista") or [])
    executadas = list(alvo.get("ferramentas_executadas_lista") or [])
    executadas_set = set(executadas)
    if operacao_id:
        alvo_op = next((op for op in operacoes if str(op.get("id")) == str(operacao_id)
                        and str(op.get('ferramenta')) == nome), None)
    else:
        alvo_op = next((op for op in operacoes
                        if str(op.get("ferramenta")) == str(nome) and str(op.get("id")) not in executadas_set), None)
    if alvo_op is None:
        return tarefa
    op_id = str(alvo_op.get("id") or "")
    texto_resultado = str(resultado or "")[:2000]
    # Falhas também são evidência durável. Antes eram substituídas apenas pelo
    # último texto da tarefa, perdendo o diagnóstico ao bloquear/replanejar.
    recibo_exato = (isinstance(recibo, dict) and recibo.get('tool') == nome
                   and recibo.get('status') == status and recibo.get('output') == resultado)
    if nome == 'ver_comando' and alvo_op.get('job_id'):
        observed = re.match(r'\AJob (job-[a-f0-9]{8}) \[', str(resultado))
        if not recibo_exato or not observed or observed.group(1) != alvo_op['job_id']:
            return tarefa  # Resultado de outro job nunca conclui esta operação.
    saida_terminada = re.match(r'\A\[[^\n]+\| saída (\d+)\]\n', str(resultado or ''))
    evidencia = dict(status=status, output=str(resultado or '')[:12000],
                     excerto=len(str(resultado or '')) > 12000,
                     verified=bool(recibo_exato and recibo.get('verified')),
                     processo_encerrado=bool(nome == 'execute_command' and status == 'error'
                         and recibo_exato and saida_terminada and int(saida_terminada.group(1)) != 0))
    if nome == 'diario':
        from core import diagnostics
        texto_resultado=diagnostics._redact({'tool':nome,'output':texto_resultado},truncate=False)['output']
        evidencia=diagnostics._redact(dict(evidencia,tool=nome),truncate=False)
    anterior = alvo_op.get('evidencia')
    if anterior and anterior != evidencia:
        alvo_op['tentativas'] = (alvo_op.get('tentativas', [])+[anterior])[-8:]
    alvo_op['evidencia'] = evidencia
    if evidencia['processo_encerrado']:
        alvo_op['correcao_preparada'] = False  # nova falha real, não o bloqueio de uma repetição
    bd.executar('UPDATE conversation_task_steps SET ferramentas=? WHERE id=?',
                (json.dumps(operacoes, ensure_ascii=False), alvo['id']), strict=True)
    if status == 'uncertain':
        bd.executar("UPDATE conversation_tasks SET status='paused', updated_at=?, ultima_acao=?, ultimo_resultado=? WHERE id=?",
                    (bd.agora(), nome, texto_resultado, tarefa.id), strict=True)
        return carregar(chave)
    if nome == "estado_imagem":
        estado_n = texto_resultado.casefold()
        if "status=done" not in estado_n:
            bd.executar(
                "UPDATE conversation_tasks SET updated_at=?, ultima_acao=?, ultimo_resultado=? WHERE id=?",
                (bd.agora(), nome, texto_resultado, tarefa.id)
            )
            if "status=error" in estado_n or "erro=" in estado_n or "status=failed" in estado_n:
                return carregar(chave)
            return carregar(chave)
    aceite_imagem = (nome=='gerar_imagem' and status=='pending' and isinstance(recibo,dict)
                     and recibo.get('tool')==nome and recibo.get('status')==status
                     and recibo.get('outcome_pending') is True and recibo.get('output')==resultado
                     and bool(re.match(r'\AIMAGEM_ENFILEIRADA=SIM\nJOB_ID=img-[a-f0-9]+\n',str(resultado))))
    # O envio aceito já foi executado. Só a consulta do job fica pendente;
    # retomar a tarefa nunca deve iniciar outra geração para o mesmo pedido.
    sucesso = str(status).lower() in {"success", "sucesso", "queued"} or aceite_imagem
    if not sucesso:
        bd.executar(
            "UPDATE conversation_tasks SET updated_at=?, ultima_acao=?, ultimo_resultado=? WHERE id=?",
            (bd.agora(), nome, texto_resultado, tarefa.id)
        )
        return carregar(chave)

    if op_id and op_id not in executadas_set:
        executadas.append(op_id)
        executadas_set.add(op_id)
    if nome == "workspace":
        for achado in re.findall(r"(?:PATH|FILE|PASTA)=([^\n]+)", texto_resultado):
            _salvar_known_path(tarefa, achado.strip())
        tarefa = carregar(chave) or tarefa

    # Auto-verificação: ações com verificador ganham uma operação seguinte,
    # mas nunca duplicam uma verificação que o próprio roteiro já declarou.
    try:
        from core import capabilities
        meta = capabilities.info(nome)
    except Exception:
        meta = None
    recibo_compativel = (isinstance(recibo, dict) and recibo.get("tool") == nome
                        and recibo.get("status") == status
                        and recibo.get("output") == resultado
                        and isinstance(recibo.get("requires_verification"), bool))
    exige_verificacao = (recibo["requires_verification"] if recibo_compativel
                        else bool(meta and meta.verifier))
    if meta and meta.verifier and exige_verificacao:
        job_id = recibo.get('background_job') if recibo_compativel else None
        if not re.fullmatch(r'job-[a-f0-9]{8}', str(job_id or '')):
            job_id = None
        ja_tem_verificador = not job_id and any(
            str(op.get("ferramenta")) == str(meta.verifier)
            for etapa_futura in tarefa.etapas
            if etapa_futura.get("status") == "pending"
            for op in (etapa_futura.get("operacoes_lista") or [])
        )
        if not ja_tem_verificador:
            novo_id = f"{op_id}::verify::{meta.verifier}"
            if not any(str(op.get("id")) == novo_id for op in operacoes):
                verificacao = {
                    "id": novo_id,
                    "ferramenta": str(meta.verifier),
                    "instrucao": f"Verifique objetivamente o resultado da operação '{nome}'.",
                    "planejada": True,
                    **({'job_id': job_id} if job_id else {}),
                }
                if job_id:
                    operacoes.insert(operacoes.index(alvo_op) + 1, verificacao)
                else:
                    operacoes.append(verificacao)
                bd.executar(
                    "UPDATE conversation_task_steps SET ferramentas=? WHERE id=?",
                    (json.dumps(operacoes, ensure_ascii=False), alvo["id"]),
                )

    final_da_etapa = all(str(op.get("id")) in executadas_set for op in operacoes if op.get("id"))
    resultado_final = texto_resultado
    if alvo.get("resultado") and texto_resultado and texto_resultado not in str(alvo.get("resultado")):
        resultado_final = (str(alvo.get("resultado")) + "\n" + texto_resultado)[-2000:]

    bd.executar(
        "UPDATE conversation_task_steps SET ferramentas_executadas=?, resultado=? WHERE id=?",
        (json.dumps(executadas, ensure_ascii=False), resultado_final, alvo["id"])
    )
    done_n = int((bd.um("SELECT COUNT(*) AS n FROM conversation_task_steps WHERE task_id=? AND status='done'", (tarefa.id,)) or {}).get("n", 0))
    if final_da_etapa:
        bd.executar("UPDATE conversation_task_steps SET status='done' WHERE id=?", (alvo["id"],))
        done_n += 1
    pend_n = int((bd.um("SELECT COUNT(*) AS n FROM conversation_task_steps WHERE task_id=? AND status='pending'", (tarefa.id,)) or {}).get("n", 0))
    status_tarefa = "completed" if pend_n == 0 else "active"
    bd.executar(
        "UPDATE conversation_tasks SET status=?, updated_at=?, etapa_atual=?, ultima_acao=?, ultimo_resultado=? WHERE id=?",
        (status_tarefa, bd.agora(), done_n, nome, texto_resultado, tarefa.id)
    )
    tarefa_row = bd.um("SELECT * FROM conversation_tasks WHERE id=?", (tarefa.id,))
    if not tarefa_row:
        return None
    steps = bd.consultar("SELECT * FROM conversation_task_steps WHERE task_id=? ORDER BY ordem, id", (tarefa.id,))
    return _carregar_row(tarefa_row, steps)

def status_id(task_id: str) -> str:
    """Retorna o status persistido de uma tarefa sem limitar a active/paused."""
    _schema()
    row = bd.um("SELECT status FROM conversation_tasks WHERE id=?", (str(task_id),))
    return str((row or {}).get("status") or "")


def limpar_chave(chave) -> int:
    """Remove a tarefa e todas as etapas do fio atual."""
    _schema()
    k = chave_texto(chave)
    rows = bd.consultar("SELECT id FROM conversation_tasks WHERE chave=?", (k,))
    ids = [r["id"] for r in rows]
    for tid in ids:
        bd.executar("DELETE FROM conversation_task_steps WHERE task_id=?", (tid,))
        bd.executar("DELETE FROM conversation_tasks WHERE id=?", (tid,))
    return len(ids)

def limpar_tudo() -> tuple[int, int]:
    """Remove todo o estado persistente de tarefas."""
    _schema()
    n_steps = int((bd.um("SELECT COUNT(*) AS n FROM conversation_task_steps") or {}).get("n", 0))
    n_tasks = int((bd.um("SELECT COUNT(*) AS n FROM conversation_tasks") or {}).get("n", 0))
    bd.executar("DELETE FROM conversation_task_steps")
    bd.executar("DELETE FROM conversation_tasks")
    return n_tasks, n_steps

def concluir(chave) -> None:
    _schema()
    tarefa = carregar(chave)
    if not tarefa:
        return

    pend_n = int(
        (bd.um(
            "SELECT COUNT(*) AS n FROM conversation_task_steps "
            "WHERE task_id=? AND status='pending'",
            (tarefa.id,),
        ) or {}).get("n", 0)
    )

    # Nunca permita concluir uma tarefa que ainda possui etapas pendentes.
    if pend_n > 0:
        return

    bd.executar(
        "UPDATE conversation_tasks SET status='completed', updated_at=? WHERE id=?",
        (bd.agora(), tarefa.id),
    )

def pausar(chave) -> None:
    _schema()
    tarefa = carregar(chave)
    if tarefa:
        bd.executar("UPDATE conversation_tasks SET status='paused', updated_at=? WHERE id=?",
                    (bd.agora(), tarefa.id))

def cancelar(chave) -> None:
    _schema()
    tarefa = carregar(chave)
    if tarefa:
        bd.executar("UPDATE conversation_tasks SET status='cancelled', updated_at=? WHERE id=?",
                    (bd.agora(), tarefa.id))

def contexto_operacao(chave, atual: str = "") -> str:
    """Contexto mínimo para executar UMA operação da tarefa.

    Diferente de `contexto()`, não despeja o roteiro inteiro no prompt. O
    controlador já escolheu a próxima operação; o modelo só precisa produzir
    os argumentos dela.
    """
    tarefa = carregar(chave)
    operacao = proxima_operacao(chave) if tarefa else None
    if not tarefa or not operacao:
        return ""
    concluidas = sum(1 for e in tarefa.etapas if e.get("status") == "done")
    total = len(tarefa.etapas)
    linhas = [
        f"TAREFA {concluidas}/{total}",
        f"OBJETIVO: {tarefa.objetivo}",
    ]
    if tarefa.workspace_root:
        linhas.append(f"WORKSPACE DA TAREFA: {tarefa.workspace_root}")
    if tarefa.known_paths:
        linhas.append(f"CAMINHOS CONHECIDOS (não inventar outros): {tarefa.known_paths[-10:]}")
    linhas += [
        f"ETAPA ATUAL: {operacao['etapa'][:500]}",
        f"OPERAÇÃO ÚNICA: {operacao['ferramenta']}",
        *([f"SUBOPERAÇÃO: {operacao.get('operacao')}"] if operacao.get('operacao') else []),
        *([f"MODO: {operacao.get('modo')}"] if operacao.get('modo') else []),
        f"INSTRUÇÃO DA OPERAÇÃO: {operacao.get('instrucao') or operacao['etapa']}"[:1800],
    ]
    if operacao.get("restantes"):
        linhas.append(f"ORDEM RESTANTE NESTE MARCO: {operacao['restantes']}")
    if tarefa.ultima_acao:
        linhas.append(f"ÚLTIMA AÇÃO: {tarefa.ultima_acao}")
    if tarefa.ultimo_resultado:
        linhas.append(f"ÚLTIMO RESULTADO: {tarefa.ultimo_resultado[:700]}")
    budget=6500
    records=[(op, ev) for etapa in tarefa.etapas for op in etapa.get('operacoes_lista',[])
             if op.get('ferramenta') in {'workspace','execute_command'}
             for ev in op.get('tentativas', [])+[op.get('evidencia', {})] if ev]
    for op, ev in reversed(records):
        output=str(ev.get('output',''))
        if len(output)>budget:
            linhas.append('EVIDÊNCIA '+str(op.get('id'))+' disponível no estado da tarefa; excerto: '+output[:min(700,budget)])
            budget-=min(700,budget)
        else:
            linhas.append('EVIDÊNCIA ATRIBUÍDA '+str(op.get('id'))+': '+output)
            budget-=len(output)
        if budget<=0:
            break
    if atual and not eh_comando_retomada(atual):
        linhas.append(f"ENTRADA RELACIONADA: {atual[:500]}")
    if tarefa.workspace_root or tarefa.known_paths:
        linhas.append("REGRA DE CAMINHO: use o workspace e os caminhos conhecidos; não invente Desktop/Área de Trabalho ou usuários alternativos.")
    return "\n".join(linhas)


def validar_contrato_escrita(tarefa, args: dict) -> str:
    """Pré-condições de correção no editor atual; nunca executa código do arquivo."""
    import ast
    if not sequencia_correcao(tarefa.objetivo) or args.get('operacao')!='salvar':
        return ''
    if re.search(r'\bautorizo\s+(?:alterar|mudar|remover)\s+(?:o\s+|a\s+)?(?:contrato|assinatura|requisitos)\b',intent.normalizar(tarefa.objetivo)):
        return ''  # somente autorização na entrada original, não no arquivo/recibo
    from tools import filesystem
    path=filesystem.resolver_caminho(args.get('caminho',''))
    if not filesystem._permitido(path):
        return 'Correção recusada: caminho fora das áreas permitidas.'
    records=[op.get('evidencia',{}) for etapa in tarefa.etapas for op in etapa.get('operacoes_lista',[])
             if op.get('ferramenta')=='workspace' and op.get('operacao')=='ler'
             and op.get('evidencia',{}).get('status') in {None,'success','sucesso'}]
    read=next((ev for ev in reversed(records) if 'PATH='+str(path)+'\n' in ev.get('output','')),None)
    if not read or read.get('excerto') or '[truncado]' in read.get('output',''):
        return 'Correção recusada: leia o arquivo completo e preserve o contrato original antes de editar.'
    old=path.read_text(encoding='utf-8')
    observed=read['output'].split('\n',3)[-1]
    if observed!=old:
        return 'Correção recusada: o arquivo mudou desde a leitura; precisa de nova observação.'
    candidate=str(args.get('conteudo',''))
    if args.get('modo')=='editar':
        search=str(args.get('procurar',''))
        if not search or search not in old:
            return 'Correção recusada: trecho de edição não encontrado na leitura original; nenhuma escrita foi tentada.'
        candidate=old.replace(search,str(args.get('substituir','')))
    elif args.get('modo')=='anexar':
        candidate=old+candidate
    if path.suffix.casefold()=='.py':
        try:
            original=ast.parse(old)
        except SyntaxError:
            return 'Correção recusada: sintaxe original inválida; contrato estrutural requer revisão explícita.'
        try:
            updated=ast.parse(candidate)
        except SyntaxError as exc:
            hint=' Use quebras de linha reais no valor conteudo, não um programa inteiro com \\n literal.' if '\n' not in candidate and r'\n' in candidate else ''
            return f'Correção recusada: Python inválido na linha {exc.lineno}; não substituí o arquivo.'+hint
        functions={n.name:n for n in updated.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for node in original.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                changed=functions.get(node.name)
                if changed is None or type(changed) is not type(node) or ast.dump(node.args)!=ast.dump(changed.args):
                    return 'Correção recusada: nome/assinatura pública original foi removido ou alterado: '+node.name
                guards=[n for n in ast.walk(node) if isinstance(n,ast.If) and any(isinstance(r,ast.Raise) for r in ast.walk(n))]
                new_guards={ast.dump(n.test) for n in ast.walk(changed) if isinstance(n,ast.If)
                            and any(isinstance(r,ast.Raise) for r in ast.walk(n))}
                if any(ast.dump(n.test) not in new_guards for n in guards):
                    return 'Correção recusada: validação original removida/alterada sem autorização: '+node.name
                required_keys=[{k.value for k in n.value.keys if isinstance(k,ast.Constant) and isinstance(k.value,str)}
                               for n in ast.walk(node) if isinstance(n,ast.Return) and isinstance(n.value,ast.Dict)]
                returned_keys=[{k.value for k in n.value.keys if isinstance(k,ast.Constant) and isinstance(k.value,str)}
                               for n in ast.walk(changed) if isinstance(n,ast.Return) and isinstance(n.value,ast.Dict)]
                if any(keys and not any(keys.issubset(actual) for actual in returned_keys) for keys in required_keys):
                    return 'Correção recusada: campos do formato de saída original foram removidos sem autorização: '+node.name
        requirements=tarefa.objetivo+'\n'+'\n'.join(ev.get('output','') for ev in records)
        for name,params in re.findall(r'(?:\bfun[cç][aã]o\s+|`)([A-Za-z_]\w*)\(([^)\n]+)\)',requirements,re.I):
            if not re.fullmatch(r'\s*[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*\s*',params):
                continue
            node=functions.get(name)
            if node is None or [a.arg for a in node.args.args]!=[p.strip() for p in params.split(',')]:
                return 'Correção recusada: a assinatura exigida no requisito original não foi preservada: '+name
    elif path.suffix.casefold()=='.json':
        try:
            before=json.loads(old);after=json.loads(candidate)
        except ValueError:
            return 'Correção recusada: JSON inválido.'
        if isinstance(before,dict) and (not isinstance(after,dict) or any(k not in after or type(after[k]) is not type(v) for k,v in before.items())):
            return 'Correção recusada: campos/tipos do formato original foram alterados sem autorização.'
    return ''


def contexto(chave, atual: str = "") -> str:
    tarefa = carregar(chave)
    if not tarefa:
        return ""
    concluidas = [e["texto"] for e in tarefa.etapas if e["status"] == "done"]
    falhas = [e["texto"] for e in tarefa.etapas if e["status"] == "failed"]
    pend = [e["texto"] for e in tarefa.etapas if e["status"] == "pending"]
    evidencias_etapas = [
        f"{e['ordem']}: {e['texto']} -> {str(e.get('resultado') or '')[:500]}"
        for e in tarefa.etapas if e["status"] in {"done", "failed"} and e.get("resultado")
    ]
    proxima = next((e for e in tarefa.etapas if e["status"] == "pending"), None)
    linhas = [
        "[TAREFA EM ANDAMENTO — NÃO RECOMEÇAR DO ZERO]",
        f"Objetivo acumulado: {tarefa.objetivo}",
        f"Concluídas: {concluidas or ['nenhuma']}",
        f"Pendentes: {pend or ['nenhuma']}",
    ]
    if proxima:
        linhas.append(f"PRÓXIMA ETAPA OBRIGATÓRIA: {proxima['texto']}")
        pendentes_ferramentas = ferramentas_pendentes(chave)
        if pendentes_ferramentas:
            linhas.append(f"PRÓXIMA FERRAMENTA OBRIGATÓRIA: {pendentes_ferramentas[0]}")
        ferramentas_etapa = proxima.get("ferramentas_lista") or ([] if not proxima.get("ferramenta") else [proxima["ferramenta"]])
        executadas_etapa = set(proxima.get("ferramentas_executadas_lista") or [])
        ferramentas_restantes = [f for f in ferramentas_etapa if f not in executadas_etapa]
        if executadas_etapa:
            linhas.append(f"FERRAMENTAS JÁ EXECUTADAS NESTA ETAPA: {sorted(executadas_etapa)}")
        if ferramentas_restantes:
            linhas.append(f"FERRAMENTAS RESTANTES DA ETAPA (nesta ordem): {ferramentas_restantes}")
            linhas.append(f"PRÓXIMA FERRAMENTA OBRIGATÓRIA: {ferramentas_restantes[0]}")
            linhas.append(f"VERIFICADOR DA ETAPA: {ferramentas_restantes[-1]}")
    if falhas:
        linhas.append(f"Falharam: {falhas}")
    if evidencias_etapas:
        linhas.append("Evidências das etapas: " + " | ".join(evidencias_etapas[-5:]))
    if tarefa.ultima_acao:
        linhas.append(f"Última ação: {tarefa.ultima_acao}")
    if tarefa.ultimo_resultado:
        linhas.append(f"Último resultado: {tarefa.ultimo_resultado[:800]}")
    if atual:
        linhas.append(f"Mensagem atual: {atual}")
        if eh_comando_retomada(atual):
            linhas.append("A mensagem atual é apenas um comando para retomar. NÃO crie outra etapa a partir dela.")
    linhas.append("Continue pela próxima etapa pendente. Não trate esta mensagem como um pedido isolado.")
    return "\n".join(linhas)

def resumo_para_log(chave) -> dict:
    tarefa = carregar(chave)
    if not tarefa:
        return {}
    return {
        "id": tarefa.id,
        "status": tarefa.status,
        "objetivo": tarefa.objetivo[:500],
        "etapa_atual": tarefa.etapa_atual,
        "pendentes": [e["texto"] for e in tarefa.etapas if e["status"] == "pending"],
        "ferramentas_proxima_etapa": (next((e.get("ferramentas_lista") for e in tarefa.etapas if e["status"] == "pending"), []) or []),
    }
