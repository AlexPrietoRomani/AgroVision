"""
Archivo: test_migrations.py
Fecha de modificación: 20/10/2026
Autor: Alex Prieto Romani <alexprieto1997@gmail.com>

Descripción:
Pruebas unitarias de las migraciones SQL versionadas de AgroVisión. Verifican que
`backend.db.migrate` descubre el archivo inicial, que el DDL cubre las tablas del
diseño y que las sentencias son idempotentes. No requieren una base de datos.

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_migrations.py -q
"""

from __future__ import annotations

import re

import pytest

from backend.db.migrate import MIGRATIONS_DIR, _normalize_dsn

INITIAL_MIGRATION = MIGRATIONS_DIR / "0001_initial_schema.sql"

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


def _read_sql() -> str:
    """Devuelve el contenido de la migración inicial."""
    return INITIAL_MIGRATION.read_text(encoding="utf-8")


def _without_comments(sql: str) -> str:
    """Elimina los comentarios `--` para inspeccionar solo sentencias ejecutables."""
    return re.sub(r"--.*$", "", sql, flags=re.MULTILINE)


def _normalized(sql: str) -> str:
    """Colapsa espacios y saltos de línea para comparar fragmentos DDL."""
    return re.sub(r"\s+", " ", sql.lower()).strip()


def test_migrations_directory_exists() -> None:
    """El directorio que consume `backend.db.migrate` existe."""
    assert MIGRATIONS_DIR.is_dir()


def test_initial_schema_is_discovered() -> None:
    """El migrador descubre la migración inicial por su patrón `*.sql`."""
    assert INITIAL_MIGRATION.is_file()
    assert INITIAL_MIGRATION in sorted(MIGRATIONS_DIR.glob("*.sql"))


def test_schema_creates_every_designed_table() -> None:
    """El DDL crea todas las tablas documentadas en `diseno_db.md`."""
    sql = _normalized(_read_sql())
    for table in REQUIRED_TABLES:
        statement = f"create table if not exists public.{table} ("
        assert statement in sql, f"Falta la tabla {table}"


def test_schema_creates_postgis_and_spatial_index() -> None:
    """El DDL habilita PostGIS y crea el índice GIST de parcelas."""
    sql = _normalized(_read_sql())
    assert "create extension if not exists postgis" in sql
    assert (
        "create index if not exists fields_geom_gist_idx "
        "on public.fields using gist (geom)" in sql
    )


def test_schema_creates_documented_indexes() -> None:
    """El DDL crea los índices de timestamp, FK y JSONB declarados en el diseño."""
    sql = _normalized(_read_sql())
    for index in REQUIRED_INDEXES:
        assert f"create index if not exists {index}" in sql, f"Falta el índice {index}"


def test_schema_uses_idempotent_ddl() -> None:
    """No hay CREATE TABLE/INDEX/EXTENSION sin la cláusula IF NOT EXISTS."""
    sql = _normalized(_without_comments(_read_sql()))
    forbidden_patterns = (
        r"create table (?!if not exists)",
        r"create index (?!if not exists)",
        r"create extension (?!if not exists)",
        r"create unique index (?!if not exists)",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, sql) is None, f"DDL no idempotente: {pattern}"


def test_schema_declares_unique_natural_keys() -> None:
    """Los UNIQUE que sostienen los upserts idempotentes están declarados."""
    sql = _normalized(_read_sql())
    assert "unique (field_id, index_type, date)" in sql
    assert "unique (field_id, timestamp)" in sql
    assert "unique (supabase_url_hash)" in sql


def test_schema_declares_integrity_constraints() -> None:
    """Las reglas de negocio del diccionario se materializan como CHECK."""
    sql = _normalized(_read_sql())
    assert "check (st_isvalid(geom))" in sql
    assert "check (index_type in ('ndvi', 'evi', 'savi', 'ndwi', 'ndre'))" in sql
    assert "check (role in ('user', 'assistant'))" in sql
    assert "check (count >= 0)" in sql
    assert (
        "check (session_mode in ('ephemeral', 'saved', 'shared'))" in sql
    )


def test_schema_enables_rls_on_every_table() -> None:
    """Todas las tablas habilitan Row Level Security."""
    sql = _normalized(_read_sql())
    for table in REQUIRED_TABLES:
        statement = f"alter table public.{table} enable row level security"
        assert statement in sql, f"RLS no habilitado en {table}"


@pytest.mark.parametrize(
    ("raw_dsn", "expected_dsn"),
    [
        (
            "postgresql+asyncpg://user:pass@localhost:5432/agrovision",
            "postgresql://user:pass@localhost:5432/agrovision",
        ),
        (
            "postgresql://user:pass@localhost:5432/agrovision",
            "postgresql://user:pass@localhost:5432/agrovision",
        ),
    ],
)
def test_normalize_dsn_for_asyncpg(raw_dsn: str, expected_dsn: str) -> None:
    """El DSN de SQLAlchemy se convierte al formato nativo de asyncpg."""
    assert _normalize_dsn(raw_dsn) == expected_dsn
