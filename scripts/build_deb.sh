#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="/tmp/sakukelly-work"
OUTPUT_DEB="${REPO_DIR}/sakukelly_6.5.2-1_all.deb"

echo "=== 1. Ejecutando Pruebas Automatizadas ==="
python3 -m unittest discover -s "$REPO_DIR/tests" -p "test_*.py" -v

echo "=== 2. Verificando Sintaxis Python ==="
python3 -m py_compile "$REPO_DIR/app.py" "$REPO_DIR"/sakukelly/*.py "$REPO_DIR"/sakukelly/*/*.py "$REPO_DIR"/tests/*.py

echo "=== 3. Sincronizando Archivos al Árbol de Trabajo ==="
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR/usr/share/sakukelly"
mkdir -p "$WORK_DIR/usr/bin"
mkdir -p "$WORK_DIR/usr/share/applications"
mkdir -p "$WORK_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$WORK_DIR/DEBIAN"

cp -r "$REPO_DIR"/* "$WORK_DIR/usr/share/sakukelly/"

mkdir -p "$WORK_DIR/usr/share/pixmaps"
mkdir -p "$WORK_DIR/usr/lib/sakukelly/bin"
cp "$REPO_DIR/sakukelly/bin/yt-dlp" "$WORK_DIR/usr/lib/sakukelly/bin/yt-dlp" 2>/dev/null || true
chmod +x "$WORK_DIR/usr/lib/sakukelly/bin/yt-dlp" 2>/dev/null || true
cp "$REPO_DIR/sakukelly/assets/sakukelly.svg" "$WORK_DIR/usr/share/icons/hicolor/scalable/apps/sakukelly.svg"
cp "$REPO_DIR/sakukelly/assets/sakukelly.svg" "$WORK_DIR/usr/share/pixmaps/sakukelly.svg"

# Crear launcher executable /usr/bin/sakukelly
cat << 'EOF' > "$WORK_DIR/usr/bin/sakukelly"
#!/bin/sh
exec python3 /usr/share/sakukelly/app.py "$@"
EOF
chmod +x "$WORK_DIR/usr/bin/sakukelly"

# Crear sakukelly.desktop
cat << 'EOF' > "$WORK_DIR/usr/share/applications/sakukelly.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Sakukelly Music
Comment=Tu música, tu pasión.
Exec=sakukelly %U
TryExec=sakukelly
Icon=sakukelly
Terminal=false
Categories=AudioVideo;Audio;Player;
StartupNotify=true
StartupWMClass=sakukelly
Keywords=music;audio;player;reproductor;música;
EOF

# Crear DEBIAN/control firmado y preparado para actualizar encima
INSTALLED_SIZE=$(du -sk "$WORK_DIR/usr" | awk '{print $1}')
cat << EOF > "$WORK_DIR/DEBIAN/control"
Package: sakukelly
Version: 6.5.2-1
Section: sound
Priority: optional
Architecture: all
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Sakukelly Project <darwinsin822@users.noreply.github.com>
Depends: python3, python3-pyqt6, python3-pyqt6.qtmultimedia, python3-dbus, ffmpeg
Replaces: sakukelly (<= 6.5.2-1)
Conflicts: sakukelly (<< 6.5.2-1)
Provides: sakukelly
Description: Reproductor inteligente híbrido (local y streaming) con controles Poweramp, crossfade, DSP y letras estilo Apple Music.
 Sakukelly Music es un reproductor moderno escrito en Python 3 y PyQt6 con soporte
 de reproducción de archivos locales y streaming en directo desde YouTube, interfaz
 táctil de hardware estilo Poweramp con halo circular persistente, ecualizador DSP y letras sincronizadas.
EOF

# Generar firmas de integridad md5sums para dpkg
(cd "$WORK_DIR" && find usr -type f -exec md5sum {} + > DEBIAN/md5sums)
chmod 644 "$WORK_DIR/DEBIAN/md5sums"

chmod 755 "$WORK_DIR/DEBIAN"
chmod 644 "$WORK_DIR/DEBIAN/control"

echo "=== 4. Construyendo Paquete Debian ==="
dpkg-deb --build "$WORK_DIR" "$OUTPUT_DEB"

echo "=== SUCCESS: Paquete construido exitosamente en $OUTPUT_DEB ==="
