from __future__ import annotations

import numpy as np


def evi(nir: np.ndarray, red: np.ndarray, blue: np.ndarray) -> np.ndarray:
    nir = nir.astype(float)
    red = red.astype(float)
    blue = blue.astype(float)
    denom = nir + 6.0 * red - 7.5 * blue + 1.0
    return np.divide(2.5 * (nir - red), denom, out=np.zeros_like(denom), where=denom != 0)


def savi(nir: np.ndarray, red: np.ndarray, L: float = 0.5) -> np.ndarray:
    nir = nir.astype(float)
    red = red.astype(float)
    denom = nir + red + L
    return np.divide((nir - red) * (1.0 + L), denom, out=np.zeros_like(denom), where=denom != 0)


def ndwi(nir: np.ndarray, green: np.ndarray) -> np.ndarray:
    nir = nir.astype(float)
    green = green.astype(float)
    denom = green + nir
    return np.divide(green - nir, denom, out=np.zeros_like(denom), where=denom != 0)


def ndre(nir: np.ndarray, re: np.ndarray) -> np.ndarray:
    nir = nir.astype(float)
    re = re.astype(float)
    denom = nir + re
    return np.divide(nir - re, denom, out=np.zeros_like(denom), where=denom != 0)
