import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import action_commentary
from memory.sqlite.init_db import TABELAS

class ActionCommentaryTests(unittest.TestCase):
    def test_comments_have_receipts_not_private_outputs_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'mind.db'
            with sqlite3.connect(p) as db:db.execute(TABELAS['episodes'])
            with patch('core.diagnostics.emit'):
                for _ in range(2):
                    self.assertTrue(action_commentary.record('pesquisar','test-receipt',
                        {'status':'pending','output':'SECRET OUTPUT','args':{'password':'SECRET'}},database=p))
            with sqlite3.connect(p) as db:
                rows=db.execute('SELECT what_happened,context,result,is_success FROM episodes').fetchall()
            self.assertEqual(len(rows),1);self.assertNotIn('SECRET',str(rows))
            self.assertEqual(rows[0][2],'pending');self.assertIsNone(rows[0][3])
            self.assertFalse(json.loads(rows[0][1])['human_conversation'])

    def test_unverified_acceptance_is_not_confirmed_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'mind.db'
            with sqlite3.connect(p) as db:db.execute(TABELAS['episodes'])
            with patch('core.diagnostics.emit'):
                self.assertTrue(action_commentary.record('acao','r',{'ok':True},database=p))
            with sqlite3.connect(p) as db:row=db.execute('SELECT is_success,what_happened FROM episodes').fetchone()
            self.assertIsNone(row[0]);self.assertIn('Não há confirmação independente',row[1])

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'missing.db'
            self.assertFalse(action_commentary.record('acao','r',{'ok':True},database=p))
            self.assertFalse(p.exists())

if __name__=='__main__':unittest.main()
