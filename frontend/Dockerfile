# Imagen de la UI Shiny for Python del MVP.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY frontend/ ./frontend/

ENV API_BASE_URL=http://localhost:8000
EXPOSE 8001
CMD ["uv", "run", "shiny", "run", "frontend/app.py", "--host", "0.0.0.0", "--port", "8001"]
