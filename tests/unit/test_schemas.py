"""
Archivo: test_schemas.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de los contratos Pydantic: aceptación de payloads válidos y
rechazo de valores fuera de rango (confianza, conteo negativo).

Ejemplo de Integración:
    uv run pytest tests/unit/test_schemas.py
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas import CountResponse, StatusResponse


def test_count_response_valido() -> None:
    """Verifica que un payload de conteo válido se instancie correctamente."""
    respuesta = CountResponse(
        count=124, density=72400.0, weeds=12, failures=1.2, confidence=0.91, overlay_b64="abc"
    )
    assert respuesta.count == 124


def test_count_response_confianza_invalida() -> None:
    """Verifica que una confianza fuera de [0, 1] dispare ValidationError."""
    with pytest.raises(ValidationError):
        CountResponse(count=1, density=1.0, weeds=0, failures=0.0, confidence=1.5, overlay_b64="x")


def test_count_response_conteo_negativo() -> None:
    """Verifica que un conteo negativo dispare ValidationError."""
    with pytest.raises(ValidationError):
        CountResponse(count=-1, density=0.0, weeds=0, failures=0.0, confidence=0.5, overlay_b64="x")


def test_status_response_defaults() -> None:
    """Verifica los valores por defecto del healthcheck."""
    estado = StatusResponse(model="agrovision-plantcount", version="2.0.0", counting_enabled=False)
    assert estado.status == "ok"
    assert estado.counting_enabled is False
