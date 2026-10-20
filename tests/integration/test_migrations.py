"""
Archivo: test_migrations.py
Fecha de modificación: 20/10/2026
Autor: Alex Prieto Romani <alexprieto1997@gmail.com>

Descripción:
Simulación de usuario de la migración inicial: aplica el DDL dos veces contra un
PostgreSQL/PostGIS real y verifica que las tablas, índices y políticas de RLS
existan, y que la re-ejecución sea idempotente. Se omite si `DATABASE_URL` no está
configurado.

Ejemplo de Integración:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres \
        uv run python -m pytest tests/integration/test_migrations.py -q
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest
from dotenv import load_dotenv

from backend.db.migrate import _normalize_dsn, apply_migrations

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL no configurado (PostgreSQL/PostGIS)",
)

REQUIRED_TABLES = {
    "fields",
    "vegetation_indices",
    "weather_data",
    "user_profiles",
    "plant_counts",
    "chat_messages",
    "events",
}

REQUIRED_INDEXES = {
    "fields_geom_gist_idx",
    "idx_fields_user_id",
    "weather_data_field_timestamp_idx",
    "plant_counts_json_gin_idx",
    "chat_session_history_idx",
    "events_session_created_idx",
}


def test_apply_migrations_is_idempotent() -> None:
    """Aplicar la migración dos veces devuelve el mismo archivo y no falla."""
    first_run = asyncio.run(apply_migrations())
    second_run = asyncio.run(apply_migrations())

    assert "0001_initial_schema.sql" in first_run
    assert second_run == first_run


def test_schema_contains_tables_indexes_and_rls() -> None:
    """Tras migrar, el esquema public contiene tablas, índices y RLS habilitado."""
    asyncio.run(apply_migrations())

    async def _inspect_schema() -> tuple[set[str], set[str], set[str]]:
        conn = await asyncpg.connect(_normalize_dsn(os.environ["DATABASE_URL"]))
        try:
            table_rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            index_rows = await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            )
            rls_rows = await conn.fetch(
                "SELECT relname FROM pg_class "
                "WHERE relnamespace = 'public'::regnamespace "
                "AND relkind = 'r' AND relrowsecurity"
            )
        finally:
            await conn.close()

        return (
            {row["tablename"] for row in table_rows},
            {row["indexname"] for row in index_rows},
            {row["relname"] for row in rls_rows},
        )

    tables, indexes, rls_tables = asyncio.run(_inspect_schema())

    assert REQUIRED_TABLES <= tables
    assert REQUIRED_INDEXES <= indexes
    assert REQUIRED_TABLES <= rls_tables
