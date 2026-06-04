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

from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.session import get_sessionmaker


@dataclass
class UserKeys:
    """Llaves BYOK de la sesión (efímeras: viven solo durante el request)."""

    groq: str | None = None
    copernicus_id: str | None = None
    copernicus_secret: str | None = None
    supabase_url: str | None = None
    supabase_key: str | None = None


def get_user_keys(
    x_user_groq_key: str | None = Header(default=None),
    x_user_copernicus_id: str | None = Header(default=None),
    x_user_copernicus_secret: str | None = Header(default=None),
    x_user_supabase_url: str | None = Header(default=None),
    x_user_supabase_key: str | None = Header(default=None),
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
    settings = get_settings()
    is_dev = settings.app_env == "development"

    # En producción, NO usar fallback del entorno (cada usuario pone sus llaves)
    dev_groq = os.getenv("DEV_GROQ_API_KEY") if is_dev else None
    dev_cop_id = os.getenv("DEV_COPERNICUS_CLIENT_ID") if is_dev else None
    dev_cop_secret = os.getenv("DEV_COPERNICUS_CLIENT_SECRET") if is_dev else None

    return UserKeys(
        groq=x_user_groq_key or dev_groq or None,
        copernicus_id=x_user_copernicus_id or dev_cop_id or None,
        copernicus_secret=(
            x_user_copernicus_secret or dev_cop_secret or None
        ),
        supabase_url=x_user_supabase_url or os.getenv("SUPABASE_URL") or None,
        supabase_key=x_user_supabase_key or os.getenv("SUPABASE_ANON_KEY") or None,
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    """Cede una sesión async de SQLAlchemy y la cierra al terminar el request."""
    async with get_sessionmaker()() as session:
        yield session
