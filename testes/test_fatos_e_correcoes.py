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

    def test_despertar_e_iniciativa_nao_contam_como_pergunta_de_fato(self):
        # Teste de uso 07/11: o texto interno do despertar ("quando", "qual", "onde") ligava o raciocínio à toa.
        interno = 'Acabei de acordar. Vejo quando foi a última conversa, qual é o estado e onde parei.'
        for espontaneo, esperado in ((True, False), (False, True)):
            ciclo = dict(purpose='conversation', choice=None, task_owner=None, task=False,
                         spontaneous=espontaneo, input=interno)
            token = resource_manager._inference_cycle.set(ciclo)
            try:
                with patch.object(config, 'THINKING', True), patch.object(config, 'RACIOCINIO_EM_FATOS', True), \
                     patch.object(resource_manager.diagnostics, 'emit'):
                    self.assertEqual(resource_manager.thinking_for_cycle([{'role': 'user', 'content': interno}]),
                                     esperado)
            finally:
                resource_manager._inference_cycle.reset(token)


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

    def test_acao_anunciada_ou_alegada_sem_ferramenta(self):
        # Teste de uso 07/11: "Vou abrir o Firefox para você. Apareceu uma aba vazia." com ferramentas=[].
        from core import conferencia
        def falta(texto, pedido='voce pode chamar a janela do firefox para min', usadas=(),
                  oferecidas=('abrir_aplicativo',)):
            return conferencia.anunciou_sem_fazer(texto, ferramentas_usadas=list(usadas),
                                                  ferramentas_oferecidas=list(oferecidas), pedido=pedido)
        self.assertEqual(falta('Vou abrir o Firefox para você. Apareceu uma aba vazia.'), 'acao')
        for texto in ('Abri o Firefox.', 'Criei a pasta na área de trabalho.', 'Pronto, já está aberto.',
                      'Enviei a mensagem pra Hoshino.',
                      'O vídeo já estava aberto e tocando.',  # 07/11, 23:05: nada estava tocando
                      'Um vídeo do Adrenaline está tocando sobre a RTX 4070 Ti Super.'):
            with self.subTest(texto=texto):
                self.assertEqual(falta(texto, pedido='e aí?'), 'acao')  # alegou ter feito: sempre cobra
        self.assertEqual(falta('Vou verificar.'), 'conferir')
        for texto, pedido in (('Vou mandar um abraço pra você também!', 'boa noite, um abraço'),
                              ('Não abri nada ainda. Quer que eu abra?', 'abre o firefox'),
                              ('Não vou abrir agora, a GPU está cheia.', 'abre o firefox'),
                              ('Não consegui abrir: o Firefox não está instalado.', 'abre o firefox'),
                              ('Que bom que você gostou!', 'abre o firefox'),
                              ('Estou bem, obrigada!', 'abra um video'),
                              ('O Firefox não está aberto agora. Quer que eu abra?', 'abra um video')):
            with self.subTest(texto=texto):
                self.assertIsNone(falta(texto, pedido=pedido))
        self.assertIsNone(falta('Abri o Firefox.', usadas=['abrir_aplicativo']))  # fez de verdade
        self.assertIsNone(falta('Abri o Firefox.', oferecidas=()))
        self.assertIn('nada aconteceu de verdade', conferencia.PEDIDO_ACAO)
        # 11/11: depois da cobrança, a resposta honesta não é cobrada de novo e não promete a ação.
        for honesta in (conferencia.FALLBACK_HONESTO, 'Não consegui conferir as janelas agora. Quer que eu tente de novo?'):
            self.assertIsNone(conferencia.anunciou_sem_fazer(honesta, ferramentas_usadas=[],
                                                             ferramentas_oferecidas=['observar_tela'],
                                                             pedido='voce consegue ver o que to assistindo'))
        self.assertIsNotNone(conferencia.anunciou_sem_fazer('Vou conferir as janelas do PC2.', ferramentas_usadas=[],
                                                            ferramentas_oferecidas=['observar_tela'],
                                                            pedido='voce consegue ver o que to assistindo'))

    def test_anuncio_ancorado_na_ferramenta_oferecida(self):
        # 12/11, Minecraft: 10 passos de "Vou conectar agora" sem chamar nada (pesos treinados v5 e v6).
        from core import conferencia
        pedido = ('Era pra você entrar, não eu: conecte a sua personagem LilithMC no servidor 10.0.0.200:25565 e '
                  'jogue lá sozinha.')
        oferecidas = [{'function': {'name': n}} for n in ('minecraft_conectar', 'minecraft_estado',
                      'minecraft_iniciar_ponte', 'criar_lembrete', 'parar_voz', 'ver_comando')]
        def anunciadas(texto, usadas=()):
            return conferencia.ferramentas_anunciadas(texto, oferecidas, pedido, usadas=list(usadas))
        for texto, esperado in (
                ('Vou conectar agora, como você pediu. Qual nome você quer que eu use?', ['minecraft_conectar']),
                ('Vou usar "LilithMC" como nome de usuário e conectar ao 10.0.0.200:25565 agora.', ['minecraft_conectar']),
                ('Vou chamar minecraft_estado para ver onde estou.', ['minecraft_estado']),
                ('Conectando ao seu servidor em 10.0.0.200...', ['minecraft_conectar'])):
            with self.subTest(texto=texto):
                self.assertEqual(anunciadas(texto), esperado)
                self.assertEqual(conferencia.anunciou_sem_fazer(texto, ferramentas_usadas=[],
                                                                ferramentas_oferecidas=oferecidas, pedido=pedido), 'acao')
        # depois de outra ferramenta, o anúncio da que falta ainda conta; a já chamada não
        self.assertEqual(anunciadas('Iniciei a ponte. Agora vou conectar.', usadas=['minecraft_iniciar_ponte']),
                         ['minecraft_conectar'])
        self.assertEqual(anunciadas('Agora vou conectar.', usadas=['minecraft_conectar']), [])
        for texto in ('Não vou conectar agora, prefiro esperar.', 'Qual nome você quer que eu use?',
                      'Vou lembrar disso. Vou parar por aqui e ver depois.', 'Conectei e estou no mundo.'):
            with self.subTest(texto=texto):
                self.assertEqual(anunciadas(texto), [])
        # sem a pessoa ter pedido a ação, o verbo sozinho não cobra ("vou conectar os pontos")
        self.assertEqual(conferencia.ferramentas_anunciadas('Vou conectar os pontos da história.', oferecidas,
                                                            'me conta uma história'), [])
        dirigida = conferencia.cobranca('Vou conectar agora.', 'acao', ferramentas_oferecidas=oferecidas, pedido=pedido)
        self.assertIn('minecraft_conectar', dirigida)
        self.assertIn('NADA ACONTECEU', dirigida)
        self.assertEqual(conferencia.cobranca('Vou verificar.', 'conferir', ferramentas_oferecidas=['ficha_da_maquina'],
                                              pedido='quanto de ram?'), conferencia.PEDIDO)
        self.assertEqual(conferencia.cobranca('Abri o Firefox.', 'acao', ferramentas_oferecidas=['abrir_aplicativo'],
                                              pedido='e aí?'), conferencia.PEDIDO_ACAO)

    def test_pedido_de_acao_liga_o_raciocinio(self):
        # 12/11: sem raciocínio os pesos treinados anunciavam e não chamavam (0/5); com ele, 4/5 no primeiro passo.
        def pensa(texto):
            with patch.object(config, 'THINKING', True), patch.object(config, 'RACIOCINIO_EM_FATOS', True), \
                 patch.object(resource_manager.diagnostics, 'emit'):
                return resource_manager.thinking_for_cycle([{'role': 'user', 'content': texto}])
        for texto in ('conecte a sua personagem LilithMC no servidor 10.0.0.200:25565', 'abre o firefox pra mim',
                      'voce pode criar uma pasta para min na area de trabalho', 'entra no servidor e joga sozinha'):
            with self.subTest(texto=texto):
                self.assertTrue(pensa(texto))
        for texto in ('oi, tudo bem?', 'boa noite', 'que legal, gostei'):
            with self.subTest(texto=texto):
                self.assertFalse(pensa(texto))

    def test_o_proprio_nome_nao_oferece_as_ferramentas_das_outras_entidades(self):
        # 12/11: "LilithMC" e "identidade" casavam com Lilith/entidade e traziam entidades_status & cia.
        from core import dispatch
        with patch.object(config, 'ENTIDADE_ID', 'lilith'), patch.dict(dispatch._PALAVRA, {}, clear=True):
            for texto in ('conecte a sua personagem LilithMC no servidor', 'Lilith, tudo bem?', 'qual é a sua identidade?'):
                with self.subTest(texto=texto):
                    self.assertNotIn('interentidades', dispatch._relevantes(texto))
            for texto in ('a Hoshino está acordada?', 'como estão as entidades?'):
                with self.subTest(texto=texto):
                    self.assertIn('interentidades', dispatch._relevantes(texto))
        with patch.object(config, 'ENTIDADE_ID', 'alistair'), patch.dict(dispatch._PALAVRA, {}, clear=True):
            self.assertIn('interentidades', dispatch._relevantes('Lilith, tudo bem?'))

    def test_pediu_o_link_e_a_resposta_nao_mandou(self):
        # 07/11 23:39: "encontre o manga the boxer e me manda o link" → "Já deixei o link do The Boxer aberto".
        from core import conferencia
        saidas = ['Título: The Boxer (manhwa) - Wikipedia Link: https://en.wikipedia.org/wiki/The_Boxer_(manhwa)']
        pedido = 'encontre um manga chamado the boxer e me manda o link'
        self.assertTrue(conferencia.faltou_link('Já deixei o link do The Boxer aberto.', pedido=pedido,
                                                saidas_ferramentas=saidas))
        self.assertFalse(conferencia.faltou_link('Aqui: https://en.wikipedia.org/wiki/The_Boxer_(manhwa)', pedido=pedido,
                                                 saidas_ferramentas=saidas))
        self.assertFalse(conferencia.faltou_link('Não achei.', pedido=pedido, saidas_ferramentas=['nada encontrado']))
        self.assertFalse(conferencia.faltou_link('É um manhwa.', pedido='o que é the boxer?', saidas_ferramentas=saidas))

    def test_chamar_a_janela_de_um_programa_oferece_abrir(self):
        for texto in ('voce pode chamar a janela do firefox para min', 'abre o firefox', 'abrir o terminal',
                      'traz a janela do steam'):
            with self.subTest(texto=texto):
                self.assertIn('abrir_aplicativo', nomes(texto))


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


class MemoriasDoTesteDeUso(unittest.TestCase):
    """07/11 16:48, com a memória recém-apagada: "eu sou o gustavo rosa nunes eu sou o responsvel pela sua existencia
    individual nessa instalação" virou "Gustavo Rosa Nunes se chama Gustavo Rosa Nunes", um segundo Gustavo sem canal,
    um fantasma "alguém" e "O usuário diz que é o responsável… da entidade" como preferência."""

    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute('DELETE FROM memories')
            c.execute('DELETE FROM people')
        p = patch.object(saber.vetor, 'salvar', return_value=False); p.start(); self.addCleanup(p.stop)

    def test_nome_sem_tautologia_e_papel_mesmo_com_erro_de_digitacao(self):
        origem = scribe.origem_entrada({'id': 'usuario'}, 'localhub')
        frase = 'eu sou o gustavo rosa nunes eu sou o responsvel pela sua existencia individual nessa instalação'
        achados = scribe.extrair_por_regra(frase, origem=origem)
        nome = next(a for a in achados if a.get('nome_detectado'))
        self.assertEqual(nome['conteudo'], 'A pessoa com quem falo se chama Gustavo Rosa Nunes')
        self.assertIn('participante:usuario', nome['entidades'])
        papel = next(a for a in achados if a.get('papel') == 'criador')
        self.assertNotIn('foi ela', papel['conteudo'])  # 07/11: "Gustavo… — foi ela que me montou"
        self.assertTrue(papel['conteudo'].startswith('Gustavo Rosa Nunes se declara responsável'))
        self.assertTrue(papel['origem']['autor_nome'] == 'Gustavo Rosa Nunes')
        self.assertEqual(scribe.pos_turno(frase, 'Prazer!', origem=origem).get('papel'), 'criador')

    def test_favorito_e_o_t34_e_nao_o_pedido_seguinte(self):
        # 07/11 23:39: "…o tank t34 sovietico, ele e meu favorito e encontre um manga…" → "favorito = encontre um manga…"
        origem = scribe.origem_entrada({'id': 'usuario'}, 'localhub')
        frase = ('voce pode abrir a wikipedia e me dizer o que e o tank t34 sovietico, ele e meu favorito e encontre um '
                 'manga de luta com tema sombrio chamado the boxer e me manda o link eu to vendo um video sobre ele agora')
        props = [a['propriedade'] for a in scribe.extrair_por_regra(frase, origem=origem) if 'propriedade' in a]
        self.assertEqual(props, [('favorito', 'tank t34 sovietico')])
        for texto, esperado in (('meu cachorro e o Thor', [('cachorro', 'o Thor')]),
                                ('minha cidade é Natal', [('cidade', 'Natal')]),
                                ('meu jogo favorito e me mostra um video', [])):
            with self.subTest(texto=texto):
                self.assertEqual([a['propriedade'] for a in scribe.extrair_por_regra(texto, origem=origem)
                                  if 'propriedade' in a], esperado)

    def test_humano_local_e_um_so_e_renomear_nao_cria_outro(self):
        from social import people
        terminal = people.identificar(nome='', canal='tui', canal_id='local')  # o boot cria "alguém"
        chat = people.identificar(nome='usuario', canal='localhub', canal_id='usuario')
        self.assertEqual(chat['id'], terminal['id'])  # o chat da Central é a mesma pessoa, não uma segunda
        people.renomear(chat['id'], 'Gustavo Rosa Nunes')
        self.assertEqual(people.por_id(chat['id'])['nome'], 'Gustavo Rosa Nunes')
        self.assertEqual(people.identificar(nome='', canal='localhub', canal_id='usuario')['id'], chat['id'])
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM people WHERE status='active'").fetchone()[0], 1)
        from core import chat_identity
        self.assertEqual(chat_identity.display_name(config.DB_PATH), 'Gustavo Rosa Nunes')  # a janela mostra o nome

    def test_bloco_da_pessoa_responde_quem_sou_eu_sem_genero_presumido(self):
        # 07/11 23:30: "me diga que eu sou" → "Não tem nada na minha agenda". O bloco mandava não falar disso, chamava
        # o Gustavo de "ela/nela" e não trazia o que ela sabia dele (a busca por palavras não achou "que eu sou").
        from social import people
        pessoa = people.identificar(nome='usuario', canal='localhub', canal_id='usuario')
        people.renomear(pessoa['id'], 'Gustavo Rosa Nunes'); people.definir_papel(pessoa['id'], 'criador')
        origem = scribe.origem_entrada({'id': 'usuario'}, 'localhub')
        scribe.registrar_achados(scribe.extrair_por_regra(
            'eu sou o gustavo rosa nunes e eu sou o responsavel pela sua existencia individual', origem=origem))
        bloco = people.bloco_pessoa(people.por_id(pessoa['id']))
        self.assertIn('Gustavo Rosa Nunes, criador', bloco)
        self.assertIn('Se perguntarem quem é, respondo', bloco)
        self.assertNotIn('não vira assunto', bloco)
        for feminino in (' nela ', ' dela', 'sobre ela'):
            self.assertNotIn(feminino, bloco)
        self.assertIn('- A pessoa com quem falo se chama Gustavo Rosa Nunes', bloco)
        self.assertIn('se declara responsável por eu existir', bloco)

    def test_anotacao_do_escriba_modelo_fala_de_quem_e_de_mim(self):
        from social import people
        pessoa = people.identificar(nome='usuario', canal='localhub', canal_id='usuario')
        people.renomear(pessoa['id'], 'Gustavo Rosa Nunes')
        origem = scribe.origem_entrada({'id': 'usuario'}, 'localhub')
        with patch.object(config, 'ENTIDADE_NOME', 'Lilith'), patch.object(config, 'ENTIDADE_ID', 'lilith'):
            item = scribe.normalizar_anotacao(dict(tipo='preferencia', confianca=0.6, entidades=['usuário'], conteudo=(
                'O usuário diz que é o responsável pela existência individual da entidade nesta instalação.')), origem)
        self.assertEqual(item['conteudo'], 'Gustavo Rosa Nunes diz que é o responsável pela existência individual da '
                                           'Lilith nesta instalação.')
        self.assertEqual(item['tipo'], 'interpretacao')  # não é gosto
        self.assertIn('participante:usuario', item['entidades'])
        gosto = scribe.normalizar_anotacao(dict(tipo='preferencia', confianca=0.6, entidades=[],
                                                conteudo='O usuário gosta de manhwa de luta.'), origem)
        self.assertEqual((gosto['tipo'], gosto['conteudo']), ('preferencia', 'Gustavo Rosa Nunes gosta de manhwa de luta.'))


class Bronze(unittest.TestCase):
    """07/11 (pedido humano): cartão de bronze no lugar da platina; "o Gustavo me disse que estou em desenvolvimento",
    "o Gustavo disse que está difícil me desenvolver"… quase tudo o que a pessoa diz vira memória."""

    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute('DELETE FROM memories'); c.execute('DELETE FROM people')
        p = patch.object(saber.vetor, 'salvar', return_value=False); p.start(); self.addCleanup(p.stop)

    def test_migracao_platina_vira_diamante_e_bronze_entra(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute("CREATE TABLE memory_card_settings(id TEXT PRIMARY KEY,tier TEXT NOT NULL CHECK(tier IN "
                       "('ferro','ouro','diamante','platina')),updated_at TEXT NOT NULL)")
            db.executemany('INSERT INTO memory_card_settings VALUES(?,?,?)', [('a', 'platina', 't'), ('b', 'ouro', 't')])
            self.assertTrue(init_db.migrar_niveis_cartoes(db))
            self.assertEqual(dict(db.execute('SELECT id,tier FROM memory_card_settings')), {'a': 'diamante', 'b': 'ouro'})
            db.execute("INSERT INTO memory_card_settings VALUES('c','bronze','t')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO memory_card_settings VALUES('d','platina','t')")
            self.assertFalse(init_db.migrar_niveis_cartoes(db))  # só uma vez

    def test_o_que_a_pessoa_disse_e_passageiro_vira_bronze(self):
        import json
        from memory import records
        from social import people
        pessoa = people.identificar(nome='usuario', canal='localhub', canal_id='usuario')
        people.renomear(pessoa['id'], 'Gustavo Rosa Nunes')
        origem = scribe.origem_entrada({'id': 'usuario'}, 'localhub')
        bruto = json.dumps([
            dict(tipo='evento', conteudo='O usuário disse que está difícil me desenvolver.', entidades=['usuário'], confianca=.6),
            dict(tipo='evento', conteudo='O vídeo já estava aberto e tocando.', entidades=[], confianca=.6),
            dict(tipo='fato', conteudo='O usuário tem um cachorro chamado Thor.', entidades=['usuário'], confianca=.6)],
            ensure_ascii=False)
        revisoes = {0: dict(guardar=False, motivo='passageira', base='pessoa', substitui=None),
                    1: dict(guardar=False, motivo='passageira', base='entidade', substitui=None),  # só ela disse
                    2: dict(guardar=False, motivo='sem_apoio', base='nenhuma', substitui=None)}   # inventada
        with patch.object(config, 'ENTIDADE_NOME', 'Lilith'):
            gravadas = scribe.aplicar_extracao(bruto, origem=origem, revisoes=revisoes)
        self.assertEqual(len(gravadas), 1)
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            c.row_factory = sqlite3.Row
            linha = dict(c.execute('SELECT * FROM memories').fetchone())
            pessoas = {r['id']: dict(r) for r in c.execute('SELECT * FROM people')}
        self.assertEqual((linha['source'], linha['type']), (records.FONTE_BRONZE, 'evento'))
        self.assertEqual(linha['content'], 'Gustavo Rosa Nunes disse que está difícil me desenvolver.')
        alvo, = records.card_targets(linha, pessoas, {})
        self.assertEqual(alvo[:2], ('bronze:usuario', 'O que Gustavo Rosa Nunes me disse'))
        self.assertEqual(records.default_tier(alvo[0]), 'bronze')
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            prioridade = records.card_priorities(c)
            self.assertEqual(prioridade('memories', linha), ('bronze', 0.0))  # a menor prioridade ao lembrar
            self.assertEqual(prioridade('memories', dict(linha, source='escriba_llm', entities='[]'))[0], 'ferro')


class ReflexaoSemInstrucoes(unittest.TestCase):
    """07/11: a reflexão leu recibos mecânicos e notas do sistema e guardou como conclusão dela ("os recibos dizem
    sucesso mas não confirmam efeito real"); o despertar virou fala de "alguém"."""

    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute('DELETE FROM episodes'); c.execute('DELETE FROM reflections')

    def test_iniciativa_e_dela_e_recibo_mecanico_nao_vira_reflexao(self):
        import main
        from mind import reflection
        with patch.object(config, 'ENTIDADE_NOME', 'Lilith'):
            main.salvar_episodio('[iniciativa: acabei de acordar: me localizar e avisar no chat]',
                                 'Acabei de acordar. Você está aí?', origem='ciclo_autonomo', canal='localhub')
            main.salvar_episodio('abre um video', 'Abri a busca.', ferramentas=['browser_abrir'], canal='localhub')
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute("INSERT INTO episodes(id,created_at,what_happened,action_taken,result,source,status) VALUES "
                      "('tool-comment-x',datetime('now','localtime'),'Registro automático de ação: browser_abrir; a "
                      "ferramenta retornou um resultado. Não há confirmação independente do efeito.','browser_abrir',"
                      "'success','tool_receipt','active')")
            textos = [r[0] for r in c.execute('SELECT what_happened FROM episodes')]
        self.assertTrue(any(t.startswith('Lilith, por iniciativa própria (acabei de acordar') for t in textos), textos)
        self.assertFalse(any("'[iniciativa:" in t for t in textos))
        material = reflection.material()
        self.assertNotIn('tool-comment-x', [e['id'] for e in material])
        prompt = reflection.prompt_reflexao(material)
        self.assertNotIn('efeitos das ferramentas exigem seus recibos', prompt)
        self.assertNotIn('Registro automático de ação', prompt)


class ModeloExternoDasProvas(unittest.TestCase):
    """07/11 (pedido humano): prova de teto com modelo externo; aqui só a tradução de formato, sem rede."""

    def test_traduz_ferramentas_e_ids_do_ollama_para_openai_e_volta(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('modelo_externo', Path(__file__).resolve().parents[1] / 'scripts/modelo_externo.py')
        me = importlib.util.module_from_spec(spec); spec.loader.exec_module(me)
        ollama = [{'role': 'system', 'content': 'Eu sou Lilith.'}, {'role': 'user', 'content': 'quanto de ram?'},
                  {'role': 'assistant', 'content': '', 'tool_calls': [
                      {'function': {'name': 'ficha_da_maquina', 'arguments': {}}},
                      {'function': {'name': 'web_search', 'arguments': {'query': 'ram'}}}]},
                  {'role': 'tool', 'tool_name': 'ficha_da_maquina', 'content': '32 GB'},
                  {'role': 'tool', 'tool_name': 'web_search', 'content': 'nada'}]
        openai = me.para_openai(ollama)
        chamadas = openai[2]['tool_calls']
        self.assertEqual([c['function']['name'] for c in chamadas], ['ficha_da_maquina', 'web_search'])
        self.assertEqual(chamadas[1]['function']['arguments'], '{"query": "ram"}')
        self.assertEqual([m['tool_call_id'] for m in openai[3:]], [chamadas[0]['id'], chamadas[1]['id']])
        volta = me.do_openai({'content': None, 'tool_calls': [{'id': 'x', 'type': 'function',
                              'function': {'name': 'ficha_da_maquina', 'arguments': '{}'}}]})
        self.assertEqual(volta, {'role': 'assistant', 'content': '',
                                 'tool_calls': [{'function': {'name': 'ficha_da_maquina', 'arguments': {}}, 'id': 'x'}]})
        # 08/11 (prova de teto): o Gemini recusa o passo 2 sem a assinatura de pensamento que veio no passo 1
        assinada = me.do_openai({'tool_calls': [{'id': 'c1', 'type': 'function', 'extra_content': {'google': {'thought_signature': 'SIG'}},
                                                 'function': {'name': 'ficha_da_maquina', 'arguments': '{}'}}]})
        ida = me.para_openai([assinada, {'role': 'tool', 'tool_name': 'ficha_da_maquina', 'content': '32 GB'}])
        self.assertEqual(ida[0]['tool_calls'][0]['extra_content'], {'google': {'thought_signature': 'SIG'}})
        self.assertEqual((ida[0]['tool_calls'][0]['id'], ida[1]['tool_call_id']), ('c1', 'c1'))


class ExecutorPorAPI(unittest.IsolatedAsyncioTestCase):
    """07/11 (pedido humano): "o projeto também deve aceitar API". Desligado por padrão; ligado, não usa GPU; falhou,
    volta para o modelo local."""

    def test_escolha_por_entidade_desligada_por_padrao(self):
        import json, tempfile
        from core import executor_api as ea
        with tempfile.TemporaryDirectory() as td:
            arquivo, chaves = Path(td) / 'executor_api.json', Path(td) / 'chaves.env'
            with patch.object(ea, 'ARQUIVO_ESCOLHA', arquivo), patch.object(ea, 'ARQUIVO_CHAVE', chaves):
                self.assertEqual(ea.escolha('lilith'), {})  # sem cadastro: modelo local
                arquivo.write_text(json.dumps({'apis': {'gemini': {'nome': 'Gemini', 'provedor': 'gemini'},
                                                        'ruim': {'nome': 'x', 'provedor': 'inventado'}},
                                               'entidades': {'lilith': 'gemini', 'hoshino': 'ruim'}}))
                self.assertEqual(ea.escolha('lilith')['modelo'], 'gemini-flash-latest')
                self.assertEqual(ea.escolha('hoshino'), {})  # provedor desconhecido não vale
                self.assertEqual(ea.escolha('alistair'), {})
                with self.assertRaises(ea.APIIndisponivel):
                    ea.chat({'messages': []}, 'hoshino')
                with self.assertRaises(ea.APIIndisponivel):  # escolhida, mas sem chave: não sai do PC
                    ea.chat({'messages': []}, 'lilith')
                chaves.write_text('GEMINI_API_KEY=antiga\n')
                self.assertEqual(ea.chave_de('gemini', 'gemini'), 'antiga')  # a salva à mão vale
                ea.guardar_chave('gemini', 'nova'); self.assertEqual(ea.chave_de('gemini', 'gemini'), 'nova')
                self.assertEqual(oct(chaves.stat().st_mode & 0o777), '0o600')
                ea.guardar_chave('gemini', None); self.assertEqual(ea.chave_de('gemini', 'gemini'), 'antiga')
                # 07/11 (teste real): presa mais de 3 min, a Lilith bloqueou o encerramento da Central.
                with patch.object(ea.Cliente, 'chat', return_value={'role': 'assistant', 'content': 'ok'}) as chamada:
                    ea.chat({'messages': []}, 'lilith')
                self.assertEqual(chamada.call_args.kwargs, {'tentativas': 1, 'limite_s': 40.0})
                self.assertLessEqual(ea.LIMITE_ENTIDADE_S, 40.0)  # menor que a espera do encerramento (45 s)
                # 07/11: modelo aposentado (404) não é tentado de novo a cada chamada; a situação fica para a Central
                with patch.object(ea, 'ARQUIVO_SITUACAO', Path(td) / 'situacao.json'), patch.dict(ea._PAUSAS, clear=True), \
                     patch.object(ea.Cliente, 'chat', side_effect=ea.APIIndisponivel('HTTP 404: modelo indisponível')) as falha:
                    for _ in range(3):
                        with self.assertRaises(ea.APIIndisponivel):
                            ea.chat({'messages': []}, 'lilith')
                    self.assertEqual(falha.call_count, 1)
                    self.assertEqual(ea.situacao()['gemini']['estado'], 'erro')
                    arquivo.write_text(json.dumps({'apis': {'gemini': {'nome': 'Gemini', 'provedor': 'gemini',
                                                                       'modelo': 'outro'}}, 'entidades': {'lilith': 'gemini'}}))
                    with self.assertRaises(ea.APIIndisponivel):
                        ea.chat({'messages': []}, 'lilith')
                    self.assertEqual(falha.call_count, 2)  # trocou o modelo: tenta de novo na hora

    async def test_chamar_modelo_usa_api_sem_gpu_e_volta_ao_local_se_falhar(self):
        import asyncio
        import main
        from core import executor_api

        class _Resp:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {'done': True, 'done_reason': 'stop', 'message': {'role': 'assistant', 'content': 'local'}}

        app = main.InterfaceHoshino.__new__(main.InterfaceHoshino)
        app.trava = asyncio.Lock(); app.trava_modelo = asyncio.Lock()
        with patch.object(config, 'STREAM_LLM', False), patch.object(executor_api, 'ativo', return_value=True), \
             patch.object(executor_api, 'escolha', return_value={'provedor': 'gemini', 'modelo': 'm'}), \
             patch.object(executor_api, 'chat', return_value={'role': 'assistant', 'content': 'da API'}), \
             patch.object(app, '_post_ollama_json_com_lease', side_effect=AssertionError('usou a GPU')) as local:
            msg = await app.chamar_modelo([{'role': 'user', 'content': 'oi'}])
        self.assertEqual(msg['content'], 'da API'); local.assert_not_called()
        with patch.object(config, 'STREAM_LLM', False), patch.object(executor_api, 'ativo', return_value=True), \
             patch.object(executor_api, 'chat', side_effect=executor_api.APIIndisponivel('HTTP 429: cota')), \
             patch.object(app, '_post_ollama_json_com_lease', return_value=_Resp()) as local:
            msg = await app.chamar_modelo([{'role': 'user', 'content': 'oi'}])
        self.assertEqual(msg['content'], 'local'); local.assert_called_once()


class VideoNoPc2(unittest.TestCase):
    """07/11 23:03: "voce pode abrir para min um video do youtube que fala da rtx 4070 ti super", pedido do PC2: o plano
    teve três browser_abrir com a mesma busca (duas abas), nenhum jeito de chegar a um vídeo, e tudo no PC1."""
    PEDIDO = 'voce pode abrir para min um video do youtube que fala da rtx 4070 ti super'

    def nomes(self, maquina):
        from core import pc2_remoto
        token = pc2_remoto.ORIGEM_TURNO.set(maquina)
        try:
            return {c['function']['name'] for c in dispatch.contratos_tarefa(self.PEDIDO)}
        finally:
            pc2_remoto.ORIGEM_TURNO.reset(token)

    def test_tarefa_de_video_tem_caminho_ate_o_video_e_as_maos_do_pc2(self):
        do_pc2 = self.nomes('pc2')
        self.assertTrue({'abrir_no_pc2', 'web_search', 'browser_clicar', 'browser_info'} <= do_pc2, do_pc2)
        do_pc1 = self.nomes('pc1')
        self.assertIn('browser_clicar', do_pc1)
        self.assertNotIn('abrir_no_pc2', do_pc1)

    def test_abrir_de_novo_o_que_ja_abriu_no_turno_nao_repete(self):
        import asyncio
        from unittest.mock import Mock
        import main
        from core import cognition
        url = 'https://www.youtube.com/results?search_query=RTX+4070+Ti+Super'
        self.assertEqual(main._chave_abertura('browser_abrir', {'url': url, 'nova_aba': True}),
                         main._chave_abertura('browser_abrir', {'url': url + '/', 'nova_aba': False}))
        self.assertEqual(main._chave_abertura('browser_rolar', {'direcao': 'baixo'}), '')  # rolar pode repetir
        app = object.__new__(main.InterfaceHoshino)
        app.sys_log = Mock(); app.pessoa = None
        frame = cognition.criar_frame('abrir vídeo')
        frame.aberturas_feitas[main._chave_abertura('browser_abrir', {'url': url})] = 'Navegador aberto: (sem título) | aba=aba-01'
        chamada = [{'function': {'name': 'browser_abrir', 'arguments': {'url': url, 'nova_aba': False}}}]
        async def rodar():
            with patch.object(dispatch, 'executar_resultado', side_effect=AssertionError('abriu de novo')):
                return await app._executar_chamadas_da_etapa(chamada, frame, 1, set())
        (nome, _, resultado), = asyncio.run(rodar())
        self.assertEqual(nome, 'browser_abrir')
        self.assertTrue(resultado['ok'] and resultado['repetida'])
        self.assertIn('não repeti', resultado['output'])


class AreaDeTrabalho(unittest.TestCase):
    def test_area_de_trabalho_real_vem_do_sistema_sem_diferenciar_maiuscula(self):
        # Teste de uso 07/11: o PC tem "Área de trabalho" (t minúsculo); a lista fixa só tinha "Área de Trabalho" e a
        # pasta pedida foi parar num ~/Desktop criado à toa, com "[PASTA VERIFICADA]".
        import os
        import tempfile
        from tools import filesystem
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            real = home / 'Área de trabalho'
            real.mkdir()
            with patch.object(Path, 'home', return_value=home), \
                 patch.dict(os.environ, {'XDG_CONFIG_HOME': str(home / 'cfg')}):
                self.assertEqual(filesystem._desktop_dir(), real.resolve())  # sem user-dirs: pelo nome, sem caixa
                (home / 'Desktop').mkdir()  # um Desktop vazio criado por engano não vence o que o sistema diz
                (home / 'cfg').mkdir()
                (home / 'cfg' / 'user-dirs.dirs').write_text('XDG_DESKTOP_DIR="$HOME/Área de trabalho"\n',
                                                             encoding='utf-8')
                self.assertEqual(filesystem._desktop_dir(), real.resolve())
                for pedido in (str(home / 'Desktop' / 'MinhaPasta'), '~/Área de Trabalho/MinhaPasta',
                               str(home / 'área de trabalho' / 'MinhaPasta')):
                    with self.subTest(pedido=pedido):
                        self.assertEqual(filesystem.resolver_caminho(pedido), (real / 'MinhaPasta').resolve())


class PainelNativo(unittest.TestCase):
    def test_rascunho_trocado_vai_como_digitado_e_atalho_usa_python_do_sistema_no_pc2(self):
        # Teste de uso 07/11 no PC2: (1) depois de uma fala, outro texto digitado era recusado para sempre ("Texto não
        # corresponde à transcrição"); (2) o atalho global exigia o ambiente do projeto, que o painel do PC2 não tem.
        import subprocess
        import tempfile
        raiz = Path(__file__).resolve().parents[1]
        codigo = r'''
import sys, importlib.util
from pathlib import Path
sys.path[:0] = [sys.argv[1] + '/app/ui', sys.argv[1] + '/app']
import central_native as cn
assert cn.draft_keeps_transcript('abre o firefox pra mim', 'abre o firefox pra mim por favor')
assert not cn.draft_keeps_transcript('abre o firefox pra mim', 'eu sou o gustavo')
assert not cn.draft_keeps_transcript('', 'qualquer coisa')
assert cn.hotkey_runtime(sys.argv[1]) == Path(sys.argv[1]) / 'compartilhado/ambientes/principal/bin/python'
sem_ambiente = cn.hotkey_runtime(sys.argv[2])
tem_pynput = importlib.util.find_spec('pynput') is not None
assert sem_ambiente == (Path(sys.executable) if tem_pynput else None), sem_ambiente
print('ok')
'''
        with tempfile.TemporaryDirectory() as pc2:
            saida = subprocess.run(['/usr/bin/python3', '-c', codigo, str(raiz), pc2], capture_output=True, text=True,
                                   timeout=60, env={**__import__('os').environ, 'QT_QPA_PLATFORM': 'offscreen'})
        self.assertEqual(saida.returncode, 0, saida.stderr[-1500:])
        self.assertIn('ok', saida.stdout)


if __name__ == '__main__':
    unittest.main()
