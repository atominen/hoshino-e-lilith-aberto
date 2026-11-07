#!/usr/bin/env bash
set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
cd "$ROOT" || exit 1
export HOSHINO_OLLAMA_URL="${HOSHINO_OLLAMA_URL:-http://127.0.0.1:11435/api/chat}"
export HOSHINO_OLLAMA_HOST="${HOSHINO_OLLAMA_HOST:-127.0.0.1:11435}"
export OLLAMA_HOST="$HOSHINO_OLLAMA_HOST"
export OLLAMA_MODELS="${HOSHINO_OLLAMA_MODELS:-$ROOT/compartilhado/modelos/ollama}"

ok=0; fail=0
check(){
  local name="$1"; shift
  if "$@" >/tmp/hoshino_v34_check.out 2>&1; then
    echo "[OK] $name"
    ok=$((ok+1))
  else
    echo "[FAIL] $name"
    cat /tmp/hoshino_v34_check.out
    fail=$((fail+1))
  fi
}

check "Python principal" "$PY" --version
check "Kokoro Python 3.12" "$VOICE_PY" -c 'import kokoro, soundfile; print(kokoro.__version__ if hasattr(kokoro,"__version__") else "kokoro ok")'
check "Vulkan RX 6650 XT" bash -lc 'vulkaninfo --summary 2>/dev/null | grep -q "AMD Radeon RX 6650 XT"'
check "sd-cli" test -x "$ROOT/compartilhado/servicos/stable-diffusion.cpp/build/bin/sd-cli"
check "Animagine checkpoint" test -f "$ROOT/compartilhado/modelos/imagem/cagliostrolab--animagine-xl-4.0/animagine-xl-4.0-opt.safetensors"
check "Ollama API" curl -fsS "${HOSHINO_OLLAMA_URL%/api/chat}/api/tags" >/dev/null
check "Qwen canônico" bash -lc 'ollama list | grep -q "Qwen3.5-9B-Uncensored-GGUF"'
check "Python compile" "$PY" -m compileall -q "$APP_DIR" "$ROOT/testes" "$ROOT/scripts"

echo
printf 'Resultado: %d OK, %d FAIL\n' "$ok" "$fail"
exit "$fail"
