"""
Archivo: credentials.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Endpoint para que la UI verifique qué servicios externos están configurados
en el `.env` del servidor (sin exponer nunca las claves reales, solo booleanos)
y el estado del DSN dinámico del usuario (Fase 9).

Acciones Principales:
    - `GET /api/credentials/status`: reporte booleano + conteo de parcelas.
    - `POST /api/credentials/connect-db`: validación de conexión, auto-migración y conteo.

Entradas / Dependencias:
    - Variables de entorno (cargadas por `backend.config`).
    - `backend.api.deps.get_user_keys`, `backend.db.session.ensure_schema_initialized`.

Ejemplo de Integración:
    from backend.api.credentials import router
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text

from backend.api.deps import UserKeys, _is_placeholder, get_user_keys
from backend.config import get_settings
from backend.db.session import ensure_schema_initialized, get_engine

router = APIRouter(prefix="/api/credentials", tags=["credenciales"])


@router.get("/status")
async def credentials_status(keys: UserKeys = Depends(get_user_keys)) -> dict:  # noqa: B008
    """Presencia (bool) de las credenciales en el `.env` del servidor (sin valores) + entorno,
    incluyendo cabeceras `X-User-*` de la sesión actual."""
    if not isinstance(keys, UserKeys):
        keys = get_user_keys()

    settings = get_settings()
    is_dev = settings.app_env == "development"

    dsn = keys.database_url
    dsn_valid = dsn is not None and not _is_placeholder(dsn)

    existing_parcels = 0
    schema_ready = False
    if dsn_valid and dsn:
        try:
            engine = get_engine(dsn)
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT COUNT(*) FROM public.fields"))
                existing_parcels = result.scalar() or 0
            schema_ready = existing_parcels >= 0
        except Exception:
            schema_ready = False

    return {
        "env": settings.app_env,
        "groq": bool(keys.groq),
        "copernicus": bool(keys.copernicus_id and keys.copernicus_secret),
        "supabase": bool(
            keys.database_url
            or (keys.supabase_url and keys.supabase_key)
            or (is_dev and dsn_valid)
        ),
        "supabase_url": keys.supabase_url or (os.getenv("SUPABASE_URL") if is_dev else None),
        "dsn_valid": dsn_valid,
        "schema_ready": schema_ready,
        "existing_parcels": existing_parcels,
    }


@router.post("/connect-db")
async def connect_db(
    payload: dict | None = Body(default=None),  # noqa: B008
    keys: UserKeys = Depends(get_user_keys),  # noqa: B008
) -> dict:
    """Validar conexión DSN, ejecutar auto-migración si es necesario y reportar estado.

    Valida la conexión al DSN provisto (en body o cabecera `X-User-Database-Url`),
    ejecuta `ensure_schema_initialized(dsn)` para crear la arquitectura si la BD está vacía,
    cuenta cuántas parcelas existen en `public.fields` y retorna
    `connected, schema_ready, migrations_applied, existing_parcels`.
    """
    if not isinstance(keys, UserKeys):
        keys = get_user_keys()

    dsn = (payload or {}).get("database_url") or keys.database_url

    if not dsn:
        raise HTTPException(
            status_code=400,
            detail="No hay DSN de base de datos configurado. Proporciona un `database_url`.",
        )

    if _is_placeholder(dsn):
        raise HTTPException(
            status_code=400,
            detail="DSN inválido: parece un placeholder `<pwd>@<host>` o `<proyecto>`.",
        )

    try:
        migrations_applied = await ensure_schema_initialized(dsn)
        engine = get_engine(dsn)
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM public.fields"))
            existing_parcels = result.scalar() or 0
        schema_ready = True
    except Exception as err:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo conectar o inicializar la base de datos: {err}",
        ) from err

    return {
        "connected": True,
        "schema_ready": schema_ready,
        "migrations_applied": migrations_applied,
        "existing_parcels": existing_parcels,
    }
