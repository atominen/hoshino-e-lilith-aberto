import ast
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "app"))

import config
from memory.sqlite import init_db
from core import task_state, intent, user_modes, dispatch
from social import people


class V18Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "hoshino.db"
        config.DB_PATH = str(self.db)
        init_db.DB_PATH = str(self.db)
        init_db.init_database(verbose=False)
        task_state._SCHEMA_DONE = False

    def tearDown(self):
        self.tmp.cleanup()


class TaskContinuityTests(V18Base):
    def test_decompoe_e_mantem_ordem(self):
        texto = "crie o arquivo x e depois execute o programa e por fim leia o resultado"
        partes = task_state.decompor(texto)
        self.assertEqual(
            partes,
            ["crie o arquivo x", "execute o programa", "leia o resultado"],
        )

    def test_tarefa_persiste_e_avanca_pela_ferramenta_certa(self):
        chave = ("tui", "local", "")
        t = task_state.iniciar_ou_continuar(
            chave,
            "crie o arquivo x e depois execute o programa e por fim leia o resultado",
        )
        self.assertEqual(len(t.etapas), 3)
        self.assertEqual([e["ferramenta"] for e in t.etapas],
                         ["workspace", "execute_command", "workspace"])
        self.assertEqual(t.etapas[0]["operacoes_lista"][0]["operacao"], "salvar")
        arquivo = Path(self.tmp.name) / "x.txt"
        recibo = dispatch.executar_resultado("workspace", {"operacao": "salvar", "caminho": str(arquivo), "conteudo": "resultado ok"})
        self.assertTrue(recibo["verified"])
        self.assertEqual(arquivo.read_text(), "resultado ok")

        t = task_state.registrar_ferramenta(chave, "workspace", recibo["status"], recibo["output"], recibo=recibo)
        self.assertEqual(t.etapas[0]["status"], "done")
        self.assertEqual(t.etapas[1]["status"], "pending")
        recibo = dispatch.executar_resultado("execute_command", {"command": "printf 'resultado ok'", "diretorio": self.tmp.name})
        self.assertTrue(recibo["ok"], recibo)
        self.assertFalse(recibo["requires_verification"])
        self.assertIn("resultado ok", recibo["output"])
        t = task_state.registrar_ferramenta(chave, "execute_command", recibo["status"], recibo["output"], recibo=recibo)
        self.assertEqual(t.etapas[1]["status"], "done")
        self.assertEqual(t.etapas[2]["status"], "pending")
        recibo = dispatch.executar_resultado("workspace", {"operacao": "ler", "caminho": str(arquivo)})
        self.assertTrue(recibo["ok"])
        self.assertIn("resultado ok", recibo["output"])
        t = task_state.registrar_ferramenta(chave, "workspace", recibo["status"], recibo["output"], recibo=recibo)
        self.assertEqual(t.status, "completed")

    def test_ferramenta_errada_nao_pula_etapa(self):
        chave = ("tui", "local", "")
        task_state.iniciar_ou_continuar(
            chave, "crie o arquivo x e depois execute o programa"
        )
        t = task_state.registrar_ferramenta(chave, "execute_command", "error", "não executado: ferramenta incompatível")
        self.assertEqual(t.etapas[0]["status"], "pending")
        self.assertEqual(t.etapas[1]["status"], "pending")

    def test_mensagem_curta_nova_nao_vira_continuacao_automaticamente(self):
        chave = ("tui", "local", "")
        task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        t2 = task_state.iniciar_ou_continuar(chave, "pesquise novidades")
        self.assertIsNotNone(t2)
        self.assertEqual(t2.objetivo, "pesquise novidades")
        self.assertEqual(task_state.carregar(chave).status, "active")

    def test_continuacao_explica_e_reabre_tarefa_concluida(self):
        chave = ("tui", "local", "")
        task_state.iniciar_ou_continuar(chave, "abra o Firefox")
        task_state.registrar_ferramenta(chave, "abrir_aplicativo", "success", "ok")
        t = task_state.iniciar_ou_continuar(chave, "agora abra o YouTube")
        self.assertIsNotNone(t)
        self.assertGreaterEqual(len(t.etapas), 2)

    def test_falha_fica_registrada_e_nao_vira_sucesso(self):
        chave = ("tui", "local", "")
        t = task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        t = task_state.registrar_ferramenta(chave, "workspace", "error", "sem permissao")
        self.assertEqual(t.etapas[0]["status"], "pending")
        self.assertEqual(t.status, "active")
        self.assertEqual(t.ultimo_resultado, "sem permissao")
        self.assertEqual(t.etapas[0]["ferramentas_executadas_lista"], [])

    def test_recibo_ausente_mantem_verificacao_conservadora(self):
        chave = ("tui", "legado", "")
        task_state.iniciar_ou_continuar(chave, "execute o programa")
        recibo = dispatch.executar_resultado("execute_command", {"command": "printf ok", "diretorio": self.tmp.name})
        self.assertTrue(recibo["ok"])
        task_state.registrar_ferramenta(chave, "execute_command", recibo["status"], recibo["output"])
        self.assertEqual(task_state.proxima_operacao(chave)["ferramenta"], "ver_comando")

    def test_recibo_de_outra_operacao_nao_dispensa_verificacao(self):
        chave = ("tui", "recibo-incompativel", "")
        task_state.iniciar_ou_continuar(chave, "execute o programa")
        executado = dispatch.executar_resultado("execute_command", {"command": "printf ok", "diretorio": self.tmp.name})
        self.assertTrue(executado["ok"])
        recibo = dispatch.executar_resultado("get_system_time", {})
        task_state.registrar_ferramenta(chave, "execute_command", executado["status"], executado["output"], recibo=recibo)
        self.assertEqual(task_state.proxima_operacao(chave)["ferramenta"], "ver_comando")

    def test_recibo_incompleto_ou_divergente_nao_dispensa_verificacao(self):
        for field, value in (("output", "outro resultado"), ("status", "error"), ("requires_verification", None)):
            with self.subTest(field=field):
                chave = ("tui", "recibo-"+field, "")
                task_state.iniciar_ou_continuar(chave, "execute o programa")
                executado = dispatch.executar_resultado("execute_command", {"command": "printf ok", "diretorio": self.tmp.name})
                self.assertTrue(executado["ok"])
                divergente = {**executado, field: value}
                task_state.registrar_ferramenta(chave, "execute_command", executado["status"], executado["output"], recibo=divergente)
                self.assertEqual(task_state.proxima_operacao(chave)["ferramenta"], "ver_comando")


class IntentV18Tests(unittest.TestCase):
    def test_microfone_atalho(self):
        i = intent.interpretar("mude meu atalho do microfone para ctrl+alt+m")
        self.assertEqual(i.ferramenta_principal, "definir_atalho_microfone")
        self.assertEqual(i.parametros_sugeridos["atalho"], "ctrl+alt+m")

    def test_silencio(self):
        i = intent.interpretar("fique em silencio")
        self.assertEqual(i.ferramenta_principal, "definir_modo_silencioso")
        self.assertTrue(i.parametros_sugeridos["silencioso"])
        i = intent.interpretar("pode falar de novo")
        self.assertFalse(i.parametros_sugeridos["silencioso"])

    def test_execucao(self):
        i = intent.interpretar("execute o programa")
        self.assertEqual(i.ferramenta_principal, "execute_command")

    def test_browser_mesma_aba(self):
        i = intent.interpretar("avance na mesma aba")
        self.assertEqual(i.ferramenta_principal, "browser_avancar")

    def test_maps_local(self):
        i = intent.interpretar("abra o Google Maps em Praça Mauá, Rio de Janeiro")
        self.assertEqual(i.ferramenta_principal, "browser_abrir")
        self.assertIn("maps/search", i.parametros_sugeridos["url"])


class TrustAndUITests(V18Base):
    def test_nova_pessoa_tem_confianca_baixa(self):
        p = people.identificar(nome="Visitante", canal="discord", canal_id="123")
        self.assertLessEqual(float(p["confianca"]), 0.10)

    def test_externo_nao_pode_alterar_maquina(self):
        visitante = {"id": "p-1", "nome": "Visitante", "confianca": 0.10}
        ok, _ = people.pode_usar_ferramenta("write_file", "discord", visitante)
        self.assertFalse(ok)
        ok, _ = people.pode_usar_ferramenta("criar_ferramenta", "discord", visitante)
        self.assertFalse(ok)
        ok, _ = people.pode_usar_ferramenta("abrir_aplicativo", "discord", visitante)
        self.assertFalse(ok)

    def test_discord_pode_responder_no_fio_atual(self):
        visitante = {"id": "p-1", "nome": "Visitante", "confianca": 0.10}
        ok, _ = people.pode_usar_ferramenta("discord_enviar", "discord", visitante, "")
        self.assertTrue(ok)
        ok, _ = people.pode_usar_ferramenta("discord_enviar", "discord", visitante, "outro")
        self.assertFalse(ok)

    def test_silencio_persistente(self):
        self.assertFalse(user_modes.silencioso())
        user_modes.definir_silencioso(True)
        self.assertTrue(user_modes.silencioso())
        user_modes.definir_silencioso(False)
        self.assertFalse(user_modes.silencioso())

    def test_bindings_ui_simplificados(self):
        text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        bindings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Binding":
                vals = [ast.literal_eval(a) for a in node.args]
                bindings.append(vals)
        actions = {x[1]: x for x in bindings}
        self.assertIn("minecraft_toggle", actions)
        self.assertIn("discord_toggle", actions)
        for removed in {"microfone", "toggle_silencio", "minecraft_stop", "discord_service",
                        "minecraft_service", "testar_voz", "encerrar_integracoes"}:
            self.assertNotIn(removed, actions)
        self.assertEqual(sum(1 for x in bindings if x[1] == "minecraft_toggle"), 1)
        self.assertEqual(sum(1 for x in bindings if x[1] == "discord_toggle"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
