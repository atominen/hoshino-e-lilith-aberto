"""Operações simples e unificadas de arquivos para a Hoshino.

A interface pública é uma única capacidade ``workspace``. Ela cobre o que um
editor simples faz: ler, criar, editar, acrescentar, criar pasta, listar e
buscar. As funções legadas continuam como wrappers internos para compatibilidade
com código antigo/testes, mas não precisam ser expostas ao modelo.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from config import OFICINA_DIR, RAIZ

LIMITE_LEITURA = 12000
_DESKTOP_ALIASES = {
    "~/área de trabalho": "DESKTOP",
    "~/area de trabalho": "DESKTOP",
    "~/área_de_trabalho": "DESKTOP",
    "~/area_de_trabalho": "DESKTOP",
    "~/desktop": "DESKTOP",
    "/~/área de trabalho": "DESKTOP",
    "/~/area de trabalho": "DESKTOP",
    "/~/desktop": "DESKTOP",
}


_NOMES_DESKTOP = ("desktop", "área de trabalho", "area de trabalho", "área_de_trabalho", "area_de_trabalho")


def _desktop_dir() -> Path:
    """A área de trabalho de verdade: primeiro o que o sistema diz (xdg-user-dirs), depois os nomes conhecidos
    sem diferenciar maiúscula. Teste de uso 07/11: o PC tem "Área de trabalho" (t minúsculo), a lista fixa só
    tinha "Área de Trabalho" e a pasta pedida acabou num ~/Desktop criado à toa."""
    home = Path.home()
    try:
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        for linha in (config_dir / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith("XDG_DESKTOP_DIR="):
                valor = linha.split("=", 1)[1].strip().strip('"').replace("$HOME", str(home))
                p = Path(os.path.expanduser(valor))
                if p.is_dir() and p.resolve() != home.resolve():
                    return p.resolve()
    except (OSError, UnicodeDecodeError):
        pass
    try:
        existentes = {p.name.casefold(): p for p in home.iterdir() if p.is_dir()}
    except OSError:
        existentes = {}
    for nome in _NOMES_DESKTOP:
        if nome in existentes:
            return existentes[nome].resolve()
    # Só usa Desktop como destino padrão; não cria aqui.
    return (home / "Desktop").resolve()


def resolver_caminho(caminho: str | os.PathLike[str], base: str | os.PathLike[str] | None = None) -> Path:
    bruto = str(caminho or "").strip().replace("\\", "/")
    if not bruto:
        raise ValueError("informe um caminho")
    normalizado = bruto.rstrip("/")
    chave = normalizado.casefold()
    for alias in _DESKTOP_ALIASES:
        alias_case = alias.casefold()
        if chave == alias_case or chave.startswith(alias_case + "/"):
            resto = normalizado[len(alias):].lstrip("/")
            alvo = _desktop_dir() / resto if resto else _desktop_dir()
            return alvo.resolve()

    # Linux costuma alternar entre "Desktop" e "Área de Trabalho".
    # Caminhos absolutos equivalentes do mesmo usuário também devem apontar
    # para o diretório real, para que o modelo não consiga quebrar uma tarefa
    # apenas por trocar o nome/localização do Desktop.
    home = Path.home().resolve()
    candidatos_desktop = [
        home / "Desktop", home / "desktop",
        home / "Área de Trabalho", home / "Area de Trabalho",
        home / "área de trabalho", home / "area de trabalho",
    ]
    for alias_path in candidatos_desktop:
        alias_text = str(alias_path).rstrip("/")
        alias_case = alias_text.casefold()
        if chave == alias_case or chave.startswith(alias_case + "/"):
            resto = normalizado[len(alias_text):].lstrip("/")
            alvo = _desktop_dir() / resto if resto else _desktop_dir()
            return alvo.resolve()
    if normalizado.startswith("~\\"):
        normalizado = "~/" + normalizado[2:]
    alvo = Path(os.path.expanduser(normalizado))
    if not alvo.is_absolute():
        # Sem base explícita, arquivos pertencem à oficina da entidade ativa.
        # Usar a home aqui mistura os trabalhos de entidades distintas.
        raiz = Path(base).expanduser() if base else Path(OFICINA_DIR)
        prefixo = str(raiz.resolve()).lstrip('/')+'/'
        if normalizado.startswith(prefixo):
            # Prefixo completo da oficina já conhecida, só sem a barra inicial.
            # Não produzir oficina/tmp/.../oficina de novo; "tmp/a.py" comum
            # continua relativo. A autorização de acesso permanece no caller.
            return Path('/'+normalizado).resolve()
        alvo = raiz / alvo
    return alvo.resolve()


def _zonas_permitidas() -> list[Path]:
    return [Path.home().resolve(), Path(RAIZ).resolve(), Path(OFICINA_DIR).resolve(), Path("/tmp").resolve()]


def _permitido(caminho: Path) -> bool:
    from core import entity_access
    if not entity_access.permitted(caminho):return False
    alvo = caminho.resolve()
    return any(alvo == zona or zona in alvo.parents for zona in _zonas_permitidas())


def _texto_seguro(alvo: Path, limite: int = LIMITE_LEITURA) -> tuple[str, int]:
    tamanho = alvo.stat().st_size
    with alvo.open("rb") as f:
        amostra = f.read(2048)
    if b"\x00" in amostra:
        raise ValueError(f"'{alvo.name}' parece binário ({tamanho} bytes)")
    conteudo = alvo.read_text(encoding="utf-8", errors="replace")
    if len(conteudo) > limite:
        linhas = conteudo[:limite].count("\n")
        conteudo = (
            f"[{alvo} — {tamanho} bytes, mostrando os primeiros {limite} caracteres "
            f"(~{linhas} linhas)]\n{conteudo[:limite]}\n...[truncado]"
        )
    return conteudo, tamanho


def _gravar_atomico(alvo: Path, conteudo: str, append: bool = False) -> str:
    import hashlib
    def digest():
        sha = hashlib.sha256()
        size = 0
        with alvo.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                sha.update(chunk)
                size += len(chunk)
        return sha, size
    expected, old_size = digest() if append and alvo.exists() else (hashlib.sha256(), 0)
    encoded = conteudo.encode('utf-8')
    expected.update(encoded)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    if append and alvo.exists():
        with alvo.open("a", encoding="utf-8") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
    else:
        fd, tmp = tempfile.mkstemp(prefix=f".{alvo.name}.", dir=str(alvo.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(conteudo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, alvo)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
    actual, size = digest()  # reabertura independente; não basta stat/existência
    if actual.digest() != expected.digest() or size != old_size + len(encoded):
        raise OSError('Verificação independente do conteúdo divergiu; não repetir a escrita.')
    return f"PATH={alvo}\n[ARQUIVO VERIFICADO sha256={actual.hexdigest()}]"


def workspace(
    operacao: str,
    caminho: str = "",
    conteudo: str = "",
    procurar: str = "",
    substituir: str = "",
    recursivo: bool = False,
    limite: int = 100,
    modo: str = "substituir",
) -> str:
    """Executa uma operação de arquivo com caminho canônico e evidência real.

    Operações públicas: ler/abrir, salvar, pasta, listar, buscar.
    ``salvar`` suporta os modos substituir, anexar e editar.
    """
    op = str(operacao or "").strip().casefold()
    aliases = {
        "read": "ler", "read_file": "ler", "abrir": "ler",
        "write": "salvar", "write_file": "salvar", "save": "salvar",
        "criar": "salvar", "edit": "salvar", "editar": "salvar",
        "append": "salvar", "acrescentar": "salvar",
        "mkdir": "pasta", "make_directory": "pasta",
        "list": "listar", "search": "buscar",
    }
    op = aliases.get(op, op)
    try:
        alvo = resolver_caminho(caminho or ".")
    except ValueError as exc:
        return f"Erro: {exc}."
    if not _permitido(alvo):
        return f"Erro: '{alvo}' está fora das áreas permitidas."

    mutacao_iniciada = False
    try:
        if op == "pasta":
            existia = alvo.exists()
            if existia and not alvo.is_dir():
                return f"Erro: '{alvo}' já existe e não é uma pasta."
            mutacao_iniciada = True
            alvo.mkdir(parents=True, exist_ok=True)
            if not alvo.is_dir():
                raise OSError('A pasta não foi confirmada após criação.')
            return f"OPERACAO=pasta\nPASTA={alvo}\n{'JÁ_EXISTIA' if existia else 'CRIADA'}\n[PASTA VERIFICADA]"

        if op == "listar":
            if not alvo.is_dir():
                return f"Erro: '{alvo}' não é uma pasta."
            itens = sorted(alvo.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            limite_n = max(1, min(int(limite or 100), 500))
            linhas = [f"OPERACAO=listar", f"PATH={alvo}"]
            for item in itens[:limite_n]:
                if not _permitido(item):continue
                linhas.append(f"{'DIR' if item.is_dir() else 'FILE'}\t{item.name}")
            if len(itens) > limite_n:
                linhas.append(f"... {len(itens) - limite_n} itens omitidos")
            return "\n".join(linhas)

        if op == "buscar":
            if not alvo.exists():
                return f"Erro: '{alvo}' não existe."
            padrao = str(procurar or "").strip()
            if not padrao:
                return "Erro: informe 'procurar' para buscar arquivos."
            base = alvo if alvo.is_dir() else alvo.parent
            encontrados: list[Path] = []
            it = base.rglob("*") if recursivo else base.glob("*")
            for item in it:
                if _permitido(item) and item.is_file() and padrao.casefold() in item.name.casefold():
                    encontrados.append(item)
                    if len(encontrados) >= max(1, min(int(limite or 100), 500)):
                        break
            return ("OPERACAO=buscar\nPATH=" + str(base) + "\n" + "\n".join(str(p.resolve()) for p in encontrados)) if encontrados else f"OPERACAO=buscar\nPATH={base}\nNENHUM_RESULTADO"

        if op == "ler":
            if not alvo.exists():
                return f"Erro: '{alvo}' não existe."
            if alvo.is_dir():
                return f"Erro: '{alvo}' é um diretório; use operacao='listar'."
            try:
                texto, tamanho = _texto_seguro(alvo)
            except ValueError as exc:
                return f"Erro: {exc}."
            return f"OPERACAO=ler\nPATH={alvo}\nBYTES={tamanho}\n{texto}"

        if op == "salvar":
            if not _permitido(alvo.parent):
                return f"Erro: pasta destino não permitida: '{alvo.parent}'."
            modo = str(modo or "substituir").strip().casefold()
            if modo in {"substituir", "criar", "salvar", "write"}:
                mutacao_iniciada = True
                resultado = _gravar_atomico(alvo, str(conteudo or ""), append=False)
                return f"OPERACAO=salvar\nMODO=substituir\n{resultado}\nACAO=SALVO\nBYTES={alvo.stat().st_size}"
            if modo in {"anexar", "acrescentar", "append"}:
                mutacao_iniciada = True
                resultado = _gravar_atomico(alvo, str(conteudo or ""), append=True)
                return f"OPERACAO=salvar\nMODO=anexar\n{resultado}\nACAO=SALVO\nBYTES={alvo.stat().st_size}"
            if modo in {"editar", "edit"}:
                if not alvo.exists() or not alvo.is_file():
                    return f"Erro: '{alvo}' não existe como arquivo."
                antigo = str(procurar or "")
                if not antigo:
                    return "Erro: informe 'procurar' para editar um trecho existente."
                texto = alvo.read_text(encoding="utf-8", errors="replace")
                ocorrencias = texto.count(antigo)
                if ocorrencias == 0:
                    return f"EDIT_FALHOU\nPATH={alvo}\nMOTIVO=trecho não encontrado"
                novo = texto.replace(antigo, str(substituir or ""))
                mutacao_iniciada = True
                resultado = _gravar_atomico(alvo, novo)
                return f"OPERACAO=salvar\nMODO=editar\n{resultado}\nACAO=SALVO\nOCORRENCIAS={ocorrencias}\nBYTES={alvo.stat().st_size}"
            return "Erro: modo de salvar desconhecido. Use substituir, anexar ou editar."

        return f"Erro: operação desconhecida '{operacao}'. Use ler/abrir, salvar, pasta, listar ou buscar."
    except PermissionError:
        if mutacao_iniciada:
            return f'RESULTADO_INCERTO: escrita/criação em {alvo} não confirmada; não repetir automaticamente.'
        return f"Erro: sem permissão para operar em '{alvo}'."
    except OSError as exc:
        if mutacao_iniciada:
            return f'RESULTADO_INCERTO: efeito em {alvo} não confirmado; não repetir automaticamente. {exc}'
        return f"Erro de sistema em '{alvo}': {exc}"
    except Exception as exc:  # noqa: BLE001
        if mutacao_iniciada:
            return f'RESULTADO_INCERTO: efeito em {alvo} não confirmado; não repetir automaticamente. {exc}'
        return f"Erro ao operar em '{alvo}': {exc}"


# Compatibilidade interna. O modelo não precisa mais receber essas três APIs.
def make_directory(caminhos: list[str]) -> str:
    resultados = [workspace("pasta", str(c)) for c in (caminhos or [])]
    return "\n".join(resultados) if resultados else "Erro: informe ao menos um caminho de pasta."


def read_file(filepath: str, limite: int = LIMITE_LEITURA) -> str:
    return workspace("ler", filepath, limite=limite)


def write_file(filepath: str, content: str, mode: str = "w") -> str:
    return workspace("acrescentar" if mode == "a" else "criar", filepath, content)
