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

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# Mock de la sesión de base de datos
class MockDbSession:
    """Mock simple de la sesión de base de datos async de SQLAlchemy."""
    
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


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
