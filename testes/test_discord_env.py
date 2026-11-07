"""O arquivo de token é dado literal, nunca script shell."""
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from integracoes.discord_env import carregar


def main():
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "discord.env"
        arquivo.write_text(
            "# configuração\n"
            "export HOSHINO_DISCORD_TOKEN='token.literal'\n"
            "HOSHINO_DISCORD_CANAIS=123,456\n"
            "NAO_PERMITIDO=ignorar\n"
            "$(nao-execute-isso)\n", encoding="utf-8")
        valores, avisos = carregar(str(arquivo))
    assert valores == {"HOSHINO_DISCORD_TOKEN": "token.literal", "HOSHINO_DISCORD_CANAIS": "123,456"}
    assert len(avisos) == 2
    print("Configuração Discord: leitura literal confirmada.")


if __name__ == "__main__":
    main()
