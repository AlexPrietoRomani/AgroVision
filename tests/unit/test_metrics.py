"""
Archivo: test_metrics.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias del cálculo de métricas de negocio a partir de detecciones.

Ejemplo de Integración:
    uv run pytest tests/unit/test_metrics.py
"""

from __future__ import annotations

from backend.core.detection import CLASS_PLANT, CLASS_WEED, Detection
from backend.core.metrics import compute_metrics


def test_compute_metrics_cuenta_y_densidad() -> None:
    """Verifica el conteo por clase, la densidad y la confianza media."""
    detections = [
        Detection(0, 0, 1, 1, 0.9, CLASS_PLANT),
        Detection(0, 0, 1, 1, 0.8, CLASS_PLANT),
        Detection(0, 0, 1, 1, 0.7, CLASS_WEED),
    ]
    metrics = compute_metrics(detections, area_ha=2.0)
    assert metrics["count"] == 2
    assert metrics["weeds"] == 1
    assert metrics["density"] == 1.0  # 2 plantas / 2 Ha
    assert metrics["confidence"] == round((0.9 + 0.8 + 0.7) / 3, 2)


def test_compute_metrics_lista_vacia() -> None:
    """Verifica el comportamiento con cero detecciones (sin división por cero)."""
    metrics = compute_metrics([], area_ha=1.0)
    assert metrics["count"] == 0
    assert metrics["density"] == 0.0
    assert metrics["confidence"] == 0.0
