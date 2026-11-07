"""Controle de integração só chama unidades fixas do usuário."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import integracoes


def test_estado_de_unidade_normaliza_saida():
    with patch.object(integracoes, "_executar", return_value=(3, "inactive\n")):
        assert integracoes._estado_unidade("hoshino-discord.service") == "inactive"


def test_iniciar_usa_unidade_fixa_e_confirma_estado():
    with patch.object(integracoes, "_estado_unidade", side_effect=["inactive", "active"]), \
         patch.object(integracoes, "_executar", return_value=(0, "ok")) as executar:
        resultado = integracoes._iniciar_unidade("hoshino-discord.service", ["/bin/true"], "Discord")
    assert "confirmado ativo" in resultado
    comando = executar.call_args.args[0]
    assert comando[:5] == ["systemd-run", "--user", "--unit", "hoshino-discord", "--collect"]


def test_minecraft_sem_dependencia_nao_inicia():
    with TemporaryDirectory() as pasta, patch.object(integracoes.config, "MINECRAFT_DIR", Path(pasta)):
        assert "Minecraft não foi iniciado" in integracoes.iniciar_minecraft()


if __name__ == "__main__":
    test_estado_de_unidade_normaliza_saida()
    test_iniciar_usa_unidade_fixa_e_confirma_estado()
    test_minecraft_sem_dependencia_nao_inicia()
    print("3 testes de integração passaram")
