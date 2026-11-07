"""Corpo pulsado dos orbes (Pestinha, só leitura): protocolo, sono, persistência e custo.

Offline: precisa do checkout fixado em compartilhado/servicos/pestinha e de numpy
(ambiente principal); sem eles, os testes são pulados. Escreve só em diretório temporário.
"""
import io
import json
import math
import signal
import statistics
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'compartilhado/servicos/pestinha'

import sys  # noqa: E402
sys.path.insert(0, str(ROOT / 'app/ui'))
import corpo_pulsado as cp  # noqa: E402

try:
    import numpy  # noqa: F401
    NUCLEO = cp.carregar_nucleo(UPSTREAM) if (UPSTREAM / '.git/HEAD').is_file() else None
except Exception:  # sem numpy ou checkout: nada a testar aqui
    NUCLEO = None


class InterpretarTests(unittest.TestCase):
    def test_mensagens_validas(self):
        self.assertEqual(cp.interpretar('{"tipo":"cutucar","entidade":"lilith"}'), dict(tipo='cutucar', entidade='lilith'))
        msg = cp.interpretar(json.dumps(dict(tipo='estado', entidade='hoshino', status='working',
                                             emocoes={'alegria': 0.7, 'raiva': 2, 'inventada': 1}, reduzido=True)))
        self.assertEqual(msg, dict(tipo='estado', entidade='hoshino', status='working',
                                   emocoes={'alegria': 0.7, 'raiva': 1.0}, reduzido=True))

    def test_mensagens_recusadas_ou_saneadas(self):
        for linha in ('', 'lixo', '[]', '{"tipo":"cutucar","entidade":"outra"}', '{"tipo":"apagar","entidade":"lilith"}',
                      '{"tipo":"cutucar"}', 'x' * (cp.MAX_LINHA + 1)):
            self.assertIsNone(cp.interpretar(linha))
        msg = cp.interpretar('{"tipo":"estado","entidade":"lilith","status":"rm -rf","emocoes":{"medo":NaN,"alegria":true},"reduzido":"sim"}')
        self.assertEqual((msg['status'], msg['emocoes'], msg['reduzido']), ('awake', {}, False))
        self.assertFalse(cp.interpretar('{"tipo":"arrastar","entidade":"lilith","ativo":1}')['ativo'])


@unittest.skipIf(NUCLEO is None, 'checkout do Pestinha ou numpy ausente')
class CorpoTests(unittest.TestCase):
    def setUp(self):
        self.nucleo, self.revisao = NUCLEO

    def corpo(self, entidade='lilith', ruido=1):
        return cp.CorpoPulsado(self.nucleo, entidade, self.revisao, ruido=ruido)

    def test_sono_nao_simula_e_recupera_habituacao_ao_acordar(self):
        corpo, perfil = self.corpo(), cp.perfil_de({})
        for _ in range(8):
            corpo.cutucar()
            for _ in range(40):
                corpo.passo('awake', perfil)
        antes = corpo.brain.efficacy()['POKE']
        tempo_rede = corpo.brain.time_ms
        for k in range(10):
            r = corpo.passo('sleeping', perfil, agora=corpo.agora + 60, simular_quieto=False)
        self.assertEqual(r['rotulo'], 'dormindo')
        self.assertEqual(corpo.brain.time_ms, tempo_rede)          # nada simulado dormindo
        corpo.passo('awake', perfil, agora=corpo.agora + 0.1)
        tau = float(corpo.brain.s_tau_rec[corpo.brain.pool('POKE')['start']])
        esperado = 1 - (1 - antes) * math.exp(-600.1 / tau)
        self.assertAlmostEqual(corpo.brain.efficacy()['POKE'], esperado, delta=0.01)

    def test_cutucada_mexe_o_corpo_e_movimento_reduzido_zera_amplitude(self):
        corpo, perfil = self.corpo(), cp.perfil_de({})
        for _ in range(30):
            corpo.passo('awake', perfil)
        base = sum(corpo.brain.motor_activity()[m] for m in cp.EXPRESSAO)
        corpo.cutucar()
        pico = max(sum(corpo.passo('awake', perfil)['motores'].values()) for _ in range(30))
        self.assertGreater(pico, base + 3)
        corpo.cutucar()
        reduzido = [corpo.passo('awake', perfil, reduzido=True)['animacao'] for _ in range(30)]
        self.assertTrue(all(a['amplitude_px'] == 0 and not a['sobressalto'] for a in reduzido))

    def test_estado_de_outra_entidade_e_recusado(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'corpo_lilith.json'
            self.corpo().salvar(arquivo)
            ok, motivo = self.corpo('hoshino').carregar(arquivo)
            self.assertEqual((ok, motivo), (False, 'outra entidade'))
            self.assertTrue(self.corpo().carregar(arquivo)[0])

    def test_custo_por_passo(self):
        corpo, perfil = self.corpo(), cp.perfil_de({'curiosidade': 0.6})
        tempos = []
        for _ in range(100):
            t = time.perf_counter(); corpo.passo('working', perfil); tempos.append(time.perf_counter() - t)
        self.assertLess(statistics.median(tempos) * 1000, 15)    # medido ~4,5 ms; folga para máquina ocupada

    def test_servir_protocolo_salva_so_na_pasta_do_corpo(self):
        liberar = threading.Event()
        linhas = [json.dumps(dict(tipo='estado', entidade='lilith', status='awake', emocoes={'alegria': 0.8})),
                  json.dumps(dict(tipo='estado', entidade='hoshino', status='sleeping', emocoes={})),
                  json.dumps(dict(tipo='cutucar', entidade='lilith')), 'lixo']

        def entrada():
            yield from (l + '\n' for l in linhas)
            liberar.wait(10)
        saida = io.StringIO()
        anterior = signal.getsignal(signal.SIGTERM)
        try:
            with tempfile.TemporaryDirectory() as root:
                ticks = cp.servir(root, UPSTREAM, entrada(), saida, max_ticks=12)
                arquivos = sorted(str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file())
        finally:
            liberar.set(); signal.signal(signal.SIGTERM, anterior)
        self.assertEqual(ticks, 12)
        self.assertEqual(arquivos, [f'compartilhado/runtime/overlay/corpo_{e}.json' for e in ('alistair', 'hoshino', 'lilith')])
        ultima = json.loads(saida.getvalue().splitlines()[-1])['corpos']
        self.assertEqual(set(ultima), set(cp.TEMPERAMENTOS))
        self.assertEqual(ultima['hoshino']['rotulo'], 'dormindo')
        self.assertEqual(ultima['alistair']['rotulo'], 'dormindo')      # sem estado ainda = offline
        self.assertGreater(ultima['lilith']['animacao']['amplitude_px'], 0)


if __name__ == '__main__':
    unittest.main()
