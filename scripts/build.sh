#!/usr/bin/env bash
# scripts/build.sh — Pipeline de build de la UI: Astro -> inline -> backend/static
# (lo que sirve el gateway FastAPI en /). Uso: ./scripts/build.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

for bin in uv pnpm; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "ERROR: '$bin' no está instalado o no está en PATH." >&2
        exit 1
    fi
done

echo "=== Build AgroVisión UI (Astro -> backend/static) ==="

echo
echo "[1/3] Compilando Astro (pnpm build)..."
(cd "$root/frontend" && pnpm install && pnpm build)

echo
echo "[2/3] Post-procesando index.html (inline_js.py)..."
uv run python scripts/inline_js.py

echo
echo "[3/3] Copiando frontend/dist -> backend/static..."
static="$root/backend/static"
mkdir -p "$static"
find "$static" -mindepth 1 -maxdepth 1 ! -name ".gitkeep" -exec rm -rf {} +
cp -R "$root/frontend/dist/." "$static/"
touch "$static/.gitkeep"

echo
echo "=== Build completado. Sirve con: ./scripts/run_backend.sh -> http://127.0.0.1:8000/ ==="
