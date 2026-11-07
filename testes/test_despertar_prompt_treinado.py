"""06/11 (pedido humano): prompt reduzido para pesos treinados no corpus vigente,
despertar com uma fala no chat e fala por iniciativa visível na Central.
Fixtures temporárias; nenhum modelo, GPU ou banco real."""
import asyncio
import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import config
from core import autonomy, job_bus, kernel, pesos_treinados, prompting
from memory.sqlite import init_db
from tools import agenda
from laboratorio import corpus_atual


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'mind.db'
        identidade = self.root / 'identity'
        identidade.mkdir()
        (identidade / 'constitution.json').write_text(json.dumps({
            'identidade': ['Sou Hoshino. Meu jeito de partida é inspirado numa personagem, mas não sou a personagem.',
                           'Sou uma entidade individual.'],
            'honestidade': ['Não invento memória.'],
            'silencio': ['Silêncio é o padrão quando não há nada concreto a dizer.'],
            'acao': ['A máquina é do usuário.'],
            'expressao': ['Eu tenho opinião.'],
            'continuidade': ['Minha memória é minha responsabilidade.']}, ensure_ascii=False))
        (identidade / 'self_model.json').write_text(json.dumps({
            'identity': {'name': 'Hoshino', 'self_concept': 'Sou uma entidade local.', 'nature': 'Sou um programa.'},
            'cognitive_framework': ['Penso antes de agir.']}, ensure_ascii=False))
        for obj, key, value in (
            (config, 'DB_PATH', str(self.db)), (init_db, 'DB_PATH', str(self.db)),
            (config, 'ESTADO_MENTE', str(self.root / 'state.json')),
            (config, 'RUNTIME_DIR', str(self.root)), (config, 'ENTIDADE_ID', 'hoshino'),
            (job_bus, 'DB_PATH', self.root / 'jobs.db'), (agenda, 'DB_PATH', str(self.db)),
            (config, 'HORARIO_SILENCIO', (0, 0)),
            (prompting, 'CONSTITUICAO_PATH', str(identidade / 'constitution.json')),
            (prompting, 'SELF_MODEL_PATH', str(identidade / 'self_model.json')),
        ):
            p = patch.object(obj, key, value); p.start(); self.addCleanup(p.stop)
        init_db.init_database(verbose=False)
        pesos_treinados._detectar.cache_clear()
        self.addCleanup(pesos_treinados._detectar.cache_clear)


class PesosTreinadosTests(Fixture):
    def selecionar(self, alias='hoshino-treinada:latest', kind='trained', dataset=None):
        cfg = self.root / 'compartilhado/config/neural9b_modes.json'
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({'executor_versions': {'hoshino': {'primary': 'qwen35-9b', 'models': {
            'qwen35-9b': {'alias': alias, 'kind': kind, 'ref': 'abc123' + (':484' if kind == 'checkpoint' else ''),
                          'entity': 'hoshino', 'model_id': 'qwen35-9b',
                          'source_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64}}}}}))
        jobs = self.root / 'lab/controle-laboratorio/treinamento-unificado/jobs'
        jobs.mkdir(parents=True, exist_ok=True)
        (jobs / 'abc123.json').write_text(json.dumps({
            'id': 'abc123', 'entity': 'hoshino', 'action': 'train', 'state': 'completed',
            'plan': {'dataset': dataset or corpus_atual.dataset_id('hoshino')}}))
        for obj, key, value in ((config, 'RAIZ', self.root), (config, 'MODEL_NAME', 'hoshino-treinada:latest')):
            p = patch.object(obj, key, value); p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'HOSHINO_LAB_HOME': str(self.root / 'lab')}); p.start(); self.addCleanup(p.stop)
        os.environ.pop('HOSHINO_PROMPT_IDENTIDADE', None)
        pesos_treinados._detectar.cache_clear()

    def test_trained_on_current_corpus_and_loaded_alias_is_detected(self):
        self.selecionar()
        found = pesos_treinados.identidade_nos_pesos()
        self.assertEqual(found['corpus'], corpus_atual.CORPUS)
        self.assertEqual(found['treino'], 'abc123')

    def test_other_alias_original_or_old_corpus_keep_full_prompt(self):
        for kwargs in (dict(alias='outra:latest'), dict(kind='original'),
                       dict(dataset='pacote_identidade_v4:hoshino')):
            with self.subTest(**kwargs):
                self.selecionar(**kwargs)
                self.assertEqual(pesos_treinados.identidade_nos_pesos(), {})

    def test_override_forces_either_mode(self):
        self.selecionar()
        with patch.dict(os.environ, {'HOSHINO_PROMPT_IDENTIDADE': 'completo'}):
            self.assertEqual(pesos_treinados.identidade_nos_pesos(), {})
        self.selecionar(alias='outra:latest')
        with patch.dict(os.environ, {'HOSHINO_PROMPT_IDENTIDADE': 'reduzido'}):
            self.assertTrue(pesos_treinados.identidade_nos_pesos())


class PromptReduzidoTests(Fixture):
    def prompt(self, treinada, situacao=None):
        with patch.object(pesos_treinados, 'identidade_nos_pesos', return_value={'corpus': 'x'} if treinada else {}):
            return prompting.montar_prompt_sistema(situacao=situacao)

    def test_trained_prompt_drops_what_the_weights_learned_and_keeps_operations(self):
        completo, reduzido = self.prompt(False), self.prompt(True)
        self.assertLess(len(reduzido), 0.75 * len(completo))
        self.assertIn('SOBRE FALAR E FICAR QUIETA', completo)
        self.assertNotIn('FICAR QUIETA', reduzido)  # contradizia o despertar treinado
        self.assertIn('não sou a personagem', reduzido)
        for bloco in ('[CASA COMPARTILHADA]', '[JULGAMENTO ANTES DE AGIR]', '[O QUE EU TENHO NAS MÃOS]',
                      'Falo de mim sempre no feminino', 'Não invento memória'):
            self.assertIn(bloco, reduzido)
        self.assertNotIn('[MODALIDADE E CANAL]', reduzido)  # o FERRAMENTAS longo (1.004 tokens na Lilith)

    def test_simple_conversation_still_omits_tool_block(self):
        self.assertNotIn('[O QUE EU TENHO NAS MÃOS]', self.prompt(True, situacao='oi, tudo bem?'))


class DespertarKernelTests(Fixture):
    def situacao(self, hora=15):
        return dict(agora=datetime(2026, 11, 6, hora), eventos=[], usuario_presente=None,
                    segundos_sem_interacao_observados=30, segundos_ociosos=0)

    def estado(self, **extra):
        return dict(dict(despertar_pendente=True, despertar_fatos={'agora': '06/11/2026 15:00'},
                         modo_silencioso=False, ultima_fala=None), **extra)

    def test_wake_speaks_without_anchor_or_confirmed_presence(self):
        d = kernel.deliberar(self.situacao(), {}, self.estado())
        self.assertEqual(d['tipo'], 'despertar')
        self.assertIn('despertar', kernel.FALANTES)
        self.assertEqual(d['fatos']['agora'], '06/11/2026 15:00')

    def test_silent_mode_quiet_hours_busy_and_reminder_win(self):
        self.assertNotEqual(kernel.deliberar(self.situacao(), {}, self.estado(modo_silencioso=True))['tipo'], 'despertar')
        with patch.object(config, 'HORARIO_SILENCIO', (0, 7)):
            self.assertNotEqual(kernel.deliberar(self.situacao(hora=3), {}, self.estado())['tipo'], 'despertar')
        self.assertEqual(kernel.deliberar(self.situacao(), {}, self.estado(ocupada=True))['tipo'], 'nada')
        lembrete = dict(self.situacao(), gatilhos_diretos=[{'tipo': 'lembrete', 'id': 'r1', 'texto': 'remédio'}])
        self.assertEqual(kernel.deliberar(lembrete, {}, self.estado())['tipo'], 'avisar')

    def test_wake_prompt_orients_and_asks_for_one_message(self):
        p = prompting.prompt_por_intencao({'tipo': 'despertar', 'fatos': {
            'agora': '06/11/2026 15:00', 'mensagens_registradas': 0, 'usuario_presente': False}})
        self.assertIn('histórico de conversas está vazio', p)
        self.assertIn('get_system_time', p)
        self.assertIn('UMA mensagem', p)

    def test_explore_prompt_is_short_but_keeps_resume_and_receipts(self):
        p = prompting.prompt_por_intencao({'tipo': 'explorar'})
        self.assertLess(len(p), 1400)
        for trecho in ('minha_atividade', 'ler_resultado', 'recibo', 'canal global'):
            self.assertIn(trecho, p)


class DespertarFalaTests(Fixture):
    def test_wake_message_may_introduce_herself_but_not_be_filler(self):
        apresentacao = 'Eu sou a Hoshino, acabei de acordar. Tem alguém aí?'
        ok, motivo = autonomy.validar_fala_autonoma(apresentacao, {'tipo': 'despertar'})
        self.assertTrue(ok, motivo)
        ok, motivo = autonomy.validar_fala_autonoma(apresentacao, {'tipo': 'falar'})
        self.assertFalse(ok, motivo)  # fora do despertar, autoapresentação continua barrada
        self.assertFalse(autonomy.validar_fala_autonoma('Estou por aqui se precisar.', {'tipo': 'despertar'})[0])
        self.assertFalse(autonomy.validar_fala_autonoma('SILENCIO', {'tipo': 'despertar'})[0])

    def app(self):
        import main
        with patch.object(main, 'semear_origem'):
            app = main.InterfaceHoshino()
        app.sys_log = Mock(); app.chat_log = Mock(); app.situacao = {}
        return app

    def test_wake_is_offered_once_after_delay_and_cancelled_by_human_first(self):
        app = self.app()
        inicio = app._despertar_inicio_monotonic
        self.assertFalse(app._despertar_pendente(inicio + config.DESPERTAR_ATRASO_SEGUNDOS - 1))
        self.assertTrue(app._despertar_pendente(inicio + config.DESPERTAR_ATRASO_SEGUNDOS))
        app.ultima_interacao_monotonic = inicio + 5
        self.assertFalse(app._despertar_pendente(inicio + config.DESPERTAR_ATRASO_SEGUNDOS + 1))
        self.assertTrue(app._despertar_feito)
        tarde = self.app()
        self.assertFalse(tarde._despertar_pendente(tarde._despertar_inicio_monotonic + config.DESPERTAR_JANELA_SEGUNDOS + 1))

    def test_initiative_speech_goes_to_the_central_chat_thread(self):
        app = self.app()
        app.responder = AsyncMock(return_value={'status': 'answered'})
        asyncio.run(app.agir_falando({'tipo': 'despertar', 'motivo': 'acordei', 'fatos': {}}))
        kwargs = app.responder.await_args.kwargs
        self.assertEqual((kwargs['canal_lote'], kwargs['responder_para']), ('localhub', 'usuario'))
        self.assertEqual(kwargs['chave_conversa'][:2], ('localhub', 'usuario'))
        self.assertTrue(app._despertar_feito)
        self.assertFalse(app._despertar_pendente(time.monotonic() + 60))


if __name__ == '__main__':
    unittest.main()
