"""Ciclo de projeto de programação (pedido humano 29/10): observar, uma ação pensada, checkpoint.

Sem modelo real: o modelo e a execução são dublês; banco e oficina temporários.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.chdir(ROOT)

import config  # noqa: E402
from memory.sqlite import init_db  # noqa: E402
from core import task_state, progress, project_agent  # noqa: E402
from tools import workspace  # noqa: E402

for mod_name, attrs in [
    ("textual", {}),
    ("textual.app", {"App": object, "ComposeResult": object}),
    ("textual.binding", {"Binding": lambda *a, **k: None}),
    ("textual.containers", {"Horizontal": object, "Vertical": object}),
    ("textual.widgets", {"Footer": object, "Header": object, "RichLog": object, "TextArea": object, "Static": object}),
]:
    mod = types.ModuleType(mod_name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[mod_name] = mod

import main  # noqa: E402

OBJETIVO = ("Projeto: crie um programa C++ que imprime uma tabela de quadrados, compile, execute e "
            "entregue as instruções.")


def _ambiente(td):
    config.DB_PATH = str(Path(td) / "h.db")
    init_db.DB_PATH = config.DB_PATH
    task_state._SCHEMA_DONE = False
    init_db.init_database(verbose=False)
    return patch.object(workspace, "OFICINA", Path(td) / "oficina")


def _app(respostas, execucoes):
    app = object.__new__(main.InterfaceHoshino)
    app._fila_chaves, app._saidas_por_conversa, app._locks_saida = {}, {}, {}
    vistos = []

    async def chamar_modelo(mensagens, ferramentas=None, **kwargs):
        vistos.append(json.loads(mensagens[-1]["content"]) if mensagens[-1]["role"] == "user"
                      and mensagens[-1]["content"].startswith("{") else mensagens[-1]["content"])
        item = respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        nome, args = item
        if nome is None:
            return {"content": args, "tool_calls": []}
        return {"content": "nota curta", "tool_calls": [{"function": {"name": nome, "arguments": args}}]}

    async def executar(chamadas, frame, passo, *a, **k):
        nome = chamadas[0]["function"]["name"]
        args = chamadas[0]["function"]["arguments"]
        saida = execucoes(nome, args)
        return [(nome, args, {"ok": not saida.startswith("Erro"), "status": "success", "output": saida,
                              "receipt_id": f"tool-{passo}"})]
    app.chamar_modelo = chamar_modelo
    app._executar_chamadas_da_etapa = executar
    return app, vistos


def test_marcador_e_pasta_do_projeto():
    assert project_agent.is_project(OBJETIVO)
    assert project_agent.is_project("  projeto: algo")
    assert not project_agent.is_project("Crie um pequeno programa C++ na sua oficina")
    assert project_agent._slug(OBJETIVO) == "crie_um_programa_c"
    assert project_agent._slug("Projeto: desenvolva sua própria simulação") == "desenvolva_sua_propria_simulacao"


def _incompleta(parcial=""):
    exc = RuntimeError("LLM_STREAM_INCOMPLETO: erro de protocolo/backend.")
    exc.partial_thinking = parcial
    return exc


def test_decisao_incompleta_do_backend_nao_derruba_o_projeto():
    # 29/10: saída no limite no meio da tool call virou quadro de erro do Ollama e o turno caiu.
    with tempfile.TemporaryDirectory() as td, _ambiente(td):
        chave = ("local", "projeto-4", "")
        tarefa = task_state.iniciar_ou_continuar(chave, OBJETIVO)
        executadas = []
        respostas = [_incompleta("Vou listar a pasta primeiro."),         # conclui com o raciocínio parcial
                     ("listar_oficina", {"subpasta": "projetos"}),
                     _incompleta(), _incompleta(), _incompleta()]          # sem parcial: 3 seguidas pausam
        app, vistos = _app(respostas, lambda n, a: executadas.append(n) or "ok")
        progress.limpar()
        texto, _ = asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local"))
        assert executadas == ["listar_oficina"]
        assert "três decisões seguidas não terminaram" in texto
        assert task_state.status_id(tarefa.id) == "paused"
        assert any("O tempo de pensar deste passo acabou" in str(v) for v in vistos)


def test_conclusao_so_depois_de_execucao_bem_sucedida_posterior_a_mudanca():
    with tempfile.TemporaryDirectory() as td, _ambiente(td):
        chave = ("local", "projeto-1", "")
        tarefa = task_state.iniciar_ou_continuar(chave, OBJETIVO)
        pasta = "projetos/" + project_agent._slug(OBJETIVO)
        arquivo = pasta + "/main.cpp"

        def execucoes(nome, args):
            if nome == "escrever_na_oficina":
                return workspace.escrever_na_oficina(args["caminho"], args["conteudo"])
            if nome == "executar_na_oficina":
                if args.get("codigo", "").startswith("g++"):
                    return "Arquivo: x\n[oficina | código 0]\n(sem saída)"  # só compilou
                return "Arquivo: x\n[oficina | código 0]\n1 1\n2 4"
            return "Erro: inesperado"
        respostas = [
            ("anotar_plano", {"passos": ["escrever main.cpp", "compilar"], "nota": "tabela de 1 a 5"}),
            ("escrever_na_oficina", {"caminho": arquivo, "conteudo": "int main(){}\n"}),
            ("concluir_projeto", {"resumo": "r", "como_executar": "c", "limitacoes": "l"}),  # cedo demais
            ("executar_na_oficina", {"codigo": "g++ main.cpp", "linguagem": "bash"}),  # compilar não basta
            ("concluir_projeto", {"resumo": "r", "como_executar": "c", "limitacoes": "l"}),
            ("executar_na_oficina", {"arquivo": arquivo, "linguagem": "cpp"}),
            ("executar_na_oficina", {"arquivo": arquivo, "linguagem": "cpp"}),  # repetição sem mudança
            ("concluir_projeto", {"resumo": "Tabela feita e testada.", "como_executar": "g++ main.cpp",
                                  "limitacoes": "nenhuma"}),
        ]
        app, vistos = _app(respostas, execucoes)
        progress.limpar()
        texto, usados = asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local"))
        assert "Tabela feita e testada." in texto and "g++ main.cpp" in texto
        assert usados == ["escrever_na_oficina", "executar_na_oficina", "executar_na_oficina"]
        assert task_state.status_id(tarefa.id) == "completed"
        cp = project_agent.load(tarefa)
        assert [e["ok"] for e in cp["events"]] == [True, True, False, True, False, True, False, True]
        assert "Ainda não houve execução" in cp["events"][2]["saida"]
        assert "compilar sem saída não basta" in cp["events"][4]["saida"]
        assert "nada mudou" in cp["events"][6]["saida"]
        # A visão mostra o plano dela, os arquivos e o conteúdo escrito resumido, não repetido.
        ultimo = vistos[-1]["projeto_atual"]
        assert ultimo["meu_plano"]["passos"][0] == "escrever main.cpp"
        assert ultimo["arquivos"][0]["arquivo"] == arquivo
        assert any(r["argumentos"].get("conteudo") == "int main(){}\n" or "caracteres" in str(r["argumentos"])
                   for r in ultimo["ultimos_recibos"] if r["ferramenta"] == "escrever_na_oficina")


def test_sem_chamada_pausa_e_decisao_humana_pausa_com_pergunta():
    with tempfile.TemporaryDirectory() as td, _ambiente(td):
        chave = ("local", "projeto-2", "")
        tarefa = task_state.iniciar_ou_continuar(chave, OBJETIVO)
        app, _ = _app([(None, "só texto")] * project_agent.SEM_ACAO_MAX, lambda n, a: "")
        progress.limpar()
        texto, _ = asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local"))
        assert "pausado" in texto and task_state.status_id(tarefa.id) == "paused"
        tarefa = task_state.iniciar_ou_continuar(chave, "continue")
        app, _ = _app([("pedir_decisao_humana", {"pergunta": "Posso usar GLEW?"})], lambda n, a: "")
        progress.limpar()
        texto, _ = asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local", retomar=True))
        assert "Posso usar GLEW?" in texto
        assert task_state.status_id(tarefa.id) == "paused"
        # A resposta (texto livre, não "continue") retoma o projeto e aparece na visão dela.
        tarefa = task_state.iniciar_ou_continuar(chave, "Pode usar GLEW, está instalado.")
        assert tarefa and project_agent.is_project(tarefa.objetivo)
        app, vistos = _app([(None, "só texto")] * project_agent.SEM_ACAO_MAX, lambda n, a: "")
        progress.limpar()
        asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local",
                                       entrada="Pode usar GLEW, está instalado.", pessoa="Gustavo"))
        visao = next(v for v in vistos if isinstance(v, dict))["projeto_atual"]
        assert visao["resposta_a_sua_pergunta"]["texto"] == "Pode usar GLEW, está instalado."
        assert not project_agent.aguardando_humano(tarefa)
        # "continue, …" com texto: mesma tarefa, objetivo intacto, texto visível como mensagem.
        objetivo = tarefa.objetivo
        aviso = "continue, deixei uma referência em dados/referencias/x.txt"
        tarefa = task_state.iniciar_ou_continuar(chave, aviso)
        assert tarefa.objetivo == objetivo
        app, vistos = _app([(None, "só texto")] * project_agent.SEM_ACAO_MAX, lambda n, a: "")
        progress.limpar()
        asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local", entrada=aviso))
        visao = next(v for v in vistos if isinstance(v, dict))["projeto_atual"]
        assert visao["mensagem_da_pessoa"]["texto"] == aviso


def test_ferramenta_fora_do_modo_projeto_e_recusada_antes_de_executar():
    with tempfile.TemporaryDirectory() as td, _ambiente(td):
        chave = ("local", "projeto-3", "")
        tarefa = task_state.iniciar_ou_continuar(chave, OBJETIVO)
        executadas = []
        app, _ = _app([("execute_command", {"command": "rm -rf /"})] + [(None, "")] * project_agent.SEM_ACAO_MAX,
                      lambda n, a: executadas.append(n) or "")
        progress.limpar()
        asyncio.run(app._ciclo_projeto(tarefa, chave_conversa=chave, canal="local"))
        assert executadas == []
        cp = project_agent.load(tarefa)
        assert "não está disponível no modo projeto" in cp["events"][0]["saida"]


def test_editar_na_oficina_troca_trecho_unico_e_recusa_ambiguo():
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        workspace.escrever_na_oficina("projetos/a.cpp", "int x = 1;\nint y = 1;\n")
        assert "Editado" in workspace.editar_na_oficina("projetos/a.cpp", "int x = 1;", "int x = 2;")
        assert "aparece 2 vezes" not in workspace.ler_da_oficina("projetos/a.cpp")
        assert "int x = 2;" in workspace.ler_da_oficina("projetos/a.cpp")
        workspace.escrever_na_oficina("projetos/b.cpp", "a\na\n")
        assert "aparece 2 vezes" in workspace.editar_na_oficina("projetos/b.cpp", "a", "b")
        falta = workspace.editar_na_oficina("projetos/a.cpp", "int  y = 1;", "z")
        assert "não aparece" in falta and "Nada foi alterado" in falta


def test_releitura_do_mesmo_arquivo_sem_mudanca_e_recusada():
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    project_agent.record(cp, "escrever_na_oficina", {"caminho": "p/a.cpp", "conteudo": "x"}, "Gravado", ok=True)
    project_agent.record(cp, "ler_da_oficina", {"caminho": "p/a.cpp"}, "x", ok=True)
    project_agent.record(cp, "ler_da_oficina", {"caminho": "p/a.cpp"}, "x", ok=True)
    assert "já leu esse mesmo trecho de p/a.cpp 2 vezes" in project_agent.releitura_excessiva(
        cp, "ler_da_oficina", {"caminho": "p/a.cpp"})
    # Ler as linhas do erro continua permitido (29/10: o arquivo inteiro aparecia cortado).
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp", "inicio": 80, "fim": 110}) is None
    # A quota não pode afirmar que um intervalo nunca mostrado já foi lido.
    salvo = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    project_agent.record(salvo, "escrever_na_oficina", {"caminho": "p/c.cpp", "conteudo": "x"},
                         "Gravado\nVerificação ao salvar: 1 erro(s), 0 aviso(s):\n  p/c.cpp:162:5: erro: ‘phi’ was not declared", ok=True)
    for inicio in (150, 158, 140, 150):
        project_agent.record(salvo, "ler_da_oficina", {"caminho": "p/c.cpp", "inicio": inicio, "fim": inicio + 20}, "x", ok=True)
    assert project_agent.releitura_excessiva(salvo, "ler_da_oficina", {"caminho": "p/c.cpp", "inicio": 100, "fim": 120}) is None
    aviso = project_agent.releitura_excessiva(salvo, "ler_da_oficina", {"caminho": "p/c.cpp", "inicio": 150, "fim": 170})
    assert "4 vezes (trechos diferentes)" in aviso and "p/c.cpp:162:5: erro" in aviso and "editar_na_oficina" in aviso
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/b.cpp"}) is None
    project_agent.record(cp, "editar_na_oficina", {"caminho": "p/a.cpp", "trecho": "x", "novo": "y"}, "Editado", ok=True)
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp"}) is None


def test_visao_mostra_a_leitura_mais_recente_quase_inteira():
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1, "pasta": "projetos/x", "plano": None}
    project_agent.record(cp, "ler_da_oficina", {"caminho": "p/a.cpp"}, "A" * 6000, ok=True)
    project_agent.record(cp, "ler_da_oficina", {"caminho": "p/b.cpp"}, "B" * 6000, ok=True)
    recibos = project_agent.view(cp, "Projeto: x", Path("/nao/existe"), 10)["projeto_atual"]["ultimos_recibos"]
    assert len(recibos[0]["saida"]) < 1300 and recibos[1]["saida"].count("B") == 6000


def test_editar_por_linhas_e_falha_mostra_o_texto_real():
    # 29/10: ela reconstruía o trecho de memória e errava; com a leitura bloqueada, ficava sem saída.
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        workspace.escrever_na_oficina("p/a.txt", "um\ndois\n    tres = x;\nquatro\n")
        falha = workspace.editar_na_oficina("p/a.txt", "  tres = y;\nquatro", "z")
        assert "Nada foi alterado" in falha and "    3|     tres = x;" in falha
        ok = workspace.editar_na_oficina("p/a.txt", novo="TRES\nTRES2", inicio=3, fim=3)
        assert "linhas 3–3 trocadas por 2" in ok and "tres = x" in ok
        assert workspace.ler_da_oficina("p/a.txt") == "um\ndois\nTRES\nTRES2\nquatro\n"
        assert "fora do arquivo" in workspace.editar_na_oficina("p/a.txt", novo="x", inicio=9, fim=9)
        # Trecho e linhas juntos: trecho exato vale; trecho errado cai para as linhas.
        assert "1 trecho trocado" in workspace.editar_na_oficina("p/a.txt", "um", "UM", inicio=2, fim=2)
        assert "linhas 2–2 trocadas" in workspace.editar_na_oficina("p/a.txt", "nao existe", "DOIS", inicio=2, fim=2)
        assert workspace.ler_da_oficina("p/a.txt").startswith("UM\nDOIS\n")
        # Só fim: do começo até fim; só inicio: de inicio até o fim do arquivo.
        assert "linhas 1–2 trocadas" in workspace.editar_na_oficina("p/a.txt", novo="A", fim=2)
        assert "linhas 2–4 trocadas" in workspace.editar_na_oficina("p/a.txt", novo="B", inicio=2)
        assert workspace.ler_da_oficina("p/a.txt") == "A\nB\n"
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    for _ in range(4):
        project_agent.record(cp, "ler_da_oficina", {"caminho": "p/a.cpp", "inicio": 1, "fim": 9}, "x", ok=True)
    project_agent.record(cp, "editar_na_oficina", {"caminho": "p/a.cpp", "trecho": "y", "novo": "z"}, "Erro", ok=False)
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp", "inicio": 1, "fim": 9}) is None


def test_codigo_do_projeto_aparece_numerado_na_visao():
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        workspace.escrever_na_oficina("projetos/x/main.cpp", "int main() {\n  return 0;\n}\n")
        workspace.escrever_na_oficina("projetos/x/build/lixo.cpp", "nao aparece\n")
        cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1, "pasta": "projetos/x", "plano": None}
        project_agent.record(cp, "ler_da_oficina", {"caminho": "projetos/x/main.cpp"}, "x" * 5000, ok=True)
        visao = project_agent.view(cp, "Projeto: x", Path(td), 10)["projeto_atual"]
        assert visao["codigo_do_projeto"]["projetos/x/main.cpp"].splitlines()[1] == "   2|   return 0;"
        assert not any("build" in a for a in visao["codigo_do_projeto"])
        assert "está completo e numerado em codigo_do_projeto" in visao["ultimos_recibos"][-1]["saida"]
        with patch.object(project_agent, "CODIGO_NA_VISAO", 10):
            assert "esboço" in project_agent.codigo_do_projeto(Path(td), "projetos/x")["projetos/x/main.cpp"]


def test_memoria_de_trabalho_primeiro_erro_e_janela_de_codigo():
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        grande = "".join(f"int f{i}() {{ return {i}; }}\n" for i in range(1, 301))
        workspace.escrever_na_oficina("projetos/x/a.cpp", grande)
        workspace.escrever_na_oficina("projetos/x/b.cpp", grande)
        os.utime(Path(td) / "projetos/x/b.cpp", (1, 1))  # b é o mais antigo: só esboço
        cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1, "pasta": "projetos/x", "plano": None}
        project_agent.record(cp, "verificar_codigo", {"caminho": "projetos/x"},
                             "Problemas em projetos/x: 1 erro(s), 0 aviso(s).\nprojetos/x/a.cpp:200:5: erro: boom [g++]",
                             ok=True, comment="O erro está no a.cpp; vou olhar a linha 200.")
        visao = project_agent.view(cp, "Projeto: x", Path(td), 10, raciocinio_anterior="pensei sobre a linha 200")
        p = visao["projeto_atual"]
        assert p["minhas_anotacoes"] == ["passo 1: O erro está no a.cpp; vou olhar a linha 200."]
        assert p["meu_raciocinio_no_passo_anterior"] == "pensei sobre a linha 200"
        assert p["primeiro_erro"]["arquivo"] == "projetos/x/a.cpp" and p["primeiro_erro"]["linha"] == 200
        assert ">> 200| int f200()" in p["primeiro_erro"]["linhas_em_volta"]
        assert p["codigo_do_projeto"]["projetos/x/a.cpp"].startswith("(linhas 150–249 de 300")
        assert "esboço" in p["codigo_do_projeto"]["projetos/x/b.cpp"]
        assert any("primeiro_erro" in a for a in p["alertas"])
        # Diagnóstico mais recente sem erro: sem primeiro_erro.
        project_agent.record(cp, "escrever_na_oficina", {"caminho": "projetos/x/a.cpp"},
                             "Gravado.\nVerificação ao salvar: nenhum erro ou aviso do compilador/validador.", ok=True)
        assert project_agent.view(cp, "Projeto: x", Path(td), 10)["projeto_atual"]["primeiro_erro"] is None


def test_ja_na_tela_e_onde_esta():
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        workspace.escrever_na_oficina("projetos/x/e.h", "#pragma once\nstruct Camera {\n  float fov;\n};\n")
        workspace.escrever_na_oficina("projetos/x/main.cpp", '#include "e.h"\nint main() {\n  Camera c;\n'
                                                             '  return 0;\n}\n')
        grande = "".join(f"int f{i}() {{ return {i}; }}\n" for i in range(1, 301))
        workspace.escrever_na_oficina("projetos/x/g.cpp", grande)
        cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1, "pasta": "projetos/x", "plano": None}
        visao = project_agent.view(cp, "Projeto: x", Path(td), 10)
        ler_e = ("ler_da_oficina", {"caminho": "projetos/x/e.h"})
        assert project_agent.ja_na_tela(visao, *ler_e, cp, Path(td)) is None  # primeira leitura passa
        assert "já está inteiro" in project_agent.ja_na_tela(visao, *ler_e, cp, Path(td))
        os.utime(Path(td) / "projetos/x/e.h", (5, 5))  # versão nova: passa de novo
        assert project_agent.ja_na_tela(visao, *ler_e, cp, Path(td)) is None
        assert project_agent.ja_na_tela(visao, "ler_da_oficina", {"caminho": "projetos/x/g.cpp", "inicio": 200},
                                        cp, Path(td)) is None
        assert project_agent.ja_na_tela(visao, "listar_oficina", {}, cp, Path(td)) is None
        saida = project_agent.onde_esta(Path(td), "projetos/x", "Camera")
        assert "projetos/x/e.h:2: struct Camera {" in saida.split("Usos")[0]
        assert "projetos/x/main.cpp:3: Camera c;" in saida
        assert "projetos/x/g.cpp:7: int f7()" in project_agent.onde_esta(Path(td), "projetos/x", "f7").split("Usos")[0]
        assert project_agent.onde_esta(Path(td), "projetos/x", "a b").startswith("Erro")
        assert "não aparece" in project_agent.onde_esta(Path(td), "projetos/x", "Inexistente")


def test_pre_busca_e_atalho_de_compilar():
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        workspace.escrever_na_oficina("projetos/x/e.h", "#pragma once\nstruct Camera {\n  float fov;\n};\n")
        grande = "".join(f"int f{i}() {{ return {i}; }}\n" for i in range(1, 301))
        workspace.escrever_na_oficina("projetos/x/main.cpp", grande)
        workspace.escrever_na_oficina("projetos/x/velho.cpp", grande)
        os.utime(Path(td) / "projetos/x/velho.cpp", (1, 1))
        cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1, "pasta": "projetos/x", "plano": None}
        assert project_agent.args_compilar(cp, Path(td)) is None  # sem CMakeLists
        workspace.escrever_na_oficina("projetos/x/CMakeLists.txt", "project(x)\n")
        assert project_agent.args_compilar(cp, Path(td))["projeto"] == "projetos/x"
        project_agent.record(cp, "verificar_codigo", {}, "ok", ok=True,
                             comment="O erro está no velho.cpp linha 200 e na `Camera`; vou olhar.")
        p = project_agent.view(cp, "Projeto: x", Path(td), 10)["projeto_atual"]
        buscado = p["ja_buscado_para_voce"]
        assert buscado[0]["arquivo"] == "projetos/x/velho.cpp" and ">" not in buscado[0]["trecho"][:3]
        assert " 200| int f200()" in buscado[0]["trecho"]
        assert buscado[1]["onde_esta"] == "Camera" and "e.h:2" in buscado[1]["resultado"]
        # Arquivo inteiro na tela (e.h) não é repetido; nota sem referências não traz nada.
        project_agent.record(cp, "verificar_codigo", {}, "ok", ok=True, comment="Vou olhar e.h de novo.")
        assert "ja_buscado_para_voce" not in project_agent.view(cp, "Projeto: x", Path(td), 10)["projeto_atual"]


def test_intermediario_avisa_pensamento_repetido_e_intencao_sem_acao():
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    nota = "O erro está claro: engine.cpp linha 6 usa DiskParams, mas a struct real é AccretionDisk."
    for _ in range(3):
        project_agent.record(cp, "ler_da_oficina", {"caminho": "a.cpp"}, "x", ok=True, comment=nota)
    avisos = project_agent.avisos_do_intermediario(cp)
    assert any(a.startswith("Pensamento repetido") and "1, 2" in a for a in avisos)
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    project_agent.record(cp, "ler_da_oficina", {"caminho": "a.cpp"}, "x", ok=True, comment="Vou corrigir a linha 6 agora.")
    project_agent.record(cp, "ler_da_oficina", {"caminho": "b.h"}, "x", ok=True)
    assert not project_agent.avisos_do_intermediario(cp)  # ainda cedo
    project_agent.record(cp, "verificar_codigo", {"caminho": "p"}, "x", ok=True)
    assert any("ia mudar o código" in a for a in project_agent.avisos_do_intermediario(cp))
    project_agent.record(cp, "editar_na_oficina", {"caminho": "a.cpp"}, "ok", ok=True)
    assert not project_agent.avisos_do_intermediario(cp)  # agiu: sem aviso


def test_intermediario_2b_avisa_com_prova_e_respeita_travas():
    from core import intermediario
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    for i in range(4):
        project_agent.record(cp, "ler_da_oficina", {"caminho": "m.cpp"}, "x", ok=True,
                             comment=f"O erro na linha 139 é claro, vou ler m.cpp antes de corrigir ({i}).")
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(intermediario, "repeticao", return_value=True) as rep:
        project_agent.consultar_intermediario(cp)
        assert rep.call_count == 1 and len(rep.call_args[0][0]) == 3
        avisos = project_agent.avisos_do_intermediario(cp)
        assert any(a.startswith("[intermediário 2B]") and "mais parecida pelo texto é a do passo" in a and "ignore" in a
                   for a in avisos)
        project_agent.consultar_intermediario(cp)
        assert rep.call_count == 1  # a mesma nota não é consultada de novo
        # Trava por regra: arquivo alterado entre as duas notas → o modelo nem é consultado.
        project_agent.record(cp, "editar_na_oficina", {"caminho": "m.cpp"}, "ok", ok=True, comment="Corrigi a linha 139.")
        project_agent.record(cp, "ler_da_oficina", {"caminho": "m.cpp"}, "x", ok=True, comment="O erro na linha 139 é claro.")
        project_agent.consultar_intermediario(cp)
        assert rep.call_count == 1 and cp["intermediario_2b"]["trava"] == "arquivo alterado"
        assert not any(a.startswith("[intermediário 2B]") for a in project_agent.avisos_do_intermediario(cp))
    with patch.object(config, "INTERMEDIARIO_URL", ""):
        cp2 = {"events": list(cp["events"]), "steps": cp["steps"], "last_change_step": -1, "last_ok_run_step": -1}
        project_agent.consultar_intermediario(cp2)
        assert "intermediario_2b" not in cp2  # desligado por padrão
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"):
        assert intermediario.repeticao(["a"], "b", timeout=0.5) is None  # fora do ar: sem aviso, sem exceção
        for estranho in (True, 42, {"so_repete": "false"}, {}):  # revisão Codex: nunca exceção nem aviso
            with patch.object(intermediario, "_chat", return_value=estranho):
                assert intermediario.repeticao(["a"], "b") is None
        with patch.object(intermediario, "_iniciar", side_effect=PermissionError("log")):
            assert intermediario.iniciar().startswith("intermediário não iniciado")
    # Edição entre notas antigas: só compara com as notas depois dela e cita uma delas.
    cp3 = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    project_agent.record(cp3, "ler_da_oficina", {"caminho": "m.cpp"}, "x", ok=True, comment="Vou ler m.cpp.")
    project_agent.record(cp3, "verificar_codigo", {"caminho": "p", "formatar": True}, "ok", ok=True, comment="Formatei.")
    for i in range(3):
        project_agent.record(cp3, "ler_da_oficina", {"caminho": "m.cpp"}, "x", ok=True, comment=f"Vou ler m.cpp ({i}).")
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(intermediario, "repeticao", return_value=True) as rep:
        project_agent.consultar_intermediario(cp3)
        assert [len(a) for a in rep.call_args[0][:1]] == [2]  # passos 3 e 4; o 1 e o 2 (formatação) ficam fora
        assert "do passo 3" in cp3["intermediario_2b"]["aviso"] or "do passo 4" in cp3["intermediario_2b"]["aviso"]
    with patch.object(config, "INTERMEDIARIO_URL", ""):  # desligado: aviso persistido não aparece
        assert not any(a.startswith("[intermediário 2B]") for a in project_agent.avisos_do_intermediario(cp3))


def test_intermediario_no_minecraft_so_em_trecho_sem_progresso():
    from core import intermediario
    # Isolado da configuração de ensaio e de uma pausa deixada por outro teste (revisão Codex 30/10).
    with patch.multiple(intermediario, _falhas_seguidas=0, _pausado_ate=0.0), \
         patch.object(config, "INTERMEDIARIO_MINECRAFT", False):
        _corpo_intermediario_minecraft()


def _corpo_intermediario_minecraft():
    from core import intermediario
    recusa = ("Server refused to place crafting_table at (-146, 84, -221): the block is still air (você está a 10 "
              "blocos do ponto de nascimento do mundo)")
    cp = {"no_progress": 1, "events": [
        {"tool": "minecraft_colocar_bloco", "arguments": {"nome": "crafting_table"}, "status": "uncertain",
         "output": "x" * 400 + recusa, "comment": ""},
        {"tool": "minecraft_colocar_bloco", "arguments": {"nome": "crafting_table", "x": -146}, "status": "uncertain",
         "output": recusa, "comment": "Vou colocar a bancada de novo."}]}
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(intermediario, "tentativa_repetida", return_value=True) as rep:
        assert intermediario.aviso_minecraft({**cp, "no_progress": 5}) is None and rep.call_count == 0  # desligado
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(config, "INTERMEDIARIO_MINECRAFT", True), \
         patch.object(intermediario, "tentativa_repetida", return_value=True) as rep:
        assert intermediario.aviso_minecraft(cp) is None and rep.call_count == 0  # só 1 sem progresso: regra barra
        cp["no_progress"] = 2
        aviso = intermediario.aviso_minecraft(cp)
        assert rep.call_count == 1 and "2 decisões sem progresso" in aviso and "minecraft_colocar_bloco" in aviso
        # Comentário vazio não esconde a tentativa; o motivo da recusa (fim da saída longa) chega ao modelo.
        anteriores, nova = rep.call_args[0][:2]
        assert "anotação: (vazia)" in anteriores[0] and "ponto de nascimento" in anteriores[0]
        assert '"x": -146' in nova and "Vou colocar a bancada de novo." in nova
        assert intermediario.aviso_minecraft(cp) == aviso and rep.call_count == 1  # mesmo estado: sem nova consulta
        cp["events"].append({"tool": None, "status": "rejected_before_effect"})  # sem ferramenta: fica de fora
        cp["no_progress"] = 3
        intermediario.aviso_minecraft(cp)
        assert '"x": -146' in rep.call_args[0][1]
        # Lista de eventos cheia (tamanho constante): trecho novo com o mesmo no_progress é consultado de novo.
        chamadas = rep.call_count
        cp2 = {"no_progress": 2, "events": [{"tool": "minecraft_coletar", "comment": "Vou minerar carvão."},
                                            {"tool": "minecraft_coletar", "comment": "Vou minerar carvão agora."}]}
        intermediario.aviso_minecraft(cp2)
        cp2["events"] = [{"tool": "minecraft_ir_para", "comment": "Vou ao forno."},
                         {"tool": "minecraft_ir_para", "comment": "Vou até o forno agora."}]
        intermediario.aviso_minecraft(cp2)
        assert rep.call_count == chamadas + 2
        # Falha do modelo não vira "avaliado sem aviso": no mesmo estado, consulta de novo.
        rep.return_value = None
        cp3 = {"no_progress": 2, "events": [{"tool": "minecraft_forno", "comment": "a"},
                                            {"tool": "minecraft_forno", "comment": "b"}]}
        antes = rep.call_count
        assert intermediario.aviso_minecraft(cp3) is None and intermediario.aviso_minecraft(cp3) is None
        assert rep.call_count == antes + 2 and "intermediario_mc" not in cp3
    # O aviso chega à visão de decisão com opções (30/10: decision_view o descartava).
    from core import minecraft_cognition
    assert minecraft_cognition.decision_view({"intermediario": "[intermediário 2B] x"})["intermediario"]
    # O motivo da recusa no fim de uma saída longa sobrevive aos dois cortes.
    longa = intermediario.descrever_tentativa({"tool": "minecraft_colocar_bloco", "arguments": {"nome": "a" * 150},
                                               "status": "uncertain", "comment": "c" * 300,
                                               "output": "x" * 900 + " ponto de nascimento do mundo"})
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(intermediario, "_chat", return_value={"so_repete": False}) as chat:
        intermediario.tentativa_repetida([longa], longa)
        assert chat.call_args[0][1].count("ponto de nascimento do mundo") == 2
    # Estouros de tempo seguidos pausam o intermediário em vez de cada decisão esperar o timeout.
    def estoura(*_a, info=None, **_k):
        info["falha"] = "TimeoutError"
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(intermediario, "_falhas_seguidas", 0), patch.object(intermediario, "_pausado_ate", 0.0), \
         patch.object(intermediario, "_chat", side_effect=estoura) as chat:
        for _ in range(5):
            assert intermediario.repeticao(["a"], "b") is None
        assert chat.call_count == intermediario._FALHAS_PARA_PAUSAR
    # A categoria da falha HTTP vem da exceção e do status, não do texto do motivo.
    import urllib.error
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("u", 503, "x", {}, None)):
        info = {}
        assert intermediario._chat("s", "u", {}, 1, info=info) is None
        assert info["falha"] == "HTTPError" and info["http_status"] == 503
    # Cada consulta é medida no diagnóstico, com resposta e tempo.
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(intermediario, "_chat", return_value={"so_repete": True}), \
         patch("core.diagnostics.emit") as emit:
        assert intermediario.tentativa_repetida(["a"], "b") is True
        nome, dados = emit.call_args[0][0], emit.call_args[1]
        assert nome == "intermediario.consulta" and dados["tipo"] == "tentativa" and dados["resposta"] is True
        assert isinstance(dados["elapsed_ms"], int)
    with patch.object(config, "INTERMEDIARIO_URL", ""):
        assert intermediario.aviso_minecraft({"no_progress": 9, "events": cp["events"]}) is None
    with patch.object(config, "INTERMEDIARIO_URL", "http://127.0.0.1:9"), \
         patch.object(config, "INTERMEDIARIO_MINECRAFT", True), \
         patch.object(intermediario, "tentativa_repetida", side_effect=RuntimeError("x")):
        assert intermediario.aviso_minecraft({"no_progress": 5, "events": cp["events"]}) is None


def test_leitura_que_saiu_da_visao_nao_conta():
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    for _ in range(4):
        project_agent.record(cp, "ler_da_oficina", {"caminho": "p/a.cpp"}, "x", ok=True)
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp", "inicio": 1, "fim": 5}) is None
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp"})
    for i in range(project_agent.RECIBOS_NA_VISAO):
        project_agent.record(cp, "listar_oficina", {"subpasta": f"p{i}"}, "y", ok=True)
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp"}) is None


def test_formatar_conta_como_mudanca():
    cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1}
    for _ in range(4):
        project_agent.record(cp, "ler_da_oficina", {"caminho": "p/a.cpp", "inicio": 1, "fim": 9}, "x", ok=True)
    project_agent.record(cp, "verificar_codigo", {"caminho": "p", "formatar": True}, "ok", ok=True)
    assert cp["last_change_step"] == 5
    assert project_agent.releitura_excessiva(cp, "ler_da_oficina", {"caminho": "p/a.cpp", "inicio": 1, "fim": 9}) is None


def test_estado_do_projeto_alerta_sem_compilar_e_relatorio():
    with tempfile.TemporaryDirectory() as td, patch.object(workspace, "OFICINA", Path(td)):
        workspace.preparar_oficina()
        workspace.escrever_na_oficina("projetos/x/main.cpp", "int main(){}\n")
        cp = {"events": [], "steps": 0, "last_change_step": -1, "last_ok_run_step": -1, "pasta": "projetos/x", "plano": None}
        for _ in range(project_agent.SEM_COMPILAR_ALERTA):
            project_agent.record(cp, "ler_da_oficina", {"caminho": "projetos/x/main.cpp"}, "x", ok=True)
        visao = project_agent.view(cp, "Projeto: x", Path(td), 10)["projeto_atual"]
        assert visao["estado_do_projeto"]["ultimo_build"] == "o projeto ainda não foi compilado nenhuma vez"
        assert any("não compila nem roda nada" in a for a in visao["alertas"])
        assert "Compilou: nunca" in project_agent.relatorio_sessao(cp, Path(td), 0)
        project_agent.record(cp, "executar_na_oficina", {"codigo": "cmake -B build && cmake --build build"},
                             "Arquivo: x\n[oficina | código 2]\nmain.cpp:1:1: error: expected", ok=True)
        assert cp["ultimo_build"]["ok"] is False and "error" in cp["ultimo_build"]["erros"][0]
        # Consultar caminhos com "cmake" no nome não é build.
        assert not project_agent.construcao("executar_na_oficina", {"codigo": "ls /usr/lib/cmake/GLFW* || grep '\\.cmake$' x"})
        project_agent.record(cp, "executar_na_oficina", {"codigo": "cd p && cmake --build build"},
                             "[oficina | código 1]\n[stderr]\nx.sh: line 1: cd: p: No such file or directory", ok=True)
        assert "No such file" in cp["ultimo_build"]["erros"][0]
        project_agent.record(cp, "executar_na_oficina", {"codigo": "cd p && make 2>&1 | head -300"},
                             "[oficina | código 0]\nmain.cpp:3:1: error: x", ok=True)
        assert cp["ultimo_build"]["ok"] is False
        assert not project_agent.construcao("executar_na_oficina", {"codigo": "cd p && cmake -B build -S ."})
        assert not project_agent.construcao("executar_na_oficina", {"codigo": "cmake --version"})
        assert not project_agent.construcao("executar_na_oficina", {"codigo": "false && g++ main.cpp; echo finished"})
        visao = project_agent.view(cp, "Projeto: x", Path(td), 10)["projeto_atual"]
        assert not any("não compila nem roda nada" in a for a in visao["alertas"])
        assert "Compilou: não (passo 17)" in project_agent.relatorio_sessao(cp, Path(td), 0)


def test_saida_de_execucao_bem_sucedida_por_tipo():
    assert project_agent.run_succeeded("executar_na_oficina", "Arquivo: a\n[oficina | código 0]\nok")
    assert not project_agent.run_succeeded("executar_na_oficina", "Arquivo: a\n[oficina | código 0]\n(sem saída)")
    assert not project_agent.run_succeeded("executar_na_oficina", "Arquivo: a\n[oficina | código 1]\nerro")
    assert not project_agent.run_succeeded("executar_grafico_na_oficina", "Arquivo: a — rodou 8s e foi encerrado por mim.")
    assert not project_agent.run_succeeded("executar_grafico_na_oficina", "Arquivo: a — terminou sozinho com código 139.")


def test_leitura_6054_preservada_e_corte_grande_explicito():
    cp={"events":[],"steps":0,"last_change_step":-1,"last_ok_run_step":-1,"pasta":"projetos/x","plano":None}
    text='x'*6040+'FIM_DO_ARQUIVO'
    project_agent.record(cp,'ler_da_oficina',{'caminho':'projetos/x/a.cpp'},text,ok=True)
    seen=project_agent.view(cp,'Projeto: x',Path('/nao/existe'),10)['projeto_atual']['ultimos_recibos'][-1]
    assert seen['saida']==text,'A leitura perdeu a cauda sem avisar'
    project_agent.record(cp,'ler_da_oficina',{'caminho':'projetos/x/a.cpp'},'x'*12000,ok=True)
    seen=project_agent.view(cp,'Projeto: x',Path('/nao/existe'),10)['projeto_atual']['ultimos_recibos'][-1]
    assert seen['saida_truncada'] is True and '[cortado]' in seen['saida']


def test_fontes_nao_somem_atras_de_arquivos_gerados():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);generated=root/'projetos/x/build/CMakeFiles';generated.mkdir(parents=True)
        for i in range(410):(generated/f'{i:04}.txt').write_text('generated')
        (root/'projetos/x/main.cpp').write_text('fixture')
        files=project_agent._arquivos(root,'projetos/x')
        assert any(f['arquivo']=='projetos/x/main.cpp' for f in files)
        assert all('CMakeFiles' not in f['arquivo'] for f in files)


def test_comando_consulta_e_build_nao_comprovam_execucao_e_versao_importa():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);base=root/'projetos/x';base.mkdir(parents=True)
        source=base/'main.cpp';source.write_text('fixture v1')
        binary=base/'program';binary.write_text('fixture executable');binary.chmod(0o755)
        cp={"events":[],"steps":0,"last_change_step":-1,"last_ok_run_step":-1,"pasta":"projetos/x","plano":None}
        for command in ('ls','cmake --version','cmake -S . -B build','cmake --build build'):
            project_agent.record(cp,'executar_na_oficina',{'codigo':command,'linguagem':'bash','projeto':'x'},
                                 '[oficina | código 0]\ntexto',ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root) is not None
        project_agent.record(cp,'executar_na_oficina',{'codigo':'./program','linguagem':'bash','projeto':'x'},
                             '[oficina | código 0]\noutput do programa',ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root) is None
        source.write_text('fixture v2 changed by a command')
        assert project_agent.completion_problem(cp,root) is not None


def test_janela_sem_captura_e_execucao_de_outro_projeto_nao_aprovam():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);base=root/'projetos/x';base.mkdir(parents=True)
        (base/'main.cpp').write_text('fixture')
        binary=base/'app';binary.write_text('fixture executable');binary.chmod(0o755)
        other=root/'projetos/y';other.mkdir();(other/'app.py').write_text('fixture')
        cp={"events":[],"steps":0,"last_change_step":-1,"last_ok_run_step":-1,"pasta":"projetos/x","plano":None}
        project_agent.record(cp,'executar_na_oficina',{'arquivo':'projetos/y/app.py','linguagem':'python'},
                             '[oficina | código 0]\nok',ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root) is not None
        project_agent.record(cp,'executar_grafico_na_oficina',{'arquivo':'projetos/x/app'},
                             'Arquivo: projetos/x/app — rodou 8s e foi encerrado por mim.\nNenhuma janela nova apareceu.\n[saída]\n(sem saída)',
                             ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root) is not None


def test_orcamento_total_e_execucao_legada_nao_sao_aprovacao():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);base=root/'projetos/x';base.mkdir(parents=True);(base/'README.md').write_text('fixture')
        cp={"events":[],"steps":590,"last_change_step":1,"last_ok_run_step":125,"pasta":"projetos/x","plano":None,'max_total_steps':600}
        assert project_agent.session_limit(cp,60)==10
        cp['steps']=600;assert project_agent.session_limit(cp,60)==0
        assert project_agent.completion_problem(cp,root) is not None


def test_execucao_grafica_qualificada_e_trecho_de_versao_nova():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);base=root/'projetos/x';base.mkdir(parents=True)
        source=base/'main.cpp';source.write_text('fixture v1')
        binary=base/'app';binary.write_text('fixture executable');binary.chmod(0o755)
        cp={"events":[],"steps":0,"last_change_step":-1,"last_ok_run_step":-1,"pasta":"projetos/x","plano":None,'require_graphical_run':True}
        (root/'capturas').mkdir();(root/'capturas/app.png').write_bytes(b'fixture capture')
        out='Arquivo: projetos/x/app — rodou 8s e foi encerrado por mim.\nCapturas: capturas/app.png (800x600, janela fixture)\n[saída]\nok'
        project_agent.record(cp,'executar_grafico_na_oficina',{'arquivo':'projetos/x/app'},out,ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root) is None
        for _ in range(2):
            project_agent.record(cp,'ler_da_oficina',{'caminho':'projetos/x/main.cpp'},'fixture v1',ok=True,raiz=root)
        assert project_agent.releitura_excessiva(cp,'ler_da_oficina',{'caminho':'projetos/x/main.cpp'},root)
        source.write_text('fixture v2 written outside edit tool')
        assert project_agent.releitura_excessiva(cp,'ler_da_oficina',{'caminho':'projetos/x/main.cpp'},root) is None
        assert project_agent.completion_problem(cp,root) is not None


def test_recursos_em_build_e_scripts_de_consulta_nao_dao_falso_credito():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);base=root/'projetos/x';base.mkdir(parents=True)
        build=base/'build';build.mkdir()
        shader=build/'runtime.comp';shader.write_text('fixture shader v1')
        (base/'main.cpp').write_text('fixture')
        script=base/'consulta.sh';script.write_text('#!/bin/sh\ncmake --version\n')
        binary=build/'app';binary.write_text('fixture executable')
        cp={"events":[],"steps":0,"last_change_step":-1,"last_ok_run_step":-1,"pasta":"projetos/x","plano":None}
        project_agent.record(cp,'executar_na_oficina',{'arquivo':'projetos/x/consulta.sh'},
                             '[oficina | código 0]\ncmake version fixture',ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root),'Script de consulta não comprova execução do produto'
        (root/'capturas').mkdir();(root/'capturas/app.png').write_bytes(b'fixture')
        out='Arquivo: projetos/x/build/app — rodou 8s e foi encerrado por mim.\nCapturas: capturas/app.png (800x600)\n[saída]\nok'
        project_agent.record(cp,'executar_grafico_na_oficina',{'arquivo':'projetos/x/build/app'},out,ok=True,raiz=root)
        assert project_agent.completion_problem(cp,root) is None
        shader.write_text('fixture shader v2')
        assert project_agent.completion_problem(cp,root),'Recurso em build mudou após execução'
    for command in ('make -n','ninja --dry-run','cmake --build build --target help'):
        assert not project_agent.construcao('executar_na_oficina',{'codigo':command,'linguagem':'bash'}),command


def test_ciclo_releitura_de_versao_nova_passa_pela_guarda_generica():
    with tempfile.TemporaryDirectory() as td, _ambiente(td):
        chave=('local','projeto-versao','')
        tarefa=task_state.iniciar_ou_continuar(chave,OBJETIVO)
        cp=project_agent.initial(tarefa)
        path=workspace.OFICINA/cp['pasta']/'main.cpp';path.parent.mkdir(parents=True)
        path.write_text('fixture v1')
        args={'caminho':str(path.relative_to(workspace.OFICINA))}
        responses=[('ler_da_oficina',args),('ler_da_oficina',args)]
        calls=[]
        app,_=_app(responses,lambda n,a:calls.append(n) or path.read_text())
        with patch.object(config,'MAX_PASSOS_PROJETO',1):
            asyncio.run(app._ciclo_projeto(tarefa,chave_conversa=chave,canal='local'))
            path.write_text('fixture v2')
            asyncio.run(app._ciclo_projeto(tarefa,chave_conversa=chave,canal='local',retomar=True))
        assert calls==['ler_da_oficina','ler_da_oficina']
        assert project_agent.load(tarefa)['events'][-1]['saida']=='fixture v2'


def test_orcamento_conta_decisao_sem_chamada_e_backend_incompleto():
    for resposta in ((None,'sem chamada'),_incompleta()):
        with tempfile.TemporaryDirectory() as td, _ambiente(td):
            chave=('local','projeto-limite','')
            tarefa=task_state.iniciar_ou_continuar(chave,OBJETIVO)
            cp=project_agent.initial(tarefa);cp.update(steps=599,max_total_steps=600)
            project_agent.save(tarefa,cp)
            app,vistos=_app([resposta],lambda n,a:'Não deve executar')
            asyncio.run(app._ciclo_projeto(tarefa,chave_conversa=chave,canal='local',retomar=True))
            assert project_agent.load(tarefa)['steps']==600
            calls=len(vistos)
            texto,_=asyncio.run(app._ciclo_projeto(tarefa,chave_conversa=chave,canal='local',retomar=True))
            assert len(vistos)==calls and 'orçamento total' in texto
            assert 'Diga "continue"' not in texto


if __name__ == "__main__":
    testes = [test_marcador_e_pasta_do_projeto,
              test_decisao_incompleta_do_backend_nao_derruba_o_projeto,
              test_conclusao_so_depois_de_execucao_bem_sucedida_posterior_a_mudanca,
              test_sem_chamada_pausa_e_decisao_humana_pausa_com_pergunta,
              test_ferramenta_fora_do_modo_projeto_e_recusada_antes_de_executar,
              test_editar_na_oficina_troca_trecho_unico_e_recusa_ambiguo,
              test_releitura_do_mesmo_arquivo_sem_mudanca_e_recusada,
              test_visao_mostra_a_leitura_mais_recente_quase_inteira,
              test_editar_por_linhas_e_falha_mostra_o_texto_real,
              test_codigo_do_projeto_aparece_numerado_na_visao,
              test_memoria_de_trabalho_primeiro_erro_e_janela_de_codigo,
              test_ja_na_tela_e_onde_esta,
              test_pre_busca_e_atalho_de_compilar,
              test_intermediario_avisa_pensamento_repetido_e_intencao_sem_acao,
              test_intermediario_2b_avisa_com_prova_e_respeita_travas,
              test_intermediario_no_minecraft_so_em_trecho_sem_progresso,
              test_leitura_que_saiu_da_visao_nao_conta,
              test_formatar_conta_como_mudanca,
              test_estado_do_projeto_alerta_sem_compilar_e_relatorio,
              test_saida_de_execucao_bem_sucedida_por_tipo,
              test_leitura_6054_preservada_e_corte_grande_explicito,
              test_fontes_nao_somem_atras_de_arquivos_gerados,
              test_comando_consulta_e_build_nao_comprovam_execucao_e_versao_importa,
              test_janela_sem_captura_e_execucao_de_outro_projeto_nao_aprovam,
              test_orcamento_total_e_execucao_legada_nao_sao_aprovacao,
              test_execucao_grafica_qualificada_e_trecho_de_versao_nova,
              test_recursos_em_build_e_scripts_de_consulta_nao_dao_falso_credito,
              test_ciclo_releitura_de_versao_nova_passa_pela_guarda_generica,
              test_orcamento_conta_decisao_sem_chamada_e_backend_incompleto]
    for teste in testes:
        teste()
        print("ok", teste.__name__)
