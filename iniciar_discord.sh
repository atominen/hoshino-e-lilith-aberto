#!/bin/bash
set -euo pipefail
ROOT="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
source "$ROOT/scripts/ambiente.sh"
cd "$ROOT"

if [ ! -x "$PY" ]; then
  echo "ERRO: o ambiente Python principal não existe em compartilhado/ambientes/principal."
  exit 1
fi

ENV_FILE="$ENTIDADE_DIR/runtime/discord.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERRO: $ENV_FILE não existe."
  echo "Copie entidades/$HOSHINO_ENTIDADE/config/discord.env.example para entidades/$HOSHINO_ENTIDADE/runtime/discord.env e coloque o token do bot."
  exit 1
fi

# O adaptador lê este arquivo como dotenv restrito. Não use `source`: uma chave
# do Discord é dado, não código que este lançador deve executar.
exec "$PY" "$APP_DIR/integracoes/discord_bot.py" "$ENV_FILE"
