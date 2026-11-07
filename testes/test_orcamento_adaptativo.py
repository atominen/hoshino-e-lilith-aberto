"""Orçamento adaptativo de raciocínio: níveis por sinais, aprendizado pelo estouro e modos.

Puro: não chama modelo, jogo nem banco. O checkpoint é um dict em memória.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from core import orcamento_adaptativo as oa  # noqa: E402


def cp(**extra) -> dict:
    base: dict = dict(steps=10, trajectory=[dict(step=9, tool='minecraft_coletar', status='success')],
                goal_monitor=dict(actions_without_progress=0), subgoal=dict(item='stick', total=4, selected_step=2))
    base.update(extra)
    return base


def sinais(c, **kw):
    return oa.sinais_minecraft(c, c.get('goal_monitor'), **kw)


class NiveisTests(unittest.TestCase):
    def test_rotina_aplica_teto_baixo_so_no_modo_ativo(self):
        c = cp()
        ativo = oa.escolher(c, sinais(c), modo_atual='ativo')
        self.assertEqual((ativo['nivel'], ativo['limite']), ('rotina', 1536))
        observar = oa.escolher(c, sinais(c), modo_atual='observar')
        self.assertEqual((observar['nivel'], observar['escolhido'], observar['limite']), ('rotina', 1536, oa.TETO_FIXO))
        desligado = oa.escolher(c, sinais(c), modo_atual='desligado')
        self.assertEqual((desligado['nivel'], desligado['limite']), (None, oa.TETO_FIXO))

    def test_sinais_de_dificuldade_sobem_o_nivel(self):
        casos = [
            (cp(barrier=dict(level=1)), {}, 'dificil', 'barreira'),
            (cp(choice_feedback='divergiu'), {}, 'dificil', 'escolha_divergente'),
            (cp(), dict(morte=True), 'dificil', 'morte'),
            (cp(goal_monitor=dict(actions_without_progress=2)), {}, 'atencao', 'sem_progresso'),
            (cp(trajectory=[dict(status='error')]), {}, 'atencao', 'ultimo_recibo_error'),
            (cp(), dict(perigo=True), 'atencao', 'perigo'),
            (cp(), dict(chat=True), 'atencao', 'chat'),
            (cp(subgoal=dict(selected_step=10)), {}, 'atencao', 'meta_nova'),
            (cp(steps=1), {}, 'atencao', 'inicio'),
        ]
        for c, kw, nivel, motivo in casos:
            with self.subTest(motivo=motivo):
                e = oa.escolher(c, sinais(c, **kw), modo_atual='ativo')
                self.assertEqual(e['nivel'], nivel)
                self.assertIn(motivo, e['motivos'])
                self.assertEqual(e['limite'], oa.TETOS[nivel])

    def test_primeira_meta_pede_atencao_mas_so_na_classe_meta(self):
        c = cp(subgoal=None)
        self.assertEqual(oa.escolher(c, sinais(c), modo_atual='ativo')['nivel'], 'rotina')
        meta = oa.escolher(c, sinais(c), modo_atual='ativo', classe='meta')
        self.assertEqual((meta['nivel'], meta['motivos'], meta['limite']), ('atencao', ['sem_meta'], 4096))
        self.assertEqual(oa.escolher(cp(), sinais(cp()), modo_atual='ativo', classe='meta')['nivel'], 'rotina')

    def test_entrada_estranha_nao_quebra(self):
        s = oa.sinais_minecraft(None, None)
        self.assertEqual(oa.nivel_por_sinais(s)[0], 'atencao')        # sem passos = início
        c = cp(trajectory='lixo', goal_monitor=dict(actions_without_progress='muitas'), subgoal=[1])
        self.assertEqual(oa.escolher(c, sinais(c), modo_atual='ativo')['nivel'], 'rotina')
        c[oa.CHAVE] = dict(teto_rotina=10**9, janela_rotina='x', elevar=-4)
        self.assertEqual(oa.escolher(c, sinais(c), modo_atual='ativo')['limite'], 1536)

    def test_modo_por_ambiente(self):
        for valor, esperado in (('observar', 'observar'), (' DESLIGADO ', 'desligado'), ('qualquer', 'ativo'), ('', 'ativo')):
            with mock.patch.dict(os.environ, {'HOSHINO_ORCAMENTO_ADAPTATIVO': valor}):
                self.assertEqual(oa.modo(), esperado)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(oa.modo(), 'ativo')          # padrão desde o descongelamento de 05/11


class AprendizadoTests(unittest.TestCase):
    def decidir(self, c, pensamento, estourou, modo='ativo'):
        e = oa.escolher(c, sinais(c), modo_atual=modo)
        oa.registrar(c, e, pensamento_chars=pensamento, estourou=estourou)
        return e

    def test_estouro_eleva_a_proxima_e_depois_volta(self):
        c = cp()
        self.assertEqual(self.decidir(c, 6000, True)['nivel'], 'rotina')
        seguinte = self.decidir(c, 500, False)
        self.assertEqual((seguinte['nivel'], seguinte['motivos']), ('atencao', ['estouro_anterior']))
        self.assertEqual(self.decidir(c, 500, False)['nivel'], 'rotina')

    def test_teto_de_rotina_sobe_com_estouros_frequentes_e_desce_com_folga(self):
        c = cp()
        for _ in range(oa.JANELA // 2):      # metade das rotinas estoura (a seguinte vem elevada)
            self.decidir(c, 6000, True)
            self.decidir(c, 500, False)
        self.assertGreater(c[oa.CHAVE]['teto_rotina'], 1536)
        subiu = c[oa.CHAVE]['teto_rotina']
        for _ in range(oa.JANELA):
            self.decidir(c, 300, False)
        self.assertEqual(c[oa.CHAVE]['teto_rotina'], subiu - oa.PASSO)
        for _ in range(oa.JANELA * 10):
            self.decidir(c, 300, False)
        self.assertEqual(c[oa.CHAVE]['teto_rotina'], oa.ROTINA_MIN)      # nunca abaixo do piso
        for _ in range(60):
            self.decidir(c, 9000, True)
            self.decidir(c, 500, False)
        self.assertEqual(c[oa.CHAVE]['teto_rotina'], oa.ROTINA_MAX)      # nem acima do teto

    def test_estouro_continuo_mantem_decisoes_elevadas(self):
        c = cp()
        limites = [self.decidir(c, 20000, True)['limite'] for _ in range(8)]
        self.assertEqual(limites[0], 1536)
        self.assertTrue(all(lim >= oa.TETOS['atencao'] for lim in limites[1:]))

    def test_observar_estima_estouro_pelo_tamanho_do_raciocinio(self):
        c = cp()
        e = oa.escolher(c, sinais(c), modo_atual='observar')
        r = oa.registrar(c, e, pensamento_chars=int(1536 * 3.5) + 1, estourou=False)
        self.assertTrue(r['estouro'])
        r = oa.registrar(c, e, pensamento_chars=1000, estourou=False)
        self.assertFalse(r['estouro'])

    def test_memoria_persiste_no_checkpoint_em_json(self):
        c = cp()
        self.decidir(c, 6000, True)
        volta = json.loads(json.dumps(c))
        self.assertEqual(oa.escolher(volta, sinais(volta), modo_atual='ativo')['motivos'], ['estouro_anterior'])

    def test_escolha_e_meta_aprendem_separadas(self):
        c = cp()
        meta = oa.escolher(c, sinais(c), modo_atual='ativo', classe='meta')
        oa.registrar(c, meta, pensamento_chars=9000, estourou=True)
        self.assertIn(oa.CLASSES['meta'], c)
        self.assertNotIn(oa.CHAVE, c)
        self.assertEqual(oa.escolher(c, sinais(c), modo_atual='ativo')['nivel'], 'rotina')
        self.assertEqual(oa.escolher(c, sinais(c), modo_atual='ativo', classe='meta')['motivos'], ['estouro_anterior'])

    def test_desligado_nao_registra(self):
        c = cp()
        e = oa.escolher(c, sinais(c), modo_atual='desligado')
        self.assertEqual(oa.registrar(c, e, pensamento_chars=9000, estourou=True), {})
        self.assertNotIn(oa.CHAVE, c)


class IntegracaoEstaticaTests(unittest.TestCase):
    def test_teto_adaptativo_so_na_escolha_com_fechamento(self):
        fonte = (ROOT / 'app/main.py').read_text(encoding='utf-8')
        self.assertEqual(fonte.count('limite_saida=choice_output if thinking else 1024'), 1)
        # catálogo completo e chamada nativa não têm fechamento: continuam no teto fixo
        self.assertEqual(fonte.count('limite_saida=DECISION_OUTPUT if thinking else 1024'), 2)
        # a meta usa o teto escolhido na classe própria e registra o resultado
        self.assertIn("classe='meta'", fonte)
        self.assertEqual(fonte.count("orcamento_adaptativo.registrar("), 2)


@unittest.skipIf(os.environ.get('HOSHINO_TEST_OFFLINE') != '1', 'ciclo real só pelo executor isolado')
class CicloMinecraftTests(unittest.TestCase):
    """Ponta a ponta no ciclo observado de main.py, com modelo e jogo simulados."""

    def rodar(self, respostas, modo='ativo'):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import config
        import main
        from core import minecraft_agent, task_state, action_commentary
        app = object.__new__(main.InterfaceHoshino)
        app.chamar_modelo = AsyncMock(side_effect=respostas)
        task = SimpleNamespace(id='orc', objetivo='Minecraft host 127.0.0.1 porta 34993: fabrique um forno.')
        criteria = minecraft_agent.targets(task.objetivo)
        c = minecraft_agent.initial(task.objetivo, criteria)
        c.update(steps=5, subgoal_review_step=5,
                 subgoal={'item': 'stick', 'total': 10, 'note': 'x', 'author': 'lilith', 'selected_step': 0})
        state = {'connected': True, 'verified': True, 'sessionId': 's', 'host': '127.0.0.1', 'port': 34993,
                 'username': 'LilithMC', 'health': 20, 'food': 20,
                 'inventory': [{'name': 'stick', 'count': 2}, {'name': 'oak_planks', 'count': 4}]}
        escolhas = []

        async def probe(*_, **callbacks):
            escolhas.append(await callbacks['ask'](state, c))
            return {'status': 'paused', 'reason': 'fixture', 'used': []}
        with mock.patch.dict(os.environ, {'HOSHINO_ORCAMENTO_ADAPTATIVO': modo}), \
             mock.patch.object(config, 'THINKING', True), mock.patch.object(config, 'ENTIDADE_ID', 'lilith'), \
             mock.patch.object(minecraft_agent, 'load', return_value=c), \
             mock.patch.object(minecraft_agent, 'run', side_effect=probe), \
             mock.patch.object(main.dispatch, 'executar_resultado',
                               return_value={'output': json.dumps(state | {'percepcao': {}})}), \
             mock.patch.object(task_state, 'pausar'), mock.patch.object(action_commentary, 'record_deliberation'):
            asyncio.run(app._ciclo_minecraft_observado(task, criteria, chave_conversa=('test', 'orc', '')))
        return app.chamar_modelo.call_args_list, c, escolhas

    def test_rotina_estoura_o_teto_baixo_fecha_a_decisao_e_eleva_a_proxima(self):
        estouro = RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido; resposta não concluída.')
        estouro.partial_thinking = 'pensei em ver o estado primeiro ' * 200
        chamadas, c, escolhas = self.rodar([estouro, {'content': json.dumps({'opcao': 'estado', 'comentario': 'Ver.'})}])
        self.assertEqual(chamadas[0].kwargs['limite_saida'], 1536)
        self.assertTrue(chamadas[0].kwargs['think_override'])
        self.assertFalse(chamadas[1].kwargs['think_override'])
        self.assertIn('O tempo de pensar desta decisão acabou', chamadas[1].args[0][-1]['content'])
        self.assertEqual(escolhas[0]['tool'], 'minecraft_estado')
        self.assertEqual(c[oa.CHAVE]['elevar'], 1)

    def test_modo_observar_mantem_o_teto_fixo(self):
        chamadas, c, _ = self.rodar([{'content': json.dumps({'opcao': 'estado', 'comentario': 'Ver.'}),
                                       'thinking': 'curto'}], modo='observar')
        self.assertEqual(chamadas[0].kwargs['limite_saida'], oa.TETO_FIXO)
        self.assertEqual(c[oa.CHAVE]['elevar'], 0)


@unittest.skipIf(os.environ.get('HOSHINO_TEST_OFFLINE') != '1', 'main só pelo executor isolado')
class RecargaTests(unittest.TestCase):
    """Carga de ~0,2 s com modelo residente não é recarga; não sobrescreve o custo real no RM."""

    def stream(self, load_ns):
        import main
        from core import resource_manager

        class Resposta:
            def raise_for_status(self): pass
            def iter_lines(self, decode_unicode=True):
                yield json.dumps({'message': {'content': 'oi'}, 'done': False})
                yield json.dumps({'message': {'content': ''}, 'done': True, 'done_reason': 'stop',
                                  'load_duration': load_ns, 'eval_duration': 10, 'total_duration': 20,
                                  'prompt_eval_count': 50, 'prompt_eval_duration': 5, 'eval_count': 2})
            def close(self): pass
        with mock.patch.object(main.requests, 'post', return_value=Resposta()), \
             mock.patch.object(resource_manager, 'record_reload') as gravar:
            msg = main.InterfaceHoshino._post_ollama_stream({'model': 'm', 'options': {}}, 'llm-teste')
        self.assertEqual(msg['content'], 'oi')
        return gravar

    def test_carga_quente_nao_conta_como_recarga(self):
        self.assertFalse(self.stream(220_000_000).called)

    def test_recarga_real_e_registrada(self):
        gravar = self.stream(3_300_000_000)
        self.assertEqual(gravar.call_args.args[1:], ('m', 3.3))


@unittest.skipIf(os.environ.get('HOSHINO_TEST_OFFLINE') != '1', 'main só pelo executor isolado')
class ResumoDiarioTests(unittest.TestCase):
    def rodar(self, respostas):
        import asyncio
        from datetime import datetime
        from unittest.mock import AsyncMock
        import main
        from mind import daily_summary, night_reflection
        app = object.__new__(main.InterfaceHoshino)
        app.prompt_sistema = 'Eu sou Lilith.'
        app.ultima_interacao = None
        app.chamar_modelo = AsyncMock(side_effect=respostas)
        lote = {'id': 'lote-1', 'prompt': 'Resuma o dia.'}
        with mock.patch.object(night_reflection, 'horario_noturno', return_value=True), \
             mock.patch.object(main.InterfaceHoshino, '_trabalho_em_andamento', return_value=False), \
             mock.patch.object(daily_summary, 'next_batch', return_value=lote), \
             mock.patch.object(daily_summary, 'commit') as commit:
            feito = asyncio.run(app.talvez_resumir_dia(datetime(2026, 11, 5, 23, 0)))
        return feito, app.chamar_modelo.call_args_list, commit

    def test_estouro_no_raciocinio_fecha_o_resumo_em_vez_de_perder_o_lote(self):
        estouro = RuntimeError('LLM_STREAM_INCOMPLETO: limite de geração atingido; resposta não concluída.')
        estouro.partial_thinking = 'o dia teve a fornalha e o arco ' * 50
        feito, chamadas, commit = self.rodar([estouro, {'content': 'Hoje terminei o arco.'}])
        self.assertTrue(feito)
        self.assertEqual(len(chamadas), 2)
        self.assertFalse(chamadas[1].kwargs['think_override'])
        self.assertIn('o dia teve a fornalha', chamadas[1].args[0][-2]['content'])
        self.assertEqual(commit.call_args.args[1], 'Hoje terminei o arco.')

    def test_outro_erro_continua_sem_resumo(self):
        feito, chamadas, commit = self.rodar([RuntimeError('LLM_STREAM_INCOMPLETO: prazo total excedido.')])
        self.assertTrue(feito)
        self.assertEqual(len(chamadas), 1)
        self.assertFalse(commit.called)


@unittest.skipIf(os.environ.get('HOSHINO_TEST_OFFLINE') != '1', 'main só pelo executor isolado')
class ReflexaoNoturnaTests(unittest.TestCase):
    """27/10: a janela do executor era menor que a estimada e a reflexão falhava 11 vezes seguidas."""

    def test_recusa_por_contexto_encolhe_o_material_e_tenta_de_novo(self):
        import asyncio
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock
        import main
        from mind import night_reflection as nr
        pedidos = []

        def preparar(limite, agora=None):
            pedidos.append(limite)
            return {'texto': 'x' * min(limite, 3000), 'evidencias': {'material_sha256': 'h', 'limits': limite}}
        fake = SimpleNamespace(ultima_interacao=None, prompt_sistema='Identidade preservada', sys_log=Mock(),
                               chamar_modelo=AsyncMock(side_effect=[
                                   ValueError('Contexto excede o teto seguro; compactação existente necessária.'),
                                   {'content': '[MIM] Ainda devo conferir o que aprendi.'}]))
        with mock.patch.object(nr, 'pendente', return_value=False), \
             mock.patch.object(nr, 'horario_noturno', return_value=True), \
             mock.patch.object(nr, 'concluida_na_noite', return_value=False), \
             mock.patch.object(nr, 'recuperar_salvas', return_value=0), \
             mock.patch.object(nr, 'preparar_material', side_effect=preparar), \
             mock.patch.object(nr, 'prompt', side_effect=lambda preparado: preparado['texto']), \
             mock.patch.object(nr, 'extrair_linhas', return_value=[('mim', 'Ainda devo conferir o que aprendi.')]), \
             mock.patch.object(nr, 'salvar', return_value=1) as salvar, \
             mock.patch.object(nr, 'marcar_concluida', return_value=True), \
             mock.patch.object(main.InterfaceHoshino, '_trabalho_em_andamento', return_value=False), \
             mock.patch.object(main, 'registrar_evento'):
            asyncio.run(main.InterfaceHoshino.talvez_refletir_noturno(fake, datetime(2026, 11, 5, 23, 0)))
        self.assertEqual(fake.chamar_modelo.await_count, 2)
        self.assertLess(pedidos[-1], pedidos[0])
        self.assertTrue(salvar.called)
        self.assertEqual(fake.chamar_modelo.call_args_list[1].args[0][0]['content'], 'Identidade preservada')


class ProjecaoFerramentasTests(unittest.TestCase):
    """05/11: sem janela, o núcleo da atividade declarada é o último esquema a sair."""

    def schema(self, nome, tamanho):
        return {'type': 'function', 'function': {'name': nome, 'description': 'x' * tamanho,
                                                 'parameters': {'type': 'object', 'properties': {}}}}

    def test_ferramenta_essencial_da_atividade_fica_e_as_de_fora_saem_primeiro(self):
        from core import compaction, initiative
        tools = [self.schema('minha_atividade', 300), self.schema('oficina_logica', 2600),
                 self.schema('diario', 600), self.schema('executar_na_oficina', 1000),
                 self.schema('execute_command', 1000), self.schema('ler_da_oficina', 400)]
        msgs = [{'role': 'system', 'content': 'identidade ' * 900}, {'role': 'user', 'content': 'trabalhar'}]
        with mock.patch.object(initiative, 'activity', return_value={'capacidades': ['programacao']}):
            _, sobra = compaction.activity_projection(msgs, tools, context_max=6144, output_max=1024)
        nomes = [s['function']['name'] for s in sobra]
        self.assertIn('executar_na_oficina', nomes)
        self.assertIn('minha_atividade', nomes)
        self.assertNotIn('oficina_logica', nomes)          # fora da atividade e a maior: sai primeiro
        if 'ler_da_oficina' not in nomes:                  # o núcleo só sai depois de todo o resto
            self.assertNotIn('execute_command', nomes)


if __name__ == '__main__':
    unittest.main()
