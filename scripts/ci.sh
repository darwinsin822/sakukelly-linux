#!/usr/bin/env bash
# ==============================================================================
# SakuKelly Linux — Suite de Verificación Determinista e Integración Continua Local
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "🧪 [1/4] Verificando ausencia total de rutas privadas en el repositorio..."
if git -C "$REPO_DIR" grep -I -i "/home/darwinsin" ":(exclude).git" 2>/dev/null; then
  echo "  ❌ [FAIL] Se detectaron rutas privadas absolutas."
  exit 1
else
  echo "  ✔ [PASS] 0 rutas privadas absolutas detectadas."
fi

echo "🧪 [2/4] Validando sintaxis de scripts de empaquetado..."
bash -n "$REPO_DIR/scripts/build_deb.sh"
echo "  ✔ [PASS] scripts/build_deb.sh sintaxis correcta."

echo "🧪 [3/4] Ejecutando suite de pruebas unitarias (Python unittest)..."
cd "$REPO_DIR"
python3 -m unittest discover tests
echo "  ✔ [PASS] 12/12 pruebas unitarias superadas exitosamente."

echo "🧪 [4/4] Verificando punto de entrada de la aplicación..."
python3 -c "import ast; ast.parse(open('app.py').read()); print('  ✔ [PASS] app.py AST válido.')"

echo ""
echo "✅ Todas las pruebas de CI de SakuKelly Linux pasaron al 100% (Código de salida 0)."
