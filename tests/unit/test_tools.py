"""
Archivo: test_tools.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de las herramientas del agente: el esquema de function calling y el
formateo puro de la tendencia NDVI.

Ejecución:
    uv run python -m pytest tests/unit/test_tools.py
"""

from __future__ import annotations

from backend.services.tools import TOOLS_SCHEMA, _describe_trend, _in_range


def test_tools_schema_define_tres_herramientas() -> None:
    """El esquema declara las 3 herramientas con `field_name` requerido."""
    names = {t["function"]["name"] for t in TOOLS_SCHEMA}
    assert names == {
        "get_vegetation_index_trend",
        "get_weather_context",
        "get_field_planting_density",
    }
    for tool in TOOLS_SCHEMA:
        assert "field_name" in tool["function"]["parameters"]["required"]


def test_describe_trend_descenso() -> None:
    """Una serie que baja se describe como 'descenso' con el delta correcto."""
    series = [
        {"date": "2026-01-01", "mean_value": 0.80},
        {"date": "2026-03-01", "mean_value": 0.70},
    ]
    out = _describe_trend("Lote A", series)
    assert "descenso" in out
    assert "Lote A" in out
    assert "-0.10" in out


def test_describe_trend_estable() -> None:
    """Un cambio menor a 0.02 se considera 'estable'."""
    series = [
        {"date": "2026-01-01", "mean_value": 0.70},
        {"date": "2026-03-01", "mean_value": 0.71},
    ]
    assert "estable" in _describe_trend("Lote A", series)


def test_describe_trend_insuficiente() -> None:
    """Con menos de 2 observaciones se reporta datos insuficientes."""
    assert "insuficientes" in _describe_trend("Lote A", [{"date": "2026-01-01", "mean_value": 0.7}])


def test_in_range() -> None:
    """El filtro de rango respeta los límites ISO."""
    assert _in_range("2026-03-01", "2026-01-01", "2026-12-31")
    assert not _in_range("2025-12-01", "2026-01-01", None)
    assert _in_range("2026-03-01", None, None)
