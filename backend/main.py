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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.count import router as count_router
from backend.api.fields import router as fields_router
from backend.api.ndvi import router as ndvi_router
from backend.api.weather import router as weather_router
from backend.config import get_settings
from backend.core.inference import ModelNotAvailableError, create_adapter

_logger = logging.getLogger("agrovision.backend")


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
    app.include_router(fields_router)  # Creación de Parcelas
    app.include_router(ndvi_router)  # Teledetección NDVI
    app.include_router(weather_router)  # Clima
    app.include_router(chat_router)  # Asistente Agéntico (RAG)
    app.include_router(count_router)  # Conteo (en desarrollo / standby)
    return app


app = create_app()
