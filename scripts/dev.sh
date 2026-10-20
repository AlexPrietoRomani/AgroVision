#!/usr/bin/env bash
# Arranca el stack de DESARROLLO en local (sin Docker):
#   - Gateway FastAPI (:8000) — API en /api (+ UI compilada en / si existe backend/static).
#   - Astro dev server (:4321) — UI con hot-reload; proxea /api -> :8000.
# Uso: ./scripts/dev.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v pnpm >/dev/null 2>&1; then
    echo "ERROR: 'pnpm' no está instalado o no está en PATH." >&2
    exit 1
fi

"$root/scripts/run_backend.sh" &
backend_pid=$!

cleanup() {
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "API:             http://127.0.0.1:8000/api/status"
echo "UI (Astro, dev): http://localhost:4321/        (hot-reload)"
echo "UI (compilada):  http://127.0.0.1:8000/        (tras ./scripts/build.sh)"

cd "$root/frontend"
pnpm dev
