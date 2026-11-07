import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from laboratorio.core import Laboratory,safe_path
from laboratorio.controle import process_identity


class TestOverlay(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name)
        self.repo=base/'repo';self.repo.mkdir()
        subprocess.run(['git','init','-q',str(self.repo)],check=True)
        (self.repo/'app'/'core').mkdir(parents=True)
        (self.repo/'app'/'core'/'prompting.py').write_text('ORIGINAL = True\n')
        (self.repo/'README.md').write_text('Original protegido\n')
        (self.repo/'laboratorio'/'mods'/'teste'/'files').mkdir(parents=True)
        self.mod=self.repo/'laboratorio'/'mods'/'teste'
        (self.mod/'files'/'override.py').write_text('ORIGINAL = False\n')
        (self.mod/'manifest.json').write_text(json.dumps({'id':'teste','name':'Teste','version':'1',
            'overrides':{'app/core/prompting.py':'files/override.py'}}))
        subprocess.run(['git','-C',str(self.repo),'add','app','README.md'],check=True)
        self.lab=Laboratory(self.repo,base/'home')

    def test_no_original_edit(self):
        self.assertEqual(self.lab.mods()[0]['enabled'],False)
        self.lab.set_mod('teste',True)
        built=self.lab.build()
        self.assertEqual((self.lab.current/'app/core/prompting.py').read_text(),'ORIGINAL = False\n')
        self.assertEqual((self.repo/'app/core/prompting.py').read_text(),'ORIGINAL = True\n')
        self.assertEqual(built['overrides'],{'app/core/prompting.py':'teste'})
        self.lab.set_mod('teste',False)
        self.lab.build()
        self.assertEqual((self.lab.current/'app/core/prompting.py').read_text(),'ORIGINAL = True\n')
        self.assertEqual((self.repo/'app/core/prompting.py').read_text(),'ORIGINAL = True\n')

    def test_traversal(self):
        for path in ['../app/x.py','/etc/passwd','app/../x.py','app/.env','entidades/lilith/memory/banco.db','app/runtime/foo.py']:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):safe_path(path)

    def test_refuse_symlink(self):
        p=self.mod/'files'/'override.py'
        p.unlink()
        p.symlink_to(self.repo/'README.md')
        with self.assertRaises(ValueError):self.lab.mods()

    def test_last_mod_wins(self):
        other=self.repo/'laboratorio/mods/ultimo';(other/'files').mkdir(parents=True)
        (other/'files/override.py').write_text('LAST = True\n')
        (other/'manifest.json').write_text(json.dumps({'id':'ultimo',
            'overrides':{'app/core/prompting.py':'files/override.py'}}))
        self.lab.set_mod('teste',True);self.lab.set_mod('ultimo',True)
        self.lab.build()
        self.assertEqual((self.lab.current/'app/core/prompting.py').read_text(),'LAST = True\n')
        self.assertEqual((self.repo/'app/core/prompting.py').read_text(),'ORIGINAL = True\n')

    def test_proc_identity_refuses_other(self):
        with self.assertRaises((PermissionError,FileNotFoundError,ProcessLookupError,ValueError)):
            process_identity(os.getpid())

if __name__=='__main__': unittest.main()
