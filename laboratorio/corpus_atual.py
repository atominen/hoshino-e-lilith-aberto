"""Corpus de identidade vigente do laboratório: único lugar que diz onde ficam treino, validação e holdout.

06/11/2026 (pedido humano): o material antigo (pacote_neural_v2/v3, pacote_identidade_v4, seed do
Alistair) foi apagado e o v5, escrito à mão, passou a ser o corpus original de cada entidade.
Caminhos relativos ao `home` do laboratório (`laboratorio-local`).
"""
CORPUS = 'pacote_identidade_v5'
ENTIDADES = ('hoshino', 'lilith', 'alistair')


def _checar(entity):
    if entity not in ENTIDADES:
        raise ValueError('Entidade inválida')


def dataset_id(entity):
    """Identificador do corpus original da entidade no catálogo (`allowed_data`)."""
    _checar(entity)
    return f'{CORPUS}:{entity}'


def treino(entity):
    _checar(entity)
    return f'{CORPUS}/{entity}_train.jsonl'


def validacao(entity):
    _checar(entity)
    return f'{CORPUS}/{entity}_validation.jsonl'


def holdout(entity):
    """Teste separado: escrito à parte e conferido contra treino/validação pelo montador."""
    _checar(entity)
    return f'{CORPUS}/{entity}_holdout.jsonl'


def entidade_do_corpus(dataset):
    """Entidade dona de um corpus original (`pacote_...:<entidade>`), ou None."""
    if not isinstance(dataset, str) or not dataset.startswith('pacote_') or ':' not in dataset:
        return None
    stem = dataset.split(':', 1)[1]
    return next((e for e in ENTIDADES if stem.startswith(e)), None)
