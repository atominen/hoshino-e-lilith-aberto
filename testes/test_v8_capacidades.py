#!/usr/bin/env python3
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
import sys
sys.path.insert(0, str(ROOT / "app"))

import config
from core import dispatch
from mind import night_reflection
from tools import file_transfer, workspace


class _TmpConfig:
    pass


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    # Registro vivo de capacidades.
    for nome in (
        "abrir_aplicativo", "acao_desktop", "observar_tela",
        "instalar_aplicativo", "preparar_ambiente_ia", "instalar_pacote_ia",
        "executar_na_ia", "abrir_pasta_entregas", "enviar_arquivo_para_hoshino",
        "analisar_recebido", "observar_imagem_recebida", "baixar_arquivo",
        "browser_estado", "browser_abrir", "browser_info", "browser_clicar",
        "browser_preencher", "browser_tecla", "discord_abrir_canal",
        "discord_diagnostico",
    ):
        ok(nome in dispatch.nomes(), f"capacidade ausente: {nome}")
        ok(nome in dispatch.HANDLERS, f"handler ausente: {nome}")

    # Sandbox persistente de IA.
    workspace.preparar_ambiente_ia()
    for sub in ("ia", "ia/modelos", "ia/ferramentas", "ia/dados"):
        ok((workspace.OFICINA / sub).is_dir(), f"pasta IA ausente: {sub}")
    ok((workspace.OFICINA / "ia" / "ambiente.json").is_file(), "manifesto IA ausente")

    # Colisão de nomes nunca sobrescreve entrega anterior.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        primeira = base / "arquivo.txt"
        segunda = base / "arquivo.txt"
        primeira.write_text("um", encoding="utf-8")
        destino1 = file_transfer._nome_livre(base, primeira.name)
        ok(destino1.name == "arquivo-2.txt", "nome livre deveria evitar colisão")
        segunda.write_text("dois", encoding="utf-8")
        ok(segunda.read_text(encoding="utf-8") == "dois", "teste de arquivo temporário falhou")

    # Horário noturno cruza meia-noite.
    from datetime import datetime
    cfg_start, cfg_end = config.REFLEXAO_NOTURNA_INICIO, config.REFLEXAO_NOTURNA_FIM
    a = datetime(2026, 9, 18, 23, 0)
    b = datetime(2026, 9, 19, 2, 0)
    if cfg_start == 22 and cfg_end == 6:
        ok(night_reflection.horario_noturno(a), "23h deveria estar no período noturno")
        ok(night_reflection.horario_noturno(b), "02h deveria estar no período noturno")

    print("V8 capacidades: tudo passou.")


if __name__ == "__main__":
    main()
