"""
Archivo: test_domain_schemas.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de los esquemas de dominio de la plataforma (Fase 1): validación
de geometría de parcelas (polígono cerrado EPSG:4326), rango de NDVI y rol del chat.

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_domain_schemas.py
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.core.schemas import ChatMessage, FieldIn, NDVIPoint, WeatherPoint

_CLOSED_SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[-58.0, -34.0], [-58.0, -34.1], [-57.9, -34.1], [-57.9, -34.0], [-58.0, -34.0]]
    ],
}


def test_field_in_acepta_poligono_cerrado() -> None:
    """Un polígono con anillo cerrado y >=4 vértices se acepta."""
    field = FieldIn(name="Lote A", geojson=_CLOSED_SQUARE)
    assert field.name == "Lote A"


def test_field_in_rechaza_poligono_abierto() -> None:
    """Un anillo cuyo primer punto != último debe rechazarse."""
    abierto = {
        "type": "Polygon",
        "coordinates": [[[-58.0, -34.0], [-58.0, -34.1], [-57.9, -34.1]]],
    }
    with pytest.raises(ValidationError):
        FieldIn(name="x", geojson=abierto)


def test_field_in_rechaza_tipo_no_poligono() -> None:
    """Una geometría que no es Polygon debe rechazarse."""
    punto = {"type": "Point", "coordinates": [-58.0, -34.0]}
    with pytest.raises(ValidationError):
        FieldIn(name="x", geojson=punto)


def test_ndvi_point_acepta_rango_valido() -> None:
    """Un NDVI dentro de [-1, 1] y nubosidad dentro de [0, 100] se acepta."""
    punto = NDVIPoint(date="2026-04-01", mean_ndvi=0.72, cloud_cover=4.1)
    assert punto.mean_ndvi == 0.72


def test_ndvi_point_rechaza_fuera_de_rango() -> None:
    """Un NDVI fuera de [-1, 1] dispara ValidationError."""
    with pytest.raises(ValidationError):
        NDVIPoint(date="2026-04-01", mean_ndvi=1.5)


def test_weather_point_acepta_nulos() -> None:
    """Las variables climáticas son opcionales (pueden faltar en una fecha)."""
    punto = WeatherPoint(date="2026-04-01")
    assert punto.precip_mm is None


def test_chat_message_rechaza_rol_invalido() -> None:
    """Solo se permiten los roles 'user' y 'assistant'."""
    with pytest.raises(ValidationError):
        ChatMessage(role="system", content="x", session_id="s1")
