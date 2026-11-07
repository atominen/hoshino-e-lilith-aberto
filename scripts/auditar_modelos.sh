#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
cd "$ROOT"
export HOSHINO_OLLAMA_URL="${HOSHINO_OLLAMA_URL:-http://127.0.0.1:11435/api/chat}"
export HOSHINO_OLLAMA_HOST="${HOSHINO_OLLAMA_HOST:-127.0.0.1:11435}"
export OLLAMA_HOST="$HOSHINO_OLLAMA_HOST"
export OLLAMA_MODELS="${HOSHINO_OLLAMA_MODELS:-$ROOT/compartilhado/modelos/ollama}"
CANONICAL="${HOSHINO_MODEL:-hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M}"
echo "endpoint: ${HOSHINO_OLLAMA_URL}"
echo "armazenamento: ${OLLAMA_MODELS}"
echo "modelo canônico: ${CANONICAL}"
echo
ollama list || true
echo
echo "Arquivos grandes fora do armazenamento Ollama (apenas auditoria):"
find "$ROOT" -type f -size +100M -not -path "$ROOT/compartilhado/modelos/ollama/*" -not -path "$ROOT/entidades/hoshino/workspace/ia/venv/*" -not -path "$ROOT/compartilhado/ambientes/*" -printf '%p %s bytes\n' 2>/dev/null | sort -k2nr | head -40 || true
