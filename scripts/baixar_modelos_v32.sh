#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
cd "$ROOT"
export HF_HOME="${HF_HOME:-$ROOT/compartilhado/modelos/huggingface}"
export HOSHINO_OLLAMA_HOST="${HOSHINO_OLLAMA_HOST:-127.0.0.1:11435}"
export OLLAMA_HOST="$HOSHINO_OLLAMA_HOST"
export OLLAMA_MODELS="${HOSHINO_OLLAMA_MODELS:-$ROOT/compartilhado/modelos/ollama}"
mkdir -p "$OLLAMA_MODELS"

mkdir -p "$ROOT/compartilhado/modelos/imagem" "$ROOT/compartilhado/modelos/voz" "$ENTIDADE_DIR/runtime/voice" "$ENTIDADE_DIR/runtime/imagens"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERRO: Ollama não encontrado no PATH."
  exit 1
fi

echo "== 1/4: modelo conversacional =="
ollama pull 'hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M'

echo "== 2/4: ouvido (Whisper large-v3) =="
"$PY" - <<'PY'
from faster_whisper import WhisperModel
print('Baixando/validando Systran/faster-whisper-large-v3...')
WhisperModel('large-v3', device='cpu', compute_type='int8')
print('OK')
PY

echo "== 3/4: voz local Kokoro CPU =="
"$VOICE_PY" - <<'PY'
from huggingface_hub import snapshot_download
repo = 'hexgrad/Kokoro-82M'
print(f'Baixando/validando {repo}...')
snapshot_download(repo)
print('OK')
PY

echo "== 4/4: imagem Animagine XL 4.0 =="
"$PY" - <<'PY'
from pathlib import Path
import config
from huggingface_hub import hf_hub_download
p = hf_hub_download(
    repo_id='cagliostrolab/animagine-xl-4.0',
    filename='animagine-xl-4.0-opt.safetensors',
    local_dir=str(Path(config.RAIZ) / 'compartilhado/modelos/imagem/cagliostrolab--animagine-xl-4.0'),
)
print(p)
PY

echo
cat <<'TXT'
Modelos principais baixados/validados.

Diarização pyannote ainda exige aceite dos termos no Hugging Face. Depois de
aceitar e exportar HOSHINO_HF_TOKEN, valide com:

  ./compartilhado/ambientes/principal/bin/python - <<'PY2'
  import os
  from pyannote.audio import Pipeline
  Pipeline.from_pretrained('pyannote/speaker-diarization-community-1', token=os.environ['HOSHINO_HF_TOKEN'])
  print('Diarização validada')
  PY2

A Hoshino também tenta carregar o pipeline na primeira escuta.
TXT
