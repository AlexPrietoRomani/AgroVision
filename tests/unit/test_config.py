"""
Archivo: test_config.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de la configuración del backend: parseo de booleanos y valores
por defecto del entorno.

Ejemplo de Integración:
    uv run pytest tests/unit/test_config.py
"""

from __future__ import annotations

import pytest

from backend.config import _parse_bool, get_settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("YES", True), ("on", True), ("0", False), ("no", False)],
)
def test_parse_bool_reconoce_valores(raw: str, expected: bool) -> None:
    """Verifica el reconocimiento de valores verdaderos y falsos."""
    assert _parse_bool(raw) is expected


def test_parse_bool_usa_default_si_none() -> None:
    """Verifica que se use el valor por defecto cuando la variable es None."""
    assert _parse_bool(None, default=True) is True
    assert _parse_bool(None) is False


def test_get_settings_standby_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que el conteo arranque en standby cuando no se define la variable."""
    monkeypatch.delenv("COUNTING_ENABLED", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.counting_enabled is False
    assert settings.model_version
    get_settings.cache_clear()
