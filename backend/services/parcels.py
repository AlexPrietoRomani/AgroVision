"""
Archivo: parcels.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Servicio de parcelas (módulo *Creación de Parcelas*). Orquesta el alta/listado/borrado
de parcelas sobre el repositorio y dispara el **backfill** NDVI de 5 años al crear una
parcela. El backfill corre como tarea de fondo (no bloquea la respuesta) y persiste la
serie mensual en `vegetation_indices` de forma idempotente.

Acciones Principales:
    - CRUD de parcelas y backfill NDVI al crear.

Estructura Interna:
    - `create_parcel` / `list_parcels` / `get_parcel` / `delete_parcel`.
    - `run_ndvi_backfill`: tarea de fondo (sesión propia) que llama a teledetección.

Entradas / Dependencias:
    - `backend.db` (repos/sesión), `backend.services.remote_sensing`.

Salidas / Efectos:
    - Escribe parcelas y serie NDVI en la BD del usuario.

Ejemplo de Integración:
    from backend.services import parcels
    row = await parcels.create_parcel(session, field_in)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys
from backend.api.events import emit as emit_event
from backend.core.schemas import FieldIn
from backend.db import repositories as repo
from backend.db.session import get_sessionmaker
from backend.services import remote_sensing

_logger = logging.getLogger("agrovision.parcels")


async def create_parcel(
    session: AsyncSession, field_in: FieldIn, user_id: str | None = None
) -> Row:
    """Crea una parcela (geometría validada por `FieldIn`) y devuelve id/nombre/área."""
    return await repo.create_field(
        session, name=field_in.name, geojson=field_in.geojson, user_id=user_id
    )


async def list_parcels(session: AsyncSession, user_id: str | None = None) -> list[Row]:
    """Lista las parcelas (opcionalmente filtradas por usuario)."""
    return await repo.list_fields(session, user_id=user_id)


async def get_parcel(session: AsyncSession, field_id: Any) -> Row | None:
    """Devuelve una parcela por id o None."""
    return await repo.get_field(session, field_id)


async def update_parcel(
    session: AsyncSession, field_id: Any, attributes: dict
) -> Row | None:
    """Actualiza los atributos de configuración de una parcela y la devuelve."""
    return await repo.update_field_attributes(session, field_id, attributes)


async def delete_parcel(session: AsyncSession, field_id: Any) -> bool:
    """Borra una parcela por id; True si existía."""
    return await repo.delete_field(session, field_id)


async def run_ndvi_backfill(field_id: str, geojson: dict, keys: UserKeys, name: str = "") -> int:
    """
    Tarea de fondo: calcula la serie NDVI de 5 años y la persiste en vegetation_indices.

    Abre su propia sesión (se ejecuta después de responder). Captura errores para no
    romper el request ya finalizado; los registra sin exponer secretos.

    Args:
        field_id (str): Parcela recién creada.
        geojson (dict): Geometría de la parcela.
        keys (UserKeys): Credenciales BYOK de la sesión (Copernicus).
        name (str): Nombre de la parcela (para telemetría).

    Returns:
        int: Número de puntos NDVI persistidos (0 si no hubo credenciales o falló).
    """
    if not (keys.copernicus_id and keys.copernicus_secret):
        _logger.info("Backfill NDVI omitido: faltan credenciales de Copernicus.")
        emit_event(
            "backfill_skip",
            {"field_id": field_id, "name": name, "reason": "no_credentials"},
        )
        return 0
    try:
        emit_event("backfill_start", {"field_id": field_id, "name": name})
        series = await remote_sensing.index_series_monthly(
            geojson, None, None, keys.copernicus_id, keys.copernicus_secret, index="ndvi"
        )
        async with get_sessionmaker()() as session:
            count = await repo.upsert_index_points(session, field_id, series, index="ndvi")
        emit_event("backfill_done", {"field_id": field_id, "name": name, "points": count})
        return count
    except Exception as error:  # noqa: BLE001 - el request ya respondió; solo registramos
        _logger.warning("Backfill NDVI falló para %s: %s", field_id, error)
        emit_event(
            "backfill_error",
            {"field_id": field_id, "name": name, "error": str(error)[:200]},
        )
        return 0
