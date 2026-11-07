#!/usr/bin/env bash
set -euo pipefail
PACOTE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$PACOTE_DIR"
export PYTHONDONTWRITEBYTECODE=1
python3 verificar_pc2.py
if [[ ! -f worker.json ]]; then
  python3 configurar_pc2.py
fi
if [[ ! -f /sys/fs/cgroup/cgroup.controllers ]]; then
  echo "Sem cgroup v2: limites rígidos não estão disponíveis. Nada foi iniciado."
  exit 1
fi
# Scope dedicado: inclui daemon e runners filhos; parar não atinge outros Ollamas.
# Falha nos limites/serviço do usuário não inicia uma cópia sem proteção.
exec systemd-run --user --scope --unit=alistair-pc2 \
  -p MemoryMax=7G -p MemorySwapMax=0 -p CPUQuota=150% -p Nice=10 \
  python3 -B pc2_node.py
