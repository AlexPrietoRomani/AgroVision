"""
Archivo: weather.py
Fecha de modificación: 16/06/2026
Autor: Equipo AgroVisión

Descripción:
Servicio de clima usando **Open-Meteo** (archivo histórico). Obtiene datos horarios granulares
para 13 variables y los persiste en la tabla `weather_data`. Para mantener compatibilidad
con la UI, devuelve la serie agregada mensualmente.

Estructura Interna:
    - `fetch_and_persist_weather`: Consulta Open-Meteo y persiste en DB.
    - `aggregate_weather_monthly`: Agrega datos horarios a mensuales.
    - `weather_series`: Entrada principal que orquesta la obtención y agregación.

Entradas / Dependencias:
    - `httpx`; Open-Meteo (endpoint público).
    - `backend.db.repositories` para persistencia.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

import httpx
from dateutil.relativedelta import relativedelta

from backend.db import repositories
from sqlalchemy.ext.asyncio import AsyncSession

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,dewpoint_2m,cloud_cover,pressure_msl,"
    "wind_speed_10m,wind_direction_10m,precipitation,shortwave_radiation,"
    "et0_fao_evapotranspiration,vapour_pressure_deficit,"
    "soil_temperature_0_to_7cm,soil_moisture_0_to_7cm"
)


def _default_range() -> tuple[str, str]:
    """Devuelve el rango por defecto (últimos 5 años) como fechas ISO."""
    end = dt.date.today()
    start = end - relativedelta(years=5)
    return start.isoformat(), end.isoformat()


def aggregate_weather_monthly(hourly_data: list[dict]) -> list[dict]:
    """
    Agrega el histórico horario a puntos mensuales para compatibilidad de UI.
    """
    buckets: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"precip": [], "temp": [], "rad": [], "wind": [], "humidity": []}
    )
    for row in hourly_data:
        # timestamp es formato ISO 'YYYY-MM-DDTHH:MM' o similar, tomamos YYYY-MM
        ts = str(row.get("timestamp", ""))
        if not ts:
            continue
        month = ts[:7]
        
        # Open-Meteo returns nulls sometimes, handle them
        if row.get("precipitation") is not None:
            buckets[month]["precip"].append(row["precipitation"])
        if row.get("temperature_2m") is not None:
            buckets[month]["temp"].append(row["temperature_2m"])
        if row.get("shortwave_radiation") is not None:
            buckets[month]["rad"].append(row["shortwave_radiation"])
        if row.get("wind_speed_10m") is not None:
            buckets[month]["wind"].append(row["wind_speed_10m"])
        if row.get("relative_humidity_2m") is not None:
            buckets[month]["humidity"].append(row["relative_humidity_2m"])

    series: list[dict] = []
    for month in sorted(buckets):
        values = buckets[month]
        temps = values["temp"]
        hums = values["humidity"]
        series.append(
            {
                "date": f"{month}-01",
                "precip_mm": round(sum(values["precip"]), 1) if values["precip"] else 0.0,
                "temp_mean_c": round(sum(temps) / len(temps), 1) if temps else None,
                "radiation": round(sum(values["rad"]), 1) if values["rad"] else 0.0,
                "humidity_mean": round(sum(hums) / len(hums), 1) if hums else None,
                "wind_max": round(max(values["wind"]), 1) if values["wind"] else None,
            }
        )
    return series


async def fetch_and_persist_weather(
    session: AsyncSession, field_id: Any, lat: float, lon: float, start: str, end: str
) -> list[dict]:
    """
    Consulta Open-Meteo, procesa los datos horarios y los persiste en la BD.
    
    Returns:
        list[dict]: La lista de diccionarios insertada (datos horarios).
    """
    params = {
        "latitude": str(lat),
        "longitude": str(lon),
        "start_date": start,
        "end_date": end,
        "hourly": _HOURLY_VARS,
        "timezone": "UTC",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(_ARCHIVE_URL, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    
    if not times:
        return []

    # Extraer arrays paralelos
    t2m = hourly.get("temperature_2m", [])
    rh2m = hourly.get("relative_humidity_2m", [])
    dp2m = hourly.get("dewpoint_2m", [])
    cc = hourly.get("cloud_cover", [])
    pm = hourly.get("pressure_msl", [])
    ws10 = hourly.get("wind_speed_10m", [])
    wd10 = hourly.get("wind_direction_10m", [])
    prec = hourly.get("precipitation", [])
    sr = hourly.get("shortwave_radiation", [])
    et0 = hourly.get("et0_fao_evapotranspiration", [])
    vpd = hourly.get("vapour_pressure_deficit", [])
    st = hourly.get("soil_temperature_0_to_7cm", [])
    sm = hourly.get("soil_moisture_0_to_7cm", [])

    records = []
    for i, t in enumerate(times):
        # Open-Meteo API usually returns identical length arrays
        # Use simple indexing with out-of-bounds protection fallback to None
        records.append({
            "timestamp": t + ":00Z" if len(t) == 16 else t,  # Add seconds+Z if 'YYYY-MM-DDTHH:MM'
            "temperature_2m": t2m[i] if i < len(t2m) else None,
            "relative_humidity_2m": rh2m[i] if i < len(rh2m) else None,
            "dewpoint_2m": dp2m[i] if i < len(dp2m) else None,
            "cloud_cover": cc[i] if i < len(cc) else None,
            "pressure_msl": pm[i] if i < len(pm) else None,
            "wind_speed_10m": ws10[i] if i < len(ws10) else None,
            "wind_direction_10m": wd10[i] if i < len(wd10) else None,
            "precipitation": prec[i] if i < len(prec) else None,
            "shortwave_radiation": sr[i] if i < len(sr) else None,
            "et0_fao_evapotranspiration": et0[i] if i < len(et0) else None,
            "vapour_pressure_deficit": vpd[i] if i < len(vpd) else None,
            "soil_temperature_0_to_7cm": st[i] if i < len(st) else None,
            "soil_moisture_0_to_7cm": sm[i] if i < len(sm) else None,
        })

    # Persistir en lotes para evitar sobrecargar la query
    # En 5 años son ~43800 registros
    batch_size = 5000
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        await repositories.upsert_weather_data(session, field_id, batch)

    return records


async def weather_series(
    session: AsyncSession, field_id: Any, start: str | None = None, end: str | None = None
) -> list[dict]:
    """
    Orquesta la obtención del clima horario (BD o API) y devuelve la serie mensual.
    """
    field = await repositories.get_field(session, field_id)
    if not field:
        raise ValueError("Field not found")

    if not start or not end:
        start, end = _default_range()

    # Chequear si ya tenemos datos en ese rango (aprox) en la base de datos
    # Como la descarga de 5 años toma unos segundos, para simplificar, si hay datos
    # que cubren parcialmente el rango, asumimos que no necesitamos descargar todo
    # En producción real se cruzarían rangos faltantes. Para este MV, validamos
    # si hay al menos un registro en el mes inicial.
    
    db_records = await repositories.get_weather_series(session, field_id, start, end)
    
    # Si la cantidad de registros horarios es muy pequeña (ej. < 1 mes = 720 hs),
    # o no hay datos, forzamos descarga completa
    if len(db_records) < 720:
        db_records = await fetch_and_persist_weather(
            session, field_id, lat=field.lat, lon=field.lon, start=start, end=end
        )

    return aggregate_weather_monthly(db_records)
