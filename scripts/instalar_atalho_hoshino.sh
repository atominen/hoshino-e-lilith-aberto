#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd -P)"
APP_DIR="${HOME}/.local/share/applications"
DESKTOP="${APP_DIR}/Hoshino.desktop"
ICON_DIR="${ROOT}/desktop"

mkdir -p "$APP_DIR"

cat > "$DESKTOP" <<EOD
[Desktop Entry]
Version=1.0
Type=Application
Name=Hoshino
Comment=Iniciar a Interface Hoshino
Exec="${ROOT}/iniciar_hoshino.sh"
Path=${ROOT}
Icon=${ICON_DIR}/hoshino.svg
Terminal=true
Categories=Utility;Development;
StartupNotify=true
EOD

chmod +x "${ROOT}/iniciar_hoshino.sh"
chmod +x "$DESKTOP"

# Compatibilidade com menus que mantém cache local.
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" || true

echo "Atalho instalado: $DESKTOP"
echo "Projeto: $ROOT"
