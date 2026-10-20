"""
Archivo: test_profiles.py
Fecha de modificación: 17/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias para el router de perfiles de usuario (/api/profiles)
y los endpoints de conexión y gestión de perfiles (Fase 15).

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_profiles.py
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.main import app


@pytest.fixture(autouse=True)
def override_db_dependency() -> Iterator[None]:
    """Inyecta una sesión mock para que los tests no requieran `DATABASE_URL`."""
    app.dependency_overrides[get_db] = lambda: AsyncMock(spec=AsyncSession)
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client() -> TestClient:
    """Fixture que retorna el cliente de prueba de FastAPI."""
    return TestClient(app)


def test_connect_profile_validation(client: TestClient) -> None:
    """Valida los límites de entrada del endpoint de conexión."""
    # Hash muy corto debe fallar (min_length=16)
    response = client.post("/api/profiles/connect", json={"supabase_url_hash": "short"})
    assert response.status_code == 422

    # Nombre muy largo debe fallar (max_length=100)
    long_name = "a" * 101
    response = client.post(
        "/api/profiles/connect",
        json={"supabase_url_hash": "a" * 32, "display_name": long_name}
    )
    assert response.status_code == 422


def test_update_profile_validation(client: TestClient) -> None:
    """Valida los límites de entrada del endpoint de actualización."""
    # Modo de sesión inválido
    response = client.patch(
        "/api/profiles/some-id",
        json={"session_mode": "invalid_mode"}
    )
    assert response.status_code == 422
