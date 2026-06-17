"""
Archivo: repositories.py
Fecha de modificación: 17/06/2026
Autor: Equipo AgroVisión

Descripción:
Capa de acceso a datos (patrón Repository) de AgroVisión. Encapsula el SQL del dominio
para que servicios y API no escriban consultas crudas. Usa SQLAlchemy **Core** (`text`)
con PostGIS para las operaciones con geometría (más robusto que el ORM bajo asyncpg):
las parcelas se insertan con `ST_GeomFromGeoJSON` y su área se calcula con
`ST_Area(geom::geography)`. El upsert de NDVI es idempotente por `UNIQUE(field_id, date)`.

Acciones Principales:
    - CRUD de parcelas, índices espectrales y memoria de chat.

Estructura Interna:
    - Parcelas: `create_field`, `get_field`, `list_fields`, `delete_fields_for_user`.
    - Índices espectrales: `upsert_index_points`, `get_index_series`.
    - Chat: `save_chat_message`, `get_chat_history`, `delete_chat_for_session`.
    - Perfiles de usuario: `upsert_profile`, `get_profile`, `get_profile_by_hash`,
      `update_profile`, `delete_profile`.
    - [DEPRECATED] `upsert_ndvi_points`, `get_ndvi_series` (solo tests).

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
        "ST_Y(ST_Centroid(geom)) as lat, ST_AsGeoJSON(geom) as geojson from fields"
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


async def upsert_index_points(
    session: AsyncSession, field_id: Any, points: list[dict], index: str
) -> int:
    """
    Inserta/actualiza puntos de un índice espectral de forma idempotente.

    Args:
        session (AsyncSession): Sesión async.
        field_id (Any): Parcela asociada.
        points (list[dict]): Puntos con claves 'date', 'mean_<index>' y opcionales
            'min_<index>', 'max_<index>', 'cloud_cover', 'source'.
        index (str): Nombre del índice ('ndvi', 'evi', 'savi', 'ndwi', 'ndre').

    Returns:
        int: Número de puntos procesados.
    """
    if not points:
        return 0
    key_mean = f"mean_{index}"
    key_min = f"min_{index}"
    key_max = f"max_{index}"
    params = [
        {
            "field_id": str(field_id),
            "index_type": index,
            "date": _to_date(p["date"]),
            "mean_value": p[key_mean],
            "min_value": p.get(key_min),
            "max_value": p.get(key_max),
            "cloud_cover": p.get("cloud_cover"),
            "source": p.get("source", "sentinel2"),
        }
        for p in points
    ]
    await session.execute(
        text(
            "insert into vegetation_indices "
            "(field_id, index_type, date, mean_value, min_value, max_value, cloud_cover, source) "
            "values (:field_id, :index_type, :date, :mean_value, :min_value, :max_value, "
            ":cloud_cover, coalesce(:source, 'sentinel2')) "
            "on conflict (field_id, index_type, date) do update set "
            "mean_value = excluded.mean_value, min_value = excluded.min_value, "
            "max_value = excluded.max_value, cloud_cover = excluded.cloud_cover"
        ),
        params,
    )
    await session.commit()
    return len(params)


async def get_index_series(session: AsyncSession, field_id: Any, index: str) -> list[dict]:
    """Devuelve la serie de un índice espectral de una parcela, ordenada por fecha."""
    try:
        result = await session.execute(
            text(
                "select date, mean_value, min_value, max_value, cloud_cover "
                "from vegetation_indices "
                "where field_id = :fid and index_type = :idx order by date"
            ),
            {"fid": str(field_id), "idx": index},
        )
        rows = [dict(r._mapping) for r in result.all()]
    except Exception:
        rows = []
    return rows


async def insert_event(
    session: AsyncSession,
    *,
    action: str,
    session_id: str,
    meta: dict | None = None,
) -> None:
    """Persiste un evento de telemetría (Fase 9) en la tabla `events`; hace commit."""
    await session.execute(
        text(
            "insert into events (action, session_id, meta) "
            "values (:action, :session_id, cast(:meta as jsonb))"
        ),
        {"action": action, "session_id": session_id, "meta": json.dumps(meta or {})},
    )
    await session.commit()


async def save_chat_message(
    session: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
    user_id: str | None = None,
    field_id: str | None = None,
) -> Row:
    """Persiste un turno de chat (con parcela opcional) y devuelve id y rol.

    Args:
        session (AsyncSession): Sesión de base de datos activa.
        session_id (str): Identificador de la sesión de chat.
        role (str): Rol del emisor ('user' o 'assistant').
        content (str): Contenido del mensaje.
        user_id (str, opcional): Identificador del usuario. Por defecto None.
        field_id (str, opcional): Identificador de la parcela asociada. Por defecto None.

    Returns:
        Row: Fila insertada conteniendo el id y rol.
    """
    result = await session.execute(
        text(
            "insert into chat_messages (user_id, session_id, role, content, field_id) "
            "values (:user_id, :session_id, :role, :content, :field_id) returning id, role"
        ),
        {
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "field_id": str(field_id) if field_id else None,
        },
    )
    row = result.first()
    await session.commit()
    return row


async def get_chat_history(
    session: AsyncSession, session_id: str, field_id: str | None = None
) -> list[Row]:
    """Devuelve el historial de una sesión de chat filtrando opcionalmente por parcela.

    Args:
        field_id (str, opcional): Identificador de la parcela para acotar la búsqueda.
            Por defecto None.

    Returns:
        list[Row]: Lista de filas con el rol, contenido y fecha de creación de los mensajes.
    """
    query = "select role, content, created_at from chat_messages where session_id = :sid"
    params = {"sid": session_id}
    if field_id:
        query += " and field_id = :fid"
        params["fid"] = str(field_id)
    else:
        query += " and field_id is null"
        
    query += " order by created_at, id"
    result = await session.execute(text(query), params)
    return list(result.all())


async def delete_chat_for_session(session: AsyncSession, session_id: str) -> None:
    """Borra los mensajes de una sesión de chat (limpieza de pruebas)."""
    await session.execute(
        text("delete from chat_messages where session_id = :sid"), {"sid": session_id}
    )
    await session.commit()


async def upsert_weather_data(
    session: AsyncSession, field_id: Any, data: list[dict]
) -> int:
    """
    Inserta o actualiza datos horarios de clima en la tabla `weather_data`.
    
    Args:
        session (AsyncSession): Sesión async.
        field_id (Any): Parcela asociada.
        data (list[dict]): Lista de diccionarios con las variables horarias y 'timestamp'.
        
    Returns:
        int: Número de filas procesadas.
    """
    if not data:
        return 0
        
    params = []
    for row in data:
        p = dict(row)
        p["field_id"] = str(field_id)
        params.append(p)
        
    await session.execute(
        text(
            "insert into weather_data ("
            "field_id, timestamp, temperature_2m, relative_humidity_2m, dewpoint_2m, "
            "cloud_cover, pressure_msl, wind_speed_10m, wind_direction_10m, "
            "precipitation, shortwave_radiation, et0_fao_evapotranspiration, "
            "vapour_pressure_deficit, soil_temperature_0_to_7cm, soil_moisture_0_to_7cm) "
            "values ("
            ":field_id, :timestamp, :temperature_2m, :relative_humidity_2m, :dewpoint_2m, "
            ":cloud_cover, :pressure_msl, :wind_speed_10m, :wind_direction_10m, "
            ":precipitation, :shortwave_radiation, :et0_fao_evapotranspiration, "
            ":vapour_pressure_deficit, :soil_temperature_0_to_7cm, :soil_moisture_0_to_7cm) "
            "on conflict (field_id, timestamp) do update set "
            "temperature_2m = excluded.temperature_2m, "
            "relative_humidity_2m = excluded.relative_humidity_2m, "
            "dewpoint_2m = excluded.dewpoint_2m, "
            "cloud_cover = excluded.cloud_cover, "
            "pressure_msl = excluded.pressure_msl, "
            "wind_speed_10m = excluded.wind_speed_10m, "
            "wind_direction_10m = excluded.wind_direction_10m, "
            "precipitation = excluded.precipitation, "
            "shortwave_radiation = excluded.shortwave_radiation, "
            "et0_fao_evapotranspiration = excluded.et0_fao_evapotranspiration, "
            "vapour_pressure_deficit = excluded.vapour_pressure_deficit, "
            "soil_temperature_0_to_7cm = excluded.soil_temperature_0_to_7cm, "
            "soil_moisture_0_to_7cm = excluded.soil_moisture_0_to_7cm"
        ),
        params,
    )
    await session.commit()
    return len(params)


async def get_weather_series(
    session: AsyncSession, field_id: Any, start: str | None = None, end: str | None = None
) -> list[dict]:
    """Devuelve la serie horaria climática de una parcela, ordenada por fecha."""
    try:
        query = "select * from weather_data where field_id = :fid"
        params: dict[str, Any] = {"fid": str(field_id)}
        
        if start:
            query += " and timestamp >= :start"
            params["start"] = start
        if end:
            query += " and timestamp <= :end"
            params["end"] = end
            
        query += " order by timestamp"
        
        result = await session.execute(text(query), params)
        # Convert tuples to dicts, resolving UUID and datetime objects to strings
        rows = []
        for r in result.all():
            d = dict(r._mapping)
            d["id"] = str(d["id"])
            d["field_id"] = str(d["field_id"])
            d["timestamp"] = d["timestamp"].isoformat() if d.get("timestamp") else None
            d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
            rows.append(d)
    except Exception as e:
        print(f"Error reading weather_data: {e}")
        rows = []
    return rows


# ---------------------------------------------------------------------------
# Perfiles de usuario (Fase 15)
# ---------------------------------------------------------------------------

async def upsert_profile(
    session: AsyncSession,
    supabase_url_hash: str,
    display_name: str = "Agrónomo",
) -> dict[str, Any]:
    """
    Busca un perfil existente por hash de URL de Supabase o crea uno nuevo.

    Args:
        session (AsyncSession): Sesión de base de datos activa.
        supabase_url_hash (str): Hash SHA-256 de la URL de Supabase del usuario.
        display_name (str, opcional): Nombre para mostrar. Por defecto 'Agrónomo'.

    Returns:
        dict: Diccionario con los datos del perfil (id, display_name, preferences, etc.).
    """
    result = await session.execute(
        text(
            "INSERT INTO user_profiles (supabase_url_hash, display_name) "
            "VALUES (:hash, :name) "
            "ON CONFLICT (supabase_url_hash) DO UPDATE SET updated_at = now() "
            "RETURNING id, display_name, supabase_url_hash, active_field_id, "
            "preferences, session_mode, created_at, updated_at"
        ),
        {"hash": supabase_url_hash, "name": display_name},
    )
    await session.commit()
    row = result.one()
    return _profile_row_to_dict(row)


async def get_profile(
    session: AsyncSession,
    profile_id: str,
) -> dict[str, Any] | None:
    """
    Obtiene un perfil de usuario por su ID.

    Args:
        session (AsyncSession): Sesión de base de datos activa.
        profile_id (str): UUID del perfil.

    Returns:
        dict | None: Diccionario con los datos del perfil, o None si no existe.
    """
    result = await session.execute(
        text(
            "SELECT id, display_name, supabase_url_hash, active_field_id, "
            "preferences, session_mode, created_at, updated_at "
            "FROM user_profiles WHERE id = :pid"
        ),
        {"pid": profile_id},
    )
    row = result.one_or_none()
    return _profile_row_to_dict(row) if row else None


async def get_profile_by_hash(
    session: AsyncSession,
    supabase_url_hash: str,
) -> dict[str, Any] | None:
    """
    Busca un perfil por el hash de la URL de Supabase.

    Args:
        session (AsyncSession): Sesión de base de datos activa.
        supabase_url_hash (str): Hash SHA-256 de la URL de Supabase.

    Returns:
        dict | None: Diccionario con los datos del perfil, o None si no existe.
    """
    result = await session.execute(
        text(
            "SELECT id, display_name, supabase_url_hash, active_field_id, "
            "preferences, session_mode, created_at, updated_at "
            "FROM user_profiles WHERE supabase_url_hash = :hash"
        ),
        {"hash": supabase_url_hash},
    )
    row = result.one_or_none()
    return _profile_row_to_dict(row) if row else None


async def update_profile(
    session: AsyncSession,
    profile_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Actualiza campos específicos de un perfil de usuario.

    Args:
        session (AsyncSession): Sesión de base de datos activa.
        profile_id (str): UUID del perfil a actualizar.
        updates (dict): Campos a actualizar (display_name, preferences, etc.).

    Returns:
        dict | None: Perfil actualizado, o None si no existe.
    """
    allowed_fields = {"display_name", "active_field_id", "preferences", "session_mode"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return await get_profile(session, profile_id)

    set_clauses = ", ".join(f"{k} = :{k}" for k in filtered)
    # Serializar preferences a JSON si es un dict
    params: dict[str, Any] = {"pid": profile_id}
    for k, v in filtered.items():
        params[k] = json.dumps(v) if k == "preferences" and isinstance(v, dict) else v

    result = await session.execute(
        text(
            f"UPDATE user_profiles SET {set_clauses}, updated_at = now() "
            f"WHERE id = :pid "
            f"RETURNING id, display_name, supabase_url_hash, active_field_id, "
            f"preferences, session_mode, created_at, updated_at"
        ),
        params,
    )
    await session.commit()
    row = result.one_or_none()
    return _profile_row_to_dict(row) if row else None


async def delete_profile(
    session: AsyncSession,
    profile_id: str,
) -> bool:
    """
    Elimina un perfil de usuario.

    Args:
        session (AsyncSession): Sesión de base de datos activa.
        profile_id (str): UUID del perfil a eliminar.

    Returns:
        bool: True si se eliminó correctamente, False si no existía.
    """
    result = await session.execute(
        text("DELETE FROM user_profiles WHERE id = :pid"),
        {"pid": profile_id},
    )
    await session.commit()
    return result.rowcount > 0


def _profile_row_to_dict(row: Row) -> dict[str, Any]:
    """Convierte una fila de `user_profiles` a un diccionario serializable."""
    data = dict(row._mapping)
    data["id"] = str(data["id"])
    if data.get("active_field_id"):
        data["active_field_id"] = str(data["active_field_id"])
    data["created_at"] = data["created_at"].isoformat() if data.get("created_at") else None
    data["updated_at"] = data["updated_at"].isoformat() if data.get("updated_at") else None
    return data
