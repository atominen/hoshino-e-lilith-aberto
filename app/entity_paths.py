"""Localiza dados de uma entidade sem abrir bancos nem criar diretórios.

Cada processo seleciona uma entidade na inicialização. O código e os modelos
podem ser comuns; identidade, memória e estado nunca fazem fallback entre elas.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class EntidadePaths:
    id: str
    nome: str
    raiz: Path
    identity: Path
    memory: Path
    runtime: Path
    workspace: Path
    config: Path


def carregar_entidade(raiz: Path, entidade_id: str) -> EntidadePaths:
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", entidade_id or ""):
        raise ValueError("Identificador de entidade inválido.")
    entidades = (Path(raiz).resolve() / "entidades").resolve()
    pasta = (entidades / entidade_id).resolve()
    if pasta.parent != entidades:
        raise ValueError("A entidade precisa ter uma pasta própria em entidades/.")
    manifesto = json.loads((pasta / "entidade.json").read_text(encoding="utf-8"))
    if manifesto.get("id") != entidade_id:
        raise ValueError("Identificador do manifesto não corresponde à pasta da entidade.")
    if manifesto.get("status") != "ativa":
        raise ValueError(f"A entidade {entidade_id} está reservada e ainda não foi configurada para iniciar.")
    nome = manifesto.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        raise ValueError("Manifesto sem nome da entidade.")
    caminhos = {chave: pasta / chave for chave in
                ("identity", "memory", "runtime", "workspace", "config")}
    for caminho in caminhos.values():
        if not caminho.resolve().is_relative_to(pasta):
            raise ValueError("Dados da entidade apontam para fora de sua pasta.")
    return EntidadePaths(entidade_id, nome, pasta, **caminhos)
