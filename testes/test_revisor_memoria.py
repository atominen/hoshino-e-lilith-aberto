"""Revisor de memória (07/11): segunda chamada que confere cada anotação do escriba antes de guardar.

Modelo simulado; banco só de fixture (executar via testes/executar_isolado.py).
"""
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import config
if not any(Path(config.DB_PATH).resolve().is_relative_to(Path(p)) for p in ('/tmp', '/var/tmp')):
    raise RuntimeError('Use testes/executar_isolado.py; banco mental real não é fixture.')
import main
from core import diagnostics
from memory.sqlite import init_db
from memory import knowledge_store as saber
from mind import revisor_memoria as rv, scribe


def resposta(citacao='', contradiz=False, duravel=True, relacao='nova'):
    return json.dumps(dict(citacao=citacao, contradiz=contradiz, duravel=duravel, relacao=relacao))


def chamada(nome, **argumentos):
    return {'function': {'name': nome, 'arguments': argumentos}}


class Regras(unittest.TestCase):
    def test_esquema_so_oferece_letras_existentes_e_chaves_em_ordem_alfabetica(self):
        self.assertEqual(rv.esquema(0)['properties']['relacao']['enum'], ['nova'])
        self.assertEqual(rv.esquema(2)['properties']['relacao']['enum'],
                         ['nova', 'igual A', 'igual B', 'atualiza A', 'atualiza B'])
        chaves = list(rv.esquema(3)['properties'])
        self.assertEqual(chaves, sorted(chaves))  # o Ollama devolveu em ordem alfabética; o trecho vem primeiro
        self.assertEqual(chaves[0], 'citacao')

    def test_resposta_fora_do_formato_nao_vira_decisao(self):
        for bruto in ('', 'talvez', '{"citacao": 3, "contradiz": false, "duravel": true, "relacao": "nova"}',
                      '{"citacao": "", "contradiz": "não", "duravel": true, "relacao": "nova"}',
                      resposta(relacao='igual'), resposta(relacao='igual D')):
            self.assertIsNone(rv.ler_resposta(bruto), bruto)
        self.assertEqual(rv.ler_resposta('```json\n' + resposta('x', relacao='atualiza B') + '\n```'),
                         dict(citacao='x', contradiz=False, duravel=True, relacao='atualiza', antiga='B'))

    def test_base_vem_de_onde_o_trecho_esta_nao_da_opiniao_do_modelo(self):
        base = lambda citacao, conteudo, **k: rv.apurar_base(dict(citacao=citacao), dict(conteudo=conteudo), **k)
        conversa = dict(pessoa='lembra do nome do meu cachorro que te falei ontem?', fala='Claro, é o Thor!')
        # Sobre a pessoa, mas o nome veio dela (entidade): 07/11 o 9B chamava isso de "a pessoa disse".
        self.assertEqual(base('meu cachorro', 'O cachorro da pessoa se chama Thor', **conversa), 'entidade')
        self.assertEqual(base('Claro, é o Thor!', 'O cachorro da pessoa se chama Thor', **conversa), 'entidade')
        self.assertEqual(base('', 'O cachorro da pessoa se chama Thor', **conversa), 'nenhuma')
        self.assertEqual(base('trecho que ninguém escreveu', 'O cachorro se chama Thor', **conversa), 'nenhuma')
        self.assertEqual(base('Meu cachorro se chama Bento', 'O cachorro da pessoa se chama Bento',
                              pessoa='meu cachorro se chama bento!', fala='Que nome bonito!'), 'pessoa')
        fontes = [('fetch_page', 'The Boxer is a South Korean manhwa written by Jung Ji-Hoon (2019–2022).')]
        self.assertEqual(base('South Korean manhwa written by Jung Ji-Hoon', 'The Boxer é um manhwa de Jung Ji-Hoon',
                              pessoa='o que é the boxer', fala='É de Jung Ji-Hoon.', fontes=fontes), 'fonte')

    def test_resgate_depois_de_conferir_so_com_todos_os_nomes_e_numeros(self):
        conferencia = [('ficha_da_maquina', {}, 'Placa de vídeo: Radeon RX 6650 XT (VRAM 8.0 GiB); RAM 31.2 GiB')]
        conversa = dict(pessoa='minha placa aguenta?', fala='Sua RX 6650 XT de 8 GB aguenta.', conferencia=conferencia)
        apurar = lambda conteudo: rv.apurar_base(dict(citacao='Sua RX 6650 XT de 8 GB aguenta.'), dict(conteudo=conteudo),
                                                 **conversa)
        self.assertEqual(apurar('A placa de vídeo da pessoa é uma RX 6650 XT de 8 GB'), 'conferencia')
        self.assertEqual(apurar('O PC da pessoa tem 64 GB de RAM'), 'entidade')  # 64 não está na ficha
        self.assertEqual(rv.apurar_base(dict(citacao='Sua RX 6650 XT de 8 GB aguenta.'),
                                        dict(conteudo='A placa da pessoa é boa'), **conversa), 'entidade')  # sem detalhes
        sem_conferencia = dict(conversa, conferencia=None)
        self.assertEqual(rv.apurar_base(dict(citacao='Sua RX 6650 XT de 8 GB aguenta.'),
                                        dict(conteudo='A placa de vídeo da pessoa é uma RX 6650 XT de 8 GB'),
                                        **sem_conferencia), 'entidade')

    def test_decisoes_fixas(self):
        antigas = [dict(id='mem-a', conteudo='A pessoa mora em Recife'), dict(id='mem-b', conteudo='Outra')]
        def decidir(base='pessoa', conferida=False, **k):
            lida = rv.ler_resposta(resposta(**k)); lida['base'] = base
            return rv.decidir(lida, antigas, conferida=conferida)
        self.assertEqual(decidir(contradiz=True)['motivo'], 'sem_apoio')
        # A pessoa corrigindo o que já estava guardado é atualização, não desmentido; vindo de fonte, desmentido vale.
        self.assertEqual(decidir(contradiz=True, relacao='atualiza A')['substitui'], 'mem-a')
        self.assertEqual(decidir(base='fonte', contradiz=True, relacao='atualiza A')['motivo'], 'sem_apoio')
        self.assertEqual(decidir(base='nenhuma')['motivo'], 'sem_apoio')
        self.assertEqual(decidir(duravel=False)['motivo'], 'passageira')
        self.assertEqual(decidir(base='entidade', duravel=False)['motivo'], 'passageira')  # nem confere
        self.assertEqual((decidir(base='entidade')['guardar'], decidir(base='entidade')['motivo']), (False, 'conferir'))
        self.assertEqual(decidir(base='entidade', conferida=True)['motivo'], 'nao_conferida')
        for base in ('pessoa', 'fonte', 'conferencia'):
            self.assertEqual((decidir(base=base)['guardar'], decidir(base=base)['substitui']), (True, None))
        for relacao in ('igual A', 'atualiza A'):  # igual e atualiza dão o mesmo resultado
            d = decidir(relacao=relacao)
            self.assertEqual((d['guardar'], d['substitui'], d['antiga_conteudo']), (True, 'mem-a', 'A pessoa mora em Recife'))
        sem_alvo = decidir(relacao='igual C')  # letra que não existe nesta lista: guarda, não desativa nada
        self.assertEqual((sem_alvo['guardar'], sem_alvo['substitui'], sem_alvo['motivo']), (True, None, 'nova_sem_alvo'))
        self.assertIsNone(rv.decidir(None, antigas))

    def test_pedido_traz_conversa_fontes_anotacao_e_letras(self):
        msgs = rv.mensagens('me mudei pra Natal', 'Que legal!', dict(tipo='fato', conteudo='A pessoa mora em Natal'),
                            [dict(id='x', conteudo='A pessoa mora em Recife')], nome='Lilith')
        self.assertEqual([m['role'] for m in msgs], ['system', 'user'])
        self.assertIn('na fala de Lilith', msgs[0]['content'])
        self.assertIn('PESSOA: "me mudei pra Natal"', msgs[1]['content'])
        self.assertIn('LILITH: "Que legal!"', msgs[1]['content'])
        self.assertIn('[A] "A pessoa mora em Recife"', msgs[1]['content'])
        sem = rv.mensagens('oi', 'oi', dict(conteudo='x' * 10), [], nome='Hoshino')
        self.assertIn('JÁ GUARDADAS: nenhuma', sem[1]['content'])
        self.assertIn('FONTES: nenhuma', sem[1]['content'])
        self.assertNotIn('CONFERÊNCIA', sem[0]['content'] + sem[1]['content'])
        conferida = rv.mensagens('oi', 'oi', dict(conteudo='x' * 10), [], nome='Hoshino',
                                 conferencia=[('web_search', {'query': 'q'}, 'achado')])
        self.assertIn('nas FONTES ou na CONFERÊNCIA', conferida[0]['content'])
        self.assertIn('- web_search {"query": "q"}: achado', conferida[1]['content'])

    def test_fontes_do_turno_curtas_e_as_mais_recentes(self):
        fontes = [(f'ferramenta{i}', f'saída {i} ' + 'x' * 3000) for i in range(6)]
        texto = rv.mensagens('p', 'r', dict(conteudo='anotação qualquer'), [], nome='Lilith', fontes=fontes)[1]['content']
        self.assertNotIn('ferramenta1:', texto)  # só as 4 mais recentes
        self.assertNotIn('ferramenta2:', texto)  # o total passa do limite: sai a mais antiga, não a mais nova
        self.assertIn('[1] ferramenta3: saída 3', texto)
        self.assertIn('[3] ferramenta5: saída 5', texto)
        self.assertLessEqual(max(len(l) for l in texto.splitlines()), rv.MAX_FONTE + 40)


class Conferencia(unittest.IsolatedAsyncioTestCase):
    async def test_o_que_so_ela_disse_e_conferido_e_decidido_com_o_que_achou(self):
        respostas = [{'content': resposta('É sobre uma boxeadora.')},
                     {'content': '', 'tool_calls': [chamada('web_search', query='The Boxer manhwa enredo')]},
                     {'content': 'pronto'},
                     {'content': resposta('')}]
        pedidos = []

        async def chamar(msgs, formato=None, ferramentas=None):
            pedidos.append((msgs, formato, ferramentas))
            return respostas[len(pedidos) - 1]
        executar = AsyncMock(return_value='The Boxer (Jung Ji-Hoon): Yu, um garoto frio, vira boxeador.')
        ferramentas = [{'function': {'name': 'web_search'}}, rv.ESQUEMA_FICHA]
        decisao, info = await rv.revisar(dict(conteudo='The Boxer é sobre uma boxeadora'), [], pessoa='o que é the boxer',
                                         resposta='É sobre uma boxeadora.', nome='Lilith', chamar=chamar,
                                         executar=executar, ferramentas=ferramentas)
        self.assertEqual((decisao['guardar'], decisao['motivo']), (False, 'sem_apoio'))
        executar.assert_awaited_once_with('web_search', {'query': 'The Boxer manhwa enredo'})
        self.assertEqual(info['conferencia'][0]['ferramenta'], 'web_search')
        self.assertIsNone(pedidos[0][2])
        self.assertIs(pedidos[1][2], ferramentas)
        self.assertIn('Só Lilith afirmou', pedidos[1][0][-1]['content'])
        final_msgs = pedidos[-1][0]
        self.assertIn('CONFERÊNCIA FEITA AGORA', final_msgs[1]['content'])
        self.assertIn('Yu, um garoto frio', final_msgs[1]['content'])

    async def test_conferencia_que_confirma_guarda(self):
        respostas = iter([{'content': resposta('Foi o Linus Torvalds, em 1991.')},
                          {'tool_calls': [chamada('web_search', query='criador do linux')]}, {'content': ''},
                          {'content': resposta('creator of the Linux kernel since 1991')}])

        async def chamar(msgs, formato=None, ferramentas=None):
            return next(respostas)
        executar = AsyncMock(return_value='Linus Torvalds is the creator of the Linux kernel since 1991.')
        decisao, info = await rv.revisar(dict(conteudo='O Linux foi criado por Linus Torvalds em 1991'), [],
                                         pessoa='quem criou o linux?', resposta='Foi o Linus Torvalds, em 1991.',
                                         nome='Hoshino', chamar=chamar, executar=executar,
                                         ferramentas=[{'function': {'name': 'web_search'}}])
        self.assertEqual((decisao['guardar'], info['base']), (True, 'conferencia'))

    async def test_no_maximo_duas_ferramentas_e_so_as_de_leitura(self):
        calls = [chamada('execute_command', comando='rm -rf /'), chamada('web_search', query='a'), chamada('web_search', query='b')]
        respostas = iter([{'content': resposta('Isso é assim.')}, {'tool_calls': calls}, {'content': resposta('')}])

        async def chamar(msgs, formato=None, ferramentas=None):
            return next(respostas)
        executar = AsyncMock(return_value='ok')
        decisao, info = await rv.revisar(dict(conteudo='Anotação do mundo'), [], pessoa='p', resposta='Isso é assim.',
                                         nome='Lilith', chamar=chamar, executar=executar,
                                         ferramentas=[{'function': {'name': 'web_search'}}])
        self.assertEqual([c['ferramenta'] for c in info['conferencia']], ['execute_command', 'web_search'])
        executar.assert_awaited_once_with('web_search', {'query': 'a'})  # o comando nunca roda
        self.assertFalse(decisao['guardar'])

    async def test_sem_ferramentas_o_que_so_ela_disse_nao_entra(self):
        chamadas = []

        async def chamar(msgs, formato=None, ferramentas=None):
            chamadas.append(ferramentas)
            return {'content': resposta('Seu PC tem 64 GB de RAM.')}
        decisao, info = await rv.revisar(dict(conteudo='O PC da pessoa tem 64 GB de RAM'), [], pessoa='quanto de ram?',
                                         resposta='Seu PC tem 64 GB de RAM.', nome='Hoshino', chamar=chamar)
        self.assertEqual(chamadas, [None])
        self.assertEqual((decisao['guardar'], decisao['motivo'], info['conferencia']), (False, 'nao_conferida', []))


class Banco(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute('DELETE FROM memories')
        p = patch.object(saber.vetor, 'salvar', return_value=False); p.start(); self.addCleanup(p.stop)
        p = patch.object(saber.vetor, 'buscar', return_value=[]); p.start(); self.addCleanup(p.stop)

    def status(self, mem_id):
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            return c.execute('SELECT status FROM memories WHERE id=?', (mem_id,)).fetchone()[0]

    def inserir(self, mem_id, conteudo, fonte):
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute("INSERT INTO memories(id,type,content,created_at,source,confidence,status) "
                      "VALUES (?,?,?,?,?,?, 'active')", (mem_id, 'interpretacao', conteudo, '2026-11-06T10:00:00', fonte, .6))

    def test_substituir_so_anotacao_ativa_do_escriba_modelo(self):
        self.inserir('mem-escriba', 'A pessoa mora em Recife', 'escriba_llm')
        self.inserir('mem-regra', 'A pessoa se chama Gustavo', 'escriba_regra')
        self.inserir('mem-reflexao', 'Preciso conferir recibos', 'reflexao')
        saber.remember('A pessoa mora em Natal', tipo='interpretacao', fonte='escriba_llm',
                       substituir=['mem-escriba', 'mem-regra', 'mem-reflexao', 'mem-inexistente'])
        self.assertEqual(self.status('mem-escriba'), 'superseded')
        self.assertEqual(self.status('mem-regra'), 'active')
        self.assertEqual(self.status('mem-reflexao'), 'active')
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            vinculo = c.execute("SELECT supersedes FROM memories WHERE content='A pessoa mora em Natal'").fetchone()[0]
        self.assertEqual(json.loads(vinculo), ['mem-escriba'])

    def test_semelhantes_so_do_escriba_ativas_sem_marcar_acesso(self):
        self.inserir('mem-1', 'A pessoa mora em Recife com a família', 'escriba_llm')
        self.inserir('mem-2', 'A pessoa mora em Recife', 'escriba_regra')
        self.inserir('mem-3', 'A pessoa gosta de café', 'escriba_llm')
        achadas = saber.semelhantes('A pessoa mora em Natal com a família')
        self.assertEqual([a['id'] for a in achadas], ['mem-1'])
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            self.assertEqual(c.execute("SELECT COALESCE(access_count,0) FROM memories WHERE id='mem-1'").fetchone()[0], 0)
        self.assertEqual(saber.semelhantes(''), [])

    def test_aplicar_extracao_respeita_revisao(self):
        self.inserir('mem-velha', 'A pessoa mora em Recife', 'escriba_llm')
        bruto = json.dumps([dict(tipo='fato', conteudo='A pessoa pediu para abrir a Wikipedia agora'),
                            dict(tipo='fato', conteudo='A pessoa mora em Natal desde outubro'),
                            dict(tipo='preferencia', conteudo='A pessoa prefere respostas curtas')])
        revisoes = {0: dict(guardar=False, motivo='passageira', substitui=None),
                    1: dict(guardar=True, motivo='atualiza', substitui='mem-velha')}
        with patch.object(scribe, '_origem_atual', return_value={}):
            gravados = scribe.aplicar_extracao(bruto, origem={'autor_id': 'usuario'}, revisoes=revisoes)
        self.assertEqual(gravados, ['A pessoa mora em Natal desde outubro', 'A pessoa prefere respostas curtas'])
        self.assertEqual(self.status('mem-velha'), 'superseded')
        with closing(sqlite3.connect(config.DB_PATH)) as c:
            links = json.loads(c.execute("SELECT links FROM memories WHERE content LIKE '%Natal%'").fetchone()[0])
        self.assertEqual(links[0]['revisao'], 'atualiza')


class Chamada(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        app = object.__new__(main.InterfaceHoshino)
        app._memory_generation = 0
        app.sys_log = AsyncMock()
        return app

    async def test_segunda_chamada_do_mesmo_modelo_estavel_e_curta(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock(side_effect=[{'content': resposta('pediu um vídeo agora', duravel=False)},
                                                   {'content': resposta('tenho um gato, o Tom', relacao='igual A')}])
        candidatos = [dict(tipo='evento', conteudo='A pessoa pediu um vídeo agora'),
                      dict(tipo='fato', conteudo='A pessoa tem um gato chamado Tom')]
        antigas = [[], [dict(id='mem-gato', tipo='fato', conteudo='O gato da pessoa se chama Tom')]]
        with patch.object(config, 'REVISOR_MEMORIA', 'entidade'), \
             patch.object(saber, 'semelhantes', side_effect=antigas), \
             patch.object(diagnostics, 'emit') as emit:
            revisoes = await app.revisar_memoria(candidatos, 'tenho um gato, o Tom; pediu um vídeo agora', 'Que fofo!')
        self.assertEqual(revisoes[0]['motivo'], 'passageira')
        self.assertEqual(revisoes[1]['substitui'], 'mem-gato')
        kwargs = app.chamar_modelo.call_args.kwargs
        self.assertEqual((kwargs['temperatura'], kwargs['limite_saida'], kwargs['priority']), (0, 160, 5))
        self.assertTrue(kwargs['forcar_sem_pensar'])
        self.assertEqual(kwargs['formato']['properties']['relacao']['enum'], ['nova', 'igual A', 'atualiza A'])
        self.assertIsNone(kwargs['ferramentas'])  # a resposta final é JSON; ferramentas só na conferência
        eventos = [c.args[0] for c in emit.call_args_list]
        self.assertEqual(eventos, ['memory.review', 'memory.review'])
        self.assertEqual(emit.call_args_list[1].kwargs['antiga'], 'O gato da pessoa se chama Tom')

    async def test_conferencia_pela_ficha_da_maquina_e_pelo_despachante(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock(side_effect=[
            {'content': resposta('Uma RTX 4090.')},
            {'content': '', 'tool_calls': [chamada('ficha_da_maquina'), chamada('web_search', query='rx 6650 xt vram')]},
            {'content': resposta('')}])
        with patch.object(config, 'REVISOR_MEMORIA', 'entidade'), \
             patch.object(saber, 'semelhantes', return_value=[]), \
             patch('tools.ficha_maquina.ficha', return_value='- Placa de vídeo: RX 6650 XT (VRAM 8.0 GiB)'), \
             patch.object(main.dispatch, 'executar_resultado', return_value={'output': '8 GB GDDR6'}) as despacho, \
             patch.object(diagnostics, 'emit') as emit:
            revisoes = await app.revisar_memoria([dict(conteudo='O PC1 tem uma RTX 4090')], 'que placa eu tenho?',
                                                 'Uma RTX 4090.', fontes=[('observar_tela', 'tela com jogo')])
        self.assertEqual(revisoes[0]['motivo'], 'sem_apoio')
        despacho.assert_called_once_with('web_search', {'query': 'rx 6650 xt vram'})
        nomes = {e['function']['name'] for e in app.chamar_modelo.call_args_list[1].kwargs['ferramentas']}
        self.assertEqual(nomes, set(rv.FERRAMENTAS_CONFERENCIA))
        self.assertIn('RX 6650 XT', app.chamar_modelo.call_args_list[2].args[0][1]['content'])
        self.assertIn('[1] observar_tela: tela com jogo', app.chamar_modelo.call_args_list[0].args[0][1]['content'])
        evento = emit.call_args.kwargs
        self.assertEqual(([c['ferramenta'] for c in evento['conferencia']], evento['fontes']),
                         (['ficha_da_maquina', 'web_search'], 1))

    async def test_falha_ou_resposta_invalida_grava_como_antes(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock(side_effect=[TimeoutError('fixture'), {'content': 'não sei'}])  # formato inválido
        candidatos = [dict(conteudo='Primeira anotação qualquer'), dict(conteudo='Segunda anotação qualquer')]
        with patch.object(config, 'REVISOR_MEMORIA', 'entidade'), \
             patch.object(saber, 'semelhantes', return_value=[]), \
             patch.object(diagnostics, 'emit') as emit:
            revisoes = await app.revisar_memoria(candidatos, 'entrada', 'saída')
        self.assertEqual(revisoes, {})
        self.assertEqual([c.args[0] for c in emit.call_args_list], ['memory.review_failed', 'memory.review_failed'])

    async def test_sono_no_meio_para_de_revisar_sem_erro(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock(side_effect=main.TurnoCancelado())
        with patch.object(config, 'REVISOR_MEMORIA', 'entidade'), \
             patch.object(saber, 'semelhantes', return_value=[]), \
             patch.object(diagnostics, 'emit') as emit:
            revisoes = await app.revisar_memoria([dict(conteudo='Primeira anotação'), dict(conteudo='Segunda anotação')], 'a', 'b')
        self.assertEqual(revisoes, {})
        self.assertEqual(app.chamar_modelo.await_count, 1)
        self.assertEqual(emit.call_args.kwargs['error_type'], 'entity_sleep')

    async def test_desligado_ou_sem_candidatas_nao_chama_modelo(self):
        app = self.fixture()
        app.chamar_modelo = AsyncMock()
        with patch.object(config, 'REVISOR_MEMORIA', 'desligado'):
            self.assertIsNone(await app.revisar_memoria([dict(conteudo='Uma anotação')], 'a', 'b'))
        with patch.object(config, 'REVISOR_MEMORIA', 'entidade'):
            self.assertIsNone(await app.revisar_memoria([], 'a', 'b'))
        with patch.object(config, 'REVISOR_MEMORIA', 'intermediario'), patch.object(config, 'INTERMEDIARIO_URL', ''):
            self.assertIsNone(await app.revisar_memoria([dict(conteudo='Uma anotação')], 'a', 'b'))
        app.chamar_modelo.assert_not_called()

    async def test_extrair_memoria_passa_revisoes_ao_gravar(self):
        app = self.fixture()
        bruto = json.dumps([dict(tipo='fato', conteudo='A pessoa tem um gato chamado Tom')])
        app.chamar_modelo = AsyncMock(return_value={'content': bruto})
        app.revisar_memoria = AsyncMock(return_value={0: dict(guardar=False, motivo='sem_apoio', substitui=None)})
        with patch.object(main.scribe, 'conhecido_sobre', return_value=[]), \
             patch.object(main.scribe, 'aplicar_extracao', return_value=[]) as aplicar, \
             patch('core.speech_perception.learning_allowed', return_value=True):
            await app.extrair_memoria('tenho um gato chamado Tom em casa', 'Que fofo!', fontes=[('web_search', 'x')])
        self.assertEqual(app.revisar_memoria.call_args.kwargs['fontes'], [('web_search', 'x')])
        candidatos = app.revisar_memoria.call_args.args[0]
        self.assertEqual([c['conteudo'] for c in candidatos], ['A pessoa tem um gato chamado Tom'])
        self.assertEqual(aplicar.call_args.kwargs['revisoes'], {0: dict(guardar=False, motivo='sem_apoio', substitui=None)})


if __name__ == '__main__':
    unittest.main()
