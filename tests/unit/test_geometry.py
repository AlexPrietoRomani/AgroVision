"""
Archivo: test_geometry.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de las funciones geométricas puras (Fase 1): distancia de muestreo
terrestre (GSD), densidad por hectárea y área geodésica de un polígono lon/lat.

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_geometry.py
"""

from __future__ import annotations

from backend.core.geometry import density_per_ha, geodesic_area_m2, gsd_cm_per_px


def test_gsd_valor_conocido() -> None:
    """GSD = (sensor*altura)/(focal*ancho)*100; caso redondo -> 10 cm/px."""
    g = gsd_cm_per_px(sensor_w_mm=10, flight_h_m=100, focal_mm=10, img_w_px=1000)
    assert g == 10.0


def test_density_per_ha_una_hectarea() -> None:
    """100 plantas en 10.000 m² (1 ha) -> 100 pl/Ha."""
    assert density_per_ha(100, 10_000) == 100.0


def test_density_per_ha_area_cero() -> None:
    """Área cero no debe dividir por cero; devuelve 0.0."""
    assert density_per_ha(5, 0) == 0.0


def test_geodesic_area_caja_un_grado_cerca_ecuador() -> None:
    """Una caja de 1°x1° cerca del ecuador mide ~1.23e10 m² (≈12.300 km²)."""
    box = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    area = geodesic_area_m2(box)
    assert 1.1e10 < area < 1.4e10


def test_geodesic_area_independiente_del_sentido() -> None:
    """El área no depende del sentido de giro del polígono (se toma valor absoluto)."""
    horario = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    antihorario = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    assert round(geodesic_area_m2(horario), 2) == round(geodesic_area_m2(antihorario), 2)
