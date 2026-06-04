"""
Archivo: fields.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Router del módulo *Creación de Parcelas*: CRUD de parcelas (`/api/fields`). Al crear una
parcela, dispara en segundo plano el backfill NDVI de 5 años (si hay credenciales de
Copernicus). La geometría se valida con `FieldIn` (polígono cerrado EPSG:4326).

Estructura Interna:
    - `POST /api/fields`, `GET /api/fields`, `GET /api/fields/{id}`, `DELETE /api/fields/{id}`.

Entradas / Dependencias:
    - `backend.services.parcels`, `backend.api.deps`.

Ejemplo de Integración:
    from backend.api.fields import router
"""

from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.core.schemas import FieldIn
from backend.services import parcels

router = APIRouter(prefix="/api/fields", tags=["parcelas"])


@router.post("")
async def create_field(
    body: FieldIn,
    background: BackgroundTasks,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Crea una parcela y agenda el backfill NDVI de 5 años en segundo plano."""
    row = await parcels.create_parcel(session, body, user_id=None)
    background.add_task(parcels.run_ndvi_backfill, str(row.id), body.geojson, keys)
    return {"id": str(row.id), "name": row.name, "area_ha": row.area_ha}


@router.get("")
async def list_fields(session: AsyncSession = Depends(get_db)) -> list[dict]:
    """Lista las parcelas registradas."""
    rows = await parcels.list_parcels(session)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "lon": r.lon,
            "lat": r.lat,
            "geojson": json.loads(r.geojson) if r.geojson else None,
        }
        for r in rows
    ]


@router.get("/{field_id}")
async def get_field(field_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Devuelve una parcela por id (404 si no existe)."""
    row = await parcels.get_parcel(session, field_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    return {
        "id": str(row.id),
        "name": row.name,
        "area_ha": row.area_ha,
        "lon": row.lon,
        "lat": row.lat,
    }


@router.delete("/{field_id}")
async def delete_field(field_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Borra una parcela por id (404 si no existía)."""
    if not await parcels.delete_parcel(session, field_id):
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    return {"deleted": field_id}
