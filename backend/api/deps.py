"""
Archivo: deps.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Dependencias compartidas de la API (gateway): el proxy **efímero** de credenciales
BYOK y la sesión de base de datos. Las llaves del usuario llegan por cabeceras
`X-User-*` (modelo de cero persistencia). En **desarrollo local** (`APP_ENV=development`),
hacen *fallback* a las variables `DEV_*`/`SUPABASE_*` del `.env`. En **producción**,
las credenciales son **obligatorias** vía cabeceras (cada usuario pone las suyas).

Acciones Principales:
    - `get_user_keys`: extrae las llaves del request (header o entorno DEV en local).
    - `get_db`: cede una sesión async de SQLAlchemy.

Entradas / Dependencias:
    - `fastapi.Header`, `backend.db.session`, `backend.config`.

Salidas / Efectos:
    - Abre una sesión por request; no persiste credenciales.

Ejemplo de Integración:
    from backend.api.deps import get_user_keys, get_db
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.session import ensure_schema_initialized, get_sessionmaker


@dataclass
class UserKeys:
    """Llaves BYOK de la sesión (efímeras: viven solo durante el request)."""

    groq: str | None = None
    copernicus_id: str | None = None
    copernicus_secret: str | None = None
    supabase_url: str | None = None
    supabase_key: str | None = None
    database_url: str | None = None


def _is_placeholder(url: str | None) -> bool:
    """Devuelve True si la URL es el placeholder genérico <pwd>, <host> o <proyecto>."""
    if url is None or not isinstance(url, str):
        return False
    return (
        "<pwd>" in url
        or "<host>" in url
        or "<proyecto>" in url
        or "placeholder_" in url
    )


def get_user_keys(
    x_user_groq_key: str | None = Header(default=None),
    x_user_copernicus_id: str | None = Header(default=None),
    x_user_copernicus_secret: str | None = Header(default=None),
    x_user_supabase_url: str | None = Header(default=None),
    x_user_supabase_key: str | None = Header(default=None),
    x_user_database_url: str | None = Header(default=None),
) -> UserKeys:
    """
    Construye las `UserKeys` del request.

    En **desarrollo local** (`APP_ENV=development`): cabecera primero, entorno DEV como
    fallback (permite trabajar sin reescribir llaves en la UI).

    En **producción** (`APP_ENV=production`): **solo cabeceras**. Cada usuario debe
    proporcionar sus propias credenciales vía la pestaña Credenciales de la UI.

    Returns:
        UserKeys: Credenciales de la sesión (nunca se persisten).
    """
    # Normalizar argumentos que no sean str a None (soporta llamadas directas en tests sin Depends)
    groq = x_user_groq_key if isinstance(x_user_groq_key, str) else None
    cop_id = x_user_copernicus_id if isinstance(x_user_copernicus_id, str) else None
    cop_sec = x_user_copernicus_secret if isinstance(x_user_copernicus_secret, str) else None
    sb_url = x_user_supabase_url if isinstance(x_user_supabase_url, str) else None
    sb_key = x_user_supabase_key if isinstance(x_user_supabase_key, str) else None
    db_url = x_user_database_url if isinstance(x_user_database_url, str) else None

    settings = get_settings()
    is_dev = settings.app_env == "development"

    # En producción solo valen las cabeceras x_user_* enviadas por el usuario
    if is_dev:
        groq = groq or os.getenv("DEV_GROQ_API_KEY") or None
        cop_id = cop_id or os.getenv("DEV_COPERNICUS_CLIENT_ID") or None
        cop_sec = cop_sec or os.getenv("DEV_COPERNICUS_CLIENT_SECRET") or None
        sb_url = sb_url or os.getenv("SUPABASE_URL") or None
        sb_key = sb_key or os.getenv("SUPABASE_ANON_KEY") or None
        env_db_url = os.getenv("DATABASE_URL")
        if not db_url and env_db_url and not _is_placeholder(env_db_url):
            db_url = env_db_url

    if db_url and _is_placeholder(db_url):
        db_url = None

    return UserKeys(
        groq=groq,
        copernicus_id=cop_id,
        copernicus_secret=cop_sec,
        supabase_url=sb_url,
        supabase_key=sb_key,
        database_url=db_url,
    )


async def get_db(keys: UserKeys = Depends(get_user_keys)) -> AsyncIterator[AsyncSession]:
    """Cede una sesión async de SQLAlchemy y la cierra al terminar el request."""
    if not isinstance(keys, UserKeys):
        keys = get_user_keys()
    dsn = keys.database_url
    if not dsn:
        from fastapi import HTTPException
        from starlette.status import HTTP_503_SERVICE_UNAVAILABLE

        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay DSN de base de datos configurado. Conecta tu Supabase en Credenciales.",
        )
    await ensure_schema_initialized(dsn)
    async with get_sessionmaker(dsn)() as session:
        yield session
