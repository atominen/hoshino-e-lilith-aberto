#!/usr/bin/env bash
# Painel da Central no PC2 (pedido humano 06/11): só a janela. Entidades, modelos e memórias ficam no PC1;
# o PC2 conversa com a Central do PC1 pela rede local.
#
# Uso:  bash instalar_painel_pc2.sh IP_DO_PC1 CODIGO [PORTA]
#
# O IP e o código aparecem na Central do PC1, em Configurações → "Painel no PC2 pela rede local"
# (ligue, salve e reabra a Central do PC1 uma vez). O botão "Copiar comando do PC2" já monta esta linha.
# Repositório privado: o git deste PC precisa estar autenticado na conta do GitHub.
set -euo pipefail

PC1="${1:-}"
CODIGO="${2:-}"
PORTA="${3:-8770}"
REPO="${HOSHINO_REPO:-https://github.com/atominen/hoshino-e-lilith.git}"
RAMO="${HOSHINO_RAMO:-main}"
DESTINO="${HOSHINO_PAINEL_DIR:-$HOME/hoshino-e-lilith-painel}"

if [[ -z "$PC1" || -z "$CODIGO" ]]; then
  echo "Uso: $0 IP_DO_PC1 CODIGO [PORTA]   (veja em Configurações na Central do PC1)" >&2
  exit 2
fi
if ! python3 - "$PC1" "$PORTA" 2>/dev/null <<'PY'
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
assert isinstance(ip, ipaddress.IPv4Address) and ip.is_private and not ip.is_loopback
assert 1024 < int(sys.argv[2]) < 65536
PY
then
  echo "Use o IP privado do PC1 na rede local (ex.: 10.0.0.102) e uma porta válida." >&2
  exit 2
fi

# 1. O painel só precisa do PyQt5 do sistema: nada de modelo, torch ou ambiente do projeto.
falta=()
python3 -c 'import PyQt5.QtWidgets' 2>/dev/null || falta+=(python3-pyqt5)
command -v git >/dev/null || falta+=(git)
command -v curl >/dev/null || falta+=(curl)
command -v paplay >/dev/null || falta+=(pulseaudio-utils)  # tocar a voz das entidades e gravar o microfone (parec)
# Sentidos deste PC para as entidades (06/11): apps abertos, tempo sem teclado/mouse, mídia tocando, janela ativa.
command -v wmctrl >/dev/null || falta+=(wmctrl)
command -v xprintidle >/dev/null || falta+=(xprintidle)
command -v playerctl >/dev/null || falta+=(playerctl)
command -v xprop >/dev/null || falta+=(x11-utils)
if ((${#falta[@]})); then
  echo "Instalando: ${falta[*]} (pede a senha do sudo)"
  sudo apt-get update -qq
  sudo apt-get install -y "${falta[@]}"
fi

# 2. Código pelo GitHub.
if [[ -d "$DESTINO/.git" ]]; then
  echo "Atualizando $DESTINO ($RAMO)…"
  git -C "$DESTINO" fetch --quiet origin "$RAMO"
  git -C "$DESTINO" checkout --quiet "$RAMO"
  git -C "$DESTINO" merge --quiet --ff-only "origin/$RAMO"
else
  echo "Baixando o projeto em $DESTINO ($RAMO)…"
  git clone --quiet --branch "$RAMO" "$REPO" "$DESTINO"
fi

# 3. Endereço e código do PC1, só para este usuário.
mkdir -p "$DESTINO/compartilhado/runtime/launcher"
( umask 077; printf 'http://%s:%s/#%s\n' "$PC1" "$PORTA" "$CODIGO" > "$DESTINO/compartilhado/runtime/launcher/central.url" )

# 4. Conferir a conexão antes de criar o atalho.
# Consulta autenticada e rápida (control/entities leva ~7 s na primeira vez; não serve de teste de conexão).
rc=0
status="$(curl -s -o /dev/null -w '%{http_code}' -m 20 -H "Authorization: Bearer $CODIGO" \
  "http://$PC1:$PORTA/api/control/gpu-alerts")" || rc=$?
case "$status" in
  200) echo "Conexão com a Central do PC1 confirmada." ;;
  403) echo "O PC1 recusou o código. Confira se copiou inteiro (Configurações → Copiar comando do PC2)." >&2; exit 1 ;;
  *) if [[ $rc -eq 7 ]]; then
       echo "O PC1 recusou a conexão em $PC1:$PORTA: a Central está fechada ou o acesso pela rede está desligado." >&2
     elif [[ $rc -eq 28 ]]; then
       echo "O PC1 não respondeu em $PC1:$PORTA em 20 s: confira o IP e o firewall do PC1" >&2
       echo "(sudo ufw allow from <rede>/24 to any port $PORTA proto tcp)." >&2
     else
       echo "Resposta inesperada do PC1: HTTP $status (curl $rc)." >&2
     fi
     exit 1 ;;
esac

# 5. Atalho no menu. Fechar esta janela fecha só o painel; a Central e as entidades seguem no PC1.
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/hoshino-e-lilith-painel.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Central Hoshino e Lilith (PC2)
Comment=Painel da Central do PC1 pela rede local
Exec=/usr/bin/python3 "$DESTINO/app/ui/central_native.py" --root "$DESTINO"
Icon=$DESTINO/desktop/hoshino-e-lilith.svg
Terminal=false
Categories=Utility;
DESKTOP
chmod 644 "$HOME/.local/share/applications/hoshino-e-lilith-painel.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Pronto. Abra 'Central Hoshino e Lilith (PC2)' no menu, ou rode:"
echo "  /usr/bin/python3 \"$DESTINO/app/ui/central_native.py\" --root \"$DESTINO\""
echo "Para atualizar depois: rode este script de novo com o mesmo IP e código."
