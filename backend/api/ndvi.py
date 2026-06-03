"""
Archivo: ndvi.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Router de Teledetección (NDVI). `POST /api/ndvi` devuelve la serie mensual: si se pasa
`field_id`, la lee persistida (rápida); si se pasa `geojson`, la calcula en vivo vía
Sentinel Hub (default últimos 5 años). `POST /api/ndvi/raster` devuelve el heatmap NDVI
(PNG ~10 m/px) para pintar como capa en el mapa.

Estructura Interna:
    - `POST /api/ndvi` (serie), `POST /api/ndvi/raster` (heatmap PNG).

Entradas / Dependencias:
    - `backend.services.remote_sensing`, `backend.db.repositories`, `backend.api.deps`.

Ejemplo de Integración:
    from backend.api.ndvi import router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.db import repositories as repo
from backend.services import remote_sensing

router = APIRouter(prefix="/api/ndvi", tags=["teledetección"])


class NdviRequest(BaseModel):
    """Petición de serie NDVI: por parcela (persistida) o por geometría (en vivo)."""

    field_id: str | None = None
    geojson: dict | None = None
    start: str | None = None
    end: str | None = None


class NdviRasterRequest(BaseModel):
    """Petición de heatmap NDVI (PNG) por parcela (`field_id`) o geometría directa."""

    field_id: str | None = None
    geojson: dict | None = None
    start: str | None = None
    end: str | None = None


def _require_copernicus(keys: UserKeys) -> None:
    """Lanza 400 si faltan las credenciales de Copernicus para una consulta en vivo."""
    if not (keys.copernicus_id and keys.copernicus_secret):
        raise HTTPException(
            status_code=400, detail="Faltan credenciales de Copernicus (pestaña Credenciales)."
        )


@router.post("")
async def ndvi_series(
    body: NdviRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Devuelve la serie NDVI mensual (persistida por parcela o calculada en vivo)."""
    if body.field_id:
        series = await repo.get_ndvi_series(session, body.field_id)
        return {"series": series}
    if body.geojson:
        _require_copernicus(keys)
        series = await remote_sensing.ndvi_series_monthly(
            body.geojson, body.start, body.end, keys.copernicus_id, keys.copernicus_secret
        )
        return {"series": series}
    raise HTTPException(status_code=422, detail="Indica 'field_id' o 'geojson'.")


@router.post("/raster")
async def ndvi_raster(
    body: NdviRasterRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Devuelve el heatmap NDVI (PNG ~10 m/px) por parcela (`field_id`) o geometría."""
    _require_copernicus(keys)
    geojson = body.geojson
    if geojson is None and body.field_id:
        geojson = await repo.get_field_geojson(session, body.field_id)
    if geojson is None:
        raise HTTPException(status_code=422, detail="Indica 'field_id' o 'geojson'.")
    png = await remote_sensing.ndvi_heatmap_png(
        geojson, keys.copernicus_id, keys.copernicus_secret, body.start, body.end
    )
    return Response(content=png, media_type="image/png")
