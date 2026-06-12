"""
Archivo: test_agent.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Prueba de integración del agente RAG (Fase 5): con una parcela y serie NDVI sembradas,
una consulta de tendencia debe disparar la herramienta `get_vegetation_index_trend` y
producir una respuesta. Verifica function calling + memoria end-to-end. Se omite si
faltan la llave de Groq o `DATABASE_URL`.

Ejecución:
    uv run python -m pytest tests/integration/test_agent.py -v
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import pytest
from dotenv import load_dotenv

load_dotenv()

_HAS_GROQ = bool(os.getenv("DEV_GROQ_API_KEY"))
_HAS_DB = bool(os.getenv("DATABASE_URL"))

from backend.db import repositories as repo  # noqa: E402
from backend.db.session import get_engine, get_sessionmaker  # noqa: E402
from backend.services.agent import run_agent  # noqa: E402

_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[-58.0, -34.0], [-58.0, -34.1], [-57.9, -34.1], [-57.9, -34.0], [-58.0, -34.0]]
    ],
}


@contextlib.asynccontextmanager
async def _engine_scope():
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield get_sessionmaker()
    finally:
        await get_engine().dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest.mark.skipif(not (_HAS_GROQ and _HAS_DB), reason="Faltan Groq o DATABASE_URL")
def test_agente_llama_herramienta_ndvi() -> None:
    """Una consulta de NDVI dispara la herramienta de tendencia y devuelve respuesta."""
    user_id = str(uuid.uuid4())
    field_name = f"Lote Test {uuid.uuid4().hex[:6]}"
    session_id = f"sess-{uuid.uuid4()}"

    async def _run() -> None:
        async with _engine_scope() as sm, sm() as session:
            try:
                field = await repo.create_field(
                    session, name=field_name, geojson=_SQUARE, user_id=user_id
                )
                await repo.upsert_index_points(
                    session,
                    field.id,
                    [
                        {"date": "2026-01-01", "mean_ndvi": 0.80, "cloud_cover": 5},
                        {"date": "2026-03-01", "mean_ndvi": 0.68, "cloud_cover": 7},
                    ],
                    index="ndvi",
                )
                out = await run_agent(
                    session,
                    f"¿Cómo evolucionó el NDVI de {field_name}?",
                    session_id,
                    os.environ["DEV_GROQ_API_KEY"],
                    [field_name],
                )
                assert out["reply"]
                tools_used = {log["tool"] for log in out["tool_logs"]}
                assert "get_vegetation_index_trend" in tools_used
            finally:
                await repo.delete_chat_for_session(session, session_id)
                await repo.delete_fields_for_user(session, user_id)

    asyncio.run(_run())
