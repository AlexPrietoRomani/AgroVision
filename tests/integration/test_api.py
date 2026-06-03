"""
Archivo: test_api.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas de integración HTTP del backend con `TestClient`. Verifican el
healthcheck y que el endpoint de conteo respete el modo standby (503) cuando el
modelo no está habilitado.

Ejemplo de Integración:
    uv run pytest tests/integration/test_api.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garantiza el modo standby por defecto limpiando la caché de configuración."""
    monkeypatch.delenv("COUNTING_ENABLED", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_status_reporta_standby() -> None:
    """Verifica que `/api/status` reporte el conteo en standby por defecto."""
    with TestClient(app) as client:
        response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "agrovision-plantcount"
    assert body["counting_enabled"] is False


def test_count_en_standby_devuelve_503() -> None:
    """Verifica que `/api/count` devuelva 503 mientras el conteo esté en standby."""
    fake_image = b"no-importa-en-standby"
    with TestClient(app) as client:
        response = client.post(
            "/api/count",
            files={"file": ("orto.png", fake_image, "image/png")},
            data={"area_ha": "1.0"},
        )
    assert response.status_code == 503
