"""
Archivo: metrics.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Convierte el resultado crudo de la detección (lista de cajas) en los indicadores
agronómicos de negocio: conteo de plantas, densidad por hectárea, número de
malezas, porcentaje de fallas de siembra y confianza media. Se mantiene aislado
de la inferencia para poder probarlo de forma determinista.

Acciones Principales:
    - Calcula las métricas de negocio a partir de una lista de detecciones.

Estructura Interna:
    - `compute_metrics`: agrega las detecciones en métricas de negocio.
    - `_estimate_failures`: heurística de fallas de siembra (placeholder del MVP).

Entradas / Dependencias:
    - `backend.core.detection.Detection`.

Salidas / Efectos:
    - Ninguno; función pura que retorna un diccionario de métricas.

Ejemplo de Integración:
    from backend.core.metrics import compute_metrics
    metricas = compute_metrics(detecciones, area_ha=1.0)
"""

from __future__ import annotations

from backend.core.detection import CLASS_PLANT, CLASS_WEED, Detection

SQUARE_METERS_PER_HECTARE: int = 10_000


def _estimate_failures(plant_count: int) -> float:
    """
    Estima el porcentaje de fallas de siembra (huecos en hilera).

    Nota: en el MVP devuelve 0.0 como marcador. La heurística real (detección de
    huecos en hileras) se incorpora cuando el modelo de conteo esté publicado y se
    disponga de la disposición espacial de las plantas.

    Args:
        plant_count (int): Número de plantas detectadas.

    Returns:
        float: Porcentaje estimado de fallas de siembra en el rango [0, 100].
    """
    return 0.0


def compute_metrics(detections: list[Detection], area_ha: float) -> dict[str, float]:
    """
    Agrega una lista de detecciones en los indicadores agronómicos de negocio.

    Args:
        detections (list[Detection]): Detecciones producidas por el modelo.
        area_ha (float): Área del lote en hectáreas, usada para la densidad.

    Returns:
        dict[str, float]: Diccionario con las claves 'count', 'weeds', 'density',
        'failures' y 'confidence'.
    """
    plant_count = sum(1 for detection in detections if detection.class_id == CLASS_PLANT)
    weed_count = sum(1 for detection in detections if detection.class_id == CLASS_WEED)

    confidences = [detection.confidence for detection in detections]
    mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    density = round(plant_count / area_ha, 1) if area_ha > 0 else 0.0

    return {
        "count": plant_count,
        "weeds": weed_count,
        "density": density,
        "failures": _estimate_failures(plant_count),
        "confidence": mean_confidence,
    }
