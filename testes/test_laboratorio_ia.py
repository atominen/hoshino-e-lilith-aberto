"""Garante que o laboratório usa seu próprio venv dentro do isolamento."""
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from tools import workspace


def main():
    original = workspace.OFICINA
    try:
        with tempfile.TemporaryDirectory(prefix="hoshino_ia_") as temporario:
            workspace.OFICINA = Path(temporario) / "oficina"
            saida = workspace.executar_na_ia("import sys; print(sys.prefix)")
            assert "[oficina | código 0]" in saida, saida
            # Dentro do bwrap a oficina é montada em /workspace. A presença
            # deste prefixo prova que não caiu silenciosamente no Python-base.
            assert "/workspace/ia/venv" in saida, saida
            assert (workspace.OFICINA / "ia" / "ambiente.json").is_file()
            print("Laboratório IA: venv isolado confirmado.")
        # Mesmo grupo oficial inclui os contratos stdlib do Laboratório Neural;
        # nenhum treino/modelo/hardware é iniciado por descoberta automática.
        import unittest
        root=Path(__file__).resolve().parents[1]
        sys.path.insert(0,str(root))
        suite=unittest.defaultTestLoader.discover(str(root/'laboratorio/tests'),top_level_dir=str(root))
        result=unittest.TextTestRunner(verbosity=1).run(suite)
        assert result.wasSuccessful(), 'Contratos do Laboratório Neural falharam'
    finally:
        workspace.OFICINA = original


if __name__ == "__main__":
    main()
