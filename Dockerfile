# =====================================================================================
# Dockerfile ÚNICO de AgroVisión — gateway FastAPI que sirve la UI Astro en / y la API
# en /api. Lo usan: Hugging Face Spaces (deploy activo), Render y docker-compose (local).
#
# Multi-stage: (1) Node compila Astro (se DESCARTA: node_modules nunca llega a la imagen
# final); (2) Python/uv corre el gateway con el build de Astro copiado a backend/static.
# Corre como usuario NO-root 1000 (requisito de HF Spaces; buena práctica en todos lados).
# BYOK: sin secretos en la imagen. Puerto 8000 (README → app_port: 8000).
# El `.dockerignore` mantiene el build context mínimo (solo frontend/, backend/, manifiestos).
# =====================================================================================

# --- Stage 1: build de la UI Astro (descartado en la imagen final) ---
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
RUN corepack enable
# Solo manifiestos primero → capa de deps cacheable mientras no cambien.
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Stage 2: backend FastAPI (CPU) — imagen final ---
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Libs de sistema mínimas en runtime:
#   libglib2.0-0 → requerido por opencv-python-headless (cv2 se importa al arrancar)
#   libgomp1     → requerido por onnxruntime (import diferido; al activar el conteo)
#   libxcb1      → requerido por opencv-python-headless (librería X11 en Debian)
# --no-install-recommends + limpieza de listas: nada de basura de apt en la capa.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root (UID 1000). Se cambia a USER antes de WORKDIR para que el directorio
# de trabajo (y el .venv que se crea dentro) queden a nombre de 'user' (evita EACCES).
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:$PATH \
    UV_PROJECT_ENVIRONMENT=/home/user/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COUNTING_ENABLED=false \
    EVENTS_PERSIST=false
USER user
WORKDIR /home/user/app

# Capa de dependencias (cacheable): solo manifiestos. --no-cache evita dejar el cache
# de wheels de uv dentro de la imagen; UV_COMPILE_BYTECODE acelera el arranque en frío.
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-cache

# Código + UI Astro compilada (servida por el gateway en /).
COPY --chown=user backend/ ./backend/
COPY --chown=user --from=ui /ui/dist/ ./backend/static/

# --- (Conteo, EN DESARROLLO) Para activar el modelo real, descomenta y rebuild con
#     COUNTING_ENABLED=true y MODEL_BACKEND=onnx. Descarga el artefacto de HF Hub en el build:
# RUN uv run python -c "from huggingface_hub import hf_hub_download; \
#     hf_hub_download(repo_id='<org>/agrovision-plantcount', \
#     filename='agrovision-plantcount-v2.0.0.onnx', local_dir='/home/user/app/models')"

EXPOSE 8000
# El venv ya está en PATH → uvicorn corre directo (sin re-resolver con uv en runtime).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
