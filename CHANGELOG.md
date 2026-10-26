# Changelog - Sakukelly Music

## [6.5.0-RC1] - 2026-08-15

### 🚀 Nuevas Características y Soporte Multiplataforma
- **Soporte Nativo para Windows (.exe)**:
  - Generación de instalador setup gráfico `Sakukelly-Setup.exe` y ejecutable portable `Sakukelly.exe`.
  - Ocultación total de ventana de consola CMD (`--noconsole`) al ejecutar el reproductor.
  - Integración nativa de almacenamiento en `%LOCALAPPDATA%\sakukelly`.
- **Icono Vectorial de Alta Definición**:
  - Incorporación del asset vectorial `sakukelly/assets/sakukelly.svg` y bindeos a iconos de aplicación.
- **Suite de Pruebas Automatizadas (QA)**:
  - Pruebas unitarias para parsing LRC (`tests/test_lrc.py`), base de datos SQLite (`tests/test_database.py`) y caché TTL de streaming (`tests/test_resolver.py`).
- **DevOps Build Pipeline**:
  - Scripts de compilación reproducibles para Linux (`build_deb.sh`) y Windows (`build_windows.bat` y `Sakukelly-Setup.iss`).

### 🐛 Correcciones de Errores
- Corrección de lanzamiento duplicado de instancia única IPC vía socket timeout de 1000ms.
- Limpieza de títulos de canales de YouTube (VEVO / Topic) en la resolución de letras.
- Restablecimiento del estilo estético Apple Music en la sincronización de letras a 30 FPS.
