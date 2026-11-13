"""Os pesos em uso já trazem a identidade? (pedido humano 06/11)

Um candidato treinado no corpus de identidade vigente (`laboratorio/corpus_atual.py`)
aprendeu nome, voz e regras básicas. Repetir tudo isso no prompt de sistema gasta
contexto e, pior, empurra o modelo de volta para as instruções antigas. Este módulo
só responde à pergunta; quem decide o tamanho do prompt é `core.prompting`.

A resposta vem da seleção pinada da Central (`neural9b_modes`), do alias que o
processo realmente carregou e do registro do job de treino. Sem essas três coisas
batendo, a resposta é "não": o prompt completo continua sendo o padrão seguro.

`HOSHINO_PROMPT_IDENTIDADE` força o modo para comparação (A/B):
`completo`, `reduzido` ou `auto` (padrão).
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import config

MODOS = ('auto', 'completo', 'reduzido')


def _job(home: Path, ref: str) -> dict:
    jid = str(ref).split(':', 1)[0]
    if not jid or '/' in jid or jid.startswith('.'):
        return {}
    path = home / 'controle-laboratorio' / 'treinamento-unificado' / 'jobs' / (jid + '.json')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=8)
def _detectar(entidade: str, modelo_carregado: str) -> dict:
    from core import neural9b_modes
    raiz = Path(config.RAIZ)
    home = Path(os.environ.get('HOSHINO_LAB_HOME') or raiz / 'laboratorio-local')
    try:
        familia = neural9b_modes.primary_family(raiz, entidade)
        selecionada = neural9b_modes.selected_version(raiz, entidade, familia) if familia else None
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if not selecionada or selecionada.get('alias') != modelo_carregado:
        return {}
    if selecionada.get('kind') not in ('trained', 'checkpoint'):
        return {}
    job = _job(home, selecionada.get('ref', ''))
    dataset = str((job.get('plan') or {}).get('dataset') or '')
    if job.get('entity') != entidade or job.get('action') != 'train' or job.get('state') != 'completed':
        return {}
    try:
        from laboratorio import corpus_atual
    except ImportError:
        return {}
    corpo, _, dono = dataset.partition(':')
    if corpo not in getattr(corpus_atual, 'CORPOS_DE_IDENTIDADE', (corpus_atual.CORPUS,)) or dono != entidade:
        return {}
    return dict(corpus=corpo, treino=job.get('id'), versao=selecionada.get('kind'), alias=modelo_carregado)


def identidade_nos_pesos() -> dict:
    """Dados do treino quando os pesos carregados aprenderam a identidade vigente.

    Vazio = prompt completo. Nunca levanta exceção: na dúvida, o prompt é o completo.
    """
    modo = os.environ.get('HOSHINO_PROMPT_IDENTIDADE', 'auto').strip().casefold()
    if modo == 'completo':
        return {}
    if modo == 'reduzido':
        return dict(corpus='forcado', treino=None, versao='forcado', alias=config.MODEL_NAME)
    try:
        return dict(_detectar(config.ENTIDADE_ID, config.MODEL_NAME))
    except Exception:  # noqa: BLE001
        return {}
