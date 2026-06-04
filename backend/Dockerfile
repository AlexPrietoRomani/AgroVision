# =====================================================================================
# Imagen del backend AgroVisión: FastAPI (gateway) que sirve la API en /api y la
# UI Astro estática en /. Multi-stage: (1) Node compila Astro; (2) Python/uv corre
# el gateway con el build de Astro copiado a backend/static.
# =====================================================================================

# --- Stage 1: build de la UI Astro ---
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Stage 2: backend FastAPI (CPU) ---
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app

# Dependencias de producción desde el manifiesto
COPY pyproject.toml ./
RUN uv sync --no-dev

COPY backend/ ./backend/
# UI Astro compilada (servida por el gateway en /)
COPY --from=ui /ui/dist/ ./backend/static/

# Para ACTIVAR el conteo: descargar el modelo desde Hugging Face Hub en el build.
# (Mientras COUNTING_ENABLED=false el backend funciona en standby y no requiere modelo.)
# ARG MODEL_VERSION=2.0.0
# RUN uv run python -c "from huggingface_hub import hf_hub_download; \
#   hf_hub_download(repo_id='<org>/agrovision-plantcount', \
#   filename='agrovision-plantcount-v${MODEL_VERSION}.onnx', local_dir='/app/models')"

ENV COUNTING_ENABLED=false
ENV MODEL_PATH=/app/models/agrovision-plantcount-v2.0.0.onnx
ENV MODEL_VERSION=2.0.0
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
