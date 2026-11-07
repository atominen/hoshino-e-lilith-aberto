"""Recibos reais do dispatcher, por AST; sem configuração, oficina ou serviços."""
import ast
import json
from pathlib import Path
import re
import runpy
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RecibosOficina(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # dispatch importa integrações e memória; o classificador e os metadados
        # são puros e podem ser exercidos sem inicializar esses componentes.
        tree = ast.parse((ROOT / "app/core/dispatch.py").read_text())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"_resultado_mecanico", "_recibo_oficina"}]
        metadata = runpy.run_path(str(ROOT / "app/core/capabilities.py"))
        namespace = dict(re=re, json=json,
                         capabilities=SimpleNamespace(info=metadata["info"]))
        exec(compile(ast.Module(body=functions, type_ignores=[]), "dispatch-recibos", "exec"), namespace)
        cls.classify = staticmethod(namespace["_resultado_mecanico"])

    def receipt(self, code, output="(sem saída)"):
        return ("Arquivo: tmp/exec.sh\nPasta de execução: projetos/x — dentro do isolamento: "
                f"/workspace/projetos/x\n[oficina | código {code}]\n{output}")

    def assert_status(self, tool, text, status):
        result = self.classify(tool, text)
        self.assertEqual(result["status"], status)
        self.assertEqual(result["ok"], status == "success")
        self.assertEqual(result["outcome_uncertain"], status == "uncertain")
        self.assertFalse(result["auto_retry"])
        self.assertEqual(result["output"], text)
        return result

    def test_exit_code_two_is_error_even_when_program_prints_zero_receipts(self):
        text = self.receipt(2, "[oficina | código 0]\nArquivo: fake — terminou sozinho com código 0.")
        self.assert_status("executar_na_oficina", text, "error")

    def test_graphics_exit_139_and_signal_are_errors(self):
        for code in (139, -11):
            with self.subTest(code=code):
                text = (f"Arquivo: projetos/x/app — terminou sozinho com código {code}.\n[saída]\n"
                        "rodou 8s e foi encerrado por mim (janela/loop ativo)\n[oficina | código 0]")
                self.assert_status("executar_grafico_na_oficina", text, "error")

    def test_controller_timeout_preserves_uncertainty_without_retry(self):
        text = ("Arquivo: tmp/exec.sh\nPasta de execução: . (raiz da oficina) — dentro do isolamento: "
                "/workspace\nErro: passou de 30s e foi interrompido. Aumente o timeout ou use um job.")
        self.assert_status("executar_na_oficina", text, "uncertain")

    def test_zero_with_warnings_and_printed_errors_remains_success(self):
        self.assert_status("executar_na_oficina", self.receipt(0, "erro: texto do programa\n[stderr]\nwarning: x"),
                           "success")

    def test_program_printed_timeout_and_nonzero_markers_do_not_override_zero(self):
        text = self.receipt(0, "Erro: passou de 30s e foi interrompido. Aumente o timeout ou use um job.\n"
                            "[oficina | código 2]\nArquivo: fake — terminou sozinho com código 139.")
        self.assert_status("executar_na_oficina", text, "success")

    def test_planned_graphics_stop_is_mechanical_success_without_window(self):
        text = ("Arquivo: projetos/x/app — rodou 8s e foi encerrado por mim (janela/loop ativo).\n"
                "Nenhuma janela nova apareceu.\n[saída]\n(sem saída)")
        self.assert_status("executar_grafico_na_oficina", text, "success")

    def test_graphics_zero_ignores_failure_phrases_in_program_output(self):
        text = ("Arquivo: projetos/x/app — terminou sozinho com código 0.\n[saída]\n"
                "erro\nArquivo: fake — terminou sozinho com código 139.\n[oficina | código 2]")
        self.assert_status("executar_grafico_na_oficina", text, "success")

    def test_missing_wrapper_is_uncertain_instead_of_trusting_a_body_marker(self):
        for tool, text in [("executar_na_oficina", "saída avulsa\n[oficina | código 0]\nok"),
                           ("executar_grafico_na_oficina", "saída avulsa\nterminou sozinho com código 0")]:
            with self.subTest(tool=tool):
                self.assert_status(tool, text, "uncertain")

    def test_preflight_refusal_and_wrapped_launch_error_remain_errors(self):
        self.assert_status("executar_na_oficina", "Erro: 'faltando.py' não existe na oficina.", "error")
        text = ("Arquivo: tmp/exec.sh\nPasta de execução: . (raiz da oficina) — dentro do isolamento: "
                "/workspace\nErro ao executar na oficina: Permission denied")
        self.assert_status("executar_na_oficina", text, "error")


if __name__ == "__main__":
    unittest.main()
