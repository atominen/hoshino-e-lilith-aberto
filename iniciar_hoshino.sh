#!/bin/bash
set -euo pipefail
ROOT="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
source "$ROOT/scripts/ambiente.sh"
cd "$ROOT" || exit 1
[[ -x "$PY" ]] || { echo "ERRO: ambiente principal não encontrado em compartilhado/ambientes/principal."; exit 1; }

if [[ "${1:-}" == "--verificar" ]]; then
  exec "$PY" -B - <<'PY'
from importlib.util import find_spec
from pathlib import Path
import config

root = Path(config.RAIZ).resolve()
required = (
    root / "app/main.py",
    Path(config.ENTIDADE_DIR) / "identity",
    Path(config.ENTIDADE_DIR) / "memory",
    Path(config.ENTIDADE_DIR) / "runtime",
    root / "compartilhado/ambientes/principal/bin/python",
    root / "compartilhado/ambientes/voz/bin/python",
    root / "compartilhado/servicos/minecraft/start_bridge.sh",
)
missing = [str(path.relative_to(root)) for path in required if not path.exists()]
missing += [f"dependência Python: {name}" for name in ("textual", "requests", "numpy") if find_spec(name) is None]
if missing:
    print("Verificação falhou: " + "; ".join(missing))
    raise SystemExit(1)
assert Path(config.RUNTIME_DIR).resolve() == Path(config.ENTIDADE_DIR).resolve() / "runtime", "runtime fora da entidade ativa"
assert Path(config.DB_PATH).resolve().is_relative_to(Path(config.ENTIDADE_DIR).resolve() / "memory"), "memória fora da entidade ativa"
print(f"Estrutura e ambiente de {config.ENTIDADE_NOME} verificados em: {root}")
print("Nenhum serviço, modelo, microfone ou interface foi iniciado.")
PY
elif [[ $# -gt 0 ]]; then
  echo "Uso: $0 [--verificar]"
  exit 2
fi

export HOSHINO_MODEL="${HOSHINO_MODEL:-hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M}"
# O descritor herdado mantém a reserva durante TODA a preparação, mesmo após
# o Python de admissão sair. O runner valida o inode e adota a mesma trava.
mkdir -p "$ROOT/entidades/$HOSHINO_ENTIDADE/runtime"
exec 9>>"$ROOT/entidades/$HOSHINO_ENTIDADE/runtime/entity.boot.lock"
export HOSHINO_ENTITY_LOCK_FD=9
"$PY" -B - <<'PY'
import config
from core.entity_admission import boot
with boot(config.RAIZ, config.ENTIDADE_ID):
    pass
PY
# Destino fixado antes de carregar qualquer motor. O Xbox/PC2 não precisa de
# daemon Ollama local nem dispara recuperação/treino para poder acordar.
ALISTAIR_REMOTE=0
if [[ "$HOSHINO_ENTIDADE" == "alistair" ]]; then
  ALISTAIR_REMOTE="$("$PY" -B - <<'PY'
import config
from core.alistair_execution import is_remote
print(int(is_remote(config.RAIZ)))
PY
)"
fi
# Reconstrói apenas executores ausentes no MESMO worker do laboratório. Nunca
# baixa pesos nem acorda outras entidades; falha pendente interrompe o boot.
if [[ "$ALISTAIR_REMOTE" == 0 && -d "$ROOT/laboratorio-local" ]]; then
  PYTHONPATH="$ROOT:$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PY" -B -m laboratorio.recuperacao_modelos ensure \
    --home "$ROOT/laboratorio-local" --project "$ROOT" --entity "$HOSHINO_ENTIDADE" --confirm --wait
fi
# Recuperação pode ter promovido a última estável enquanto aguardávamos. Ler
# novamente o seletor existente; não conservar um override herdado já obsoleto.
HOSHINO_NEURAL9B_MODEL="$("$PY" -B - <<'PY'
import os
from core.neural9b_modes import startup_override
import config
print(startup_override(config.RAIZ, os.environ['HOSHINO_ENTIDADE']) or '')
PY
)"
# O ambiente do projeto carrega .env acima. A seleção neural tem precedência
# somente nesta instância e nunca escreve nos arquivos originais.
if [[ -n "${HOSHINO_NEURAL9B_MODEL:-}" ]]; then
  # startup_override verificou identidade, manifesto pinado e recibo físico.
  export HOSHINO_MODEL="$HOSHINO_NEURAL9B_MODEL"
fi
unset HOSHINO_NEURAL9B_MODEL
export HOSHINO_CONTEXT_TOKENS="$("$PY" -B - <<'PY'
import os,config
from core.neural9b_modes import context_limit
print(min(int(os.environ.get('HOSHINO_CONTEXT_TOKENS','16384')),context_limit(config.RAIZ,os.environ['HOSHINO_ENTIDADE'])))
PY
)"
export HOSHINO_NUM_PREDICT="$(( ${HOSHINO_NUM_PREDICT:-4096} < HOSHINO_CONTEXT_TOKENS - 512 ? ${HOSHINO_NUM_PREDICT:-4096} : HOSHINO_CONTEXT_TOKENS - 512 ))"
export HOSHINO_AUDIO_CONTINUO="${HOSHINO_AUDIO_CONTINUO:-1}"
export HOSHINO_AUDIO_DIARIZACAO="${HOSHINO_AUDIO_DIARIZACAO:-0}"
export HOSHINO_IMAGE_BACKEND="${HOSHINO_IMAGE_BACKEND:-te=cpu,diffusion=vulkan0,vae=cpu}"
export HOSHINO_IMAGE_PARAMS_BACKEND="${HOSHINO_IMAGE_PARAMS_BACKEND:-te=cpu,diffusion=cpu,vae=cpu}"
export HOSHINO_IMAGE_MAX_VRAM_GIB="${HOSHINO_IMAGE_MAX_VRAM_GIB:-7.0}"

# Voz: Kokoro usa seu próprio ambiente Python 3.12.
if [[ "$HOSHINO_ENTIDADE" != "alistair" ]]; then
if [[ ! -x "$VOICE_PY" ]]; then
  echo "ERRO: ambiente de voz não encontrado: $VOICE_PY"
  echo "Crie-a com Python 3.12 e instale kokoro==0.9.4 nela."
  exit 1
fi
if ! "$VOICE_PY" -c 'import kokoro, soundfile; print("Kokoro: OK")'; then
  echo "ERRO: Kokoro não está funcional no ambiente de voz."
  exit 1
fi
fi

# Ollama da Hoshino: um único endpoint e um único diretório de modelos.
# Não use o ~/.ollama do sistema como armazenamento da Hoshino. Isso evita que
# um segundo daemon em 11434 seja confundido com o daemon do projeto.
export HOSHINO_OLLAMA_URL="${HOSHINO_OLLAMA_URL:-http://127.0.0.1:11435/api/chat}"
export HOSHINO_OLLAMA_HOST="${HOSHINO_OLLAMA_HOST:-127.0.0.1:11435}"
export HOSHINO_OLLAMA_MODELS="${HOSHINO_OLLAMA_MODELS:-$ROOT/compartilhado/modelos/ollama}"
export OLLAMA_HOST="$HOSHINO_OLLAMA_HOST"
export OLLAMA_MODELS="$HOSHINO_OLLAMA_MODELS"
# Mesmo backend Vulkan da preparação inicial. A reserva/concorrência continua
# sob o Resource Manager; num_gpu=0 ainda força o fallback CPU.
export OLLAMA_VULKAN="${OLLAMA_VULKAN:-1}"
export OLLAMA_NOPRUNE=1
if [[ "$ALISTAIR_REMOTE" == 1 ]]; then
  # O cliente remoto lê os recibos pinados do seletor existente, em laboratorio/.
  # Execução de um script app/ não inclui automaticamente a raiz no sys.path.
  export PYTHONPATH="$ROOT:$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"
  exec "$PY" "$APP_DIR/alistair_runner.py"
fi
OLLAMA_RUNTIME_DIR="$ROOT/compartilhado/runtime/ollama/$HOSHINO_ENTIDADE"
mkdir -p "$OLLAMA_MODELS" "$OLLAMA_RUNTIME_DIR"

if ! curl -fsS --max-time 2 "${HOSHINO_OLLAMA_URL%/api/chat}/api/tags" >/dev/null 2>&1; then
  echo "Modelo de $HOSHINO_ENTIDADE parado; iniciando em $HOSHINO_OLLAMA_HOST ..."
  nohup ollama serve >"$OLLAMA_RUNTIME_DIR/server.log" 2>&1 < /dev/null 9>&- &
  echo $! > "$OLLAMA_RUNTIME_DIR/ollama.pid"
  for i in {1..30}; do
    curl -fsS --max-time 1 "${HOSHINO_OLLAMA_URL%/api/chat}/api/tags" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

if ! curl -fsS --max-time 3 "${HOSHINO_OLLAMA_URL%/api/chat}/api/tags" >/dev/null 2>&1; then
  echo "ERRO: modelo de $HOSHINO_ENTIDADE não respondeu em $HOSHINO_OLLAMA_URL"
  echo "Verifique: $OLLAMA_RUNTIME_DIR/server.log"
  exit 1
fi

if [[ "$HOSHINO_ENTIDADE" == "alistair" ]]; then
  exec "$PY" "$APP_DIR/alistair_runner.py"
fi

SDCLI="${HOSHINO_IMAGE_SD_CLI:-$ROOT/compartilhado/servicos/stable-diffusion.cpp/build/bin/sd-cli}"
if [[ -x "$SDCLI" ]]; then
  echo "Imagem GPU: OK ($SDCLI)"
else
  echo "AVISO: sd-cli não encontrado em $SDCLI; geração de imagem ficará indisponível."
fi

"$PY" "$APP_DIR/memory/sqlite/init_db.py"
exec "$PY" "$APP_DIR/entity_runner.py"
