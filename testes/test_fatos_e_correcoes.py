"""Fatos e correções (07/11, pedido humano: "não pode ficar um erro para sempre; as instruções são claras?").

Prompt com regra e exemplos de fato, ficha da máquina como ferramenta, ferramentas certas para perguntas de fato e
de lembrança, amostragem da Qwen, raciocínio em pergunta de fato e correção da pessoa guardada. Banco só de fixture.
"""
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import config
if not any(Path(config.DB_PATH).resolve().is_relative_to(Path(p)) for p in ('/tmp', '/var/tmp')):
    raise RuntimeError('Use testes/executar_isolado.py; banco mental real não é fixture.')
from core import capabilities, dispatch, prompting, resource_manager
from memory.sqlite import init_db
from memory import knowledge_store as saber
from mind import scribe


def nomes(pergunta):
    with patch.object(dispatch.ui_policy, 'filter_schemas', side_effect=lambda root, e, s: s):
        return {e['function']['name'] for e in dispatch.esquemas(pergunta)}


class Prompt(unittest.TestCase):
    def test_bloco_de_fatos_com_regra_e_exemplos_nos_dois_prompts(self):
        for texto in (prompting.FATOS,):
            self.assertIn('digo que não sei', texto)
            self.assertIn('ficha_da_maquina', texto)
            self.assertIn('Você ainda não me disse', texto)
            self.assertIn('não precisa de', texto)  # o que é certo e conhecido não vira busca
        with patch('core.pesos_treinados.identidade_nos_pesos', return_value={'corpus': 'x'}):
            reduzido = prompting.montar_prompt_sistema(situacao='oi, tudo bem?')  # conversa simples também leva
        self.assertIn('[FATOS', reduzido)
        with patch('core.pesos_treinados.identidade_nos_pesos', return_value={}):
            completo = prompting.montar_prompt_sistema(situacao='quanto de ram tem meu pc?')
        self.assertIn('[FATOS', completo)


class Ferramentas(unittest.TestCase):
    def test_ficha_da_maquina_e_leitura_e_esta_sempre_a_mao(self):
        self.assertIn('ficha_da_maquina', capabilities.READ_ONLY)
        self.assertIn('ficha_da_maquina', dispatch.NUCLEO)
        self.assertIn('ficha_da_maquina', nomes('quanto de ram tem meu pc?'))
        with patch('tools.ficha_maquina.ficha', return_value='- Memória RAM: 31.2 GiB'):
            self.assertIn('31.2 GiB', dispatch._executar_bruto('ficha_da_maquina', {}))

    def test_pergunta_de_fato_oferece_pesquisa_e_lembranca_oferece_historico(self):
        for pergunta in ('o que é a obra the boxer?', 'quem escreveu Dom Casmurro?', 'qual o protagonista do mangá X?'):
            with self.subTest(pergunta=pergunta):
                self.assertTrue({'web_search', 'pesquisa_profunda'} <= nomes(pergunta))
        for pergunta in ('lembra do nome do meu cachorro?', 'qual é o meu nome?', 'que tipo de música eu gosto?',
                         'o que eu te disse ontem?'):
            with self.subTest(pergunta=pergunta):
                self.assertIn('buscar_historico_chat', nomes(pergunta))
        self.assertFalse({'web_search', 'buscar_historico_chat'} & nomes('oi, tudo bem?'))


class Amostragem(unittest.TestCase):
    def test_recomendacao_da_qwen_ou_padrao_do_ollama(self):
        with patch.object(config, 'AMOSTRAGEM', 'qwen'):
            self.assertEqual(resource_manager.amostragem(False), {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20})
            self.assertEqual(resource_manager.amostragem(True)['temperature'], 0.6)
        with patch.object(config, 'AMOSTRAGEM', 'padrao'):
            self.assertEqual(resource_manager.amostragem(False), {})

    def test_pergunta_de_fato_liga_o_raciocinio_e_conversa_comum_nao(self):
        def pensa(texto, ligado=True):
            with patch.object(config, 'THINKING', True), patch.object(config, 'RACIOCINIO_EM_FATOS', ligado), \
                 patch.object(resource_manager.diagnostics, 'emit'):
                return resource_manager.thinking_for_cycle([{'role': 'user', 'content': texto}])
        for texto in ('quanto de ram tem meu pc?', 'quem escreveu Dom Casmurro?', 'o que é a obra the boxer?',
                      'lembra do nome do meu cachorro?', 'qual é o meu nome?'):
            with self.subTest(texto=texto):
                self.assertTrue(pensa(texto))
        for texto in ('oi, tudo bem?', 'que legal, gostei', 'boa noite', 'qual é seu nome?', 'qual sua cor favorita?'):
            with self.subTest(texto=texto):
                self.assertFalse(pensa(texto))
        self.assertFalse(pensa('quanto de ram tem meu pc?', ligado=False))


class Conferencia(unittest.TestCase):
    def test_anunciou_ou_alegou_conferencia_sem_chamar_ferramenta(self):
        from core import conferencia
        cobrar = lambda texto, usadas=(), oferecidas=('ficha_da_maquina',): conferencia.anunciou_sem_conferir(
            texto, ferramentas_usadas=list(usadas), ferramentas_oferecidas=list(oferecidas))
        for texto in ('Vou ver a ficha do PC e te responder com o que está escrito lá.', 'Vou verificar.',
                      'O que aparece na ficha é: Intel Core Ultra 5', 'Pesquisando por "The Boxer".',
                      'Segundo a pesquisa, é de 2013.', 'Conferi e são 16 GB.'):
            with self.subTest(texto=texto):
                self.assertTrue(cobrar(texto))
        for texto in ('Paris.', '56.', 'Não sei seu time ainda. Quer me contar?', 'Linus Torvalds, em 1991.',
                      'Recebi o recado, mas não conferi nada.',
                      'Vou te mostrar uma coisa legal'):
            with self.subTest(texto=texto):
                self.assertFalse(cobrar(texto))
        self.assertFalse(cobrar('Vou verificar.', usadas=['ficha_da_maquina']))  # já conferiu
        self.assertFalse(cobrar('Vou verificar.', oferecidas=()))  # sem ferramenta, não há o que cobrar
        self.assertIn('não chamou nenhuma ferramenta', conferencia.PEDIDO)


class Pesquisa(unittest.TestCase):
    def test_fonte_sobre_outra_coisa_vem_marcada(self):
        from tools import pesquisa_profunda as pp
        self.assertEqual(pp.termos_chave("protagonista do mangá 'Céu de Ferro Azul' do Kenji Morita"),
                         ['Céu de Ferro Azul', 'Kenji Morita'])
        paginas = {'https://a.example/1': '<title>Tensura</title><p>' + 'Satoru Mikami renasce como slime. ' * 5 + '</p>',
                   'https://b.example/2': '<title>Outro</title><p>' + 'Rimuru Tempest e o reino dos monstros. ' * 5 + '</p>'}
        buscar = lambda q, n: [{'href': u, 'title': ''} for u in paginas]
        baixar = lambda url, limite, aceitar: (paginas[url].encode(), url, 'text/html')
        with patch('core.rede.exigir', return_value=(True, '')):
            saida = pp.pesquisar("protagonista do mangá 'Céu de Ferro Azul' do Kenji Morita", 2, buscar=buscar, baixar=baixar,
                                 root='/tmp')
        self.assertIn("⚠ não cita 'Céu de Ferro Azul', 'Kenji Morita'", saida)
        self.assertIn('ATENÇÃO: nenhuma fonte cita', saida)
        paginas['https://a.example/1'] = '<title>Céu de Ferro Azul</title><p>' + 'Kenji Morita escreveu Céu de Ferro Azul. ' * 5 + '</p>'
        with patch('core.rede.exigir', return_value=(True, '')):
            saida = pp.pesquisar("protagonista do mangá 'Céu de Ferro Azul' do Kenji Morita", 2, buscar=buscar, baixar=baixar,
                                 root='/tmp')
        self.assertNotIn('ATENÇÃO', saida)


class Correcao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute('DELETE FROM memories')
        p = patch.object(saber.vetor, 'salvar', return_value=False); p.start(); self.addCleanup(p.stop)

    def test_o_que_e_correcao(self):
        for texto, esperado in (('não, o protagonista é um garoto, o Yu', True), ('não, são 32', True),
                                ('nao esse e o meu nome, voce e lilith', True), ('tá errado, é Machado de Assis', True),
                                ('na verdade eu moro em Natal', True), ('você errou o nome', True),
                                ('não, obrigado', False), ('não precisa', False), ('não quero agora', False),
                                ('abre o youtube', False), ('não é?', False)):
            with self.subTest(texto=texto):
                self.assertEqual(scribe.e_correcao(texto), esperado)

    def test_correcao_fica_guardada_com_as_duas_falas_e_autoria_da_pessoa(self):
        origem = scribe.origem_entrada({'id': 'usuario'}, 'localhub')
        guardada = scribe.registrar_correcao('não, o protagonista é um garoto, o Yu',
                                             'The Boxer é um manhwa sobre uma boxeadora.', origem=origem)
        self.assertIn('Eu tinha dito: "The Boxer é um manhwa sobre uma boxeadora."', guardada)
        self.assertIn('o Yu', guardada)
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            fonte, confianca, status = c.execute('SELECT source, confidence, status FROM memories').fetchone()
        self.assertEqual((fonte, confianca, status), ('correcao_da_pessoa', 0.9, 'active'))
        self.assertNotIn('correcao_da_pessoa', saber.FONTES_REVISAVEIS)  # o revisor nunca substitui
        self.assertIsNone(scribe.registrar_correcao('não, obrigado', 'Quer café?', origem=origem))
        self.assertIsNone(scribe.registrar_correcao('não, é o Yu', '', origem=origem))


if __name__ == '__main__':
    unittest.main()
