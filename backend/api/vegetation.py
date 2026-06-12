from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.api.events import emit as emit_event
from backend.db import repositories as repo
from backend.services import remote_sensing

_VALID_INDICES = {"ndvi", "evi", "savi", "ndwi", "ndre"}
_INDEX_DESCRIPTIONS = {
    "ndvi": "NDVI — Normalized Difference Vegetation Index (salud vegetal general)",
    "evi": "EVI — Enhanced Vegetation Index (corrige aerosoles, mejor en vegetación densa)",
    "savi": "SAVI — Soil Adjusted Vegetation Index (minimiza suelo desnudo)",
    "ndwi": "NDWI — Normalized Difference Water Index (contenido de agua)",
    "ndre": "NDRE — Normalized Difference Red Edge (clorofila/nitrógeno, detección temprana)",
}

router = APIRouter(prefix="/api/vegetation", tags=["teledetección"])


class IndexRequest(BaseModel):
    field_id: str | None = None
    geojson: dict | None = None
    start: str | None = None
    end: str | None = None


class IndexRasterRequest(BaseModel):
    field_id: str | None = None
    geojson: dict | None = None
    start: str | None = None
    end: str | None = None


class ReprocessRequest(BaseModel):
    field_id: str
    mode: str = "all"  # "indices" | "weather" | "all"


def _require_copernicus(keys: UserKeys) -> None:
    if not (keys.copernicus_id and keys.copernicus_secret):
        raise HTTPException(
            status_code=400, detail="Faltan credenciales de Copernicus (pestaña Credenciales)."
        )


def _validate_index(index: str) -> None:
    if index not in _VALID_INDICES:
        raise HTTPException(
            status_code=422,
            detail=f"Índice no válido: '{index}'. Válidos: {', '.join(sorted(_VALID_INDICES))}.",
        )


@router.get("/indices")
async def list_indices() -> dict:
    """Devuelve la lista de índices espectrales disponibles con descripciones."""
    return {"indices": [{"id": k, "description": v} for k, v in _INDEX_DESCRIPTIONS.items()]}


@router.post("/reprocess")
async def reprocess_field(
    body: ReprocessRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Recalcula TODOS los índices espectrales (y opcionalmente clima) para una parcela."""
    _require_copernicus(keys)
    if body.mode not in ("indices", "weather", "all"):
        raise HTTPException(status_code=422, detail="mode debe ser 'indices', 'weather' o 'all'.")
    geojson = await repo.get_field_geojson(session, body.field_id)
    if not geojson:
        raise HTTPException(status_code=404, detail="Parcela no encontrada.")
    result: dict = {"field_id": body.field_id, "mode": body.mode, "indices": [], "weather": False}
    if body.mode in ("indices", "all"):
        for index in sorted(_VALID_INDICES):
            series = await remote_sensing.index_series_monthly(
                geojson, None, None, keys.copernicus_id, keys.copernicus_secret, index
            )
            count = await repo.upsert_index_points(session, body.field_id, series, index)
            result["indices"].append({"index": index, "points": count})
    if body.mode in ("weather", "all"):
        result["weather"] = True
    emit_event("reprocess_done", result)
    return result


@router.post("/{index}")
async def index_series(
    index: str,
    body: IndexRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Devuelve la serie mensual de un índice (persistida o calculada en vivo)."""
    _validate_index(index)
    if body.field_id:
        series = await repo.get_index_series(session, body.field_id, index)
        emit_event(
            "index_series",
            {"index": index, "field_id": body.field_id, "source": "db", "points": len(series)},
        )
        return {"index": index, "series": series}
    if body.geojson:
        _require_copernicus(keys)
        emit_event(
            "index_series",
            {"index": index, "source": "copernicus", "start": body.start, "end": body.end},
        )
        series = await remote_sensing.index_series_monthly(
            body.geojson, body.start, body.end, keys.copernicus_id, keys.copernicus_secret, index
        )
        return {"index": index, "series": series}
    raise HTTPException(status_code=422, detail="Indica 'field_id' o 'geojson'.")


@router.post("/{index}/raster")
async def index_raster(
    index: str,
    body: IndexRasterRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Devuelve el heatmap (PNG ~10 m/px) de un índice por parcela o geometría."""
    _validate_index(index)
    _require_copernicus(keys)
    geojson = body.geojson
    if geojson is None and body.field_id:
        geojson = await repo.get_field_geojson(session, body.field_id)
    if geojson is None:
        raise HTTPException(status_code=422, detail="Indica 'field_id' o 'geojson'.")
    emit_event(
        "index_raster",
        {"index": index, "field_id": body.field_id, "start": body.start, "end": body.end},
    )
    png = await remote_sensing.index_heatmap_png(
        geojson, keys.copernicus_id, keys.copernicus_secret, body.start, body.end, index=index
    )
    return Response(content=png, media_type="image/png")
