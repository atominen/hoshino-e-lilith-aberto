"""Regressões das guardas do runner, sem tocar serviço/hardware/banco real."""
import os
import socket
import sqlite3
import subprocess
import tempfile
import unittest
import sys
import runpy
from pathlib import Path

from catalogo import ROOT, GRUPOS, automaticos, categoria, validar


class SuiteTests(unittest.TestCase):
    def test_runner_includes_project_root_for_laboratory_imports(self):
        script=(ROOT/'rodar_testes.sh').read_text()
        exports=[line for line in script.splitlines() if line.startswith('export PYTHONPATH=')]
        self.assertEqual(len(exports),1)
        self.assertIn('$APP_DIR:$ROOT',exports[0])

    def test_memory_source_can_be_versioned_but_mental_databases_remain_ignored(self):
        for path in ('app/memory/cognitive_notes.py','app/memory/knowledge_store.py','app/memory/records.py',
                     'app/memory/sqlite/init_db.py','app/memory/vector/chroma_store.py'):
            out=subprocess.run(['git','check-ignore','--quiet','--no-index',path],cwd=ROOT)
            self.assertEqual(out.returncode,1,path)
        for path in ('entidades/hoshino/memory/sqlite/hoshino.db','app/memory/private-data.json',
                     'app/memory/vector/private-index.bin','entidades/lilith/config/lilith.env'):
            out=subprocess.run(['git','check-ignore','--quiet','--no-index',path],cwd=ROOT)
            self.assertEqual(out.returncode,0,path)
    def test_destructive_historical_group_refuses_direct_production_invocation(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'testes/test_integridade_memoria.py')],
            cwd=str(ROOT),env={'PATH':os.environ['PATH'],'PYTHONPATH':str(ROOT/'app')},capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertIn('Use testes/executar_isolado.py',result.stderr)

    def test_alistair_and_legacy_readiness_groups_require_isolated_runner(self):
        for name in ('test_prontidao_r1_r7','test_alistair_imagem','test_alistair_continuidade'):
            with self.subTest(group=name):
                result=subprocess.run([sys.executable,'-B',str(ROOT/'testes'/f'{name}.py')],cwd=ROOT,
                    env={'PATH':os.environ['PATH'],'PYTHONPATH':str(ROOT/'app')},capture_output=True,text=True,timeout=10)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Use testes/executar_isolado.py',result.stderr)
    def test_inventario_completo_sem_duplicatas(self):
        validar()
        self.assertEqual(len(automaticos()), sum(len(GRUPOS[t]) for t in ('unitario', 'regressao', 'integracao_offline')))

    def test_manual_nunca_entra_na_ci(self):
        self.assertEqual(categoria('test_microfone_continuo_v33'), 'hardware_manual')
        self.assertNotIn('test_microfone_continuo_v33', automaticos())
        with self.assertRaises(ValueError):
            automaticos('hardware_manual')

    def test_descoberta_manual_nao_inicializa_asr_e_execucao_offline_e_recusada(self):
        namespace = runpy.run_path(str(ROOT/'testes/test_microfone_continuo_v33.py'), run_name='inspecao_manual')
        self.assertNotIn('Transcritor', namespace)
        self.assertNotIn('t', namespace)
        with self.assertRaisesRegex(SystemExit, 'manual de hardware proibido'):
            namespace['main']()

    def test_rede_externa_bloqueada_antes_de_conectar(self):
        with socket.socket() as sock, self.assertRaises(PermissionError):
            sock.connect(('192.0.2.1', 443))

    def test_daemon_real_bloqueado_antes_de_conectar(self):
        with socket.socket() as sock, self.assertRaises(PermissionError):
            sock.connect(('127.0.0.1', 11435))

    def test_porta_fixa_nao_e_fixture(self):
        with socket.socket() as sock, self.assertRaises(PermissionError):
            sock.bind(('127.0.0.1', 11436))

    def test_fixture_loopback_efemera_funciona(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            with socket.create_connection(server.getsockname(), timeout=1) as client:
                conn, _ = server.accept()
                with conn:
                    client.sendall(b'fixture')
                    self.assertEqual(conn.recv(7), b'fixture')

    def test_banco_real_nao_e_aberto(self):
        with self.assertRaises(PermissionError):
            sqlite3.connect(str(ROOT / 'entidades/hoshino/memory/sqlite/hoshino.db'))

    def test_banco_temporario_funciona(self):
        with tempfile.TemporaryDirectory() as tmp:
            with sqlite3.connect(str(Path(tmp)/'teste.db')) as conn:
                conn.execute('CREATE TABLE exemplo (valor INTEGER)')
                conn.execute('INSERT INTO exemplo VALUES (0)')
                self.assertEqual(conn.execute('SELECT valor FROM exemplo').fetchone()[0], 0)
            with sqlite3.connect((Path(tmp)/'teste.db').as_uri()+'?mode=ro', uri=True) as conn:
                self.assertEqual(conn.execute('SELECT valor FROM exemplo').fetchone()[0], 0)

    def test_escrita_fora_do_temporario_bloqueada(self):
        with self.assertRaises(PermissionError):
            (ROOT / 'testes/NAO_CRIAR_ISOLAMENTO.txt').write_text('não escrever')
        self.assertFalse((ROOT / 'testes/NAO_CRIAR_ISOLAMENTO.txt').exists())

    def test_restart_real_bloqueado(self):
        with self.assertRaises(PermissionError):
            subprocess.run(['systemctl', '--user', 'restart', 'ollama'], check=True)

    def test_link_relativo_de_fixture_funciona(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'original').write_text('fixture')
            (path/'link').symlink_to('original')
            self.assertEqual((path/'link').read_text(), 'fixture')

    def test_link_para_projeto_real_bloqueado(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(PermissionError):
            (Path(tmp)/'link').symlink_to(ROOT/'README.md')

    def test_unlink_relativo_a_descritor_temporario(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fixture'
            path.write_text('fixture')
            fd = os.open(tmp, os.O_RDONLY)
            try:
                os.unlink('fixture', dir_fd=fd)
                self.assertFalse(path.exists())
            finally:
                os.close(fd)

    def test_limpeza_venv_temporario_nao_remove_python_base(self):
        executable = Path(sys.executable).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(Path(tmp)/'venv')], check=True)
        self.assertTrue(executable.is_file())

    def test_microfone_real_bloqueado(self):
        import sounddevice
        with self.assertRaises(PermissionError):
            sounddevice.InputStream()
        self.assertNotIn('DISPLAY', os.environ)
        self.assertNotIn('WAYLAND_DISPLAY', os.environ)
        self.assertIsNone(sys.modules['pyautogui'])


if __name__ == '__main__':
    if os.environ.get('HOSHINO_TEST_OFFLINE') != '1':
        raise SystemExit('Execute pelo runner isolado; este arquivo testa suas guardas.')
    unittest.main(verbosity=2)
