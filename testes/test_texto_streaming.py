"""Prévia pública de conversa; bancos temporários, sem modelos ou serviços reais."""
import importlib
import importlib.util
import contextlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from core import interentity as bus, job_bus


class TextStreamTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='text-stream-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for module in (bus, job_bus):
            p = patch.object(module, 'DB_PATH', self.root / (module.__name__ + '.db'))
            p.start(); self.addCleanup(p.stop)
        self.assertIsNotNone(importlib.util.find_spec('core.text_stream'), 'Prévia contínua ainda não implementada')
        self.mod = importlib.import_module('core.text_stream')
        self.now = 10.0
        p = patch.object(self.mod, 'monotonic', lambda: self.now)
        p.start(); self.addCleanup(p.stop)

    def stream(self, entity='hoshino', *, scope='direct', validator=None, cancelled=None):
        message = bus.send('usuario', entity, 'Olá', wake=False, chat_scope=scope)
        token = bus.processing_message.set(message)
        try:
            return self.mod.TextStream(entity, 'localhub', validator=validator or (lambda _: True),
                                       cancelled=cancelled or (lambda: False), request_id='fixture-request')
        finally:
            bus.processing_message.reset(token)

    def view(self, entity='hoshino', scope='direct'):
        return self.mod.snapshot(entity, bus.daily_session(entity)['id'], scope)['streams']

    def test_prefix_is_available_before_sentence_and_completion(self):
        stream = self.stream(); stream.push('Olá, estou')
        row = job_bus.get(stream.id, 'hoshino')
        self.assertEqual(row['status'], 'running')
        self.assertEqual(row['details']['text'], 'Olá, estou')
        self.assertFalse(row['details']['final'])
        self.assertEqual(self.view()[0]['text'], 'Olá, estou')

    def test_updates_are_coalesced_and_finish_flushes_without_committing(self):
        stream = self.stream(); stream.push('O')
        first = job_bus.get(stream.id)['details']['revision']
        self.now += .01; stream.push('Olá')
        self.assertEqual(job_bus.get(stream.id)['details']['revision'], first)
        self.now += .11; stream.push('Olá, mundo')
        self.assertGreater(job_bus.get(stream.id)['details']['revision'], first)
        stream.finish('Olá, mundo!')
        self.assertEqual(job_bus.get(stream.id)['status'], 'running')
        self.assertEqual(self.view()[0]['text'], 'Olá, mundo!')

    def test_physical_final_receipt_is_required_and_terminal_never_reopens(self):
        stream = self.stream(); stream.finish('Resposta final.')
        with self.assertRaises(ValueError): stream.commit('invented-message')
        parent = dict(id=stream.envelope['message_id'])
        token = bus.processing_message.set(parent)
        try:
            final = bus.send('hoshino', 'usuario', 'Resposta final.', metadata={'text_streams': [stream.id]})
        finally: bus.processing_message.reset(token)
        stream.commit(final['id'])
        self.assertEqual(job_bus.get(stream.id)['status'], 'done')
        stream.push('Outra resposta')
        stream.stop('cleanup')
        self.assertEqual(job_bus.get(stream.id)['status'], 'done')
        self.assertEqual(job_bus.get(stream.id)['details']['final_message_id'], final['id'])

    def test_missing_or_forged_source_is_rejected(self):
        for message in (None, {'id': 'invented'}, bus.send('usuario', 'lilith', 'Oi', wake=False)):
            token = bus.processing_message.set(message)
            try:
                with self.assertRaises(ValueError):
                    self.mod.TextStream('hoshino', 'localhub', validator=lambda _: True, cancelled=lambda: False)
            finally: bus.processing_message.reset(token)

    def test_only_public_response_channels_of_hoshino_and_lilith_are_eligible(self):
        message = bus.send('usuario', 'hoshino', 'Oi', wake=False)
        token = bus.processing_message.set(message)
        try:
            for entity, channel in (('alistair', 'localhub'), ('hoshino', 'discord')):
                with self.assertRaises(ValueError):
                    self.mod.TextStream(entity, channel, validator=lambda _: True, cancelled=lambda: False)
        finally: bus.processing_message.reset(token)

    def test_split_internal_markers_never_publish_private_text(self):
        for text in ('<think>SEGREDO', '< analysis>SEGREDO', '[CICLO INTERNO] SEGREDO', '[SISTEMA] SEGREDO'):
            stream = self.stream()
            for index in range(1, len(text) + 1):
                self.now += .12; stream.push(text[:index])
                row = job_bus.get(stream.id)
                self.assertNotIn('SEGREDO', str(row))
                if row: self.assertNotIn(text[:index], row['details'].get('text', '') or '')
            self.assertTrue(stream.stopped)
            self.assertFalse((job_bus.get(stream.id) or {}).get('details', {}).get('text'))

    def test_private_marker_after_public_prefix_invalidates_preview(self):
        stream = self.stream(); stream.push('Oi. ')
        stream.push('Oi. <think>SEGREDO')
        row = job_bus.get(stream.id)
        self.assertEqual(row['status'], 'interrupted')
        self.assertEqual(row['details']['text'], '')
        self.assertNotIn('SEGREDO', str(row))

    def test_verification_gate_rejects_unsafe_prefix(self):
        stream = self.stream(validator=lambda text: 'concluí' not in text)
        stream.push('Já concluí o trabalho')
        self.assertTrue(stream.stopped)
        self.assertFalse(self.view())

    def test_prefix_rewrite_is_interrupted_without_retry(self):
        stream = self.stream(); stream.push('Resposta original')
        stream.push('Resposta diferente')
        row = job_bus.get(stream.id)
        self.assertEqual(row['status'], 'interrupted')
        self.assertFalse(row['details']['auto_retry'])

    def test_cancellation_prevents_later_content(self):
        cancel = [False]; stream = self.stream(cancelled=lambda: cancel[0])
        stream.push('Primeiro'); cancel[0] = True
        self.now += .2; stream.push('Primeiro, outro trecho')
        row = job_bus.get(stream.id)
        self.assertEqual(row['status'], 'interrupted')
        self.assertEqual(row['details']['text'], 'Primeiro')

    def test_discard_after_interruption_clears_obsolete_preview(self):
        stream = self.stream(); stream.push('Tentativa anterior')
        stream.stop('generation_failed')
        self.assertEqual(self.view()[0]['text'], 'Tentativa anterior')
        stream.stop('response_replaced', discard_text=True)
        self.assertFalse(self.view())
        self.assertFalse(job_bus.get(stream.id)['details']['text'])

    def test_cancellation_during_first_prefix_cannot_leave_running_job(self):
        entered, release = threading.Event(), threading.Event()
        def validator(_):
            entered.set(); release.wait(3); return True
        stream = self.stream(validator=validator)
        producer = threading.Thread(target=stream.push, args=('Trecho cancelado',))
        producer.start(); stopper = None
        try:
            self.assertTrue(entered.wait(1))
            stopper = threading.Thread(target=stream.stop, args=('user_interruption',))
            stopper.start(); stopper.join(.5)
            self.assertFalse(stopper.is_alive(), 'Cancelamento não deve esperar a validação do texto')
        finally:
            release.set(); producer.join(2)
            if stopper is not None: stopper.join(2)
        row = job_bus.get(stream.id)
        self.assertFalse(row and row['status'] == 'running')
        self.assertFalse(self.view())

    def test_overlong_content_stops_before_database_growth(self):
        stream = self.stream(); stream.push('a' * 12001)
        self.assertTrue(stream.stopped)
        self.assertFalse(self.view())

    def test_scopes_and_sessions_are_not_interchangeable(self):
        direct = self.stream(); direct.push('DIRECT_SENTINEL')
        public = self.stream('lilith', scope='global'); public.push('PUBLIC_SENTINEL')
        self.assertEqual([s['text'] for s in self.view()], ['DIRECT_SENTINEL'])
        self.assertEqual([s['text'] for s in self.view('lilith', 'global')], ['PUBLIC_SENTINEL'])
        self.assertEqual([s['text'] for s in self.view('hoshino', 'global')], ['PUBLIC_SENTINEL'])
        self.assertFalse(self.view('lilith'))
        with self.assertRaises(ValueError): self.mod.snapshot('hoshino', bus.daily_session('lilith')['id'], 'direct')
        with self.assertRaises(ValueError): self.mod.snapshot('hoshino', '', 'wrong')

    def test_global_room_includes_both_producers_with_distinct_sessions(self):
        h = self.stream(scope='global'); h.push('Hoshino')
        l = self.stream('lilith', scope='global'); l.push('Lilith')
        self.assertNotEqual(h.envelope['conversation_session_id'], l.envelope['conversation_session_id'])
        self.assertEqual({s['text'] for s in self.view('alistair', 'global')}, {'Hoshino', 'Lilith'})

    def test_job_type_filter_happens_before_limit(self):
        stream = self.stream(); stream.push('Não sumir por fila ocupada')
        for i in range(205): job_bus.publish('noise-' + str(i), 'lilith', 'done', kind='fixture')
        self.assertEqual(self.view()[0]['id'], stream.id)

    def test_snapshot_never_projects_other_day_or_sensitive_extra_fields(self):
        stream = self.stream(scope='global'); stream.push('Texto público')
        job_bus.annotate(stream.id, 'hoshino', thinking='THINKING_SENTINEL', prompts='PROMPT_SENTINEL')
        view = self.view('lilith', 'global')
        self.assertNotIn('SENTINEL', str(view))
        job_bus.annotate(stream.id, 'hoshino', room_day='2000-01-01')
        self.assertFalse(self.view('lilith', 'global'))


class TurnIntegrationTests(unittest.TestCase):
    setUp = TextStreamTests.setUp
    stream = TextStreamTests.stream
    view = TextStreamTests.view

    @contextlib.contextmanager
    def turn(self):
        from main import InterfaceHoshino
        from core import speech_stream, gpu_resource
        import config
        message = bus.send('usuario', 'hoshino', 'Olá', wake=False)
        parent = bus.processing_message.set(message)
        context = dict(channel='localhub', streams=[], cancelled=lambda: False, validator=lambda _: True)
        scope = speech_stream.context.set(context)
        app = InterfaceHoshino.__new__(InterfaceHoshino)
        app.chat_log = Mock(); app.pessoa = {}; app.ultima_entrada = 'Olá'
        app._interentity_inflight = {message['id']}
        try:
            with patch.object(config, 'ENTIDADE_ID', 'hoshino'), patch.object(config, 'VOZ_ATIVA', False), \
                 patch.object(gpu_resource, 'lease', return_value=contextlib.nullcontext({'backend': 'cpu'})), \
                 patch('main.history.message'), patch.object(app, '_historico_da_conversa', return_value=[]):
                yield app, context
        finally:
            bus.processing_message.reset(parent); speech_stream.context.reset(scope)

    def test_actual_transport_publishes_before_done_without_voice(self):
        response = Mock()
        def frames():
            yield json.dumps(dict(message={'thinking': 'PRIVATE_THOUGHT'}))
            yield json.dumps(dict(message={'content': 'Olá, estou'}))
            self.assertEqual(self.view()[0]['text'], 'Olá, estou')
            self.assertEqual(self.view()[0]['status'], 'running')
            yield json.dumps(dict(message={'content': ' aqui!'}, done=True))
        response.iter_lines.side_effect = lambda **_: frames()
        with self.turn() as (app, context), patch('main.requests.post', return_value=response):
            result = app._post_ollama_stream_com_lease({'model': 'mock'}, 'fixture')
            self.assertEqual(result['content'], 'Olá, estou aqui!')
            self.assertNotIn('PRIVATE_THOUGHT', str(self.view()))
            self.assertEqual(len(context['text_streams']), 1)
            self.assertEqual(self.view()[0]['status'], 'running')

    def test_tool_call_invalidates_previously_visible_content(self):
        frames = [dict(message={'content': 'Um instante'}), dict(message={'tool_calls': [
            {'function': {'name': 'fixture_tool', 'arguments': {'secret': 'TOOL_SENTINEL'}}}]}, done=True)]
        response = Mock(iter_lines=Mock(return_value=[json.dumps(f) for f in frames]))
        with self.turn() as (app, context), patch('main.requests.post', return_value=response):
            app._post_ollama_stream_com_lease({'model': 'mock'}, 'fixture')
            self.assertFalse(self.view())
            self.assertTrue(context['text_streams'][0].stopped)
            self.assertNotIn('TOOL_SENTINEL', str(job_bus.status(kind='llm_text')))

    def test_incomplete_transport_is_not_published_as_completed(self):
        response = Mock(iter_lines=Mock(return_value=[json.dumps(dict(message={'content': 'Parcial'}))]))
        with self.turn() as (app, _), patch('main.requests.post', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'EOF'):
                app._post_ollama_stream_com_lease({'model': 'mock'}, 'fixture')
        self.assertEqual(self.view()[0]['status'], 'interrupted')

    def test_final_envelope_commits_and_names_preview(self):
        with self.turn() as (app, _):
            stream = self.mod.TextStream('hoshino', 'localhub', validator=lambda _: True, cancelled=lambda: False)
            stream.finish('Resposta final.')
            app.publicar('Resposta final.', [], False, {}, 'usuario', canal='localhub',
                         entrada_usuario='Olá', fala_incerta=True, text_streams=[stream])
            row = job_bus.get(stream.id)
            self.assertEqual(row['status'], 'done')
            final = bus.user_conversation('hoshino')[-1]
            self.assertIn(stream.id, json.loads(final['metadata'])['text_streams'])
            self.assertEqual(row['details']['final_message_id'], final['id'])

    def test_changed_final_keeps_receipt_link_but_discards_wrong_preview(self):
        with self.turn() as (app, _):
            stream = self.mod.TextStream('hoshino', 'localhub', validator=lambda _: True, cancelled=lambda: False)
            stream.finish('Texto inicial.')
            app.publicar('Texto corrigido.', [], False, {}, 'usuario', canal='localhub',
                         entrada_usuario='Olá', fala_incerta=True, text_streams=[stream])
            self.assertFalse(self.view())
            final = bus.user_conversation('hoshino')[-1]
            self.assertEqual(final['text'], 'Texto corrigido.')
            self.assertIn(stream.id, json.loads(final['metadata'])['text_streams'])

    def test_failed_final_delivery_interrupts_preview(self):
        with self.turn() as (app, _):
            stream = self.mod.TextStream('hoshino', 'localhub', validator=lambda _: True, cancelled=lambda: False)
            stream.finish('Resposta final.')
            with patch.object(bus, 'send', side_effect=OSError('fixture disk full')):
                with self.assertRaises(OSError):
                    app.publicar('Resposta final.', [], False, {}, 'usuario', canal='localhub',
                                 entrada_usuario='Olá', fala_incerta=True, text_streams=[stream])
            self.assertEqual(job_bus.get(stream.id)['status'], 'interrupted')
            self.assertFalse(job_bus.get(stream.id)['details']['final'])


class StreamHttpTests(unittest.TestCase):
    stream = TextStreamTests.stream

    def setUp(self):
        import test_central_control as fixture
        fixture.CentralControlTests.setUp(self)
        self.mod = importlib.import_module('core.text_stream')
        self.server, self.token = fixture.launcher.make_server(self.supervisor, 0, self.audio)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True); thread.start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)

    def request(self, path, *, auth=True, expected=200):
        headers = {'Authorization': 'Bearer ' + self.token} if auth else {}
        req = Request(f'http://127.0.0.1:{self.server.server_port}/api/' + path, headers=headers)
        try:
            with urlopen(req, timeout=5) as response:
                self.assertEqual(response.status, expected); return json.load(response)
        except HTTPError as exc:
            self.assertEqual(exc.code, expected); return json.load(exc)

    def test_compact_endpoint_is_authenticated_scoped_and_never_wakes(self):
        stream = self.stream(); stream.push('DIRECT_HTTP_SENTINEL')
        session = bus.daily_session('hoshino')['id']
        route = 'chat/streams?entity=hoshino&chat_scope=direct&conversation_session_id=' + session
        self.request(route, auth=False, expected=403)
        self.assertEqual(self.request(route)['streams'][0]['text'], 'DIRECT_HTTP_SENTINEL')
        self.assertFalse(self.request(route.replace('scope=direct', 'scope=global'))['streams'])
        self.request(route.replace('entity=hoshino', 'entity=lilith'), expected=400)
        self.request(route.replace('scope=direct', 'scope=unknown'), expected=400)
        self.assertFalse(bus.pending_wake_requests())

    def test_generic_state_does_not_export_unscoped_preview_text(self):
        stream = self.stream(); stream.push('UNSCOPED_SENTINEL')
        state = self.request('state?entity=lilith&daily=1&chat_scope=global')
        self.assertNotIn('UNSCOPED_SENTINEL', str(state['jobs']))


class PreviewProjectionTests(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app/ui'))
        self.assertIsNotNone(importlib.util.find_spec('native_chat_stream'), 'Mesclagem de prévias ainda ausente')
        self.ui = importlib.import_module('native_chat_stream')
        self.session = dict(id='session-h', local_date='2026-10-24')
        self.preview = dict(id='text-fixture', entity='hoshino', status='running', text='Olá', revision=1,
                            chat_scope='direct', conversation_session_id='session-h', room_day='2026-10-24')

    def merge(self, streams, conversation=None, **options):
        params = dict(entity='hoshino', session=self.session, scope='direct') | options
        return self.ui.merge_previews(conversation or [], streams, **params)

    def test_same_stream_is_one_message_with_latest_revision(self):
        rows = self.merge([self.preview, self.preview | dict(text='Olá mundo', revision=2), self.preview])
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['text'], 'Olá mundo')
        self.assertIn('gerando', rows[0]['metadata']['processing']['status'])
        self.assertNotIn('feedback_target', rows[0])

    def test_physical_final_replaces_preview_even_if_text_changed(self):
        final = dict(id='final-1', sender='hoshino', recipient='usuario', text='Resposta corrigida',
                     metadata={'text_streams': ['text-fixture']}, kind='chat')
        self.assertEqual(self.merge([self.preview], [final]), [final])

    def test_failure_is_marked_incomplete_not_successful(self):
        for status in ('error', 'interrupted'):
            rows = self.merge([self.preview | dict(status=status)])
            self.assertEqual(len(rows), 1)
            self.assertIn('incompleta', rows[0]['metadata']['processing']['status'])
        self.assertFalse(self.merge([self.preview | dict(text='')]))

    def test_archives_filters_and_other_direct_audiences_cannot_gain_preview(self):
        for option in (dict(read_only=True), dict(query='olá'), dict(before=12), dict(entity='lilith'),
                       dict(session=dict(id='other', local_date='2026-10-24')), dict(scope='global')):
            self.assertFalse(self.merge([self.preview], **option))

    def test_global_uses_room_day_not_selected_entity_session(self):
        h = self.preview | dict(chat_scope='global')
        l = h | dict(id='text-l', entity='lilith', conversation_session_id='session-l', text='Lilith')
        self.assertEqual({m['sender'] for m in self.merge([h, l], scope='global')}, {'hoshino', 'lilith'})
        self.assertFalse(self.merge([h | dict(room_day='2026-10-23')], scope='global'))


if __name__ == '__main__': unittest.main()
