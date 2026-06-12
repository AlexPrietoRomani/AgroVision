"""
Archivo: main.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Punto de entrada del backend FastAPI del MVP. Configura CORS, carga el modelo de
conteo en el `lifespan` (si está habilitado y disponible) y monta las rutas del
MVP. Soporta el modo **standby**: si el conteo está deshabilitado o el modelo no
existe, el backend arranca igual y el endpoint de conteo responde 503.

Acciones Principales:
    - Crea la app FastAPI, configura CORS y carga (opcionalmente) el modelo.

Estructura Interna:
    - `lifespan`: gestiona la carga/descarga del adaptador de inferencia.
    - `create_app`: construye y configura la instancia de FastAPI.
    - `app`: instancia ASGI servida por uvicorn.

Entradas / Dependencias:
    - `fastapi`, `backend.config`, `backend.core.inference`, `backend.api.count`.

Salidas / Efectos:
    - Expone un servicio ASGI en el puerto configurado.

Ejecución:
    uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000

Ejemplo de Uso:
    uv run uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.chat import router as chat_router
from backend.api.count import router as count_router
from backend.api.credentials import router as credentials_router
from backend.api.data import router as data_router
from backend.api.events import router as events_router
from backend.api.fields import router as fields_router
from backend.api.ndvi import router as ndvi_router
from backend.api.vegetation import router as vegetation_router
from backend.api.weather import router as weather_router
from backend.config import get_settings
from backend.core.inference import ModelNotAvailableError, create_adapter
from backend.core.ratelimit import SlidingWindowRateLimiter

_logger = logging.getLogger("agrovision.backend")

# Cabeceras de seguridad aplicadas a todas las respuestas (hardening básico).
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",  # CSP/headers modernos lo sustituyen; evita modos heredados
}


def _client_key(request: Request) -> str:
    """IP del cliente para el rate limiting (respeta el proxy del host: X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Carga el adaptador de inferencia al iniciar y lo libera al terminar.

    En modo standby (conteo deshabilitado o modelo ausente) deja el adaptador en
    None y registra el motivo, permitiendo que el backend arranque de todas formas.

    Args:
        app (FastAPI): Instancia de la aplicación cuyo estado se inicializa.

    Yields:
        None: Cede el control mientras la app está en ejecución.
    """
    settings = get_settings()
    app.state.adapter = None

    if settings.counting_enabled:
        try:
            app.state.adapter = create_adapter(
                settings.model_backend, settings.model_path, settings.model_architecture
            )
            _logger.info("Adaptador de conteo activo: backend=%s", settings.model_backend)
        except ModelNotAvailableError as error:
            _logger.warning("Conteo en standby (modelo no disponible): %s", error)
    else:
        _logger.info("Conteo en standby (COUNTING_ENABLED=false).")

    yield
    app.state.adapter = None


def create_app() -> FastAPI:
    """
    Construye y configura la instancia de FastAPI del MVP.

    Returns:
        FastAPI: Aplicación con CORS y rutas montadas.
    """
    settings = get_settings()
    app = FastAPI(
        title="AgroVisión — Backend (plataforma)",
        version=settings.model_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],  # necesario para las cabeceras BYOK X-User-*
    )

    # Rate limiting (anti-abuso/DDoS) sobre /api + cabeceras de seguridad en todo.
    # Por proceso/en memoria: defensa en profundidad junto al borde del host (HF Spaces).
    limiter = SlidingWindowRateLimiter(settings.rate_limit_per_min, window_seconds=60.0)

    @app.middleware("http")
    async def _security_and_ratelimit(request: Request, call_next):  # type: ignore[no-untyped-def]
        if limiter.enabled and request.url.path.startswith("/api"):
            if not limiter.allow(_client_key(request)):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Demasiadas peticiones. Inténtalo de nuevo en un momento."},
                    headers={"Retry-After": "60", **_SECURITY_HEADERS},
                )
        response = await call_next(request)
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    app.include_router(fields_router)  # Creación de Parcelas
    app.include_router(ndvi_router)  # Teledetección NDVI (legacy)
    app.include_router(vegetation_router)  # Índices espectrales (Fase 13)
    app.include_router(weather_router)  # Clima
    app.include_router(chat_router)  # Asistente Agéntico (RAG)
    app.include_router(credentials_router)  # Presencia de .env (dev)
    app.include_router(events_router)  # Telemetría de UI (Fase 9)
    app.include_router(data_router)  # Explorador de Datos (Fase 11)
    app.include_router(count_router)  # Conteo (en desarrollo / standby)

    # UI Astro estática (Fase 8): se monta en "/" AL FINAL, tras los routers /api y
    # /shiny, para no interceptar sus rutas. El build se copia a backend/static
    # (`pnpm build` + copia). Si no existe (sin build), el backend arranca igual.
    static_dir = Path(__file__).resolve().parent / "static"
    if (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
        _logger.info("UI Astro servida desde %s", static_dir)
    else:
        _logger.info("UI Astro no compilada (sin backend/static/index.html); solo /api.")
    return app


app = create_app()
