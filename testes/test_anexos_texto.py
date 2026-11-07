"""Verifica que anexos textuais entram no contexto sem aceitar binários grandes."""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from tools import vision


class Resposta:
    def __init__(self, dados: bytes, tamanho=None):
        self.dados = dados
        self.headers = {"Content-Length": str(len(dados) if tamanho is None else tamanho)}

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=1):
        for inicio in range(0, len(self.dados), chunk_size):
            yield self.dados[inicio:inicio + chunk_size]


def main():
    assert vision.parece_texto("https://exemplo.test/notas.md?x=1")
    assert vision.parece_texto("https://exemplo.test/dados.json")
    assert not vision.parece_texto("https://exemplo.test/relatorio.pdf")
    with patch("core.rede.exigir", return_value=(True, "")), \
         patch.object(vision.requests, "get", return_value=Resposta(b"# titulo\nconteudo")):
        assert vision.baixar_texto_url("https://exemplo.test/notas.md") == "# titulo\nconteudo"
    with patch("core.rede.exigir", return_value=(True, "")), \
         patch.object(vision.requests, "get", return_value=Resposta(b"abc", tamanho=vision.ANEXO_TEXTO_MAX_BYTES + 1)):
        try:
            vision.baixar_texto_url("https://exemplo.test/grande.txt")
            raise AssertionError("anexo grande deveria ser recusado")
        except ValueError:
            pass
    print("Anexos textuais: leitura limitada confirmada.")


if __name__ == "__main__":
    main()
