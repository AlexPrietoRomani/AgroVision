"""
Archivo: session.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Fábrica de motor y sesiones async de SQLAlchemy contra el Supabase del usuario
(PostgreSQL + PostGIS). Construye la URL async (driver asyncpg) a partir de
`DATABASE_URL` descomponiéndola con `URL.create` para tolerar contraseñas con
caracteres especiales. Está pensado para el **Session pooler** de Supabase
(IPv4-compatible); `statement_cache_size=0` evita choques de prepared statements
con pgbouncer.

Acciones Principales:
    - Expone `get_engine()` y `get_sessionmaker()` (memoizados).

Estructura Interna:
    - `_async_url`: deriva la URL `postgresql+asyncpg` desde `DATABASE_URL`.
    - `get_engine` / `get_sessionmaker`: singletons por proceso.

Entradas / Dependencias:
    - `sqlalchemy[asyncio]`, `asyncpg`; variable de entorno `DATABASE_URL`.

Salidas / Efectos:
    - Abre conexiones a la BD del usuario; no persiste credenciales.

Ejemplo de Integración:
    from backend.db.session import get_sessionmaker
    async with get_sessionmaker()() as session:
        ...
"""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import unquote, urlparse

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def _async_url() -> URL:
    """
    Construye la URL async de SQLAlchemy a partir de `DATABASE_URL`.

    Returns:
        URL: URL con driver `postgresql+asyncpg` y componentes desescapados.
    """
    parsed = urlparse(os.environ["DATABASE_URL"])
    return URL.create(
        "postgresql+asyncpg",
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/") or None,
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Crea (una vez) el motor async; `statement_cache_size=0` por el pooler pgbouncer."""
    return create_async_engine(
        _async_url(),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker:
    """Devuelve (una vez) la fábrica de sesiones async."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)
