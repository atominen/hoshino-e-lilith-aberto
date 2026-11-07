#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/ambiente.sh"
cd "$ROOT"
export HOSHINO_OLLAMA_URL="${HOSHINO_OLLAMA_URL:-http://127.0.0.1:11435/api/chat}"
export HOSHINO_OLLAMA_HOST="${HOSHINO_OLLAMA_HOST:-127.0.0.1:11435}"
export HOSHINO_OLLAMA_MODELS="${HOSHINO_OLLAMA_MODELS:-$ROOT/compartilhado/modelos/ollama}"

echo "== endpoint Hoshino =="
curl -fsS --max-time 4 "${HOSHINO_OLLAMA_URL%/api/chat}/api/tags" >/tmp/hoshino_tags.json
"$PY" -m json.tool /tmp/hoshino_tags.json | sed -n '1,80p'

echo "== modelo configurado =="
"$PY" - <<'PY'
import json, sys
import config
with open('/tmp/hoshino_tags.json', encoding='utf-8') as f:
    data=json.load(f)
models={str(x.get('name') or x.get('model') or '').lower() for x in data.get('models',[]) if isinstance(x,dict)}
print('config:', config.MODEL_NAME)
print('instalado:', config.MODEL_NAME.lower() in models)
if config.MODEL_NAME.lower() not in models:
    sys.exit(2)
PY

echo "== chat mínimo =="
"$PY" - <<'PY'
import requests, config
p={"model":config.MODEL_NAME,"messages":[{"role":"user","content":"Responda somente: OK"}],"stream":False,"think":False,"options":{"num_ctx":4096,"num_predict":16}}
r=requests.post(config.OLLAMA_URL,json=p,timeout=60)
print('status:',r.status_code)
print(r.text[:2000])
r.raise_for_status()
PY

echo "== áudio/transcritor =="
"$PY" - <<'PY'
from tools.transcricao import FonteDeAudio, Reconhecedor
import config
print('captura:', FonteDeAudio.backends_disponiveis())
print('motores:', Reconhecedor().disponiveis())
print('modelo:', config.WHISPER_MODELO)
print('beam:', config.WHISPER_BEAM_SIZE)
PY

echo "== compilação =="
"$PY" -m compileall -q "$APP_DIR"
echo "V36 OK"
