"""Regressões da camada intenção -> capacidade -> resultado -> verificação."""
import json
import os
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace, ModuleType
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from core import capabilities, cognition, dispatch, intent
from tools import browser, desktop


class BrowserWorkerTests(unittest.TestCase):
    def test_real_mailbox_handler_preserves_sender_recipient_and_does_not_wake(self):
        from core import interentity as bus
        import config
        with tempfile.TemporaryDirectory() as folder,patch.object(bus,'DB_PATH',Path(folder)/'bus.db'),patch.object(config,'ENTIDADE_ID','lilith'):
            bus.register('alistair','sleeping')
            receipt=json.loads(dispatch.HANDLERS['entidades_enviar_mensagem']({'entidade':'alistair','texto':'Oi, Alistair. Sou Lilith.','acordar':False},None))
            actual=bus.peek('alistair')[0]
            self.assertEqual((actual['sender'],actual['recipient']),('lilith','alistair'))
            self.assertEqual(actual['id'],receipt['id']);self.assertIsNone(actual['read_at'])
            self.assertEqual(bus.user_conversation('lilith'),[])
            self.assertEqual(bus.presence('alistair')['status'],'sleeping')

    def test_explicit_entity_message_requires_delivery_not_human_reply(self):
        from core import task_state
        text='so existe um alistair so mande um oi e se apresente lilith'
        chosen=intent.interpretar(text)
        self.assertEqual(chosen.ferramenta_principal,'entidades_enviar_mensagem')
        self.assertEqual(chosen.parametros_sugeridos,{'entidade':'alistair'})
        self.assertTrue(task_state.parece_tarefa(text))
        self.assertIn('entidades_enviar_mensagem',{s['function']['name'] for s in dispatch.esquemas(text)})
        self.assertEqual(intent.interpretar('Envie "oi" para Alistair.').alvo,'alistair')

    def test_mentions_drafts_negation_and_ambiguous_recipients_do_not_send(self):
        for text in ('Você conhece Alistair?', 'Não mande oi ao Alistair.',
                     'Escreva um rascunho para Alistair sem enviar.',
                     'Se eu pedir mande oi ao Alistair, o que acontece?',
                     'Explique a frase "mande oi ao Alistair".',
                     'Sinto saudades de Alistair, oi!', 'Mande um oi e se apresente Lilith.',
                     'Ela disse "mande oi ao Alistair".', 'Ele disse mande oi ao Alistair.',
                     'Escreva uma mensagem para Alistair que diga oi.',
                     'Caso queira, mande oi ao Alistair.',
                     'Não mande mensagem ao Alistair.', 'Ela disse "mande mensagem ao Alistair".',
                     '```mande oi para Alistair```',
                     'Mande oi para Hoshino ou Alistair.', 'Mande oi pra ele.'):
            with self.subTest(text=text):
                self.assertNotEqual(intent.interpretar(text).ferramenta_principal,'entidades_enviar_mensagem')
                self.assertNotEqual(intent.interpretar(text).ferramenta_principal,'discord_enviar')

    def test_installed_native_steam_is_preferred_to_missing_flatpak(self):
        with patch.object(desktop.shutil,'which',side_effect=lambda name: '/usr/bin/flatpak' if name=='flatpak' else None), \
             patch.object(desktop,'_resolver_desktop',return_value=['/usr/games/steam']), \
             patch.object(desktop.subprocess,'Popen') as start:
            result=desktop.abrir_aplicativo('Steam','steam://install/48010')
        self.assertEqual(start.call_args.args[0],['/usr/games/steam','steam://install/48010'])
        self.assertIn('ainda não foi verificada',result)

    def test_info_reports_observed_viewport_not_requested_scroll(self):
        page=SimpleNamespace(url='https://example.org/',title=lambda:'Exemplo',
            locator=lambda _:SimpleNamespace(inner_text=lambda **_: 'Conteúdo'),
            evaluate=Mock(return_value=dict(x=0,y=650,height=900,total=3000)))
        state={**browser._STATE,'pages':{},'page_ids':{},'next_page_id':1}
        with patch.object(browser,'_STATE',state),patch.object(browser,'_get_context'), \
             patch.object(browser,'_page',return_value=page):
            result=browser.info(aba='aba-01')
        self.assertIn('y=650',result);self.assertIn('total=3000',result)
        self.assertNotIn('y=700',result)

    def test_scroll_request_keeps_existing_tab_and_exposes_real_action(self):
        request='Na mesma aba aba-01, role a página para baixo e me diga duas curiosidades.'
        chosen=intent.interpretar(request)
        self.assertEqual(chosen.ferramenta_principal,'browser_rolar')
        self.assertEqual(chosen.parametros_sugeridos,{'aba':'aba-01','pixels':700})
        names={s['function']['name'] for s in dispatch.esquemas(request)}
        self.assertTrue({'browser_rolar','browser_info'} <= names)
        up=intent.interpretar('Role a aba aba-02 para cima 400 pixels.')
        self.assertEqual(up.parametros_sugeridos,{'aba':'aba-02','pixels':-400})

    def test_negated_scroll_and_roleplay_are_not_scroll_actions(self):
        for text in ('Não role a página; só explique.','Vamos fazer roleplay no navegador.'):
            self.assertNotEqual(intent.interpretar(text).ferramenta_principal,'browser_rolar')

    def setUp(self):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.release = threading.Event()
        self.addCleanup(self.executor.shutdown, wait=True)
        self.addCleanup(self.release.set)
        p = patch.object(browser, '_EXECUTOR', self.executor)
        p.start(); self.addCleanup(p.stop)

    def test_open_url_is_required_by_shared_schema(self):
        self.assertIn('url', dispatch.formato_argumentos('browser_abrir')['required'])
        for args in ({}, {'url': None}):
            with self.subTest(args=args):
                self.assertIn('obrigatório ausente: url',
                              dispatch.validar_argumentos('browser_abrir', args))
        self.assertEqual(dispatch.validar_argumentos('browser_abrir',
                         {'url': 'https://example.org/', 'nova_aba': True}), '')

    def test_missing_url_cannot_reach_mutable_handler_or_receipt(self):
        handler = Mock(return_value='must not execute')
        with patch.dict(dispatch.HANDLERS, {'browser_abrir': handler}), \
             patch.object(dispatch.ui_policy, 'allowed', return_value=True), \
             patch.object(dispatch.diagnostics, 'emit'), \
             patch('core.job_bus.reserve_action') as reserve:
            result = dispatch.executar_resultado('browser_abrir', {})
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['ok'])
        self.assertIn('obrigatório ausente: url', result['output'])
        handler.assert_not_called()
        reserve.assert_not_called()

    def test_browser_uses_shared_engine_without_sharing_entity_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / 'shared/chromium-1243/chrome-linux64/chrome'
            installed.parent.mkdir(parents=True)
            installed.touch()
            profile, cache = root / 'entity/profile', root / 'entity/engines'
            ctx = SimpleNamespace(set_default_timeout=Mock(), set_default_navigation_timeout=Mock())
            launch = Mock(return_value=ctx)
            pw = SimpleNamespace(chromium=SimpleNamespace(executable_path=str(installed),
                                 launch_persistent_context=launch), stop=Mock())
            module = ModuleType('playwright.sync_api')
            module.sync_playwright = lambda: SimpleNamespace(start=lambda:pw)
            state = {**browser._STATE, 'context': None, 'playwright': None}
            with patch.dict(os.environ, {}, clear=True), \
                 patch.dict(sys.modules, {'playwright.sync_api': module}), \
                 patch.object(browser, '_STATE', state), patch.object(browser, '_paths', return_value=(profile, cache)):
                self.assertIs(browser._get_context(), ctx)
                self.assertNotIn('PLAYWRIGHT_BROWSERS_PATH', os.environ)
            self.assertEqual(launch.call_args.kwargs['user_data_dir'], str(profile))
            self.assertNotIn('executable_path', launch.call_args.kwargs)
            pw.stop.assert_not_called()

    def test_browser_can_reuse_exact_revision_in_entity_cache(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            root = Path(td)
            expected = root / 'missing/chromium-1243/chrome-linux64/chrome'
            installed = root / 'entity/chromium-1243/chrome-linux64/chrome'
            installed.parent.mkdir(parents=True); installed.touch()
            self.assertEqual(browser._installed_executable_options(
                SimpleNamespace(executable_path=str(expected)), root / 'entity'),
                {'executable_path': str(installed)})

    def test_browser_does_not_use_incompatible_revision(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            root = Path(td)
            expected = root / 'missing/chromium-1243/chrome-linux64/chrome'
            other = root / 'entity/chromium-1242/chrome-linux64/chrome'
            other.parent.mkdir(parents=True); other.touch()
            self.assertEqual(browser._installed_executable_options(
                SimpleNamespace(executable_path=str(expected)), root / 'entity'), {})

    def test_browser_never_overrides_explicit_engine_configuration(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.dict(os.environ, {'PLAYWRIGHT_BROWSERS_PATH': '/explicit/missing'}, clear=True):
            root = Path(td)
            expected = root / 'missing/chromium-1243/chrome-linux64/chrome'
            installed = root / 'entity/chromium-1243/chrome-linux64/chrome'
            installed.parent.mkdir(parents=True); installed.touch()
            self.assertEqual(browser._installed_executable_options(
                SimpleNamespace(executable_path=str(expected)), root / 'entity'), {})

    def test_nested_context_does_not_deadlock_or_change_thread(self):
        threads = []
        page = SimpleNamespace(url='about:blank', title=lambda:'fixture',
            goto=lambda *a, **k:threads.append(threading.get_ident()),
            wait_for_load_state=lambda *a, **k:None)
        state = {**browser._STATE, 'context':SimpleNamespace(pages=[page], new_page=lambda:page),
                 'pages':{}, 'page_ids':{}, 'next_page_id':1}
        with patch.object(browser, '_STATE', state), patch.object(browser, '_BROWSER_CALL_TIMEOUT', .2):
            result = browser.abrir('about:blank')
        self.assertTrue(result.startswith('Navegador aberto:'))
        owner = browser._run(threading.get_ident, .2)
        self.assertEqual(threads, [owner])
        self.assertNotEqual(owner, threading.get_ident())

    def test_http_404_is_not_reported_as_opened_and_points_to_search(self):
        # 06/11: youtube.com/@<nome falado> devolveu 404 e a ferramenta disse "Navegador aberto" (sucesso).
        page = SimpleNamespace(url='https://www.youtube.com/@games-eduu', title=lambda:'404 Not Found',
            goto=lambda *a, **k:SimpleNamespace(status=404), wait_for_load_state=lambda *a, **k:None)
        state = {**browser._STATE, 'context':SimpleNamespace(pages=[], new_page=lambda:page),
                 'pages':{}, 'page_ids':{}, 'next_page_id':1}
        with patch.object(browser, '_STATE', state):
            result = browser.abrir('https://www.youtube.com/@games-eduu')
        self.assertTrue(result.startswith('Não existe: a página respondeu HTTP 404'))
        self.assertIn('results?search_query=', result)
        with patch.dict(dispatch.HANDLERS, {'browser_abrir': lambda a, c: result}):
            self.assertEqual(dispatch.executar_resultado('browser_abrir', {'url':'https://x'})['status'], 'error')
        self.assertIn('search_query', dispatch.formato_argumentos('browser_abrir').get('description', '') or
                      json.dumps(dispatch.esquemas('abra o canal no youtube'), ensure_ascii=False))

    def test_closed_window_is_reopened_once_instead_of_failing_forever(self):
        class TargetClosedError(Exception):
            pass
        def dead():
            raise TargetClosedError('BrowserContext.new_page: Target page, context or browser has been closed')
        page = SimpleNamespace(url='https://www.youtube.com/results?search_query=games', title=lambda:'YouTube',
            goto=lambda *a, **k:SimpleNamespace(status=200), wait_for_load_state=lambda *a, **k:None)
        old_ctx, old_pw = SimpleNamespace(pages=[], new_page=dead, close=Mock()), SimpleNamespace(stop=Mock())
        fresh = SimpleNamespace(pages=[], new_page=lambda:page)
        state = {**browser._STATE, 'context':old_ctx, 'playwright':old_pw, 'pages':{'aba-01':object()},
                 'page_ids':{}, 'next_page_id':2}
        with patch.object(browser, '_STATE', state), \
             patch.object(browser, '_get_context', side_effect=[old_ctx, fresh]):
            result = browser.abrir(page.url)
            self.assertEqual(result, f'Navegador aberto: YouTube | {page.url} | aba=aba-02')
            old_pw.stop.assert_called_once(); self.assertNotIn('aba-01', state['pages'])
        self.assertIn('browser_abrir abre um navegador novo', browser._failure('ao ler página', TargetClosedError('x')))
        # Aba inventada: o erro lista as que existem.
        aberta = object()
        with patch.object(browser, '_STATE', {**browser._STATE, 'pages':{'aba-03':aberta}, 'page_ids':{id(aberta):'aba-03'}}):
            with self.assertRaisesRegex(ValueError, 'abas abertas: aba-03'):
                browser._page(SimpleNamespace(pages=[aberta]), None, 'aba-02')

    def test_nested_run_uses_same_worker(self):
        def outer():
            owner = threading.get_ident()
            self.assertEqual(browser._run(threading.get_ident, .1), owner)
            return 'fixture-ok'
        self.assertEqual(browser._run(outer, .2), 'fixture-ok')

    def test_running_timeout_remains_uncertain_in_action_contract(self):
        with self.assertRaises(browser.BrowserOutcomeUncertain) as captured:
            browser._run(lambda:self.release.wait(1), .02)
        output = browser._failure('ao abrir navegador', captured.exception)
        receipt = dispatch._resultado_mecanico('browser_abrir', output)
        self.assertEqual(receipt['status'], 'uncertain')
        self.assertTrue(receipt['outcome_uncertain'])
        self.assertFalse(receipt['ok'])

    def test_queued_timeout_cancels_before_execution(self):
        with self.assertRaises(browser.BrowserOutcomeUncertain):
            browser._run(lambda:self.release.wait(1), .02)
        effects = []
        with self.assertRaises(TimeoutError) as captured:
            browser._run(lambda:effects.append('not-executed'), .02)
        self.assertNotIsInstance(captured.exception, browser.BrowserOutcomeUncertain)
        self.release.set()
        self.executor.shutdown(wait=True)
        self.assertEqual(effects, [])

    def test_worker_timeout_is_not_mistaken_for_queue_timeout(self):
        def failed():
            raise TimeoutError('fixture failed before any action')
        with self.assertRaisesRegex(TimeoutError, 'fixture failed') as captured:
            browser._run(failed, .2)
        self.assertNotIsInstance(captured.exception, browser.BrowserOutcomeUncertain)


def nomes(q):
    return {x["function"]["name"] for x in dispatch.esquemas(q)}


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    casos = {
        "crie um arquivo txt com hello": "write_file",
        "abra o Firefox": "abrir_aplicativo",
        "abra o YouTube": "browser_abrir",
        "abra a pasta ~/Downloads": "abrir_pasta",
        "mande uma mensagem para o Andrews no Discord": "discord_enviar",
        "conecte no Minecraft LAN": "minecraft_conectar_lan",
        "mine a pedra": "minecraft_minerar",
        "me lembra amanhã às 9 de estudar": "criar_lembrete",
    }
    for q, esperado in casos.items():
        i = intent.interpretar(q)
        check(i.ferramenta_principal == esperado, f"intent: {q}: {i}")
        publico = "workspace" if esperado in dispatch.LEGADOS_ARQUIVOS else esperado
        check(publico in nomes(q), f"roteamento não expôs {publico}: {q}")
        check(not (nomes(q) & dispatch.LEGADOS_ARQUIVOS), "API legada exposta ao modelo")

    discord_intent = intent.interpretar("mande uma mensagem para o Andrews no Discord dizendo oi")
    check(discord_intent.parametros_sugeridos == {"destino": "andrews", "texto": "oi"},
          f"extração de parâmetros Discord incorreta: {discord_intent}")
    desktop_intent = intent.interpretar("abra o Firefox")
    check(desktop_intent.parametros_sugeridos.get("aplicativo") == "firefox",
          f"extração do aplicativo incorreta: {desktop_intent}")
    site_intent = intent.interpretar("abra o YouTube")
    check(site_intent.parametros_sugeridos.get("url") == "https://www.youtube.com/",
          f"extração do site incorreta: {site_intent}")
    pasta_intent = intent.interpretar("abra a pasta ~/Downloads")
    check(pasta_intent.ferramenta_principal == "abrir_pasta" and pasta_intent.parametros_sugeridos.get("caminho") == "~/downloads",
          f"extração da pasta incorreta: {pasta_intent}")

    # 11/11: Hoshino e Lilith não recebem de fábrica as ferramentas que mostram as outras entidades e seus estados.
    check(nomes("oi tudo bem") == dispatch.NUCLEO - {"entidades_status", "recursos_status"},
          "conversa simples deve receber somente o núcleo atual")
    check(all(not capabilities.info(n).mutates for n in nomes("oi tudo bem")), "ação mutável exposta sem intenção")
    multi = nomes("crie um arquivo teste.txt e depois execute um script")
    check("workspace" in multi and "execute_command" in multi, f"pedido composto perdeu uma etapa: {multi}")
    check(capabilities.info("propria_conta").requires_verification is False,
          "ferramenta própria sem verificador não pode criar pendência impossível")
    check(cognition.classificar_erro("Não tenho nada registrado sobre Andrews") == "indefinido",
          "palavra registrada não pode significar sucesso")
    check(cognition.classificar_erro("No histórico antigo estava offline") == "indefinido",
          "palavra offline dentro de dado histórico não pode significar estado offline")

    frame = cognition.criar_frame("crie um arquivo txt")
    with tempfile.TemporaryDirectory() as tmp:
        arquivo = Path(tmp) / "arquivo.txt"
        res = dispatch.executar_resultado("workspace", {"operacao": "salvar", "caminho": str(arquivo), "conteudo": "hello"})
        check(res["ok"] and res["verified"], f"escrita sem recibo verificado: {res}")
        check(arquivo.read_text() == "hello", "efeito externo da escrita ausente")
        cognition.registrar_ferramenta(frame, "workspace", res)
        check(not frame.verificar_depois, "workspace já verifica o hash após a escrita")
        leitura = dispatch.executar_resultado("workspace", {"operacao": "ler", "caminho": str(arquivo)})
        check(leitura["ok"] and "hello" in leitura["output"], "leitura real perdeu conteúdo")
        cognition.registrar_ferramenta(frame, "workspace", leitura)
    check(not cognition.deve_continuar(frame), "frame não deveria entrar em novo loop")

    estado = dispatch.executar_resultado("get_system_time", {})
    for chave in ("tool", "ok", "status", "output", "mutates", "requires_verification", "verified"):
        check(chave in estado, f"resultado estruturado sem {chave}: {estado}")
    check(estado["status"] == "success" and estado["mutates"] is False,
          f"contrato incorreto: {json.dumps(estado, ensure_ascii=False)}")

    check(capabilities.info("write_file").requires_verification,
          "adaptador legado preservado precisa de verificação")
    check(not capabilities.info("consultar_conhecimento").requires_verification,
          "consulta de memória não deve pedir verificação de uma leitura")

    cmd_ok = dispatch._resultado_mecanico("execute_command", "[sistema | dir: /tmp | saída 0]\nok")
    check(cmd_ok["status"] == "success" and not cmd_ok["requires_verification"],
          f"execute_command síncrono com código 0 não deveria abrir verificação: {cmd_ok}")
    cmd_fail = dispatch._resultado_mecanico("execute_command", "[sistema | dir: /tmp | saída 2]\nerro")
    check(cmd_fail["status"] == "error",
          f"código de saída não-zero deveria ser erro: {cmd_fail}")
    print("ok - intenção, roteamento, resultado estruturado e verificação")
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(BrowserWorkerTests))
    check(result.wasSuccessful(), 'contrato do worker de navegador falhou')


if __name__ == "__main__":
    main()
