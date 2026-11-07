from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import config
from core import capabilities, dispatch, task_state
from main import InterfaceHoshino
from memory.sqlite import init_db
from mind import psych_state
from tools import primitives


def ok(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f"ok - {name}")


# Primitivas determinísticas.
ok("cálculo aritmético", "RESULTADO=21" in primitives.calcular("3 * 7"))
ok("cálculo bloqueia código", primitives.calcular("__import__('os').system('id')").startswith("ERRO_CALCULO:"))
r = primitives.sortear("dados", 2, 6)
ok("dois dados válidos", all(1 <= int(x) <= 6 for x in r.split("RESULTADOS=")[1].split(" SOMA=")[0].split(",")))
moeda = primitives.sortear("moeda")
ok("moeda válida", "RESULTADOS=cara" in moeda or "RESULTADOS=coroa" in moeda)

# Roteamento explícito.
def nomes(texto):
    return [x["function"]["name"] for x in dispatch.contratos_tarefa(texto, limite=10)]

ok("jogo genérico não vira xadrez", not ({"jogar_xadrez", "estado_partida"} & set(nomes("Crie um jogo simples"))))
ok("xadrez explícito mantém xadrez", "jogar_xadrez" in nomes("Comece uma partida de xadrez"))
ok("dados roteiam para sorteio", "sortear" in nomes("Role dois dados de 6 lados"))
ok("imagem roteia para gerador", "gerar_imagem" in nomes("Gere uma imagem do jogo"))
ok("matemática roteia para calculadora", "calcular" in nomes("Calcule 18 + 3"))
ok("arquivo roteia para workspace", "workspace" in nomes("Crie um arquivo teste.txt"))

ok("validação não dispara novo sorteio", "sortear" not in nomes("Valide os resultados, os dados, a moeda e a imagem já gerada."))
ok("imagem não dispara shell", "execute_command" not in nomes("Gere uma imagem dos três desafios e execute a capacidade de geração disponível."))

# Contratos obrigatórios da macroetapa: a inteligência do modelo pode planejar,
# mas não pode apagar uma operação determinística exigida pelo texto.
app = object.__new__(InterfaceHoshino)
req = app._ferramentas_obrigatorias_da_etapa
ok("21 exige execução + cálculo + síntese", {"execute_command", "calcular", "__modelo__"} <= req("Implemente uma rodada jogável de 21; explique as regras e valide matematicamente o resultado."))
ok("dados exigem sorteio + cálculo", {"sortear", "calcular", "__modelo__"} <= req("Role dois dados, informe a soma e valide a soma."))
ok("imagem exige gerador", "gerar_imagem" in req("Gere uma imagem dos três desafios."))
ok("validação de imagem usa consulta, não nova geração", {"estado_imagem", "__modelo__"} <= req("Valide se a imagem foi realmente gerada."))
ok("relatório final é cognitivo", not req("Apresente o relatório final com resultados e validações."))

pedido_url = ("Prazer, Hoshino! Vamos começar com um passo pequeno: abra https://www.youtube.com "
              "no navegador usando sua ferramenta existente. Não faça login, não toque vídeo ainda "
              "e não use voz. Confira o que realmente aconteceu; se só conseguiu solicitar a abertura, "
              "diga isso sem inventar que viu a página.")
ok("abrir URL e conferir mantém ação externa", req(pedido_url) == {"browser_abrir", "__modelo__"})
ok("URL no navegador não vira abrir aplicativo", task_state._detectar_ferramentas(pedido_url) == ["browser_abrir"])
for texto in ("Não abra https://www.youtube.com. Confira a instrução.",
              'Ele disse "abra https://www.youtube.com". Explique a frase.',
              "Se eu disser abra https://www.youtube.com, explique o que faria.",
              "Confira se a explicação está correta."):
    ok("menção não obriga abertura: " + texto, "browser_abrir" not in req(texto))

# Planner deve injetar ferramentas obrigatórias mesmo quando o dispatch heurístico
# não encontrar um candidato com a mesma palavra exata.
with tempfile.TemporaryDirectory() as td:
    old_db = config.DB_PATH
    config.DB_PATH = str(Path(td) / "planner.db")
    init_db.DB_PATH = config.DB_PATH
    task_state._SCHEMA_DONE = False
    init_db.init_database(verbose=False)
    chave = ("test", "planner", "required")
    tarefa = task_state.iniciar_ou_continuar(
        chave,
        "Implemente uma rodada jogável de 21; explique as regras e valide matematicamente o resultado.",
    )
    app = object.__new__(InterfaceHoshino)

    async def fake_modelo(*args, **kwargs):
        return {
            "content": json.dumps({
                "operacoes": [{
                    "ferramenta": "execute_command",
                    "instrucao": "implementar e executar uma rodada simples de 21",
                }],
                "concluida": False,
            })
        }

    app.chamar_modelo = fake_modelo
    ok_plano, erro = asyncio.run(app._planejar_operacoes_de_tarefa(tarefa))
    atual = task_state.carregar(chave)
    ops = [str(x.get("ferramenta")) for x in (atual.etapas[0].get("operacoes_lista") or [])] if atual else []
    ok("planner injeta calcular e modelo ausentes", ok_plano and not erro and ops[:1] == ["execute_command"] and "calcular" in ops and "__modelo__" in ops)

    async def fake_so_texto(*args, **kwargs):
        return {"content": json.dumps({"operacoes": [{"ferramenta": "__modelo__", "instrucao": "explicar resultado"}], "concluida": False})}

    chave_url = ("test", "planner", "url")
    tarefa_url = task_state.iniciar_ou_continuar(chave_url, pedido_url)
    app.chamar_modelo = fake_so_texto
    planejado, erro = asyncio.run(app._planejar_operacoes_de_tarefa(tarefa_url))
    ops_url = [x['ferramenta'] for x in task_state.carregar(chave_url).etapas[0]['operacoes_lista']]
    ok("planner não troca abertura por promessa textual", planejado and not erro and ops_url == ['browser_abrir', '__modelo__'])

    async def fake_vazio(*args, **kwargs):
        return {"content": json.dumps({"operacoes": [], "concluida": True})}

    app.chamar_modelo = fake_vazio
    planejado, erro = asyncio.run(app._planejar_operacoes_de_tarefa(tarefa_url))
    ok("planner vazio não declara tarefa externa concluída", not planejado and bool(erro))
    config.DB_PATH = old_db
    task_state._SCHEMA_DONE = False

# TTS padrão coerente com CPU.
ok("TTS Kokoro CPU", config.TTS_BACKEND == "kokoro" and "Kokoro" in config.TTS_MODEL and config.TTS_DEVICE == "cpu")

# Estado psicológico adaptativo.
with tempfile.TemporaryDirectory() as td:
    old = config.RUNTIME_DIR
    config.RUNTIME_DIR = td
    e0 = psych_state.estado()
    psych_state.aplicar_evento("tarefa_falhou_de_novo", 1.0)
    e1 = psych_state.estado()
    ok("estado psicológico reage a falha", e1["estresse_acumulado"] > e0["estresse_acumulado"])
    ok("carga não resolvida reage", e1["carga_nao_resolvida"] > e0["carga_nao_resolvida"])
    ok("bloco psicológico existe", bool(psych_state.bloco_para_prompt()))
    config.RUNTIME_DIR = old

# Workspace canônico.
ok("minha workspace aponta para oficina", task_state._inferir_workspace_root("Na minha workspace crie o arquivo teste.txt") == str(Path(config.OFICINA_DIR).resolve()))

# Estado de imagem é assíncrono e não deve ser concluído em queued/running.
with tempfile.TemporaryDirectory() as td:
    old_db = config.DB_PATH
    config.DB_PATH = str(Path(td) / "tasks.db")
    task_state._SCHEMA_DONE = False
    from memory import sqlite as _dbmod  # compatibilidade com pacote presente
    from memory.sqlite import init_db
    init_db.DB_PATH = config.DB_PATH
    init_db.init_database(verbose=False)
    chave = ("test", "melhorias", "img")
    tarefa = task_state.iniciar_ou_continuar(chave, "Gere uma imagem e depois confirme.")
    task_state.definir_operacoes(chave, [{"id":"img-1","ferramenta":"gerar_imagem","instrucao":"gere a imagem"}])
    task_state.registrar_ferramenta(chave, "gerar_imagem", "success", "JOB_ID=img-1 STATUS=queued", "img-1")
    t = task_state.carregar(chave)
    op = task_state.proxima_operacao(chave)
    ok("verificador de imagem criado", op and op["ferramenta"] == "estado_imagem")
    task_state.registrar_ferramenta(chave, "estado_imagem", "success", "STATUS=running JOB_ID=img-1", op["operacao_id"])
    op2 = task_state.proxima_operacao(chave)
    ok("imagem running permanece pendente", op2 and op2["ferramenta"] == "estado_imagem")
    task_state.registrar_ferramenta(chave, "estado_imagem", "success", "STATUS=done PATH=/tmp/x.png JOB_ID=img-1", op2["operacao_id"])
    restante = task_state.proxima_operacao(chave)
    ok("imagem done fecha verificador", not (restante and restante.get("ferramenta") == "estado_imagem"))
    config.DB_PATH = old_db
    task_state._SCHEMA_DONE = False

# Self-model mantém identidade estável separada do estado adaptativo.
d = json.loads(Path(config.SELF_MODEL_PATH).read_text(encoding="utf-8"))
# 05/11: v9 acrescenta o jeito de partida da Hoshino; a estrutura da v8 continua exigida.
ok("self-model v8 ou posterior", isinstance(d.get("version"), int) and d["version"] >= 8)
ok("self-model explicita camadas adaptativas", any("estado psicológico" in x for x in d.get("cognitive_framework", [])))

print("MELHORIAS_EXECUCAO_OK")
