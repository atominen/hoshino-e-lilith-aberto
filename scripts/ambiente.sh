#!/usr/bin/env bash
# Caminhos físicos: funciona também pelos atalhos legados de compatibilidade.
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd -P)"
APP_DIR="$ROOT/app"
export HOSHINO_ENTIDADE="${HOSHINO_ENTIDADE:-hoshino}"
ENTIDADE_DIR="$ROOT/entidades/$HOSHINO_ENTIDADE"
PY="$ROOT/compartilhado/ambientes/principal/bin/python"
VOICE_PY="$ROOT/compartilhado/ambientes/voz/bin/python"

ENV_FILE="$ENTIDADE_DIR/config/${HOSHINO_ENTIDADE}.env"
if [[ "$HOSHINO_ENTIDADE" == "hoshino" && ! -f "$ENV_FILE" ]]; then
  ENV_FILE="$ENTIDADE_DIR/config/hoshino_v32.env"
fi
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# Scripts absolutos em app/ não herdam o cwd no sys.path. O seletor de
# executores depende também de laboratorio/ e scripts/ na raiz do projeto.
export PYTHONPATH="$ROOT:$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$ROOT/compartilhado/ambientes/principal/bin:$PATH"
export HF_HOME="${HF_HOME:-$ROOT/compartilhado/modelos/huggingface}"
export HOSHINO_OLLAMA_URL="${HOSHINO_OLLAMA_URL:-http://127.0.0.1:11435/api/chat}"
export HOSHINO_OLLAMA_HOST="${HOSHINO_OLLAMA_HOST:-127.0.0.1:11435}"
export HOSHINO_OLLAMA_MODELS="${HOSHINO_OLLAMA_MODELS:-$ROOT/compartilhado/modelos/ollama}"
export OLLAMA_HOST="$HOSHINO_OLLAMA_HOST"
export OLLAMA_MODELS="$HOSHINO_OLLAMA_MODELS"
