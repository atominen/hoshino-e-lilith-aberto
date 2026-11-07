"""Telemetria de recursos deve chegar ao freio de autonomia."""
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from core import kernel, situation


def main():
    agora = datetime(2026, 9, 18, 12, 0)
    sensores = {
        "janela_ativa": "Hoshino", "janelas": ["Hoshino"], "midia": {},
        "ociosidade_x11": 0, "load1": 1.2, "memoria_usada_pct": 41,
        "disco_usado_pct": 73, "disco_livre_gb": 120.5,
    }
    with patch.object(situation, "_memoria_curta", return_value={}), \
         patch.object(situation, "_gravar_memoria_curta"), \
         patch.object(situation, "ja_viu", return_value=True), \
         patch.object(situation, "_pendencias", return_value={}):
        estado = situation.atualizar(sensores, agora=agora)
    assert estado["carga"] == {
        "load1": 1.2, "memoria_usada_pct": 41,
        "disco_usado_pct": 73, "disco_livre_gb": 120.5,
    }
    assert kernel._recursos_saturados({"carga": {"memoria_usada_pct": 95}})
    assert kernel._recursos_saturados({"carga": {"disco_usado_pct": 98}})
    assert not kernel._recursos_saturados({"carga": estado["carga"]})
    print("Recursos do sistema: telemetria e freio confirmados.")


if __name__ == "__main__":
    main()
