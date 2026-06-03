"""
Archivo: test_weather.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias (sin red) de la agregación mensual del clima de Open-Meteo.

Ejecución:
    uv run python -m pytest tests/unit/test_weather.py
"""

from __future__ import annotations

from backend.services.weather import aggregate_weather_monthly

_DAILY = {
    "time": ["2026-04-01", "2026-04-02", "2026-05-01"],
    "precipitation_sum": [10.0, 5.0, 20.0],
    "temperature_2m_mean": [18.0, 20.0, 22.0],
    "shortwave_radiation_sum": [100.0, 110.0, 120.0],
}


def test_aggregate_weather_monthly_suma_y_promedia() -> None:
    """Precipitación y radiación se suman por mes; la temperatura se promedia."""
    series = aggregate_weather_monthly(_DAILY)
    assert [p["date"] for p in series] == ["2026-04-01", "2026-05-01"]
    abril = series[0]
    assert abril["precip_mm"] == 15.0
    assert abril["temp_mean_c"] == 19.0
    assert abril["radiation"] == 210.0


def test_aggregate_weather_monthly_vacio() -> None:
    """Un bloque diario vacío produce una serie vacía."""
    assert aggregate_weather_monthly({}) == []
