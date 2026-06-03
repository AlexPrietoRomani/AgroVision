"""
Archivo: weather.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Datos agroclimáticos por coordenadas usando **Open-Meteo** (archivo histórico, sin
llave). Se consulta on-demand y se **agrega por mes** para los gráficos de Teledetección
(precipitación sumada, temperatura media, radiación sumada). Por defecto cubre los
últimos 5 años, alineado con la serie NDVI.

Acciones Principales:
    - Descarga el histórico diario y lo resume a puntos mensuales.

Estructura Interna:
    - `_default_range`: rango por defecto (últimos 5 años).
    - `aggregate_weather_monthly`: agregación mensual pura (testeable sin red).
    - `open_meteo` / `weather_series`: descarga async + serie mensual.

Entradas / Dependencias:
    - `httpx`; Open-Meteo (endpoint público, sin credenciales).

Salidas / Efectos:
    - Llamada HTTPS a Open-Meteo; sin persistencia.

Ejemplo de Integración:
    from backend.services.weather import weather_series
    serie = await weather_series(-34.6, -58.38)
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import httpx
from dateutil.relativedelta import relativedelta

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_DAILY_VARS = "precipitation_sum,temperature_2m_mean,shortwave_radiation_sum"


def _default_range() -> tuple[str, str]:
    """Devuelve el rango por defecto (últimos 5 años) como fechas ISO."""
    end = dt.date.today()
    start = end - relativedelta(years=5)
    return start.isoformat(), end.isoformat()


def aggregate_weather_monthly(daily: dict) -> list[dict]:
    """
    Agrega el histórico diario de Open-Meteo a puntos mensuales.

    Args:
        daily (dict): Bloque 'daily' de Open-Meteo con listas paralelas 'time',
            'precipitation_sum', 'temperature_2m_mean', 'shortwave_radiation_sum'.

    Returns:
        list[dict]: Puntos {date, precip_mm, temp_mean_c, radiation} por mes,
        ordenados cronológicamente.
    """
    times = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    temp = daily.get("temperature_2m_mean", [])
    radiation = daily.get("shortwave_radiation_sum", [])

    buckets: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"precip": [], "temp": [], "rad": []}
    )
    for i, day in enumerate(times):
        month = str(day)[:7]
        if i < len(precip) and precip[i] is not None:
            buckets[month]["precip"].append(precip[i])
        if i < len(temp) and temp[i] is not None:
            buckets[month]["temp"].append(temp[i])
        if i < len(radiation) and radiation[i] is not None:
            buckets[month]["rad"].append(radiation[i])

    series: list[dict] = []
    for month in sorted(buckets):
        values = buckets[month]
        temps = values["temp"]
        series.append(
            {
                "date": f"{month}-01",
                "precip_mm": round(sum(values["precip"]), 1),
                "temp_mean_c": round(sum(temps) / len(temps), 1) if temps else None,
                "radiation": round(sum(values["rad"]), 1),
            }
        )
    return series


async def open_meteo(lat: float, lon: float, start: str, end: str) -> dict:
    """
    Descarga el bloque 'daily' del histórico de Open-Meteo para unas coordenadas.

    Args:
        lat (float): Latitud.
        lon (float): Longitud.
        start (str): Fecha inicial (YYYY-MM-DD).
        end (str): Fecha final (YYYY-MM-DD).

    Returns:
        dict: Bloque 'daily' de la respuesta.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": _DAILY_VARS,
        "timezone": "UTC",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(_ARCHIVE_URL, params=params, timeout=60)
    response.raise_for_status()
    return response.json().get("daily", {})


async def weather_series(
    lat: float, lon: float, start: str | None = None, end: str | None = None
) -> list[dict]:
    """
    Devuelve la serie climática mensual de unas coordenadas (default: últimos 5 años).

    Args:
        lat (float): Latitud.
        lon (float): Longitud.
        start (str | None): Fecha inicial; default últimos 5 años.
        end (str | None): Fecha final; default hoy.

    Returns:
        list[dict]: Serie mensual {date, precip_mm, temp_mean_c, radiation}.
    """
    if not start or not end:
        start, end = _default_range()
    daily = await open_meteo(lat, lon, start, end)
    return aggregate_weather_monthly(daily)
