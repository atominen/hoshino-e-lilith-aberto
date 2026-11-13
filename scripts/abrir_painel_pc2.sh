#!/usr/bin/env bash
# Abre o painel da Central no PC2 depois de atualizar o código pelo GitHub (pedido humano 11/11).
#
# Toda vez que o atalho "Central Hoshino e Lilith (PC2)" é aberto:
#   1. busca o ramo no GitHub (até 20 s) e avança só se for avanço simples (--ff-only);
#   2. sem rede, sem acesso ao GitHub ou com alteração local no caminho, abre a versão que já está aqui;
#   3. abre a janela.
# O resultado de cada abertura fica em compartilhado/runtime/launcher/atualizacao-painel.log.
#
# Uso:  bash abrir_painel_pc2.sh                    abre (atualizando antes)
#       bash abrir_painel_pc2.sh --instalar-atalho  só (re)cria o atalho do menu apontando para este script
set -uo pipefail

DESTINO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAMO="${HOSHINO_RAMO:-main}"
LOG="$DESTINO/compartilhado/runtime/launcher/atualizacao-painel.log"

instalar_atalho() {
  local pasta="$HOME/.local/share/applications"
  mkdir -p "$pasta"
  cat > "$pasta/hoshino-e-lilith-painel.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Central Hoshino e Lilith (PC2)
Comment=Painel da Central do PC1 pela rede local (atualiza ao abrir)
Exec=/bin/bash "$DESTINO/scripts/abrir_painel_pc2.sh"
Icon=$DESTINO/desktop/hoshino-e-lilith.svg
Terminal=false
Categories=Utility;
DESKTOP
  chmod 644 "$pasta/hoshino-e-lilith-painel.desktop"
  command -v update-desktop-database >/dev/null && update-desktop-database "$pasta" 2>/dev/null || true
  echo "Atalho 'Central Hoshino e Lilith (PC2)' aponta para $DESTINO/scripts/abrir_painel_pc2.sh"
}

if [[ "${1:-}" == "--instalar-atalho" ]]; then
  instalar_atalho
  exit 0
fi

atualizar() {
  local antes depois atual
  antes="$(git -C "$DESTINO" rev-parse --short HEAD 2>/dev/null)" || { echo "sem git em $DESTINO: abrindo como está"; return; }
  atual="$(git -C "$DESTINO" symbolic-ref --short -q HEAD)"
  if [[ "$atual" != "$RAMO" ]]; then
    echo "no ramo '${atual:-destacado}', não em '$RAMO': abrindo $antes sem atualizar"; return
  fi
  # Sem pedir senha: aberto pelo menu não há terminal para responder.
  if ! GIT_TERMINAL_PROMPT=0 timeout 20 git -C "$DESTINO" fetch --quiet origin "$RAMO"; then
    echo "GitHub indisponível (rede ou credencial): abrindo a versão atual $antes"; return
  fi
  if ! git -C "$DESTINO" merge --quiet --ff-only "origin/$RAMO"; then
    echo "não deu para avançar sem mexer em alteração local: abrindo a versão atual $antes"; return
  fi
  depois="$(git -C "$DESTINO" rev-parse --short HEAD)"
  if [[ "$antes" != "$depois" ]]; then
    echo "atualizado $antes → $depois"
    command -v notify-send >/dev/null && notify-send "Central (PC2)" "Painel atualizado: $antes → $depois" 2>/dev/null || true
  else
    echo "já na última versão ($depois)"
  fi
}

mkdir -p "$(dirname "$LOG")"
{ printf '%s  ' "$(date '+%F %T')"; atualizar; } >>"$LOG" 2>&1
tail -n 200 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"

exec /usr/bin/python3 "$DESTINO/app/ui/central_native.py" --root "$DESTINO" "$@"
