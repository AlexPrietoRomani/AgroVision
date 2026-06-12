from __future__ import annotations

import numpy as np

from backend.core.indices import evi, ndre, ndwi, savi


def test_evi_valor_conocido() -> None:
    arr = evi(np.array([0.8]), np.array([0.2]), np.array([0.1]))
    denom = 0.8 + 6.0 * 0.2 - 7.5 * 0.1 + 1.0
    expected = 2.5 * (0.8 - 0.2) / denom
    assert round(float(arr[0]), 4) == round(expected, 4)


def test_evi_division_por_cero() -> None:
    arr = evi(np.array([0.0]), np.array([0.0]), np.array([0.0]))
    denom = 0.0 + 6.0 * 0.0 - 7.5 * 0.0 + 1.0
    expected = 2.5 * 0.0 / denom
    assert float(arr[0]) == expected


def test_savi_valor_conocido() -> None:
    arr = savi(np.array([0.8]), np.array([0.2]))
    expected = (0.8 - 0.2) * 1.5 / (0.8 + 0.2 + 0.5)
    assert round(float(arr[0]), 4) == round(expected, 4)


def test_savi_L_personalizado() -> None:
    arr = savi(np.array([0.8]), np.array([0.2]), L=1.0)
    expected = (0.8 - 0.2) * 2.0 / (0.8 + 0.2 + 1.0)
    assert round(float(arr[0]), 4) == round(expected, 4)


def test_ndwi_valor_conocido() -> None:
    arr = ndwi(np.array([0.8]), np.array([0.3]))
    expected = (0.3 - 0.8) / (0.3 + 0.8)
    assert round(float(arr[0]), 4) == round(expected, 4)


def test_ndwi_agua() -> None:
    arr = ndwi(np.array([0.05]), np.array([0.3]))
    assert float(arr[0]) > 0


def test_ndre_valor_conocido() -> None:
    arr = ndre(np.array([0.8]), np.array([0.3]))
    expected = (0.8 - 0.3) / (0.8 + 0.3)
    assert round(float(arr[0]), 4) == round(expected, 4)


def test_savi_division_por_cero() -> None:
    arr = savi(np.array([0.0]), np.array([0.0]))
    assert float(arr[0]) == 0.0


def test_ndwi_division_por_cero() -> None:
    arr = ndwi(np.array([0.0]), np.array([0.0]))
    assert float(arr[0]) == 0.0


def test_ndre_division_por_cero() -> None:
    arr = ndre(np.array([0.0]), np.array([0.0]))
    assert float(arr[0]) == 0.0
