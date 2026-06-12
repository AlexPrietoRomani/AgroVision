"""
Archivo: test_remote_sensing.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias (sin red) del parseo de la Statistical API de Sentinel Hub y del
rango por defecto de 5 años.

Ejecución:
    uv run python -m pytest tests/unit/test_remote_sensing.py
"""

from __future__ import annotations

import datetime as dt

from backend.services.remote_sensing import _default_range, _parse_stats


def _item(month: str, stats: dict, output_id: str = "ndvi") -> dict:
    """Construye un item de la respuesta Statistical API con las stats dadas."""
    return {
        "interval": {"from": f"{month}-01T00:00:00Z", "to": f"{month}-28T00:00:00Z"},
        "outputs": {output_id: {"bands": {"B0": {"stats": stats}}}},
    }


_SAMPLE = {
    "data": [
        _item("2024-09", {"mean": 0.274, "min": -0.143, "max": 0.923, "sampleCount": 60000}),
        _item("2024-10", {"mean": 0.321, "min": -0.13, "max": 0.928, "sampleCount": 60000}),
        _item("2024-12", {"sampleCount": 0}),  # mes sin píxeles válidos -> se descarta
    ]
}


_SAMPLE_EVI = {
    "data": [
        _item(
            "2024-09",
            {"mean": 0.150, "min": -0.05, "max": 0.650, "sampleCount": 60000},
            output_id="evi",
        ),
        _item(
            "2024-10",
            {"mean": 0.210, "min": -0.03, "max": 0.700, "sampleCount": 60000},
            output_id="evi",
        ),
    ]
}


def test_parse_stats_extrae_y_ordena() -> None:
    """Parsea la serie NDVI, normaliza la fecha al día 1 y descarta meses vacíos."""
    series = _parse_stats(_SAMPLE)
    assert [p["date"] for p in series] == ["2024-09-01", "2024-10-01"]
    assert series[0]["mean_ndvi"] == 0.274
    assert series[0]["min_ndvi"] == -0.143
    assert series[0]["source"] == "sentinel2"


def test_parse_stats_evi() -> None:
    """Parsea la serie EVI con output_id y clave dinámica."""
    series = _parse_stats(_SAMPLE_EVI, output_id="evi", index="evi")
    assert len(series) == 2
    assert series[0]["mean_evi"] == 0.15
    assert series[0]["min_evi"] == -0.05
    assert series[1]["mean_evi"] == 0.21


def test_parse_stats_serie_vacia() -> None:
    """Una respuesta sin datos produce una serie vacía (no error)."""
    assert _parse_stats({"data": []}) == []


def test_default_range_cinco_anios() -> None:
    """El rango por defecto abarca 5 años y termina en formato ISO con Z."""
    start, end = _default_range()
    assert end.endswith("Z") and start.endswith("Z")
    start_year = int(start[:4])
    end_year = int(end[:4])
    assert end_year - start_year == 5
    assert end[:10] == f"{dt.date.today().isoformat()}"
