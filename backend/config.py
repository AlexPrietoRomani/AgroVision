"""
Archivo: config.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Centraliza la configuración del backend del MVP leyéndola de variables de
entorno, evitando valores mágicos dispersos por el código y facilitando el
despliegue en distintos entornos (local, Render).

Acciones Principales:
    - Expone `get_settings`, que construye y cachea la configuración del entorno.

Estructura Interna:
    - `Settings`: dataclass inmutable con los parámetros del backend.
    - `get_settings`: lee el entorno y devuelve la configuración cacheada.

Entradas / Dependencias:
    - Variables de entorno: APP_ENV, MODEL_PATH, MODEL_VERSION, MODEL_ARCHITECTURE,
      ALLOWED_ORIGINS, COUNTING_ENABLED, MAX_UPLOAD_MB, CONFIDENCE_THRESHOLD.

Salidas / Efectos:
    - No genera efectos secundarios; únicamente lee variables de entorno.

Ejemplo de Integración:
    from backend.config import get_settings
    settings = get_settings()
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # carga variables desde .env en desarrollo local (no sobreescribe el entorno real)

DEFAULT_CONFIDENCE_THRESHOLD: float = 0.25
DEFAULT_MAX_UPLOAD_MB: int = 50
DEFAULT_MODEL_PATH: str = "./models/agrovision-plantcount-v2.0.0.onnx"
DEFAULT_MODEL_VERSION: str = "2.0.0"
DEFAULT_MODEL_ARCHITECTURE: str = "yolo26n"
DEFAULT_MODEL_BACKEND: str = "mock"  # mock (datos falsos para probar) | onnx (modelo real)


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    """
    Convierte una variable de entorno textual en un booleano.

    Args:
        raw (str | None): Valor crudo de la variable de entorno.
        default (bool, opcional): Valor a devolver si `raw` es None. Por defecto False.

    Returns:
        bool: True si el texto representa un valor verdadero ('1', 'true', 'yes', 'on').
    """
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable del backend del MVP, derivada del entorno."""

    app_env: str
    model_path: str
    model_version: str
    model_architecture: str
    model_backend: str
    allowed_origins: tuple[str, ...]
    counting_enabled: bool
    events_persist: bool
    rate_limit_per_min: int
    max_upload_mb: int
    confidence_threshold: float


@lru_cache
def get_settings() -> Settings:
    """
    Construye la configuración del backend a partir de variables de entorno.

    Returns:
        Settings: Instancia cacheada con la configuración activa del backend.
    """
    origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:8001")
    origins = tuple(origin.strip() for origin in origins_raw.split(",") if origin.strip())
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        model_path=os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH),
        model_version=os.getenv("MODEL_VERSION", DEFAULT_MODEL_VERSION),
        model_architecture=os.getenv("MODEL_ARCHITECTURE", DEFAULT_MODEL_ARCHITECTURE),
        model_backend=os.getenv("MODEL_BACKEND", DEFAULT_MODEL_BACKEND),
        allowed_origins=origins,
        counting_enabled=_parse_bool(os.getenv("COUNTING_ENABLED"), default=False),
        events_persist=_parse_bool(os.getenv("EVENTS_PERSIST"), default=False),
        rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "120")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))),
        confidence_threshold=float(
            os.getenv("CONFIDENCE_THRESHOLD", str(DEFAULT_CONFIDENCE_THRESHOLD))
        ),
    )
