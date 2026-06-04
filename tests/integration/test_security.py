"""
Archivo: test_security.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas del *hardening* del gateway: cabeceras de seguridad en las respuestas y el
rate limiting de `/api` (429 al exceder el cupo). Recrea la app con un límite bajo.

Ejecución:
    uv run python -m pytest tests/integration/test_security.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import get_settings


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COUNTING_ENABLED", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cabeceras_de_seguridad_presentes() -> None:
    """Toda respuesta incluye las cabeceras de hardening."""
    from backend.main import create_app

    with TestClient(create_app()) as client:
        r = client.get("/api/status")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Referrer-Policy" in r.headers


def test_rate_limit_devuelve_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """Al exceder el cupo de /api, el gateway responde 429 con Retry-After."""
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    get_settings.cache_clear()
    from backend.main import create_app

    with TestClient(create_app()) as client:
        codes = [client.get("/api/status").status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_rate_limit_desactivado_no_bloquea(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con RATE_LIMIT_PER_MIN=0 no se aplica límite."""
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")
    get_settings.cache_clear()
    from backend.main import create_app

    with TestClient(create_app()) as client:
        codes = [client.get("/api/status").status_code for _ in range(10)]
    assert all(c == 200 for c in codes)
