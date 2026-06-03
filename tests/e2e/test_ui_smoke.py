"""
Archivo: test_ui_smoke.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Esqueleto de prueba E2E (Playwright) que simula al usuario abriendo la UI Shiny y
verificando el aviso de standby y la efimeralidad de credenciales al refrescar.
Se omite por defecto porque requiere los servicios en ejecución y los navegadores
de Playwright instalados (`uv run playwright install`).

Ejemplo de Integración:
    uv run pytest tests/e2e/test_ui_smoke.py
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="E2E requiere UI/backend en ejecución y navegadores de Playwright instalados."
)


def test_pestana_conteo_muestra_standby() -> None:
    """
    Simula la apertura de la UI y verifica que el módulo de conteo muestre el aviso
    de standby mientras el modelo no esté publicado.

    Pasos previstos (cuando se habilite):
        1. Abrir la app Shiny con Playwright.
        2. Localizar el banner "Módulo en preparación (standby)".
        3. Afirmar que el botón de conteo no produce resultados.
    """
    raise NotImplementedError("Pendiente: habilitar cuando el modelo esté publicado.")


def test_credenciales_se_borran_al_refrescar() -> None:
    """
    Simula ingresar una credencial, refrescar la página y verificar que el campo
    quede vacío (efimeralidad por sesión).
    """
    raise NotImplementedError("Pendiente: implementar con Playwright.")
