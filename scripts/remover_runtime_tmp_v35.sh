#!/usr/bin/env bash
set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
find "$ENTIDADE_DIR/workspace/tmp" -maxdepth 1 -type f -name 'exec_*.py' -delete
find "$ENTIDADE_DIR/workspace/tmp" -maxdepth 1 -type f -name 'exec_*.pyc' -delete
printf 'Temporários quebrados removidos da área de trabalho da Hoshino.\n'
