"""
Archivo: weather.py
Fecha de modificación: 16/06/2026
Autor: Equipo AgroVisión

Descripción:
Router de clima (`/api/weather`). Devuelve la serie agroclimática mensual (precipitación,
temperatura media, radiación) por parcela (`field_id`) usando Open-Meteo. Los datos se
persisten a nivel horario pero se devuelven agregados mensualmente por compatibilidad UI.

Estructura Interna:
    - `POST /api/weather`.

Entradas / Dependencias:
    - `backend.services.weather`.
    - `backend.api.deps` (para la sesión DB).

Ejemplo de Integración:
    from backend.api.weather import router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services import weather

router = APIRouter(prefix="/api/weather", tags=["clima"])


class WeatherRequest(BaseModel):
    """Petición de clima por parcela y rango opcional (default últimos 5 años)."""

    field_id: str = Field(description="UUID de la parcela asociada.")
    start: str | None = None
    end: str | None = None
    raw: bool = Field(
        default=False,
        description="Si es True, devuelve la serie horaria sin agregar."
    )


@router.post("")
async def weather_series(
    body: WeatherRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Devuelve la serie climática mensual o cruda de la parcela indicada."""
    series = await weather.weather_series(
        session, body.field_id, body.start, body.end, body.raw
    )
    return {"series": series}
