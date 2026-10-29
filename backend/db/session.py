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


def _is_valid_dsn(url: str | None) -> bool:
    """Valida que la DSN no sea None/buena y no contenga placeholders <pwd>@<host>."""
    if not url or not url.strip():
        return False
    return "<pwd>" not in url and "<host>" not in url


def _async_url(dsn: str | None = None) -> URL:
    """
    Construye la URL async de SQLAlchemy a partir de un DSN.

    Si `dsn` es None o vacío, caeback a `DATABASE_URL` del entorno.
    """
    dsn = dsn or os.environ.get("DATABASE_URL", "")
    if not _is_valid_dsn(dsn):
        raise ValueError(f"DSN inválido o placeholder: {dsn!r}")
    parsed = urlparse(dsn)
    return URL.create(
        "postgresql+asyncpg",
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/") or None,
    )


@lru_cache(maxsize=1)
def get_engine(dsn: str | None = None) -> AsyncEngine:
    """Crea (una vez por DSN) el motor async; `statement_cache_size=0` por el pooler pgbouncer."""
    return create_async_engine(
        _async_url(dsn),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )


@lru_cache(maxsize=1)
def get_sessionmaker(dsn: str | None = None) -> async_sessionmaker:
    """Devuelve (una vez por DSN) la fábrica de sesiones async."""
    return async_sessionmaker(get_engine(dsn), expire_on_commit=False)


_INITIALIZED_DSNS: set[str] = set()


async def apply_migrations(dsn: str | None = None) -> list[str]:
    """Aplica todas las migraciones SQL versionadas contra el DS dado.

    Usa `backend.db.migrate.apply_migrations` y devuelve la lista de nombres
    de los archivos aplicados.
    """
    from backend.db.migrate import apply_migrations as _apply
    return await _apply(dsn)


async def ensure_schema_initialized(dsn: str | None = None) -> list[str]:
    """Inicializa el esquema de la BD del usuario si aún no lo hizo.

    Aplica las migraciones `0001_initial_schema.sql` y `0002_field_selected_indices.sql`
    automáticamente la primera vez que ve un DSN válido y lo marca en caché para no
    repetir DDL en cada request subsecuente.

    Returns:
        list[str]: Nombres de las migraciones aplicadas (vacío si ya estaba initialized).
    """
    resolved = _resolve_raw_url(dsn)
    if resolved in _INITIALIZED_DSNS:
        return []
    applied = await apply_migrations(resolved)
    _INITIALIZED_DSNS.add(resolved)
    return applied


def _resolve_raw_url(dsn: str | None = None) -> str:
    """Resuelve el DSN limpio para usar como clave de caché, ignorando placeholders."""
    dsn = dsn or os.environ.get("DATABASE_URL", "")
    if not _is_valid_dsn(dsn):
        return "<none>"
    return dsn.strip()
