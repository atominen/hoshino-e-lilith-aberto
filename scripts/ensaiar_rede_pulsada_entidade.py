"""Reproduz o núcleo e o classificador emocional originais em CPU, sem desktop."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time

STEP_MS = 100


def run(upstream, trials):
    sys.path.insert(0, str(upstream.resolve()))
    import numpy as np
    from pestinha.core.nervous_system import LIFBrain
    from pestinha.core.emotion import EmotionState

    bryan = json.loads((upstream / 'pets/bryan.json').read_text())
    # Amplitudes e decaimentos de ComputerSenses; WORK/TYPING e SOUND
    # seguem a demonstração headless do upstream.
    cases = [
        ('original', 'repouso', {}, {}),
        ('original', 'troca de janela', {}, {'MOTION': (0.75, 2.0)}),
        ('original', 'retorno do usuário', {}, {'NOVELTY': (1.0, 3.0)}),
        ('original', 'cutucada', {}, {'POKE': (0.8, 1.5)}),
        ('original', 'batida forte', {}, {'IMPACT': (0.5, 4.0)}),
        ('original', 'trabalho', {'WORK': 1.0, 'TYPING': 0.8}, {}),
        ('original', 'música', {'SOUND': 1.0}, {}),
        ('adaptação', 'dano confirmado no Minecraft', {}, {'IMPACT': (0.5, 4.0)}),
        ('adaptação', 'som ambíguo', {'SOUND': 1.0}, {'NOVELTY': (1.0, 3.0)}),
        ('adaptação', 'som familiar', {'SOUND': 1.0}, {}),
        ('adaptação', 'falha repetida de compilação', {'WORK': 1.0}, {'DISMISS': (0.7, 6.0)}),
    ]
    # Perfil "normal" do app, em vez dos tempos acelerados do modo teste.
    profile = dict(emotion_tau=5.0, emotion_dwell=1.5)
    results = []
    for group, label, sustained, pulses in cases:
        rows = []
        for seed in range(trials):
            brain = LIFBrain(seed=bryan['seed'], temperament=bryan['temperamento'])
            # A topologia permanece a do Bryan. Só o ruído recebe sementes
            # controladas, para comparar os mesmos estímulos entre rodadas.
            brain.rng = np.random.default_rng(seed)
            emotion = EmotionState()
            emotion.since = 0
            peaks, transitions, samples, costs = {}, [], {}, []
            previous = 'observando'
            for frame in range(101):
                relative = (frame - 20) * STEP_MS / 1000
                active = 0 <= relative < 4
                inputs = dict(sustained) if active else {}
                if active:
                    inputs.update({key: strength * math.exp(-relative / decay)
                                   for key, (strength, decay) in pulses.items()})
                started = time.perf_counter_ns()
                brain.stimulate(inputs)
                brain.step(STEP_MS)
                costs.append((time.perf_counter_ns() - started) / 1e6)
                motors = brain.motor_activity()
                emotion.update(motors, STEP_MS / 1000, profile, now=frame * STEP_MS / 1000)
                if relative < 0:
                    continue
                for name, hz in motors.items():
                    peaks[name] = max(peaks.get(name, 0), hz)
                if emotion.current != previous:
                    transitions.append([relative, emotion.current])
                    previous = emotion.current
                if relative in (1, 4, 8):
                    samples[str(relative)] = [emotion.current, round(emotion.valence, 3), round(emotion.arousal, 3)]
            rows.append(dict(seed=seed, peaks_hz=peaks, transitions=transitions,
                             samples=samples, median_cpu_ms=statistics.median(costs)))
        results.append(dict(group=group, case=label, trials=rows))
    # Estímulos idênticos produzem a mesma resposta. Os nomes da situação
    # não chegam ao núcleo, portanto não criam uma distinção por si só.
    for original, adapted in ((4, 7), (6, 9)):
        for a, b in zip(results[original]['trials'], results[adapted]['trials']):
            assert (a['peaks_hz'], a['transitions'], a['samples']) == (b['peaks_hz'], b['transitions'], b['samples'])
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--trials', type=int, default=8)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error('Informe pelo menos uma repetição.')
    print(json.dumps(run(args.upstream, args.trials), ensure_ascii=False, indent=2))
