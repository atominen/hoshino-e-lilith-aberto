import ast
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import config
from memory.sqlite import init_db
from core import bd, dispatch, task_state, intent
from social import people
from tools import filesystem
from unittest.mock import patch


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config.DB_PATH = str(Path(self.tmp.name) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        init_db.init_database(verbose=False)
        task_state._SCHEMA_DONE = False

    def tearDown(self):
        self.tmp.cleanup()


class ContinuityV19(Base):
    def test_comando_de_retomada_nao_cria_etapa(self):
        chave = ("tui", "local", "")
        t = task_state.iniciar_ou_continuar(chave, "crie o arquivo x e depois execute o programa")
        before = len(t.etapas)
        t2 = task_state.iniciar_ou_continuar(chave, "continue a tarefa anterior a esta mensagem, nada aconteceu")
        self.assertEqual(len(t2.etapas), before)
        self.assertEqual(t2.etapas[0]["status"], "pending")
        self.assertEqual(task_state.eh_comando_retomada("continue a tarefa anterior a esta mensagem, nada aconteceu"), True)

    def test_retomada_entrega_ferramenta_pendente_ao_roteador(self):
        chave = ("tui", "local", "")
        task_state.iniciar_ou_continuar(chave, "crie o arquivo x e depois execute o programa")
        toolset = dispatch.esquemas("continue a tarefa anterior", ferramentas_prioritarias=task_state.ferramentas_pendentes(chave))
        nomes = {x["function"]["name"] for x in toolset}
        self.assertIn("workspace", nomes)
        self.assertFalse(nomes & dispatch.LEGADOS_ARQUIVOS)
        self.assertEqual(task_state.proxima_operacao(chave)["operacao"], "salvar")

    def test_repetir_etapa_pendente_nao_duplica(self):
        chave = ("tui", "local", "")
        t = task_state.iniciar_ou_continuar(chave, "crie o arquivo x e depois execute o programa")
        t2 = task_state.iniciar_ou_continuar(chave, "crie o arquivo x agora")
        self.assertEqual(t2.id, t.id)
        self.assertEqual(len(t2.etapas), 2)
        self.assertEqual(t2.etapas[0]["texto"], "crie o arquivo x agora")

    def test_apos_primeira_etapa_retomada_passa_para_proxima(self):
        chave = ("tui", "local", "")
        task_state.iniciar_ou_continuar(chave, "crie o arquivo x e depois execute o programa")
        self.assertEqual(task_state.ferramentas_pendentes(chave), ["workspace"])
        path = Path(self.tmp.name) / "x.txt"
        receipt = dispatch.executar_resultado("workspace", {"operacao": "salvar", "caminho": str(path), "conteudo": "x"})
        self.assertTrue(receipt["verified"])
        self.assertEqual(path.read_text(), "x")
        task_state.registrar_ferramenta(chave, "workspace", receipt["status"], receipt["output"])
        self.assertEqual(task_state.ferramentas_pendentes(chave), ["execute_command"])

    def test_tarefa_nao_expoe_etapa_futura_antes_da_hora(self):
        chave = ("tui", "local", "")
        task_state.iniciar_ou_continuar(chave, "crie o arquivo x e depois execute o programa")
        prioridades = task_state.ferramentas_pendentes(chave)
        self.assertEqual(prioridades, ["workspace"])
        schemas = dispatch.esquemas("tarefa em andamento", ferramentas_prioritarias=prioridades)
        nomes = {x["function"]["name"] for x in schemas}
        self.assertIn("workspace", nomes)
        self.assertFalse(nomes & dispatch.LEGADOS_ARQUIVOS)
        # A leitura/verificação é suboperação de workspace; o comando futuro
        # não deve ser antecipado ao LLM.
        self.assertNotIn("execute_command", nomes)

    def test_mesma_aba_nao_abre_outra(self):
        i = intent.interpretar("abra o YouTube na mesma aba")
        self.assertEqual(i.ferramenta_principal, "browser_abrir")
        self.assertFalse(i.parametros_sugeridos["nova_aba"])

    def test_atalho_mic_alias(self):
        i = intent.interpretar("mude meu atalho do mic para F2")
        self.assertEqual(i.ferramenta_principal, "definir_atalho_microfone")
        self.assertEqual(i.parametros_sugeridos["atalho"], "f2")

    def test_conversa_nao_aumenta_confianca(self):
        p = people.identificar(nome="Visitante", canal="discord", canal_id="123")
        antes = float(p["confianca"])
        p2 = people.registrar_evento(p["id"], "conversa", "falamos")
        self.assertAlmostEqual(float(p2["confianca"]), antes, places=6)
        self.assertGreater(float(p2["familiaridade"]), float(p["familiaridade"]))


    def test_reset_total_remove_pessoas_preserva_identidade_estatica(self):
        from tools import memory_admin
        p = people.identificar(nome="Contato", canal="discord", canal_id="123")
        self.assertIsNotNone(p)
        identity = Path(config.SELF_MODEL_PATH).read_bytes()
        with patch.object(memory_admin, "DB_PATH", config.DB_PATH):
            memory_admin.wipe_persistent_memory()
            self.assertEqual(memory_admin.memoria_restante(), "")
        depois = people.identificar(nome="Contato", criar=False)
        self.assertIsNone(depois)
        self.assertEqual(Path(config.SELF_MODEL_PATH).read_bytes(), identity)

    def test_repetir_leitura_preserva_tarefa_e_etapas(self):
        chave = ("tui", "repetir-leitura", "")
        t = task_state.iniciar_ou_continuar(chave, "leia o arquivo x e depois execute o programa")
        t2 = task_state.iniciar_ou_continuar(chave, "leia o arquivo x novamente")
        self.assertEqual(t2.id, t.id)
        self.assertEqual(len(t2.etapas), 2)

    def test_leitura_nao_substitui_escrita_pendente(self):
        chave = ("tui", "suboperacao", "")
        t = task_state.iniciar_ou_continuar(chave, "crie o arquivo x e depois execute o programa")
        t2 = task_state.iniciar_ou_continuar(chave, "leia o arquivo x")
        self.assertNotEqual(t2.id, t.id)
        self.assertEqual(task_state.proxima_operacao(chave)["operacao"], "ler")
        self.assertEqual(bd.um("SELECT status FROM conversation_tasks WHERE id=?", (t.id,))["status"], "paused")

    def test_anexar_nao_substitui_escrita_pendente(self):
        chave = ("tui", "modo-escrita", "")
        t = task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        t2 = task_state.iniciar_ou_continuar(chave, "adicione conteúdo ao arquivo x")
        self.assertNotEqual(t2.id, t.id)
        self.assertEqual(task_state.proxima_operacao(chave)["modo"], "anexar")

    def test_tarefa_legada_dict_legivel_sem_migracao_cega(self):
        chave = ("tui", "legacy-dict", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        serializado = json.dumps([{"id": "antiga-1", "ferramenta": "write_file", "instrucao": "crie o arquivo x"}])
        bd.executar("UPDATE conversation_task_steps SET ferramenta=?, ferramentas=? WHERE id=?",
                    ("write_file", serializado, tarefa.etapas[0]["id"]))
        op = task_state.proxima_operacao(chave)
        self.assertEqual(op["ferramenta"], "workspace")
        self.assertEqual(op["operacao"], "salvar")
        self.assertEqual(op["operacao_id"], "antiga-1")
        self.assertEqual(bd.um("SELECT ferramentas FROM conversation_task_steps WHERE id=?", (tarefa.etapas[0]["id"],))["ferramentas"], serializado)

    def test_nome_legado_executado_nao_volta_a_ser_escrita_pendente(self):
        # Simula somente o formato persistido antigo; não afirma efeito externo.
        chave = ("tui", "legacy-executada", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        operacoes = [{"id": "escrita", "ferramenta": "write_file", "instrucao": "crie o arquivo x"},
                     {"id": "leitura", "ferramenta": "read_file", "instrucao": "leia o arquivo x"}]
        bd.executar("UPDATE conversation_task_steps SET ferramentas=?, ferramentas_executadas=? WHERE id=?",
                    (json.dumps(operacoes), json.dumps(["write_file"]), tarefa.etapas[0]["id"]))
        op = task_state.proxima_operacao(chave)
        self.assertEqual(op["operacao_id"], "leitura")
        self.assertEqual(op["ferramenta"], "workspace")
        self.assertEqual(op["operacao"], "ler")

    def test_nome_legado_de_leitura_nao_marca_escrita_como_executada(self):
        chave = ("tui", "legacy-suboperacao", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        bd.executar("UPDATE conversation_task_steps SET ferramentas=?, ferramentas_executadas=? WHERE id=?",
                    (json.dumps(["write_file", "read_file"]), json.dumps(["read_file"]), tarefa.etapas[0]["id"]))
        op = task_state.proxima_operacao(chave)
        self.assertEqual(op["operacao_id"], "legacy-1")
        self.assertEqual(op["operacao"], "salvar")
        self.assertEqual(task_state.carregar(chave).etapas[0]["ferramentas_executadas_lista"], ["legacy-2"])

    def test_lista_legada_nao_reexecuta_escrita_ja_registrada(self):
        chave = ("tui", "legacy-lista-escrita", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "crie o arquivo x")
        bd.executar("UPDATE conversation_task_steps SET ferramentas=?, ferramentas_executadas=? WHERE id=?",
                    (json.dumps(["write_file", "read_file"]), json.dumps(["write_file"]), tarefa.etapas[0]["id"]))
        op = task_state.proxima_operacao(chave)
        self.assertEqual(op["operacao_id"], "legacy-2")
        self.assertEqual(op["operacao"], "ler")
        self.assertEqual(task_state.carregar(chave).etapas[0]["ferramentas_executadas_lista"], ["legacy-1"])

    def test_ui_nao_exibe_controles_removidos(self):
        txt = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("[F7] silêncio", txt)
        self.assertNotIn("[F12] desconectar", txt)
        self.assertNotIn("[Ctrl+M] Minecraft", txt)
        self.assertNotIn("[Ctrl+V] testar voz", txt)
        self.assertIn("[CONTINUIDADE DO FIO]", (ROOT / "app" / "main.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
