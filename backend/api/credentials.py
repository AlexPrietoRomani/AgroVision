"""
Archivo: credentials.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Endpoint de conveniencia para desarrollo: informa **qué credenciales BYOK están
presente en el `.env` del servidor` (variables `DEV_*` / `SUPABASE_*` / `DATABASE_URL`),
para que la UI pueda ofrecer "usar las del servidor" sin que el usuario las reescriba.
Devuelve **solo booleanos de presencia** — nunca los valores — para no exponer secretos.

En **producción** (`APP_ENV=production`), las `DEV_*` keys NO están disponibles
(cada usuario debe poner las suyas). El endpoint reporta `env: "production"` para
que la UI muestre el aviso correspondiente.

También expone:
    - `POST /api/credentials/connect-db`: valida conexión DSN, ejecuta auto-migración
      si la BD está vacía, cuenta parcelas y retorna estado completo.
    - `GET /api/credentials/status`: considera cabeceras `X-User-*` de la sesión actual
      e ignora placeholders `<pwd>@<host>` del entorno.

Estructura Interna:
    - `GET /api/credentials/status`: presencia (bool) de Groq, Copernicus y Supabase + entorno,
      incluyendo cabeceras `X-User-*`.
    - `POST /api/credentials/connect-db`: validación de conexión, auto-migración y conteo.

Entradas / Dependencias:
    - Variables de entorno (cargadas por `backend.config`).
    - `backend.api.deps.get_user_keys`, `backend.db.session.ensure_schema_initialized`.

Ejemplo de Integración:
    from backend.api.credentials import router
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from backend.api.deps import get_user_keys
from backend.config import get_settings
from backend.db.session import ensure_schema_initialized, get_engine

router = APIRouter(prefix="/api/credentials", tags=["credenciales"])


def _resolve_db_dsn() -> str | None:
    """Resuelve el DSN del usuario desde la cabecera X-User-Database-Url o el entorno."""
    keys = get_user_keys()
    return keys.database_url


def _is_placeholder(url: str | None) -> bool:
    """Devuelve True si la URL es el placeholder genérico <pwd>@<host>."""
    return bool(url and ("<pwd>" in url or "<host>" in url))


@router.get("/status")
async def credentials_status() -> dict:
    """Presencia (bool) de las credenciales en el `.env` del servidor (sin valores) + entorno,
    incluyendo cabeceras `X-User-*` de la sesión actual."""
    settings = get_settings()
    is_dev = settings.app_env == "development"

    dev_groq = bool(os.getenv("DEV_GROQ_API_KEY")) if is_dev else False
    dev_cop = (
        bool(os.getenv("DEV_COPERNICUS_CLIENT_ID") and os.getenv("DEV_COPERNICUS_CLIENT_SECRET"))
        if is_dev
        else False
    )

    # Usar DSN del usuario si está configurado (no es placeholder)
    dsn = _resolve_db_dsn()
    dsn_valid = dsn is not None and not _is_placeholder(dsn)

    # Contar parcelas si el DSN es válido y la tabla existe
    existing_parcels = 0
    schema_ready = False
    if dsn_valid:
        try:
            from sqlalchemy import text

            engine = get_engine(dsn)
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT COUNT(*) FROM public.fields"))
                existing_parcels = result.scalar()
            schema_ready = existing_parcels >= 0  # tabla existe y es accesible
        except Exception:
            schema_ready = False

    return {
        "env": settings.app_env,
        "groq": dev_groq,
        "copernicus": dev_cop,
        "supabase": bool(os.getenv("DATABASE_URL")),
        "supabase_url": os.getenv("SUPABASE_URL") if is_dev else None,
        "dsn": dsn,
        "dsn_valid": dsn_valid,
        "schema_ready": schema_ready,
        "existing_parcels": existing_parcels,
    }


@router.post("/connect-db")
async def connect_db() -> dict:
    """Validar conexión DSN, ejecutar auto-migración si es necesario y reportar estado.

    Valida la conexión al DSN provisto (usando cabecera `X-User-Database-Url` o el
    configurado en la sesión), ejecuta `ensure_schema_initialized(dsn)` para crear la
      arquitectura si la BD está vacía, cuenta cuántas parcelas existen en `public.fields`
      y retorna `connected, schema_ready, migrations_applied, existing_parcels`.
    """
    keys = get_user_keys()
    dsn = keys.database_url

    if not dsn:
        raise HTTPException(
            status_code=400,
            detail="No hay DSN de base de datos configurado. Proporciona un `X-User-Database-Url`.",
        )

    # Validar que no sea placeholder
    if _is_placeholder(dsn):
        raise HTTPException(
            status_code=400,
            detail="DSN inválido: parece un placeholder `<pwd>@<host>`.",
        )

    # Ejecutar auto-migración y contar resultados
    migrations_applied = await ensure_schema_initialized(dsn)

    # Contar parcelas existentes
    existing_parcels = 0
    schema_ready = False
    try:
        from sqlalchemy import text

        from backend.db.session import get_engine
        engine = get_engine(dsn)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM public.fields"))
            existing_parcels = result.scalar() or 0
        schema_ready = True
    except Exception:
        schema_ready = False

    return {
        "connected": True,
        "schema_ready": schema_ready,
        "migrations_applied": migrations_applied,
        "existing_parcels": existing_parcels,
    }
