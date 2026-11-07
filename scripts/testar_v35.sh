#!/usr/bin/env bash
set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
cd "$ROOT" || exit 1

[[ -x "$PY" ]] || { echo "Ambiente principal ausente."; exit 1; }
export PYTHONUNBUFFERED=1

ok=0; fail=0; warn=0
check(){
  local name="$1"; shift
  if "$@" >/tmp/hoshino_v35_check.out 2>&1; then
    echo "[OK]   $name"; ok=$((ok+1))
  else
    echo "[FAIL] $name"; tail -15 /tmp/hoshino_v35_check.out; fail=$((fail+1))
  fi
}
warn_check(){
  local name="$1"; shift
  if "$@" >/tmp/hoshino_v35_warn.out 2>&1; then
    echo "[OK]   $name"; ok=$((ok+1))
  else
    echo "[WARN] $name"; tail -8 /tmp/hoshino_v35_warn.out; warn=$((warn+1))
  fi
}

check "Python principal" "$PY" --version
check "Sintaxe do núcleo" "$PY" -m compileall -q "$APP_DIR" testes scripts
check "Hardening V35" "$PY" testes/executar_isolado.py testes/test_v35_hardening.py
check "Diagnóstico" "$PY" testes/executar_isolado.py testes/test_diagnostico.py
check "Integração" "$PY" testes/executar_isolado.py testes/test_hoshino.py
check "Turno E2E" "$PY" testes/executar_isolado.py testes/test_turno_e2e.py
check "Tarefa operacional" "$PY" testes/executar_isolado.py testes/test_v28_tarefa_operacional.py

if [ -x "$VOICE_PY" ]; then
  check "Venv de voz" "$VOICE_PY" -c 'import kokoro, soundfile; print("Kokoro OK")'
else
  echo "[WARN] venv de voz ausente: voz não foi certificada nesta execução"; warn=$((warn+1))
fi

warn_check "API Ollama" curl -fsS "${HOSHINO_OLLAMA_URL%/api/chat}/api/tags"
warn_check "Vulkan" bash -lc 'command -v vulkaninfo >/dev/null && vulkaninfo --summary 2>/dev/null | grep -q "AMD Radeon RX 6650 XT"'
warn_check "sd-cli" test -x "$ROOT/compartilhado/servicos/stable-diffusion.cpp/build/bin/sd-cli"
warn_check "Animagine" test -f "$ROOT/compartilhado/modelos/imagem/cagliostrolab--animagine-xl-4.0/animagine-xl-4.0-opt.safetensors"

printf '\nResultado V35: %d OK, %d FAIL, %d WARN\n' "$ok" "$fail" "$warn"
exit "$fail"
