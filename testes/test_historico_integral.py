"""Histórico real em SQLite temporário; nenhum banco mental/serviço é aberto."""
import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import config
from core import history
from tools import historico, terminal


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        for obj, key, value in (
            (history, 'DB', self.base / 'history.sqlite3'),
            (config, 'ENTIDADE_ID', 'lilith'),
            (config, 'ENTIDADE_NOME', 'Lilith'),
            (config, 'LOCAL_TIMEZONE', 'America/Sao_Paulo'),
            (config, 'ENTREGA_SAIDA', str(self.base / 'exports')),
        ):
            p = patch.object(obj, key, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def test_routine_checks_are_hidden_by_default_in_the_activity_tab(self):
        # 06/11 (pedido humano): decisões "nada" e avisos repetidos de VRAM somem da aba Atividade por padrão.
        history.message('in', 'user', 'abre o youtube', 'localhub')
        history.event('cognition.autonomy_decision', data={'tipo': 'nada', 'motivo': 'nenhuma pressão'})
        history.event('gpu.app_close_skipped', data={'reason': 'no_single_app_frees_enough'})
        history.event('cognition.autonomy_decision', data={'tipo': 'explorar', 'motivo': 'tempo livre'})
        history.event('tool.end', data={'tool': 'browser_abrir'})
        hidden = history.daily_records(None, newest_first=True, hide_routine=True)['items']
        kinds = [(r['record_kind'], r.get('kind'), (r.get('data') or {}).get('tipo')) for r in hidden]
        self.assertNotIn(('event', 'cognition.autonomy_decision', 'nada'), kinds)
        self.assertNotIn('gpu.app_close_skipped', [k for _, k, _ in kinds])
        self.assertIn(('event', 'cognition.autonomy_decision', 'explorar'), kinds)
        self.assertIn(('message', None, None), kinds)
        self.assertEqual(len(history.daily_records(None, hide_routine=False)['items']), 5)
        self.assertTrue(history.evento_rotineiro('cognition.autonomy_decision', {'tipo': 'nada'}))
        self.assertFalse(history.evento_rotineiro('cognition.autonomy_decision', {'tipo': 'falar'}))

    def add(self, ts, direction='in', **kwargs):
        with patch.object(history, 'utc_timestamp', return_value=ts):
            return history.message(direction, 'assistant' if direction == 'out' else 'user',
                                   kwargs.pop('content', 'Mensagem real'), **kwargs)

    def test_existing_integral_search_and_restart_remain_compatible(self):
        mid = history.message('in', 'user', 'mensagem integral para revisão', 'tui', session_id='teste')
        history.message('out', 'assistant', 'resposta integral confirmada', 'tui', session_id='teste')
        history._INITIALIZED_DB = None
        self.assertTrue(mid.startswith('msg-'))
        self.assertEqual(len(history.search('integral', 10)), 2)
        self.assertEqual(history.stats()['mensagens'], 2)

    def test_output_author_is_entity_not_recipient(self):
        history.message('out', 'assistant', 'Eu ouvi.', person={'id': 'gustavo', 'nome': 'Gustavo'})
        result = historico.recente()
        self.assertIn('Lilith: Eu ouvi.', result)
        self.assertNotIn('Hoshino:', result)
        self.assertNotIn('Gustavo: Eu ouvi.', result)

    def test_incoming_author_and_export_use_entity_identity(self):
        history.message('in', 'user', 'Sou Alistair.', person={'id': 'alistair', 'nome': 'Alistair'})
        history.message('out', 'assistant', 'Oi, Alistair.')
        self.assertIn('Alistair: Sou Alistair.', historico.buscar('Alistair'))
        path = Path(history.export_txt())
        self.assertEqual(path.name, 'historico_lilith.txt')
        self.assertIn('Alistair:', path.read_text())
        self.assertIn('Lilith:', path.read_text())
        self.assertNotIn('HOSHINO:', path.read_text())

    def test_unknown_incoming_author_is_not_invented(self):
        history.message('in', 'user', 'Texto sem autoria registrada.')
        self.assertIn('Autor não registrado:', historico.recente())

    def test_new_messages_events_are_utc_and_metadata_distinguishes_recipient(self):
        history.message('out', 'assistant', 'Olá', person={'id': 'gustavo', 'nome': 'Gustavo'},
                        metadata={'evidence': 'receipt-1'}, turn_id='turn-1', session_id='proc-1')
        history.event('test.event', data={'source_id': 'source-1'})
        with closing(sqlite3.connect(history.DB)) as db:
            row = db.execute('SELECT ts,person_name,metadata,turn_id,session_id FROM messages').fetchone()
            ts = db.execute('SELECT ts FROM events').fetchone()[0]
        self.assertTrue(row[0].endswith('+00:00'))
        self.assertTrue(ts.endswith('+00:00'))
        meta = json.loads(row[2])
        self.assertEqual((meta['author_id'], meta['author_name'], meta['observer_entity']), ('lilith', 'Lilith', 'lilith'))
        self.assertEqual(meta['recipient_id'], 'gustavo')
        self.assertEqual(row[1], 'Gustavo')  # O contrato antigo de destinatário continua legível.
        self.assertEqual(meta['evidence'], 'receipt-1')
        self.assertEqual(row[3:], ('turn-1', 'proc-1'))

    def test_local_day_utc_boundaries_and_origin_fields(self):
        self.add('2026-10-10T02:59:59.000+00:00', person={'id': 'a', 'nome': 'Alistair'},
                 metadata={'source_id': 'envelope-1', 'confidence': 0.0}, turn_id='turn-a', session_id='diag-a')
        self.add('2026-10-10T03:00:00.000+00:00', content='Dia seguinte')
        out = history.daily_records('2026-10-09', include_events=False)
        self.assertEqual(len(out['items']), 1)
        row = out['items'][0]
        self.assertEqual((row['person_id'], row['author'], row['turn_id'], row['session_id']), ('a', 'Alistair', 'turn-a', 'diag-a'))
        self.assertEqual(row['metadata']['confidence'], 0.0)
        self.assertEqual(row['metadata']['source_id'], 'envelope-1')
        self.assertTrue(row['timestamp']['timezone_known'])
        self.assertEqual(len(history.daily_records('2026-10-10')['items']), 1)
        self.assertFalse(out['global_causal_order'])

    def test_legacy_rows_are_read_without_rewrite_or_fabricated_utc(self):
        self.add('2026-10-09T23:59:59.000', person={'nome': 'Gustavo'})
        before = history.DB.read_bytes()
        out = history.daily_records('2026-10-09')
        self.assertEqual(history.DB.read_bytes(), before)
        row = out['items'][0]
        self.assertEqual(row['ts'], '2026-10-09T23:59:59.000')
        self.assertFalse(row['timestamp']['timezone_known'])
        self.assertIsNone(row['timestamp']['utc'])
        self.assertTrue(out['legacy_timezone_unknown'])

    def test_day_filters_do_not_mix_people_channels_or_targets(self):
        stamp = '2026-10-09T15:00:00+00:00'
        for canal, target, pid in [('discord', 'one', 'a'), ('discord', 'two', 'a'), ('tui', 'one', 'a'), ('discord', 'one', 'b')]:
            self.add(stamp, channel=canal, channel_target=target, person={'id': pid, 'nome': pid}, content='Lua azul')
        out = history.daily_records('2026-10-09', channel='discord', channel_target='one', person_id='a', query='azul')
        self.assertEqual(len(out['items']), 1)
        self.assertEqual(out['items'][0]['channel_target'], 'one')
        self.assertEqual(history.daily_records('2026-10-09', query='inexistente')['items'], [])

    def test_pagination_and_event_correlation_survive_reopen(self):
        for i in range(3):
            self.add(f'2026-10-09T15:00:0{i}+00:00', content=f'Mensagem {i}')
        with patch.object(history, 'utc_timestamp', return_value='2026-10-09T15:00:04+00:00'):
            eid = history.event('tool.receipt', data={'request_id': 'rpc-1'}, turn_id='turn-rpc')
        history._INITIALIZED_DB = None
        first = history.daily_records('2026-10-09', limit=2)
        second = history.daily_records('2026-10-09', limit=2, offset=first['next_offset'])
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual(second['items'][-1]['id'], eid)
        self.assertEqual(second['items'][-1]['data']['request_id'], 'rpc-1')
        self.assertEqual(second['items'][-1]['turn_id'], 'turn-rpc')

    def test_timeline_can_search_across_days_and_select_events_only(self):
        self.add('2026-10-08T15:00:00Z', content='Conteúdo copiado do clipboard: lua azul')
        eid = history.event('tool.receipt', 'lua azul', severity='ERROR',
                            timestamp='2026-10-09T15:00:00Z')
        history.event('tool.receipt', 'lua azul', timestamp='2026-10-09T16:00:00Z')
        first = history.daily_records(None, query='LUA AZUL', limit=1, newest_first=True)
        self.assertTrue(first['has_more'])
        self.assertEqual(first['items'][0]['severity'], 'INFO')
        errors = history.daily_records(None, include_messages=False, severity='ERROR')
        self.assertEqual([row['id'] for row in errors['items']], [eid])
        messages = history.daily_records(None, query='clipboard', include_events=False)
        self.assertIn('lua azul', messages['items'][0]['content'])

    def test_entity_database_inspection_is_read_only_and_does_not_create_missing_db(self):
        self.add('2026-10-09T12:00:00Z')
        another = self.base / 'missing.sqlite3'
        self.assertTrue(history.daily_records('2026-10-09', db_path=another, entity='hoshino')['missing'])
        self.assertFalse(another.exists())
        out = history.daily_records('2026-10-09', db_path=history.DB, entity='lilith')
        self.assertTrue(out['read_only'])
        self.assertEqual(out['entity'], 'lilith')

    def test_invalid_date_limits_timezone_are_rejected(self):
        for invalid in ('hoje', '2026-02-30', '20261009', '2026-10-09 OR 1=1'):
            with self.assertRaises(ValueError):
                history.daily_records(invalid)
        for invalid in (0, -1, True, 501):
            with self.assertRaises(ValueError):
                history.daily_records('2026-10-09', limit=invalid)
        with patch.object(config, 'LOCAL_TIMEZONE', 'invalid/zone'):
            with self.assertRaises(ValueError):
                history.local_now()

    def test_existing_history_tool_can_retrieve_day_without_new_tool(self):
        self.add('2026-10-09T15:00:00Z', person={'nome': 'Alistair'}, content='A lua azul')
        self.add('2026-10-10T15:00:00Z', content='Outra lua')
        result = historico.buscar('lua', data='2026-10-09')
        self.assertIn('Alistair:', result)
        self.assertNotIn('Outra lua', result)

    def test_wall_time_tool_exposes_real_local_timezone(self):
        result = terminal.get_system_time()
        self.assertIn('America/Sao_Paulo', result)
        self.assertIn('UTC', result)

    def test_three_databases_do_not_share_authors_messages_or_ids(self):
        for entity in ('hoshino', 'lilith', 'alistair'):
            with patch.object(history, 'DB', self.base / (entity+'.sqlite3')), \
                 patch.object(config, 'ENTIDADE_ID', entity), patch.object(config, 'ENTIDADE_NOME', entity.capitalize()):
                self.add('2026-10-09T15:00:00Z', 'out', content='Eu sou '+entity)
        ids = set()
        for entity in ('hoshino', 'lilith', 'alistair'):
            out = history.daily_records('2026-10-09', db_path=self.base / (entity+'.sqlite3'), entity=entity)
            self.assertEqual(len(out['items']), 1)
            row = out['items'][0]
            self.assertEqual(row['author'], entity.capitalize())
            self.assertEqual(row['metadata']['author_id'], entity)
            self.assertNotIn(row['id'], ids)
            ids.add(row['id'])

    def test_metadata_cannot_relabel_explicit_speaker(self):
        self.add('2026-10-09T15:00:00Z', person={'id':'a','nome':'Alistair'},
                 metadata={'author_id':'gustavo','author_name':'Gustavo','source_id':'envelope-1'})
        row = history.daily_records('2026-10-09')['items'][0]
        self.assertEqual((row['metadata']['author_id'], row['metadata']['author_name']), ('a','Alistair'))
        self.assertEqual(row['metadata']['source_id'], 'envelope-1')

    def test_filters_without_date_are_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, 'data'):
            historico.buscar('lua', pessoa_id='another')
        with self.assertRaisesRegex(ValueError, 'data'):
            historico.recente(destino='another')

    def test_offset_timestamp_and_literal_percent_query_are_supported(self):
        self.add('2026-10-10T08:59:59+09:00', content='Ganhei 10% de tempo')
        self.add('2026-10-09T15:00:00Z', content='Sem percentual')
        out = history.daily_records('2026-10-09', query='10%')
        self.assertEqual(len(out['items']), 1)
        self.assertEqual(out['items'][0]['ts'], '2026-10-10T08:59:59+09:00')

    def test_invalid_timestamp_is_visible_as_unknown_not_confirmed_utc(self):
        info = history.timestamp_details('ontem')
        self.assertEqual(info['kind'], 'invalid')
        self.assertIsNone(info['local_date'])
        self.assertFalse(info['timezone_known'])
        self.assertIsNone(info['utc'])

    def test_elapsed_uses_offsets_and_legacy_local_assumption_not_host_timezone(self):
        end = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)
        for start in ('2026-10-09T11:00:00', '2026-10-09T14:00:00Z', '2026-10-09T23:00:00+09:00'):
            self.assertEqual(history.elapsed_seconds(start, end), 3600.)
        self.assertEqual(history.elapsed_seconds('2026-10-09T11:00:00', datetime(2026, 10, 9, 12)), 3600.)
        self.assertFalse(history.timestamp_details('2026-10-09T11:00:00')['timezone_known'])

    def test_clock_invalid_and_future_are_unknown_and_diagnosed_not_elapsed_success(self):
        from core import diagnostics
        end = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)
        with patch.object(diagnostics, 'emit') as emit:
            for start in ('inválido', '2026-10-10T15:00:00Z'):
                self.assertIsNone(history.elapsed_seconds(start, end, operation='test.clock'))
        self.assertEqual(emit.call_count, 2)
        self.assertEqual({c.kwargs['reason'] for c in emit.call_args_list}, {'invalid_timestamp', 'clock_regression'})
        self.assertTrue(all(c.args[0] == 'clock.unreliable' for c in emit.call_args_list))

    def test_missing_time_is_unknown_zero_is_valid_and_clock_warning_is_bounded(self):
        from core import diagnostics
        end = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)
        history._clock_warning.cache_clear()
        self.assertIsNone(history.elapsed_seconds(None, end))
        self.assertEqual(history.elapsed_seconds(end, end), 0.)
        with patch.object(diagnostics, 'emit') as emit:
            for _ in range(50):
                self.assertIsNone(history.elapsed_seconds('não registrar isto', end, operation='test.bounded_clock'))
        emit.assert_called_once()
        self.assertNotIn('não registrar isto', str(emit.call_args))

    def test_current_dispatcher_preserves_date_filters_and_rejects_invalid_limit(self):
        from core import dispatch
        self.add('2026-10-09T15:00:00Z', person={'id':'a','nome':'Alistair'}, content='Lua azul')
        args={'consulta':'Lua','data':'2026-10-09','pessoa_id':'a'}
        handler=dispatch.HANDLERS['buscar_historico_chat']
        self.assertIn('Alistair:', handler(args,{}))
        self.assertIn('message_id=', handler(args,{}))
        for limit in (0,-1,True,'20'):
            with self.assertRaises(ValueError):
                handler(args|{'limite':limit},{})

    def test_explicit_event_timestamp_is_normalized_to_utc_not_guessed(self):
        history.event('external.clock', timestamp='2026-10-10T08:59:59.001+09:00')
        with closing(sqlite3.connect(history.DB)) as db:
            ts=db.execute("SELECT ts FROM events WHERE kind='external.clock'").fetchone()[0]
        self.assertEqual(ts,'2026-10-09T23:59:59.001+00:00')
        for value in ('2026-10-09T10:00:00','ontem'):
            with self.assertRaises(ValueError):
                history.event('invalid.clock',timestamp=value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
