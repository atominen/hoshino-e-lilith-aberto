#!/bin/bash
set -euo pipefail
ROOT="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
cd "$ROOT"
source "$ROOT/scripts/ambiente.sh"
export HOSHINO_RUNTIME_DIR="$ENTIDADE_DIR/runtime"
exec bash "$ROOT/compartilhado/servicos/minecraft/start_bridge.sh"
