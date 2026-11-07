import os
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.chdir(ROOT)

from core import conversation, intent, task_state  # noqa: E402


def test_nao_sei_nao_e_correcao():
    assert not conversation.parece_correcao("não sei como faço isso")
    assert conversation.parece_correcao("não quero que faça isso")


def test_criar_ferramenta_e_intencao_explicita():
    i = intent.interpretar("crie uma ferramenta para contar palavras")
    assert i.ferramenta_principal == "criar_ferramenta"
    assert i.confianca >= 0.95


def test_nome_de_arquivo_nao_vira_etapa_teste():
    partes = task_state.decompor("crie um arquivo teste.txt")
    assert partes == ["crie um arquivo teste.txt"]


def test_retomada_nao_reabre_concluida(tmp_path):
    import config
    from core import dispatch
    old = config.DB_PATH
    config.DB_PATH = str(tmp_path / "t.db")
    task_state._SCHEMA_DONE = False
    try:
        key = ("tui", "local", "")
        tarefa = task_state.iniciar_ou_continuar(key, "crie um arquivo teste.txt")
        assert tarefa and tarefa.status == "active"
        arquivo = tmp_path / "teste.txt"
        recibo = dispatch.executar_resultado(
            "workspace", {"operacao": "salvar", "caminho": str(arquivo), "conteudo": "teste"}
        )
        assert recibo["verified"] and arquivo.read_text() == "teste"
        concluida = task_state.registrar_ferramenta(
            key, "workspace", recibo["status"], recibo["output"], recibo=recibo
        )
        assert concluida and concluida.status == "completed"
        # Uma tarefa concluída não pode ser ressuscitada por "continue".
        assert task_state.carregar(key) is None
        assert task_state.carregar_ultimo(key) is None
        assert task_state.iniciar_ou_continuar(key, "continue") is None
    finally:
        config.DB_PATH = old
        task_state._SCHEMA_DONE = False


if __name__ == "__main__":
    test_nao_sei_nao_e_correcao()
    test_criar_ferramenta_e_intencao_explicita()
    test_nome_de_arquivo_nao_vira_etapa_teste()
    with TemporaryDirectory() as pasta:
        test_retomada_nao_reabre_concluida(Path(pasta))
    print("4 testes de estabilidade passaram")
