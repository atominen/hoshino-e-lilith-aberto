import concurrent.futures
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
import config
from core import bd, diagnostics, state_file
from memory.sqlite import init_db
from mind import personality, reflection, night_reflection, psych_state, scribe
from social import people


class Persistencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def tearDown(self):
        with sqlite3.connect(config.DB_PATH) as c:
            for trigger in ('fail_traits', 'fail_relation', 'fail_reflection', 'fail_curiosity'):
                c.execute(f'DROP TRIGGER IF EXISTS {trigger}')
        Path(psych_state._path()).unlink(missing_ok=True)

    def test_traco_nao_conta_falha(self):
        with sqlite3.connect(config.DB_PATH) as c:
            c.execute("CREATE TRIGGER fail_traits BEFORE UPDATE ON traits BEGIN SELECT RAISE(ABORT,'simulação disco cheio'); END")
        with patch.object(diagnostics, 'persistence_failure') as diag:
            resultado = personality.registrar_evidencia('humor', .8)
            self.assertTrue(resultado.startswith('Erro de persistência'))
            self.assertTrue(diag.called)
        r = scribe.pos_turno('', 'Olá!')
        self.assertEqual(r['tracos'], [])

    def test_relacao_reverte_ambas_escritas(self):
        pessoa = people.identificar('Teste rollback')
        with sqlite3.connect(config.DB_PATH) as c:
            c.execute("CREATE TRIGGER fail_relation BEFORE INSERT ON person_events BEGIN SELECT RAISE(ABORT,'simulação'); END")
        self.assertEqual(people.registrar_evento(pessoa['id'], 'conversa'), {})
        self.assertEqual(bd.um('SELECT interacoes FROM people WHERE id=?', (pessoa['id'],))['interacoes'], 0)

    def test_reflexao_reverte_aprendizado(self):
        with sqlite3.connect(config.DB_PATH) as c:
            c.execute("CREATE TRIGGER fail_reflection BEFORE INSERT ON memories BEGIN SELECT RAISE(ABORT,'simulação'); END")
        self.assertEqual(reflection.aplicar('- Esta reflexão não deve ser considerada gravada.'), [])
        self.assertIsNone(bd.um("SELECT id FROM reflections WHERE conteudo LIKE 'Esta reflexão%'"))
        with patch.object(bd, 'conexao', side_effect=sqlite3.OperationalError('bloqueado')):
            with self.assertRaises(sqlite3.Error):
                night_reflection.salvar([('teste', 'Nada gravado')])

    def test_concorrencia_preserva_contadores(self):
        with sqlite3.connect(config.DB_PATH) as c:
            c.execute("DELETE FROM traits WHERE nome='curiosidade'")
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda _: personality.registrar_evidencia('curiosidade', .7), range(16)))
        self.assertEqual(bd.um("SELECT evidencias FROM traits WHERE nome='curiosidade'")['evidencias'], 16)

    def test_json_corrompido_nao_e_substituido(self):
        path = Path(psych_state._path())
        path.write_text('{inválido', encoding='utf-8')
        r = psych_state.aplicar_evento('elogio')
        self.assertFalse(r['persisted'])
        self.assertEqual(path.read_text(), '{inválido')

    def test_zero_psicologico_e_none(self):
        from datetime import datetime
        agora = datetime.now()
        r = psych_state.aplicar_evento('elogio', 0, agora)
        self.assertEqual(r['autoeficacia'], psych_state.BASE['autoeficacia'])
        r = psych_state.aplicar_evento('elogio', None, agora)
        self.assertGreater(r['autoeficacia'], psych_state.BASE['autoeficacia'])

    def test_replace_falha_preserva_estado(self):
        psych_state.aplicar_evento('elogio', 0)
        antigo = Path(psych_state._path()).read_bytes()
        with patch('core.state_file.os.replace', side_effect=OSError('disco cheio')):
            self.assertFalse(psych_state.aplicar_evento('elogio')['persisted'])
        self.assertEqual(Path(psych_state._path()).read_bytes(), antigo)

    def test_particoes_json_nao_apagam_outras(self):
        path = Path(config.RUNTIME_DIR) / 'particoes.json'
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            results = list(pool.map(lambda i: state_file.update(path, lambda d: d.update({str(i):i})), range(20)))
        self.assertTrue(all(results))
        self.assertEqual(len(state_file.read(path)), 20)

    def test_diagnostico_estruturado_e_fallback(self):
        with patch.object(diagnostics, '_dirs', side_effect=OSError('sem espaço')), patch('sys.stderr.write') as stderr:
            r = diagnostics.persistence_failure('teste', config.DB_PATH, OSError('cheio'), retry_safe=False)
        self.assertTrue(stderr.called)
        self.assertTrue(r['ts'])
        for field in ('operation','entity','target','error','retry_safe','committed'):
            self.assertIn(field, r['data'])

    def test_indice_vetorial_nao_finge_disponibilidade(self):
        from memory.vector import chroma_store as vetor
        from memory import knowledge_store as saber
        collection = __import__('unittest.mock').mock.Mock()
        collection.upsert.side_effect = OSError('índice indisponível')
        with patch.object(vetor, 'DISPONIVEL', True), patch.object(vetor, 'knowledge_collection', collection), patch.object(diagnostics, 'persistence_failure') as diag:
            r = saber.remember('SQLite independente do índice opcional')
        self.assertIn('índice vetorial não atualizado', r)
        self.assertTrue(diag.called)
        self.assertTrue(bd.um('SELECT id FROM memories WHERE content=?', ('SQLite independente do índice opcional',)))

    def test_noite_nao_remove_pendente_se_estado_falha(self):
        self.assertTrue(night_reflection.solicitar('regressão'))
        with patch('core.state_file.os.replace', side_effect=OSError('cheio')):
            self.assertFalse(night_reflection.marcar_concluida())
        self.assertTrue(night_reflection.pendente())

    def test_self_model_indice_parcial_e_bom_legivel(self):
        from tools import reflection as self_reflection
        with patch.object(self_reflection.sqlite3, 'connect', side_effect=sqlite3.OperationalError('cheio')), patch.object(diagnostics, 'persistence_failure') as diag:
            self.assertFalse(self_reflection._registrar_versao({'version':10}))
        self.assertTrue(diag.call_args.kwargs['partial'])
        path = Path(config.RUNTIME_DIR) / 'legado_bom.json'
        path.write_text('\ufeff{"legado":true}', encoding='utf-8')
        self.assertEqual(state_file.read(path), {'legado':True})

    def test_episodio_nao_inventa_sucesso_da_ferramenta(self):
        import main
        main.salvar_episodio('Teste observável', 'Respondi', ['acao_teste'])
        r = bd.um("SELECT is_success FROM episodes WHERE what_happened LIKE '%Teste observável%'")
        self.assertIsNone(r['is_success'])
        with patch.object(main.sqlite3, 'connect', side_effect=sqlite3.OperationalError('cheio')), patch.object(diagnostics, 'persistence_failure') as diag:
            self.assertFalse(main.salvar_episodio('Não salvo', 'Respondi'))
        self.assertEqual(diag.call_args.args[0], 'memory.save_episode')

    def test_curiosidade_nao_retorna_id_fantasma(self):
        with sqlite3.connect(config.DB_PATH) as c:
            c.execute("CREATE TRIGGER fail_curiosity BEFORE INSERT ON curiosities BEGIN SELECT RAISE(ABORT,'falha'); END")
        self.assertEqual(scribe.curiosidade_nova('Pergunta que não deve aparentar ter sido gravada?', origem='teste'), '')

    def test_self_model_corrompido_nao_e_sobrescrito(self):
        from tools import reflection as self_reflection
        path = Path(config.RUNTIME_DIR) / 'self_model_corrompido.json'
        path.write_text('{inválido', encoding='utf-8')
        with patch.object(self_reflection, 'SELF_MODEL_PATH', str(path)):
            with self.assertRaises(OSError):
                self_reflection._gravar({'version':2})
        self.assertEqual(path.read_text(), '{inválido')

    def test_emocao_nao_afirma_escrita_falha(self):
        from mind import emotions
        with patch.object(emotions, '_gravar', return_value=False):
            self.assertEqual(emotions.sentir('alegria', .5), {})
            with self.assertRaises(OSError):
                emotions.disparar('elogio')

    def test_evento_afetivo_parcial_nao_parece_persistido(self):
        from mind import affect, emotions
        with patch.object(emotions, '_gravar', return_value=False), patch.object(diagnostics, 'persistence_failure') as diag:
            r = affect.apreciar('elogio')
        self.assertFalse(r['persisted'])
        self.assertTrue(r['partial'])
        self.assertEqual(diag.call_args.args[0], 'affect.emotions')


if __name__ == '__main__':
    unittest.main()
