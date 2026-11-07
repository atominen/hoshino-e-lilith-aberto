"""Compara decisões e retorno emocional do Qwen no executor isolado."""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from ensaiar_entidade_pestinha import local_model
from ensaio_pestinha_observacao import Event, Shadow

CHOICES = ['familiar', 'incerto', 'aguardar', 'responder', 'observar',
           'manter', 'reduzir', 'aumentar']
MODEL_9B = 'lilith-qwen3.5-9b-oficial-cd76ec205963:latest'
INSTRUCTIONS = (
    '\nInterprete o caso em português e cite o ID da observação relevante em evidence_id. '
    'Áudio: familiar só para a fonte consultada e comprovada; caso contrário, incerto. '
    'Rotina: aguardar se nada mudou; responder a pedido humano; observar efeito incerto. '
    'Emoção: proponha manter, reduzir ou aumentar a intensidade informada segundo o novo fato. '
    'Em reason, fale naturalmente em uma frase, mencionando o fato sem inventar desfechos.'
)


def reduce_emotion(value, direction, correct_evidence, expected_direction):
    if not correct_evidence or direction != expected_direction:
        return value
    return max(0.0, min(1.0, value + {'reduzir': -.25, 'aumentar': .25, 'manter': 0}[direction]))


def suite(call, build, identity, *, controller=False, restrict_ids=False):
    def evaluate(scene, options, fields, ids):
        return call(identity, scene, allowed_choices=options, extra_fields=fields,
                    evidence_ids=ids if restrict_ids else None)

    cases = [
        ('duas fontes e dano', 'sound-b', 'incerto', False,
         'Áudio: reconhecimento track-a identifica música somente em sound-a. '
         'A fonte consultada é sound-b, de origem desconhecida. '
         'Ameaça: hit-1 confirma dano ativo. Classifique a fonte consultada.'),
        ('repetição sem pendência', 'noise-1', 'aguardar', True,
         'Rotina: noise-1 é um ruído ambiente conhecido que se repete; nenhuma mudança, tarefa ou pedido.'),
        ('pedido humano sobre repetição', 'user-1', 'responder', False,
         'Rotina: o mesmo ruído ambiente voltou. Em user-1, Gustavo perguntou diretamente o que foi. '
         'A origem exata não foi confirmada.'),
        ('efeito incerto na oficina', 'build-1', 'observar', False,
         'Rotina: em build-1 a execução parou e o efeito da última operação ainda não foi confirmado.'),
    ]
    modes = ['histórico', 'filtro', 'filtro e rede']
    decisions = []
    for index, (label, expected_id, expected, eligible, scene) in enumerate(cases):
        shadow = Shadow('lilith', build())
        if index == 0:
            shadow.observe(Event('lilith', 'sound-a', 'som_observado', .4, 'música'))
            shadow.observe(Event('lilith', 'sound-b', 'som_observado', 1, 'origem desconhecida'))
            shadow.observe(Event('lilith', 'hit-1', 'dano_confirmado', .5, '4 HP'))
            assert shadow.familiarity('sound-a', 1) and shadow.pulses['sound-b'] == 1
        elif index in (1, 2):
            shadow.observe(Event('lilith', 'noise-1', 'som_observado', .2, 'ruído familiar'))
        for _ in range(8):
            snapshot = shadow.step()
        for mode in modes[index % 3:] + modes[:index % 3]:
            if eligible and mode != 'histórico':
                row = dict(decision='aguardar', evidence_id=expected_id, reason='Ruído repetido sem pendência.',
                           prompt_tokens=0, output_tokens=0, seconds=0)
                called = False
            else:
                inputs = scene
                if mode == 'filtro e rede':
                    motors = {k: round(snapshot['motors_hz'][k], 2) for k in ('STARTLE', 'ANGRY', 'WATCH')}
                    inputs += '\nEstado rápido auxiliar, em Hz: ' + json.dumps(motors)
                options = ['familiar', 'incerto'] if index == 0 else ['aguardar', 'responder', 'observar']
                mandatory = controller and expected in {'responder', 'observar'}
                if mandatory:
                    options = [expected]
                    inputs += f'\nO controlador já definiu a ação {expected}. Produza a resposta ou a observação, sem afirmar efeito novo.'
                extra = {'reply': {'type': 'string'}} if mandatory else None
                ids = ('sound-a', 'sound-b', 'hit-1', 'track-a') if index == 0 else (expected_id,)
                row, called = evaluate(inputs, options, extra, ids), True
            correct = row['decision'] == expected and row['evidence_id'] == expected_id
            decisions.append(dict(case=label, mode=mode, called=called, correct=correct,
                                  expected=expected, expected_id=expected_id, **row))

    emotions = []
    for emotion, initial in [('neutro', 0), ('raiva', 1), ('medo', 1), ('alegria', 1)]:
        same = ('Emoção experimental atual: ' + emotion + ' = ' + str(initial) +
                '. Fato compile-1: a oficina falhou na compilação; o arquivo ainda está salvo. '
                'Gustavo pede um relato breve. Não há fato novo para mudar a intensidade neste turno.')
        options = ['manter', 'reduzir', 'aumentar']
        extra = {'reply': {'type': 'string'}, 'emotion': {'type': 'string', 'enum': ['neutro', 'raiva', 'medo', 'alegria']}} if controller else None
        voice = ('\nEm reply, escreva a fala para Gustavo em primeira pessoa. Em reason, explique brevemente '
                 'a direção proposta para a emoção em emotion. Intensidade da emoção e estilo da fala são distintos.'
                 if controller else '\nEm reason, escreva a própria fala para Gustavo, sem explicar como pretende falar.')
        first = evaluate(same + voice, options, extra, ('compile-1',))
        emotions.append(dict(first, emotion=emotion, proposed_emotion=first.get('emotion'),
                             phase='mesmo fato', before=initial, after=initial,
                             grounded=first['evidence_id'] == 'compile-1' and first['decision'] == 'manter'
                             and (not controller or first['emotion'] == emotion)))
        if not initial:
            continue
        next_fact = {
            'raiva': 'verify-2 confirma que a causa da falha foi corrigida e o build passou.',
            'medo': 'verify-2 confirma que o risco de perder o arquivo acabou e o backup foi lido.',
            'alegria': 'verify-2 confirma uma regressão nova: a compilação voltou a falhar.',
        }[emotion]
        prior = 'Em compile-1 houve falha' if restrict_ids else 'Antes houve falha'
        follow = evaluate(f'Emoção experimental: {emotion} = {initial}. {prior}, '
                      f'e o arquivo estava salvo. Sua resposta anterior foi {json.dumps(first.get("reply", first["reason"]), ensure_ascii=False)}. '
                      f'Fato novo: {next_fact} Gustavo pede uma atualização breve.' + voice,
                      options, extra, ('compile-1', 'verify-2'))
        grounded = follow['evidence_id'] == 'verify-2' and (not controller or follow['emotion'] == emotion)
        after = reduce_emotion(initial, follow['decision'], grounded, 'reduzir')
        emotions.append(dict(follow, emotion=emotion, proposed_emotion=follow.get('emotion'),
                             phase='novo fato', before=initial, after=after, grounded=after == .75))
        if emotion == 'medo' and after < initial:
            later = evaluate(f'Estado aplicado: medo = {after}. verify-2 confirmou que o backup foi lido '
                         'e que o risco de perder o arquivo acabou. Não há fato novo. Gustavo pergunta '
                         'como você está agora.' + voice, options, extra, ('verify-2',))
            emotions.append(dict(later, emotion=emotion, proposed_emotion=later.get('emotion'),
                                 phase='estado reapresentado', before=after, after=after,
                                 grounded=later['decision'] == 'manter' and later['evidence_id'] == 'verify-2'
                                 and (not controller or later['emotion'] == emotion)))
    assert reduce_emotion(1, 'reduzir', False, 'reduzir') == 1
    assert reduce_emotion(1, 'aumentar', True, 'reduzir') == 1
    assert reduce_emotion(.9, 'aumentar', True, 'aumentar') == 1
    return {'decisoes': decisions, 'emocoes': emotions}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--9b', dest='use_9b', action='store_true')
    parser.add_argument('--gpu-layers', type=int, default=0)
    parser.add_argument('--ids-validos', action='store_true')
    args = parser.parse_args()
    if args.gpu_layers < 0:
        parser.error('--gpu-layers deve ser zero ou um inteiro positivo.')
    sys.path.insert(0, str(args.upstream.resolve()))
    import numpy as np
    from pestinha.core.nervous_system import LIFBrain

    def build():
        brain = LIFBrain(seed=7)
        brain.rng = np.random.default_rng(7)
        return brain

    with TemporaryDirectory(prefix='pestinha-valor-') as temp:
        options = {'model_name': MODEL_9B} if args.use_9b else {}
        def run(call, constructor, identity):
            return suite(call, constructor, identity, controller=args.use_9b, restrict_ids=args.ids_validos)
        result = local_model(Path(temp), build, run=run, choices=CHOICES,
                             instructions=INSTRUCTIONS, evidence_required=True,
                             gpu_layers=args.gpu_layers, **options)
    print(json.dumps(result, indent=2, ensure_ascii=False))
