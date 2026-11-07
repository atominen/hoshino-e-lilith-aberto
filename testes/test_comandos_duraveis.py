"""Processos curtos reais em diretório descartável; nenhum modelo ou serviço."""
import asyncio
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, Mock

import config
from tools import terminal
from tools.command_receipt import atomic_json
from core import command_watch, dispatch, task_state
from memory.sqlite import init_db


class Recibos(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.jobs = self.root / 'jobs'
        for p in (patch.object(terminal, 'JOBS_DIR', str(self.jobs)),
                  patch.object(terminal, '_montar_ambiente', return_value=(dict(__import__('os').environ), str(self.root), 'teste'))):
            p.start()
            self.addCleanup(p.stop)

    def finished(self, job):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = terminal.ver_comando(job)
            if 'RESULTADO_JOB=pending\n' not in result:
                return result
            time.sleep(.03)
        self.fail('Processo curto não terminou no prazo de teste')

    def start(self, command):
        output = terminal.iniciar_comando_longo(command, ambiente='oficina')
        return re.search(r'Job (job-\w+)', output).group(1)

    def test_saida_real_zero_e_nao_zero_duravel(self):
        for code in (0, 7):
            job = self.start(f'printf real; exit {code}')
            result = self.finished(job)
            self.assertIn(f'CODIGO_SAIDA={code}\n', result)
            self.assertIn('real', result)
            saved = json.loads((self.jobs / f'{job}.json').read_text())
            self.assertEqual(saved['codigo'], code)
            # Nova leitura apenas de disco, sem Popen ou handle em memória.
            with patch.object(terminal.subprocess, 'Popen', side_effect=AssertionError('replay')):
                self.assertEqual(terminal.ver_comando(job), result)

    def test_timeout_preserva_um_unico_efeito_e_mesmo_job(self):
        result = terminal.execute_command('printf x >> effect; sleep 1.2; exit 4', ambiente='oficina', timeout=1)
        job = re.search(r'virou o job (job-\w+)', result).group(1)
        self.assertIn('CODIGO_SAIDA=4\n', self.finished(job))
        self.assertEqual((self.root / 'effect').read_text(), 'x')
        self.assertEqual(len(list(self.jobs.glob('job-*.json'))), 1)

    def test_sincrono_usa_exit_do_filho_nao_do_observador(self):
        output = terminal.execute_command('exit 9', ambiente='oficina')
        self.assertEqual(dispatch._resultado_mecanico('execute_command', output)['status'], 'error')
        self.assertIn('saída 9]', output)

    def test_recibo_ausente_nunca_vira_sucesso(self):
        job = self.start('exit 0')
        self.finished(job)
        meta = terminal._ler_job(job)
        # O recibo é gravado pouco antes do processo sair; sob carga ele ainda pode
        # estar vivo, e processo vivo sem recibo é corretamente "pending".
        deadline = time.monotonic() + 8
        while terminal._vivo(meta['pid']) and time.monotonic() < deadline:
            time.sleep(.02)
        (self.jobs / f'{job}.receipt').unlink()
        meta.update(status='rodando', codigo=None)
        terminal._salvar_job(meta)
        self.assertIn('RESULTADO_JOB=uncertain\n', terminal.ver_comando(job))

    def test_recibo_de_outro_processo_rejeitado(self):
        job = self.start('exit 0')
        self.finished(job)
        meta = terminal._ler_job(job)
        receipt = json.loads((self.jobs / f'{job}.receipt').read_text())
        for field in ('process_token', 'pid', 'entity', 'project_root', 'job_id'):
            atomic_json(self.jobs / f'{job}.receipt', {**receipt, field: 'outro'})
            self.assertIsNone(terminal._recibo(meta), field)

    def test_cancelamento_nao_e_sucesso_mesmo_com_recibo_zero(self):
        job = self.start('exit 0')
        self.finished(job)
        meta = terminal._ler_job(job)
        meta.update(status='rodando', codigo=None, outcome='uncertain')
        terminal._salvar_job(meta)
        self.assertIn('RESULTADO_JOB=uncertain\n', terminal.ver_comando(job))

    def test_heartbeat_captura_codigo_real(self):
        job = self.start('exit 3')
        deadline = time.monotonic() + 8
        receipt = self.jobs / f'{job}.receipt'
        while not receipt.exists() and time.monotonic() < deadline:
            time.sleep(.03)
        completed = terminal.jobs_recem_terminados()
        self.assertEqual([(r['id'], r['codigo']) for r in completed], [(job, 3)])
        self.assertEqual(terminal.jobs_recem_terminados(), [])

    def test_caminho_externo_nao_e_job(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('leitura indevida')):
            self.assertIsNone(terminal._ler_job('../segredo'))

    def test_falha_de_lancamento_nao_vira_zero_do_wrapper(self):
        with patch.object(terminal, '_comando_shell', return_value=['/executavel-inexistente-fixture']):
            job = self.start('teste')
        result = self.finished(job)
        self.assertIn('RESULTADO_JOB=error\n', result)
        self.assertIn('CODIGO_SAIDA=None\n', result)

    def test_comando_multilinha_nao_quebra_recibo_mecanico(self):
        job = self.start('printf teste\nexit 5')
        result = self.finished(job)
        self.assertEqual(dispatch._resultado_mecanico('ver_comando', result)['status'], 'error')

    def test_recibo_escrito_durante_consulta_de_pid_nao_se_perde(self):
        meta = {'id':'job-1234abcd', 'pid':123, 'status':'rodando', 'codigo':None}
        receipt = {'code':0, 'started':True, 'finished_at':'agora'}
        with patch.object(terminal, '_recibo', side_effect=[None, receipt]), \
             patch.object(terminal, '_vivo', return_value=False), patch.object(terminal, '_salvar_job'):
            terminal._atualizar_job(meta)
        self.assertEqual(meta['codigo'], 0)


class Continuidade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)

    def setUp(self):
        self.key = ('teste-duravel', self.id())

    def test_pergunta_lateral_preserva_objetivo_sem_se_anexar(self):
        before = task_state.iniciar_ou_continuar(self.key, 'Crie o arquivo resultado.txt e depois leia o arquivo')
        self.assertIsNone(task_state.iniciar_ou_continuar(self.key, 'Como você está?'))
        after = task_state.carregar(self.key)
        self.assertEqual((after.id, after.status, after.objetivo, after.etapas),
                         (before.id, 'active', before.objetivo, before.etapas))

    def test_conversa_nao_reabre_pausa_e_pare_ainda_cancela(self):
        before = task_state.iniciar_ou_continuar(self.key, 'Crie o arquivo resultado.txt')
        task_state.pausar(self.key)
        task_state.iniciar_ou_continuar(self.key, 'Como você está?')
        self.assertEqual(task_state.status_id(before.id), 'paused')
        task_state.iniciar_ou_continuar(self.key, 'pare')
        self.assertNotEqual(task_state.status_id(before.id), 'active')

    def test_verificador_duravel_vinculado_e_nao_inventado(self):
        task_state.iniciar_ou_continuar(self.key, 'Execute o programa')
        output = 'Ainda rodando depois de 1s — não matei o processo, virou o job job-abcdef12 (pid 123).\nSaída parcial:\n'
        receipt = dispatch._resultado_mecanico('execute_command', output)
        task_state.registrar_ferramenta(self.key, 'execute_command', receipt['status'], output, recibo=receipt)
        operation = task_state.proxima_operacao(self.key)
        self.assertEqual((operation['ferramenta'], operation['job_id']), ('ver_comando', 'job-abcdef12'))
        task_state.definir_operacoes(self.key, [{'ferramenta':'execute_command', 'instrucao':'rodar de novo'}])
        self.assertEqual(task_state.proxima_operacao(self.key), operation)
        task = task_state.carregar(self.key)
        self.assertEqual(task_state.normalizar_argumentos_operacao(task, operation, {'job_id':'inventado'})['job_id'], 'job-abcdef12')
        for job in ('job-aaaaaaaa', 'job-abcdef12'):
            out = f'Job {job} [terminado] — comando\nRESULTADO_JOB=success\nCODIGO_SAIDA=0\n'
            r = dispatch._resultado_mecanico('ver_comando', out)
            result = task_state.registrar_ferramenta(self.key, 'ver_comando', r['status'], out, recibo=r)
            self.assertEqual(result.status, 'completed' if job == 'job-abcdef12' else 'active')

    def test_job_bloqueia_dependencias_no_mesmo_marco(self):
        task_state.iniciar_ou_continuar(self.key, 'Execute o programa')
        task_state.definir_operacoes(self.key, [
            {'ferramenta':'execute_command', 'instrucao':'compilar'},
            {'ferramenta':'workspace', 'operacao':'ler', 'instrucao':'ler resultado'}])
        text = 'Job job-abcdef12 iniciado em segundo plano (oficina, pid 123).\nComando: compilar'
        # O controlador pode usar execute_command e receber um aceite durável.
        receipt = dispatch._resultado_mecanico('execute_command', text)
        task_state.registrar_ferramenta(self.key, 'execute_command', receipt['status'], text, recibo=receipt)
        operation = task_state.proxima_operacao(self.key)
        self.assertEqual((operation['ferramenta'], operation['job_id']), ('ver_comando', 'job-abcdef12'))

    def test_espera_consulta_ate_termino_sem_chamar_modelo_ou_acao(self):
        read = AsyncMock(side_effect=[{'status':'pending'}, {'status':'success'}])
        with patch.object(command_watch.asyncio, 'sleep', new_callable=AsyncMock):
            result = asyncio.run(command_watch.wait_for_command({'status':'pending'}, read, lambda: None, time.monotonic()+10))
        self.assertEqual(result['status'], 'success')
        self.assertEqual(read.await_count, 2)

    def test_espera_interrompe_por_cancelamento_e_respeita_prazo(self):
        read = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, 'cancelado'):
            asyncio.run(command_watch.wait_for_command({'status':'pending'}, read, Mock(side_effect=RuntimeError('cancelado')), time.monotonic()+10))
        read.assert_not_awaited()
        result = asyncio.run(command_watch.wait_for_command({'status':'pending'}, read, lambda: None, time.monotonic()-1))
        self.assertEqual(result['status'], 'pending')
        read.assert_not_awaited()

    def test_espera_para_em_falha_ou_incerteza(self):
        for state in ('error', 'uncertain'):
            read = AsyncMock(return_value={'status': state})
            with patch.object(command_watch.asyncio, 'sleep', new_callable=AsyncMock):
                result = asyncio.run(command_watch.wait_for_command({'status':'pending'}, read, lambda: None, time.monotonic()+10))
            self.assertEqual(result['status'], state)
            read.assert_awaited_once()

    def test_ciclo_real_aguarda_job_e_segue_proxima_etapa(self):
        # Mesmo controlador da UI, apenas modelo/ferramentas substituídos por
        # fixtures. Não é uma simulação de qualidade do LLM nem de renderização.
        from test_v28_tarefa_operacional import main
        from core import progress
        task = task_state.iniciar_ou_continuar(self.key, 'Execute o programa e depois leia o arquivo resultado.txt')
        app = object.__new__(main.InterfaceHoshino)
        app._fila_chaves = {}
        app._saidas_por_conversa = {}
        app._locks_saida = {}
        calls = []
        original_args = app._obter_args_de_tarefa

        async def args_for_task(task, operation, **kwargs):
            name = operation['ferramenta']
            if name == 'ver_comando':
                return await original_args(task, operation)
            if name == 'execute_command':
                return {'command': 'comando-fixture'}, ''
            return {'operacao': 'ler', 'caminho': '/tmp/resultado.txt'}, ''

        pending = 'Job job-abcdef12 [rodando] — fixture\nRESULTADO_JOB=pending\nCODIGO_SAIDA=None\n'
        final = 'Job job-abcdef12 [terminado] — fixture\nRESULTADO_JOB=success\nCODIGO_SAIDA=0\n'
        async def execute(calls_tool, *args, **kwargs):
            tool = calls_tool[0]['function']
            name = tool['name']
            params = tool['arguments']
            if isinstance(params, str):
                params = json.loads(params)
            calls.append(name)
            output = ('Ainda rodando depois de 1s — não matei o processo, virou o job job-abcdef12 (pid 123).\n'
                      if name == 'execute_command' else pending if name == 'ver_comando' else 'conteúdo lido')
            return [(name, params, dispatch._resultado_mecanico(name, output))]

        app._obter_args_de_tarefa = args_for_task
        app._executar_chamadas_da_etapa = execute
        app._planejar_operacoes_de_tarefa = AsyncMock(return_value=(False, 'fixture determinística'))
        progress.limpar()
        progress.iniciar('teste-recibo-duravel')
        with patch.object(command_watch.asyncio, 'sleep', new_callable=AsyncMock), \
             patch.object(main.dispatch, 'executar_resultado', return_value=dispatch._resultado_mecanico('ver_comando', final)) as query:
            asyncio.run(app._ciclo_de_ferramentas_impl(
                [{'role':'user', 'content':task.objetivo}], [], chave_conversa=self.key,
                canal='tui', tarefa_turno=task))
        self.assertEqual(calls, ['execute_command', 'ver_comando', 'workspace'])
        self.assertEqual(task_state.status_id(task.id), 'completed')
        query.assert_called_once_with('ver_comando', {'job_id':'job-abcdef12'}, canal='tui', pessoa=None)


if __name__ == '__main__':
    unittest.main()
