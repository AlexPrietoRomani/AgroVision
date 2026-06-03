"""
Archivo: deps.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Dependencias compartidas de la API (gateway): el proxy **efímero** de credenciales
BYOK y la sesión de base de datos. Las llaves del usuario llegan por cabeceras
`X-User-*` (modelo de cero persistencia) y, para desarrollo local, hacen *fallback* a
las variables `DEV_*`/`SUPABASE_*` del entorno. La `UserKeys` vive solo durante el
request: nunca se escribe a disco, log ni BD.

Acciones Principales:
    - `get_user_keys`: extrae las llaves del request (header o entorno DEV).
    - `get_db`: cede una sesión async de SQLAlchemy.

Entradas / Dependencias:
    - `fastapi.Header`, `backend.db.session`.

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
    Construye las `UserKeys` del request: cabecera primero, entorno DEV como fallback.

    El fallback permite el desarrollo local (las llaves en `.env` como `DEV_*`), pero en
    producción siempre llegan por cabecera desde la UI y se descartan tras el request.

    Returns:
        UserKeys: Credenciales de la sesión (nunca se persisten).
    """
    return UserKeys(
        groq=x_user_groq_key or os.getenv("DEV_GROQ_API_KEY") or None,
        copernicus_id=x_user_copernicus_id or os.getenv("DEV_COPERNICUS_CLIENT_ID") or None,
        copernicus_secret=(
            x_user_copernicus_secret or os.getenv("DEV_COPERNICUS_CLIENT_SECRET") or None
        ),
        supabase_url=x_user_supabase_url or os.getenv("SUPABASE_URL") or None,
        supabase_key=x_user_supabase_key or os.getenv("SUPABASE_ANON_KEY") or None,
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    """Cede una sesión async de SQLAlchemy y la cierra al terminar el request."""
    async with get_sessionmaker()() as session:
        yield session
