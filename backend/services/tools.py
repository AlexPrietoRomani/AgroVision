"""
Archivo: tools.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Herramientas tipadas del agente RAG (function calling). El LLM no inventa datos: decide
qué función llamar y nuestro código la ejecuta contra la BD / clima real y devuelve el
resultado para que redacte. Tres herramientas: tendencia NDVI, contexto climático y
densidad de siembra (esta última, en desarrollo mientras el Conteo esté inactivo).

Acciones Principales:
    - Define `TOOLS_SCHEMA` (JSON-Schema) y `TOOL_DISPATCH` (name -> coroutine).

Estructura Interna:
    - `_describe_trend`: formateo puro de la tendencia NDVI (testeable sin BD).
    - `get_vegetation_index_trend` / `get_weather_context` / `get_field_planting_density`.

Entradas / Dependencias:
    - `backend.db.repositories`, `backend.services.weather`.

Salidas / Efectos:
    - Lecturas a la BD del usuario y a Open-Meteo.

Ejemplo de Integración:
    from backend.services.tools import TOOLS_SCHEMA, TOOL_DISPATCH
"""

from __future__ import annotations

import datetime as dt

from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import repositories as repo
from backend.services import weather


def _in_range(date_value: object, start: str | None, end: str | None) -> bool:
    """Indica si una fecha (date o str) cae dentro de [start, end] (ISO) si se dan."""
    day = str(date_value)[:10]
    if start and day < start[:10]:
        return False
    return not (end and day > end[:10])


def _describe_trend(field_name: str, series: list[dict]) -> str:
    """
    Redacta la tendencia NDVI de una serie (función pura).

    Args:
        field_name (str): Nombre de la parcela.
        series (list[dict]): Puntos con 'date' y 'mean_ndvi' ordenados por fecha.

    Returns:
        str: Texto con la tendencia (descenso/incremento/estable) y los extremos.
    """
    valid = [p for p in series if p.get("mean_ndvi") is not None]
    if len(valid) < 2:
        return f"Datos insuficientes de NDVI para '{field_name}' (se necesitan ≥2 observaciones)."
    first, last = valid[0], valid[-1]
    delta = last["mean_ndvi"] - first["mean_ndvi"]
    trend = "estable" if abs(delta) < 0.02 else ("descenso" if delta < 0 else "incremento")
    return (
        f"NDVI de '{field_name}': {trend} de {delta:+.2f} entre {str(first['date'])[:10]} "
        f"({first['mean_ndvi']:.2f}) y {str(last['date'])[:10]} ({last['mean_ndvi']:.2f}). "
        f"Observaciones: {len(valid)}."
    )


async def get_vegetation_index_trend(
    session: AsyncSession,
    field_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Tendencia de NDVI de una parcela entre dos fechas (usa la serie persistida)."""
    field = await repo.get_field_by_name(session, field_name)
    if field is None:
        return f"No encontré la parcela '{field_name}'."
    series = await repo.get_ndvi_series(session, field.id)
    in_range = [p for p in series if _in_range(p["date"], start_date, end_date)]
    return _describe_trend(field_name, in_range)


async def get_weather_context(
    session: AsyncSession,
    field_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Resumen agroclimático de una parcela (clima de Open-Meteo en su centroide)."""
    field = await repo.get_field_by_name(session, field_name)
    if field is None:
        return f"No encontré la parcela '{field_name}'."
    if not start_date or not end_date:
        end = dt.date.today()
        start = end - relativedelta(months=12)
        start_date, end_date = start.isoformat(), end.isoformat()
    series = await weather.weather_series(field.lat, field.lon, start_date, end_date)
    if not series:
        return f"Sin datos climáticos para '{field_name}' en el rango."
    total_precip = round(sum(p["precip_mm"] for p in series), 1)
    temps = [p["temp_mean_c"] for p in series if p["temp_mean_c"] is not None]
    avg_temp = round(sum(temps) / len(temps), 1) if temps else None
    return (
        f"Clima de '{field_name}' ({start_date} a {end_date}): precipitación acumulada "
        f"{total_precip} mm, temperatura media {avg_temp} °C sobre {len(series)} meses."
    )


async def get_field_planting_density(session: AsyncSession, field_name: str) -> str:
    """Densidad de siembra de una parcela (en desarrollo: depende del módulo de Conteo)."""
    field = await repo.get_field_by_name(session, field_name)
    if field is None:
        return f"No encontré la parcela '{field_name}'."
    area = f"{field.area_ha:.2f} ha" if field.area_ha else "área desconocida"
    return (
        f"La parcela '{field_name}' mide {area}. La densidad de plantas aún no está "
        "disponible: el módulo de conteo por dron está en desarrollo."
    )


TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_vegetation_index_trend",
            "description": "Tendencia del NDVI (vigor vegetal) de una parcela entre dos fechas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string", "description": "Nombre de la parcela"},
                    "start_date": {"type": "string", "description": "Inicio YYYY-MM-DD (opcional)"},
                    "end_date": {"type": "string", "description": "Fin YYYY-MM-DD (opcional)"},
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_context",
            "description": "Resumen agroclimático (precipitación y temperatura) de una parcela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string", "description": "Nombre de la parcela"},
                    "start_date": {"type": "string", "description": "Inicio YYYY-MM-DD (opcional)"},
                    "end_date": {"type": "string", "description": "Fin YYYY-MM-DD (opcional)"},
                },
                "required": ["field_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_field_planting_density",
            "description": "Densidad de siembra (pl/Ha) de una parcela. En desarrollo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string", "description": "Nombre de la parcela"},
                },
                "required": ["field_name"],
            },
        },
    },
]

TOOL_DISPATCH = {
    "get_vegetation_index_trend": get_vegetation_index_trend,
    "get_weather_context": get_weather_context,
    "get_field_planting_density": get_field_planting_density,
}
