"""
Archivo: geometry.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Funciones geométricas **puras** (Fase 1): distancia de muestreo terrestre (GSD) que
relaciona la resolución con la geometría de vuelo del dron, densidad de siembra por
hectárea y área geodésica de un polígono lon/lat. El área geodésica sirve de respaldo
cuando no hay PostGIS disponible (en producción se usa `ST_Area(geom::geography)`).

Acciones Principales:
    - Calcula GSD, densidad por hectárea y área geodésica.

Estructura Interna:
    - `gsd_cm_per_px`: cm/píxel a partir de sensor/altura/focal/ancho.
    - `density_per_ha`: plantas por hectárea a partir de conteo y área.
    - `geodesic_area_m2`: área (m²) de un anillo [lon, lat] sobre la esfera.

Entradas / Dependencias:
    - `math` (biblioteca estándar).

Salidas / Efectos:
    - Ninguno; funciones puras.

Ejemplo de Integración:
    from backend.core.geometry import gsd_cm_per_px, density_per_ha, geodesic_area_m2
"""

from __future__ import annotations

import math

_EARTH_RADIUS_M: float = 6_378_137.0  # radio ecuatorial WGS84
SQUARE_METERS_PER_HECTARE: int = 10_000


def gsd_cm_per_px(
    sensor_w_mm: float, flight_h_m: float, focal_mm: float, img_w_px: float
) -> float:
    """
    Calcula la distancia de muestreo terrestre (GSD) en centímetros por píxel.

    Args:
        sensor_w_mm (float): Ancho del sensor en milímetros.
        flight_h_m (float): Altura de vuelo en metros.
        focal_mm (float): Distancia focal en milímetros.
        img_w_px (float): Ancho de la imagen en píxeles.

    Returns:
        float: GSD en cm/px; 0.0 si focal o ancho son 0.
    """
    denom = focal_mm * img_w_px
    if denom == 0:
        return 0.0
    return (sensor_w_mm * flight_h_m) / denom * 100


def density_per_ha(count: int, area_m2: float) -> float:
    """
    Calcula la densidad de plantas por hectárea.

    Args:
        count (int): Número de plantas detectadas.
        area_m2 (float): Área de la parcela en metros cuadrados.

    Returns:
        float: Plantas por hectárea; 0.0 si el área es 0.
    """
    if area_m2 <= 0:
        return 0.0
    return count / (area_m2 / SQUARE_METERS_PER_HECTARE)


def geodesic_area_m2(coords: list[list[float]]) -> float:
    """
    Calcula el área geodésica (m²) de un anillo de coordenadas [lon, lat].

    Usa la fórmula estándar de área de un polígono sobre la esfera (la misma de la
    librería de geometría de Google Maps). El resultado es el valor absoluto, por lo
    que no depende del sentido de giro.

    Args:
        coords (list[list[float]]): Vértices [lon, lat] en grados (anillo cerrado o no).

    Returns:
        float: Área en metros cuadrados (>= 0).
    """
    if len(coords) < 3:
        return 0.0
    total = 0.0
    n = len(coords)
    for i in range(n):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[(i + 1) % n]
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * _EARTH_RADIUS_M * _EARTH_RADIUS_M / 2.0)
