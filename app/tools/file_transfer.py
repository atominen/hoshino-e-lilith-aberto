"""Entrada/saída amigável de arquivos para a interface da Hoshino."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import config


def pasta_downloads_usuario() -> Path:
    """Obtém a pasta Downloads do desktop; cai em ~/Downloads."""
    try:
        p = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=3)
        bruto = p.stdout.strip()
        if bruto:
            return Path(bruto).expanduser()
    except Exception:
        pass
    return Path.home() / "Downloads"


def pasta_entregas_usuario() -> Path:
    p = pasta_downloads_usuario() / config.ENTIDADE_NOME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _nome_livre(pasta: Path, nome: str) -> Path:
    nome = Path(nome).name
    alvo = pasta / nome
    if not alvo.exists():
        return alvo
    base, suf = alvo.stem, alvo.suffix
    n = 2
    while (pasta / f"{base}-{n}{suf}").exists():
        n += 1
    return pasta / f"{base}-{n}{suf}"


def importar_caminhos(caminhos: list[str]) -> str:
    entrada = Path(config.ENTREGA_ENTRADA)
    entrada.mkdir(parents=True, exist_ok=True)
    copiados = []
    falhas = []
    for bruto in caminhos or []:
        origem = Path(os.path.expanduser(str(bruto))).resolve()
        if not origem.is_file():
            falhas.append(f"não achei: {bruto}")
            continue
        try:
            destino = _nome_livre(entrada, origem.name)
            shutil.copy2(origem, destino)
            copiados.append(destino.name)
        except OSError as exc:
            falhas.append(f"{origem.name}: {exc}")
    partes = []
    if copiados:
        partes.append(f"Importei para a caixa da {config.ENTIDADE_NOME}: {', '.join(copiados)}")
    if falhas:
        partes.append("Falhas: " + "; ".join(falhas))
    return "\n".join(partes) if partes else "Nenhum arquivo importado."



def importar_url(url: str, nome: str = "", max_mb: int = 100) -> str:
    """Baixa um anexo remoto autorizado para a caixa de entrada da Hoshino."""
    alvo_url = (url or "").strip()
    if not alvo_url.startswith(("http://", "https://")):
        return "Erro: só importo anexos por http/https."
    try:
        from core import rede
        pode, recusa = rede.exigir("baixar anexo", url=alvo_url)
        if not pode:
            return recusa
        import requests
        resposta = requests.get(alvo_url, stream=True, timeout=20)
        resposta.raise_for_status()
        tamanho = int(resposta.headers.get("Content-Length") or 0)
        teto = int(max_mb) * 1024 * 1024
        if tamanho and tamanho > teto:
            return f"Anexo recusado: {tamanho/1048576:.1f} MB > limite de {max_mb} MB."
        pasta = Path(config.ENTREGA_ENTRADA)
        pasta.mkdir(parents=True, exist_ok=True)
        nome_url = Path(alvo_url.split("?", 1)[0]).name
        nome_final = Path(nome or nome_url or "anexo").name
        destino = _nome_livre(pasta, nome_final)
        total = 0
        with destino.open("wb") as out:
            for pedaco in resposta.iter_content(chunk_size=256 * 1024):
                if not pedaco:
                    continue
                total += len(pedaco)
                if total > teto:
                    out.close()
                    destino.unlink(missing_ok=True)
                    return f"Anexo recusado: passou de {max_mb} MB durante o download."
                out.write(pedaco)
        return f"Anexo importado: {destino.name} ({total/1024:.0f} KB)."
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui importar o anexo: {type(exc).__name__}: {exc}"


def selecionar_arquivos() -> list[str]:
    """Abre seletor gráfico de arquivos. Zenity é o caminho preferido no Mint/Cinnamon."""
    comandos = [
        ["zenity", "--file-selection", "--multiple", "--separator=\n",
         f"--title=Enviar arquivos para {config.ENTIDADE_NOME}"],
        ["kdialog", "--getopenfilename", str(Path.home()), "*"] ,
    ]
    for cmd in comandos:
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception:
            continue
        if r.returncode != 0:
            return []
        return [x.strip() for x in r.stdout.splitlines() if x.strip()]
    return []


def enviar_do_seletor() -> str:
    arquivos = selecionar_arquivos()
    if not arquivos:
        return "Seleção cancelada ou nenhum seletor gráfico disponível."
    return importar_caminhos(arquivos)


def abrir_entregas() -> str:
    pasta = pasta_entregas_usuario()
    try:
        subprocess.Popen(["xdg-open", str(pasta)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return f"Abri a pasta de entregas da {config.ENTIDADE_NOME}: {pasta}"
    except Exception as exc:
        return f"Não consegui abrir a pasta de entregas: {exc}"


def sincronizar_saida_usuario(caminho: str) -> str:
    origem = Path(os.path.expanduser(caminho)).resolve()
    if not origem.is_file():
        return f"Arquivo não encontrado: {caminho}"
    destino = _nome_livre(pasta_entregas_usuario(), origem.name)
    try:
        shutil.copy2(origem, destino)
    except OSError as exc:
        return f"Não consegui copiar para Downloads/{config.ENTIDADE_NOME}: {exc}"
    return f"Arquivo disponível em {destino}"
