"""
Archivo: test_weather.py
Fecha de modificacion: 12/06/2026
Autor: Equipo AgroVision

Descripcion:
Pruebas unitarias (sin red) de la agregacion mensual del clima de Open-Meteo.

Ejecucion:
    uv run python -m pytest tests/unit/test_weather.py
"""

from __future__ import annotations

from backend.services.weather import aggregate_weather_monthly

_DAILY = {
    "time": ["2026-04-01", "2026-04-02", "2026-05-01"],
    "precipitation_sum": [10.0, 5.0, 20.0],
    "temperature_2m_mean": [18.0, 20.0, 22.0],
    "shortwave_radiation_sum": [100.0, 110.0, 120.0],
    "wind_speed_10m_max": [15.0, 10.0, 20.0],
}

_HOURLY = {
    "time": [
        "2026-04-01T00:00",
        "2026-04-01T12:00",
        "2026-04-02T00:00",
        "2026-04-02T12:00",
        "2026-05-01T00:00",
        "2026-05-01T12:00",
    ],
    "relative_humidity_2m": [60.0, 65.0, 70.0, 75.0, 80.0, 85.0],
}


def test_aggregate_weather_monthly_suma_y_promedia() -> None:
    """Precipitacion y radiacion se suman; temperatura y humedad se promedian; viento es maximo."""
    series = aggregate_weather_monthly(_DAILY, _HOURLY)
    assert [p["date"] for p in series] == ["2026-04-01", "2026-05-01"]
    abril = series[0]
    assert abril["precip_mm"] == 15.0
    assert abril["temp_mean_c"] == 19.0
    assert abril["radiation"] == 210.0
    assert abril["humidity_mean"] == 67.5
    assert abril["wind_max"] == 15.0
    mayo = series[1]
    assert mayo["precip_mm"] == 20.0
    assert mayo["temp_mean_c"] == 22.0
    assert mayo["radiation"] == 120.0
    assert mayo["humidity_mean"] == 82.5
    assert mayo["wind_max"] == 20.0


def test_aggregate_weather_monthly_sin_horario() -> None:
    """Sin bloque horario, humidity_mean y wind_max deben ser None si no hay datos."""
    daily_no_wind = {k: v for k, v in _DAILY.items() if k != "wind_speed_10m_max"}
    series = aggregate_weather_monthly(daily_no_wind)
    assert len(series) == 2
    assert series[0]["humidity_mean"] is None
    assert series[0]["wind_max"] is None


def test_aggregate_weather_monthly_vacio() -> None:
    """Un bloque diario vacio produce una serie vacia."""
    assert aggregate_weather_monthly({}) == []
