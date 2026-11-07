#!/usr/bin/env bash
# Desktop leve no PC1 (pedido humano 06/11): sobra mais VRAM para os modelos.
#
# Medido em 06/11: o Cinnamon (compositor muffin) ocupa 137–168 MiB na placa de 8 GB, e com a Lilith em
# 33 camadas faltaram 182 MiB. O Xfce com o compositor desligado não desenha com a GPU: fica só o
# framebuffer do servidor gráfico. O Cinnamon continua instalado; a sessão é escolhida na tela de login.
#
# Uso (no seu terminal, porque o sudo pede senha):  bash scripts/instalar_desktop_leve.sh
set -euo pipefail

pacotes=(
  xfce4-session   # sessão
  xfwm4           # gerenciador de janelas (compositor desligado abaixo)
  xfce4-panel     # barra com menu e relógio
  xfce4-settings  # monitores, teclado, aparência
  xfce4-terminal  # onde o Claude Code roda
  xfce4-notifyd   # notificações (alerta de VRAM da Central)
  thunar          # arquivos, se precisar
)
echo "Instalando o Xfce mínimo: ${pacotes[*]}"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends "${pacotes[@]}"

# Compositor desligado desde a primeira sessão (sem efeitos de transparência/sombra = sem uso de GPU).
conf="$HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
mkdir -p "$conf"
if [[ -f "$conf/xfwm4.xml" ]]; then
  if command -v xfconf-query >/dev/null && [[ "${XDG_CURRENT_DESKTOP:-}" == *XFCE* ]]; then
    xfconf-query -c xfwm4 -p /general/use_compositing -s false
  else
    sed -i 's#name="use_compositing" type="bool" value="true"#name="use_compositing" type="bool" value="false"#' "$conf/xfwm4.xml"
  fi
else
  cat > "$conf/xfwm4.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="use_compositing" type="bool" value="false"/>
  </property>
</channel>
XML
fi

echo
echo "Pronto. Para usar:"
echo "  1. Feche a Central com 'Encerrar com segurança' e saia da sessão."
echo "  2. Na tela de login, escolha a sessão 'Xfce Session' antes de digitar a senha."
echo "  3. Abra só o terminal (Claude Code) e a Central pelo menu."
echo "Para voltar: escolha 'Cinnamon' na tela de login. Nada do Cinnamon foi removido."
