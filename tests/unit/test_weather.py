"""
Archivo: test_weather.py
Fecha de modificación: 16/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de la agregación mensual del clima de Open-Meteo.

Ejecución:
    uv run python -m pytest tests/unit/test_weather.py
"""

from __future__ import annotations

from backend.services.weather import aggregate_weather_monthly

_HOURLY_DATA = [
    {
        "timestamp": "2026-04-01T00:00Z",
        "precipitation": 5.0,
        "temperature_2m": 15.0,
        "shortwave_radiation": 50.0,
        "wind_speed_10m": 10.0,
        "relative_humidity_2m": 60.0,
    },
    {
        "timestamp": "2026-04-01T12:00Z",
        "precipitation": 5.0,
        "temperature_2m": 25.0,
        "shortwave_radiation": 150.0,
        "wind_speed_10m": 20.0,
        "relative_humidity_2m": 40.0,
    },
    {
        "timestamp": "2026-05-01T00:00Z",
        "precipitation": 20.0,
        "temperature_2m": 22.0,
        "shortwave_radiation": 120.0,
        "wind_speed_10m": 15.0,
        "relative_humidity_2m": 80.0,
    },
]


def test_aggregate_weather_monthly_suma_y_promedia() -> None:
    """Precipitacion y radiacion se suman; temperatura y humedad se promedian; viento es maximo."""
    series = aggregate_weather_monthly(_HOURLY_DATA)
    assert [p["date"] for p in series] == ["2026-04-01", "2026-05-01"]
    
    abril = series[0]
    assert abril["precip_mm"] == 10.0  # 5.0 + 5.0
    assert abril["temp_mean_c"] == 20.0  # (15.0 + 25.0) / 2
    assert abril["radiation"] == 200.0  # 50.0 + 150.0
    assert abril["humidity_mean"] == 50.0  # (60.0 + 40.0) / 2
    assert abril["wind_max"] == 20.0  # max(10.0, 20.0)
    
    mayo = series[1]
    assert mayo["precip_mm"] == 20.0
    assert mayo["temp_mean_c"] == 22.0
    assert mayo["radiation"] == 120.0
    assert mayo["humidity_mean"] == 80.0
    assert mayo["wind_max"] == 15.0


def test_aggregate_weather_monthly_sin_datos_algunos_campos() -> None:
    """Si faltan datos, los promedios/sumas devuelven None/0 de manera segura."""
    incomplete_data = [
        {
            "timestamp": "2026-04-01T00:00Z",
            "precipitation": 0.0,
            "temperature_2m": None,
            "shortwave_radiation": None,
            "wind_speed_10m": None,
            "relative_humidity_2m": None,
        }
    ]
    series = aggregate_weather_monthly(incomplete_data)
    assert len(series) == 1
    assert series[0]["precip_mm"] == 0.0
    assert series[0]["temp_mean_c"] is None
    assert series[0]["radiation"] == 0.0
    assert series[0]["humidity_mean"] is None
    assert series[0]["wind_max"] is None


def test_aggregate_weather_monthly_vacio() -> None:
    """Una lista vacia produce una serie vacia."""
    assert aggregate_weather_monthly([]) == []
