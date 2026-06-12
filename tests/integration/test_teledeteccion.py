"""
Archivo: test_teledeteccion.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas de integración de Teledetección (Fase 3) contra Sentinel Hub (CDSE) y la BD del
usuario. Verifican que la serie NDVI mensual se obtiene en vivo y que la cadena
parcela → NDVI → persistencia funciona. Se omiten si faltan credenciales de Copernicus
o `DATABASE_URL`.

Ejecución:
    uv run python -m pytest tests/integration/test_teledeteccion.py -v
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

_HAS_COP = bool(os.getenv("DEV_COPERNICUS_CLIENT_ID") and os.getenv("DEV_COPERNICUS_CLIENT_SECRET"))
_HAS_DB = bool(os.getenv("DATABASE_URL"))

from backend.db import repositories as repo  # noqa: E402
from backend.db.session import get_engine, get_sessionmaker  # noqa: E402
from backend.services import remote_sensing  # noqa: E402

_SMALL_GEOM = {
    "type": "Polygon",
    "coordinates": [
        [[-58.50, -34.60], [-58.50, -34.58], [-58.47, -34.58], [-58.47, -34.60], [-58.50, -34.60]]
    ],
}
_RANGE = ("2024-09-01T00:00:00Z", "2024-12-31T23:59:59Z")


@contextlib.asynccontextmanager
async def _engine_scope():
    """Engine fresco por test (cada test usa su propio event loop)."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield get_sessionmaker()
    finally:
        await get_engine().dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest.mark.skipif(not _HAS_COP, reason="Faltan credenciales de Copernicus")
def test_ndvi_series_live() -> None:
    """La Statistical API devuelve una serie NDVI mensual con valores en [-1, 1]."""

    async def _run() -> None:
        series = await remote_sensing.ndvi_series_monthly(
            _SMALL_GEOM,
            _RANGE[0],
            _RANGE[1],
            os.environ["DEV_COPERNICUS_CLIENT_ID"],
            os.environ["DEV_COPERNICUS_CLIENT_SECRET"],
        )
        assert len(series) >= 1
        for point in series:
            assert -1 <= point["mean_ndvi"] <= 1
            assert point["date"].endswith("-01")

    asyncio.run(_run())


@pytest.mark.skipif(not (_HAS_COP and _HAS_DB), reason="Faltan Copernicus o DATABASE_URL")
def test_parcel_ndvi_persist() -> None:
    """Cadena completa: crear parcela → calcular NDVI → persistir → leer la serie."""
    user_id = str(uuid.uuid4())

    async def _run() -> None:
        async with _engine_scope() as sm, sm() as session:
            try:
                field = await repo.create_field(
                    session, name="Lote Teledet", geojson=_SMALL_GEOM, user_id=user_id
                )
                series = await remote_sensing.ndvi_series_monthly(
                    _SMALL_GEOM,
                    _RANGE[0],
                    _RANGE[1],
                    os.environ["DEV_COPERNICUS_CLIENT_ID"],
                    os.environ["DEV_COPERNICUS_CLIENT_SECRET"],
                )
                await repo.upsert_index_points(session, field.id, series, index="ndvi")
                persisted = await repo.get_index_series(session, field.id, "ndvi")
                assert len(persisted) == len(series)
                assert len(persisted) >= 1
            finally:
                await repo.delete_fields_for_user(session, user_id)

    asyncio.run(_run())
