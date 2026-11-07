"""
Oficina — o ambiente isolado e próprio da Hoshino para escrever e rodar código.

Antes, `tools/sandbox.py` jogava o código num `runtime/sandbox/script_xxxx.py`
com nome aleatório, rodava com o python do sistema, sem limite de memória, sem
diretório de trabalho e com timeout de 10s. Não era sandbox e não era espaço de
trabalho: era um paredão de scripts descartáveis.

A oficina é diferente:
  * mora em `workspace/`, com estrutura estável — projetos/, ferramentas/,
    dados/, tmp/, home/ e um venv só dela;
  * tem isolamento real quando o sistema oferece (`bwrap`, do bubblewrap) e,
    quando não oferece, limites de recurso via rlimit (CPU, memória, tamanho de
    arquivo, número de processos);
  * caminho é confinado: qualquer `../` que tente sair de workspace/ é recusado;
  * o trabalho PERSISTE. Ela pode criar um projeto hoje, continuar amanhã, e
    instalar dependências sem sujar o Python do sistema nem o venv do projeto.
"""
import json
import os
import re
import resource
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import (ARQUIVO_MAX_OFICINA_MB, CPU_MAX_OFICINA_SEG,
                    LIMITE_SAIDA_CHARS, MEMORIA_MAX_OFICINA_MB, OFICINA_DIR,
                    TIMEOUT_OFICINA_PADRAO)

OFICINA = Path(OFICINA_DIR)
SUBPASTAS = ("projetos", "ferramentas", "dados", "tmp", "home", "logs", "capturas")
EXTENSOES = {"python": ".py", "bash": ".sh", "node": ".js", "texto": ".txt", "cpp": ".cpp"}
_MONTAGEM_OFICINA = Path("/workspace")
# Execução gráfica (pedido humano 29/10, desafio OpenGL): só nesta ferramenta a
# oficina vê a GPU (/dev/dri) e o display X11, sob lease da GPU e por tempo limitado.
GRAFICO_VRAM_MB = 768
GRAFICO_SEGUNDOS_MAX = 60
_XAUTH_NO_SANDBOX = "/run/oficina-xauthority"


# ---------------------------------------------------------------------------
# Estrutura e caminhos
# ---------------------------------------------------------------------------

def preparar_oficina() -> Path:
    """Cria a estrutura da oficina se ainda não existir. Idempotente."""
    for sub in SUBPASTAS:
        (OFICINA / sub).mkdir(parents=True, exist_ok=True)
    leiame = OFICINA / "LEIA-ME.md"
    if not leiame.exists():
        leiame.write_text(
            "# Oficina da Hoshino\n\n"
            "Este diretório é o espaço de trabalho isolado da Hoshino.\n\n"
            "- `projetos/` — projetos de código dela, um por pasta, persistentes\n"
            "- `ferramentas/` — ferramentas que ela criou para si mesma\n"
            "- `dados/` — arquivos de dados que ela gerou ou baixou\n"
            "- `tmp/` — execuções avulsas (pode apagar à vontade)\n"
            "- `home/` — HOME falso usado nas execuções isoladas\n"
            "- `venv/` — ambiente Python próprio (não mexe no venv do projeto)\n\n"
            "Nada aqui é carregado automaticamente pelo processo principal: as\n"
            "ferramentas criadas rodam sempre em subprocesso isolado.\n",
            encoding="utf-8")
    return OFICINA


def caminho_seguro(relativo: str, criar_pai: bool = False) -> Path:
    """Resolve um caminho garantindo que ele fica dentro da oficina."""
    preparar_oficina()
    bruto = (relativo or "").strip().lstrip("/")
    alvo = (OFICINA / bruto).resolve()
    raiz = OFICINA.resolve()
    if raiz != alvo and raiz not in alvo.parents:
        raise ValueError(f"Caminho fora da oficina recusado: {relativo}")
    if criar_pai:
        alvo.parent.mkdir(parents=True, exist_ok=True)
    return alvo


def _truncar(texto: str) -> str:
    if len(texto) <= LIMITE_SAIDA_CHARS:
        return texto
    return texto[:LIMITE_SAIDA_CHARS] + f"\n...[+{len(texto) - LIMITE_SAIDA_CHARS} caracteres]"


# ---------------------------------------------------------------------------
# Venv próprio
# ---------------------------------------------------------------------------

def python_da_oficina() -> str:
    """Caminho do python do venv da oficina (cai no do sistema se não existir)."""
    candidato = OFICINA / "venv" / "bin" / "python"
    return str(candidato) if candidato.exists() else sys.executable


def criar_venv(com_pacotes_do_sistema: bool = False) -> str:
    """Cria o ambiente Python próprio da oficina."""
    preparar_oficina()
    destino = OFICINA / "venv"
    if (destino / "bin" / "python").exists():
        return f"O venv da oficina já existe em {destino}."
    cmd = [sys.executable, "-m", "venv"]
    if com_pacotes_do_sistema:
        cmd.append("--system-site-packages")
    cmd.append(str(destino))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return "Erro: a criação do venv da oficina demorou demais."
    if r.returncode != 0:
        return f"Erro ao criar o venv da oficina: {r.stderr.strip()[:500]}"
    return f"Venv da oficina criado em {destino}."


def instalar_pacote(pacote: str) -> str:
    """Instala um pacote Python SÓ dentro da oficina (não afeta o sistema nem a Hoshino)."""
    nome = (pacote or "").strip()
    if not nome or any(c in nome for c in ";|&`$\n"):
        return "Erro: nome de pacote inválido."
    if not (OFICINA / "venv" / "bin" / "python").exists():
        criado = criar_venv()
        if criado.startswith("Erro"):
            return criado
    try:
        r = subprocess.run([python_da_oficina(), "-m", "pip", "install", nome],
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return f"A instalação de '{nome}' passou de 10 minutos e foi interrompida."
    saida = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        return f"Falha ao instalar '{nome}' na oficina:\n{_truncar(saida)}"
    return f"'{nome}' instalado na oficina.\n{saida[-600:]}"


# ---------------------------------------------------------------------------
# Isolamento
# ---------------------------------------------------------------------------

def _limites(nova_sessao: bool = True, limitar_processos: bool = True):
    """Aplicado no processo filho antes do exec (fallback sem bubblewrap)."""
    def aplicar():
        mem = MEMORIA_MAX_OFICINA_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_MAX_OFICINA_SEG, CPU_MAX_OFICINA_SEG + 5))
        arq = ARQUIVO_MAX_OFICINA_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (arq, arq))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if limitar_processos:
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
            except (ValueError, OSError):
                pass
        # O bubblewrap já cria a própria sessão com --new-session. Tentar uma
        # segunda setsid no filho antes dele montar namespaces faz algumas
        # versões falharem com "Creating new namespace failed".
        if nova_sessao:
            os.setsid()
    return aplicar


def _tem_bubblewrap() -> bool:
    return shutil.which("bwrap") is not None


def _x11():
    """Display e Xauthority do desktop, para as execuções gráficas."""
    display = os.environ.get("DISPLAY") or ""
    xauth = os.environ.get("XAUTHORITY") or str(Path.home() / ".Xauthority")
    return display, (xauth if os.path.isfile(xauth) else None)


def _montar_chamada(argv: list, cwd: Path, sem_rede: bool, grafico: bool = False,
                    somente_leitura_extra=()):
    """Envolve a chamada em bubblewrap quando disponível."""
    if grafico and not _tem_bubblewrap():
        # Sem bwrap não há como liberar só a GPU/display; não abrir a máquina inteira.
        raise PermissionError("execução gráfica exige bubblewrap")
    if not _tem_bubblewrap():
        from core import entity_access
        return entity_access.command(argv)  # fail closed when private foreign stores exist
    # O Python que roda a interface pode viver num venv fora da oficina. A
    # oficina é o único diretório gravável no sandbox, mas o interpretador e a
    # biblioteca padrão precisam entrar como somente-leitura; sem isso bwrap
    # encontra o comando no host e devolve "No such file or directory" lá
    # dentro. O runtime é derivado do executável real, nunca de um caminho
    # fornecido pelo modelo.
    runtime_python = Path(sys.executable).resolve()
    runtime_raiz = runtime_python.parent.parent
    # Não use ``resolve`` para o executável: o Python de um venv é um symlink
    # para o interpretador-base. Resolver cedo demais apaga a identidade do
    # venv e faz o laboratório ignorar os pacotes instalados nele.
    raiz_oficina = OFICINA.absolute()

    def caminho_no_sandbox(valor: str) -> str:
        """Traduz apenas caminhos da oficina para a montagem privada."""
        if not os.path.isabs(valor):
            return valor
        try:
            relativo = Path(valor).absolute().relative_to(raiz_oficina)
        except ValueError:
            return valor
        return str(_MONTAGEM_OFICINA / relativo)

    try:
        cwd_no_sandbox = str(_MONTAGEM_OFICINA / cwd.absolute().relative_to(raiz_oficina))
    except ValueError:
        # Este módulo só chama a função com cwd da oficina; manter um fallback
        # explícito evita fabricar um caminho que escaparia do isolamento.
        raise ValueError("diretório de execução fora da oficina")
    bw = ["bwrap",
          "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc",
          "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
          "--ro-bind-try", "/bin", "/bin", "--ro-bind-try", "/sbin", "/sbin",
          # 29/10: sem isto dpkg/apt diziam "nada instalado" com libglfw3-dev instalado.
          "--ro-bind-try", "/var/lib/dpkg", "/var/lib/dpkg",
          "--ro-bind", str(runtime_raiz), str(runtime_raiz),
          "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
          "--dir", str(_MONTAGEM_OFICINA),
          "--bind", str(OFICINA), str(_MONTAGEM_OFICINA),
          "--unshare-pid", "--unshare-uts", "--unshare-ipc",
          "--die-with-parent", "--new-session",
          "--chdir", cwd_no_sandbox]
    # A symlink under the writable workspace must not expose foreign stores.
    from core import entity_access
    for root in entity_access.foreign_roots():
        if root.is_relative_to(runtime_raiz):bw+=['--tmpfs',str(root)]
    for extra in somente_leitura_extra:  # ex.: binários dos verificadores de código
        bw += ["--ro-bind", str(extra), str(extra)]
    if grafico:
        # Só o necessário para OpenGL na AMD e uma janela no X11: nós DRM, /sys
        # somente leitura (o Mesa identifica a placa por ali), o socket e o cookie X.
        display, xauth = _x11()
        bw += ["--dev-bind", "/dev/dri", "/dev/dri", "--ro-bind", "/sys", "/sys"]
        if os.path.isdir("/tmp/.X11-unix"):
            bw += ["--bind", "/tmp/.X11-unix", "/tmp/.X11-unix"]
        if xauth:
            bw += ["--ro-bind", xauth, _XAUTH_NO_SANDBOX]
    if sem_rede:
        bw.append("--unshare-net")
    # Venvs normalmente usam um symlink para o Python-base. O caminho do link
    # pode estar fora da oficina (e portanto fora do bwrap); executar o destino
    # real usa o runtime somente-leitura que foi ligado acima.
    argv_no_sandbox = [caminho_no_sandbox(str(arg)) for arg in argv]
    if (argv_no_sandbox and os.path.isabs(argv_no_sandbox[0])
            and not argv_no_sandbox[0].startswith(f"{_MONTAGEM_OFICINA}/")):
        argv_no_sandbox[0] = str(Path(argv_no_sandbox[0]).resolve())
    return bw + ["--"] + argv_no_sandbox


def isolamento_disponivel() -> str:
    return ("bubblewrap (isolamento de sistema de arquivos + processos)"
            if _tem_bubblewrap() else
            "rlimits (CPU/memória/arquivo) — instale `bubblewrap` para isolamento mais forte")


def _ambiente_execucao(grafico: bool = False) -> dict:
    env = {
        "PATH": f"{OFICINA / 'venv' / 'bin'}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(OFICINA / "home"),
        "TMPDIR": str(OFICINA / "tmp"),
        "LANG": os.environ.get("LANG", "pt_BR.UTF-8"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if grafico:
        display, xauth = _x11()
        env["DISPLAY"] = display
        if xauth:
            env["XAUTHORITY"] = _XAUTH_NO_SANDBOX
    return env


def _executar(argv: list, cwd: Path, timeout: int, sem_rede: bool) -> str:
    env = _ambiente_execucao()
    try:
        r = subprocess.run(_montar_chamada(argv, cwd, sem_rede),
                           capture_output=True, text=True, errors="replace",
                           timeout=timeout, cwd=str(cwd), env=env,
                           # bwrap já assume a sessão; o fallback precisa
                           # criá-la para que o timeout não deixe filhos presos.
                           preexec_fn=_limites(
                               nova_sessao=not _tem_bubblewrap(),
                               # bwrap cria namespaces e não consegue fazê-lo
                               # se o filho já recebeu um RLIMIT_NPROC baixo.
                               # O limite de PID dele é a proteção equivalente.
                               limitar_processos=not _tem_bubblewrap()),
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return f"Erro: passou de {timeout}s e foi interrompido. Aumente o timeout ou use um job."
    except MemoryError:
        return "Erro: estourou o limite de memória da oficina."
    except Exception as e:  # noqa: BLE001
        return f"Erro ao executar na oficina: {e}"
    partes = []
    if r.stdout.strip():
        partes.append(r.stdout.strip())
    if r.stderr.strip():
        partes.append("[stderr]\n" + r.stderr.strip())
    corpo = "\n".join(partes) or "(sem saída)"
    return f"[oficina | código {r.returncode}]\n{_truncar(corpo)}"


# ---------------------------------------------------------------------------
# API de uso
# ---------------------------------------------------------------------------

def criar_projeto(nome: str, descricao: str = "") -> str:
    """Cria uma pasta de projeto persistente dentro da oficina."""
    limpo = "".join(c for c in (nome or "").strip().lower().replace(" ", "_")
                    if c.isalnum() or c in "_-")
    if not limpo:
        return "Erro: nome de projeto inválido."
    destino = caminho_seguro(f"projetos/{limpo}")
    ja_existia = destino.exists()
    destino.mkdir(parents=True, exist_ok=True)
    manifesto = destino / "projeto.json"
    if not manifesto.exists():
        manifesto.write_text(json.dumps(
            {"nome": limpo, "descricao": descricao,
             "criado_em": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return (f"Projeto '{limpo}' {'já existia' if ja_existia else 'criado'} em {destino}. "
            f"Use escrever_na_oficina('projetos/{limpo}/arquivo.py', ...) para escrever nele.")


def escrever_na_oficina(caminho: str, conteudo: str, modo: str = "w") -> str:
    """Escreve um arquivo dentro da oficina (cria as pastas que faltarem)."""
    try:
        alvo = caminho_seguro(caminho, criar_pai=True)
    except ValueError as e:
        return f"Erro: {e}"
    modo = modo if modo in ("w", "a") else "w"
    with open(alvo, modo, encoding="utf-8") as f:
        f.write(conteudo or "")
    from tools import code_check  # problemas imediatos, como o sublinhado do editor (29/10)
    return f"Gravado: {alvo.relative_to(OFICINA)} ({alvo.stat().st_size} bytes)." + code_check.resumo_ao_salvar(alvo)


def _trecho_mais_parecido(linhas: list, trecho: str) -> str:
    """Bloco do arquivo mais parecido com o trecho pedido, numerado, para copiar (29/10)."""
    import difflib
    alvo = [l.strip() for l in trecho.splitlines() if l.strip()]
    if not alvo or not linhas:
        return ""
    tamanho = max(1, len(trecho.splitlines()))
    melhor, inicio = 0.0, 0
    for i in range(0, max(1, len(linhas) - tamanho + 1)):
        janela = [l.strip() for l in linhas[i:i + tamanho] if l.strip()]
        razao = difflib.SequenceMatcher(None, "\n".join(alvo), "\n".join(janela)).ratio()
        if razao > melhor:
            melhor, inicio = razao, i
    if melhor < 0.35:
        return ""
    a, b = max(0, inicio - 1), min(len(linhas), inicio + tamanho + 1)
    return "\n".join(f"{n + 1:>5}| {linhas[n]}" for n in range(a, b))


def editar_na_oficina(caminho: str, trecho: str = "", novo: str = "", inicio: int = None, fim: int = None) -> str:
    """Troca UM trecho exato, ou as linhas inicio..fim, de um arquivo da oficina; sem shell.

    29/10: no ensaio C++ o echo com várias linhas/aspas falhou e o programa foi
    trocado por um trivial. O trecho precisa aparecer exatamente uma vez; no
    desafio ela reconstruía o trecho de memória e errava, então dá para trocar
    pelas linhas numeradas que acabou de ler, e a falha mostra o texto real.
    """
    try:
        alvo = caminho_seguro(caminho)
    except ValueError as e:
        return f"Erro: {e}"
    if not alvo.is_file():
        return f"Erro: '{caminho}' não existe na oficina."
    texto = alvo.read_text(encoding="utf-8", errors="replace")
    linhas = texto.splitlines()
    antes = len(linhas)
    # Os dois juntos (29/10, ela mandou assim): o trecho exato vale se aparece uma vez; senão, as linhas.
    if (inicio is not None or fim is not None) and not (trecho and texto.count(trecho) == 1):
        try:
            # Só fim = do começo até fim; só inicio = de inicio até o fim do arquivo (29/10: só fim=125
            # virou 'trocar a linha 125' e o arquivo novo inteiro foi colado no lugar do '}' final).
            a, b = int(inicio if inicio is not None else 1), int(fim if fim is not None else antes)
        except (TypeError, ValueError):
            return "Erro: inicio/fim precisam ser números de linha. Nada foi alterado."
        if not 1 <= a <= b <= antes:
            return f"Erro: linhas {a}–{b} fora do arquivo (1–{antes}). Nada foi alterado."
        trocadas = "\n".join(f"{n:>5}| {linhas[n - 1]}" for n in range(a, b + 1))
        novas = (novo or "").splitlines()
        linhas[a - 1:b] = novas
        alvo.write_text("\n".join(linhas) + ("\n" if texto.endswith("\n") else ""), encoding="utf-8")
        from tools import code_check
        return (f"Editado: {alvo.relative_to(OFICINA)} (linhas {a}–{b} trocadas por {len(novas)} linha(s); "
                f"{antes} → {len(linhas)} linhas). Linhas removidas:\n{trocadas[:1500]}" + code_check.resumo_ao_salvar(alvo))
    if not trecho:
        return "Erro: passe o trecho exato a trocar, ou inicio/fim das linhas. Nada foi alterado."
    vezes = texto.count(trecho)
    if vezes == 0:
        parecido = _trecho_mais_parecido(linhas, trecho)
        dica = (f" O bloco mais parecido no arquivo atual é (copie daqui ou use inicio/fim):\n{parecido}"
                if parecido else " Leia as linhas com ler_da_oficina inicio/fim, ou edite por inicio/fim.")
        return (f"Erro: o trecho não aparece em {caminho} (precisa ser cópia exata, com espaços/indentação). "
                f"Nada foi alterado.{dica}")
    if vezes > 1:
        return f"Erro: o trecho aparece {vezes} vezes em {caminho}; inclua mais linhas ou use inicio/fim. Nada foi alterado."
    texto = texto.replace(trecho, novo or "", 1)
    alvo.write_text(texto, encoding="utf-8")
    from tools import code_check
    return (f"Editado: {alvo.relative_to(OFICINA)} (1 trecho trocado; {antes} → {texto.count(chr(10)) + 1} linhas)."
            + code_check.resumo_ao_salvar(alvo))


def ler_da_oficina(caminho: str, limite: int = 8000, inicio: int = None, fim: int = None) -> str:
    """Lê um arquivo de dentro da oficina; com inicio/fim, só essas linhas, numeradas."""
    try:
        alvo = caminho_seguro(caminho)
    except ValueError as e:
        return f"Erro: {e}"
    if not alvo.exists():
        return f"Erro: '{caminho}' não existe na oficina."
    if alvo.is_dir():
        return listar_oficina(caminho)
    texto = alvo.read_text(encoding="utf-8", errors="replace")
    if inicio is not None or fim is not None:
        # Para ir direto à linha de um erro de compilação sem reler o arquivo inteiro.
        linhas = texto.splitlines()
        a = max(1, int(inicio or 1))
        b = min(len(linhas), int(fim or len(linhas)), a + 399)
        trecho = "\n".join(f"{n:>5}| {linhas[n - 1]}" for n in range(a, b + 1))
        return (f"{alvo.relative_to(OFICINA)} linhas {a}–{b} de {len(linhas)}:\n" + trecho)[:limite]
    return texto[:limite] + ("\n...[truncado]" if len(texto) > limite else "")


def listar_oficina(subpasta: str = "") -> str:
    """Lista até 200 entradas visíveis; pastas internas podem ser alvo explícito."""
    try:
        alvo = caminho_seguro(subpasta or "")
    except ValueError as e:
        return f"Erro: {e}"
    if not alvo.exists():
        return f"'{subpasta}' não existe na oficina."
    linhas = []
    internas = {"CMakeFiles", "__pycache__", ".git", "browser_profile", "venv"}
    for item in sorted(alvo.rglob("*")):
        # O filtro vale dentro do alvo: pedir CMakeFiles diretamente ainda
        # permite inspecioná-la, sem seus arquivos consumirem a lista do projeto.
        if any(parte in internas for parte in item.relative_to(alvo).parts):
            continue
        rel = item.relative_to(OFICINA)
        linhas.append(f"{rel}/" if item.is_dir() else f"{rel}  ({item.stat().st_size}B)")
        if len(linhas) >= 200:
            break
    return f"Oficina ({alvo.relative_to(OFICINA) or '.'}):\n" + ("\n".join(linhas) or "(vazia)")


def executar_na_oficina(codigo: str = None, arquivo: str = None, linguagem: str = "python",
                        projeto: str = None, timeout: int = None, sem_rede: bool = False,
                        argumentos: list = None, interpretador: Path | str | None = None) -> str:
    """Roda código dentro da oficina, isolado.

    Ou passa `codigo` (que é salvo e executado), ou `arquivo` (caminho relativo
    à oficina, para reexecutar algo que já existe).
    """
    preparar_oficina()
    timeout = max(1, min(int(timeout or TIMEOUT_OFICINA_PADRAO), 600))
    linguagem = linguagem if linguagem in EXTENSOES else "python"
    pasta_projeto = None
    if projeto and not arquivo:
        # 29/10: projeto='projetos/x/build' virava projetos/projetos/x/build e voltava Errno 2 cru.
        nome_projeto = str(projeto).strip().strip("/").removeprefix("projetos/")
        try:
            pasta_projeto = caminho_seguro(f"projetos/{nome_projeto}")
        except ValueError as e:
            return f"Erro: {e}"
        if not pasta_projeto.is_dir():
            return (f"Erro: a pasta projetos/{nome_projeto} não existe; nada foi executado. "
                    "projeto é o nome da pasta em projetos/ (ou omita e use cd no código).")
        # 29/10: quatro vezes 'projeto=...' com 'cd projetos/...' no script; o recibo explicava e ela
        # repetia. O cd inicial diz onde ela quer estar: se só vale a partir da raiz, roda da raiz.
        primeiro_cd = re.match(r"\s*cd\s+([^\s;&|]+)", codigo or "")
        if primeiro_cd and not primeiro_cd.group(1).startswith("/"):
            destino = primeiro_cd.group(1).strip("'\"")
            if not (pasta_projeto / destino).is_dir() and (OFICINA / destino).is_dir():
                pasta_projeto = None

    if arquivo:
        try:
            alvo = caminho_seguro(arquivo)
        except ValueError as e:
            return f"Erro: {e}"
        if not alvo.exists():
            return f"Erro: '{arquivo}' não existe na oficina."
    else:
        if not (codigo or "").strip():
            return "Erro: nada para executar (passe `codigo` ou `arquivo`)."
        # 29/10: com projeto, o script avulso ia para a pasta do projeto e ela o editava como
        # se fosse parte dele. O avulso fica sempre em tmp/; o projeto só define onde roda.
        base = "tmp"
        nome = f"exec_{datetime.now():%Y%m%d_%H%M%S}{EXTENSOES[linguagem]}"
        alvo = caminho_seguro(f"{base}/{nome}", criar_pai=True)
        alvo.write_text(codigo, encoding="utf-8")

    # 29/10: código avulso rodava em tmp/ e 'projetos/...' relativo não existia ali; ela repetiu
    # o g++ por 30 passos sem saber a pasta. Avulso roda na raiz da oficina (mesma referência das
    # outras ferramentas), com projeto na pasta dele; arquivo existente roda na pasta do arquivo.
    cwd = alvo.parent if arquivo else (pasta_projeto or OFICINA)
    if linguagem == "python" or alvo.suffix == ".py":
        python = str(interpretador) if interpretador else python_da_oficina()
        argv = [python, str(alvo)]
    elif linguagem == "bash" or alvo.suffix == ".sh":
        argv = ["bash", str(alvo)]
    elif linguagem == "node" or alvo.suffix == ".js":
        if not shutil.which("node"):
            return "Erro: node não está instalado no sistema."
        argv = ["node", str(alvo)]
    elif linguagem == "cpp" or alvo.suffix in (".cpp", ".cc"):
        # Um arquivo C++ compila e roda; projetos com vários arquivos/CMake usam bash.
        binario = alvo.with_suffix(".bin")
        argv = ["bash", "-c", 'g++ -std=c++17 -O2 -Wall -o "$1" "$2" && "$1" "${@:3}"', "cpp",
                str(binario), str(alvo)]
    else:
        return f"Erro: não sei executar '{linguagem}'."

    argv += [str(a) for a in (argumentos or [])]
    saida = _executar(argv, cwd, timeout, sem_rede)
    relativa = cwd.relative_to(OFICINA).as_posix() if cwd != OFICINA else ""
    # Dentro do isolamento a oficina é /workspace (ela usava /workspace/oficina/...).
    pasta = (f"{relativa or '. (raiz da oficina)'} — dentro do isolamento: "
             f"{(_MONTAGEM_OFICINA / relativa).as_posix() if relativa else _MONTAGEM_OFICINA.as_posix()}")
    # 29/10: projeto='projetos/x' já roda em projetos/x e o script ainda fazia 'cd projetos/x'.
    m = re.search(r"cd: ([^:\n]+): (?:No such file or directory|Arquivo ou diretório inexistente)", saida)
    if m and relativa and (OFICINA / m.group(1).strip()).is_dir():
        saida += (f"\n(Este comando já rodou em {relativa}; '{m.group(1).strip()}' existe a partir da raiz "
                  "da oficina. Tire o cd ou não passe projeto.)")
    return f"Arquivo: {alvo.relative_to(OFICINA)}\nPasta de execução: {pasta}\n{saida}"


def _janelas_x11() -> dict:
    """IDs e títulos das janelas do desktop (wmctrl), lidos fora do sandbox."""
    try:
        r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {}
    janelas = {}
    for linha in r.stdout.splitlines():
        partes = linha.split(None, 3)
        if partes:
            janelas[partes[0]] = partes[3] if len(partes) > 3 else ""
    return janelas


def _janela_exibida(janela: str) -> dict | None:
    """Posição real de uma janela que o desktop está mostrando; None se não está exibida.

    29/10: com o monitor em espera o compositor não mapeia janelas novas; o
    wmctrl ainda lista a janela com uma posição falsa e a captura saía errada.
    """
    try:
        info = subprocess.run(["xwininfo", "-id", janela], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    campos = {}
    for linha in info.splitlines():
        chave, _, valor = linha.strip().partition(":")
        campos[chave.strip()] = valor.strip()
    if campos.get("Map State") != "IsViewable":
        return None
    try:
        return {"left": int(campos["Absolute upper-left X"]), "top": int(campos["Absolute upper-left Y"]),
                "width": int(campos["Width"]), "height": int(campos["Height"])}
    except (KeyError, ValueError):
        return None


def _capturar_janela(janela: str, caixa: dict, destino: Path) -> str:
    """Põe a janela acima das outras (sem roubar o foco) e salva a área dela da tela (PNG)."""
    import time
    import mss
    from PIL import Image
    subprocess.run(["wmctrl", "-i", "-r", janela, "-b", "add,above"], capture_output=True, timeout=5)
    time.sleep(0.4)
    try:
        with mss.mss() as tela:
            raw = tela.grab(caixa)
            Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX").save(destino)
    finally:
        subprocess.run(["wmctrl", "-i", "-r", janela, "-b", "remove,above"], capture_output=True, timeout=5)
    return f"{caixa['width']}x{caixa['height']}"


def executar_grafico_na_oficina(arquivo: str, argumentos: list = None, segundos: int = 8,
                                capturar: bool = True) -> str:
    """Roda um programa da oficina com GPU e janela por alguns segundos e captura a janela.

    O programa (binário compilado, .sh ou .py) roda no mesmo isolamento da
    oficina, acrescido só de /dev/dri, /sys somente leitura e do display X11.
    A GPU é reservada pelo gestor de recursos durante a execução. Ao fim do
    prazo, as janelas novas são capturadas em capturas/ e o programa é encerrado.
    """
    preparar_oficina()
    try:
        alvo = caminho_seguro(arquivo)
    except ValueError as e:
        return f"Erro: {e}"
    if not alvo.is_file():
        return f"Erro: '{arquivo}' não existe na oficina (compile antes e passe o executável)."
    segundos = max(1, min(int(segundos or 8), GRAFICO_SEGUNDOS_MAX))
    if alvo.suffix == ".py":
        argv = [python_da_oficina(), str(alvo)]
    elif alvo.suffix == ".sh":
        argv = ["bash", str(alvo)]
    elif os.access(alvo, os.X_OK):
        argv = [str(alvo)]
    else:
        return f"Erro: '{arquivo}' não é executável (use o binário gerado pelo compilador, .sh ou .py)."
    argv += [str(a) for a in (argumentos or [])]
    try:
        chamada = _montar_chamada(argv, alvo.parent, sem_rede=True, grafico=True)
    except PermissionError as e:
        return f"Erro: {e}."
    if not os.environ.get("DISPLAY"):
        return "Erro: não há display gráfico disponível para abrir janelas."
    from core import gpu_resource, resource_manager
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_out, log_err = (OFICINA / "logs" / f"grafico_{carimbo}.{n}.log" for n in ("out", "err"))
    capturas, encerrado = [], False
    try:
        with gpu_resource.lease("batch", model="oficina-grafica", vram_bytes=GRAFICO_VRAM_MB * 1024 * 1024,
                                workspace_bytes=0, wait=60, cpu_fallback=False):
            antes = _janelas_x11()
            with open(log_out, "w") as out, open(log_err, "w") as err:
                proc = subprocess.Popen(chamada, cwd=str(alvo.parent), env=_ambiente_execucao(grafico=True),
                                        stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                        preexec_fn=_limites(nova_sessao=False, limitar_processos=False))
                try:
                    codigo = proc.wait(timeout=segundos)
                except subprocess.TimeoutExpired:
                    codigo = None
                    if capturar:
                        for janela, titulo in _janelas_x11().items():
                            if janela in antes:
                                continue
                            caixa = _janela_exibida(janela)
                            if caixa is None:
                                capturas.append(f"a janela '{titulo}' foi criada, mas o desktop não a está exibindo "
                                                "(monitor em espera?); sem captura confiável agora")
                                continue
                            destino = OFICINA / "capturas" / f"{alvo.stem}_{carimbo}_{len(capturas) + 1}.png"
                            try:
                                tamanho = _capturar_janela(janela, caixa, destino)
                                capturas.append(f"{destino.relative_to(OFICINA)} ({tamanho}, janela '{titulo}')")
                            except Exception as exc:  # noqa: BLE001
                                capturas.append(f"falhou ao capturar a janela '{titulo}': {exc}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    encerrado = True
    except resource_manager.GPUWaitTimeout as exc:
        return f"Erro: GPU indisponível agora ({exc}); nada foi executado."
    saida = _truncar((log_out.read_text(errors="replace").strip() +
                      ("\n[stderr]\n" + log_err.read_text(errors="replace").strip()
                       if log_err.read_text(errors="replace").strip() else "")).strip() or "(sem saída)")
    estado = (f"rodou {segundos}s e foi encerrado por mim (janela/loop ativo)" if encerrado
              else f"terminou sozinho com código {codigo}")
    return (f"Arquivo: {alvo.relative_to(OFICINA)} — {estado}.\n"
            + ("Capturas: " + "; ".join(capturas) + "\n" if capturas else
               ("Nenhuma janela nova apareceu.\n" if encerrado and capturar else ""))
            + f"[saída]\n{saida}")


def observar_imagem_da_oficina(caminho: str, pergunta: str = None) -> str:
    """Olha uma imagem da própria oficina (ex.: capturas/...) com a visão do modelo."""
    try:
        alvo = caminho_seguro(caminho)
    except ValueError as e:
        return f"Erro: {e}"
    if not alvo.is_file():
        return f"Erro: '{caminho}' não existe na oficina."
    from tools import vision
    return vision.observar_imagem(str(alvo), pergunta)


def estado_da_oficina() -> str:
    """Resumo do ambiente isolado: onde fica, o que tem, que isolamento está ativo."""
    preparar_oficina()
    projetos = [p.name for p in (OFICINA / "projetos").iterdir() if p.is_dir()] \
        if (OFICINA / "projetos").exists() else []
    ferramentas = [p.name for p in (OFICINA / "ferramentas").iterdir() if p.is_dir()] \
        if (OFICINA / "ferramentas").exists() else []
    tem_venv = (OFICINA / "venv" / "bin" / "python").exists()
    return (f"Oficina em {OFICINA}\n"
            f"Isolamento: {isolamento_disponivel()}\n"
            f"Venv próprio: {'sim' if tem_venv else 'ainda não criado (criar_venv)'}\n"
            f"Limites: {MEMORIA_MAX_OFICINA_MB}MB de RAM, {CPU_MAX_OFICINA_SEG}s de CPU, "
            f"{ARQUIVO_MAX_OFICINA_MB}MB por arquivo\n"
            f"Projetos ({len(projetos)}): {', '.join(projetos) or 'nenhum'}\n"
            f"Ferramentas próprias ({len(ferramentas)}): {', '.join(ferramentas) or 'nenhuma'}")


# ---------------------------------------------------------------- laboratório IA
def preparar_ambiente_ia() -> str:
    """Cria a área persistente de experimentos de IA dentro da oficina."""
    preparar_oficina()
    raiz = OFICINA / "ia"
    for sub in (raiz, raiz / "modelos", raiz / "ferramentas", raiz / "dados", raiz / "tmp"):
        sub.mkdir(parents=True, exist_ok=True)
    manifesto = raiz / "ambiente.json"
    if not manifesto.exists():
        manifesto.write_text(json.dumps({
            "descricao": "Laboratório de IA da Hoshino",
            "rede_por_padrao": False,
            "isolamento_exigido": "bubblewrap",
            "criado_em": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Laboratório IA pronto em {raiz}."


def instalar_pacote_ia(pacote: str) -> str:
    """Instala dependência somente no venv do laboratório de IA."""
    nome = (pacote or "").strip()
    if not nome or any(c in nome for c in ";|&`$\n"):
        return "Erro: nome de pacote inválido."
    python, erro = _python_ia()
    if erro:
        return erro
    try:
        r = subprocess.run([str(python), "-m", "pip", "install", nome],
                           capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return f"A instalação de '{nome}' excedeu 15 minutos."
    saida = (r.stdout + r.stderr).strip()
    return (f"'{nome}' instalado no laboratório IA." if not r.returncode
            else f"Falha ao instalar '{nome}' no laboratório IA:\n{_truncar(saida)}")


def _python_ia() -> tuple[Path | None, str]:
    """Garante e devolve o interpretador próprio do laboratório de IA."""
    preparar_ambiente_ia()
    venv = OFICINA / "ia" / "venv"
    python = venv / "bin" / "python"
    if python.exists():
        return python, ""
    try:
        criado = subprocess.run([sys.executable, "-m", "venv", str(venv)],
                                capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "Erro: criação do venv de IA excedeu 5 minutos."
    if criado.returncode or not python.exists():
        detalhe = (criado.stderr or criado.stdout).strip()[:500]
        return None, f"Erro ao criar venv de IA: {detalhe}"
    return python, ""


def executar_na_ia(codigo: str = None, arquivo: str = None, linguagem: str = "python",
                   timeout: int = None, sem_rede: bool = True) -> str:
    """Executa experimento no laboratório; sem bubblewrap, recusa por segurança."""
    if not _tem_bubblewrap():
        return "Erro: o laboratório IA exige bubblewrap para isolamento forte."
    python, erro = _python_ia()
    if erro:
        return erro
    if arquivo and not str(arquivo).replace("\\", "/").startswith("ia/"):
        return "Erro: arquivo do laboratório deve ficar dentro de ia/."
    if arquivo:
        return executar_na_oficina(arquivo=arquivo, linguagem=linguagem, timeout=timeout,
                                   sem_rede=sem_rede, interpretador=python)
    if not (codigo or "").strip():
        return "Erro: passe código ou arquivo para executar no laboratório IA."
    extensao = EXTENSOES.get(linguagem, ".py")
    nome = f"ia/tmp/exec_{datetime.now():%Y%m%d_%H%M%S}{extensao}"
    alvo = caminho_seguro(nome, criar_pai=True)
    alvo.write_text(codigo, encoding="utf-8")
    return executar_na_oficina(arquivo=nome, linguagem=linguagem, timeout=timeout,
                               sem_rede=sem_rede, interpretador=python)
