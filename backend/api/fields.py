from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.api.events import emit as emit_event
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
    emit_event("field_created", {"id": str(row.id), "name": row.name, "area_ha": row.area_ha})
    background.add_task(parcels.run_ndvi_backfill, str(row.id), body.geojson, keys, row.name)
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
    """Elimina una parcela por id."""
    ok = await parcels.delete_parcel(session, field_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    emit_event("field_deleted", {"id": field_id})
    return {"ok": True}
