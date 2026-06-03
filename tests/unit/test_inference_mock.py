"""
Archivo: test_inference_mock.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias del adaptador de inferencia simulado (mock): genera detecciones
falsas dentro de los límites de la imagen, deterministas por imagen, y la fábrica
devuelve la implementación correcta.

Ejemplo de Integración:
    uv run pytest tests/unit/test_inference_mock.py
"""

from __future__ import annotations

import numpy as np

from backend.core.detection import CLASS_PLANT, CLASS_WEED
from backend.core.inference import MockInferenceAdapter, create_adapter


def test_mock_genera_detecciones_dentro_de_imagen() -> None:
    """Verifica que el mock produzca detecciones válidas dentro de la imagen."""
    image = np.full((480, 640, 3), 120, dtype=np.uint8)
    detections = MockInferenceAdapter().predict(image, confidence=0.25)

    assert len(detections) > 0
    for detection in detections:
        assert detection.class_id in {CLASS_PLANT, CLASS_WEED}
        assert 0.25 <= detection.confidence <= 1.0
        assert 0 <= detection.x1 < detection.x2 <= 640
        assert 0 <= detection.y1 < detection.y2 <= 480


def test_mock_es_determinista_por_imagen() -> None:
    """Verifica que la misma imagen produzca el mismo número de detecciones."""
    image = np.full((300, 300, 3), 80, dtype=np.uint8)
    first = MockInferenceAdapter().predict(image, confidence=0.25)
    second = MockInferenceAdapter().predict(image, confidence=0.25)
    assert len(first) == len(second)


def test_create_adapter_devuelve_mock() -> None:
    """Verifica que la fábrica devuelva el adaptador mock para el backend 'mock'."""
    adapter = create_adapter("mock", model_path="", architecture="yolo26n")
    assert isinstance(adapter, MockInferenceAdapter)
