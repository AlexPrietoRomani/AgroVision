"""
Archivo: parcels.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Servicio de parcelas (módulo *Creación de Parcelas*). Orquesta el alta/listado/borrado
de parcelas sobre el repositorio y dispara el **backfill** de 5 años de las variables
satelitales seleccionadas al crear una parcela. El backfill corre como tarea de fondo
(no bloquea la respuesta) y persiste cada serie mensual en `vegetation_indices` de forma
idempotente. El cálculo es selectivo en el alta e incremental cuando el usuario agrega
nuevas variables satelitales a una parcela existente.

Acciones Principales:
    - CRUD de parcelas y backfill multivariable al crear.
    - Backfill selectivo/incremental de índices espectrales.

Estructura Interna:
    - `create_parcel` / `list_parcels` / `get_parcel` / `delete_parcel`.
    - `run_indices_backfill`: tarea de fondo (sesión propia) para N índices.
    - `run_ndvi_backfill`: wrapper retrocompatible restringido a NDVI.

Entradas / Dependencias:
    - `backend.db` (repos/sesión), `backend.services.remote_sensing`.

Salidas / Efectos:
    - Escribe parcelas y series de índices espectrales en la BD del usuario.

Ejemplo de Integración:
    from backend.services import parcels
    row = await parcels.create_parcel(session, field_in)
    await parcels.run_indices_backfill(str(row.id), field_in.geojson, keys, ["ndvi", "ndwi"])
"""

from __future__ import annotations

import inspect
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


def _supported_kwargs(function: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Filtra `kwargs` según la firma real de `function`.

    Permite invocar repositorios extendidos (Fase 4) sin romper con mocks o versiones
    antiguas cuyo `create_field` aún no recibe `crop_variety`/`selected_indices`.

    Args:
        function (Any): Callable cuya firma se inspecciona.
        kwargs (dict[str, Any]): Argumentos opcionales candidatos.

    Returns:
        dict[str, Any]: Solo los argumentos que la función acepta.
    """
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return dict(kwargs)
    parameters = signature.parameters.values()
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return dict(kwargs)
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def _normalize_indices(indices: list[str] | None) -> list[str]:
    """
    Normaliza una lista de índices (minúsculas, sin vacíos ni duplicados).

    Args:
        indices (list[str] | None): Índices solicitados; `None` equivale a `["ndvi"]`.

    Returns:
        list[str]: Índices normalizados preservando el orden de entrada.
    """
    normalized: list[str] = []
    for item in indices or ["ndvi"]:
        index = str(item).strip().lower()
        if index and index not in normalized:
            normalized.append(index)
    return normalized or ["ndvi"]


async def create_parcel(
    session: AsyncSession, field_in: FieldIn, user_id: str | None = None
) -> Row:
    """
    Crea una parcela (geometría validada por `FieldIn`) y devuelve sus atributos.

    Pasa `crop_variety` y `selected_indices` al repositorio cuando su firma los
    admite; si no (mocks o repositorios previos a la Fase 4), los omite.

    Args:
        session (AsyncSession): Sesión async de base de datos.
        field_in (FieldIn): Datos validados de la parcela.
        user_id (str | None): Propietario opcional (modelo BYOK monousuario).

    Returns:
        Row: Fila con `id`, `name`, `area_ha` y, si el repo lo soporta, la selección.
    """
    optional = _supported_kwargs(
        repo.create_field,
        {
            "crop_variety": field_in.crop_variety,
            "selected_indices": field_in.selected_indices,
        },
    )
    return await repo.create_field(
        session,
        name=field_in.name,
        geojson=field_in.geojson,
        user_id=user_id,
        **optional,
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


async def run_indices_backfill(
    field_id: str,
    geojson: dict,
    keys: UserKeys,
    indices: list[str] | None = None,
    name: str = "",
) -> dict[str, int]:
    """
    Tarea de fondo: calcula y persiste la serie de cada índice satelital solicitado.

    Abre su propia sesión (se ejecuta después de responder). Captura errores para no
    romper el request ya finalizado; los registra sin exponer secretos. Se usa tanto en
    el alta selectiva (varios índices) como en la expansión incremental (solo los
    índices nuevos).

    Args:
        field_id (str): Parcela objetivo.
        geojson (dict): Geometría de la parcela.
        keys (UserKeys): Credenciales BYOK de la sesión (Copernicus).
        indices (list[str] | None): Índices a calcular; `None` equivale a `["ndvi"]`.
        name (str): Nombre de la parcela (para telemetría).

    Returns:
        dict[str, int]: Puntos persistidos por índice (vacío si no hay credenciales).
    """
    requested = _normalize_indices(indices)
    if not (keys.copernicus_id and keys.copernicus_secret):
        _logger.info("Backfill de índices omitido: faltan credenciales de Copernicus.")
        emit_event(
            "backfill_skip",
            {
                "field_id": field_id,
                "name": name,
                "indices": requested,
                "reason": "no_credentials",
            },
        )
        return {}
    counts: dict[str, int] = {}
    try:
        emit_event(
            "backfill_start",
            {"field_id": field_id, "name": name, "indices": requested},
        )
        async with get_sessionmaker(keys.database_url)() as session:
            for index in requested:
                series = await remote_sensing.index_series_monthly(
                    geojson,
                    None,
                    None,
                    keys.copernicus_id,
                    keys.copernicus_secret,
                    index=index,
                )
                counts[index] = await repo.upsert_index_points(
                    session, field_id, series, index=index
                )
        emit_event(
            "backfill_done",
            {
                "field_id": field_id,
                "name": name,
                "indices": requested,
                "points": sum(counts.values()),
                "by_index": counts,
            },
        )
        return counts
    except Exception as error:  # noqa: BLE001 - el request ya respondió; solo registramos
        _logger.warning("Backfill de índices falló para %s: %s", field_id, error)
        emit_event(
            "backfill_error",
            {
                "field_id": field_id,
                "name": name,
                "indices": requested,
                "error": str(error)[:200],
            },
        )
        return counts


async def run_ndvi_backfill(field_id: str, geojson: dict, keys: UserKeys, name: str = "") -> int:
    """
    Wrapper retrocompatible: calcula solo la serie NDVI de 5 años.

    Args:
        field_id (str): Parcela recién creada.
        geojson (dict): Geometría de la parcela.
        keys (UserKeys): Credenciales BYOK de la sesión (Copernicus).
        name (str): Nombre de la parcela (para telemetría).

    Returns:
        int: Número de puntos NDVI persistidos (0 si no hubo credenciales o falló).
    """
    counts = await run_indices_backfill(
        field_id, geojson, keys, indices=["ndvi"], name=name
    )
    return counts.get("ndvi", 0)
