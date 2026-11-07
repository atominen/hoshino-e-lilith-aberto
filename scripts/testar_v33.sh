#!/bin/bash
set -u
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
cd "$ROOT" || exit 1
echo '=== HOSHINO V33 CHECK ==='
echo '-- Python --'; "$PY" --version
echo '-- Ollama --'; ollama list
echo '-- Vulkan --'; vulkaninfo --summary 2>/dev/null | grep -E 'GPU0:|deviceName|driverName' | head -6 || true
echo '-- sd-cli --'; "$ROOT/compartilhado/servicos/stable-diffusion.cpp/build/bin/sd-cli" --list-devices || true
echo '-- Python imports --'
"$PY" - <<'PY'
import importlib.util
for m in ('faster_whisper','kokoro','soundfile','pygame'):
    print(f'{m}:', 'OK' if importlib.util.find_spec(m) else 'MISSING')
PY
echo '-- Compilação --'; "$PY" -m compileall -q "$APP_DIR" && echo OK
echo '-- Microfone --'; HOSHINO_AUDIO_DIARIZACAO=0 "$PY" testes/executar_isolado.py testes/test_escuta.py
