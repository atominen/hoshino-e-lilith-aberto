"""Ciclo de projeto de programação: uma ação por vez, com raciocínio e checkpoint durável.

Pedido humano 29/10: depois do Minecraft, o alvo de programação é um projeto
grande (simulação C++/OpenGL). O pipeline geral de tarefas escreve argumentos
sem raciocínio e em ~10 passos; no ensaio C++ ela trocou o programa por
`int main(){return 0;}` porque o `echo` com aspas falhava. Aqui, como no
Minecraft, ela observa o projeto (arquivos, últimos recibos, erros, o próprio
plano), escolhe UMA ferramenta pensando com a própria identidade, e o
controlador executa pelos contratos existentes e guarda o checkpoint.

O controlador não escreve código, não completa etapas e não decide a física:
só observa, executa o que ela pediu, recusa repetições sem efeito e só aceita
`concluir_projeto` depois de uma execução bem-sucedida posterior à última
alteração dos arquivos.
"""
import hashlib
import json
import re
import shlex
from pathlib import Path

from core import bd

VERSION = 1
# Pedido explícito: "Projeto: ..." no início. Pedidos curtos continuam no pipeline geral.
_MARCADOR = re.compile(r"^\s*projeto\s*:", re.IGNORECASE)
TOOLS = ("escrever_na_oficina", "editar_na_oficina", "ler_da_oficina", "listar_oficina", "verificar_codigo",
         "executar_na_oficina", "executar_grafico_na_oficina", "observar_imagem_da_oficina",
         "web_search", "fetch_page")
CHANGES = {"escrever_na_oficina", "editar_na_oficina"}
RUNS = {"executar_na_oficina", "executar_grafico_na_oficina"}
SEM_ACAO_MAX = 3      # respostas seguidas sem chamada de ferramenta antes de pausar
RECIBOS_NA_VISAO = 6  # 29/10: menos histórico bruto, mais foco (context rot)

PROMPT = (
    "MODO PROJETO DE PROGRAMAÇÃO. Você trabalha no seu projeto passo a passo, na sua oficina. "
    "A cada passo você recebe projeto_atual (objetivo, sua pasta, arquivos, seus últimos recibos e seu plano) "
    "e codigo_do_projeto: seus fontes atuais, numerados, como um editor (arquivo pequeno inteiro; o do erro "
    "numa janela em volta do erro; os outros como esboço com as linhas das definições). Não precisa ler de novo "
    "o que está ali; para outra parte, ler_da_oficina com inicio/fim. primeiro_erro mostra o erro mais recente "
    "com as linhas em volta. minhas_anotacoes é o seu diário: a cada passo, escreva no texto da resposta 1 ou 2 "
    "frases com o que você concluiu do último resultado e por que escolheu esta ação; elas voltam nos próximos "
    "passos, então confie nelas em vez de refazer o que já descobriu. Arquivos (arquivo:linha) e `nomes` entre "
    "crases citados na sua nota aparecem já buscados em ja_buscado_para_voce no passo seguinte. "
    "compilar_projeto configura e compila com CMake sem precisar de cd; onde_esta acha definições e usos. "
    "e chama EXATAMENTE UMA ferramenta. O resultado volta no próximo passo; nada é executado sem a sua chamada. "
    "Escreva arquivos com escrever_na_oficina (conteúdo completo) e corrija partes com editar_na_oficina: "
    "pelas linhas inicio/fim que você leu numeradas com ler_da_oficina, ou por um trecho copiado exatamente. "
    "Ao salvar um arquivo de código, o resultado já traz os erros/avisos do compilador ou validador; "
    "verificar_codigo mostra o painel completo de problemas (análise estática e estilo também). "
    "Compile e rode com executar_na_oficina (bash para vários arquivos/CMake; cpp para um arquivo só). "
    "Programas com janela/GPU rodam com executar_grafico_na_oficina, que captura a janela; "
    "olhe a captura com observar_imagem_da_oficina antes de afirmar como ficou. "
    "Pesquise com web_search e leia páginas com fetch_page quando precisar estudar. "
    "Use anotar_plano para manter seu plano e notas (ele volta a cada passo). "
    "Quando um erro aparecer, leia a mensagem e as linhas indicadas e corrija a causa; "
    "avisos não impedem compilar: priorize erros e avançar no objetivo. estado_do_projeto mostra se o projeto "
    "inteiro já compilou e rodou; compile cedo e com frequência. "
    "não troque o objetivo por uma versão mais fácil sem dizer. "
    "Se precisar de uma decisão humana (permissão, mudança de requisito), use pedir_decisao_humana. "
    "Quando terminar de verdade, chame concluir_projeto com o que foi feito, como executar e as limitações: "
    "ele só é aceito depois de uma execução do programa com saída visível (ou janela) feita após a última "
    "alteração dos arquivos. No resumo, descreva só o que os recibos mostraram; não afirme uma saída que não viu. "
    "Sua resposta em texto, se houver, é uma nota curta; o raciocínio é seu e não é mostrado.")

VIRTUAL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "compilar_projeto",
        "description": "Configura e compila o projeto com CMake na pasta do projeto (cmake -S . -B build e "
                       "cmake --build build), sem precisar de cd.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "onde_esta",
        "description": "Mostra onde um nome (struct, classe, função, variável, macro) é definido e usado nos "
                       "arquivos do seu projeto, com arquivo e linha.",
        "parameters": {"type": "object", "properties": {
            "nome": {"type": "string", "description": "O nome exato, por exemplo AccretionDisk."}},
            "required": ["nome"]}}},
    {"type": "function", "function": {
        "name": "anotar_plano",
        "description": "Guarda/atualiza seu plano do projeto e notas; ele aparece em meu_plano a cada passo.",
        "parameters": {"type": "object", "properties": {
            "passos": {"type": "array", "items": {"type": "string"}, "description": "Próximos passos, curtos."},
            "nota": {"type": "string", "description": "Decisões, descobertas ou pendências que quer lembrar."}},
            "required": ["passos"]}}},
    {"type": "function", "function": {
        "name": "concluir_projeto",
        "description": "Declara o projeto concluído. Só é aceito depois de uma execução bem-sucedida após a última alteração.",
        "parameters": {"type": "object", "properties": {
            "resumo": {"type": "string", "description": "O que você construiu e o que foi realmente testado."},
            "como_executar": {"type": "string", "description": "Comandos para compilar e rodar."},
            "limitacoes": {"type": "string", "description": "O que ficou faltando ou é aproximado."}},
            "required": ["resumo", "como_executar", "limitacoes"]}}},
    {"type": "function", "function": {
        "name": "pedir_decisao_humana",
        "description": "Pausa o projeto e pergunta ao humano (permissão, mudança de requisito, bloqueio externo).",
        "parameters": {"type": "object", "properties": {
            "pergunta": {"type": "string"}}, "required": ["pergunta"]}}},
]
VIRTUAL = {s["function"]["name"] for s in VIRTUAL_SCHEMAS}


def is_project(objetivo: str) -> bool:
    return bool(_MARCADOR.match(str(objetivo or "")))


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _slug(objetivo: str) -> str:
    import unicodedata
    texto = _MARCADOR.sub("", str(objetivo or ""), count=1)
    # 29/10: 'própria' virava 'prpria'; os acentos são decompostos antes de cair para ASCII.
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    palavras = re.findall(r"[a-z0-9]+", texto.lower())
    return "_".join(palavras[:4]) or "projeto"


def initial(task) -> dict:
    return {"kind": "projeto", "version": VERSION, "goal_hash": _digest(task.objetivo),
            "pasta": "projetos/" + _slug(task.objetivo), "steps": 0, "events": [], "plano": None,
            "pending": None, "sem_acao": 0, "last_change_step": -1, "last_ok_run_step": -1,
            "feedback": None, "concluido": None}


def _schema():
    bd.executar('''CREATE TABLE IF NOT EXISTS conversation_task_game_states(
        task_id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL)''', strict=True)


def load(task) -> dict:
    _schema()
    row = bd.um("SELECT payload FROM conversation_task_game_states WHERE task_id=?", (task.id,), strict=True)
    cp = json.loads(row["payload"]) if row else initial(task)
    if cp.get("kind") != "projeto" or cp.get("version") != VERSION:
        raise ValueError("PROJECT_CHECKPOINT_REVIEW_REQUIRED")
    if cp.get("goal_hash") != _digest(task.objetivo):
        raise ValueError("PROJECT_GOAL_CHANGED")
    return cp


def aguardando_humano(task) -> bool:
    """Projeto parado em pedir_decisao_humana ainda sem resposta: a próxima mensagem é a resposta."""
    if not task or not is_project(task.objetivo):
        return False
    _schema()
    row = bd.um("SELECT payload FROM conversation_task_game_states WHERE task_id=?", (task.id,))
    if not row:
        return False
    cp = json.loads(row["payload"])
    ultimo = (cp.get("events") or [{}])[-1]
    return (ultimo.get("ferramenta") == "pedir_decisao_humana"
            and (cp.get("resposta_humana") or {}).get("pergunta_passo") != ultimo.get("passo"))


def receber_resposta(cp: dict, texto: str, autor: str = "") -> bool:
    """Guarda a resposta à última pergunta dela (29/10: o texto era descartado na retomada)."""
    ultimo = (cp.get("events") or [{}])[-1]
    if ultimo.get("ferramenta") != "pedir_decisao_humana" or not str(texto or "").strip():
        return False
    if (cp.get("resposta_humana") or {}).get("pergunta_passo") == ultimo.get("passo"):
        return False
    cp["resposta_humana"] = {"pergunta_passo": ultimo["passo"], "passo": cp["steps"],
                             "autor": str(autor or "")[:80], "texto": str(texto).strip()[:1500]}
    return True


def receber_mensagem(cp: dict, texto: str, autor: str = "", objetivo: str = "") -> bool:
    """Mensagem da pessoa ao retomar (fora de pergunta): aparece na visão por alguns passos."""
    texto = str(texto or "").strip()
    if not texto or texto == str(objetivo or "").strip() or is_project(texto):
        return False
    cp["mensagem_humana"] = {"passo": cp["steps"], "autor": str(autor or "")[:80], "texto": texto[:1500]}
    return True


def save(task, cp) -> None:
    _schema()
    bd.executar('''INSERT INTO conversation_task_game_states(task_id,payload,updated_at) VALUES(?,?,?)
        ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at''',
                (task.id, json.dumps(cp, ensure_ascii=False), bd.agora()), strict=True)


CODIGO_NA_VISAO = 18000  # caracteres; ~5 mil tokens, cabe com folga no contexto de 32K
FONTES_NA_VISAO = {".cpp", ".cc", ".c", ".h", ".hpp", ".comp", ".vert", ".frag", ".glsl", ".py", ".txt", ".cmake"}


JANELA_LINHAS = 100  # SWE-agent: ~100 linhas rendem mais que 30 ou o arquivo inteiro
_DEFINICAO = re.compile(r"^(?:struct|class|enum|namespace|#include|#define|#pragma|layout|uniform|"
                        r"(?:static\s+|inline\s+|const\s+)*[\w:<>,*&\s]+?\s+[\w:~]+\s*\([^;]*$)")


def _esboco(linhas: list) -> str:
    """Só as definições (structs, funções, includes) com o número da linha: o mapa do arquivo."""
    marcas = [f"{i:>4}| {l.strip()[:90]}" for i, l in enumerate(linhas, 1) if _DEFINICAO.match(l)]
    return f"({len(linhas)} linhas; esboço — leia trechos com ler_da_oficina inicio/fim)\n" + "\n".join(marcas[:40])


def args_compilar(cp: dict, raiz: Path) -> dict | None:
    """Atalho compilar_projeto (29/10: cd duplicado, $0 em tmp/, make fora de build/ custaram passos)."""
    if not (raiz / cp["pasta"] / "CMakeLists.txt").is_file():
        return None
    return {"codigo": "cmake -S . -B build && cmake --build build -j4", "linguagem": "bash",
            "projeto": cp["pasta"], "timeout": 300}


_REF_ARQUIVO = re.compile(r"([\w./-]+\.(?:cpp|cc|c|h|hpp|comp|vert|frag|glsl|py|txt))"
                          r"(?:\s*(?::|,)?\s*(?:linhas?|line)?\s*(\d+))?", re.I)
_REF_LINHA_DO = re.compile(r"linhas?\s+(\d+)\s+(?:do|de|em|no)\s+`?([\w./-]+\.(?:cpp|cc|c|h|hpp|comp|glsl|py|txt))", re.I)
_REF_NOME = re.compile(r"`([A-Za-z_]\w{2,})`")


def pre_busca(cp: dict, raiz: Path, texto: str, codigo: dict) -> list:
    """O que ela disse que vai olhar, já posto na tela (29/10: 'vou ler engine.h para ver a struct' virava
    um passo inteiro). Só referências explícitas: arquivo[:linha] e `nomes` entre crases."""
    base = raiz / cp["pasta"]
    if not texto or not base.is_dir():
        return []
    fontes = {f.name: f for f in base.rglob("*") if f.is_file() and f.suffix in FONTES_NA_VISAO
              and not any(x in f.parts for x in ("build", "CMakeFiles"))}
    achados = []
    # Uma referência por arquivo; a que tem linha vale mais que a sem linha.
    pedidos = {}
    for nome_arq, linha in ([(m.group(1), m.group(2)) for m in _REF_ARQUIVO.finditer(texto)]
                            + [(m.group(2), m.group(1)) for m in _REF_LINHA_DO.finditer(texto)]):
        f = fontes.get(Path(nome_arq).name)
        if f and (linha or f not in pedidos):
            pedidos[f] = int(linha) if linha and linha.isdigit() else 1
    for f, centro in pedidos.items():
        rel = str(f.relative_to(raiz))
        na_tela = codigo.get(rel, "")
        janela = re.match(r"\(linhas (\d+)–(\d+) de", na_tela)
        if (na_tela and not na_tela.startswith("(")) or (janela and int(janela[1]) <= centro <= int(janela[2])):
            continue  # o arquivo inteiro, ou a janela com essa linha, já está na tela
        try:
            linhas = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        a, b = max(1, centro - 12), min(len(linhas), max(1, centro - 12) + 24)
        achados.append({"arquivo": rel, "linhas": f"{a}–{b} de {len(linhas)}",
                        "trecho": "\n".join(f"{i:>4}| {linhas[i - 1]}" for i in range(a, b + 1))})
        if len(achados) >= 2:
            break
    for nome in dict.fromkeys(_REF_NOME.findall(texto)):
        if len(achados) >= 4 or Path(nome).suffix:
            break
        saida = onde_esta(raiz, cp["pasta"], nome)
        if saida.startswith("Definição provável") and "(0)" not in saida.split("\n")[0]:
            achados.append({"onde_esta": nome, "resultado": saida.split("\nUsos")[0]})
    return achados


_INTENCAO_MUDAR = re.compile(r"\bvou\s+(?:agora\s+)?(?:editar|corrigir|reescrever|substituir|trocar|consertar|"
                             r"remover|apagar|adicionar|incluir|escrever)\b", re.I)
_SO_OLHA = {"ler_da_oficina", "listar_oficina", "verificar_codigo"}


def _parecida(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def avisos_do_intermediario(cp: dict) -> list:
    """Avisos por regra sobre o próprio caminho dela (sem modelo; o mini-modelo só entra no que regra não pega).
    São fatos sobre as notas e ações registradas, não ordens: a decisão continua dela."""
    avisos = []
    notas = [(e["passo"], e["nota"].strip()) for e in cp["events"] if (e.get("nota") or "").strip()]
    if len(notas) >= 2:
        passo, ultima = notas[-1]
        iguais = [p for p, n in notas[-8:-1] if _parecida(ultima[:400], n[:400]) >= 0.75]
        if len(iguais) >= 2:
            avisos.append(f"Pensamento repetido: sua nota do passo {passo} é quase igual às dos passos "
                          f"{', '.join(map(str, iguais[-3:]))}. Essa conclusão já está nas suas anotações; "
                          "o próximo passo útil é agir sobre ela.")
    # Disse que ia mudar o código e as ações seguintes só olharam.
    for i in range(len(cp["events"]) - 1, max(-1, len(cp["events"]) - 6), -1):
        e = cp["events"][i]
        if _INTENCAO_MUDAR.search(e.get("nota") or ""):
            depois = cp["events"][i:]
            if len(depois) >= 3 and all(x["ferramenta"] in _SO_OLHA for x in depois):
                avisos.append(f"No passo {e['passo']} você escreveu que ia mudar o código, e desde então foram "
                              f"{len(depois)} passos só lendo ou verificando.")
            break
    from core import intermediario
    registro = cp.get("intermediario_2b") or {}
    if intermediario.ativo() and registro.get("aviso") and cp["steps"] - registro["passo"] <= 1:
        avisos.append("[intermediário 2B] " + registro["aviso"])
    return avisos


def _erro_no_momento(cp: dict, passo: int) -> str | None:
    """Primeiro erro do diagnóstico mais recente ANTES de `passo` — o que a nota daquele passo tinha diante de si."""
    for e in reversed(cp["events"]):
        saida = e.get("saida") or ""
        if e["passo"] >= passo or not re.search(r"Verificação ao salvar|Problemas em|\[oficina \| código", saida):
            continue
        m = _ERRO_COMPILADOR.search(saida)
        return m.group(0) if m else ""  # inteiro (revisão Codex: prefixo igual escondia causa diferente)
    return None


def _mudou_arquivo(cp: dict, de: int, ate: int) -> bool:
    return any(e["ok"] and (e["ferramenta"] in CHANGES or formata(e["ferramenta"], e.get("argumentos")))
               and de <= e["passo"] < ate for e in cp["events"])


def consultar_intermediario(cp: dict) -> None:
    """Pergunta ao intermediário 2B (CPU) se a nota mais recente só repete as anteriores (29/10, pedido humano).
    Travas por regra vêm antes do modelo; a anterior citada é escolhida por regra; o aviso é suave e mostra a prova.
    Avaliação: compartilhado/runtime/ensaios/intermediario-20261029/."""
    from core import intermediario
    if not intermediario.ativo():
        return
    notas = [(e["passo"], e["nota"].strip()) for e in cp["events"] if (e.get("nota") or "").strip()]
    if len(notas) < 4:
        return
    passo, nova = notas[-1]
    anterior = cp.get("intermediario_2b") or {}
    if anterior.get("passo") == passo and not anterior.get("falhou"):
        return  # esta nota já foi consultada (uma falha não conta: tenta de novo na próxima decisão)
    registro = {"passo": passo, "aviso": None}
    cp["intermediario_2b"] = registro
    # Só compara com notas escritas depois da última novidade (revisão Codex: a trava olhava só a nota anterior,
    # mas a comparação usava cinco). Novidade = arquivo alterado/formatado ou primeiro erro diferente.
    erro_agora = _erro_no_momento(cp, passo)
    comparaveis = []
    for p_ant, n_ant in reversed(notas[-6:-1]):
        if _mudou_arquivo(cp, p_ant, passo):
            registro["trava"] = "arquivo alterado"
            break
        if _erro_no_momento(cp, p_ant) != erro_agora:
            registro["trava"] = "erro do compilador mudou"
            break
        comparaveis.insert(0, (p_ant, n_ant))
    if not comparaveis:
        return
    julgamento = intermediario.repeticao([n for _, n in comparaveis], nova)
    if julgamento is None:
        registro["falhou"] = True
        return
    if not julgamento:
        return
    registro.pop("trava", None)
    p_sim, n_sim = max(comparaveis, key=lambda pn: _parecida(nova[:400], pn[1][:400]))
    # O modelo só diz sim/não; o passo citado é o mais parecido pelo texto (revisão Codex 30/10).
    registro["aviso"] = (f"O intermediário acha que sua anotação do passo {passo} só repete as anteriores; a mais "
                         f"parecida pelo texto é a do passo {p_sim}: \"{n_sim[:160]}\". Se há algo novo, ignore "
                         "este aviso.")


def ja_na_tela(visao: dict, tool: str, args: dict, cp: dict, raiz: Path) -> str | None:
    """Reler um arquivo que já está inteiro em codigo_do_projeto e não mudou desde a última leitura
    não traz nada novo (29/10: 46 de 48 passos eram leituras, muitas do engine.h de 42 linhas que
    estava inteiro na tela dela). A primeira leitura e a de uma versão nova sempre passam."""
    if tool != "ler_da_oficina" or not isinstance((args or {}).get("caminho"), str):
        return None
    caminho = args["caminho"].strip().lstrip("./")
    texto = ((visao.get("projeto_atual") or {}).get("codigo_do_projeto") or {}).get(caminho)
    if not texto or texto.startswith("("):
        return None  # não está na tela, ou só em janela/esboço: ler é legítimo
    try:
        versao = (raiz / caminho).stat().st_mtime_ns
    except OSError:
        return None
    lidos = cp.setdefault("lido_versao", {})
    if lidos.get(caminho) != versao:
        lidos[caminho] = versao
        return None
    return (f"{caminho} já está inteiro e numerado em codigo_do_projeto, na sua tela agora; ler de novo não "
            "traz nada novo. Use as linhas que você vê: edite (editar_na_oficina com inicio/fim) ou compile.")


def onde_esta(raiz: Path, pasta: str, nome) -> str:
    """Definições e usos de um nome nos fontes do projeto, por busca de texto (rápido e sem modelo)."""
    nome = str(nome or "").strip()
    if not re.fullmatch(r"[A-Za-z_]\w*", nome):
        return "Erro: passe um nome só (struct, classe, função, variável ou macro), sem espaços."
    palavra = re.compile(rf"\b{nome}\b")
    definicao = re.compile(
        rf"^\s*(?:typedef\s+)?(?:struct|class|enum(?:\s+class)?|union|namespace)\s+{nome}\b"
        rf"|^\s*#\s*define\s+{nome}\b"
        rf"|^(?!\s*(?:return|if|while|for|else|switch)\b)\s*[\w:<>,*&\s]+?\b{nome}\s*\([^;]*$"
        rf"|^(?!\s*(?:return|if|while|for|else|switch)\b)\s*[\w:<>,*&\s]+?\b{nome}\s*\([^)]*\)\s*(?:const\s*)?\{{"
        rf"|^\s*(?:static\s+|const\s+|constexpr\s+|inline\s+)*[\w:<>,*&]+\s+[*&]?{nome}\s*(?:=|;|\[|\{{)")
    defs, usos = [], []
    base = raiz / pasta
    for f in sorted(base.rglob("*")) if base.is_dir() else []:
        if not f.is_file() or f.suffix not in FONTES_NA_VISAO or any(
                x in f.parts for x in ("build", "CMakeFiles", "__pycache__", ".git")):
            continue
        try:
            linhas = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(f.relative_to(raiz))
        for i, linha in enumerate(linhas, 1):
            if palavra.search(linha):
                (defs if definicao.search(linha) else usos).append(f"  {rel}:{i}: {linha.strip()[:120]}")
    if not defs and not usos:
        return f"'{nome}' não aparece em nenhum arquivo de {pasta}."
    return (f"Definição provável de '{nome}' ({len(defs)}):\n" + ("\n".join(defs[:10]) or "  nenhuma encontrada")
            + f"\nUsos ({len(usos)}" + (", primeiros 12" if len(usos) > 12 else "") + "):\n"
            + ("\n".join(usos[:12]) or "  nenhum"))


def codigo_do_projeto(raiz: Path, pasta: str, foco: dict | None = None) -> dict:
    """Fontes atuais como um editor (29/10). Arquivo pequeno aparece inteiro; o arquivo do erro aparece
    numa janela de ~100 linhas em volta do erro; o mais recente desde o topo; os outros só como esboço.
    Antes eram 7 mil tokens de código por passo e o 9B se perdia (context rot)."""
    base = raiz / pasta
    if not base.is_dir():
        return {}
    foco = foco or {}
    fontes = [p for p in base.rglob("*") if p.is_file() and p.suffix in FONTES_NA_VISAO
              and not any(x in p.parts for x in ("build", "CMakeFiles", "__pycache__", ".git"))]
    fontes.sort(key=lambda p: p.stat().st_mtime, reverse=True)  # o que ela mexeu por último primeiro
    visao, usado = {}, 0
    for n, p in enumerate(fontes):
        rel = str(p.relative_to(raiz))
        try:
            linhas = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        numerar = lambda a, b: "\n".join(f"{i:>4}| {linhas[i - 1]}" for i in range(a, b + 1))
        if len(linhas) <= 40 or (len(linhas) <= JANELA_LINHAS + 20 and (rel in foco or n == 0)):
            texto = numerar(1, len(linhas)) if linhas else ""
        elif rel in foco or n == 0:
            centro = foco.get(rel, 1)
            inicio = max(1, min(centro - JANELA_LINHAS // 2, len(linhas) - JANELA_LINHAS + 1))
            fim = min(len(linhas), inicio + JANELA_LINHAS - 1)
            texto = (f"(linhas {inicio}–{fim} de {len(linhas)}; o resto com ler_da_oficina inicio/fim)\n"
                     + numerar(inicio, fim))
        else:
            texto = _esboco(linhas)
        if usado + len(texto) > CODIGO_NA_VISAO:
            texto = _esboco(linhas)
        visao[rel] = texto
        usado += len(texto)
    return visao


_ERRO_COMPILADOR = re.compile(r"(?P<arq>[^\s:]+\.(?:cpp|cc|c|h|hpp|comp|vert|frag|glsl|py|txt)):(?P<l>\d+):"
                              r"(?:(?P<c>\d+):)? ?(?:erro|error|fatal error|ERROR):\s*(?P<msg>.*)")


def primeiro_erro(cp: dict, raiz: Path) -> dict | None:
    """O primeiro erro do diagnóstico mais recente, com as linhas em volta (como o editor ao clicar).
    Só fatos do compilador; a causa e a correção são dela."""
    for e in reversed(cp["events"]):
        saida = e.get("saida") or ""
        if not re.search(r"Verificação ao salvar|Problemas em|\[oficina \| código", saida):
            continue
        m = _ERRO_COMPILADOR.search(saida)
        if not m:
            return None  # o diagnóstico mais recente não tem erro
        rel = m["arq"].removeprefix("/workspace/").lstrip("./")
        linha = int(m["l"])
        trecho = ""
        try:
            linhas = (raiz / rel).read_text(encoding="utf-8").splitlines()
            a, b = max(1, linha - 4), min(len(linhas), linha + 4)
            trecho = "\n".join(f"{'>>' if i == linha else '  '}{i:>4}| {linhas[i - 1]}" for i in range(a, b + 1))
        except (OSError, UnicodeDecodeError):
            pass
        return {"do_passo": e["passo"], "arquivo": rel, "linha": linha, "mensagem": m["msg"].strip()[:400],
                "linhas_em_volta": trecho}
    return None


def _arquivos(raiz: Path, pasta: str) -> list:
    base = raiz / pasta
    if not base.is_dir():
        return []
    linhas = []
    for item in sorted(base.rglob("*")):
        if not item.is_file() or any(p in item.parts for p in ("CMakeFiles", "__pycache__", ".git")):
            continue
        rel = str(item.relative_to(raiz))
        try:
            texto = item.read_text(encoding="utf-8")
            linhas.append({"arquivo": rel, "linhas": texto.count("\n") + (1 if texto and not texto.endswith("\n") else 0),
                           "bytes": item.stat().st_size})
        except (UnicodeDecodeError, OSError):
            linhas.append({"arquivo": rel, "bytes": item.stat().st_size, "binario": True})
        if len(linhas) >= 60:
            break
    return linhas


def args_summary(tool: str, args: dict) -> dict:
    """Recibo legível: o conteúdo escrito vira tamanho, não ocupa o contexto de novo."""
    out = {}
    for key, value in (args or {}).items():
        if key in {"conteudo", "novo", "trecho", "codigo"} and isinstance(value, str) and len(value) > 160:
            out[key] = f"<{len(value)} caracteres, {value.count(chr(10)) + 1} linhas>"
        else:
            out[key] = value
    return out


def signature(tool: str, args: dict) -> str:
    return _digest([tool, args or {}])


def run_succeeded(tool: str, output: str) -> bool:
    texto = str(output or "")
    if tool == "executar_na_oficina":
        # 29/10: compilar sem saída contava como "executou"; ela então descreveu uma saída
        # que nenhum recibo mostrou. Só vale código 0 com saída visível do programa.
        status=re.search(r'^\[oficina \| código (-?\d+)\]\s*$',texto,re.M)
        return bool(status and int(status[1])==0 and texto[status.end():].strip() not in ('','(sem saída)'))
    if tool == "executar_grafico_na_oficina":
        header=texto.split('[saída]',1)[0]
        first=header.splitlines()[0] if header else ''
        return bool(('encerrado por mim' in first or 'terminou sozinho com código 0.' in first)
                    and re.search(r'^Capturas: .*capturas/[^\n;]+\.png \(',header,re.M))
    return False


def session_limit(cp: dict, per_session: int) -> int:
    total=cp.get('max_total_steps')
    return min(max(1,per_session),max(0,total-cp['steps'])) if type(total) is int and total>0 else max(1,per_session)


def _inside(root: Path, value: str) -> Path | None:
    value=str(value or '')
    if value.startswith('/workspace/'):value=value[len('/workspace/'):]
    path=(root/value).resolve()
    return path if path.is_relative_to(root.resolve()) else None


def _file_sha(path):
    try:return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else None
    except OSError:return None


def _source_stamp(root: Path, pasta: str):
    base=_inside(root,pasta)
    if not base or not base.is_dir():return None
    files=[]
    for path in sorted(base.rglob('*')):
        relative=path.relative_to(base)
        if any(p in {'CMakeFiles','__pycache__','.git','browser_profile','venv'} for p in relative.parts):continue
        # Build contém artefatos derivados, mas também pode conter shaders e
        # recursos carregados em execução. Esses inputs precisam invalidar a prova.
        if 'build' in relative.parts and path.suffix.lower() not in {
                '.c','.cc','.cpp','.h','.hpp','.comp','.vert','.frag','.glsl',
                '.png','.jpg','.jpeg','.bmp','.hdr','.obj','.mtl','.json','.ini','.csv','.bin'}:
            continue
        if not path.is_file():continue
        if not path.resolve().is_relative_to(base):return None
        digest=_file_sha(path)
        if digest is None:return None
        files.append([str(relative),digest])
    return _digest(files) if files else None


def _execution_target(root: Path, cp, tool, args, output):
    base=_inside(root,cp['pasta'])
    if not base:return None
    if args.get('arquivo'):
        target=_inside(root,args['arquivo'])
    elif tool=='executar_na_oficina' and args.get('linguagem','python')!='bash':
        match=re.match(r'Arquivo: ([^\n]+)',output)
        target=_inside(root,match[1]) if match else None
    else:
        script=str(args.get('codigo') or '').strip()
        # Somente uma cadeia && cujo último comando executa o artefato. Um
        # compilador seguido de echo, pipes ou condicionais não prova execução.
        if not script or any(x in script for x in (';','||','|','`','$(','\n','>','<')):return None
        cwd=root
        if args.get('projeto'):
            cwd=_inside(root,'projetos/'+str(args['projeto']).strip('/').removeprefix('projetos/'))
        if not cwd:return None
        commands=script.split('&&')
        for command in commands[:-1]:
            try:parts=shlex.split(command)
            except ValueError:return None
            if parts and parts[0]=='cd':
                if len(parts)!=2:return None
                cwd=_inside(root,str(cwd/parts[1]))
                if not cwd:return None
        try:parts=shlex.split(commands[-1])
        except ValueError:return None
        if not parts:return None
        if parts[0] in {'python','python3','node','bash','sh'}:
            if len(parts)<2 or parts[1].startswith('-'):return None
            path=parts[1]
        elif '/' in parts[0] and not parts[0].startswith('$'):path=parts[0]
        else:return None
        target=_inside(root,str(cwd/path))
    if not target or not target.is_file() or not target.is_relative_to(base):return None
    # Um wrapper shell pode só consultar/compilar. Para comprovar o produto,
    # execute seu artefato diretamente, sem inferir sucesso pelo script auxiliar.
    if target.suffix=='.sh':return None
    return target


def _execution_proof(cp,root,tool,args,output):
    if root is None or not run_succeeded(tool,output):return None
    root=Path(root).resolve()
    target=_execution_target(root,cp,tool,args,output)
    if target is None:return None
    stamp=_source_stamp(root,cp['pasta'])
    if stamp is None:return None
    graphical=tool=='executar_grafico_na_oficina'
    if graphical:
        captures=re.findall(r'(capturas/[^\n;]+\.png) \(',output.split('[saída]',1)[0])
        if not any(_file_sha(_inside(root,capture)) for capture in captures):return None
    if target.suffix not in {'.cpp','.cc','.c','.py','.js','.sh'}:
        sources=[p for p in (root/cp['pasta']).rglob('*') if p.is_file()
                 and 'build' not in p.relative_to(root/cp['pasta']).parts
                 and (p.suffix in {'.cpp','.cc','.c','.h','.hpp','.comp','.vert','.frag','.glsl'} or p.name=='CMakeLists.txt')]
        if any(p.stat().st_mtime_ns>target.stat().st_mtime_ns for p in sources):return None
    return {'passo':cp['steps'],'tipo':'grafico' if graphical else 'texto','pasta':cp['pasta'],
            'arquivo':str(target.relative_to(root)),'artefato_sha256':_file_sha(target),'fontes_sha256':stamp}


def formata(tool: str, args: dict) -> bool:
    """verificar_codigo com formatar=true reescreve os arquivos (29/10)."""
    return tool == "verificar_codigo" and (args or {}).get("formatar") is True


def record(cp: dict, tool: str, args: dict, output: str, *, ok: bool, receipt=None, comment: str = "", raiz=None) -> dict:
    cp["steps"] += 1
    full=str(output or '');limit=7000 if tool=='ler_da_oficina' else 6000
    event = {"passo": cp["steps"], "ferramenta": tool, "argumentos": args_summary(tool, args),
             "ok": bool(ok), "saida": full[:limit], "saida_chars":len(full),
             "saida_truncada":len(full)>limit, "recibo": receipt,
             "nota": str(comment or "")[:400]}
    if raiz is not None and args.get('caminho'):
        event['arquivo_sha256']=_file_sha(_inside(Path(raiz),args['caminho']))
    cp["events"] = (cp["events"] + [event])[-48:]
    if event["nota"].strip():
        # 29/10: ela concluía 'vou parar de reler' e no passo seguinte esquecia; as conclusões ficam.
        cp["memoria"] = (cp.get("memoria", []) + [{"passo": cp["steps"], "texto": event["nota"].strip()}])[-40:]
    if ok and (tool in CHANGES or formata(tool, args)):
        cp["last_change_step"] = cp["steps"]
    proof=_execution_proof(cp,raiz,tool,args,full) if ok and tool in RUNS else None
    if proof:
        cp['verified_run']=proof;cp['last_ok_run_step']=cp['steps']
    if tool in RUNS:
        if proof or construcao(tool,args):cp['last_run_step']=cp['steps']
        if construcao(tool, args):
            texto = str(output or "")
            erros = [l.strip() for l in texto.splitlines() if re.search(r"\berror\b|\berro\b", l, re.I)][:3]
            if not erros and "[stderr]" in texto:  # 29/10: 'cd: ...: No such file' ficava como erros: []
                erros = [l.strip() for l in texto.split("[stderr]", 1)[1].splitlines() if l.strip()][:2]
            exit_status=re.search(r'^\[oficina \| código (-?\d+)\]\s*$',texto,re.M)
            # 29/10: 'make 2>&1 | head' devolve código 0 com erros na saída; ok exige os dois.
            com_erro = any(re.search(r"\berror\b|\berro\b", l, re.I) for l in texto.splitlines())
            cp["ultimo_build"] = {"passo": cp["steps"], "ok": bool(exit_status and int(exit_status[1])==0) and not com_erro,
                                  "erros": erros}
    return event


def construcao(tool: str, args: dict) -> bool:
    """Execução que compila (g++/cmake/make ou linguagem cpp), para o estado do projeto."""
    if tool != "executar_na_oficina":
        return False
    texto = str((args or {}).get("codigo") or "")
    if (args or {}).get("linguagem") == "cpp":
        return True
    if any(token in texto for token in (';','||','|','`','$(','\n')):return False
    # Só o comando em si (29/10: "ls /usr/lib/cmake/..." e "grep \.cmake$" contavam como build ok).
    for comando in texto.split('&&'):
        palavras = comando.split()
        if palavras and palavras[0]=='cmake':
            if '--build' in palavras and not any(x in palavras for x in ('help','--version','--help','-n','--dry-run')):
                return True
            continue  # configuração e --version não compilam o projeto.
        if palavras and palavras[0] in COMPILADORES and not any(x in palavras for x in ('--version','--help','-E','-fsyntax-only','-n','--dry-run')):
            return True
    return False


COMPILADORES = {"cmake", "make", "ninja", "g++", "c++", "gcc", "cc", "clang", "clang++"}


SEM_COMPILAR_ALERTA = 15  # passos sem rodar nada, com código no projeto (29/10: 115 passos sem compilar)


def estado_projeto(cp: dict, raiz: Path) -> dict:
    """Fatos objetivos do projeto, mostrados a cada passo e no relatório da sessão."""
    arquivos = _arquivos(raiz, cp["pasta"])
    fontes = [a for a in arquivos if Path(a["arquivo"]).suffix in {".cpp", ".cc", ".c", ".h", ".hpp", ".comp",
                                                                   ".vert", ".frag", ".glsl", ".py"}]
    build = cp.get("ultimo_build")
    return {"arquivos_de_codigo": len(fontes), "bytes_de_codigo": sum(a.get("bytes", 0) for a in fontes),
            "ultimo_build": build or "o projeto ainda não foi compilado nenhuma vez",
            "ja_rodou_com_saida": bool(cp.get('verified_run')),
            "passos_desde_a_ultima_execucao": cp["steps"] - cp.get("last_run_step", 0)}


def relatorio_sessao(cp: dict, raiz: Path, inicio_sessao: int) -> str:
    estado = estado_projeto(cp, raiz)
    build = cp.get("ultimo_build")
    return (f"Sessão: passos {inicio_sessao + 1}–{cp['steps']}. Código: {estado['arquivos_de_codigo']} arquivo(s), "
            f"{estado['bytes_de_codigo']} bytes. Compilou: "
            + ("nunca" if not build else ("sim" if build["ok"] else "não") + f" (passo {build['passo']})")
            + f". Rodou com saída: {'sim' if estado['ja_rodou_com_saida'] else 'não'}.")


LEITURAS_SEM_MUDANCA = 2
LEITURAS_DO_ARQUIVO_SEM_MUDANCA = 4  # qualquer trecho (29/10: 6 leituras em volta da linha 162)


def releitura_excessiva(cp: dict, tool: str, args: dict, raiz=None) -> str | None:
    """Mesmo arquivo lido várias vezes sem nenhuma escrita nele no meio (29/10: 4 leituras seguidas
    do engine.cpp alternando inteiro/intervalo escapavam da guarda de chamada idêntica)."""
    if tool != "ler_da_oficina" or not isinstance(args.get("caminho"), str):
        return None
    caminho = args["caminho"].strip().lstrip("./")
    # 29/10: contar só o MESMO trecho; ler outras linhas (a do erro) é exatamente o que ela precisa.
    trecho = (args.get("inicio"), args.get("fim"))
    version=_file_sha(_inside(Path(raiz),caminho)) if raiz is not None else None
    leituras, do_arquivo, problema = 0, 0, ""
    # Só o que ainda está na visão dela (29/10: leituras de 40 passos atrás, fora dos recibos,
    # bloqueavam o engine.cpp e a recusa dizia que o conteúdo estava nos recibos).
    for e in reversed(cp["events"][-RECIBOS_NA_VISAO:]):
        argumentos = e.get("argumentos") or {}
        alvo = str(argumentos.get("caminho") or "").strip().lstrip("./")
        if e["ok"] and formata(e["ferramenta"], argumentos) and caminho.startswith(alvo):
            break  # formatado (o arquivo ou a pasta dele): as linhas mudaram
        if alvo != caminho:
            continue
        if e["ferramenta"] in CHANGES and not e["ok"]:
            break  # edição que não encontrou o trecho: reler para copiar o texto real é legítimo (29/10)
        if e["ferramenta"] in CHANGES and e["ok"]:
            # O último problema apontado ao salvar este arquivo, para ela encarar a correção.
            problema = next((l.strip() for l in e["saida"].splitlines() if ": erro:" in l), "")
            break
        if e["ferramenta"] == "ler_da_oficina" and e["ok"]:
            if raiz is not None and e.get('arquivo_sha256')!=version:
                continue  # trecho antigo/versão desconhecida não prova leitura da versão atual.
            do_arquivo += 1
            if (argumentos.get("inicio"), argumentos.get("fim")) == trecho:
                leituras += 1
    if do_arquivo >= LEITURAS_DO_ARQUIVO_SEM_MUDANCA and leituras:
        return (f"Você já leu {caminho} {do_arquivo} vezes (trechos diferentes) e ele não mudou; o conteúdo está "
                "nos recibos. " + (f"O problema apontado ao salvar foi: {problema}. " if problema else "")
                + "Corrija agora com editar_na_oficina (trecho exato → novo), ou compile/verifique.")
    if leituras < LEITURAS_SEM_MUDANCA:
        return None
    return (f"Você já leu esse mesmo trecho de {caminho} {leituras} vezes e o arquivo não mudou. "
            "Para ver as linhas de um erro, leia só esse intervalo (ler_da_oficina com inicio/fim); "
            "ou edite (editar_na_oficina), compile/rode ou verifique (verificar_codigo).")


def completion_problem(cp: dict, raiz: Path) -> str | None:
    if not _arquivos(raiz, cp["pasta"]):
        return f"Não há arquivos em {cp['pasta']}; nada para entregar ainda."
    proof=cp.get('verified_run')
    if not proof:
        return ("Ainda não houve execução do programa com saída visível (compilar sem saída não basta; "
                "rode o executável ou abra a janela).")
    if cp.get('require_graphical_run') and proof.get('tipo')!='grafico':
        return 'Este projeto exige janela/captura real; execução textual não comprova esse requisito.'
    target=_inside(raiz,proof.get('arquivo',''))
    if (proof.get('pasta')!=cp['pasta'] or _source_stamp(raiz,cp['pasta'])!=proof.get('fontes_sha256')
            or _file_sha(target)!=proof.get('artefato_sha256') or cp['last_change_step']>proof['passo']):
        return ("Os arquivos mudaram depois da última execução bem-sucedida; compile E rode o programa "
                "de novo (com saída visível) antes de concluir.")
    return None


def finish_task(task, cp) -> None:
    """Fecha a tarefa: todas as etapas pendentes com o relatório dela (o projeto cobre o objetivo inteiro)."""
    relatorio = json.dumps(cp.get("concluido") or {}, ensure_ascii=False)[:2000]
    with bd.conexao(escrita=True) as db:
        row = db.execute("SELECT objetivo,status FROM conversation_tasks WHERE id=?", (task.id,)).fetchone()
        if not row or _digest(row["objetivo"]) != cp["goal_hash"]:
            raise ValueError("PROJECT_TASK_CHANGED")
        db.execute("UPDATE conversation_task_steps SET status='done',resultado=? WHERE task_id=? AND status='pending'",
                   (relatorio, task.id))
        db.execute("UPDATE conversation_tasks SET status='completed',updated_at=?,ultima_acao=?,ultimo_resultado=? WHERE id=?",
                   (bd.agora(), "concluir_projeto", relatorio, task.id))


MEMORIA_NA_VISAO = 12


def view(cp: dict, objetivo: str, raiz: Path, limite: int, raciocinio_anterior: str = "") -> dict:
    recibos = []
    janela = cp["events"][-RECIBOS_NA_VISAO:]
    erro = primeiro_erro(cp, raiz)
    codigo = codigo_do_projeto(raiz, cp["pasta"], {erro["arquivo"]: erro["linha"]} if erro else None)
    visiveis = {a for a, t in codigo.items() if not t.startswith("(")}
    # 29/10: arquivo de 5,4 mil caracteres aparecia cortado em 2.500 e ela nunca via as linhas
    # do erro; a leitura mais recente aparece quase inteira, as antigas ficam resumidas.
    ultima_leitura = next((e["passo"] for e in reversed(janela) if e["ferramenta"] == "ler_da_oficina" and e["ok"]), None)
    for e in janela:
        lido = str((e.get("argumentos") or {}).get("caminho", "")).strip().lstrip("./")
        if e["ferramenta"] == "ler_da_oficina" and e["ok"] and lido in visiveis:
            # 29/10: o recibo cortado em 300 parecia leitura falha e ela relia; dizer onde está.
            recibos.append({**e, "saida": f"O conteúdo ATUAL de {lido} está completo e numerado em "
                                          f"codigo_do_projeto[\"{lido}\"]; não precisa ler de novo."})
            continue
        if e["passo"] == ultima_leitura:
            limite_saida = 7000
        elif e["ferramenta"] == "ler_da_oficina" and e["ok"]:
            limite_saida = 1200
        else:
            limite_saida = (2500 if not e["ok"] or e["ferramenta"] in RUNS | {"fetch_page", "web_search",
                                                                              "verificar_codigo"} else 900)
            if e["passo"] < janela[-1]["passo"] - 1:
                limite_saida = min(limite_saida, 900)  # antigos resumidos; primeiro_erro já traz o diagnóstico
        legacy=('saida_chars' not in e and len(e['saida'])==6000)
        cut=bool(e.get('saida_truncada') or len(e['saida'])>limite_saida or legacy)
        recibos.append({**e,'saida_truncada':cut, "saida": e["saida"][:limite_saida] + ("…[cortado]" if cut else "")})
    alerta = []
    estado = estado_projeto(cp, raiz)
    if estado["arquivos_de_codigo"] and estado["passos_desde_a_ultima_execucao"] >= SEM_COMPILAR_ALERTA:
        alerta.append(f"Faz {estado['passos_desde_a_ultima_execucao']} passos que você não compila nem roda nada. "
                      "Compile o projeto inteiro (por exemplo com CMake) para ver os erros reais; "
                      "avisos não impedem compilar.")
    if cp["last_change_step"] > cp["last_ok_run_step"] >= 0:
        alerta.append("Arquivos mudaram depois da última execução bem-sucedida.")
    if cp.get("feedback"):
        alerta.append(cp["feedback"])
    if erro:
        alerta.append("Há um erro em primeiro_erro. Antes de agir, escreva no texto da resposta qual você acha "
                      "que é a causa dele (olhe a mensagem completa e de onde o arquivo foi incluído).")
    # Checkpoint anterior à memória: começa pelas notas que ela já deixou nos recibos.
    notas = cp.get("memoria") or [{"passo": e["passo"], "texto": e["nota"].strip()}
                                  for e in cp["events"] if (e.get("nota") or "").strip()]
    memoria = [f"passo {m['passo']}: {m['texto'][:300]}" for m in notas[-MEMORIA_NA_VISAO:]]
    # A nota mais recente dos dois últimos passos (metade dos passos dela vem sem nota).
    intermediario = avisos_do_intermediario(cp)
    ultima_nota = next((e.get("nota") for e in reversed(cp["events"][-2:]) if (e.get("nota") or "").strip()), "")
    adiantado = pre_busca(cp, raiz, ultima_nota + "\n" + raciocinio_anterior[-1200:], codigo)
    # Ordem (29/10): o estável primeiro, o que muda a cada passo por último. O Ollama reaproveita o
    # prefixo já lido (medido: 16,5 mil tokens em 29 s sem cache, ~1 s com) e o modelo atende mais
    # ao fim do prompt, onde ficam o diário, o raciocínio anterior, o erro e os alertas.
    return {"projeto_atual": {
        "objetivo": objetivo, "sua_pasta": cp["pasta"], "meu_plano": cp.get("plano"),
        "arquivos": _arquivos(raiz, cp["pasta"]), "codigo_do_projeto": codigo,
        "ultimos_recibos": recibos, "estado_do_projeto": estado, "primeiro_erro": erro,
        **({"resposta_a_sua_pergunta": cp["resposta_humana"]} if cp.get("resposta_humana")
           and cp["steps"] - cp["resposta_humana"]["passo"] < RECIBOS_NA_VISAO else {}),
        **({"mensagem_da_pessoa": cp["mensagem_humana"]} if cp.get("mensagem_humana")
           and cp["steps"] - cp["mensagem_humana"]["passo"] < RECIBOS_NA_VISAO else {}),
        "minhas_anotacoes": memoria,
        **({"meu_raciocinio_no_passo_anterior": raciocinio_anterior[-1200:]} if raciocinio_anterior else {}),
        **({"ja_buscado_para_voce": adiantado} if adiantado else {}),
        **({"intermediario": intermediario} if intermediario else {}),
        "alertas": alerta, "passo": cp["steps"], "passos_nesta_sessao_restantes": limite}}
