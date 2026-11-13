"""Regressões V28 para tarefas: ferramenta real, recuperação de tool-call e observabilidade."""
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
from core import task_state  # noqa: E402

# Stub Textual apenas para importar main sem UI.
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


def test_task_detects_workspace_then_read_and_context_updates():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "local", "")
        tarefa = task_state.iniciar_ou_continuar(
            chave, "Crie o arquivo projeto.txt. Depois leia o arquivo e verifique o resultado."
        )
        assert task_state.ferramentas_pendentes(chave) == ["workspace"]
        task_state.registrar_ferramenta(chave, "workspace", "success", "PATH=/tmp/projeto.txt\nACAO=CRIADO")
        assert task_state.ferramentas_pendentes(chave) == ["workspace"]
        contexto = task_state.contexto(chave)
        assert "PRÓXIMA FERRAMENTA OBRIGATÓRIA: workspace" in contexto


def test_dispatch_tarefa_expoe_so_ferramentas_do_marco():
    from core import dispatch
    schemas = dispatch.esquemas("tarefa", ferramentas_prioritarias=["write_file"], modo_operacao="tarefa")
    nomes = {x["function"]["name"] for x in schemas}
    assert "workspace" in nomes
    assert "execute_command" not in nomes
    assert "browser_abrir" not in nomes


def test_progress_mostra_modelo_deliberacao_contexto_e_entrada():
    from core import progress
    progress.limpar()
    progress.iniciar("tarefa", model="qwen3.5:9b", num_ctx=24576, task_id="ct-1", task_step=1, task_total=11,
                     thinking_enabled=False, streaming_enabled=True)
    progress.cognicao("executar", "projeto.txt", "workspace")
    progress.contexto(8)
    progress.ferramentas_disponiveis(["workspace"])
    texto = progress.render(pending_inputs=1, active_workers=1)
    assert "modelo=qwen3.5:9b" in texto
    assert "contexto=8 msgs" in texto
    assert "deliberação=executar" in texto
    assert "próxima=workspace" in texto
    assert "ENTRADA REAL AGUARDANDO=1" in texto
    progress.finalizar("concluido")


def test_task_tool_call_missing_recovery_is_present():
    text = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert '"task_tool_call_missing"' in text
    assert "RECUPERAÇÃO OPERACIONAL OBRIGATÓRIA" in text


def test_structured_task_args_usa_schema_da_unica_ferramenta():
    from core import dispatch
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "local-structured", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "Crie o arquivo /tmp/projeto.txt")
        operacao = task_state.proxima_operacao(chave)
        assert operacao and operacao["ferramenta"] == "workspace"

        app = object.__new__(main.InterfaceHoshino)
        chamadas = []

        async def fake_chamar_modelo(mensagens, ferramentas=None, forcar_sem_pensar=False,
                                     think_override=None, formato=None):
            chamadas.append({"mensagens": mensagens, "ferramentas": ferramentas,
                             "forcar_sem_pensar": forcar_sem_pensar,
                             "think_override": think_override, "formato": formato})
            return {"content": '{"operacao":"criar","caminho":"/tmp/projeto.txt","conteudo":"ok"}'}

        app.chamar_modelo = fake_chamar_modelo
        args, erro = asyncio.run(app._obter_args_de_tarefa(tarefa, operacao))
        assert not erro
        assert args == {"operacao": "salvar", "modo": "substituir", "caminho": "/tmp/projeto.txt", "conteudo": "ok"}
        assert chamadas and chamadas[0]["ferramentas"] is None
        assert chamadas[0]["forcar_sem_pensar"] is True
        assert chamadas[0]["think_override"] is False
        esperado = app._schema_workspace_operacao(operacao)
        assert chamadas[0]["formato"] == esperado


def test_browser_task_rejeita_args_vazios_antes_da_execucao():
    from core import dispatch
    tarefa = types.SimpleNamespace(chave=('tui', 'browser-args', ''), id='ct-browser-args')
    app = object.__new__(main.InterfaceHoshino)
    chamadas = []

    async def fake_chamar_modelo(mensagens, ferramentas=None, **kwargs):
        chamadas.append(kwargs['formato'])
        return {'content': '{}'}

    app.chamar_modelo = fake_chamar_modelo
    with patch.object(task_state, 'contexto_operacao', return_value='Abra https://example.org/'):
        args, erro = asyncio.run(app._obter_args_de_tarefa(tarefa, {'ferramenta': 'browser_abrir'}))
    assert args == {}
    assert 'obrigatório ausente: url' in erro
    assert len(chamadas) == 2
    assert all(schema == dispatch.formato_argumentos('browser_abrir') for schema in chamadas)
    assert all(schema['required'] == ['url'] for schema in chamadas)


def test_browser_task_corrige_so_argumentos_sem_repetir_acao():
    tarefa = types.SimpleNamespace(chave=('tui', 'browser-args-repair', ''), id='ct-browser-repair')
    app = object.__new__(main.InterfaceHoshino)
    respostas = iter(('{}', '{"url":"https://example.org/","nova_aba":true}'))

    async def fake_chamar_modelo(*args, **kwargs):
        return {'content': next(respostas)}

    app.chamar_modelo = fake_chamar_modelo
    with patch.object(task_state, 'contexto_operacao', return_value='Abra https://example.org/'), \
         patch.object(main.dispatch, 'executar_resultado') as executar:
        args, erro = asyncio.run(app._obter_args_de_tarefa(tarefa, {'ferramenta': 'browser_abrir'}))
    assert not erro
    assert args == {'url': 'https://example.org/', 'nova_aba': True}
    executar.assert_not_called()


def test_tarefa_longo_executa_operacoes_sem_tool_call_nativo():
    from core import progress
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "local-loop", "")
        tarefa = task_state.iniciar_ou_continuar(
            chave, "Crie o arquivo /tmp/a.txt. Depois leia o arquivo."
        )
        app = object.__new__(main.InterfaceHoshino)
        app._fila_chaves = {}
        app._saidas_por_conversa = {}
        app._locks_saida = {}
        progress.limpar()
        progress.iniciar("teste-tarefa")
        chamadas = []

        async def fake_args(tarefa_viva, operacao, tentativa_max=2, observacoes=()):
            nome = operacao["ferramenta"]
            chamadas.append(nome)
            if nome == "workspace":
                subop = str(operacao.get("operacao") or "criar")
                if subop == "criar":
                    return {"operacao": "criar", "caminho": "/tmp/a.txt", "conteudo": "ok"}, ""
                return {"operacao": "ler", "caminho": "/tmp/a.txt"}, ""

        async def fake_exec(chamadas_tool, frame, passo, *args, **kwargs):
            from core import cognition
            nome = chamadas_tool[0]["function"]["name"]
            resultado = {"ok": True, "status": "success", "output": "ok"}
            cognition.registrar_ferramenta(frame, nome, resultado)
            return [(nome, {}, resultado)]

        app._obter_args_de_tarefa = fake_args
        app._executar_chamadas_da_etapa = fake_exec
        async def fake_planejar(*args, **kwargs):
            return False, "teste do fallback determinístico, sem chamada ao modelo real"
        app._planejar_operacoes_de_tarefa = fake_planejar
        resultado = asyncio.run(app._ciclo_de_ferramentas_impl(
            [{"role": "user", "content": tarefa.objetivo}],
            [], chave_conversa=chave, canal="tui", tarefa_turno=tarefa,
        ))
        assert chamadas == ["workspace", "workspace"]
        assert task_state.carregar(chave) is None
        # Sem um modelo de apresentação nesta fixture, devolve recibo atribuído,
        # nunca a antiga aprovação genérica de requisitos não testados.
        assert "Recibo da ferramenta; requisitos não certificados:" in resultado[0]
        assert "Terminei essa etapa" not in resultado[0]
        progress.finalizar("concluido")


def test_contratos_de_tarefa_sao_limitados_e_relevantes():
    from core import dispatch
    contratos = dispatch.contratos_tarefa(
        "Crie as pastas do projeto e depois leia o arquivo estado.txt.", limite=10)
    nomes = [x["function"]["name"] for x in contratos]
    assert len(contratos) <= 10
    assert nomes == ["workspace"]


def test_planejador_persiste_repeticao_da_mesma_ferramenta():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "planner", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "Crie os arquivos A.txt e B.txt e depois leia ambos.")
        app = object.__new__(main.InterfaceHoshino)

        async def fake_chamar_modelo(mensagens, ferramentas=None, forcar_sem_pensar=False,
                                     think_override=None, formato=None):
            assert ferramentas is None
            assert formato and "operacoes" in formato["properties"]
            return {"content": json.dumps({
                "operacoes": [
                    {"ferramenta": "workspace", "operacao": "criar", "instrucao": "Crie A.txt."},
                    {"ferramenta": "workspace", "operacao": "criar", "instrucao": "Crie B.txt."},
                    {"ferramenta": "workspace", "operacao": "ler", "instrucao": "Leia A.txt e B.txt."},
                ]
            }, ensure_ascii=False)}

        # Import local apenas para manter este teste isolado das funções não usadas acima.
        app.chamar_modelo = fake_chamar_modelo
        ok, erro = asyncio.run(app._planejar_operacoes_de_tarefa(tarefa))
        assert ok and not erro
        op1 = task_state.proxima_operacao(chave)
        assert op1["ferramenta"] == "workspace"
        task_state.registrar_ferramenta(chave, "workspace", "success", "PATH=/tmp/A.txt\nACAO=CRIADO", op1["operacao_id"])
        op2 = task_state.proxima_operacao(chave)
        assert op2["ferramenta"] == "workspace"
        task_state.registrar_ferramenta(chave, "workspace", "success", "PATH=/tmp/B.txt\nACAO=CRIADO", op2["operacao_id"])
        op3 = task_state.proxima_operacao(chave)
        assert op3["ferramenta"] == "workspace"


def test_planejador_pode_concluir_marco_sem_ferramenta():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "planner-noop", "")
        tarefa = task_state.iniciar_ou_continuar(
            chave, "Crie a pasta /tmp/noopdir. Depois faça uma revisão mental do estado e não invente nenhuma ação externa."
        )
        first = task_state.proxima_operacao(chave)
        assert first and first["ferramenta"] == "workspace"
        task_state.registrar_ferramenta(chave, "workspace", "success", "PASTA=/tmp/noopdir\nCRIADA", first["operacao_id"])
        tarefa = task_state.carregar(chave)
        app = object.__new__(main.InterfaceHoshino)

        async def fake_chamar_modelo(mensagens, ferramentas=None, forcar_sem_pensar=False,
                                     think_override=None, formato=None):
            assert ferramentas is None
            assert "__nenhuma__" in (formato["properties"]["operacoes"]["items"]["properties"]["ferramenta"]["enum"])
            return {"content": json.dumps({
                "operacoes": [], "concluida": True,
                "observacao": "Esta etapa não exige ferramenta externa."
            }, ensure_ascii=False)}

        app.chamar_modelo = fake_chamar_modelo
        ok, erro = asyncio.run(app._planejar_operacoes_de_tarefa(tarefa))
        assert ok and not erro
        assert task_state.carregar(chave) is None


def test_workspace_e_auto_verificado_no_mesmo_resultado():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "planner-verifier", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "Crie o arquivo /tmp/apenas-uma-vez.txt")
        op = task_state.proxima_operacao(chave)
        assert op and op["ferramenta"] == "workspace"
        assert op.get("operacao") == "salvar"
        assert op.get("modo") == "substituir"
        task_state.registrar_ferramenta(chave, "workspace", "success", "PATH=/tmp/apenas-uma-vez.txt\nACAO=CRIADO", op["operacao_id"])
        assert task_state.carregar(chave) is None


def test_contratos_tarefa_filtra_ruido_e_toolforge_para_arquivo_de_codigo():
    from core import dispatch
    nomes = [x["function"]["name"] for x in dispatch.contratos_tarefa(
        "Crie a ferramenta própria analisador_teste.py dentro de 02_ferramentas. Depois execute-a e leia o resultado."
    )]
    assert "workspace" in nomes
    assert "execute_command" in nomes
    assert "criar_ferramenta" not in nomes
    assert "escrever_na_oficina" not in nomes
    assert "browser_abas" not in nomes
    assert len(nomes) <= 5


def test_workspace_e_escrita_segura():
    from core import capabilities
    info = capabilities.info("workspace")
    assert info.mutates is True
    assert info.categoria == "acao"
    assert info.verifier == ""
    assert "workspace" not in capabilities.READ_ONLY


def test_workspace_api_unificada_substituir_anexar_editar():
    from tools import filesystem
    with tempfile.TemporaryDirectory() as td:
        alvo = Path(td) / "nota.txt"
        # O módulo de workspace permite ao chamador usar um base path explícito.
        assert filesystem.workspace("salvar", str(alvo), "linha 1") .startswith("OPERACAO=salvar")
        assert alvo.read_text(encoding="utf-8") == "linha 1"
        filesystem.workspace("salvar", str(alvo), "\nlinha 2", modo="anexar")
        assert alvo.read_text(encoding="utf-8") == "linha 1\nlinha 2"
        filesystem.workspace("salvar", str(alvo), procurar="linha 2", substituir="linha 3", modo="editar")
        assert alvo.read_text(encoding="utf-8") == "linha 1\nlinha 3"
        leitura = filesystem.workspace("ler", str(alvo))
        assert "linha 3" in leitura


def test_workspace_handler_preserva_modo_editar():
    from core import dispatch
    with tempfile.TemporaryDirectory() as td:
        alvo = Path(td) / "nota.txt"
        alvo.write_text("antes", encoding="utf-8")
        resultado = dispatch.executar("workspace", {
            "operacao": "salvar", "modo": "editar", "caminho": str(alvo),
            "procurar": "antes", "substituir": "depois"
        })
        assert "MODO=editar" in resultado
        assert "ACAO=SALVO" in resultado
        assert alvo.read_text(encoding="utf-8") == "depois"


def test_workspace_stage_detecta_pasta_antes_de_arquivo():
    assert task_state._inferir_workspace_operacao("Crie a pasta 01_arquivos") == "pasta"
    assert task_state._inferir_workspace_operacao("Crie o arquivo projeto.txt") == "salvar"
    assert task_state._inferir_workspace_operacao("Liste o conteúdo da pasta 01_arquivos") == "listar"


def test_workspace_editar_detecta_modo_editar():
    op = task_state._detectar_operacoes("Edite o arquivo registro.txt substituindo 'a' por 'b'.")
    assert [o['operacao'] for o in op] == ['ler','salvar']
    assert op[1]["modo"] == "editar"  # leitura prévia não transforma patch em overwrite


def test_workspace_canonicaliza_raiz_inventada_para_o_workspace_da_tarefa():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "v31-root", "")
        root = Path(td) / "HOSHINO_TESTE_V2"
        arquivo = root / "01_arquivos" / "registro.txt"
        tarefa = task_state.iniciar_ou_continuar(
            chave, f"Crie o arquivo {arquivo}. Depois edite o mesmo arquivo."
        )
        root.mkdir(parents=True)
        arquivo.parent.mkdir(parents=True)
        arquivo.write_text("antes", encoding="utf-8")
        task_state.registrar_ferramenta(
            chave, "workspace", "success", f"PATH={arquivo}\nACAO=SALVO", 
            task_state.proxima_operacao(chave)["operacao_id"]
        )
        tarefa = task_state.carregar(chave)
        op = task_state.proxima_operacao(chave)
        args = task_state.normalizar_argumentos_operacao(
            tarefa, op,
            {"operacao": "salvar", "modo": "editar",
             "caminho": "/home/user/workspace/HOSHINO_TESTE_V2/01_arquivos/registro.txt",
             "procurar": "antes", "substituir": "depois"},
        )
        assert args["caminho"] == str(arquivo.resolve())


def test_proxima_operacao_preserva_modo_do_workspace():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "v31-mode", "")
        tarefa = task_state.iniciar_ou_continuar(chave, "Edite o arquivo registro.txt")
        op = task_state.proxima_operacao(chave)
        assert op["ferramenta"] == "workspace"
        assert op['operacao']=='ler'
        task_state.registrar_ferramenta(chave,'workspace','success','leitura mockada')
        op=task_state.proxima_operacao(chave)
        assert op["operacao"] == "salvar"
        assert op["modo"] == "editar"


if __name__ == "__main__":
    tests = [
        test_task_detects_workspace_then_read_and_context_updates,
        test_dispatch_tarefa_expoe_so_ferramentas_do_marco,
        test_progress_mostra_modelo_deliberacao_contexto_e_entrada,
        test_task_tool_call_missing_recovery_is_present,
        test_structured_task_args_usa_schema_da_unica_ferramenta,
        test_browser_task_rejeita_args_vazios_antes_da_execucao,
        test_browser_task_corrige_so_argumentos_sem_repetir_acao,
        test_tarefa_longo_executa_operacoes_sem_tool_call_nativo,
        test_contratos_de_tarefa_sao_limitados_e_relevantes,
        test_planejador_persiste_repeticao_da_mesma_ferramenta,
        test_planejador_pode_concluir_marco_sem_ferramenta,
        test_workspace_e_auto_verificado_no_mesmo_resultado,
        test_contratos_tarefa_filtra_ruido_e_toolforge_para_arquivo_de_codigo,
        test_workspace_e_escrita_segura,
        test_workspace_api_unificada_substituir_anexar_editar,
        test_workspace_handler_preserva_modo_editar,
        test_workspace_stage_detecta_pasta_antes_de_arquivo,
        test_workspace_editar_detecta_modo_editar,
        test_workspace_canonicaliza_raiz_inventada_para_o_workspace_da_tarefa,
        test_proxima_operacao_preserva_modo_do_workspace,
    ]
    for t in tests:
        t()
        print("ok -", t.__name__)


def test_workspace_normaliza_desktop_absoluto_para_desktop_real():
    from tools import filesystem
    import os
    home = Path.home()
    aliases = [home / "Área de Trabalho" / "HOSHINO_V30" / "registro.txt",
               home / "Area de Trabalho" / "HOSHINO_V30" / "registro.txt"]
    for alias in aliases:
        got = filesystem.resolver_caminho(str(alias))
        assert got.parents[1] == filesystem._desktop_dir()



def test_workspace_tira_caminho_conhecido_do_estado_da_tarefa():
    home = Path.home()
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "v30-known", "")
        arquivo = str(Path(td) / "registro.txt")
        tarefa = task_state.iniciar_ou_continuar(chave, f"Crie o arquivo {arquivo}. Depois edite o mesmo arquivo.")
        op = task_state.proxima_operacao(chave)
        assert op and op["ferramenta"] == "workspace" and op["operacao"] == "salvar"
        task_state.registrar_ferramenta(chave, "workspace", "success", f"OPERACAO=criar\nPATH={arquivo}\nACAO=CRIADO", op["operacao_id"])
        tarefa = task_state.carregar(chave)
        # Simula um LLM tentando trocar o Desktop/caminho; o arquivo conhecido vence.
        op2 = task_state.proxima_operacao(chave)
        assert op2 and op2["ferramenta"] == "workspace"
        args = task_state.normalizar_argumentos_operacao(
            tarefa, op2, {"operacao": "editar", "caminho": str(home / "Área de Trabalho" / "outro.txt"),
                          "procurar": "a", "substituir": "b"})
        assert args["caminho"] == arquivo

def test_contratos_tarefa_nao_expoe_wrappers_de_arquivos():
    from core import dispatch
    nomes = {x["function"]["name"] for x in dispatch.contratos_tarefa("Leia e edite o arquivo registro.txt") }
    assert "workspace" in nomes
    assert not ({"read_file", "write_file", "make_directory"} & nomes)



def test_workspace_ignora_caminho_inventado_quando_etapa_so_diz_o_arquivo():
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "v30-known-2", "")
        arquivo = str(Path(td) / "registro.txt")
        tarefa = task_state.iniciar_ou_continuar(chave, f"Crie o arquivo {arquivo}. Depois leia novamente o arquivo.")
        op = task_state.proxima_operacao(chave)
        task_state.registrar_ferramenta(chave, "workspace", "success", f"PATH={arquivo}\nACAO=CRIADO", op["operacao_id"])
        tarefa = task_state.carregar(chave)
        op2 = task_state.proxima_operacao(chave)
        args = task_state.normalizar_argumentos_operacao(
            tarefa, op2, {"operacao": "ler", "caminho": str(Path(td) / "casa.txt")})
        assert args["caminho"] == arquivo


def test_chamada_duplicada_em_tarefa_pede_replanejamento_estruturado():
    from types import SimpleNamespace
    from core import cognition
    with tempfile.TemporaryDirectory() as td:
        config.DB_PATH = str(Path(td) / "h.db")
        init_db.DB_PATH = config.DB_PATH
        task_state._SCHEMA_DONE = False
        init_db.init_database(verbose=False)
        chave = ("tui", "v30-replan", "")
        arquivo = str(Path(td) / "registro.txt")
        tarefa = task_state.iniciar_ou_continuar(chave, f"Leia o arquivo {arquivo}")
        frame = SimpleNamespace(
            tarefa_id=tarefa.id, etapas_pendentes=[tarefa.etapas[0]["texto"]],
            verificador_pendente="", ferramentas_esperadas=(),
            confianca_intencao=0.0, ferramenta_sugerida="", multi_etapa=False,
        )
        args = {"operacao": "ler", "caminho": arquivo}
        assinatura = cognition.assinatura_chamada("workspace", args)
        app = object.__new__(main.InterfaceHoshino)
        resultado = asyncio.run(app._executar_chamadas_da_etapa(
            [{"function": {"name": "workspace", "arguments": args}}], frame, 1,
            {assinatura}, chave_conversa=chave, canal="tui"))
        assert resultado and isinstance(resultado[0][2], dict)
        assert resultado[0][2]["controlador_replanejar"] is True
        assert resultado[0][2]["ok"] is False
