#!/usr/bin/env bash
set -euo pipefail
# SIGTERM pede drenagem/cancelamento ao worker; systemd contém seus filhos.
exec systemctl --user stop alistair-pc2.scope
