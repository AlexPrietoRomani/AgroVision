"""
Archivo: test_ndvi.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias del motor NDVI puro (Fase 1): cálculo vectorizado, evitación de
división por cero, estadística zonal y agregación mensual (1 punto/mes, menor nube).

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_ndvi.py
"""

from __future__ import annotations

import numpy as np

from backend.core.ndvi import aggregate_monthly, ndvi, zonal_stats


def test_ndvi_valor_conocido() -> None:
    """NDVI(0.8, 0.2) = (0.8-0.2)/(0.8+0.2) = 0.6."""
    arr = ndvi(np.array([0.8]), np.array([0.2]))
    assert round(float(arr[0]), 4) == 0.6


def test_ndvi_evita_division_por_cero() -> None:
    """Cuando NIR+Red = 0, el NDVI debe ser 0.0 (sin error)."""
    arr = ndvi(np.array([0.0]), np.array([0.0]))
    assert float(arr[0]) == 0.0


def test_zonal_stats_mean_min_max() -> None:
    """La estadística zonal devuelve media, mínimo y máximo sobre la máscara."""
    arr = np.array([0.2, 0.4, 0.6])
    mask = np.array([True, True, True])
    stats = zonal_stats(arr, mask)
    assert stats["min_ndvi"] == 0.2
    assert stats["max_ndvi"] == 0.6
    assert round(stats["mean_ndvi"], 2) == 0.4


def test_aggregate_monthly_elige_menor_nube_por_mes() -> None:
    """Por cada mes se conserva la escena de menor nubosidad; la fecha se normaliza al día 1."""
    series = [
        {"date": "2026-04-03", "mean_ndvi": 0.70, "cloud_cover": 40},
        {"date": "2026-04-20", "mean_ndvi": 0.80, "cloud_cover": 5},  # mejor de abril
        {"date": "2026-05-10", "mean_ndvi": 0.60, "cloud_cover": 10},
    ]
    out = aggregate_monthly(series)
    assert len(out) == 2
    abril = next(p for p in out if p["date"] == "2026-04-01")
    assert abril["mean_ndvi"] == 0.80
    assert abril["cloud_cover"] == 5


def test_aggregate_monthly_ordena_cronologicamente() -> None:
    """La salida queda ordenada por fecha ascendente."""
    series = [
        {"date": "2026-05-10", "mean_ndvi": 0.6, "cloud_cover": 10},
        {"date": "2026-04-20", "mean_ndvi": 0.8, "cloud_cover": 5},
    ]
    out = aggregate_monthly(series)
    assert [p["date"] for p in out] == ["2026-04-01", "2026-05-01"]
