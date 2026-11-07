"""
Forja de ferramentas — a Hoshino criando ferramentas para si mesma.

Uma ferramenta dela vive em `workspace/ferramentas/<nome>/`:
    ferramenta.py    -> precisa expor `def executar(**kwargs) -> str`
    manifesto.json   -> nome, descrição, parâmetros, estado, histórico
    versoes/         -> versões anteriores (nada é sobrescrito sem cópia)

Regras que tornam isso seguro e útil de verdade:
  * o código é validado com `ast.parse` antes de existir como ferramenta;
  * passa por um teste de fumaça real antes de ser ativada — se quebrar na
    importação ou na primeira chamada, nasce desativada com o traceback junto;
  * roda SEMPRE em subprocesso isolado na oficina, nunca dentro do processo da
    Hoshino: uma ferramenta ruim não derruba a Hoshino nem vaza para o sistema;
  * o schema para o LLM é gerado a partir do manifesto, então ferramentas novas
    aparecem para ela na conversa seguinte sem editar nenhum código do projeto.
"""
import ast
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from tools.workspace import (OFICINA, _executar, caminho_seguro, preparar_oficina,
                             python_da_oficina)

DIR_FERRAMENTAS = OFICINA / "ferramentas"
NOME_VALIDO = re.compile(r"^[a-z][a-z0-9_]{2,39}$")

# Nomes nativos que não podem ser sequestrados por uma ferramenta criada.
# Esta lista era fixa e desandou: tinha 32 nomes contra as 76 ferramentas que o
# dispatch realmente registra hoje — 45 nativas ficaram de fora e uma
# ("usar_ferramenta") já nem existia mais. O despacho em si nunca foi enganado
# (ferramenta criada só é chamada pelo prefixo `propria_`), mas deixar a Hoshino
# criar uma `discord_enviar` própria produz duas coisas com o mesmo nome no
# manual dela, que é justamente o tipo de confusão que a forja deveria evitar.
# Agora sai do dispatch, então não tem como divergir de novo.
RESERVADOS_EXTRA = {"usar_ferramenta"}   # nomes históricos, mantidos por garantia


def _reservados() -> set:
    """Import tardio: core.dispatch importa este módulo, então importar lá de
    cima daria ciclo. Aqui dentro, só roda quando alguém cria uma ferramenta."""
    nomes = set(RESERVADOS_EXTRA)
    try:
        from core import dispatch
        nomes |= {e["function"]["name"] for e in dispatch.ESQUEMAS}
    except Exception:  # noqa: BLE001
        pass   # sem o dispatch, NOME_VALIDO e o prefixo `propria_` seguram
    return nomes

MODELO_RUNNER = '''"""Executor de ferramenta da oficina (gerado automaticamente — não editar)."""
import importlib.util
import json
import sys


def main():
    caminho, argumentos = sys.argv[1], json.loads(sys.argv[2])
    spec = importlib.util.spec_from_file_location("ferramenta_hoshino", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    if not hasattr(modulo, "executar"):
        print(json.dumps({"ok": False, "erro": "a ferramenta não define executar()"}))
        return
    try:
        resultado = modulo.executar(**argumentos)
    except TypeError as e:
        print(json.dumps({"ok": False, "erro": f"argumentos incompatíveis: {e}"}))
        return
    print(json.dumps({"ok": True, "resultado": str(resultado)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


def _preparar():
    preparar_oficina()
    DIR_FERRAMENTAS.mkdir(parents=True, exist_ok=True)
    runner = OFICINA / "_runner.py"
    if not runner.exists() or runner.read_text(encoding="utf-8") != MODELO_RUNNER:
        runner.write_text(MODELO_RUNNER, encoding="utf-8")
    return runner


def _manifesto(nome: str):
    arq = DIR_FERRAMENTAS / nome / "manifesto.json"
    if not arq.exists():
        return None
    return json.loads(arq.read_text(encoding="utf-8"))


def _gravar_manifesto(nome: str, dados: dict):
    (DIR_FERRAMENTAS / nome / "manifesto.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def _validar_codigo(codigo: str):
    """Devolve (ok, mensagem). Só checagem estática — o teste de fumaça vem depois."""
    if not (codigo or "").strip():
        return False, "código vazio"
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as e:
        return False, f"erro de sintaxe na linha {e.lineno}: {e.msg}"
    tem_executar = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and n.name == "executar" for n in arvore.body)
    if not tem_executar:
        return False, ("a ferramenta precisa definir uma função de nível superior "
                       "chamada `executar` (ex: `def executar(texto): ...`)")
    return True, ""


def criar_ferramenta(nome: str, descricao: str, codigo: str, parametros: dict = None,
                     obrigatorios: list = None, teste: dict = None) -> str:
    """Cria (ou atualiza) uma ferramenta própria da Hoshino.

    `parametros` é um dicionário no formato JSON Schema, ex:
        {"texto": {"type": "string", "description": "o que converter"}}
    `teste` são argumentos usados no teste de fumaça, ex: {"texto": "abc"}.
    """
    _preparar()
    nome = (nome or "").strip().lower()
    if not NOME_VALIDO.match(nome):
        return ("Erro: nome inválido. Use minúsculas, números e _ (3 a 40 caracteres), "
                "começando por letra. Ex: converter_moeda")
    if nome in _reservados():
        return f"Erro: '{nome}' é o nome de uma ferramenta nativa. Escolha outro."
    if not (descricao or "").strip():
        return "Erro: descreva para que serve a ferramenta — é isso que você vai ler depois."

    ok, msg = _validar_codigo(codigo)
    if not ok:
        return f"Ferramenta não criada: {msg}"

    pasta = DIR_FERRAMENTAS / nome
    existente = _manifesto(nome)
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / "ferramenta.py"

    if alvo.exists():  # versiona antes de sobrescrever
        (pasta / "versoes").mkdir(exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(alvo, pasta / "versoes" / f"ferramenta_{carimbo}.py")
    alvo.write_text(codigo, encoding="utf-8")

    manifesto = {
        "nome": nome,
        "descricao": descricao.strip(),
        "parametros": parametros or {},
        "obrigatorios": obrigatorios or [],
        "criada_em": (existente or {}).get("criada_em", datetime.now().isoformat()),
        "atualizada_em": datetime.now().isoformat(),
        "versao": (existente or {}).get("versao", 0) + 1,
        "ativa": False,
        "usos": (existente or {}).get("usos", 0),
        "falhas": (existente or {}).get("falhas", 0),
        "ultimo_erro": None,
    }
    _gravar_manifesto(nome, manifesto)

    # Teste de fumaça: nasce desativada e só é liberada se rodar de verdade.
    resultado = _rodar(nome, teste or {}, timeout=20)
    if not resultado.get("ok"):
        manifesto["ultimo_erro"] = resultado.get("erro", "")[:1500]
        _gravar_manifesto(nome, manifesto)
        return (f"Ferramenta '{nome}' salva mas NÃO ativada: falhou no teste.\n"
                f"{resultado.get('erro', '')[:1200]}\n"
                f"Conserte o código e chame criar_ferramenta de novo.")

    manifesto["ativa"] = True
    _gravar_manifesto(nome, manifesto)
    return (f"Ferramenta '{nome}' criada, testada e ativada (v{manifesto['versao']}).\n"
            f"Teste devolveu: {str(resultado.get('resultado'))[:400]}\n"
            f"Ela fica disponível para você a partir da próxima mensagem.")


def _rodar(nome: str, argumentos: dict, timeout: int = 30) -> dict:
    runner = _preparar()
    alvo = DIR_FERRAMENTAS / nome / "ferramenta.py"
    if not alvo.exists():
        return {"ok": False, "erro": f"ferramenta '{nome}' não existe"}
    argv = [python_da_oficina(), str(runner), str(alvo),
            json.dumps(argumentos or {}, ensure_ascii=False)]
    bruto = _executar(argv, OFICINA, timeout=timeout, sem_rede=False)
    for linha in reversed(bruto.strip().splitlines()):
        linha = linha.strip()
        if linha.startswith("{"):
            try:
                return json.loads(linha)
            except json.JSONDecodeError:
                continue
    return {"ok": False, "erro": bruto}


def usar_ferramenta(nome: str, argumentos: dict = None, timeout: int = 30) -> str:
    """Executa uma ferramenta que a Hoshino mesma criou."""
    manifesto = _manifesto(nome)
    if not manifesto:
        disponiveis = ", ".join(n["nome"] for n in _todas()) or "nenhuma"
        return (f"Não existe ferramenta própria chamada '{nome}'. "
                f"Criadas até agora: {disponiveis}.")
    if not manifesto.get("ativa"):
        return (f"A ferramenta '{nome}' está desativada porque falhou no último teste: "
                f"{manifesto.get('ultimo_erro', 'sem detalhe')}")
    faltando = [p for p in manifesto.get("obrigatorios", [])
                if p not in (argumentos or {})]
    if faltando:
        return f"Faltam argumentos obrigatórios para '{nome}': {', '.join(faltando)}"

    resultado = _rodar(nome, argumentos or {}, timeout=timeout)
    manifesto["usos"] = manifesto.get("usos", 0) + 1
    if not resultado.get("ok"):
        manifesto["falhas"] = manifesto.get("falhas", 0) + 1
        manifesto["ultimo_erro"] = str(resultado.get("erro", ""))[:1500]
        if manifesto["falhas"] >= 3 and manifesto["falhas"] > manifesto["usos"] // 2:
            manifesto["ativa"] = False
        _gravar_manifesto(nome, manifesto)
        return (f"A ferramenta '{nome}' falhou:\n{resultado.get('erro', '')[:1200]}\n"
                f"{'Desativei ela até você consertar.' if not manifesto['ativa'] else ''}")
    _gravar_manifesto(nome, manifesto)
    return str(resultado.get("resultado", ""))


def _todas() -> list:
    _preparar()
    saida = []
    for pasta in sorted(DIR_FERRAMENTAS.iterdir()):
        if pasta.is_dir():
            man = _manifesto(pasta.name)
            if man:
                saida.append(man)
    return saida


def listar_ferramentas() -> str:
    """Lista as ferramentas que a Hoshino criou para si mesma."""
    todas = _todas()
    if not todas:
        return ("Você ainda não criou nenhuma ferramenta própria. "
                "Use criar_ferramenta(nome, descricao, codigo) quando precisar de algo "
                "que as ferramentas nativas não fazem.")
    linhas = []
    for m in todas:
        estado = "ativa" if m.get("ativa") else "DESATIVADA"
        linhas.append(f"[{estado}] {m['nome']} (v{m['versao']}, {m.get('usos', 0)} usos) "
                      f"— {m['descricao']}")
    return "Ferramentas próprias:\n" + "\n".join(linhas)


def ler_ferramenta(nome: str) -> str:
    """Mostra o código de uma ferramenta criada, para revisar ou corrigir."""
    alvo = DIR_FERRAMENTAS / nome / "ferramenta.py"
    if not alvo.exists():
        return f"Não existe ferramenta '{nome}'."
    man = _manifesto(nome) or {}
    return (f"# {nome} v{man.get('versao')} — {'ativa' if man.get('ativa') else 'desativada'}\n"
            f"# {man.get('descricao', '')}\n\n"
            f"{alvo.read_text(encoding='utf-8')[:6000]}")


def remover_ferramenta(nome: str) -> str:
    """Desativa e arquiva uma ferramenta criada (não some com o código)."""
    pasta = DIR_FERRAMENTAS / nome
    if not pasta.exists():
        return f"Não existe ferramenta '{nome}'."
    lixeira = OFICINA / "ferramentas_arquivadas"
    lixeira.mkdir(exist_ok=True)
    destino = lixeira / f"{nome}_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.move(str(pasta), str(destino))
    return f"Ferramenta '{nome}' arquivada em {destino.relative_to(OFICINA)}."


def esquemas_para_llm(contexto: str = "", limite: int = 8) -> list:
    """Expõe só as ferramentas próprias plausíveis para o turno atual.

    Ferramentas próprias crescem com o uso; enviar todas ao modelo em todo turno
    recria exatamente o problema de sobrecarga que o dispatch evita para as nativas.
    """
    ativas = [m for m in _todas() if m.get("ativa")]
    if not ativas:
        return []
    t = normalizar_contexto(contexto)
    tokens = set(re.findall(r"[a-z0-9_]{3,}", t))

    def score(m):
        nome = str(m.get("nome", "")).casefold()
        desc = str(m.get("descricao", "")).casefold()
        palavras = set(re.findall(r"[a-z0-9_]{3,}", normalizar_contexto(nome + " " + desc)))
        pontos = 0
        if nome in t:
            pontos += 100
        pontos += 4 * len(tokens & palavras)
        if "ferramenta" in tokens or "capacidade" in tokens:
            pontos += 2
        return pontos

    ativas.sort(key=lambda m: (-score(m), str(m.get("nome", ""))))
    # Em contexto explícito de ferramenta, as primeiras 8 são úteis; em contexto
    # irrelevante, só as que realmente têm alguma sobreposição entram.
    scored = [(score(m), m) for m in ativas]
    selecionadas = [m for pts, m in scored if pts > 0][:limite]
    if not selecionadas:
        return []
    return [{
        "type": "function",
        "function": {
            "name": f"propria_{m['nome']}",
            "description": f"[ferramenta que você mesma criou] {m['descricao']}",
            "parameters": {
                "type": "object",
                "properties": m.get("parametros", {}),
                "required": m.get("obrigatorios", []),
            },
        },
    } for m in selecionadas]


def normalizar_contexto(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in t if not unicodedata.combining(c))
