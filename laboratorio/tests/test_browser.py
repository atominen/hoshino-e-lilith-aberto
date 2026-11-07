"""Navegador com APIs simuladas; não substitui homologação física AMD."""
import os,subprocess,tempfile,unittest
from pathlib import Path

class LaboratoryBrowserTests(unittest.TestCase):
    def test_single_training_interface_has_resume_evaluation_and_guarded_night(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,TMPDIR=tmp,XDG_CONFIG_HOME=tmp,XDG_CACHE_HOME=tmp)
            result=subprocess.run(['node',str(root/'laboratorio/tests/browser.cjs'),str(root)],
                                   env=env,text=True,capture_output=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('"passed":true',result.stdout)
