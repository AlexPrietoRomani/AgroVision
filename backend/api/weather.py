"""
Archivo: weather.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Router de clima (`/api/weather`). Devuelve la serie agroclimática mensual (precipitación,
temperatura media, radiación) por coordenadas usando Open-Meteo (sin llave). Por defecto
cubre los últimos 5 años, para cruzarse con la serie NDVI en Teledetección.

Estructura Interna:
    - `POST /api/weather`.

Entradas / Dependencias:
    - `backend.services.weather`.

Ejemplo de Integración:
    from backend.api.weather import router
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services import weather

router = APIRouter(prefix="/api/weather", tags=["clima"])


class WeatherRequest(BaseModel):
    """Petición de clima por coordenadas y rango opcional (default últimos 5 años)."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    start: str | None = None
    end: str | None = None


@router.post("")
async def weather_series(body: WeatherRequest) -> dict:
    """Devuelve la serie climática mensual de las coordenadas indicadas."""
    series = await weather.weather_series(body.lat, body.lon, body.start, body.end)
    return {"series": series}
