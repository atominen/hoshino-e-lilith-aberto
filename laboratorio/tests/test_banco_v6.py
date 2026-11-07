"""Banco de treinamento v6: formato, validação e montagem (07/11/2026)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('montar_banco_v6', RAIZ / 'scripts' / 'montar_banco_v6.py')
assert _spec and _spec.loader
banco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(banco)


def montar(texto, nome='pares_teste.txt'):
    pasta = Path(tempfile.mkdtemp())
    (pasta / nome).write_text(texto, encoding='utf-8')
    return banco.exemplos('v6', pasta, nome.startswith('holdout'))


FERRAMENTAS = {'ficha_da_maquina': {'properties': {}, 'required': []},
               'criar_lembrete': {'properties': {'mensagem': {}, 'quando': {}}, 'required': ['mensagem', 'quando']},
               'area_de_transferencia': {'properties': {'operacao': {'enum': ['listar', 'ler']}}, 'required': ['operacao']}}


class Formato(unittest.TestCase):
    def test_par_com_contexto_ferramenta_e_resposta_ruim(self):
        exs = montar('''# aspecto: fatos
# cat: maquina
U: quanto de ram?
S: [CANAL] voz
N: Tem 16 GB, conforme o arquivo de estado.
F: ficha_da_maquina {}
R: - Memória RAM: cerca de 32 GB instalados no total
H: 32 GB.
L: São 32 GB.
''')
        self.assertEqual([e['entidade'] for e in exs], ['hoshino', 'lilith'])
        msgs = exs[0]['mensagens']
        self.assertEqual([m['role'] for m in msgs], ['system', 'user', 'assistant', 'tool', 'assistant'])
        self.assertEqual(msgs[2]['tool_calls'][0]['function'], {'name': 'ficha_da_maquina', 'arguments': {}})
        self.assertEqual(exs[1]['mensagens'][-1]['content'], 'São 32 GB.')
        self.assertEqual(exs[0]['rejeitada'], 'Tem 16 GB, conforme o arquivo de estado.')
        self.assertIsNone(banco.para_texto(msgs))  # com ferramenta, não vai para o treino atual

    def test_contexto_vira_prefixo_no_treino_atual(self):
        ex = montar('# aspecto: voz_falada\n# cat: curto\nU: tá aí?\nS: [CANAL] voz\nH: Tô.\nL: Estou aqui.\n')[0]
        self.assertEqual(banco.para_texto(ex['mensagens']),
                         [{'role': 'user', 'content': '[CANAL] voz\n\ntá aí?'}, {'role': 'assistant', 'content': 'Tô.'}])

    def test_dialogo_com_ferramenta_no_meio(self):
        ex = montar('''# ent: lilith
# aspecto: dialogo
# cat: x
U: oi
A: Oi!
U: me lembra às 8
F: criar_lembrete {"mensagem": "x", "quando": "8:00"}
R: OK: lembrete criado.
A: Lembrete criado.
''', 'dialogos_teste.txt')[0]
        self.assertEqual([m['role'] for m in ex['mensagens']], ['user', 'assistant', 'user', 'assistant', 'tool', 'assistant'])

    def test_estruturas_quebradas_falham(self):
        for texto in ('# aspecto: fatos\n# cat: x\nU: oi\nH: Oi.\n',                       # par sem L
                      '# aspecto: fatos\n# cat: x\nU: oi\nR: algo\nH: Oi.\nL: Olá.\n',     # R sem F
                      '# aspecto: fatos\n# cat: x\nU: oi\nF: ficha_da_maquina {x}\nR: r\nH: a.\nL: b.\n',  # JSON ruim
                      '# aspecto: inventado\n# cat: x\nU: oi\nH: Oi.\nL: Olá.\n'):           # aspecto desconhecido
            with self.subTest(texto=texto[:40]), self.assertRaises(ValueError):
                montar(texto)


class Validacao(unittest.TestCase):
    def erros(self, texto, nome='pares_teste.txt'):
        return banco.validar(montar(texto, nome), FERRAMENTAS)[0]

    def test_promessa_sem_acao_e_alegacao_sem_ferramenta(self):
        erros = self.erros('# aspecto: fatos\n# cat: x\nU: quanto de ram?\nH: Vou verificar na ficha.\n'
                           'L: Aparece na ficha que são 16 GB.\n')
        self.assertTrue(any('promete conferir' in e for e in erros))
        self.assertTrue(any('anuncia conferência sem ferramenta' in e and '[lilith' in e for e in erros))

    def test_ferramenta_e_argumentos_conferidos_no_esquema(self):
        erros = self.erros('''# aspecto: ferramentas
# cat: x
U: lembra
F: criar_lembrete {"mensagem": "x"}
R: OK
H: Feito, ficou marcado.
L: Ficou marcado.

U: lista
F: area_de_transferencia {"operacao": "apagar"}
R: OK
H: Listado aí.
L: Está listado.

U: abre
F: ferramenta_que_nao_existe {}
R: OK
H: Abri pra você.
L: Abri.
''')
        self.assertTrue(any('falta o argumento obrigatório "quando"' in e for e in erros))
        self.assertTrue(any("fora das opções" in e for e in erros))
        self.assertTrue(any('ferramenta desconhecida' in e for e in erros))

    def test_dia_da_semana_dado_real_genero_e_repeticao(self):
        self.assertEqual(banco.datas_erradas('quinta-feira, 14/11/2026'), ['quinta-feira, 14/11/2026 (é sábado)'])
        self.assertEqual(banco.datas_erradas('sábado, 14/11/2026'), [])
        erros = self.erros('''# aspecto: fatos
# cat: x
U: que dia é hoje?
S: [AGORA] quinta-feira, 14/11/2026
H: Quinta.
L: É quinta.

U: quem sou eu?
H: Você é o Gustavo.
L: Você é o Gustavo, do PC.

U: tudo bem?
H: Tô cansado hoje.
L: Estou bem, obrigada.
''')
        self.assertTrue(any('dia da semana errado' in e for e in erros))
        self.assertTrue(any('dado pessoal real' in e for e in erros))
        self.assertTrue(any('masculino ao falar de si' in e for e in erros))


class BancoReal(unittest.TestCase):
    def test_v5_mais_v6_passam_na_validacao(self):
        ferramentas = banco._ferramentas_conhecidas()
        todos = banco.exemplos('v5', banco.FONTE_V5, False) + banco.exemplos('v6', banco.FONTE_V6, False)
        teste = banco.exemplos('v5', banco.FONTE_V5, True) + banco.exemplos('v6', banco.FONTE_V6, True)
        erros = banco.validar(todos, ferramentas)[0] + banco.validar(teste, ferramentas)[0]
        self.assertEqual(erros, [])
        aspectos = {e['aspecto'] for e in todos if e['versao'] == 'v6'}
        for asp in ('fatos', 'perceber', 'consertar', 'perguntar', 'memoria_uso', 'ferramentas', 'voz_falada',
                    'conhecimento', 'preferencias', 'identidade', 'emocional', 'convivencia', 'iniciativa', 'seguranca'):
            self.assertIn(asp, aspectos)
        self.assertTrue(any(e['rejeitada'] for e in todos))
        self.assertTrue(teste)


if __name__ == '__main__':
    unittest.main()
