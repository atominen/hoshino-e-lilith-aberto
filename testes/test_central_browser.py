"""Contrato de navegador com transporte simulado; sem hardware/providers reais."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class BrowserTests(unittest.TestCase):
    def test_real_browser_mock_transport_navigation_controls_and_redaction(self):
        module=Path(os.environ.get('HOSHINO_UI_PLAYWRIGHT_MODULE','/home/gustavo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'))
        self.assertTrue(module.is_dir(),'Playwright local necessário; não baixar automaticamente.')
        with tempfile.TemporaryDirectory() as tmp:
            env={'PATH':os.environ['PATH'],'TMPDIR':tmp,'LANG':'C.UTF-8','XDG_CONFIG_HOME':tmp,'XDG_CACHE_HOME':tmp,
                 'PLAYWRIGHT_BROWSERS_PATH':'/home/gustavo/.cache/ms-playwright'}
            if os.environ.get('HOSHINO_UI_CHROMIUM_PATH'):
                env['HOSHINO_UI_CHROMIUM_PATH']=os.environ['HOSHINO_UI_CHROMIUM_PATH']
            result=subprocess.run(['node',str(ROOT/'testes/central_browser.cjs'),str(ROOT),str(module)],
                                  env=env,text=True,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('"passed":15',result.stdout)


if __name__=='__main__':unittest.main()
