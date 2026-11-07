"""Oficina gráfica (pedido humano 29/10): GPU e janela só na execução gráfica, sob lease.

Não abre janela nem usa GPU: o sandbox, o lease e o X11 são substituídos por
dublês; a compilação C++ real roda no isolamento normal da oficina.
"""
import contextlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import workspace


class OficinaGrafica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(workspace, "OFICINA", Path(self.tmp.name))
        self.patch.start()
        workspace.preparar_oficina()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_gpu_e_display_so_na_execucao_grafica(self):
        cwd = workspace.OFICINA / "projetos"
        with patch.object(workspace, "_tem_bubblewrap", return_value=True), \
             patch.object(workspace, "_x11", return_value=(":0", "/home/x/.Xauthority")), \
             patch("os.path.isdir", return_value=True):
            normal = workspace._montar_chamada(["true"], cwd, sem_rede=True)
            grafica = workspace._montar_chamada(["true"], cwd, sem_rede=True, grafico=True)
        self.assertNotIn("/dev/dri", normal)
        # Lista de pacotes visível (só leitura): dpkg -l não pode mentir que nada está instalado.
        self.assertEqual(normal[normal.index("/var/lib/dpkg") - 1], "--ro-bind-try")
        self.assertIn("--dev-bind", grafica)
        self.assertEqual(grafica[grafica.index("--dev-bind") + 1], "/dev/dri")
        self.assertIn("/tmp/.X11-unix", grafica)
        self.assertIn(workspace._XAUTH_NO_SANDBOX, grafica)
        # O /tmp privado vem antes do socket X: senão o tmpfs esconderia o socket.
        self.assertLess(grafica.index("--tmpfs"), grafica.index("/tmp/.X11-unix"))
        with patch.object(workspace, "_tem_bubblewrap", return_value=False):
            with self.assertRaises(PermissionError):
                workspace._montar_chamada(["true"], cwd, sem_rede=True, grafico=True)

    def _executavel(self):
        alvo = workspace.OFICINA / "projetos" / "app"
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text("#!/bin/sh\n")
        alvo.chmod(0o755)
        return "projetos/app"

    def _rodar(self, janelas, exibida):
        class Processo:
            def __init__(self, *a, **k):
                self.encerrado = False
            def wait(self, timeout=None):
                if not self.encerrado:
                    raise subprocess.TimeoutExpired("app", timeout)
                return -15
            def terminate(self):
                self.encerrado = True
            kill = terminate
        leases = []

        @contextlib.contextmanager
        def lease(owner, **kw):
            leases.append((owner, kw))
            yield {"backend": "gpu"}
        capturas = []
        with patch.object(workspace, "_montar_chamada", return_value=["bwrap", "--", "app"]), \
             patch.dict("os.environ", {"DISPLAY": ":0"}), \
             patch("core.gpu_resource.lease", side_effect=lease), \
             patch.object(workspace.subprocess, "Popen", Processo), \
             patch.object(workspace, "_janelas_x11", side_effect=janelas), \
             patch.object(workspace, "_janela_exibida", return_value=exibida), \
             patch.object(workspace, "_capturar_janela",
                          side_effect=lambda j, c, d: capturas.append(d) or "320x200"):
            saida = workspace.executar_grafico_na_oficina(self._executavel(), segundos=2)
        return saida, leases, capturas

    def test_roda_sob_lease_captura_janela_nova_e_encerra(self):
        saida, leases, capturas = self._rodar([{"0x1": "terminal"}, {"0x1": "terminal", "0x2": "buraco"}],
                                              {"left": 0, "top": 0, "width": 320, "height": 200})
        self.assertEqual(leases[0][0], "batch")
        self.assertEqual(leases[0][1]["vram_bytes"], workspace.GRAFICO_VRAM_MB * 1024 * 1024)
        self.assertFalse(leases[0][1]["cpu_fallback"])
        self.assertEqual(len(capturas), 1)
        self.assertIn("encerrado por mim", saida)
        self.assertIn("janela 'buraco'", saida)

    def test_janela_nao_exibida_nao_vira_captura_falsa(self):
        # 29/10: monitor em espera; o wmctrl listava a janela, mas a captura saía de outra coisa.
        saida, _, capturas = self._rodar([{}, {"0x2": "buraco"}], None)
        self.assertEqual(capturas, [])
        self.assertIn("não a está exibindo", saida)

    def test_recusa_arquivo_inexistente_ou_fora_da_oficina(self):
        self.assertIn("não existe", workspace.executar_grafico_na_oficina("projetos/nada"))
        self.assertTrue(workspace.executar_grafico_na_oficina("../fora").startswith("Erro"))
        self.assertTrue(workspace.observar_imagem_da_oficina("../fora.png").startswith("Erro"))

    def test_leitura_por_linhas_numeradas(self):
        workspace.escrever_na_oficina("projetos/a.cpp", "\n".join(f"linha {n}" for n in range(1, 21)))
        trecho = workspace.ler_da_oficina("projetos/a.cpp", inicio=4, fim=6)
        self.assertIn("linhas 4–6 de 20", trecho)
        self.assertIn("    5| linha 5", trecho)
        self.assertNotIn("linha 7", trecho)

    def test_codigo_avulso_roda_na_raiz_e_informa_a_pasta(self):
        # 29/10: rodava em tmp/ e 'projetos/...' não existia; ela repetiu o g++ sem saber a pasta.
        workspace.escrever_na_oficina("projetos/p/main.txt", "conteudo")
        saida = workspace.executar_na_oficina(codigo="cat projetos/p/main.txt", linguagem="bash")
        self.assertIn("Pasta de execução: . (raiz da oficina) — dentro do isolamento: /workspace", saida)
        self.assertIn("conteudo", saida)
        no_projeto = workspace.executar_na_oficina(codigo="cat main.txt", linguagem="bash", projeto="p")
        self.assertIn("Pasta de execução: projetos/p — dentro do isolamento: /workspace/projetos/p", no_projeto)
        self.assertIn("conteudo", no_projeto)
        self.assertEqual(sorted(p.name for p in (workspace.OFICINA / "projetos" / "p").iterdir()), ["main.txt"])
        # Caminho com projetos/ na frente vale; pasta inexistente é recusada antes de rodar.
        self.assertIn("conteudo", workspace.executar_na_oficina(codigo="cat main.txt", linguagem="bash", projeto="projetos/p"))
        faltando = workspace.executar_na_oficina(codigo="echo x", linguagem="bash", projeto="projetos/p/build")
        self.assertIn("projetos/p/build não existe; nada foi executado", faltando)
        # cd inicial válido só a partir da raiz: roda da raiz (o cd diz onde ela quer estar).
        dobrado = workspace.executar_na_oficina(codigo="cd projetos/p && cat main.txt", linguagem="bash", projeto="p")
        self.assertIn("Pasta de execução: . (raiz da oficina)", dobrado)
        self.assertIn("conteudo", dobrado)

    @unittest.skipUnless(shutil.which("g++") and shutil.which("glslangValidator"), "g++/glslang ausentes")
    def test_problemas_como_no_editor_e_ao_salvar(self):
        # Pedido humano 29/10: avisos de compilação/estilo/shader como no VS Code, sem executar nada.
        from tools import code_check
        salvo = workspace.escrever_na_oficina("projetos/x/main.cpp", "int main() { int x; return y; }\n")
        self.assertIn("Verificação ao salvar: 1 erro(s)", salvo)
        self.assertIn("projetos/x/main.cpp:1:28: erro", salvo)
        # Erro do código dela vem antes de erros que o compilador aponta em cabeçalhos do sistema.
        with patch.object(code_check, "_gcc", return_value=[
                {"arq": "/usr/include/c++/13/bits/chrono.h", "l": 515, "c": 44, "sev": "erro", "msg": "x", "ferramenta": "g++"},
                {"arq": "projetos/x/main.cpp", "l": 78, "c": 5, "sev": "erro", "msg": "y", "ferramenta": "g++"}]):
            primeiro = code_check.problemas(workspace.OFICINA / "projetos/x/main.cpp", completo=False)["problemas"][0]
        self.assertEqual(primeiro["arq"], "projetos/x/main.cpp")
        workspace.escrever_na_oficina("projetos/x/geo.comp", "#version 430\nvoid main(){ float a = 1.0 }\n")
        painel = code_check.verificar_codigo("projetos/x")
        self.assertIn("projetos/x/geo.comp:2:0: erro", painel)
        self.assertIn("unused variable", painel)
        self.assertRegex(painel, r"^Problemas em projetos/x: 2 erro\(s\)")
        self.assertIn("Nenhum arquivo de código", code_check.verificar_codigo("capturas"))
        self.assertTrue(code_check.verificar_codigo("../fora").startswith("Erro"))
        self.assertEqual(workspace.escrever_na_oficina("projetos/x/notas.md", "oi").count("Verificação"), 0)
        # Cabeçalho: verificado pelos .cpp que o incluem, erros do próprio .h primeiro.
        self.assertIn("nenhum .cpp do projeto inclui", workspace.escrever_na_oficina("projetos/x/solto.h", "int a;\n"))
        workspace.escrever_na_oficina("projetos/x/usa.cpp", '#include "eng.h"\nint main() { return f(); }\n')
        salvo_h = workspace.escrever_na_oficina("projetos/x/eng.h", "#pragma once\nGLuint f();\n")
        self.assertIn("projetos/x/eng.h:2:1: erro", salvo_h.split("\n")[2])
        self.assertRegex(code_check.verificar_codigo("projetos/x/eng.h"), r"^Problemas em projetos/x/eng.h: [1-9]\d* erro")
        # Cadeia de inclusão e definição anterior entram na mensagem (redefinição por include duplo).
        saida = ("In file included from /workspace/projetos/x/main.cpp:72:\n"
                 "/workspace/projetos/x/e.h:6:8: error: redefinition of 'struct A'\n"
                 "In file included from /workspace/projetos/x/main.cpp:1:\n"
                 "/workspace/projetos/x/e.h:6:8: note: previous definition of 'struct A'\n")
        prob = code_check._problemas_gcc(saida, "g++")
        self.assertEqual(len(prob), 1)
        self.assertIn("(incluído de projetos/x/main.cpp:72)", prob[0]["msg"])
        self.assertIn("definição anterior: projetos/x/e.h:6 (incluído de projetos/x/main.cpp:1)", prob[0]["msg"])
        formatado = code_check.verificar_codigo("projetos/x/main.cpp", formatar=True)
        if code_check.CLANG_FORMAT.is_file():
            self.assertIn("formatado agora", formatado)
            self.assertNotIn("estilo fora do padrão", formatado)

    @unittest.skipUnless(shutil.which("g++"), "g++ ausente")
    def test_verificacao_nao_le_arquivo_de_fora_da_oficina(self):
        # O compilador roda no isolamento: um include da máquina não traz o conteúdo para a mensagem.
        from tools import code_check
        with tempfile.NamedTemporaryFile("w", suffix=".h", delete=False) as segredo:
            segredo.write("SEGREDO_DO_HOST 123\n")
        try:
            workspace.escrever_na_oficina("projetos/y/a.cpp", f'#include "{segredo.name}"\nint main(){{}}\n')
            painel = code_check.verificar_codigo("projetos/y")
            self.assertNotIn("SEGREDO_DO_HOST", painel)
            self.assertIn("erro", painel)
        finally:
            Path(segredo.name).unlink()

    @unittest.skipUnless(shutil.which("g++"), "g++ ausente")
    def test_cpp_compila_e_roda_na_oficina(self):
        codigo = '#include <cstdio>\nint main(){std::printf("ola %d\\n", 6*7);return 0;}\n'
        saida = workspace.executar_na_oficina(codigo=codigo, linguagem="cpp", timeout=120)
        self.assertIn("ola 42", saida)
        self.assertIn("código 0", saida)
        erro = workspace.executar_na_oficina(codigo="int main(){ return x; }\n", linguagem="cpp", timeout=120)
        self.assertIn("error", erro)


# ---------------------------------------------------------------------------
# Listagem da oficina: fixtures de arquivos vazios, sem serviços ou compilação.
# ---------------------------------------------------------------------------
class ListagemOficina(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        oficina = Path(self.tmp.name)
        self.patch = patch.object(workspace, "OFICINA", oficina)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.projeto = oficina / "projetos" / "ensaio_listagem"
        self.projeto.mkdir(parents=True)

    def test_artefatos_cmake_nao_escondem_fonte_na_raiz(self):
        internos = self.projeto / "build" / "CMakeFiles"
        internos.mkdir(parents=True)
        for numero in range(450):
            (internos / f"gerado_{numero:03}.txt").touch()
        (self.projeto / "main.cpp").touch()

        saida = workspace.listar_oficina("projetos/ensaio_listagem")

        self.assertIn("projetos/ensaio_listagem/main.cpp", saida)
        self.assertNotIn("CMakeFiles", saida)

    def test_internos_sao_ignorados_por_nome_de_pasta(self):
        for nome in ("CMakeFiles", "__pycache__", ".git", "browser_profile", "venv"):
            pasta = self.projeto / nome
            pasta.mkdir()
            (pasta / "interno.txt").touch()
        (self.projeto / "browser_profile_notes.txt").touch()

        saida = workspace.listar_oficina("projetos/ensaio_listagem")

        for nome in ("CMakeFiles", "__pycache__", ".git", "browser_profile", "venv"):
            with self.subTest(nome=nome):
                self.assertNotIn(f"/{nome}/", saida)
        self.assertIn("browser_profile_notes.txt", saida)

    def test_pasta_interna_pedida_explicitamente_pode_ser_inspecionada(self):
        for nome in ("CMakeFiles", "__pycache__", ".git", "browser_profile", "venv"):
            with self.subTest(nome=nome):
                pasta = self.projeto / nome
                pasta.mkdir()
                (pasta / "metadado.txt").touch()

                saida = workspace.listar_oficina(f"projetos/ensaio_listagem/{nome}")

                self.assertIn(f"{nome}/metadado.txt", saida)

    def test_limite_conta_so_as_200_entradas_exibidas(self):
        internos = self.projeto / "CMakeFiles"
        internos.mkdir()
        for numero in range(450):
            (internos / f"gerado_{numero:03}.txt").touch()
        for numero in range(210):
            (self.projeto / f"visivel_{numero:03}.txt").touch()

        saida = workspace.listar_oficina("projetos/ensaio_listagem")

        self.assertEqual(len(saida.splitlines()) - 1, 200)
        self.assertIn("visivel_199.txt", saida)
        self.assertNotIn("visivel_200.txt", saida)
        self.assertNotIn("gerado_", saida)


if __name__ == "__main__":
    unittest.main()
