# =====================================================================================
# Dockerfile para Hugging Face Spaces (SDK: docker) — gateway AgroVisión.
# HF construye ESTE archivo (debe estar en la raíz del repo) y lo corre como el
# usuario 1000 (HOME=/home/user). El gateway FastAPI sirve la UI Astro compilada en /
# y la API en /api. Puerto: 8000 (declarado en README.md con `app_port: 8000`).
#
# Multi-stage: (1) Node compila Astro; (2) Python/uv corre el gateway con el build
# de Astro copiado a backend/static. BYOK: sin secretos en la imagen (las llaves de
# datos las pone el usuario por sesión vía cabeceras X-User-*).
#
# Local/Render usan backend/Dockerfile; este es el equivalente endurecido para HF.
# =====================================================================================

# --- Stage 1: build de la UI Astro ---
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Stage 2: backend FastAPI (CPU), como usuario no-root (requisito de HF Spaces) ---
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# HF Spaces ejecuta el contenedor como UID 1000: crear el usuario ANTES de copiar.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    UV_PROJECT_ENVIRONMENT=/home/user/app/.venv \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/home/user/.cache/uv \
    COUNTING_ENABLED=false \
    EVENTS_PERSIST=false

WORKDIR /home/user/app

# Dependencias (capa cacheable) — desde el lockfile, sin dev.
COPY --chown=user pyproject.toml uv.lock ./
USER user
RUN uv sync --no-dev --frozen

# Código + UI Astro compilada (servida por el gateway en /).
COPY --chown=user backend/ ./backend/
COPY --chown=user --from=ui /ui/dist/ ./backend/static/

EXPOSE 8000
# --no-sync: usa el venv ya construido en el build (no re-resuelve en runtime).
CMD ["uv", "run", "--no-sync", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
