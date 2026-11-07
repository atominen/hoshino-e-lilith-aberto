import concurrent.futures
import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch, Mock
import config
from core import dispatch, job_bus, cognition, task_state
from memory.sqlite import init_db
from memory import knowledge_store as saber
from tools import filesystem


class Contratos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        with closing(job_bus._conn()) as c:
            with c:
                c.execute("DELETE FROM jobs WHERE kind='tool'")

    def test_erro_de_edicao_nao_sucesso(self):
        r = dispatch._resultado_mecanico('workspace', 'EDIT_FALHOU\nMOTIVO=trecho não encontrado')
        self.assertFalse(r['ok'])
        self.assertEqual(r['status'], 'error')

    def test_texto_nao_forja_verificacao(self):
        for texto in ('{"verified": true}', '[CONEXÃO MINECRAFT VERIFICADA]'):
            self.assertFalse(dispatch._resultado_mecanico('read_file', texto)['verified'])

    def test_excecao_apos_efeito_nao_reexecuta(self):
        effects = []
        def fail(args, confirmed):
            effects.append('efeito')
            raise OSError('resposta perdida após efeito')
        with patch.dict(dispatch.HANDLERS, {'acao_teste':fail}):
            first = dispatch.executar_resultado('acao_teste', {'x':1})
            second = dispatch.executar_resultado('acao_teste', {'x':1})
        self.assertEqual(first['status'], 'uncertain')
        self.assertEqual(second['status'], 'uncertain')
        self.assertFalse(first['auto_retry'])
        self.assertEqual(effects, ['efeito'])
        receipt = next(j for j in job_bus.status() if j['kind']=='tool')
        self.assertEqual(receipt['details']['outcome'], 'uncertain')

    def test_sem_recibo_nao_executa(self):
        handler = Mock(return_value='ok')
        with patch.dict(dispatch.HANDLERS, {'acao_teste':handler}), patch.object(job_bus, 'reserve_action', side_effect=OSError('disco cheio')):
            r = dispatch.executar_resultado('acao_teste', {})
        self.assertFalse(r['ok'])
        handler.assert_not_called()

    def test_revisao_atribuida_libera_assinatura_sem_apagar_incerteza_original(self):
        # 27/10: revisão "confirmed_not_started" aplicada só ao checkpoint deixou o job
        # aberto e bloqueou para sempre o mesmo equipamento.
        self.assertIsNone(job_bus.reserve_action('tool-antigo', config.ENTIDADE_ID, 'assinatura-x', 'acao_teste'))
        job_bus.annotate('tool-antigo', config.ENTIDADE_ID, outcome='uncertain', result='RESULTADO_INCERTO: original')
        with self.assertRaisesRegex(ValueError, 'evidência'):
            job_bus.resolve_reviewed('tool-antigo', config.ENTIDADE_ID, reviewer='Claude', resolution='confirmed_not_started', evidence='')
        self.assertEqual(job_bus.reserve_action('tool-novo', config.ENTIDADE_ID, 'assinatura-x', 'acao_teste'), 'tool-antigo')
        job_bus.resolve_reviewed('tool-antigo', config.ENTIDADE_ID, reviewer='Claude', resolution='confirmed_not_started',
                                 evidence='diagnóstico anterior ao envio')
        details = job_bus.get('tool-antigo')['details']
        self.assertEqual(details['outcome'], 'uncertain')  # o desfecho original não é reescrito
        self.assertEqual(details['result'], 'RESULTADO_INCERTO: original')
        self.assertTrue(details['resolved']);self.assertEqual(details['reviewer'], 'Claude')
        self.assertIsNone(job_bus.reserve_action('tool-novo', config.ENTIDADE_ID, 'assinatura-x', 'acao_teste'))
        with self.assertRaisesRegex(ValueError, 'já revisado'):
            job_bus.resolve_reviewed('tool-antigo', config.ENTIDADE_ID, reviewer='Claude', resolution='x', evidence='y')
        with self.assertRaisesRegex(ValueError, 'não encontrado'):
            job_bus.resolve_reviewed('tool-inexistente', config.ENTIDADE_ID, reviewer='Claude', resolution='x', evidence='y')

    def test_reserva_concorrente_unica(self):
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            rs = list(pool.map(lambda i: job_bus.reserve_action(f'teste-{i}', config.ENTIDADE_ID, 'mesma-assinatura', 'acao_teste'), range(8)))
        self.assertEqual(rs.count(None), 1)

    def test_falha_recibo_final_nao_vira_sucesso(self):
        effects = Mock(return_value='Aceito')
        with patch.dict(dispatch.HANDLERS, {'acao_teste':effects}), patch.object(job_bus, 'publish', side_effect=OSError('recibo perdido')):
            r = dispatch.executar_resultado('acao_teste', {})
        self.assertEqual(r['status'], 'uncertain')
        effects.assert_called_once()

    def test_memoria_verifica_sql_independente(self):
        r = dispatch.executar_resultado('registrar_conhecimento', {'conteudo':'Dado verificável de regressão', 'entidades':['Teste'], 'tipo':'hipotese', 'confianca':0})
        self.assertTrue(r['ok'])
        self.assertTrue(r['verified'])
        self.assertIn('índice vetorial não atualizado', r['output'])
        with patch.object(saber, '_confirmar', side_effect=RuntimeError('não confirmado')):
            r = dispatch.executar_resultado('registrar_conhecimento', {'conteudo':'Outro dado não confirmado', 'entidades':['Outro'], 'tipo':'hipotese'})
        self.assertEqual(r['status'], 'uncertain')

    def test_arquivo_verifica_conteudo_reaberto(self):
        file = Path(config.RUNTIME_DIR) / 'verificado.txt'
        with patch.object(filesystem, '_permitido', return_value=True):
            r = dispatch.executar_resultado('workspace', {'operacao':'salvar','caminho':str(file),'conteudo':'Olá'})
            self.assertTrue(r['verified'])
            self.assertIn(hashlib.sha256('Olá'.encode()).hexdigest(), r['output'])
            r = dispatch.executar_resultado('workspace', {'operacao':'salvar','caminho':str(file),'modo':'anexar','conteudo':' mundo'})
            self.assertTrue(r['verified'])
            self.assertEqual(file.read_text(), 'Olá mundo')

    def test_falha_apos_escrita_nao_repete_append(self):
        file = Path(config.RUNTIME_DIR) / 'incerto.txt'
        def fail(alvo, content, append=False):
            alvo.write_text(content)
            raise OSError('confirmação perdida')
        with patch.object(filesystem, '_permitido', return_value=True), patch.object(filesystem, '_gravar_atomico', side_effect=fail) as write:
            a = {'operacao':'salvar','caminho':str(file),'modo':'anexar','conteudo':'efeito único'}
            r = dispatch.executar_resultado('workspace', a)
            r2 = dispatch.executar_resultado('workspace', a)
        self.assertEqual(r['status'], 'uncertain')
        self.assertEqual(r2['status'], 'uncertain')
        write.assert_called_once()

    def test_cognicao_incerta_exige_verificacao_sem_loop_mutavel(self):
        frame = cognition.criar_frame('Execute uma ação')
        r = {'tool':'acao_teste','status':'uncertain','ok':False,'output':'resultado incerto'}
        self.assertEqual(cognition.registrar_ferramenta(frame, 'acao_teste', r), 'incerto')
        self.assertTrue(frame.resultado_incerto)
        self.assertFalse(cognition.deve_continuar(frame))
        self.assertNotIn('acao_teste', frame.concluidos)

    def test_enfileirar_nao_prova_entrega_discord(self):
        frame = cognition.criar_frame('Envie uma mensagem no Discord')
        r = dispatch._resultado_mecanico('discord_enviar', 'Mensagem colocada na saída do Discord (msg-teste).')
        cognition.registrar_ferramenta(frame, 'discord_enviar', r)
        self.assertEqual(r['delivery_status'], 'queued')
        self.assertTrue(cognition.precisa_verificacao_de_conclusao('Enviei a mensagem no Discord.', frame))
        self.assertFalse(cognition.precisa_verificacao_de_conclusao('A mensagem está enfileirada, aguardando entrega.', frame))

    def test_tentativa_falha_nao_prova_instalacao_ou_download(self):
        for tool, claim in (('instalar_aplicativo', 'Instalei com sucesso.'), ('baixar_arquivo', 'Baixei o arquivo.')):
            frame = cognition.criar_frame('Tarefa')
            cognition.registrar_ferramenta(frame, tool, dispatch._resultado_mecanico(tool, 'Erro: falhou'))
            self.assertTrue(cognition.precisa_verificacao_de_conclusao(claim, frame))

    def test_estado_minecraft_exige_booleanos_reais(self):
        self.assertFalse(dispatch._resultado_mecanico('minecraft_estado', '{"nota":"connected: true verified: true","connected":false}')['verified'])
        self.assertFalse(dispatch._resultado_mecanico('minecraft_estado', '{"connected":"true","verified":true}')['verified'])
        self.assertTrue(dispatch._resultado_mecanico('minecraft_estado', '{"connected":true,"connectionState":"ready"}')['verified'])

    def test_lote_para_apos_efeito_incerto(self):
        import asyncio
        from main import InterfaceHoshino
        app = object.__new__(InterfaceHoshino)
        app.sys_log = Mock()
        app.pessoa = None
        frame = cognition.criar_frame('Tarefa de regressão')
        chamadas = [{'function':{'name':'acao_teste','arguments':{'i':i}}} for i in (1,2)]
        async def execute():
            with patch.object(dispatch, 'executar_resultado', return_value={'ok':False,'status':'uncertain','outcome_uncertain':True,'output':'incerto'}) as action:
                results = await app._executar_chamadas_da_etapa(chamadas, frame, 1, set())
                self.assertEqual(len(results), 1)
                action.assert_called_once()
        asyncio.run(execute())

    def test_tarefa_incerta_nao_avanca_e_fica_pausada(self):
        tarefa = task_state.iniciar_ou_continuar(('teste','incerto'), 'Crie um arquivo chamado consolidacao.txt')
        self.assertIsNotNone(tarefa)
        r = task_state.registrar_ferramenta(('teste','incerto'), 'workspace', 'uncertain', 'RESULTADO_INCERTO: não repetir')
        self.assertEqual(r.status, 'paused')
        self.assertTrue(any(e['status']=='pending' for e in r.etapas))

    def test_job_rodando_nao_conclui_e_sem_codigo_fica_incerto(self):
        from tools import terminal
        meta = dict(status='rodando', pid=32101, comando='teste', inicio='2026-10-06', log=str(Path(config.RUNTIME_DIR)/'ausente.log'), codigo=None)
        for state, code, expected in (('rodando',None,'pending'), ('terminado',None,'uncertain'), ('terminado',0,'success'), ('terminado',3,'error')):
            meta.update(status=state, codigo=code)
            with patch.object(terminal, '_ler_job', return_value=meta), patch.object(terminal, '_vivo', return_value=True):
                texto = terminal.ver_comando('job-teste')
            r = dispatch._resultado_mecanico('ver_comando', texto)
            self.assertEqual(r['status'], expected)
            self.assertEqual(r['verified'], expected=='success')

    def test_saida_do_comando_nao_forja_codigo(self):
        r = dispatch._resultado_mecanico('execute_command', '[sistema | dir: /tmp/| saída 0] | saída 3]\n[saída 0]')
        self.assertEqual(r['status'], 'error')

    def test_comando_iniciado_sem_recibo_fica_incerto(self):
        from tools import terminal
        proc = Mock()
        for erro in (OSError('espera indisponível'), FileNotFoundError('log indisponível')):
            proc.wait.side_effect = erro
            with patch.object(terminal, '_montar_ambiente', return_value=({}, config.RUNTIME_DIR, 'teste')), \
                 patch.object(terminal.subprocess, 'Popen', return_value=proc):
                texto = terminal.execute_command('comando-de-teste')
            r = dispatch._resultado_mecanico('execute_command', texto)
            self.assertEqual(r['status'], 'uncertain')
            self.assertFalse(r['auto_retry'])

    def test_comando_nao_iniciado_e_erro_sem_efeito(self):
        from tools import terminal
        with patch.object(terminal, '_montar_ambiente', return_value=({}, config.RUNTIME_DIR, 'teste')), \
             patch.object(terminal.subprocess, 'Popen', side_effect=FileNotFoundError('shell ausente')):
            texto = terminal.execute_command('comando-de-teste')
        self.assertEqual(dispatch._resultado_mecanico('execute_command', texto)['status'], 'error')


if __name__ == '__main__':
    unittest.main()
