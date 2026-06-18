from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.api.events import emit as emit_event
from backend.core.schemas import FieldIn, FieldUpdate
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
    """Lista las parcelas registradas con sus atributos."""
    rows = await parcels.list_parcels(session)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "lon": r.lon,
            "lat": r.lat,
            "geojson": json.loads(r.geojson) if r.geojson else None,
            "crop_variety": r.crop_variety,
            "field_type": r.field_type,
            "soil_type": r.soil_type,
            "irrigation_system": r.irrigation_system,
            "pests_diseases": r.pests_diseases,
            "plantation_date": r.plantation_date.isoformat() if r.plantation_date else None,
            "num_plants": r.num_plants,
            "historical_yield": r.historical_yield,
            "target_market": r.target_market,
            "document_metadata": r.document_metadata,
        }
        for r in rows
    ]


@router.get("/{field_id}")
async def get_field(field_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Devuelve una parcela por id con sus atributos (404 si no existe)."""
    row = await parcels.get_parcel(session, field_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    return {
        "id": str(row.id),
        "name": row.name,
        "area_ha": row.area_ha,
        "lon": row.lon,
        "lat": row.lat,
        "crop_variety": row.crop_variety,
        "field_type": row.field_type,
        "soil_type": row.soil_type,
        "irrigation_system": row.irrigation_system,
        "pests_diseases": row.pests_diseases,
        "plantation_date": row.plantation_date.isoformat() if row.plantation_date else None,
        "num_plants": row.num_plants,
        "historical_yield": row.historical_yield,
        "target_market": row.target_market,
        "document_metadata": row.document_metadata,
    }


@router.patch("/{field_id}")
async def update_field(
    field_id: str,
    body: FieldUpdate,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Actualiza parcialmente los atributos de configuración de una parcela."""
    updates = body.model_dump(exclude_unset=True)
    row = await parcels.update_parcel(session, field_id, updates)
    if row is None:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    emit_event("field_updated", {"id": field_id, "updates": list(updates.keys())})
    return {
        "id": str(row.id),
        "name": row.name,
        "area_ha": row.area_ha,
        "crop_variety": row.crop_variety,
        "field_type": row.field_type,
        "soil_type": row.soil_type,
        "irrigation_system": row.irrigation_system,
        "pests_diseases": row.pests_diseases,
        "plantation_date": row.plantation_date.isoformat() if row.plantation_date else None,
        "num_plants": row.num_plants,
        "historical_yield": row.historical_yield,
        "target_market": row.target_market,
        "document_metadata": row.document_metadata,
    }


@router.delete("/{field_id}")
async def delete_field(field_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Elimina una parcela por id."""
    ok = await parcels.delete_parcel(session, field_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Parcela no encontrada")
    emit_event("field_deleted", {"id": field_id})
    return {"ok": True}
