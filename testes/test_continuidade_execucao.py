import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import unittest
from core import cognition

class ContinuidadeExecucaoTests(unittest.TestCase):
    def test_tarefa_com_pendencia_nao_pode_encerrar_turno(self):
        frame = cognition.CognitiveFrame(
            objetivo="tarefa longa", dominio="arquivo", complexidade="media",
            tarefa_id="ct-1", etapas_pendentes=["etapa 2"],
        )
        self.assertTrue(cognition.deve_continuar(frame))

    def test_tarefa_sem_pendencia_pode_encerrar(self):
        frame = cognition.CognitiveFrame(
            objetivo="tarefa concluida", dominio="arquivo", complexidade="media",
            tarefa_id="ct-1", etapas_pendentes=[],
        )
        self.assertFalse(cognition.deve_continuar(frame))

if __name__ == "__main__":
    unittest.main()
