"""
Archivo: repositories.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Capa de acceso a datos (patrón Repository) de AgroVisión. Encapsula el SQL del dominio
para que servicios y API no escriban consultas crudas. Usa SQLAlchemy **Core** (`text`)
con PostGIS para las operaciones con geometría (más robusto que el ORM bajo asyncpg):
las parcelas se insertan con `ST_GeomFromGeoJSON` y su área se calcula con
`ST_Area(geom::geography)`. El upsert de NDVI es idempotente por `UNIQUE(field_id, date)`.

Acciones Principales:
    - CRUD de parcelas, upsert/lectura de NDVI y memoria de chat.

Estructura Interna:
    - Parcelas: `create_field`, `get_field`, `list_fields`, `delete_fields_for_user`.
    - NDVI: `upsert_ndvi_points`, `get_ndvi_series`.
    - Chat: `save_chat_message`, `get_chat_history`, `delete_chat_for_session`.

Entradas / Dependencias:
    - `sqlalchemy` (AsyncSession), PostGIS en la BD.

Salidas / Efectos:
    - Lee/escribe en la BD del usuario; las funciones de escritura hacen commit.

Ejemplo de Integración:
    from backend.db.repositories import create_field
    field = await create_field(session, name="Lote A", geojson=geojson, user_id=None)
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession


def _to_date(value: Any) -> dt.date:
    """Normaliza una fecha (date/datetime/str ISO) a `datetime.date`."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


async def create_field(
    session: AsyncSession, *, name: str, geojson: dict, user_id: str | None = None
) -> Row:
    """
    Inserta una parcela (geometría desde GeoJSON) y devuelve id, nombre y área (ha).

    Args:
        session (AsyncSession): Sesión async.
        name (str): Nombre de la parcela.
        geojson (dict): Geometría GeoJSON tipo Polygon (EPSG:4326).
        user_id (str | None): Propietario (modelo BYOK monousuario).

    Returns:
        Row: Fila con atributos `id`, `name`, `area_ha`.
    """
    result = await session.execute(
        text(
            "insert into fields (user_id, name, geom) "
            "values (:user_id, :name, ST_GeomFromGeoJSON(:geojson)) "
            "returning id, name, (ST_Area(geom::geography) / 10000.0) as area_ha"
        ),
        {"user_id": user_id, "name": name, "geojson": json.dumps(geojson)},
    )
    row = result.first()
    await session.commit()
    return row


async def get_field(session: AsyncSession, field_id: Any) -> Row | None:
    """Devuelve la parcela por id (id, name, área ha, centroide lon/lat) o None."""
    result = await session.execute(
        text(
            "select id, name, (ST_Area(geom::geography) / 10000.0) as area_ha, "
            "ST_X(ST_Centroid(geom)) as lon, ST_Y(ST_Centroid(geom)) as lat "
            "from fields where id = :id"
        ),
        {"id": str(field_id)},
    )
    return result.first()


async def get_field_geojson(session: AsyncSession, field_id: Any) -> dict | None:
    """Devuelve la geometría de la parcela como dict GeoJSON (para el heatmap), o None."""
    result = await session.execute(
        text("select ST_AsGeoJSON(geom) as gj from fields where id = :id"),
        {"id": str(field_id)},
    )
    row = result.first()
    return json.loads(row.gj) if row and row.gj else None


async def get_field_by_name(session: AsyncSession, name: str) -> Row | None:
    """
    Busca una parcela por nombre (case-insensitive) y devuelve id, nombre, área y centroide.

    Returns:
        Row | None: Fila con `id`, `name`, `area_ha`, `lon`, `lat` (centroide), o None.
    """
    result = await session.execute(
        text(
            "select id, name, (ST_Area(geom::geography) / 10000.0) as area_ha, "
            "ST_X(ST_Centroid(geom)) as lon, ST_Y(ST_Centroid(geom)) as lat "
            "from fields where lower(name) = lower(:name) order by created_at desc limit 1"
        ),
        {"name": name},
    )
    return result.first()


async def list_fields(session: AsyncSession, user_id: str | None = None) -> list[Row]:
    """Lista las parcelas (filtradas por usuario si se indica), ordenadas por nombre."""
    cols = (
        "select id, name, ST_X(ST_Centroid(geom)) as lon, "
        "ST_Y(ST_Centroid(geom)) as lat from fields"
    )
    if user_id is None:
        result = await session.execute(text(f"{cols} order by name"))
    else:
        result = await session.execute(
            text(f"{cols} where user_id = :uid order by name"), {"uid": user_id}
        )
    return list(result.all())


async def delete_fields_for_user(session: AsyncSession, user_id: str) -> None:
    """Borra todas las parcelas de un usuario (cascada borra su NDVI)."""
    await session.execute(text("delete from fields where user_id = :uid"), {"uid": user_id})
    await session.commit()


async def delete_field(session: AsyncSession, field_id: Any) -> bool:
    """Borra una parcela por id (cascada borra su NDVI). Devuelve True si existía."""
    result = await session.execute(
        text("delete from fields where id = :id returning id"), {"id": str(field_id)}
    )
    deleted = result.first() is not None
    await session.commit()
    return deleted


async def upsert_ndvi_points(
    session: AsyncSession, field_id: Any, points: list[dict]
) -> int:
    """
    Inserta/actualiza puntos NDVI de forma idempotente (`UNIQUE(field_id, date)`).

    Args:
        session (AsyncSession): Sesión async.
        field_id (Any): Parcela asociada.
        points (list[dict]): Puntos con claves 'date', 'mean_ndvi' y opcionales
            'min_ndvi', 'max_ndvi', 'cloud_cover', 'source'.

    Returns:
        int: Número de puntos procesados.
    """
    if not points:
        return 0
    params = [
        {
            "field_id": str(field_id),
            "date": _to_date(p["date"]),
            "mean_ndvi": p["mean_ndvi"],
            "min_ndvi": p.get("min_ndvi"),
            "max_ndvi": p.get("max_ndvi"),
            "cloud_cover": p.get("cloud_cover"),
            "source": p.get("source", "sentinel2"),
        }
        for p in points
    ]
    await session.execute(
        text(
            "insert into ndvi_timeseries "
            "(field_id, date, mean_ndvi, min_ndvi, max_ndvi, cloud_cover, source) "
            "values (:field_id, :date, :mean_ndvi, :min_ndvi, :max_ndvi, "
            ":cloud_cover, coalesce(:source, 'sentinel2')) "
            "on conflict (field_id, date) do update set "
            "mean_ndvi = excluded.mean_ndvi, min_ndvi = excluded.min_ndvi, "
            "max_ndvi = excluded.max_ndvi, cloud_cover = excluded.cloud_cover"
        ),
        params,
    )
    await session.commit()
    return len(params)


async def get_ndvi_series(session: AsyncSession, field_id: Any) -> list[dict]:
    """Devuelve la serie NDVI de una parcela (dicts), ordenada por fecha."""
    result = await session.execute(
        text(
            "select date, mean_ndvi, min_ndvi, max_ndvi, cloud_cover "
            "from ndvi_timeseries where field_id = :fid order by date"
        ),
        {"fid": str(field_id)},
    )
    return [dict(r._mapping) for r in result.all()]


async def save_chat_message(
    session: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
    user_id: str | None = None,
) -> Row:
    """Persiste un turno de chat y devuelve id y rol."""
    result = await session.execute(
        text(
            "insert into chat_messages (user_id, session_id, role, content) "
            "values (:user_id, :session_id, :role, :content) returning id, role"
        ),
        {"user_id": user_id, "session_id": session_id, "role": role, "content": content},
    )
    row = result.first()
    await session.commit()
    return row


async def get_chat_history(session: AsyncSession, session_id: str) -> list[Row]:
    """Devuelve el historial de una sesión ordenado cronológicamente."""
    result = await session.execute(
        text(
            "select role, content, created_at from chat_messages "
            "where session_id = :sid order by created_at, id"
        ),
        {"sid": session_id},
    )
    return list(result.all())


async def delete_chat_for_session(session: AsyncSession, session_id: str) -> None:
    """Borra los mensajes de una sesión de chat (limpieza de pruebas)."""
    await session.execute(
        text("delete from chat_messages where session_id = :sid"), {"sid": session_id}
    )
    await session.commit()
