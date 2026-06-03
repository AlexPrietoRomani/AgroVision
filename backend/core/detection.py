"""
Archivo: detection.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Define el tipo de dominio `Detection` y las constantes de clases del modelo de
conteo. Es un módulo puro (sin dependencias pesadas) compartido por la inferencia
y por el cálculo de métricas, evitando importaciones circulares.

Acciones Principales:
    - Provee la estructura inmutable de una detección y el catálogo de clases.

Estructura Interna:
    - `Detection`: dataclass con caja, confianza y clase de una detección.
    - Constantes `CLASS_*` y `CLASS_NAMES`: catálogo de clases del modelo.

Entradas / Dependencias:
    - Solo librería estándar.

Salidas / Efectos:
    - Ninguno; expone tipos y constantes.

Ejemplo de Integración:
    from backend.core.detection import Detection, CLASS_PLANT
    deteccion = Detection(0, 0, 10, 10, 0.9, CLASS_PLANT)
"""

from __future__ import annotations

from dataclasses import dataclass

CLASS_PLANT: int = 0
CLASS_WEED: int = 1
CLASS_NAMES: dict[int, str] = {CLASS_PLANT: "planta", CLASS_WEED: "maleza"}


@dataclass(frozen=True)
class Detection:
    """Detección individual con caja delimitadora, confianza y clase."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
