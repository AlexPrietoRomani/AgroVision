"""
Archivo: test_ui_smoke.py
Fecha de modificación: 28/10/2026
Autor: Alex Prieto Romani <alexprieto1997@gmail.com>

Descripción:
Pruebas de humo de la UI. Las pruebas estáticas verifican que el build de Astro
incluya los controles de selección y expansión de variables satelitales; las pruebas
dinámicas (Playwright) quedan pendientes de habilitarse con la UI y el backend en
ejecución.

Ejemplo de Integración:
    ./scripts/build.sh && uv run pytest tests/e2e/test_ui_smoke.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC_INDEX = Path(__file__).resolve().parents[2] / "backend" / "static" / "index.html"
PLAYWRIGHT_SKIP_REASON = (
    "E2E requiere UI/backend en ejecución y navegadores de Playwright instalados."
)
VALID_INDICES = ("ndvi", "evi", "savi", "ndwi", "ndre")


def _static_html() -> str:
    """
    Lee el HTML compilado de la UI.

    Returns:
        str: Contenido de `backend/static/index.html`.

    Raises:
        AssertionError: Si el build estático no existe.
    """
    assert STATIC_INDEX.exists(), (
        f"No existe {STATIC_INDEX}. Ejecuta ./scripts/build.sh antes de correr "
        "las pruebas de humo."
    )
    return STATIC_INDEX.read_text(encoding="utf-8")


def _class_count(html: str, class_name: str) -> int:
    """
    Cuenta los elementos cuyo atributo class incluye la clase indicada.

    Args:
        html (str): Documento HTML compilado.
        class_name (str): Clase CSS a contar.

    Returns:
        int: Número de elementos que declaran esa clase.
    """
    pattern = rf'class="[^"]*\b{re.escape(class_name)}\b[^"]*"'
    return len(re.findall(pattern, html))


def test_creator_includes_satellite_variable_selector() -> None:
    """Verifica el selector de variables en el asistente de creación de parcelas."""
    html = _static_html()
    assert 'id="creator-indices-group"' in html
    assert 'id="btn-creator-select-all-indices"' in html
    assert 'id="btn-creator-select-recommended-indices"' in html
    assert _class_count(html, "creator-index-checkbox") == 5
    for index in VALID_INDICES:
        assert f'value="{index}"' in html


def test_existing_parcel_includes_satellite_variable_expansion() -> None:
    """Verifica los controles de expansión en ajustes, teledetección y reproceso."""
    html = _static_html()
    assert 'id="attr-satellite-indices"' in html
    assert _class_count(html, "attr-index-checkbox") == 5
    assert 'id="parcel-active-indices"' in html
    assert 'id="btn-add-satellite-var"' in html
    assert _class_count(html, "reprocess-index-checkbox") == 5
    assert 'id="cred-db-url"' in html
    assert 'id="cfg-db-url"' in html


@pytest.mark.skip(reason=PLAYWRIGHT_SKIP_REASON)
def test_pestana_conteo_muestra_standby() -> None:
    """
    Simula la apertura de la UI y verifica que el módulo de conteo muestre el aviso
    de standby mientras el modelo no esté publicado.

    Pasos previstos (cuando se habilite):
        1. Abrir la app con Playwright.
        2. Localizar el banner "Módulo en preparación (standby)".
        3. Afirmar que el botón de conteo no produce resultados.
    """
    raise NotImplementedError("Pendiente: habilitar cuando el modelo esté publicado.")


@pytest.mark.skip(reason=PLAYWRIGHT_SKIP_REASON)
def test_credenciales_se_borran_al_refrescar() -> None:
    """
    Simula ingresar una credencial, refrescar la página y verificar que el campo
    quede vacío (efimeralidad por sesión).
    """
    raise NotImplementedError("Pendiente: implementar con Playwright.")
