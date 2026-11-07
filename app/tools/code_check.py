"""Problemas do código da oficina, como o painel do VS Code (pedido humano 29/10).

Compilador (g++ -Wall -Wextra), análise estática (clang-tidy), estilo
(clang-format), shaders GLSL (glslangValidator) e Python (ruff). Nada é
executado: só leitura e análise, dentro do mesmo isolamento da oficina — um
`#include` de caminho da máquina não pode trazer arquivos alheios na mensagem.
Os binários do LLVM/ruff ficam em compartilhado/ambientes/ferramentas-codigo
(fora do Git), montados só para leitura.
"""
import re
import shutil
import subprocess
from pathlib import Path

import config
from tools import workspace

FERRAMENTAS = Path(config.RAIZ) / "compartilhado" / "ambientes" / "ferramentas-codigo"
_SITE = FERRAMENTAS / "lib" / "python3.12" / "site-packages"
CLANG_TIDY = _SITE / "clang_tidy" / "data" / "bin" / "clang-tidy"
CLANG_FORMAT = _SITE / "clang_format" / "data" / "bin" / "clang-format"
RUFF = FERRAMENTAS / "bin" / "ruff"
FONTES_CPP = {".cpp", ".cc", ".cxx", ".c"}
CABECALHOS = {".h", ".hpp", ".hh"}
SHADERS = {".comp", ".vert", ".frag", ".geom", ".tesc", ".tese"}
IGNORAR = {"build", "CMakeFiles", "__pycache__", ".git", "venv"}
CHECKS_TIDY = ("-*,bugprone-*,-bugprone-easily-swappable-parameters,performance-*,"
               "modernize-use-nullptr,readability-misleading-indentation,clang-analyzer-*")
ESTILO_PADRAO = "{BasedOnStyle: LLVM, IndentWidth: 4, ColumnLimit: 110}"
MAX_ARQUIVOS = 40
MAX_PROBLEMAS = 60
_LINHA_GCC = re.compile(r"^(?P<arq>[^:\n]+):(?P<l>\d+):(?P<c>\d+): (?P<sev>fatal error|error|warning|note): (?P<msg>.*)$")
_LINHA_GLSL = re.compile(r"^(?P<sev>ERROR|WARNING): (?:\d+):(?P<l>\d+): (?P<msg>.*)$")
_LINHA_RUFF = re.compile(r"^(?P<arq>[^:\n]+):(?P<l>\d+):(?P<c>\d+): (?P<msg>.*)$")
_cflags_cache = None


def _cflags() -> list:
    """Includes das bibliotecas gráficas instaladas (GLFW/GLEW/GLM/GL)."""
    global _cflags_cache
    if _cflags_cache is None:
        try:
            saida = subprocess.run(["pkg-config", "--cflags", "glfw3", "glew", "glm", "gl"],
                                   capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            saida = ""
        _cflags_cache = saida.split()
    return list(_cflags_cache)


def _rodar(argv: list, cwd: Path, timeout: int = 60) -> str:
    """Executa um analisador no isolamento da oficina (sem rede), devolve stdout+stderr."""
    extras = [str(FERRAMENTAS)] if FERRAMENTAS.is_dir() else []
    try:
        chamada = workspace._montar_chamada(argv, cwd, sem_rede=True, somente_leitura_extra=extras)
        r = subprocess.run(chamada, capture_output=True, text=True, errors="replace", timeout=timeout,
                           cwd=str(cwd), env=workspace._ambiente_execucao(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "__TIMEOUT__"
    except (OSError, ValueError, PermissionError) as exc:
        return f"__ERRO__ {exc}"
    return (r.stdout or "") + (r.stderr or "")


def _relativo(caminho: str) -> str:
    """Caminho do sandbox (/workspace/...) ou absoluto da oficina → relativo à oficina."""
    texto = caminho.strip()
    for raiz in (str(workspace._MONTAGEM_OFICINA) + "/", str(workspace.OFICINA.absolute()) + "/"):
        if texto.startswith(raiz):
            return texto[len(raiz):]
    return texto


def _no_sandbox(arquivo: Path) -> str:
    return str(workspace._MONTAGEM_OFICINA / arquivo.absolute().relative_to(workspace.OFICINA.absolute()))


def _arquivos(alvo: Path) -> list:
    if alvo.is_file():
        return [alvo]
    encontrados = []
    for item in sorted(alvo.rglob("*")):
        if any(p in IGNORAR for p in item.relative_to(alvo).parts):
            continue
        if item.is_file() and item.suffix in FONTES_CPP | CABECALHOS | SHADERS | {".py"}:
            encontrados.append(item)
        if len(encontrados) >= MAX_ARQUIVOS:
            break
    return encontrados


def _includes(arquivo: Path, raiz_projeto: Path) -> list:
    pastas = [arquivo.parent, raiz_projeto, raiz_projeto / "include", raiz_projeto / "src"]
    args = []
    for pasta in dict.fromkeys(pastas):
        if pasta.is_dir():
            args += ["-I", _no_sandbox(pasta)]
    return args


def _gcc(arquivo: Path, raiz_projeto: Path) -> list:
    saida = _rodar(["g++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-Wpedantic", "-Wshadow",
                    *_includes(arquivo, raiz_projeto), *_cflags(), _no_sandbox(arquivo)], arquivo.parent)
    return _problemas_gcc(saida, "g++")


def _tidy(arquivo: Path, raiz_projeto: Path) -> list:
    if not CLANG_TIDY.is_file():
        return []
    saida = _rodar([str(CLANG_TIDY), _no_sandbox(arquivo), "--quiet", f"-checks={CHECKS_TIDY}", "--",
                    "-std=c++17", *_includes(arquivo, raiz_projeto), *_cflags()], arquivo.parent, timeout=90)
    # Erros de compilação já aparecem pelo g++; aqui só os avisos da análise.
    return [p for p in _problemas_gcc(saida, "clang-tidy") if p["sev"] == "aviso"]


def _problemas_gcc(saida: str, ferramenta: str) -> list:
    if saida.startswith("__"):
        return [{"arq": "", "l": 0, "c": 0, "sev": "aviso", "msg": f"{ferramenta} não terminou ({saida[:80]})",
                 "ferramenta": ferramenta}]
    problemas, incluido = [], ""
    for linha in saida.splitlines():
        # 29/10: 'redefinition' apontava só engine.h:6 e ela relia o .h; a causa (main.cpp:1 e :72
        # incluem engine.h duas vezes) estava nas linhas 'In file included from' e na nota descartadas.
        inc = re.match(r"^(?:In file included from|\s+from) (?P<arq>[^:]+):(?P<l>\d+)", linha)
        if inc:
            incluido = f"{_relativo(inc['arq'])}:{inc['l']}"
            continue
        m = _LINHA_GCC.match(linha.strip())
        if not m:
            continue
        origem, incluido = (f" (incluído de {incluido})" if incluido else ""), ""
        if m["sev"] == "note":
            if problemas and "previous definition" in m["msg"]:
                problemas[-1]["msg"] += f" — definição anterior: {_relativo(m['arq'])}:{m['l']}{origem}"
            continue
        problemas.append({"arq": _relativo(m["arq"]), "l": int(m["l"]), "c": int(m["c"]),
                          "sev": "erro" if "error" in m["sev"] else "aviso", "msg": m["msg"].strip() + origem,
                          "ferramenta": ferramenta})
    return problemas


def _glsl(arquivo: Path) -> list:
    if not shutil.which("glslangValidator"):
        return []
    saida = _rodar(["glslangValidator", _no_sandbox(arquivo)], arquivo.parent)
    rel = _relativo(str(arquivo.absolute()))
    problemas = []
    for linha in saida.splitlines():
        m = _LINHA_GLSL.match(linha.strip())
        if m and "compilation errors" not in m["msg"]:
            problemas.append({"arq": rel, "l": int(m["l"]), "c": 0,
                              "sev": "erro" if m["sev"] == "ERROR" else "aviso",
                              "msg": m["msg"].strip(" '"), "ferramenta": "glslang"})
    return problemas


def _python(arquivo: Path) -> list:
    if not RUFF.is_file():
        return []
    # Da raiz da oficina, o ruff já devolve 'projetos/x/arquivo.py'.
    saida = _rodar([str(RUFF), "check", "--output-format", "concise", "--no-cache", _no_sandbox(arquivo)],
                   workspace.OFICINA)
    problemas = []
    for linha in saida.splitlines():
        m = _LINHA_RUFF.match(linha.strip())
        if m:
            erro = bool(re.match(r"(?:SyntaxError|E9|F82)", m["msg"]))
            problemas.append({"arq": _relativo(m["arq"]), "l": int(m["l"]), "c": int(m["c"]),
                              "sev": "erro" if erro else "aviso", "msg": m["msg"].strip(), "ferramenta": "ruff"})
    return problemas


def _estilo(arquivo: Path, raiz_projeto: Path, formatar: bool) -> tuple[int, str]:
    """(trechos fora do estilo, nota). Com formatar=True, aplica o estilo no arquivo."""
    if not CLANG_FORMAT.is_file():
        return 0, ""
    estilo = "file" if (raiz_projeto / ".clang-format").is_file() else ESTILO_PADRAO
    if formatar:
        _rodar([str(CLANG_FORMAT), "-i", f"--style={estilo}", _no_sandbox(arquivo)], arquivo.parent)
        return 0, "formatado"
    saida = _rodar([str(CLANG_FORMAT), "--dry-run", f"--style={estilo}", _no_sandbox(arquivo)], arquivo.parent)
    linhas = [int(m[1]) for m in re.finditer(r":(\d+):\d+: warning:", saida)]
    return len(linhas), (f"primeira na linha {min(linhas)}" if linhas else "")


def problemas(alvo: Path, *, completo: bool = True, formatar: bool = False) -> dict:
    raiz_projeto = alvo if alvo.is_dir() else alvo.parent
    partes = raiz_projeto.absolute().relative_to(workspace.OFICINA.absolute()).parts
    if len(partes) >= 2 and partes[0] == "projetos":  # inclui a raiz do projeto, mesmo vendo um arquivo de src/
        raiz_projeto = workspace.OFICINA / partes[0] / partes[1]
    lista, estilo = [], {}
    for arquivo in _arquivos(alvo):
        if arquivo.suffix in FONTES_CPP:
            lista += _gcc(arquivo, raiz_projeto)
            if completo:
                lista += _tidy(arquivo, raiz_projeto)
        elif arquivo.suffix in SHADERS:
            lista += _glsl(arquivo)
        elif arquivo.suffix == ".py":
            lista += _python(arquivo)
        if completo and arquivo.suffix in FONTES_CPP | CABECALHOS | SHADERS:
            n, nota = _estilo(arquivo, raiz_projeto, formatar)
            if n or nota == "formatado":
                estilo[_relativo(str(arquivo.absolute()))] = nota if nota == "formatado" else f"{n} trecho(s); {nota}"
    proprio = ""
    if alvo.is_file() and alvo.suffix in CABECALHOS:
        # 29/10: verificar engine.h sozinho dizia '0 erro(s)' com 10 redefinições vindas dele;
        # um .h não compila sozinho, então vale o que os .cpp que o incluem dizem.
        proprio = _relativo(str(alvo.absolute()))
        for fonte in _quem_inclui(alvo):
            lista += _gcc(fonte, raiz_projeto)
    vistos, unicos = set(), []
    # Os do código dela primeiro (29/10: 23 erros, os 8 mostrados eram de /usr/include/.../chrono.h
    # e o main.cpp:78 'glfwInit not declared' ficava escondido).
    for p in sorted(lista, key=lambda p: (p["sev"] != "erro", p["arq"].startswith("/"), p["arq"] != proprio,
                                          p["arq"], p["l"], p["c"])):
        chave = (p["arq"], p["l"], p["c"], p["msg"])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(p)
    return {"problemas": unicos, "estilo": estilo}


def relatorio(resultado: dict, titulo: str) -> str:
    probs = resultado["problemas"]
    erros = sum(p["sev"] == "erro" for p in probs)
    linhas = [f"{p['arq']}:{p['l']}:{p['c']}: {p['sev']}: {p['msg']} [{p['ferramenta']}]" for p in probs[:MAX_PROBLEMAS]]
    if len(probs) > MAX_PROBLEMAS:
        linhas.append(f"... e mais {len(probs) - MAX_PROBLEMAS} problema(s).")
    fora = {a: n for a, n in resultado["estilo"].items() if n != "formatado"}
    for arq, nota in resultado["estilo"].items():
        # 29/10: "formatado" aparecia como problema de estilo e ela formatava de novo.
        linhas.append(f"{arq}: estilo: {'formatado agora (já está no padrão)' if nota == 'formatado' else nota} [clang-format]")
    cabecalho = (f"Problemas em {titulo}: {erros} erro(s), {len(probs) - erros} aviso(s)"
                 + (f", estilo fora do padrão em {len(fora)} arquivo(s)" if fora else "") + ".")
    return cabecalho + ("\n" + "\n".join(linhas) if linhas else "\nNenhum problema encontrado.")


def verificar_codigo(caminho: str, formatar: bool = False) -> str:
    """Ferramenta: problemas de um arquivo ou pasta da oficina (compilador, análise, estilo, shaders, Python)."""
    try:
        alvo = workspace.caminho_seguro(caminho or "")
    except ValueError as e:
        return f"Erro: {e}"
    if not alvo.exists():
        return f"Erro: '{caminho}' não existe na oficina."
    if not _arquivos(alvo):
        return f"Nenhum arquivo de código (C/C++, shader GLSL ou Python) em '{caminho}'."
    return relatorio(problemas(alvo, formatar=formatar), str(alvo.relative_to(workspace.OFICINA)) or ".")


def _quem_inclui(cabecalho: Path) -> list:
    """Fontes do projeto que fazem #include "<este cabeçalho>" (um .h não compila sozinho)."""
    partes = cabecalho.parent.absolute().relative_to(workspace.OFICINA.absolute()).parts
    raiz = workspace.OFICINA / partes[0] / partes[1] if len(partes) >= 2 and partes[0] == "projetos" else cabecalho.parent
    padrao = re.compile(r'#\s*include\s*"(?:[^"]*/)?' + re.escape(cabecalho.name) + '"')
    fontes = []
    for f in _arquivos(raiz):
        try:
            if f.suffix in FONTES_CPP and padrao.search(f.read_text(encoding="utf-8", errors="replace")):
                fontes.append(f)
        except OSError:
            continue
    return fontes


def resumo_ao_salvar(alvo: Path) -> str:
    """Problemas imediatos de um arquivo recém-salvo, como o sublinhado do editor ('' se não é código)."""
    if alvo.suffix not in FONTES_CPP | SHADERS | CABECALHOS | {".py"}:
        return ""
    try:
        if alvo.suffix in CABECALHOS:
            # 29/10: salvar engine.h não mostrava nada; ela mexia no cabeçalho às cegas (32→110 erros).
            if not _quem_inclui(alvo):
                return "\nVerificação ao salvar: nenhum .cpp do projeto inclui este cabeçalho ainda."
        resultado = problemas(alvo, completo=False)
    except Exception as exc:  # noqa: BLE001 — a verificação nunca desfaz a escrita
        return f"\n(verificação automática indisponível: {type(exc).__name__})"
    probs = resultado["problemas"]
    if not probs:
        return "\nVerificação ao salvar: nenhum erro ou aviso do compilador/validador."
    erros = sum(p["sev"] == "erro" for p in probs)
    amostra = [f"  {p['arq']}:{p['l']}:{p['c']}: {p['sev']}: {p['msg']}" for p in probs[:8]]
    return (f"\nVerificação ao salvar: {erros} erro(s), {len(probs) - erros} aviso(s)"
            + (" (primeiros 8)" if len(probs) > 8 else "") + ":\n" + "\n".join(amostra))
