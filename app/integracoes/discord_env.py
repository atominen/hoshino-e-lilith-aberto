"""Leitura restrita do arquivo local de configuração do Discord.

O arquivo contém um segredo e não deve ser executado como script shell. Só as
chaves usadas pelo adaptador são aceitas; valores são texto literal, sem expansão
de comandos, variáveis ou substituições.
"""
from __future__ import annotations

from pathlib import Path

CHAVES_PERMITIDAS = {
    "HOSHINO_DISCORD_TOKEN",
    "HOSHINO_DISCORD_NOTIFICACOES",
    "HOSHINO_DISCORD_CONTATOS",
    "HOSHINO_DISCORD_CANAIS",
}


def carregar(caminho: str) -> tuple[dict[str, str], list[str]]:
    valores: dict[str, str] = {}
    avisos: list[str] = []
    try:
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return valores, [f"não consegui ler o arquivo: {exc}"]
    for numero, bruto in enumerate(linhas, 1):
        linha = bruto.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("export "):
            linha = linha[7:].lstrip()
        if "=" not in linha:
            avisos.append(f"linha {numero} ignorada: não é chave=valor")
            continue
        chave, valor = (parte.strip() for parte in linha.split("=", 1))
        if chave not in CHAVES_PERMITIDAS:
            avisos.append(f"linha {numero} ignorada: chave não permitida")
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in {"'", '"'}:
            valor = valor[1:-1]
        valores[chave] = valor
    return valores, avisos
