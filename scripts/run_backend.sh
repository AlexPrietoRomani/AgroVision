#!/usr/bin/env bash
# Levanta el backend FastAPI del MVP en local (sin Docker), en http://127.0.0.1:8000
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' no está instalado o no está en PATH." >&2
    exit 1
fi

export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
export PYTHONUNBUFFERED=1

uv sync
uv run python -u -m uvicorn backend.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --reload \
    --log-level info \
    --reload-exclude ".venv" \
    --reload-exclude "frontend" \
    --reload-exclude "docs" \
    --reload-exclude "tests" \
    --reload-exclude "scripts" \
    --reload-exclude "supabase" \
    --reload-exclude "models" \
    --reload-exclude "sample_data" \
    --reload-exclude "scratch"
