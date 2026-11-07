#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$ROOT/server_1.16.5"
mkdir -p "$SERVER_DIR"
cd "$SERVER_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 é necessário."
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "curl é necessário. Instale com: sudo apt install curl"
  exit 1
fi

# Prefer an explicitly configured Java 16 executable; otherwise use java from PATH.
JAVA_BIN="${HOSHINO_JAVA16:-java}"
if ! command -v "$JAVA_BIN" >/dev/null 2>&1; then
  echo "Java não encontrado. O servidor precisa de uma versão compatível de Java."
  echo "Você pode definir HOSHINO_JAVA16=/caminho/para/java e repetir este script."
  exit 1
fi
JAVA_MAJOR=$("$JAVA_BIN" -version 2>&1 | awk -F[".] 'NR==1 {print ($2=="1" ? $3 : $2)}')
if [ "${JAVA_MAJOR:-0}" -lt 8 ] || [ "${JAVA_MAJOR:-0}" -gt 16 ]; then
  echo "Java encontrado: major ${JAVA_MAJOR:-desconhecido}. Para o servidor 1.16.5 do laboratório, use Java 8-16; Java 16 é a opção preferida."
  echo "Defina HOSHINO_JAVA16=/caminho/para/java e repita este script."
  exit 1
fi

# Resolve the official Mojang 1.16.5 server URL from the version manifest.
URL=$(python3 - <<'PY'
import json, urllib.request
manifest = json.load(urllib.request.urlopen('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json', timeout=20))
entry = next(v for v in manifest['versions'] if v['id'] == '1.16.5')
version = json.load(urllib.request.urlopen(entry['url'], timeout=20))
print(version['downloads']['server']['url'])
PY
)

if [ ! -f server.jar ]; then
  echo "Baixando servidor oficial Minecraft Java 1.16.5..."
  curl -fL "$URL" -o server.jar
fi

cat > server.properties <<'EOF'
server-port=25565
server-ip=127.0.0.1
online-mode=false
gamemode=survival
difficulty=normal
spawn-protection=0
allow-flight=false
enable-command-block=false
motd=Hoshino Laboratory 1.16.5
EOF

if [ ! -f eula.txt ]; then
  cat > eula.txt <<'EOF'
# Leia o EULA em https://aka.ms/MinecraftEULA e, se você concordar, altere para true.
eula=false
EOF
fi

cat > start_server.sh <<SH2
#!/bin/bash
set -euo pipefail
cd "\$(dirname "\$0")"
if ! grep -q '^eula=true' eula.txt; then
  echo "Edite eula.txt e coloque eula=true depois de aceitar o EULA da Mojang."
  exit 1
fi
exec "$JAVA_BIN" -Xms2G -Xmx4G -jar server.jar --nogui
SH2
chmod +x start_server.sh

echo
 echo "Servidor preparado em: $SERVER_DIR"
echo "1) Confirme o EULA em $SERVER_DIR/eula.txt"
echo "2) Inicie: $SERVER_DIR/start_server.sh"
echo "3) No SKLauncher 1.16.5, entre em Multiplayer -> Direct Connect -> 127.0.0.1:25565"
