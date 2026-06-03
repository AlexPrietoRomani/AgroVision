# Imagen del backend FastAPI del MVP (CPU).
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Instalar dependencias de producción desde el manifiesto
COPY pyproject.toml ./
RUN uv sync --no-dev

COPY backend/ ./backend/

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
