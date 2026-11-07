"""Testes do controlador cognitivo e das novas guardas de autonomia."""
import os
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import importlib
import tempfile
import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import config
from core import cognition, kernel, dispatch
from memory.sqlite.init_db import init_database
init_database(verbose=False)

ok = 0
falhas = []


def checar(nome, cond, det=""):
    global ok
    if cond:
        ok += 1
        print(f"[OK] {nome}")
    else:
        falhas.append(nome)
        print(f"[FALHOU] {nome} {det}")


frame = cognition.criar_frame(
    "pesquisar por que meu Discord está falhando, testar uma correção e depois conferir",
    dispatch.ESQUEMAS,
)
checar("classifica domínio de depuração/pesquisa" , frame.dominio in {"depuracao", "pesquisa"}, frame.dominio)
checar("tarefa composta recebe plano", len(frame.plano) >= 3, str(frame.plano))

classe = cognition.registrar_ferramenta(frame, "execute_command", "Erro: comando falhou")
checar("falha é classificada", classe == "erro")
checar("próxima ação muda de estratégia", "mudar" in frame.proxima_necessidade or "diagnost" in frame.proxima_necessidade, frame.proxima_necessidade)

aliases = dispatch._buscar_habilidades("mandar uma mensagem para o discord")
checar("busca semântica encontra discord", "discord_enviar" in aliases, str(aliases))
checar("diagnóstico é capacidade real", "exportar_diagnostico" in dispatch.nomes(), str(dispatch.nomes()))
frame2 = cognition.criar_frame("conectar no Minecraft e verificar", dispatch.ESQUEMAS)
cognition.registrar_ferramenta(frame2, "minecraft_conectar", "[CONEXÃO MINECRAFT NÃO VERIFICADA]")
checar("não permite alegar conexão sem verificação", cognition.precisa_verificacao_de_conclusao("Conectei ao Minecraft.", frame2))

resultado = dispatch.executar("criar_lembrete", {"mensagem": "teste"})
checar("validação barra argumento obrigatório ausente", "argumentos inválidos" in resultado.lower(), resultado)

# Uma leitura antes da escrita não pode ser confundida com a verificação do
# resultado da escrita. Esta regressão mantinha tarefas compostas frágeis.
frame3 = cognition.criar_frame("ler um arquivo, atualizar e conferir o resultado", dispatch.ESQUEMAS)
cognition.registrar_ferramenta(frame3, "read_file", "conteúdo anterior")
cognition.registrar_ferramenta(frame3, "write_file", "Gravado: arquivo.txt")
checar("exige verificação depois da ação mutável", cognition.deve_continuar(frame3), str(frame3.ferramentas_usadas))
cognition.registrar_ferramenta(frame3, "read_file", "conteúdo atualizado")
checar("leitura posterior satisfaz verificação", not cognition.deve_continuar(frame3), str(frame3.ferramentas_usadas))

agora = datetime.now()
sit_audio = {
    "agora": agora,
    "usuario_presente": True,
    "eventos": [],
    "audio_eventos": [{"canal": "discord", "origem": "Andrews", "texto": "Hoshino, você está aí?", "quando": agora}],
    "carga": {"load1": 0.0, "memoria_usada_pct": 20.0},
}
pressoes = {nome: {"pressao": 0.0} for nome in ("conexao", "curiosidade", "competencia", "coerencia", "ocio", "cuidado")}
estado = {"modo_silencioso": False, "ultima_fala": None, "ultima_acao_interna": None, "acoes_na_hora": 0, "partida_em_andamento": False}
dec = kernel.deliberar(sit_audio, pressoes, estado)
checar("áudio dirigido produz intenção de reação", dec["tipo"] == "reagir_audio", str(dec))

sit_ruido = dict(sit_audio)
sit_ruido["audio_eventos"] = [{"canal": "jogo", "origem": "jogo", "texto": "Hoshino, som ambiente", "quando": agora}]
dec2 = kernel.deliberar(sit_ruido, pressoes, estado)
checar("áudio do jogo não interrompe como Discord dirigido", dec2["tipo"] != "reagir_audio", str(dec2))

sit_carga = dict(sit_audio)
sit_carga["audio_eventos"] = []
sit_carga["carga"] = {"load1": 999.0, "memoria_usada_pct": 99.0}
pressoes2 = {nome: {"pressao": 0.9} for nome in ("curiosidade", "competencia", "coerencia", "ocio", "conexao", "cuidado")}
dec3 = kernel.deliberar(sit_carga, pressoes2, estado)
checar("recursos saturados seguram autonomia pesada", dec3["tipo"] == "nada", str(dec3))

# Regressões da V14: veracidade e julgamento conservador.
class V14TruthAndJudgmentTests(unittest.TestCase):
    def test_directed_audio_uses_listener_identity_not_hardcoded_hoshino(self):
        for listener,other in [('Lilith','Hoshino'),('Hoshino','Lilith')]:
            with self.subTest(listener=listener), patch.object(config,'ENTIDADE_NOME',listener):
                own={'audio_eventos':[{'canal':'voz','texto':listener+', olha aqui'}]}
                foreign={'audio_eventos':[{'canal':'voz','texto':other+', olha aqui'}]}
                self.assertIsNotNone(kernel._audio_dirigido(own))
                self.assertIsNone(kernel._audio_dirigido(foreign))

    def test_minecraft_verificado_e_sucesso(self):
        self.assertEqual(cognition.classificar_erro('[CONEXÃO MINECRAFT VERIFICADA]'), 'sucesso')

    def test_minecraft_nao_verificado_e_falha(self):
        self.assertEqual(cognition.classificar_erro('[CONEXÃO MINECRAFT NÃO VERIFICADA]'), 'erro')

    def test_manual_com_palavra_falhou_nao_e_erro(self):
        self.assertEqual(
            cognition.classificar_erro("Manual: não repita uma ação que falhou."),
            'indefinido')

    def test_interromper_nao_e_depuracao(self):
        self.assertNotEqual(cognition.criar_frame('interromper o alerta').dominio, 'depuracao')

    def test_contradicao_minecraft_fica_registrada(self):
        frame = cognition.criar_frame('testar conexão Minecraft')
        cognition.registrar_ferramenta(frame, 'minecraft_conectar', '[CONEXÃO MINECRAFT VERIFICADA]')
        cognition.registrar_ferramenta(frame, 'minecraft_estado', '{"connected": false, "verified": false, "connectionState": "disconnected"}')
        self.assertFalse(frame.verificacoes.get('minecraft'))
        self.assertTrue(any('CONTRADIÇÃO' in e for e in frame.evidencias))


class TemporalStateTests(unittest.TestCase):
    """Relógio/estado reais em arquivos temporários, sem inferência ou hardware."""
    def setUp(self):
        from core import history
        self.history = history
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for obj, key, value in (
            (config, 'RUNTIME_DIR', temp.name),
            (config, 'ESTADO_MENTE', str(Path(temp.name) / 'estado.json')),
            (config, 'LOCAL_TIMEZONE', 'America/Sao_Paulo'),
        ):
            patcher = patch.object(obj, key, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.now = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)

    def test_affect_legacy_and_offset_decay_are_equivalent_without_rewrite(self):
        from mind import affect
        for timestamp in ('2026-10-09T11:15:00', '2026-10-09T14:15:00Z', '2026-10-09T23:15:00+09:00'):
            raw = dict(affect.BASE, prazer=.9, atualizado_em=timestamp)
            with self.subTest(timestamp=timestamp), patch.object(affect, '_ler', return_value=raw), \
                 patch.object(config, 'MEIA_VIDA_HUMOR_MIN', 45):
                before = dict(raw)
                out = affect.estado(self.now)
                self.assertAlmostEqual(out['prazer'], affect.BASE['prazer'] + (.9-affect.BASE['prazer'])/2, places=4)
                self.assertTrue(out['atualizado_em'].endswith('+00:00'))
                self.assertEqual(raw, before)

    def test_psychological_state_decays_over_restart_without_writing_on_read(self):
        from mind import psych_state
        raw = dict(autoeficacia=.9, atualizado_em='2026-10-07T12:00:00')
        before = dict(raw)
        out = psych_state.estado(self.now, dados=raw)
        self.assertAlmostEqual(out['autoeficacia'], .7, places=4)
        self.assertEqual(raw, before)
        with patch.object(psych_state, '_gravar') as save:
            psych_state.estado(self.now, dados=raw)
        save.assert_not_called()

    def test_emotion_projection_and_mind_agree_for_utc_and_legacy(self):
        from mind import emotions
        for timestamp in ('2026-10-09T11:00:00', '2026-10-09T14:00:00Z'):
            raw = {'alegria': {'i': .8, 'em': timestamp, 'motivo': 'encontro observado'}}
            with self.subTest(timestamp=timestamp), patch.object(emotions, '_ler', return_value=raw):
                mind = emotions.estado(self.now)['alegria']
                visual = emotions.visual_profile({'emocoes': raw}, agora=self.now)
                expected = round(.8 * .5 ** (60 / emotions.EMOCOES['alegria']['meia_vida_min']), 3)
                self.assertEqual(mind['intensidade'], expected)
                self.assertEqual(visual['dominant'], 'alegria')
                self.assertEqual(visual['intensity'], expected)
                self.assertEqual(mind['desde'], timestamp)

    def test_refractory_offset_is_not_bypassed_and_invalid_time_is_conservative(self):
        from mind import drives
        for timestamp, expected in [('2026-10-09T14:52:30Z', .5), ('2026-10-09T11:52:30', .5),
                                    ('2026-10-10T15:00:00Z', 0.), ('inválido', 0.)]:
            with self.subTest(timestamp=timestamp), patch.object(drives, '_estado', return_value={'satisfacoes': {'curiosidade': timestamp}}):
                self.assertEqual(drives._refratario('curiosidade', self.now), expected)
        with patch.object(drives, '_estado', return_value={}):
            self.assertEqual(drives._refratario('curiosidade', self.now), 1.)

    def test_new_state_timestamps_are_utc_and_refractory_survives_reload(self):
        from core import state_file
        from mind import affect, psych_state, emotions, drives
        with patch.object(emotions, '_registrar'):
            self.assertTrue(affect.apreciar('elogio', agora=self.now)['persisted'])
        self.assertTrue(drives.satisfazer('curiosidade', self.now))
        raw = state_file.read(config.ESTADO_MENTE)
        self.assertTrue(raw['humor']['atualizado_em'].endswith('+00:00'))
        self.assertTrue(all(e['em'].endswith('+00:00') for e in raw['emocoes'].values()))
        self.assertTrue(raw['satisfacoes']['curiosidade'].endswith('+00:00'))
        self.assertTrue(state_file.read(psych_state._path())['atualizado_em'].endswith('+00:00'))
        importlib.reload(drives)
        self.assertEqual(drives._refratario('curiosidade', self.now), 0.)
        self.assertEqual(drives._refratario('curiosidade', self.now+timedelta(minutes=15)), 1.)
        with patch.object(config, 'ESTADO_MENTE', str(Path(config.RUNTIME_DIR) / 'lilith.json')):
            self.assertEqual(drives._refratario('curiosidade', self.now), 1.)

    def test_invalid_or_future_emotion_never_becomes_a_confirmed_visual_state(self):
        from mind import emotions
        for timestamp in ('inválido', '2026-10-10T15:00:00Z'):
            raw = {'alegria': {'i': .8, 'em': timestamp}}
            with self.subTest(timestamp=timestamp), patch.object(emotions, '_ler', return_value=raw):
                self.assertEqual(emotions.estado(self.now), {})
                self.assertIsNone(emotions.visual_profile({'emocoes': raw}, agora=self.now)['dominant'])

    def test_unreliable_clock_preserves_affect_and_psych_state_instead_of_resetting_them(self):
        from mind import affect, psych_state
        for timestamp in ('inválido', '2026-10-10T15:00:00Z'):
            with self.subTest(timestamp=timestamp), patch.object(affect, '_ler', return_value=dict(affect.BASE, prazer=.8, atualizado_em=timestamp)):
                self.assertEqual(affect.estado(self.now)['prazer'], .8)
                self.assertEqual(psych_state.estado(self.now, dados={'autoeficacia': .8, 'atualizado_em': timestamp})['autoeficacia'], .8)


class AutonomyClockTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)
        for key, value in [('LOCAL_TIMEZONE', 'America/Sao_Paulo'), ('HORARIO_SILENCIO', (0, 0))]:
            p = patch.object(config, key, value); p.start(); self.addCleanup(p.stop)

    def test_clock_offsets_do_not_crash_legacy_cooldown_guards(self):
        last = datetime(2026, 10, 9, 11, 59, 50)
        self.assertFalse(kernel._pode_falar_agora(self.now, last, False)[0])
        self.assertFalse(kernel._pode_agir_agora(self.now, last, 0)[0])
        self.assertFalse(kernel._pode_olhar_tela(self.now, last))

    def test_monotonic_cooldown_ignores_forward_and_backward_wall_clock_jumps(self):
        for wall in (self.now-timedelta(days=1), self.now+timedelta(days=1)):
            self.assertFalse(kernel._pode_falar_agora(wall, self.now, False, monotonic_now=110., last_monotonic=100.)[0])
            self.assertTrue(kernel._pode_falar_agora(wall, self.now, False, monotonic_now=1100., last_monotonic=100.)[0])
            self.assertFalse(kernel._pode_agir_agora(wall, self.now, 0, monotonic_now=110., last_monotonic=100.)[0])
            self.assertTrue(kernel._pode_agir_agora(wall, self.now, 0, monotonic_now=1100., last_monotonic=100.)[0])

    def test_monotonic_zero_is_valid_and_regression_is_not_permission(self):
        self.assertFalse(kernel._pode_olhar_tela(self.now, self.now-timedelta(days=1), monotonic_now=1., last_monotonic=0.))
        self.assertFalse(kernel._pode_agir_agora(self.now, self.now-timedelta(days=1), 0, monotonic_now=50., last_monotonic=100.)[0])
        self.assertFalse(kernel._pode_falar_agora(self.now, self.now-timedelta(days=1), False, monotonic_now=float('nan'), last_monotonic=0.)[0])

    def test_quiet_hours_are_local_even_if_input_is_utc(self):
        from core import autonomy
        now = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)  # 05:00 local
        with patch.object(config, 'HORARIO_SILENCIO', (0, 7)), patch.object(autonomy, 'HORARIO_SILENCIO', (0, 7)):
            self.assertFalse(kernel._pode_falar_agora(now, None, False)[0])
            self.assertTrue(autonomy.em_horario_de_silencio(now))
            self.assertTrue(kernel._pode_falar_agora(now, None, True)[0])

    def test_runtime_wires_monotonic_action_and_hour_quota_without_inference(self):
        import main
        app = SimpleNamespace(acoes_na_hora=deque(maxlen=60), refletir=AsyncMock(), sys_log=Mock(),
                              modo_silencioso=False, ultima_fala_autonoma=None, ultima_olhada_tela=None)
        with patch.object(main.time, 'monotonic', return_value=100.), patch.object(main.drives, 'satisfazer'):
            asyncio.run(main.InterfaceHoshino.agir_por_dentro(app, {'tipo': 'refletir', 'motivo': 'ensaio'}))
        self.assertEqual(app.ultima_acao_interna_monotonic, 100.)
        self.assertEqual(list(app.acoes_na_hora), [100.])
        # Um relógio de parede que pulou não esgota/libera a cota monotônica.
        state = main.InterfaceHoshino._estado_autonomia(app, self.now+timedelta(days=1), 200.)
        self.assertEqual(state['acoes_na_hora'], 1)
        self.assertEqual(state['ultima_acao_monotonic'], 100.)
        self.assertEqual(main.InterfaceHoshino._estado_autonomia(app, self.now-timedelta(days=1), 3700.)['acoes_na_hora'], 0)


if __name__ == '__main__':
    print()
    print(f"{ok} verificações ok, {len(falhas)} falha(s)")
    for f in falhas:
        print(" -", f)
    if falhas:
        raise SystemExit(1)
    unittest.main(verbosity=2)
