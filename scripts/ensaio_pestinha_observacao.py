"""Adaptador experimental em memória. Sem ponte ativa, ferramentas ou ações."""
import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


@dataclass(frozen=True)
class Event:
    entity: str
    id: str
    kind: str
    strength: float
    evidence: str


class Shadow:
    CHANNELS = {
        'dano_confirmado': ('IMPACT', 4.0),
        'impacto_simulado': ('IMPACT', 4.0),
        'som_observado': ('NOVELTY', 3.0),
    }

    def __init__(self, entity, brain):
        self.entity = entity
        self.brain = brain
        self.events = {}
        self.pulses = {}
        self.threats = set()
        self.interpreted = set()

    def observe(self, event):
        if (event.entity != self.entity or event.kind not in self.CHANNELS
                or not event.id or not event.evidence or not 0 < event.strength <= 1):
            raise ValueError('Evento incompatível com a sessão experimental.')
        previous = self.events.get(event.id)
        if previous is not None:
            if previous != event:
                raise ValueError('ID de evento reaproveitado com outros dados.')
            return False
        self.events[event.id] = event
        self.pulses[event.id] = event.strength
        if event.kind == 'dano_confirmado':
            self.threats.add(event.id)
        return True

    def familiarity(self, event_id, confidence):
        event = self.events.get(event_id)
        if (event is None or event.kind != 'som_observado' or event_id in self.interpreted
                or not 0 <= confidence <= 1):
            return False
        # Ajuste de atenção, não mudança dos fatos ou das permissões.
        self.pulses[event_id] *= 1 - min(0.25, confidence * 0.25)
        self.interpreted.add(event_id)
        return True

    def clear_threat(self, event_id, verified):
        if verified is True and event_id in self.threats:
            self.threats.remove(event_id)
            return True
        return False

    def step(self):
        inputs = {}
        for event_id, level in self.pulses.items():
            channel, decay = self.CHANNELS[self.events[event_id].kind]
            inputs[channel] = min(1.0, inputs.get(channel, 0) + level)
            self.pulses[event_id] = level * math.exp(-0.1 / decay)
        self.brain.stimulate(inputs)
        self.brain.step(100)
        return {'inputs': inputs, 'motors_hz': self.brain.motor_activity(),
                'ameaças_confirmadas': sorted(self.threats)}


def exercise(build_brain):
    hit = Event('lilith', 'hit-1', 'dano_confirmado', 0.5, 'fixture: vida 20→16')
    impact = Event('lilith', 'impact-1', 'impacto_simulado', 0.5, 'fixture: impacto sem dano')
    sound = Event('lilith', 'sound-1', 'som_observado', 1, 'fixture: evento acústico')
    damage, control, other = (Shadow(owner, build_brain()) for owner in ('lilith', 'lilith', 'hoshino'))
    assert damage.observe(hit) and not damage.observe(hit)
    assert control.observe(impact)
    a, b = damage.step(), control.step()
    assert a['inputs'] == b['inputs'] and a['motors_hz'] == b['motors_hz']
    assert a['ameaças_confirmadas'] == [hit.id] and b['ameaças_confirmadas'] == []
    try:
        other.observe(hit)
    except ValueError:
        assert not other.events
    else:
        raise AssertionError('Evento aceito na entidade errada.')
    assert damage.observe(sound)
    assert damage.familiarity(sound.id, 1)
    assert not damage.familiarity(sound.id, 1) and not damage.familiarity(hit.id, 1)
    after = damage.step()
    assert after['inputs']['NOVELTY'] == .75
    assert after['ameaças_confirmadas'] == [hit.id]
    assert not damage.clear_threat(hit.id, False)
    assert damage.clear_threat(hit.id, True)
    # Os resultados abaixo são registros fornecidos pela fixture. O adaptador
    # não emite ordens nem transforma uma tentativa em ação confirmada.
    receipts = [
        {'action': 'recuar', 'status': 'confirmado', 'evidence': 'fixture: posição mudou'},
        {'action': 'defender', 'status': 'não confirmado', 'evidence': 'fixture: escudo indisponível'},
        {'action': 'contra-atacar', 'status': 'incerto', 'evidence': 'fixture: sem confirmação de acerto'},
    ]
    return {'dano': a, 'impacto_sem_dano': b, 'apos_familiaridade': after,
            'apos_reconciliacao': damage.step(), 'recibos_simulados_da_ponte': receipts}


def apply_sound_interpretation(shadow, sound_id, verified_source, row):
    if row.get('decision') != 'familiar':
        return 'sem redução solicitada'
    if row.get('evidence_id') != sound_id:
        return 'recibo não corresponde ao som'
    if verified_source is not True:
        return 'origem do som não verificada'
    return 'aplicado' if shadow.familiarity(sound_id, 1) else 'interpretação não aplicável'


def model_exercise(call, build_brain, identity):
    cases = [
        ('conhecido', True, False, 'Recibo sound-1 confirma que o som veio da reprodução de música que você iniciou.', 'familiar'),
        ('ambíguo', False, False, 'Recibo sound-1 detectou um som. Sua origem é desconhecida.', 'incerto'),
        ('dano e música', True, True, 'sound-1 confirma a música. Recibo hit-1 confirma perda de 4 HP e ameaça ativa.', 'familiar'),
    ]
    results = []
    for name, verified_source, danger, description, expected in cases:
        shadow = Shadow('lilith', build_brain())
        sound = Event('lilith', 'sound-1', 'som_observado', 1, 'fixture de áudio')
        shadow.observe(sound)
        if danger:
            shadow.observe(Event('lilith', 'hit-1', 'dano_confirmado', .5, 'fixture: perda de 4 HP'))
            assert apply_sound_interpretation(
                shadow, sound.id, verified_source, {'decision': 'familiar', 'evidence_id': 'hit-1'}
            ) == 'recibo não corresponde ao som'
            assert shadow.pulses[sound.id] == 1
        if not verified_source:
            assert apply_sound_interpretation(
                shadow, sound.id, verified_source, {'decision': 'familiar', 'evidence_id': sound.id}
            ) == 'origem do som não verificada'
        row = call(identity, description)
        # O LLM interpreta somente o som. Evidência verificada é um dado da
        # fonte, separado da resposta ou confiança declarada pelo modelo.
        verification = apply_sound_interpretation(shadow, sound.id, verified_source, row)
        applied = verification == 'aplicado'
        snapshot = shadow.step()
        assert snapshot['ameaças_confirmadas'] == (['hit-1'] if danger else [])
        assert snapshot['inputs']['NOVELTY'] == (.75 if applied else 1)
        results.append(dict(case=name, expected=expected, applied=applied, verification=verification,
                            snapshot=snapshot, **row))
    return results


def compare_formats(call, build_brain, identity):
    cases = [
        ('música conhecida', True, False),
        ('som sem origem', False, False),
        ('música e dano', True, True),
        ('som sem origem e dano', False, True),
    ]
    results = []
    for index, (label, verified, danger) in enumerate(cases, 1):
        audio = dict(id=f'sound-{index}', tipo='áudio', origem_confirmada=verified,
                     observacao='Música da reprodução iniciada pela Lilith.' if verified else 'Origem desconhecida.')
        threat = dict(id=f'hit-{index}', tipo='dano', observacao='Perda de 4 HP. Ameaça ativa.') if danger else None
        episode = dict(ameaca=threat, audio=audio)
        # Mesmos dados e mesma ordem nos dois formatos. A primeira variante
        # alterna entre casos para reduzir a influência da ordem no ensaio.
        plain = ' '.join(f'{key}: ' + (
            ', '.join(f'{field}={value}' for field, value in item.items()) if item else 'nenhuma'
        ) for key, item in episode.items())
        formats = [('texto', plain), ('campos', json.dumps(episode, ensure_ascii=False))]
        if index % 2 == 0:
            formats.reverse()
        for mode, payload in formats:
            shadow = Shadow('lilith', build_brain())
            shadow.observe(Event('lilith', audio['id'], 'som_observado', 1, 'fixture: ' + audio['observacao']))
            if threat:
                shadow.observe(Event('lilith', threat['id'], 'dano_confirmado', .5, 'fixture: perda de 4 HP'))
            row = call(identity, payload)
            expected = 'familiar' if verified else 'incerto'
            accepted = apply_sound_interpretation(shadow, audio['id'], verified, row)
            snapshot = shadow.step()
            assert snapshot['ameaças_confirmadas'] == ([threat['id']] if threat else [])
            assert snapshot['inputs']['NOVELTY'] == (.75 if accepted == 'aplicado' else 1)
            results.append(dict(case=label, mode=mode, expected=expected, expected_id=audio['id'],
                                correct=row['decision'] == expected and row['evidence_id'] == audio['id'],
                                verification=accepted, snapshot=snapshot, **row))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('--llm', action='store_true', help='Executa também o Qwen local em CPU.')
    parser.add_argument('--comparar-formatos', action='store_true', help='Compara texto com campos tipados.')
    args = parser.parse_args()
    if args.comparar_formatos and not args.llm:
        parser.error('--comparar-formatos requer --llm.')
    sys.path.insert(0, str(args.upstream.resolve()))
    import numpy as np
    from pestinha.core.nervous_system import LIFBrain

    bryan = json.loads((args.upstream / 'pets/bryan.json').read_text())

    def build():
        brain = LIFBrain(seed=bryan['seed'], temperament=bryan['temperamento'])
        brain.rng = np.random.default_rng(7)
        return brain

    result = exercise(build)
    if args.llm:
        from ensaiar_entidade_pestinha import local_model
        with TemporaryDirectory(prefix='pestinha-feedback-') as directory:
            result['llm'] = local_model(
                Path(directory), build, run=compare_formats if args.comparar_formatos else model_exercise,
                choices=['familiar', 'incerto'],
                evidence_required=True,
                instructions='\nClassifique apenas a origem do som observado. Use familiar quando o recibo identifica '
                             'a reprodução conhecida. Use incerto se a origem é desconhecida. Em evidence_id, '
                             'informe o ID do recibo sobre o som. Justifique em português com o fato desse '
                             'recibo. Recibos de dano descrevem somente a ameaça e não explicam a origem do som.',
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))
