"""Percepção sem ícone giratório, habituação e sensibilização afetivas (05/11/2026).

Offline: estado em diretório temporário, sem banco real (o registro de emoção
é interceptado) e sem modelo.
"""
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import config
from core import situation, state_file
from mind import affect, emotions, habituation, psych_state


class RotuloSemIconeTests(unittest.TestCase):
    def test_spinner_do_terminal_nao_muda_o_app(self):
        for titulo in ('◐ Hoshino e Lilith no Minecraft', '◑ Hoshino e Lilith no Minecraft',
                       '✳ Hoshino e Lilith no Minecraft', '⠋ Hoshino e Lilith no Minecraft',
                       'Hoshino e Lilith no Minecraft'):
            self.assertEqual(situation.rotulo_app(titulo), 'Hoshino e Lilith no Minecraft')

    def test_icone_em_cada_parte_e_simbolos_comuns_preservados(self):
        self.assertEqual(situation.rotulo_app('⠙ build — ✳ Terminal'), 'Terminal')
        self.assertEqual(situation.detalhe_app('⠙ build — ✳ Terminal'), 'build')
        self.assertEqual(situation.rotulo_app('main.cpp — C++'), 'C++')
        self.assertEqual(situation.rotulo_app('Minecraft* 1.16.5'), 'Minecraft* 1.16.5')
        self.assertEqual(situation.rotulo_app('◐'), '')


class NovidadeDeRelanceTests(unittest.TestCase):
    """Sessões < 45 s não chegam ao banco; o app visto de relance não renasce inédito."""

    def setUp(self):
        self.stored = {}
        self.now = datetime(2026, 11, 5, 12)
        for name, kwargs in (
            ('_memoria_curta', {'side_effect': lambda: json.loads(json.dumps(self.stored))}),
            ('_gravar_memoria_curta', {'side_effect': self.save}),
            ('_pendencias', {'return_value': {}}), ('ja_viu', {'return_value': False}),
            ('_fechar_sessao', {'return_value': None}),
        ):
            patcher = patch.object(situation, name, **kwargs)
            patcher.start(); self.addCleanup(patcher.stop)

    def save(self, value):
        self.stored = json.loads(json.dumps(value)); return True

    def observe(self, seconds, title):
        return situation.atualizar({'janela_ativa': title}, agora=self.now + timedelta(seconds=seconds),
                                   monotonic_now=100 + seconds)

    def test_animacao_do_titulo_gera_uma_novidade_so(self):
        self.observe(0, 'Mozilla Firefox')                      # linha de base
        tipos = []
        for k, glyph in enumerate('◐◑◒◓✳◐◑◒◓✳'):
            tipos += [e['tipo'] for e in self.observe(1 + k, f'{glyph} Hoshino e Lilith no Minecraft')['eventos']]
        self.assertEqual(tipos, ['app_novo'])

    def test_voltar_a_um_app_breve_e_troca_nao_novidade(self):
        self.observe(0, 'Mozilla Firefox')
        self.assertEqual(self.observe(5, '◐ Projeto')['eventos'][0]['tipo'], 'app_novo')
        self.observe(10, 'Mozilla Firefox')
        state = self.observe(15, '◑ Projeto')
        self.assertEqual([e['tipo'] for e in state['eventos']], ['app_trocado'])
        self.assertTrue(state['app_familiar'])
        self.assertEqual(state['novidades'], 0)

    def test_lista_de_vistos_e_limitada(self):
        self.observe(0, 'App 0')
        for k in range(1, 100):
            self.observe(k, f'App {k}')
        self.assertEqual(len(self.stored['apps_vistos']), situation._APPS_VISTOS_MAX)
        self.assertEqual(self.stored['apps_vistos'][-1], 'App 99')


class HabituacaoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.registros = []
        for target, name, value in (
            (config, 'ESTADO_MENTE', str(self.root / 'estado_mente.json')),
            (psych_state, '_path', lambda: self.root / 'psych.json'),
            (emotions, '_registrar', lambda *a: self.registros.append(a)),
        ):
            patcher = patch.object(target, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.t0 = datetime(2026, 11, 5, 12)

    def estado(self):
        return json.loads(Path(config.ESTADO_MENTE).read_text())

    def test_novidade_repetida_pesa_menos_ate_o_piso(self):
        ganhos = [habituation.registrar('novidade', self.t0 + timedelta(seconds=k))['ganho'] for k in range(8)]
        for obtido, esperado in zip(ganhos, (1.0, 0.6, 0.36)):
            self.assertAlmostEqual(obtido, esperado, places=2)
        self.assertTrue(all(a >= b for a, b in zip(ganhos, ganhos[1:])))
        self.assertAlmostEqual(ganhos[-1], 0.2, places=2)

    def test_recupera_pelo_tempo_de_parede(self):
        habituation.registrar('novidade', self.t0)
        depois = self.t0 + timedelta(minutes=60)
        esperado = 1 - (1 - 0.6) * math.exp(-1)
        self.assertAlmostEqual(habituation.ganho('novidade', depois), esperado, places=3)
        self.assertAlmostEqual(habituation.ganho('novidade', self.t0 + timedelta(days=1)), 1.0, places=3)

    def test_risco_repetido_sensibiliza_ate_o_teto_e_volta(self):
        ganhos = [habituation.registrar('risco_observado', self.t0 + timedelta(seconds=10 * k))['ganho']
                  for k in range(6)]
        for obtido, esperado in zip(ganhos, (1.0, 1.25, 1.5625)):
            self.assertAlmostEqual(obtido, esperado, places=1)
        self.assertTrue(all(g <= 1.6 for g in ganhos))
        self.assertAlmostEqual(habituation.ganho('risco_observado', self.t0 + timedelta(hours=3)), 1.0, places=2)

    def test_gatilho_fora_da_tabela_nao_muda(self):
        self.assertEqual(habituation.registrar('maltrato', self.t0), dict(ganho=1.0, persisted=True, regra=False))
        self.assertFalse(Path(config.ESTADO_MENTE).exists())
        for evento in ('maltrato', 'critica', 'tarefa_falhou', 'tarefa_falhou_de_novo',
                       'erro_proprio_descoberto', 'confidencia', 'amizade_avancou'):
            self.assertNotIn(evento, habituation.REGRAS)

    def test_estado_ilegivel_ou_fora_do_dominio_vale_ganho_um(self):
        for ruim in ({'g': 'x', 'em': '2026-11-05T15:00:00+00:00'}, {'g': 5, 'em': '2026-11-05T15:00:00+00:00'},
                     {'g': 0.05, 'em': '2026-11-05T15:00:00+00:00'}, {'g': float('nan'), 'em': 'x'}, [], 'lixo'):
            Path(config.ESTADO_MENTE).write_text(json.dumps({'habituacao': {'novidade': ruim}}))
            self.assertEqual(habituation.ganho('novidade', self.t0), 1.0)
        Path(config.ESTADO_MENTE).write_text(json.dumps({'habituacao': []}))
        self.assertEqual(habituation.registrar('novidade', self.t0)['ganho'], 1.0)
        self.assertEqual(self.estado()['habituacao']['novidade']['g'], 0.6)

    def test_falha_de_escrita_devolve_ganho_sem_contar(self):
        with patch.object(state_file, 'update', return_value=False):
            r = habituation.registrar('novidade', self.t0)
        self.assertEqual(r, dict(ganho=1.0, persisted=False, regra=True))

    def test_apreciar_aplica_o_ganho_no_humor_e_nas_emocoes(self):
        primeiro = affect.apreciar('novidade', agora=self.t0, motivo='apareceu A')
        segundo = affect.apreciar('novidade', agora=self.t0 + timedelta(seconds=1), motivo='apareceu B')
        self.assertEqual(primeiro['habituacao'], 1.0)
        self.assertAlmostEqual(segundo['habituacao'], 0.6, places=3)
        curiosidade = self.estado()['emocoes']['curiosidade']['i']
        # sem habituação: 0,5 + 0,5*0,5 = 0,75; com: 0,5 + 0,5*0,5*0,6 = 0,65
        self.assertAlmostEqual(curiosidade, 0.65, places=2)

    def test_apreciar_sem_regra_fica_identico(self):
        r = affect.apreciar('maltrato', agora=self.t0, motivo='teste')
        self.assertNotIn('habituacao', r)
        self.assertNotIn('habituacao', self.estado())
        self.assertAlmostEqual(self.estado()['emocoes']['raiva']['i'], 0.7, places=3)

    def test_ameaca_repetida_supera_susto_passageiro(self):
        affect.apreciar('risco_observado', agora=self.t0, motivo='zumbi')
        unico = self.estado()['emocoes']['medo']['i']
        for k in range(1, 4):
            affect.apreciar('risco_observado', agora=self.t0 + timedelta(seconds=20 * k), motivo='zumbi')
        repetido = self.estado()['emocoes']['medo']['i']
        Path(config.ESTADO_MENTE).unlink()
        for k in range(4):
            affect.apreciar('risco_observado', agora=self.t0 + timedelta(hours=3 * k), motivo='zumbi')
        espacado = self.estado()['emocoes']['medo']['i']
        self.assertAlmostEqual(unico, 0.3, places=3)
        self.assertGreater(repetido, espacado + 0.05)


if __name__ == '__main__':
    unittest.main()
