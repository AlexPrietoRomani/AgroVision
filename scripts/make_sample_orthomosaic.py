"""
Archivo: make_sample_orthomosaic.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Genera un ortomosaico de arándano **simulado** (datos de prueba) para validar la
demo del MVP: suelo marrón con textura, hileras de arbustos verdes con huecos de
siembra y algunas malezas amarillas. Es determinista por semilla. El mock de
inferencia detecta estos arbustos por color, de modo que las cajas caen sobre
ellos en la UI.

Acciones Principales:
    - Genera y guarda una imagen sintética de campo de arándano.

Estructura Interna:
    - `generate_orthomosaic`: dibuja el campo y retorna imagen + conteos reales.
    - `main`: CLI que escribe la imagen y reporta los conteos.

Entradas / Dependencias:
    - `cv2`, `numpy`.

Salidas / Efectos:
    - Escribe un archivo PNG (por defecto `sample_data/blueberry_demo.png`).

Ejecución:
    python scripts/make_sample_orthomosaic.py [--output sample_data/blueberry_demo.png]

Ejemplo de Uso:
    python scripts/make_sample_orthomosaic.py --width 1024 --height 768 --rows 8 --per-row 16
"""

from __future__ import annotations

import argparse
import random

import cv2
import numpy as np

_SOIL_BGR: tuple[int, int, int] = (50, 80, 120)  # marrón
_TILLED_LINE_BGR: tuple[int, int, int] = (35, 55, 85)  # surco más oscuro
_WEED_BGR: tuple[int, int, int] = (40, 200, 220)  # amarillo
_GAP_PROBABILITY: float = 0.12  # probabilidad de hueco de siembra
_WEED_PROBABILITY: float = 0.06  # probabilidad de maleza junto a un arbusto


def generate_orthomosaic(
    width: int = 1024, height: int = 768, rows: int = 8, per_row: int = 16, seed: int = 42
) -> tuple[np.ndarray, int, int]:
    """
    Genera un ortomosaico de arándano simulado y devuelve los conteos reales.

    Args:
        width (int): Ancho de la imagen en píxeles.
        height (int): Alto de la imagen en píxeles.
        rows (int): Número de hileras de cultivo.
        per_row (int): Posiciones de siembra por hilera.
        seed (int): Semilla para reproducibilidad.

    Returns:
        tuple[np.ndarray, int, int]: Imagen BGR, número de arbustos y número de malezas.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = _SOIL_BGR
    noise = np_rng.integers(-15, 16, size=(height, width, 3), dtype=np.int16)
    image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    row_step = height / (rows + 1)
    col_step = width / (per_row + 1)
    bush_count = 0
    weed_count = 0

    for row_index in range(1, rows + 1):
        row_y = int(row_index * row_step)
        cv2.line(image, (0, row_y), (width, row_y), _TILLED_LINE_BGR, 3)

        for col_index in range(1, per_row + 1):
            if rng.random() < _GAP_PROBABILITY:  # hueco de siembra (falla)
                continue
            center_x = int(col_index * col_step) + rng.randint(-6, 6)
            center_y = row_y + rng.randint(-5, 5)
            radius = rng.randint(12, 18)
            green = rng.randint(120, 180)
            core_radius = max(3, radius // 3)
            core_color = (90, min(230, green + 60), 90)
            cv2.circle(image, (center_x, center_y), radius, (40, green, 40), -1)
            cv2.circle(image, (center_x, center_y), core_radius, core_color, -1)
            bush_count += 1

            if rng.random() < _WEED_PROBABILITY:  # maleza amarilla cercana
                weed_x = center_x + rng.randint(-int(col_step // 2), int(col_step // 2))
                weed_y = center_y + int(row_step // 2)
                cv2.circle(image, (weed_x, weed_y), rng.randint(5, 9), _WEED_BGR, -1)
                weed_count += 1

    return image, bush_count, weed_count


def main() -> None:
    """Genera la imagen según los argumentos de la CLI y reporta los conteos reales."""
    parser = argparse.ArgumentParser(description="Genera un ortomosaico de arándano simulado.")
    parser.add_argument(
        "--output", default="sample_data/blueberry_demo.png", help="Ruta de salida."
    )
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--per-row", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    image, bush_count, weed_count = generate_orthomosaic(
        width=args.width, height=args.height, rows=args.rows, per_row=args.per_row, seed=args.seed
    )
    cv2.imwrite(args.output, image)
    print(f"Imagen escrita en {args.output} | arbustos={bush_count} | malezas={weed_count}")


if __name__ == "__main__":
    main()
