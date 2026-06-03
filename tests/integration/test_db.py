"""
Archivo: test_db.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas de integración de la capa de persistencia (Fase 2) contra el Supabase del
usuario (PostgreSQL + PostGIS). Verifican que las migraciones crean el esquema, que
el CRUD de parcelas hace round-trip, que el upsert de NDVI es idempotente y que la
memoria de chat se recupera ordenada. Se omiten si `DATABASE_URL` no está configurado.

Ejecución:
    uv run python -m pytest tests/integration/test_db.py -v

Nota: estos tests escriben en la BD real usando un `user_id` aleatorio y limpian sus
propias filas al final (no contaminan datos existentes).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="DATABASE_URL no configurado (Supabase)"
)

from backend.db import repositories as repo  # noqa: E402
from backend.db.migrate import apply_migrations  # noqa: E402
from backend.db.session import get_engine, get_sessionmaker  # noqa: E402


@contextlib.asynccontextmanager
async def _engine_scope():
    """
    Provee un sessionmaker con engine fresco por test y lo desecha en el mismo loop.

    Necesario porque cada test usa su propio `asyncio.run()` (event loop nuevo) y el
    engine está memoizado; sin esto, el pool quedaría atado a un loop ya cerrado.
    """
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield get_sessionmaker()
    finally:
        await get_engine().dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()

_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[-58.0, -34.0], [-58.0, -34.1], [-57.9, -34.1], [-57.9, -34.0], [-58.0, -34.0]]
    ],
}


@pytest.fixture(scope="module", autouse=True)
def _migrate() -> None:
    """Aplica las migraciones una vez antes del módulo (idempotente)."""
    asyncio.run(apply_migrations())


def test_migraciones_crean_las_tablas() -> None:
    """Tras migrar, las 4 tablas del diseño existen en el esquema public."""

    async def _run() -> None:
        from sqlalchemy import text

        async with _engine_scope() as sm, sm() as session:
            rows = await session.execute(
                text(
                    "select table_name from information_schema.tables "
                    "where table_schema='public' and table_name = any(:names)"
                ),
                {"names": ["fields", "ndvi_timeseries", "plant_counts", "chat_messages"]},
            )
            present = {r[0] for r in rows}
        assert present == {"fields", "ndvi_timeseries", "plant_counts", "chat_messages"}

    asyncio.run(_run())


def test_field_crud_roundtrip() -> None:
    """Crear → obtener → listar → borrar una parcela funciona de extremo a extremo."""
    user_id = str(uuid.uuid4())

    async def _run() -> None:
        async with _engine_scope() as sm, sm() as session:
            try:
                field = await repo.create_field(
                    session, name="Lote Test", geojson=_SQUARE, user_id=user_id
                )
                assert field.name == "Lote Test"
                fetched = await repo.get_field(session, field.id)
                assert fetched is not None
                listed = await repo.list_fields(session, user_id=user_id)
                assert any(f.id == field.id for f in listed)
                assert field.area_ha and field.area_ha > 0  # ST_Area calculada
            finally:
                await repo.delete_fields_for_user(session, user_id)

    asyncio.run(_run())


def test_ndvi_upsert_idempotente() -> None:
    """Reinsertar los mismos puntos NDVI no duplica filas (UNIQUE field_id, date)."""
    user_id = str(uuid.uuid4())
    points = [
        {"date": "2026-03-01", "mean_ndvi": 0.66, "cloud_cover": 8},
        {"date": "2026-04-01", "mean_ndvi": 0.72, "cloud_cover": 5},
    ]

    async def _run() -> None:
        async with _engine_scope() as sm, sm() as session:
            try:
                field = await repo.create_field(
                    session, name="Lote NDVI", geojson=_SQUARE, user_id=user_id
                )
                await repo.upsert_ndvi_points(session, field.id, points)
                await repo.upsert_ndvi_points(session, field.id, points)  # idempotente
                series = await repo.get_ndvi_series(session, field.id)
                assert len(series) == 2
                assert [p["date"].isoformat() for p in series] == ["2026-03-01", "2026-04-01"]
            finally:
                await repo.delete_fields_for_user(session, user_id)

    asyncio.run(_run())


def test_chat_history_ordenado() -> None:
    """La memoria conversacional se recupera en orden cronológico por sesión."""
    user_id = str(uuid.uuid4())
    session_id = f"sess-{uuid.uuid4()}"

    async def _run() -> None:
        async with _engine_scope() as sm, sm() as session:
            try:
                await repo.save_chat_message(
                    session, session_id=session_id, role="user", content="hola", user_id=user_id
                )
                await repo.save_chat_message(
                    session,
                    session_id=session_id,
                    role="assistant",
                    content="qué tal",
                    user_id=user_id,
                )
                history = await repo.get_chat_history(session, session_id)
                assert [m.role for m in history] == ["user", "assistant"]
            finally:
                await repo.delete_chat_for_session(session, session_id)

    asyncio.run(_run())
