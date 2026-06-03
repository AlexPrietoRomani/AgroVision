"""
Archivo: test_sample_generator.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas del generador de ortomosaico de arándano simulado y de su coherencia con
el mock de inferencia (las cajas por color deben caer sobre los arbustos dibujados).

Ejemplo de Integración:
    uv run pytest tests/unit/test_sample_generator.py
"""

from __future__ import annotations

import importlib.util
from types import ModuleType

from backend.core.detection import CLASS_PLANT
from backend.core.inference import MockInferenceAdapter


def _load_generator() -> ModuleType:
    """Carga el script generador (no es un paquete) por ruta de archivo."""
    spec = importlib.util.spec_from_file_location(
        "make_sample_orthomosaic", "scripts/make_sample_orthomosaic.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generador_produce_imagen_y_conteos() -> None:
    """Verifica que el generador devuelva una imagen del tamaño pedido y arbustos > 0."""
    generator = _load_generator()
    image, bushes, _ = generator.generate_orthomosaic(
        width=512, height=384, rows=6, per_row=12, seed=7
    )
    assert image.shape == (384, 512, 3)
    assert bushes > 0


def test_mock_detecta_arbustos_del_ortomosaico() -> None:
    """Verifica que el mock detecte por color una cantidad razonable de arbustos."""
    generator = _load_generator()
    image, _, _ = generator.generate_orthomosaic(seed=7)
    detections = MockInferenceAdapter().predict(image, confidence=0.25)
    plants = [detection for detection in detections if detection.class_id == CLASS_PLANT]
    assert len(plants) >= 8
