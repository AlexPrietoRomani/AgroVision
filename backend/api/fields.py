"""
Archivo: fields.py
Fecha de modificación: 28/10/2026
Autor: Equipo AgroVisión

Descripción:
Router REST del módulo *Creación de Parcelas* (Fase 5). Expone el CRUD de parcelas con
sus variables satelitales seleccionadas (`selected_indices`). Al crear una parcela se
agenda el backfill de los índices elegidos; al actualizarla se detectan los índices
nuevos respecto a los ya calculados y se agenda únicamente su cálculo incremental.

Acciones Principales:
    - Crear, listar, consultar, actualizar y borrar parcelas.
    - Disparar el backfill selectivo (alta) e incremental (PATCH).

Estructura Interna:
    - `create_field`: alta + backfill de `body.selected_indices`.
    - `list_fields` / `get_field`: lectura con `selected_indices` y `calculated_indices`.
    - `update_field`: actualización con detección de índices nuevos.
    - `delete_field`: borrado.

Entradas / Dependencias:
    - `backend.services.parcels`, `backend.db.repositories`, cabeceras BYOK.

Salidas / Efectos:
    - Escribe parcelas y agenda tareas de fondo de teledetección.

Ejemplo de Integración:
    from backend.api.fields import router
"""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.api.events import emit as emit_event
from backend.core.schemas import FieldIn, FieldUpdate
from backend.db import repositories as repo
from backend.services import parcels

router = APIRouter(prefix="/api/fields", tags=["parcelas"])


async def _get_calculated_indices(session: AsyncSession, field_id: str) -> list[str]:
    """
    Consulta los índices ya calculados de una parcela si el repositorio lo soporta.

    Fase 4 añade `get_calculated_indices`; mientras no esté disponible (o el repo sea
    un mock antiguo) se devuelve una lista vacía.

    Args:
        session (AsyncSession): Sesión async de base de datos.
        field_id (str): Identificador de la parcela.

    Returns:
        list[str]: Tipos de índice con serie persistida (vacío si no se puede saber).
    """
    calculator = getattr(repo, "get_calculated_indices", None)
    if not callable(calculator):
        return []
    return list(await calculator(session, field_id) or [])


def _selected_indices(row: object, fallback: list[str] | None = None) -> list[str]:
    """Devuelve la selección de la fila o `fallback`/`["ndvi"]` si no la expone."""
    return list(getattr(row, "selected_indices", None) or fallback or ["ndvi"])


def _field_payload(row: object) -> dict:
    """Serializa los atributos comunes de una parcela para la respuesta HTTP."""
    return {
        "id": str(row.id),
        "name": row.name,
        "area_ha": row.area_ha,
        "crop_variety": getattr(row, "crop_variety", None),
        "field_type": getattr(row, "field_type", None),
        "soil_type": getattr(row, "soil_type", None),
        "irrigation_system": getattr(row, "irrigation_system", None),
        "pests_diseases": getattr(row, "pests_diseases", None),
        "plantation_date": (
            row.plantation_date.isoformat()
            if getattr(row, "plantation_date", None)
            else None
        ),
        "num_plants": getattr(row, "num_plants", None),
        "historical_yield": getattr(row, "historical_yield", None),
        "target_market": getattr(row, "target_market", None),
        "document_metadata": getattr(row, "document_metadata", None),
    }


@router.post("")
async def create_field(
    body: FieldIn,
    background: BackgroundTasks,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Crea una parcela y agenda el backfill de las variables satelitales elegidas."""
    row = await parcels.create_parcel(session, body, user_id=None)
    selected = _selected_indices(row, body.selected_indices)
    emit_event(
        "field_created",
        {
            "id": str(row.id),
            "name": row.name,
            "area_ha": row.area_ha,
            "selected_indices": selected,
        },
    )
    background.add_task(
        parcels.run_indices_backfill,
        str(row.id),
        body.geojson,
        keys,
        body.selected_indices,
        row.name,
    )
    return {
        "id": str(row.id),
        "name": row.name,
        "area_ha": row.area_ha,
        "crop_variety": getattr(row, "crop_variety", body.crop_variety),
        "selected_indices": selected,
    }


@router.get("")
async def list_fields(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """Lista las parcelas registradas con sus atributos y variables satelitales."""
    rows = await parcels.list_parcels(session)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "lon": r.lon,
            "lat": r.lat,
            "geojson": json.loads(r.geojson) if r.geojson else None,
            "crop_variety": getattr(r, "crop_variety", None),
            "field_type": getattr(r, "field_type", None),
            "soil_type": getattr(r, "soil_type", None),
            "irrigation_system": getattr(r, "irrigation_system", None),
            "pests_diseases": getattr(r, "pests_diseases", None),
            "plantation_date": (
                r.plantation_date.isoformat() if getattr(r, "plantation_date", None) else None
            ),
            "num_plants": getattr(r, "num_plants", None),
            "historical_yield": getattr(r, "historical_yield", None),
            "target_market": getattr(r, "target_market", None),
            "document_metadata": getattr(r, "document_metadata", None),
            "selected_indices": _selected_indices(r),
        }
        for r in rows
    ]


@router.get("/{field_id}")
async def get_field(field_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Devuelve una parcela con sus variables seleccionadas y calculadas (404 si no existe)."""
    row = await parcels.get_parcel(session, field_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    payload = _field_payload(row)
    payload["lon"] = getattr(row, "lon", None)
    payload["lat"] = getattr(row, "lat", None)
    payload["selected_indices"] = _selected_indices(row)
    payload["calculated_indices"] = await _get_calculated_indices(session, field_id)
    return payload


@router.patch("/{field_id}")
async def update_field(
    field_id: str,
    body: FieldUpdate,
    background: BackgroundTasks,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Actualiza parcialmente una parcela y calcula solo las variables satelitales nuevas.

    Compara `selected_indices` con los índices ya calculados (o, si no se pueden
    consultar, con la selección anterior) y agenda en segundo plano el backfill
    incremental únicamente de los añadidos.
    """
    previous = await parcels.get_parcel(session, field_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")

    updates = body.model_dump(exclude_unset=True)
    new_indices: list[str] = []
    if body.selected_indices is not None:
        calculated = await _get_calculated_indices(session, field_id)
        baseline = set(calculated) if calculated else set(_selected_indices(previous))
        new_indices = [index for index in body.selected_indices if index not in baseline]

    row = await parcels.update_parcel(session, field_id, updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")

    if new_indices:
        geojson = await repo.get_field_geojson(session, field_id)
        if geojson:
            background.add_task(
                parcels.run_indices_backfill,
                field_id,
                geojson,
                keys,
                new_indices,
                row.name,
            )
        emit_event(
            "field_indices_expanded",
            {"id": field_id, "indices": new_indices},
        )

    emit_event("field_updated", {"id": field_id, "updates": list(updates.keys())})
    payload = _field_payload(row)
    payload["selected_indices"] = _selected_indices(row, body.selected_indices)
    return payload


@router.delete("/{field_id}")
async def delete_field(field_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Elimina una parcela por id."""
    ok = await parcels.delete_parcel(session, field_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    emit_event("field_deleted", {"id": field_id})
    return {"ok": True}
