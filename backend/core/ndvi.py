"""
Archivo: ndvi.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Motor NDVI **puro** (Fase 1), aislado de toda I/O para poder probar la matemática
con arrays sintéticos. Incluye el cálculo vectorizado del índice, la estadística
zonal (media/mín/máx sobre una máscara) y la agregación temporal **mensual** (un
punto por mes, la escena de menor nubosidad), usada por el flujo de 5 años.

Acciones Principales:
    - Calcula NDVI por píxel, agrega estadística zonal y resume por mes.

Estructura Interna:
    - `ndvi`: índice normalizado de vegetación, vectorizado y seguro ante /0.
    - `zonal_stats`: media/mín/máx sobre los píxeles de la máscara.
    - `aggregate_monthly`: reduce una serie a 1 punto/mes (menor `cloud_cover`).

Entradas / Dependencias:
    - `numpy`.

Salidas / Efectos:
    - Ninguno; funciones puras.

Ejemplo de Integración:
    from backend.core.ndvi import ndvi, zonal_stats, aggregate_monthly
"""

from __future__ import annotations

import numpy as np


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """
    Calcula el NDVI vectorizado evitando la división por cero.

    Args:
        nir (np.ndarray): Reflectancia en el infrarrojo cercano (Banda 8).
        red (np.ndarray): Reflectancia en el rojo visible (Banda 4).

    Returns:
        np.ndarray: NDVI por píxel; 0.0 donde NIR+Red == 0.
    """
    nir = nir.astype(float)
    red = red.astype(float)
    denom = nir + red
    # `where` evita la división por cero sin emitir RuntimeWarning (np.where evaluaría
    # ambas ramas y dispararía el aviso); las posiciones con denom == 0 quedan en 0.0.
    return np.divide(nir - red, denom, out=np.zeros_like(denom), where=denom != 0)


def zonal_stats(ndvi_arr: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    """
    Calcula la estadística zonal (media/mín/máx) sobre los píxeles de la máscara.

    Args:
        ndvi_arr (np.ndarray): Array de NDVI por píxel.
        mask (np.ndarray): Máscara booleana de los píxeles dentro de la parcela.

    Returns:
        dict[str, float]: Claves 'mean_ndvi', 'min_ndvi', 'max_ndvi'.
    """
    values = ndvi_arr[mask]
    return {
        "mean_ndvi": float(values.mean()),
        "min_ndvi": float(values.min()),
        "max_ndvi": float(values.max()),
    }


def aggregate_monthly(series: list[dict]) -> list[dict]:
    """
    Reduce una serie de observaciones a un punto por mes (la de menor nubosidad).

    La fecha de cada punto resultante se normaliza al primer día del mes
    (`AAAA-MM-01`) para coincidir con el `UNIQUE(field_id, date)` del esquema.

    Args:
        series (list[dict]): Observaciones con claves 'date' (ISO) y 'cloud_cover'.

    Returns:
        list[dict]: Observaciones mensuales ordenadas cronológicamente.
    """
    best_per_month: dict[str, dict] = {}
    for point in series:
        month_key = str(point["date"])[:7]  # 'AAAA-MM'
        cloud = point.get("cloud_cover")
        current = best_per_month.get(month_key)
        cloud_value = cloud if cloud is not None else float("inf")
        current_cloud = (
            current.get("cloud_cover")
            if current and current.get("cloud_cover") is not None
            else float("inf")
        )
        if current is None or cloud_value < current_cloud:
            best_per_month[month_key] = {**point, "date": f"{month_key}-01"}
    return [best_per_month[key] for key in sorted(best_per_month)]
