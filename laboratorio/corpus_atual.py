"""Corpus de identidade vigente do laboratório: único lugar que diz onde ficam treino, validação e holdout.

06/11/2026 (pedido humano): o material antigo (pacote_neural_v2/v3, pacote_identidade_v4, seed do
Alistair) foi apagado e o v5, escrito à mão, passou a ser o corpus original de cada entidade.
Caminhos relativos ao `home` do laboratório (`laboratorio-local`).
"""
# 08/11/2026 (pedido humano: "a gente só precisa treinar o 9b"): o banco v6 ("super versão") passa a ser o corpus de
# treino. 12/11 (pedido humano "atualize o banco de treinamento"): os exemplos com ferramenta entram no treino, no
# formato real do Qwen3.5 (laboratorio/formato_treino.py, até 768 fichas), mais o aspecto "agir" (pares_agir.txt).
CORPUS = 'pacote_identidade_v6'
ENTIDADES = ('hoshino', 'lilith', 'alistair')
# Corpus que ensinam nome, identidade e costumes: pesos treinados em qualquer um deles já trazem a identidade (o prompt
# de sistema pode ser o reduzido). 08/11: a troca v5 → v6 não devolve o prompt completo aos pesos do v5.
CORPOS_DE_IDENTIDADE = ('pacote_identidade_v5', 'pacote_identidade_v6')


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
