"""Estado psicológico adaptativo de médio prazo.

Não substitui identidade, personalidade ou humor. Guarda tendências que mudam
mais devagar e influenciam decisão apenas de forma proporcional.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime

import config
from core import state_file, history

BASE = {
    "seguranca_relacional": 0.50,
    "proximidade_social": 0.50,
    "autoeficacia": 0.50,
    "estresse_acumulado": 0.10,
    "carga_nao_resolvida": 0.00,
    "novidade_mental": 0.20,
}
HALF_LIVES_MIN = {
    "seguranca_relacional": 4320.0,
    "proximidade_social": 2880.0,
    "autoeficacia": 2880.0,
    "estresse_acumulado": 720.0,
    "carga_nao_resolvida": 1440.0,
    "novidade_mental": 240.0,
}
EVENTS = {
    "usuario_voltou": {"seguranca_relacional": 0.03, "proximidade_social": 0.05},
    "usuario_chegou_perto": {"proximidade_social": 0.04},
    "conversa_boa": {"seguranca_relacional": 0.025, "proximidade_social": 0.025},
    "elogio": {"autoeficacia": 0.025, "seguranca_relacional": 0.015},
    "critica": {"seguranca_relacional": -0.025, "estresse_acumulado": 0.03},
    "desentendimento": {"seguranca_relacional": -0.05, "estresse_acumulado": 0.05, "carga_nao_resolvida": 0.08},
    "ignorada": {"seguranca_relacional": -0.02, "estresse_acumulado": 0.015},
    "tarefa_sucesso": {"autoeficacia": 0.04, "estresse_acumulado": -0.025, "carga_nao_resolvida": -0.06},
    "tarefa_falhou": {"autoeficacia": -0.03, "estresse_acumulado": 0.04, "carga_nao_resolvida": 0.08},
    "tarefa_falhou_de_novo": {"autoeficacia": -0.05, "estresse_acumulado": 0.07, "carga_nao_resolvida": 0.10},
    "descoberta": {"novidade_mental": 0.12, "autoeficacia": 0.015},
    "curiosidade_frustrada": {"novidade_mental": -0.03, "estresse_acumulado": 0.02},
    "curiosidade_saciada": {"novidade_mental": 0.04},
    "reflexao_boa": {"carga_nao_resolvida": -0.08, "estresse_acumulado": -0.025},
    "amizade_avancou": {"seguranca_relacional": 0.04, "proximidade_social": 0.06},
}


def _path() -> str:
    return os.path.join(config.RUNTIME_DIR, "estado_psicologico.json")


def _ler() -> dict:
    return state_file.read(_path())


def _gravar(dados: dict) -> bool:
    return state_file.update(_path(), lambda atual: atual.update(dados), 'psych_state.write')


def estado(agora: datetime | None = None, *, dados=None) -> dict:
    agora = agora or history.local_now()
    dados = _ler() if dados is None else dados
    atualizado = dados.get("atualizado_em")
    decorrido = history.elapsed_seconds(atualizado, agora, operation='psych_state.decay') if atualizado is not None else 0.
    minutos = (decorrido if decorrido is not None else 0.) / 60.
    out = {}
    for nome, base in BASE.items():
        val = float(dados.get(nome, base))
        fator = 0.5 ** (minutos / HALF_LIVES_MIN[nome])
        out[nome] = round(base + (val - base) * fator, 4)
    out["atualizado_em"] = history.utc_timestamp(agora)
    return out


def aplicar_evento(evento: str, intensidade: float = 1.0, agora: datetime | None = None) -> dict:
    agora = agora or history.local_now()
    fator = float(1.0 if intensidade is None else intensidade)
    if not math.isfinite(fator):
        raise ValueError('Intensidade deve ser finita.')
    fator = max(0.0, min(2.0, fator))
    resultado = {}
    def mutate(dados):
        atual = estado(agora, dados=dados)
        for nome, variacao in EVENTS.get(str(evento or ''), {}).items():
            atual[nome] = round(max(0.0, min(1.0, atual[nome] + variacao * fator)), 4)
        atual['ultimo_evento'] = str(evento or '')
        dados.update(atual)
        resultado.update(atual)
    persisted = state_file.update(_path(), mutate, 'psych_state.apply')
    if not persisted:
        resultado = estado(agora)
    return dict(resultado, persisted=persisted)


def influencia() -> dict:
    e = estado()
    return {
        "curiosidade": 0.75 + 0.35 * e["novidade_mental"],
        "conexao": 0.75 + 0.35 * e["proximidade_social"],
        "competencia": 0.70 + 0.45 * e["autoeficacia"],
        "coerencia": 0.85 + 0.35 * e["carga_nao_resolvida"],
        "cuidado": 0.90 + 0.25 * e["estresse_acumulado"],
    }


def bloco_para_prompt() -> str:
    e = estado()
    relevante = any(abs(e[n] - BASE[n]) >= 0.08 for n in BASE)
    if not relevante:
        return ""
    return (
        "[DINÂMICA INTERNA DE MÉDIO PRAZO]\n"
        f"segurança_relacional={e['seguranca_relacional']:.2f}; "
        f"proximidade={e['proximidade_social']:.2f}; "
        f"autoeficácia={e['autoeficacia']:.2f}; "
        f"estresse={e['estresse_acumulado']:.2f}; "
        f"carga_não_resolvida={e['carga_nao_resolvida']:.2f}; "
        f"novidade_mental={e['novidade_mental']:.2f}.\n"
        "Isto é estado adaptativo, não identidade fixa. Use-o para ajustar prioridades "
        "e interpretação; não o narre como ficha de personagem.")
