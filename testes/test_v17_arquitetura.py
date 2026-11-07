"""Testes das novas garantias de V17 sem exigir Ollama, Playwright ou desktop real."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from core import capabilities, dispatch, intent
from tools import browser, toolforge


def check(c, m):
    if not c:
        raise AssertionError(m)


def test_routing():
    q = "crie um arquivo teste.txt e depois execute um script"
    nomes = {x["function"]["name"] for x in dispatch.esquemas(q)}
    check("workspace" in nomes, f"workspace ausente: {nomes}")
    check(not (nomes & dispatch.LEGADOS_ARQUIVOS), "APIs legadas não devem ser públicas")
    check("execute_command" in nomes, f"execute_command ausente: {nomes}")
    q2 = "abra Firefox, depois abra o YouTube em uma nova aba"
    n2 = {x["function"]["name"] for x in dispatch.esquemas(q2)}
    check("abrir_aplicativo" in n2 and "browser_abrir" in n2, f"roteamento misto ausente: {n2}")
    check(intent.interpretar("abra o YouTube").ferramenta_principal == "browser_abrir", "YouTube não virou browser_abrir")
    check(intent.interpretar("abra a pasta ~/Downloads").ferramenta_principal == "abrir_pasta", "pasta não virou abrir_pasta")


def test_custom_tool_filter():
    original = toolforge._todas
    try:
        toolforge._todas = lambda: [
            {"nome": "conta_teste_v17", "descricao": "soma dois números", "ativa": True, "parametros": {"x": {"type": "number"}}, "obrigatorios": ["x"]},
            {"nome": "texto_teste_v17", "descricao": "transforma texto", "ativa": True, "parametros": {}, "obrigatorios": []},
        ]
        a = toolforge.esquemas_para_llm("use a conta_teste_v17", limite=8)
        check(a and a[0]["function"]["name"] == "propria_conta_teste_v17", f"ferramenta relevante não priorizada: {a}")
        b = toolforge.esquemas_para_llm("oi", limite=8)
        check(not b, "ferramentas próprias irrelevantes entraram numa conversa simples")
    finally:
        toolforge._todas = original
    check(not capabilities.info("propria_conta").requires_verification, "ferramenta própria ainda exige verificador inexistente")
    check(dispatch._resultado_mecanico("abrir_pasta", "A pasta não existe: /tmp/nao-existe")['status'] == "error",
          "erro de pasta não pode ser classificado como sucesso")
    check(dispatch._resultado_mecanico("propria_fantasma", "Não existe ferramenta própria chamada 'fantasma'")['status'] == "error",
          "erro de ferramenta própria não pode ser classificado como sucesso")
    check(dispatch._resultado_mecanico("consultar_conhecimento", "Não tenho nada registrado sobre Andrews")['status'] == "success",
          "consulta negativa continua sendo sucesso da consulta, não erro")


class FakePage:
    def __init__(self, name):
        self.name = name


class FakeContext:
    def __init__(self, pages):
        self.pages = pages


def test_stable_tabs():
    browser._STATE["page_ids"] = {}
    browser._STATE["pages"] = {}
    browser._STATE["next_page_id"] = 1
    browser._STATE["active_page_id"] = None
    a, b, c = FakePage("A"), FakePage("B"), FakePage("C")
    ctx = FakeContext([a, b, c])
    ida = browser._register_page(a)
    idb = browser._register_page(b)
    idc = browser._register_page(c)
    check((ida, idb, idc) == ("aba-01", "aba-02", "aba-03"), "IDs estáveis incorretos")
    ctx.pages.pop(0)
    check(browser._page(ctx, aba=idb) is b, "ID da aba B deixou de apontar para B após remover A")
    check(browser._page(ctx, aba=idc) is c, "ID da aba C deixou de apontar para C após remover A")


if __name__ == "__main__":
    test_routing(); test_custom_tool_filter(); test_stable_tabs()
    print("ok - V17 roteamento, ferramentas próprias e abas estáveis")
