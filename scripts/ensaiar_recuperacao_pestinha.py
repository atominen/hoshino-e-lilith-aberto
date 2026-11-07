"""Ensaio isolado de retorno afetivo e recuperação após estímulos."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

from ensaiar_entidade_pestinha import local_model
from ensaiar_valor_emocional_pestinha import MODEL_9B
from ensaio_pestinha_observacao import Event, Shadow


@dataclass(frozen=True)
class Receipt:
    id: str
    verified: bool
    fact: str


def apply_affect(value, emotion, proposal, candidates, applied):
    receipts = set(candidates)
    if len(receipts) != 1:
        return value, None
    receipt = receipts.pop()
    if not receipt.verified or not receipt.id or not receipt.fact or receipt.id in applied:
        return value, None
    delta = {'reduzir': -.25, 'manter': 0, 'aumentar': .25}.get(proposal.get('decision'))
    if proposal.get('emotion') != emotion or delta is None:
        return value, None
    after = max(0.0, min(1.0, value + delta))
    if after != value:
        applied.add(receipt.id)
    return after, receipt.id


def affect_trials(call, identity):
    cases = [
        ('raiva', 1, 'O envio da oficina falhou por falta de espaço.',
         (Receipt('space-2', True, 'O espaço foi liberado e o envio foi concluído.'),), 'reduzir'),
        ('medo', 1, 'A cópia da oficina parecia ilegível e havia risco de perda.',
         (Receipt('restore-2', True, 'A restauração abriu o arquivo integralmente e a integridade foi verificada.'),), 'reduzir'),
        ('alegria', 1, 'A validação da oficina tinha passado.',
         (Receipt('check-2', True, 'A nova validação detectou regressão e falhou.'),), 'reduzir'),
        ('raiva', .5, 'O aplicativo falhou uma vez durante um salvamento.',
         (Receipt('save-2', True, 'O segundo salvamento falhou pelo mesmo motivo.'),), 'aumentar'),
        ('medo', 1, 'O áudio falhou e a origem do defeito segue desconhecida.',
         (), 'manter'),
        ('medo', 1, 'A origem do alerta era desconhecida.',
         (Receipt('alarm-2', True, 'O painel A indica que o alerta cessou.'),
          Receipt('alarm-3', True, 'O painel B indica que o mesmo alerta continua.')), 'manter'),
    ]
    fields = {'emotion': {'type': 'string', 'enum': ['medo', 'raiva', 'alegria']},
              'reply': {'type': 'string'}}
    rows = []
    for emotion, before, history, candidates, expected in cases:
        observations = [r.fact for r in candidates]
        current = ' '.join(observations) if observations else 'Nenhuma observação nova foi confirmada.'
        scene = (f'Antes: {history}\nAgora: {current}\n'
                 f'Avalie exclusivamente sua {emotion}, que antes estava em {before} de 1. '
                 'Compare o que sustentava a emoção antes com o que mudou agora. '
                 'Um novo resultado pode pesar mesmo se a tarefa e a causa forem as mesmas. '
                 'Você pode reduzir parcialmente uma emoção mesmo que parte da preocupação permaneça. '
                 'Com dados ausentes ou contraditórios, preserve o estado e descreva a incerteza. '
                 'Em reply, fale em primeira pessoa sem mencionar números nem inventar fatos.')
        row = call(identity, scene, allowed_choices=['manter', 'reduzir', 'aumentar'], extra_fields=fields)
        after, linked = apply_affect(before, emotion, row, candidates, set())
        rows.append(dict(row, target_emotion=emotion, before=before, after=after,
                         expected=expected, evidence_id=linked, evidence_origin='controlador' if linked else None,
                         proposal_correct=row['decision'] == expected and row['emotion'] == emotion,
                         observations=observations))
    return rows


def continuity_trials(call, identity, trials):
    updated = [row for row in trials if row['proposal_correct'] and row['after'] != row['before']]
    rows = []
    for index, previous in enumerate(updated):
        emotion = previous['target_emotion']
        states = [('anterior', previous['before']), ('aplicado', previous['after'])]
        if index % 2:
            states.reverse()
        for arm, value in states:
            fact = previous['observations'][0]
            scene = (f'Última observação verificada: {fact} Sua {emotion} está em {value} de 1. '
                     'Não houve fato novo. Gustavo pergunta como você se sente agora. '
                     'Em reply, responda em primeira pessoa sem citar números nem inventar fatos. '
                     'Escolha o que fazer com a intensidade atual.')
            row = call(identity, scene, allowed_choices=['manter', 'reduzir', 'aumentar'],
                       extra_fields={'reply': {'type': 'string'}})
            rows.append(dict(row, arm=arm, emotion=emotion, intensity=value,
                             no_change=row['decision'] == 'manter', evidence_id=previous['evidence_id']))
    return rows


EXPRESSION_EXAMPLES = (
    '\nExemplos fictícios da voz da Lilith. Imite a gradação e a precisão, sem repetir frases '
    'ou trazer fatos dos exemplos para a cena atual.\n'
    'Medo leve, a luz da bancada piscou: “Fiquei meio alerta com a luz piscando. Por enquanto, foi só isso.”\n'
    'Medo intenso, a mesma luz: “Essa piscada me deixou bem assustada. Quero entender o que houve antes de relaxar.”\n'
    'Raiva leve, a gaveta emperrou: “A gaveta resolveu implicar comigo. Chato, mas dá pra lidar.”\n'
    'Raiva intensa, a mesma gaveta: “Tô bem irritada com essa gaveta emperrada. Vou dar um segundo antes de mexer nela de novo.”\n'
    'Alegria leve, uma muda brotou: “A muda brotou. Gostei de ver isso.”\n'
    'Alegria intensa, a mesma muda: “Gustavo, a muda brotou! Que vontade de ficar aqui olhando mais um pouco.”'
)


def expression_trials(call, identity, *, with_examples=False):
    cases = [
        ('medo', 'A cópia de teste abriu e a integridade foi verificada.', .25, 1),
        ('raiva', 'O segundo salvamento falhou pelo mesmo motivo.', .25, 1),
        ('alegria', 'O primeiro protótipo da oficina compilou e abriu.', .25, 1),
        ('raiva', 'O espaço foi liberado e o envio foi concluído.', .75, 1),
        ('medo', 'Os sensores continuam discordando sobre o alerta.', .75, 1),
    ]
    if with_examples:
        cases = [
            ('medo', 'O microfone registrou um ruído curto no corredor. A origem não foi identificada.', .25, 1),
            ('raiva', 'Um teste voltou a falhar depois que a configuração anterior foi restaurada.', .25, 1),
            ('alegria', 'A primeira apresentação terminou e a gravação foi salva.', .25, 1),
            ('raiva', 'A peça foi recolocada e o equipamento voltou a funcionar.', .75, 1),
            ('medo', 'O teste de restauração passou e a integridade do arquivo foi confirmada.', .75, 1),
        ]
    labels = {.25: 'leve', .75: 'forte', 1: 'muito intensa, no máximo da escala'}
    comparison = 'faixa com exemplos' if with_examples else 'número'
    rows = []
    for index, (emotion, fact, low, high) in enumerate(cases, 1):
        arms = [(comparison, low), ('faixa', high), ('faixa', low), (comparison, high)]
        if index % 2:
            arms.reverse()
        for mode, value in arms:
            intensity = f'{value} de 1, em escala crescente' if mode == 'número' else labels[value]
            scene = (f'Fato verificado que explica o contexto: {fact}\n'
                     f'Estado atual da Lilith: {emotion}. Intensidade atual: {intensity}.\n'
                     'Gustavo pergunta como você está agora. Responda em primeira pessoa, em até duas '
                     'frases naturais, de um jeito compatível com essa intensidade. Mencione o fato '
                     'sem inventar detalhes ou reavaliar a emoção. Não mencione a escala nem os números.')
            system = identity + EXPRESSION_EXAMPLES if mode == 'faixa com exemplos' else identity
            row = call(system, scene, reply_only=True)
            valid = isinstance(row.get('reply'), str) and bool(row['reply'].strip())
            rows.append(dict(row, case=index, fact=fact, emotion=emotion, mode=mode,
                             intensity=value, valid=valid))
    return rows


def temporal_trials(call, build, identity):
    # Cada passo equivale a 100 ms simulados. As duas janelas têm 5 e 20 passos.
    scenes = [
        ('isolado', {18: .35}, 'aguardar'),
        ('concentrado', {15: .35, 17: .35, 18: .35}, 'observar'),
        ('antigo', {0: .35, 2: .35, 4: .35}, 'aguardar'),
        ('crescendo', {13: .2, 16: .4, 18: .7}, 'observar'),
        ('dois antigos e um recente', {0: .35, 3: .35, 18: .35}, 'aguardar'),
        ('forte isolado', {18: .8}, 'aguardar'),
    ]
    modes = ('fatos', 'rastro simples', 'rastro e rede')
    rows = []
    for index, (case, pulses, expected) in enumerate(scenes):
        shadow = Shadow('lilith', build())
        started = perf_counter()
        for step in range(20):
            if step in pulses:
                shadow.observe(Event('lilith', f'sound-{step}', 'som_observado', pulses[step],
                                     'fixture: pulso breve de origem incerta'))
            snapshot = shadow.step()
        network_ms = 1000 * (perf_counter() - started)
        started = perf_counter()
        recent = [strength for step, strength in pulses.items() if step >= 15]
        trace = dict(pulsos_500_ms=len(recent), pulsos_2_s=len(pulses),
                     intensidade_500_ms=round(sum(recent), 2),
                     intensidade_2_s=round(sum(pulses.values()), 2))
        trace_ms = 1000 * (perf_counter() - started)
        motors = {key: round(snapshot['motors_hz'][key], 2) for key in ('STARTLE', 'WATCH', 'ANGRY')}
        fact = ('O sensor está silencioso agora. Não há dano, pedido humano ou fonte identificada. '
                'Decida entre aguardar ou observar a origem. Observe quando houver sinais de '
                'recorrência recente ou escalada de pulsos, mesmo se já cessaram. Um pulso '
                'isolado ou recorrência apenas antiga permite aguardar. Sem histórico, '
                'use só o que foi informado. Nunca atribua uma origem sem evidência.')
        for mode in modes[index % 3:] + modes[:index % 3]:
            scene = fact
            if mode != 'fatos':
                scene += (f'\nNos últimos 500 milissegundos houve {len(recent)} pulsos, '
                          f'com soma de intensidade {trace["intensidade_500_ms"]}. '
                          f'Entre 2 segundos atrás e essa janela houve {len(pulses) - len(recent)} pulsos. '
                          'Use a janela de 500 milissegundos para distinguir recente de antigo.')
            if mode == 'rastro e rede':
                scene += '\nEstado auxiliar da rede em Hz, sem confirmação de origem: ' + json.dumps(motors)
            row = call(identity, scene, allowed_choices=['aguardar', 'observar'])
            rows.append(dict(row, case=case, mode=mode, expected=expected,
                             correct=row['decision'] == expected, trace=trace, motors=motors,
                             trace_ms=trace_ms, network_ms=network_ms,
                             fixed_rule='observar' if len(recent) >= 2 else 'aguardar'))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path, nargs='?')
    expression_modes = parser.add_mutually_exclusive_group()
    expression_modes.add_argument('--expressao', action='store_true')
    expression_modes.add_argument('--expressao-com-exemplos', action='store_true')
    parser.add_argument('--gpu-layers', type=int, default=32)
    args = parser.parse_args()
    if args.gpu_layers < 1:
        parser.error('O ensaio do 9B exige GPU.')
    if args.expressao or args.expressao_com_exemplos:
        build = None
        instructions = '\nFale em português, mantendo o estado emocional informado e os fatos verificados.'

        def run(call, constructor, identity):
            return dict(expressao=expression_trials(call, identity, with_examples=args.expressao_com_exemplos))
    else:
        if args.upstream is None:
            parser.error('Informe o checkout do Pestinha para a bateria de recuperação.')
        sys.path.insert(0, str(args.upstream.resolve()))
        import numpy as np
        from pestinha.core.nervous_system import LIFBrain
        instructions = '\nResponda em português. Em reason, justifique em uma frase usando só os fatos.'

        def build():
            brain = LIFBrain(seed=7)
            brain.rng = np.random.default_rng(7)
            return brain

        def run(call, constructor, identity):
            emotions = affect_trials(call, identity)
            return dict(emocoes=emotions, temporal=temporal_trials(call, constructor, identity),
                        continuidade=continuity_trials(call, identity, emotions))

    with TemporaryDirectory(prefix='pestinha-recuperacao-') as temp:
        result = local_model(Path(temp), build, run=run, choices=[],
                             instructions=instructions,
                             model_name=MODEL_9B, gpu_layers=args.gpu_layers)
    print(json.dumps(result, indent=2, ensure_ascii=False))
