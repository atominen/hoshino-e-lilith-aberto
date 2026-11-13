"""Estado persistente e isolamento de caminhos da reflexão noturna."""
import os
import sys
import tempfile
from datetime import datetime, timezone
import json
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch
import asyncio
import hashlib
import sqlite3
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import config
from mind import night_reflection


def main():
    runtime_original = config.RUNTIME_DIR
    try:
        with tempfile.TemporaryDirectory(prefix="hoshino_noite_") as tmp:
            config.RUNTIME_DIR = tmp
            agora = datetime(2026, 9, 18, 23, 0)
            night_reflection.solicitar("teste")
            assert night_reflection.pendente()
            assert night_reflection.motivo_pendente() == "teste"
            night_reflection.marcar_concluida(agora, "teste")
            assert night_reflection.concluida_na_noite(agora)
            assert not night_reflection.pendente()
            assert (Path(tmp) / "reflexao_noturna.json").is_file()
            assert night_reflection.aviso_de_sono("vou dormir agora, boa noite")
            assert night_reflection.aviso_de_sono("tchau, fui deitar")
            assert not night_reflection.aviso_de_sono("boa noite, tudo bem?")
            print("Reflexão noturna: estado dinâmico e marcação únicos confirmados.")
    finally:
        config.RUNTIME_DIR = runtime_original


class NightFixture:
    def setUp(self):
        from memory.sqlite import init_db
        from core import bd
        self.bd = bd
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        for obj, name, value in ((config, 'RUNTIME_DIR', temp.name),
                                 (config, 'EVENT_LOG_DIR', str(Path(temp.name)/'events')),
                                 (config, 'DB_PATH', str(Path(temp.name)/'mind.db')),
                                 (init_db, 'DB_PATH', str(Path(temp.name)/'mind.db')),
                                 (config, 'LOCAL_TIMEZONE', 'America/Sao_Paulo'),
                                 (config, 'REFLEXAO_NOTURNA_INICIO', 22), (config, 'REFLEXAO_NOTURNA_FIM', 7)):
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        init_db.init_database(verbose=False)
        self.now = datetime(2026, 10, 10, 2, 30, tzinfo=timezone.utc)  # dia 9, 23:30 local


class DailySummaryTests(NightFixture, unittest.TestCase):
    def populate(self, count=12, length=2000):
        for i in range(count):
            self.bd.executar("INSERT INTO episodes(id,created_at,what_happened,source,context) VALUES(?,?,?,?,?)",
                             (f'daily-{i}', '2026-10-10T02:00:00Z', 'aprendizado '+str(i)+'x'*length,
                              'conversa',json.dumps({'autoria':{'autor_nome':'Gustavo','message_id':f'm{i}'}})), strict=True)

    def test_all_fragments_eventually_reviewed_without_limits_losing_sources(self):
        from mind import daily_summary as daily
        self.populate()
        rounds=0
        while (prepared:=daily.next_batch(agora=self.now,max_chars=2200)):
            result=daily.commit(prepared,'Interpretação provisória; consultar os IDs originais.')
            self.assertTrue(result['committed']);rounds+=1
            self.assertLess(rounds,100)
        rows=daily.batches('2026-10-09')
        sources=[s for r in rows for s in r['coverage']['sources']]
        self.assertGreater(rounds,12)
        self.assertEqual({s['id'] for s in sources},{f'daily-{i}' for i in range(12)})
        self.assertEqual(len(sources),len({s['part_key'] for s in sources}))
        self.assertTrue(all('Gustavo' in self.bd.um('SELECT context FROM episodes WHERE id=?',(s['id'],))['context'] for s in sources))

    def test_restart_late_arrival_idempotent_commit_and_no_fact_promotion(self):
        from mind import daily_summary as daily
        self.populate(1,100)
        prepared=daily.prepare('2026-10-09',agora=self.now)
        daily.commit(prepared,'Minha interpretação, não fato novo.')
        self.assertTrue(daily.commit(prepared,'Outra resposta não deve substituir o primeiro commit.')['reused'])
        self.assertIsNone(daily.next_batch(agora=self.now))
        self.bd.executar("INSERT INTO episodes(id,created_at,what_happened) VALUES('late','2026-10-10T01:00:00Z','Chegada tardia')",strict=True)
        next_day=datetime(2026,10,11,2,tzinfo=timezone.utc)
        again=daily.next_batch(agora=next_day)
        self.assertEqual(again['coverage']['day'],'2026-10-09')
        self.assertEqual(again['coverage']['sources'][0]['id'],'late')
        self.assertEqual(daily.recall('2026-10-09')['type'],'interpretacao')
        self.assertEqual(self.bd.um('SELECT COUNT(*) n FROM memories')['n'],0)

    def test_failure_empty_output_and_source_change_do_not_acknowledge(self):
        from mind import daily_summary as daily
        self.populate(1,100)
        prepared=daily.prepare('2026-10-09',agora=self.now)
        with self.assertRaises(ValueError):daily.commit(prepared,'')
        self.bd.executar("UPDATE episodes SET what_happened='novo'",strict=True)
        with self.assertRaises(ValueError):daily.commit(prepared,'Não deve consumir evidência antiga.')
        self.assertFalse(daily.batches('2026-10-09'))

    def test_oversized_context_and_escaped_content_do_not_stall_incremental_progress(self):
        from mind import daily_summary as daily
        self.populate(1,100)
        context=json.dumps({'autoria':{'autor_nome':'Gustavo'},'extra':'\\"'*6000})
        self.bd.executar('UPDATE episodes SET context=?',(context,),strict=True)
        consumed=0
        while (prepared:=daily.next_batch(agora=self.now,max_chars=2200)):
            self.assertTrue(prepared['coverage']['sources'])
            self.assertLessEqual(len(prepared['prompt']),2700)
            daily.commit(prepared,'Fragmento interpretado; contexto integral continua na origem.')
            consumed+=1;self.assertLess(consumed,200)
        self.assertGreater(consumed,12)
        self.assertEqual(self.bd.um('SELECT context FROM episodes')['context'],context)

    def test_legacy_fragment_ranges_are_preserved_and_not_reprocessed(self):
        from mind import daily_summary as daily
        self.populate(1,2400)
        with patch.object(daily,'FRAGMENT_CHARS',1000):
            old=daily.prepare('2026-10-09',agora=self.now,max_chars=2200)
            daily.commit(old,'Lote anterior compatível.')
        new=daily.prepare('2026-10-09',agora=self.now,max_chars=2200)
        consumed=old['coverage']['sources'][0]
        self.assertTrue(new['prompt'])
        self.assertTrue(all(s['start']>=consumed['end'] for s in new['coverage']['sources']))

    def test_existing_tick_yields_to_chat_and_failed_summary_does_not_advance_coverage(self):
        from main import InterfaceHoshino
        from mind import daily_summary as daily
        self.populate(1,100)
        fake=SimpleNamespace(trava_modelo=asyncio.Lock(),_fila_conversa=['user'],ultima_interacao=None,
            prompt_sistema='Identidade existente',chamar_modelo=AsyncMock(return_value={'content':''}))
        self.assertFalse(asyncio.run(InterfaceHoshino.talvez_resumir_dia(fake,self.now)))
        fake.chamar_modelo.assert_not_awaited();fake._fila_conversa=[]
        self.assertTrue(asyncio.run(InterfaceHoshino.talvez_resumir_dia(fake,self.now)))
        self.assertFalse(daily.batches('2026-10-09'))
        self.assertFalse(asyncio.run(InterfaceHoshino.talvez_resumir_dia(fake,self.now)))
        fake.chamar_modelo.assert_awaited_once()

    def test_event_only_day_and_real_tool_end_contract_are_reviewed_without_private_text(self):
        from core import history,diagnostics
        from mind import daily_summary as daily
        # history.DB is an import-time path; this fixture changes RUNTIME_DIR.
        with patch.object(history,'DB',Path(config.RUNTIME_DIR)/'history.sqlite3'):
            history.event('tool.end',component='diagnostics',data={'tool':'workspace','request_id':'req-file','result':'arquivo verificado'},timestamp='2026-10-10T02:00:00Z')
            history.event('tool.end',component='diagnostics',data=diagnostics._redact({'tool':'diario','result':'PRIVATE NOTE'}),timestamp='2026-10-10T02:00:01Z')
            prepared=daily.next_batch(agora=self.now)
            self.assertEqual(prepared['coverage']['day'],'2026-10-09');self.assertIn('req-file',prepared['prompt'])
            self.assertNotIn('PRIVATE NOTE',prepared['prompt'])
            daily.commit(prepared,'Recibo de arquivo; conteúdo privado ausente.')
            self.assertIsNone(daily.next_batch(agora=self.now))


class RecomecoDaMemoriaTests(NightFixture, unittest.TestCase):
    """11/11 (teste de uso): depois do "apagar tudo", 24 resumos de 06/11 voltaram dos recibos antigos."""

    def episodio(self, ident, quando):
        self.bd.executar("INSERT INTO episodes(id,created_at,what_happened,source) VALUES(?,?,?,?)",
                         (ident, quando, 'Hoje eu li o LEIA-ME.md '+ident, 'conversa'), strict=True)

    def test_dias_antes_do_recomeco_nao_viram_resumo_nem_a_parte_de_antes_no_mesmo_dia(self):
        from mind import daily_summary as daily
        self.episodio('antigo', '2026-10-08T15:00:00Z')        # dia 8, antes do apagamento
        self.episodio('mesmo-dia-antes', '2026-10-09T15:00:00Z')  # dia 9, 12:00 local, antes
        self.episodio('depois', '2026-10-10T01:00:00Z')        # dia 9, 22:00 local, depois
        Path(config.RUNTIME_DIR, 'memoria_recomeco.json').write_text(json.dumps({'desde': '2026-10-09T20:00:00+00:00'}))
        prepared = daily.next_batch(agora=self.now)
        self.assertEqual(prepared['coverage']['day'], '2026-10-09')
        self.assertEqual([s['id'] for s in prepared['coverage']['sources']], ['depois'])

    def test_manifesto_de_backup_nao_e_recomeco_so_a_marca_de_sucesso(self):
        # Revisão 11/11: o manifesto é escrito antes de apagar; tentativa abortada não pode esconder dias do resumo.
        from mind import daily_summary as daily
        pasta = Path(config.RUNTIME_DIR, 'memory-backups', 'manual-abc'); pasta.mkdir(parents=True)
        (pasta/'manifest.json').write_text(json.dumps({'scope': 'experience-v1'}))
        self.assertIsNone(daily.inicio_da_memoria())
        Path(config.RUNTIME_DIR, 'memoria_recomeco.json').write_text(json.dumps({'desde': '2023-11-14T22:13:20+00:00'}))
        self.assertEqual(daily.inicio_da_memoria(), 1700000000)

    def test_reflexao_nao_guarda_conclusao_sobre_pessoas_nem_lugar_inventado(self):
        linhas = night_reflection.extrair_linhas(
            "[APRENDI_SOBRE_PESSOAS] Gustavo prefere ser chamado por nome completo, ele me disse isso.\n"
            "[APRENDI_SOBRE_MIM] Acordei e avisei no chat por iniciativa própria, sem esperar.\n"
            "[APRENDI_SOBRE_AMBIENTE] Eu existo aqui dentro desta máquina e ela é a minha casa.\n"
            "[PARA_DEPOIS] Conferir a ferramenta antes de dizer que olhei alguma coisa.")
        ficam = night_reflection.filtrar(linhas, material='alguém: oi. Lilith: oi.')
        self.assertEqual([t for t, _ in ficam], ['mim', 'depois'])
        self.assertNotIn('APRENDI_SOBRE_PESSOAS', night_reflection.PROMPT)
        # O lugar dito no material sustenta a conclusão.
        self.assertEqual(len(night_reflection.filtrar(linhas[2:3], material='a pessoa disse: você mora aqui dentro desta máquina')), 1)


class NightClockTests(NightFixture, unittest.TestCase):
    def test_night_key_and_schedule_use_local_timezone_for_utc_input(self):
        self.assertTrue(night_reflection.horario_noturno(self.now))
        self.assertEqual(night_reflection._chave_noite(self.now), '2026-10-09')
        self.assertFalse(night_reflection.horario_noturno(datetime(2026, 10, 10, 14, tzinfo=timezone.utc)))

    def test_concluded_marker_uses_same_instant_as_key_and_survives_read(self):
        self.assertTrue(night_reflection.marcar_concluida(self.now))
        raw = json.loads(night_reflection._state_path().read_text())
        self.assertEqual(raw['concluida_em'], '2026-10-10T02:30:00.000+00:00')
        self.assertTrue(night_reflection.concluida_na_noite(self.now))
        self.assertEqual(json.loads(night_reflection._state_path().read_text()), raw)

    def test_daily_material_uses_both_bounds_and_excludes_future_or_invalid_evidence(self):
        for eid, ts in [('yesterday', '2026-10-09T02:59:59Z'), ('today-utc', '2026-10-10T02:29:59Z'),
                        ('today-legacy', '2026-10-09T12:00:00'), ('tomorrow', '2026-10-10T03:00:00Z'),
                        ('future-today', '2026-10-10T02:45:00Z'), ('invalid', 'inválido')]:
            self.bd.executar("INSERT INTO episodes(id,created_at,what_happened,status) VALUES(?,?,?,'active')", (eid, ts, eid), strict=True)
            self.bd.executar('INSERT INTO emotion_log(id,created_at,emocao,intensidade,motivo) VALUES(?,?,?,?,?)',
                             ('emotion-'+eid, ts, 'alegria', .2, eid), strict=True)
        with patch('core.history.local_now', return_value=self.now):
            text = night_reflection.material_do_dia()
        self.assertIn('today-utc', text); self.assertIn('today-legacy', text)
        for excluded in ('yesterday', 'tomorrow', 'future-today', 'invalid'):
            self.assertNotIn(excluded, text)

    def test_daily_event_log_is_local_and_future_events_are_not_reflection_evidence(self):
        from core import history
        path = Path(config.EVENT_LOG_DIR)/'events_2026-10-09.jsonl'
        path.parent.mkdir(parents=True)
        rows = [dict(tipo='erro', detalhe=label, ts=timestamp) for label, timestamp in (
            ('evento-utc', '2026-10-10T02:29:59Z'), ('evento-legado', '2026-10-09T12:00:00'),
            ('evento-futuro', '2026-10-10T02:45:00Z'), ('evento-ontem', '2026-10-09T02:59:59Z'),
            ('evento-sem-data', 'inválido'))]
        path.write_text('\n'.join(json.dumps(row) for row in rows))
        before = path.read_bytes()
        with patch.object(history, 'local_now', return_value=self.now):
            material = night_reflection.material_do_dia()
        self.assertIn('evento-utc', material); self.assertIn('evento-legado', material)
        for label in ('evento-futuro', 'evento-ontem', 'evento-sem-data'):
            self.assertNotIn(label, material)
        self.assertEqual(path.read_bytes(), before)

    def test_event_writer_keeps_local_filename_but_new_timestamps_are_utc(self):
        from core import history
        import main as app_main
        with patch.object(history, 'local_now', return_value=self.now), patch.object(app_main.diagnostics, 'emit'):
            app_main.registrar_evento('erro', 'descartável')
        file = Path(config.EVENT_LOG_DIR)/'events_2026-10-09.jsonl'
        self.assertEqual(json.loads(file.read_text())['ts'], '2026-10-10T02:30:00.000+00:00')

    def test_new_night_reflection_is_utc_and_remains_reflection_with_evidence(self):
        self.bd.executar("INSERT INTO reflections(id,created_at,conteudo) VALUES('legacy','2026-10-09T11:30:00','anterior')", strict=True)
        before = self.bd.um("SELECT * FROM reflections WHERE id='legacy'")
        self.assertEqual(night_reflection.salvar([('mim', 'Ainda devo verificar as minhas interpretações.')], 'ensaio-noturno'), 1)
        new = self.bd.um("SELECT * FROM reflections WHERE tema='noturna:mim'")
        self.assertTrue(new['created_at'].endswith('+00:00'))
        self.assertEqual(new['tipo'], 'reflexao')
        self.assertEqual(new['evidencias'], 'ensaio-noturno')
        self.assertEqual(self.bd.um("SELECT * FROM reflections WHERE id='legacy'"), before)


class NightEvidenceTests(NightFixture, unittest.TestCase):
    def episode(self, eid='ep-first', **fields):
        row = dict(id=eid, created_at='2026-10-10T02:00:00Z', what_happened='Tentativa observada',
                   action_taken='ler arquivo', result='falhou: arquivo ausente', is_success=0,
                   source='conversa', context=json.dumps({'autoria': {'autor_nome': 'Pessoa A', 'message_id': 'msg-A'}}))
        row.update(fields)
        self.bd.executar(f"INSERT INTO episodes({','.join(row)}) VALUES({','.join('?' for _ in row)})", tuple(row.values()), strict=True)

    def prepare(self, limit=None):
        return night_reflection.preparar_material(limit, agora=self.now)

    def run_cycle(self, model=None):
        import main as app_main
        fake = SimpleNamespace(ultima_interacao=None, trava_modelo=asyncio.Lock(), _fila_conversa=[],
                               prompt_sistema='Identidade preservada', sys_log=Mock(),
                               chamar_modelo=AsyncMock(side_effect=model) if model else AsyncMock(return_value={
                                   'content': '[PENDENCIAS] Ainda preciso confirmar o resultado da tentativa.'}))
        with patch('core.history.local_now', return_value=self.now):
            asyncio.run(app_main.InterfaceHoshino.talvez_refletir_noturno(fake, self.now))
        return fake

    def test_episode_result_origin_author_and_full_timestamp_reach_context(self):
        self.episode()
        with patch('core.history.local_now', return_value=self.now):
            text = night_reflection.material_do_dia()
        for field in ('ep-first', 'falhou: arquivo ausente', '2026-10-10T02:00:00Z', 'Pessoa A', 'msg-A'):
            self.assertIn(field, text)

    def test_budget_keeps_whole_records_and_explicitly_excludes_oversized_entry(self):
        self.episode('ep-too-large', what_happened='SEGREDO_LONGO ' * 300)
        self.bd.executar("INSERT INTO goals(id,description,status,priority,created_at) VALUES('goal-short','Conferir arquivo','active',1,?)", (self.now.isoformat(),), strict=True)
        prepared = self.prepare(1000)
        self.assertLessEqual(len(prepared['material']), 1000)
        self.assertIn('goal-short', prepared['material'])
        self.assertIn('não incluídos', prepared['material'])
        self.assertNotIn('SEGREDO_LONGO', prepared['material'])
        refs = prepared['evidencias']['sources']
        self.assertEqual([(r['table'], r['id']) for r in refs], [('goals', 'goal-short')])
        self.assertEqual(prepared['evidencias']['limits']['omitted_by_budget'], 1)
        self.assertEqual(self.bd.um("SELECT what_happened FROM episodes WHERE id='ep-too-large'")['what_happened'], 'SEGREDO_LONGO ' * 300)

    def test_material_preserves_memory_category_zero_confidence_and_message_evidence(self):
        self.bd.executar("INSERT INTO memories(id,type,created_at,source,confidence,content,entities,links) VALUES(?,?,?,?,?,?,?,?)",
                         ('mem-hyp', 'hipotese', self.now.isoformat(), 'Pessoa A', 0., 'Talvez goste de azul.', 'Pessoa A',
                          json.dumps([{'message_id': 'msg-A', 'listener': 'lilith'}])), strict=True)
        with patch.object(config, 'ENTIDADE_ID', 'lilith'):
            prepared = self.prepare()
        self.assertEqual(prepared['evidencias']['entity'], 'lilith')
        ref = prepared['evidencias']['sources'][0]
        self.assertEqual((ref['type'], ref['source'], ref['confidence']), ('hipotese', 'Pessoa A', 0.))
        self.assertEqual(ref['evidence'][0]['message_id'], 'msg-A')
        self.assertIn('[hipotese]', prepared['material'])
        self.assertIn('confiança=0.0', prepared['material'])

    def test_prepared_context_is_saved_not_recollected_after_model_returns(self):
        self.episode()
        async def reply(messages, **kwargs):
            self.assertIn('ep-first', messages[1]['content'])
            self.episode('ep-late')
            return {'content': '[PENDENCIAS] Ainda preciso confirmar o resultado da tentativa.'}
        fake = self.run_cycle(reply)
        fake.chamar_modelo.assert_awaited_once()
        row = self.bd.um("SELECT * FROM reflections WHERE tema='noturna:pendencias'")
        refs = json.loads(row['evidencias'])
        self.assertEqual(refs['kind'], 'night_reflection_context')
        self.assertEqual([r['id'] for r in refs['sources']], ['ep-first'])
        self.assertEqual(refs['sources'][0]['context']['autoria']['message_id'], 'msg-A')
        self.assertEqual(row['tipo'], 'reflexao')
        from mind import reflection
        recovered = reflection.bloco_para_prompt()
        self.assertIn('ep-first', recovered)
        self.assertIn('NÃO SÃO FATOS', recovered)
        self.assertTrue(night_reflection.concluida_na_noite(self.now))

    def test_event_evidence_contains_real_file_line_and_timestamp_without_rewriting_log(self):
        path = Path(config.EVENT_LOG_DIR)/'events_2026-10-09.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text('\n'.join(json.dumps(x) for x in [
            {'ts':'2026-10-10T02:00:00Z','tipo':'erro','detalhe':{'request_id':'req-one'}},
            {'ts':'2026-10-10T02:45:00Z','tipo':'erro','detalhe':'futuro'}]))
        before = path.read_bytes()
        prepared = self.prepare()
        ref = prepared['evidencias']['sources'][0]
        self.assertEqual(ref['file'], path.name)
        self.assertEqual(ref['line'], 1)
        self.assertEqual(ref['timestamp'], '2026-10-10T02:00:00Z')
        self.assertEqual(ref['line_sha256'], hashlib.sha256(before.splitlines()[0]).hexdigest())
        self.assertIn('req-one', prepared['material'])
        self.assertNotIn('futuro', prepared['material'])
        self.assertEqual(path.read_bytes(), before)

    def test_all_tables_are_strict_and_read_failure_does_not_complete_the_night(self):
        self.episode()
        self.bd.executar('DROP TABLE goals', strict=True)
        night_reflection.solicitar('teste de erro')
        with patch('core.history.local_now', return_value=self.now):
            with self.assertRaises(sqlite3.Error):
                night_reflection.material_do_dia()
        fake = self.run_cycle()
        fake.chamar_modelo.assert_not_awaited()
        self.assertFalse(night_reflection.concluida_na_noite(self.now))
        self.assertTrue(night_reflection.pendente())

    def test_event_read_failure_is_not_equivalent_to_no_material(self):
        path = Path(config.EVENT_LOG_DIR)/'events_2026-10-09.jsonl'
        path.mkdir(parents=True)  # um arquivo ilegível, não um dia sem eventos
        night_reflection.solicitar('teste de erro')
        with patch('core.history.local_now', return_value=self.now):
            with self.assertRaises(OSError):
                night_reflection.material_do_dia()
        fake = self.run_cycle()
        fake.chamar_modelo.assert_not_awaited()
        self.assertTrue(night_reflection.pendente())
        self.assertFalse(night_reflection.concluida_na_noite(self.now))

    def test_row_caps_are_explicit_and_read_only(self):
        for i in range(161):
            self.episode('ep-'+str(i), what_happened='Evento curto')
        prepared = self.prepare(200000)
        self.assertEqual(prepared['evidencias']['limits']['row_limits_reached'], ['episodes'])
        self.assertIn('limite de registros', prepared['material'])
        self.assertEqual(len(prepared['evidencias']['sources']), 160)
        self.assertEqual(len(self.bd.consultar('SELECT id FROM episodes')), 161)

    def test_material_only_too_large_is_not_a_successful_empty_night(self):
        self.episode(what_happened='evento ' * 4000)
        night_reflection.solicitar('revisão')
        with patch.object(config, 'REFLEXAO_NOTURNA_MAX_CHARS', 1000):
            fake = self.run_cycle()
        fake.chamar_modelo.assert_not_awaited()
        self.assertFalse(night_reflection.concluida_na_noite(self.now))
        self.assertTrue(night_reflection.pendente())

    def test_material_is_reduced_to_fit_identity_and_output_in_the_window(self):
        for i in range(40):self.episode(f'ep-{i}',what_happened='evento observado '*60)
        night_reflection.solicitar('revisão')
        import main as app_main
        fake = SimpleNamespace(ultima_interacao=None, trava_modelo=asyncio.Lock(), _fila_conversa=[],
                               prompt_sistema='Identidade preservada. '*900, sys_log=Mock(),
                               chamar_modelo=AsyncMock(return_value={'content':'[PENDENCIAS] Ainda preciso confirmar o resultado da tentativa.'}))
        with patch('core.history.local_now', return_value=self.now),patch.object(config,'NUM_CTX',16384):
            asyncio.run(app_main.InterfaceHoshino.talvez_refletir_noturno(fake, self.now))
        messages=fake.chamar_modelo.call_args.args[0]
        self.assertEqual(messages[0]['content'],'Identidade preservada. '*900)  # identidade nunca é cortada
        from core import resource_manager
        output=config.NUM_PREDICT if config.NUM_PREDICT>0 else 4096
        self.assertLessEqual(resource_manager.context_requirement(messages,output_max=output)[1],16384)

    def test_window_too_small_waits_instead_of_retrying_every_tick(self):
        self.episode(what_happened='evento observado')
        night_reflection.solicitar('revisão')
        import main as app_main
        fake = SimpleNamespace(ultima_interacao=None, trava_modelo=asyncio.Lock(), _fila_conversa=[],
                               prompt_sistema='x'*80000, sys_log=Mock(), chamar_modelo=AsyncMock())
        with patch('core.history.local_now', return_value=self.now):
            asyncio.run(app_main.InterfaceHoshino.talvez_refletir_noturno(fake, self.now))
            self.assertGreater(fake._reflexao_noturna_espera_ate,time.monotonic())
            with patch.object(night_reflection,'preparar_material',side_effect=AssertionError('tentou de novo')):
                asyncio.run(app_main.InterfaceHoshino.talvez_refletir_noturno(fake, self.now))
        fake.chamar_modelo.assert_not_awaited();self.assertTrue(night_reflection.pendente())

    def test_background_review_waits_while_a_task_worker_is_active(self):
        # 26/10: o resumo diário começou no meio de uma tarefa do Minecraft e travou a decisão por 5 min.
        self.episode(what_happened='evento observado')
        night_reflection.solicitar('revisão')
        import main as app_main
        busy = SimpleNamespace(done=lambda: False)
        fake = SimpleNamespace(ultima_interacao=None, trava_modelo=asyncio.Lock(), _fila_conversa=[],
                               _workers_por_chave={'tarefa': busy}, prompt_sistema='Identidade', sys_log=Mock(),
                               chamar_modelo=AsyncMock())
        with patch('core.history.local_now', return_value=self.now):
            self.assertFalse(asyncio.run(app_main.InterfaceHoshino.talvez_resumir_dia(fake, self.now)))
            asyncio.run(app_main.InterfaceHoshino.talvez_refletir_noturno(fake, self.now))
        fake.chamar_modelo.assert_not_awaited();self.assertTrue(night_reflection.pendente())

    def test_invalid_response_does_not_claim_reflection_saved(self):
        self.episode()
        night_reflection.solicitar('revisão')
        async def invalid(*args, **kwargs):
            return {'content': 'Saída sem as conclusões solicitadas.'}
        fake = self.run_cycle(invalid)
        fake.chamar_modelo.assert_awaited_once()
        self.assertEqual(self.bd.consultar('SELECT id FROM reflections'), [])
        self.assertFalse(night_reflection.concluida_na_noite(self.now))
        self.assertTrue(night_reflection.pendente())

    def test_retrieval_does_not_reinject_the_entire_daily_evidence_snapshot(self):
        for i in range(12):
            self.episode('ep-'+str(i), context=json.dumps({'autoria': {'autor_nome': 'Pessoa A', 'message_id': 'msg-A'},
                                                        'resultado_antigo': 'não reinjetar ' * 80}))
        prepared = self.prepare(30000)
        night_reflection.salvar([('mim', 'Ainda devo verificar as minhas interpretações.')], evidencias=prepared['evidencias'])
        from mind import reflection
        stored = self.bd.um("SELECT * FROM reflections WHERE tema='noturna:mim'")
        for recovered in (reflection.ultimas()[0], reflection.bloco_para_prompt()):
            self.assertLess(len(recovered), 4500)
            self.assertIn('sources_omitted', recovered)
            self.assertIn(stored['id'], recovered)
            self.assertIn('msg-A', recovered)
            self.assertNotIn('não reinjetar', recovered)
        self.assertEqual(len(json.loads(stored['evidencias'])['sources']), 12)
        self.assertEqual(self.bd.um("SELECT * FROM reflections WHERE id=?", (stored['id'],)), stored)

    def test_corrupt_utf8_event_still_references_exact_original_line_bytes(self):
        path = Path(config.EVENT_LOG_DIR)/'events_2026-10-09.jsonl'
        path.parent.mkdir(parents=True)
        raw = b'{"ts":"2026-10-10T02:00:00Z","tipo":"erro","detalhe":"original-\xff"}'
        path.write_bytes(raw + b'\n')
        prepared = self.prepare()
        self.assertEqual(prepared['evidencias']['sources'][0]['line_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw + b'\n')

    def test_oversized_conclusion_is_not_cut_and_saved_as_if_complete(self):
        self.episode()
        night_reflection.solicitar('revisão')
        async def oversized(*args, **kwargs):
            return {'content': '[PENDENCIAS] ' + 'Preciso verificar isto. ' * 40}
        fake = self.run_cycle(oversized)
        fake.chamar_modelo.assert_awaited_once()
        self.assertEqual(self.bd.consultar('SELECT id FROM reflections'), [])
        self.assertTrue(night_reflection.pendente())
        self.assertFalse(night_reflection.concluida_na_noite(self.now))

    def test_prepared_evidence_from_another_entity_is_refused(self):
        self.episode()
        with patch.object(config, 'ENTIDADE_ID', 'hoshino'):
            prepared = self.prepare()
        with patch.object(config, 'ENTIDADE_ID', 'lilith'):
            with self.assertRaises(ValueError):
                night_reflection.prompt(preparado=prepared)
            with self.assertRaises(ValueError):
                night_reflection.salvar([('mim', 'Esta reflexão não pertence a este ouvinte.')], evidencias=prepared['evidencias'])
        self.assertEqual(self.bd.consultar('SELECT id FROM reflections'), [])


class NightRecoveryTests(NightFixture, unittest.TestCase):
    episode = NightEvidenceTests.episode
    run_cycle = NightEvidenceTests.run_cycle

    def test_committed_reflection_marker_failure_does_not_regenerate_on_restart(self):
        self.episode()
        night_reflection.solicitar('revisão antes do restart')
        with patch.object(night_reflection, 'marcar_concluida', return_value=False):
            first = self.run_cycle()
        first.chamar_modelo.assert_awaited_once()
        before = self.bd.consultar('SELECT * FROM reflections')
        self.assertEqual(len(before), 1)
        restarted = self.run_cycle()
        restarted.chamar_modelo.assert_not_awaited()
        self.assertEqual(self.bd.consultar('SELECT * FROM reflections'), before)
        self.assertTrue(night_reflection.concluida_na_noite(self.now))
        self.assertFalse(night_reflection.pendente())

    def test_second_save_preserves_first_batch_content_and_evidence(self):
        self.episode()
        prepared = night_reflection.preparar_material(agora=self.now)
        lines = [('mim', 'Devo verificar antes de afirmar um resultado.'),
                 ('pendencias', 'A tentativa de ler arquivo ainda exige confirmação.')]
        self.assertEqual(night_reflection.salvar(lines, 'origem inicial',
                         evidencias=prepared['evidencias'], agora=self.now), 2)
        before = self.bd.consultar('SELECT * FROM reflections ORDER BY id')
        self.assertEqual(night_reflection.salvar([('mim', 'Outro resultado não substitui o commit anterior.')],
                         'repetição', evidencias=prepared['evidencias'], agora=self.now), 2)
        self.assertEqual(self.bd.consultar('SELECT * FROM reflections ORDER BY id'), before)
        self.assertEqual(night_reflection.recuperar_salvas(self.now), 2)
        for row in before:
            envelope = json.loads(row['evidencias'])
            self.assertEqual(envelope['reason'], 'origem inicial')
            self.assertEqual(envelope['sources'], prepared['evidencias']['sources'])
            self.assertEqual(row['tipo'], 'reflexao')

    def test_batch_failure_rolls_back_all_conclusions_and_remains_retryable(self):
        self.episode()
        prepared = night_reflection.preparar_material(agora=self.now)
        self.bd.executar("CREATE TRIGGER fail_second BEFORE INSERT ON reflections "
                         "WHEN NEW.tema='noturna:pendencias' BEGIN SELECT RAISE(ABORT,'simulação'); END", strict=True)
        with self.assertRaises(sqlite3.Error):
            night_reflection.salvar([('mim', 'Conclusão anterior à falha simulada.'),
                                     ('pendencias', 'Conclusão que dispara a falha simulada.')],
                                    evidencias=prepared['evidencias'], agora=self.now)
        self.assertEqual(self.bd.consultar('SELECT id FROM reflections'), [])
        self.assertEqual(night_reflection.recuperar_salvas(self.now), 0)
        self.assertFalse(night_reflection.concluida_na_noite(self.now))

    def test_partial_or_modified_committed_batch_blocks_replay_instead_of_claiming_success(self):
        self.episode()
        prepared = night_reflection.preparar_material(agora=self.now)
        night_reflection.salvar([('mim', 'Conclusão registrada antes da interrupção.'),
                                 ('pendencias', 'Outra conclusão registrada antes da interrupção.')],
                                evidencias=prepared['evidencias'], agora=self.now)
        rows = self.bd.consultar('SELECT * FROM reflections ORDER BY id')
        self.bd.executar('UPDATE reflections SET conteudo=? WHERE id=?',
                         ('conteúdo alterado', rows[0]['id']), strict=True)
        night_reflection.solicitar('ensaio de integridade')
        with self.assertRaises(ValueError):
            night_reflection.recuperar_salvas(self.now)
        fake = self.run_cycle()
        fake.chamar_modelo.assert_not_awaited()
        self.assertTrue(night_reflection.pendente())
        self.assertFalse(night_reflection.concluida_na_noite(self.now))
        self.bd.executar('DELETE FROM reflections WHERE id=?', (rows[0]['id'],), strict=True)
        with self.assertRaises(ValueError):
            night_reflection.recuperar_salvas(self.now)
        self.run_cycle().chamar_modelo.assert_not_awaited()
        self.assertEqual(len(self.bd.consultar('SELECT id FROM reflections')), 1)

    def test_recovery_is_entity_and_night_specific_and_does_not_adopt_legacy(self):
        self.episode()
        night_reflection.salvar([('mim', 'Registro legado continua legível sem dono inventado.')])
        legacy = self.bd.consultar('SELECT * FROM reflections')
        self.assertEqual(night_reflection.recuperar_salvas(self.now), 0)
        with patch.object(config, 'ENTIDADE_ID', 'hoshino'):
            prepared = night_reflection.preparar_material(agora=self.now)
            night_reflection.salvar([('mim', 'Reflexão nova de Hoshino com noite confirmada.')],
                                    evidencias=prepared['evidencias'], agora=self.now)
            self.assertEqual(night_reflection.recuperar_salvas(self.now), 1)
            self.assertEqual(night_reflection.recuperar_salvas(datetime(2026, 10, 11, 2, 30,
                                                                       tzinfo=timezone.utc)), 0)
        with patch.object(config, 'ENTIDADE_ID', 'lilith'):
            self.assertEqual(night_reflection.recuperar_salvas(self.now), 0)
        self.assertEqual(self.bd.um('SELECT * FROM reflections WHERE id=?', (legacy[0]['id'],)), legacy[0])

    def test_pending_consume_failure_after_marker_commit_does_not_call_llm_again(self):
        self.episode()
        night_reflection.solicitar('ensaio de encerramento')
        with patch.object(night_reflection, 'consumir_pendente', return_value=False):
            first = self.run_cycle()
        first.chamar_modelo.assert_awaited_once()
        self.assertTrue(night_reflection.concluida_na_noite(self.now))
        self.assertTrue(night_reflection.pendente())
        before = self.bd.consultar('SELECT * FROM reflections')
        self.run_cycle().chamar_modelo.assert_not_awaited()
        self.assertFalse(night_reflection.pendente())
        self.assertEqual(self.bd.consultar('SELECT * FROM reflections'), before)

    def test_recovery_sql_read_failure_does_not_generate_or_mark_complete(self):
        self.episode()
        night_reflection.solicitar('ensaio de leitura')
        with patch.object(night_reflection.bd, 'conexao', side_effect=sqlite3.OperationalError('indisponível')):
            self.run_cycle().chamar_modelo.assert_not_awaited()
        self.assertTrue(night_reflection.pendente())
        self.assertFalse(night_reflection.concluida_na_noite(self.now))


if __name__ == "__main__":
    main()
    unittest.main(verbosity=2)
