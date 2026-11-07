#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js não encontrado. Instale com: sudo apt install nodejs npm"
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm não encontrado. Instale com: sudo apt install npm"
  exit 1
fi
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
if [ "${NODE_MAJOR:-0}" -lt 18 ]; then
  echo "Node.js >= 18 é necessário. Encontrado: $(node --version)"
  exit 1
fi

npm install

echo
echo "Ponte Minecraft instalada. Inicie com:"
echo "  ./start_bridge.sh"
