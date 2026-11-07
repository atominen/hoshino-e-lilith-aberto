"""R6: callbacks reais da bridge, dependências e transportes em VM isolada."""
import subprocess
import unittest
from pathlib import Path


class Bridge(unittest.TestCase):
    def test_owned_callbacks_setup_ids_timeout_and_cooperative_stop(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node',str(root/'testes/fixture_minecraft_bridge.js'),
            str(root/'compartilhado/servicos/minecraft/bridge.js')],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('102 regressões passaram',result.stdout)


if __name__=='__main__': unittest.main()
