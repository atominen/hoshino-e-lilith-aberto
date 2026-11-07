"""Testes locais da ferramenta Discord (sem token e sem conexão externa)."""
import os
import tempfile
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

import config
from social import channels
from tools import discord as discord_tool


def main():
    bus = tempfile.mkdtemp(prefix="hoshino_discord_test_")
    config.BUS_DIR = bus
    os.environ["HOSHINO_DISCORD_CONTATOS"] = "123456789012345678=Amigo;222222222222222222=Outro"
    channels.marcar_vivo("discord")

    contatos = discord_tool.listar_contatos()
    assert "amigo" in contatos.lower()
    assert "123456789012345678" in contatos

    diagnostico = discord_tool.diagnostico()
    assert "Discord diagnóstico:" in diagnostico
    assert "token=" in diagnostico

    discord_tool.registrar_usuario_observado("333333333333333333", username="andrews_konigstiger", display_name="Andrews", global_name="Andrews", destino="999")
    loc = discord_tool.localizar_usuario("andrews_konigstiger")
    assert '"id": "333333333333333333"' in loc
    assert "Andrews" in loc

    add = discord_tool.adicionar_contato("Andrews", "andrews_konigstiger")
    assert "Contato 'Andrews' salvo" in add

    r = discord_tool.enviar("Olá, amigo", "Amigo")
    assert "Mensagem colocada" in r
    pendentes = channels.pendentes_de_saida("discord")
    assert any(x["destino"] == "user:123456789012345678" for x in pendentes)
    for p in pendentes:
        channels.confirmar_entrega(p["id"])

    r2 = discord_tool.enviar("Olá, Andrews", "andrews_konigstiger")
    assert "Mensagem colocada" in r2
    pendentes = channels.pendentes_de_saida("discord")
    assert len(pendentes) == 1 and pendentes[0]["destino"] == "user:333333333333333333"
    channels.confirmar_entrega(pendentes[0]["id"])

    channels.publicar_entrada("discord", "Oi, Hoshino", autor="Andrews",
                              autor_id="333333333333333333", responder_para="999")
    entrada = channels.receber()
    assert entrada and entrada[0]["autor_id"] == "333333333333333333"

    del os.environ["HOSHINO_DISCORD_CONTATOS"]
    print("18 verificações Discord passaram")


if __name__ == "__main__":
    main()
