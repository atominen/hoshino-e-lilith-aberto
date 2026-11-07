"""Testes determinísticos do ciclo de vida seguro do Ollama."""
from __future__ import annotations

import json
import os
import sys
import types
import unittest
import tempfile
import contextlib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import config  # noqa: E402


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class TestOllamaLifecycle(unittest.TestCase):
    def setUp(self):
        self._get = {}
        self._posts = []
        self._orig_model = config.MODEL_NAME
        self._orig_url = config.OLLAMA_URL
        self._orig_host = config.OLLAMA_HOST
        config.MODEL_NAME = "qwen3.5:9b"
        config.OLLAMA_HOST = "127.0.0.1:11435"
        config.OLLAMA_URL = "http://127.0.0.1:11435/api/chat"
        from core import ollama_lifecycle
        ollama_lifecycle._ATEEXIT_REGISTRADO = True
        ollama_lifecycle._ENCERRADO = False

    def tearDown(self):
        config.MODEL_NAME = self._orig_model
        config.OLLAMA_URL = self._orig_url
        config.OLLAMA_HOST = self._orig_host

    def test_inicializacao_ok_sem_restart(self):
        from core import ollama_lifecycle

        def fake_get(url, timeout=None):
            return _Resp({"models": [{"name": "qwen3.5:9b"}]})

        with patch.object(ollama_lifecycle.requests, "get", side_effect=fake_get) as get, \
             patch.object(ollama_lifecycle, "recuperar") as recover:
            status = ollama_lifecycle.inicializar()
        self.assertTrue(status.ok)
        self.assertFalse(status.recuperado)
        recover.assert_not_called()
        get.assert_called_once()

    def test_recuperacao_dedicada_nao_reinicia_servico_generico(self):
        from core import ollama_lifecycle

        import requests
        estados = iter([
            requests.exceptions.ConnectionError("Connection refused"),
            _Resp({"models": []}),
            _Resp({"models": [{"name": "qwen3.5:9b"}]}),
        ])

        def fake_get(url, timeout=None):
            item = next(estados)
            if isinstance(item, Exception):
                raise item
            return item

        with patch.object(ollama_lifecycle.requests, "get", side_effect=fake_get), \
             patch.object(ollama_lifecycle, "_servico_systemd_existe", return_value=True) as service, \
             patch.object(ollama_lifecycle, "_reiniciar_por_systemd") as restart, \
             patch.object(ollama_lifecycle, "_iniciar_instancia_propria", return_value="iniciada instância local de teste") as start, \
             patch.object(ollama_lifecycle.time, "sleep", return_value=None):
            status = ollama_lifecycle.recuperar()
        self.assertTrue(status.ok)
        self.assertTrue(status.recuperado)
        restart.assert_not_called()
        service.assert_not_called()
        start.assert_called_once()

    def test_lilith_tambem_nao_reinicia_servico_generico(self):
        from core import ollama_lifecycle as lifecycle
        import requests
        config.OLLAMA_HOST = "127.0.0.1:11436"
        config.OLLAMA_URL = "http://127.0.0.1:11436/api/chat"
        with patch.object(lifecycle.requests, "get", side_effect=requests.ConnectionError), \
             patch.object(lifecycle, "_reiniciar_por_systemd") as restart, \
             patch.object(lifecycle, "_iniciar_instancia_propria", return_value="porta ocupada; não iniciar") as start:
            self.assertFalse(lifecycle.recuperar().ok)
        restart.assert_not_called()
        start.assert_called_once()

    def test_alistair_recovery_never_restarts_generic_systemd(self):
        from core import ollama_lifecycle as lifecycle
        import requests
        config.OLLAMA_HOST = '127.0.0.1:11437'
        config.OLLAMA_URL = 'http://127.0.0.1:11437/api/chat'
        with patch.object(lifecycle.requests, 'get', side_effect=requests.ConnectionError), \
             patch.object(lifecycle, '_servico_systemd_existe') as service, \
             patch.object(lifecycle, '_reiniciar_por_systemd') as restart, \
             patch.object(lifecycle, '_iniciar_instancia_propria', return_value='porta ocupada'):
            self.assertFalse(lifecycle.recuperar().ok)
        service.assert_not_called()
        restart.assert_not_called()

    def test_modelo_ausente_nao_reinicia_nem_baixa(self):
        from core import ollama_lifecycle as lifecycle
        with patch.object(lifecycle.requests, "get", return_value=_Resp({"models": []})), \
             patch.object(lifecycle, "_reiniciar_por_systemd") as restart, \
             patch.object(lifecycle, "_iniciar_instancia_propria") as start:
            self.assertFalse(lifecycle.recuperar().ok)
        restart.assert_not_called()
        start.assert_not_called()

    def test_owned_amd_daemon_enables_vulkan_without_overriding_operator(self):
        from core import ollama_lifecycle as lifecycle, gpu_metrics
        for explicit, expected in ((None, '1'), ('0', '0')):
            with tempfile.TemporaryDirectory() as td, \
                 patch.dict(os.environ, {} if explicit is None else {'OLLAMA_VULKAN': explicit}, clear=True), \
                 patch.object(config, 'SHARED_RUNTIME_DIR', td), \
                 patch.object(lifecycle, '_modelos_dir', return_value=td+'/models'), \
                 patch.object(lifecycle.shutil, 'which', return_value='/test/ollama'), \
                 patch('socket.create_connection', side_effect=OSError), \
                 patch.object(gpu_metrics, 'snapshot', return_value={'known':True}), \
                 patch.object(lifecycle.subprocess, 'Popen') as start:
                lifecycle._iniciar_instancia_propria()
                self.assertEqual(start.call_args.kwargs['env']['OLLAMA_VULKAN'], expected)

    def test_alistair_dedicated_port_does_not_depend_on_other_daemons(self):
        from core import ollama_lifecycle as lifecycle, gpu_metrics
        config.OLLAMA_HOST = '127.0.0.1:11437'
        with tempfile.TemporaryDirectory() as td, \
             patch.dict(os.environ, {}, clear=True), \
             patch.object(config, 'SHARED_RUNTIME_DIR', td), \
             patch.object(lifecycle, '_modelos_dir', return_value=td+'/models'), \
             patch.object(lifecycle, '_processo_ollama_do_usuario', return_value=True), \
             patch.object(lifecycle.shutil, 'which', return_value='/test/ollama'), \
             patch('socket.create_connection', side_effect=OSError), \
             patch.object(gpu_metrics, 'snapshot', return_value={'known':False}), \
             patch.object(lifecycle.subprocess, 'Popen') as start:
            lifecycle._iniciar_instancia_propria()
            self.assertEqual(start.call_args.kwargs['env']['OLLAMA_HOST'], config.OLLAMA_HOST)
            self.assertNotIn('OLLAMA_VULKAN', start.call_args.kwargs['env'])

    def test_owned_daemon_receives_only_its_bounded_cache_share(self):
        from core import ollama_lifecycle as lifecycle, gpu_metrics, resource_manager as rm
        for entity, cap in (('hoshino', '3584'), ('lilith', '3584'), ('alistair', '1024')):
            with self.subTest(entity=entity), tempfile.TemporaryDirectory() as td, \
                 patch.dict(os.environ, {'LLAMA_ARG_CACHE_RAM':'-1'}, clear=True), \
                 patch.object(config, 'ENTIDADE_ID', entity), \
                 patch.object(config, 'RAIZ', Path(td)), \
                 patch.object(config, 'SHARED_RUNTIME_DIR', td), \
                 patch.object(lifecycle, '_modelos_dir', return_value=td+'/models'), \
                 patch.object(lifecycle.shutil, 'which', return_value='/test/ollama'), \
                 patch('socket.create_connection', side_effect=OSError), \
                 patch.object(gpu_metrics, 'snapshot', return_value={'known':False}), \
                 patch.object(gpu_metrics, 'ram_total', return_value=31*1024**3, create=True), \
                 patch.object(gpu_metrics, 'ram_available', return_value=22*1024**3), \
                 patch.object(lifecycle.subprocess, 'Popen') as start:
                lifecycle._iniciar_instancia_propria()
                env = start.call_args.kwargs['env']
                self.assertEqual(env.get('LLAMA_ARG_CACHE_RAM'), cap)
                self.assertEqual(env.get('OLLAMA_MAX_LOADED_MODELS'), '1')
                self.assertEqual(env.get('OLLAMA_NUM_PARALLEL'), '1')

    def test_occupied_port_does_not_reconfigure_or_restart_existing_cache(self):
        from core import ollama_lifecycle as lifecycle
        with patch('socket.create_connection') as socket, \
             patch.object(lifecycle.subprocess, 'Popen') as start:
            detail = lifecycle._iniciar_instancia_propria()
        self.assertIn('ocupada', detail)
        start.assert_not_called()

    def test_encerramento_descarrega_modelo_e_verifica(self):
        from core import ollama_lifecycle

        def fake_post(url, json=None, timeout=None):
            self._posts.append((url, json))
            return _Resp({"done": True, "done_reason": "unload"})

        estados_ps = iter([_Resp({"models": [{"name": "qwen3.5:9b"}]}), _Resp({"models": []})])

        with patch.object(ollama_lifecycle.requests, "post", side_effect=fake_post), \
             patch.object(ollama_lifecycle.requests, "get", side_effect=lambda *a, **k: next(estados_ps)), \
             patch.object(ollama_lifecycle.time, "sleep", return_value=None):
            ok = ollama_lifecycle.encerrar()
        self.assertTrue(ok)
        self.assertEqual(self._posts[0][1]["model"], "qwen3.5:9b")
        self.assertEqual(self._posts[0][1]["messages"], [])
        self.assertEqual(self._posts[0][1]["keep_alive"], 0)

    def test_encerramento_e_idempotente(self):
        from core import ollama_lifecycle
        with patch.object(ollama_lifecycle, "descarregar_modelo", return_value=(True, "unload")) as unload:
            self.assertTrue(ollama_lifecycle.encerrar())
            self.assertTrue(ollama_lifecycle.encerrar())
        unload.assert_called_once()

    def test_sleep_unloads_three_owned_executors_under_one_maintenance_lease(self):
        from core import ollama_lifecycle as lifecycle, resource_manager, gpu_resource
        catalog = [dict(model='qwen3.5:9b', tier='principal'),
                   dict(model='hoshino-qwen2.5-7b:latest', tier='light'),
                   dict(model='hoshino-companion:latest', tier='companion')]
        with patch.object(resource_manager, 'executor_catalog', return_value=catalog), \
             patch.object(resource_manager, 'local_model_installed', return_value=True), \
             patch.object(gpu_resource, 'lease', return_value=contextlib.nullcontext()) as lease, \
             patch.object(lifecycle, '_descarregar_modelo_sem_lease', return_value=(True, 'confirmado')) as unload:
            self.assertTrue(lifecycle.descarregar_modelo()[0])
        lease.assert_called_once_with('unload')
        self.assertEqual([c.kwargs.get('model') for c in unload.call_args_list],
                         [None, catalog[1]['model'], catalog[2]['model']])

    def test_sleep_does_not_report_unload_success_when_one_executor_fails(self):
        from core import ollama_lifecycle as lifecycle, resource_manager, gpu_resource
        catalog = [dict(model='qwen3.5:9b', tier='principal'),
                   dict(model='own7b', tier='light'), dict(model='own6b', tier='companion')]
        with patch.object(resource_manager, 'executor_catalog', return_value=catalog), \
             patch.object(resource_manager, 'local_model_installed', return_value=True), \
             patch.object(gpu_resource, 'lease', return_value=contextlib.nullcontext()), \
             patch.object(lifecycle, '_descarregar_modelo_sem_lease',
                          side_effect=[(True, 'principal confirmado'), (False, 'leve continua residente')]) as unload:
            ok, detail = lifecycle.descarregar_modelo()
        self.assertFalse(ok)
        self.assertIn('leve continua residente', detail)
        self.assertEqual(unload.call_count, 2)


class TestMainRuntimeRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_chamar_modelo_recupera_uma_vez_apos_connection_error(self):
        import types
        import requests

        # Dependências visuais/opcionais mínimas para importar main.py sem instalar
        # o stack completo no ambiente de testes.
        class _W:
            def write(self, *a, **k): pass
            def focus(self, *a, **k): pass

        class _App:
            def __init__(self, *a, **k): pass
            def set_interval(self, *a, **k): pass
            def run(self, *a, **k): pass

        def mod(name, **attrs):
            m = types.ModuleType(name)
            for k, v in attrs.items(): setattr(m, k, v)
            sys.modules[name] = m

        mod("textual")
        mod("textual.app", App=_App, ComposeResult=object)
        mod("textual.binding", Binding=lambda *a, **k: None)
        mod("textual.containers", Horizontal=_W, Vertical=_W)
        mod("textual.widgets", Header=_W, Footer=_W, RichLog=_W, TextArea=_W)
        mod("mss")
        mod("pygame")
        mod("edge_tts")

        # Importa main depois dos stubs; se já estivesse em cache, a implementação
        # continuaria sendo a mesma, apenas o teste seria menos isolado.
        import main
        from core import ollama_lifecycle
        import asyncio

        app = main.InterfaceHoshino.__new__(main.InterfaceHoshino)
        app.trava = asyncio.Lock()
        app.trava_modelo = asyncio.Lock()
        respostas = [
            requests.exceptions.ConnectionError("Connection refused"),
            _Resp({"done": True,"done_reason":"stop","message": {"role": "assistant", "content": "ok depois da recuperação"}}),
        ]

        status = ollama_lifecycle.OllamaStatus(
            True, config.OLLAMA_URL, config.MODEL_NAME, True, "recuperado", True)

        with patch.object(config, "STREAM_LLM", False), \
             patch.object(app, "_post_ollama_json_com_lease", side_effect=respostas) as transport, \
             patch.object(ollama_lifecycle, "recuperar", return_value=status) as recover:
            msg = await app.chamar_modelo([{"role": "user", "content": "oi"}])

        self.assertEqual(msg["content"], "ok depois da recuperação")
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(transport.call_args_list[0].args[0]["model"], transport.call_args_list[1].args[0]["model"])
        recover.assert_called_once()

    async def test_segunda_queda_nao_cria_loop_de_recuperacao(self):
        import main
        import requests
        from core import ollama_lifecycle as lifecycle
        app = main.InterfaceHoshino.__new__(main.InterfaceHoshino)
        status = lifecycle.OllamaStatus(True, config.OLLAMA_URL, config.MODEL_NAME, True, "mock", True)
        with patch.object(config, "STREAM_LLM", False), \
             patch.object(app, "_post_ollama_json_com_lease", side_effect=requests.ConnectionError) as transport, \
             patch.object(lifecycle, "recuperar", return_value=status) as recover:
            with self.assertRaises(requests.ConnectionError):
                await app.chamar_modelo([{"role": "user", "content": "oi"}])
        self.assertEqual(transport.call_count, 2)
        recover.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
