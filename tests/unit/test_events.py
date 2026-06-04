"""
Archivo: test_events.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias de la telemetría de UI (Fase 9): redacción de secretos, tope del
ring buffer en memoria y los endpoints `POST /api/events` y `GET /api/events/recent`
(incluyendo el filtrado por `session_id`). No tocan la BD (la persistencia opcional
SF9.3 está desactivada por defecto).

Ejecución:
    uv run python -m pytest tests/unit/test_events.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import events
from backend.main import app


@pytest.fixture(autouse=True)
def _clear_buffer() -> None:
    """Vacía el ring buffer antes y después de cada prueba (estado global)."""
    events._BUFFER.clear()
    yield
    events._BUFFER.clear()


def test_redact_oculta_claves_sensibles() -> None:
    """`_redact` reemplaza por '***' cualquier clave que parezca un secreto."""
    redacted = events._redact(
        {"groq_key": "gsk_abc", "token": "t", "tab": "teledeteccion", "count": 3}
    )
    assert redacted["groq_key"] == "***"
    assert redacted["token"] == "***"
    # Las claves no sensibles se conservan tal cual.
    assert redacted["tab"] == "teledeteccion"
    assert redacted["count"] == 3


def test_ring_buffer_acotado() -> None:
    """El buffer nunca crece por encima de `MAX_EVENTS`."""
    assert events._BUFFER.maxlen == events.MAX_EVENTS
    for i in range(events.MAX_EVENTS + 50):
        events._BUFFER.append({"action": "nav", "i": i})
    assert len(events._BUFFER) == events.MAX_EVENTS


def test_ingest_redacta_y_almacena() -> None:
    """`POST /api/events` valida, redacta los secretos del `meta` y guarda en el buffer."""
    with TestClient(app) as client:
        response = client.post(
            "/api/events",
            json={
                "action": "creds_set",
                "session_id": "sess-1",
                "meta": {"groq_key": "gsk_secreto", "count": 1},
            },
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    stored = list(events._BUFFER)
    assert len(stored) == 1
    assert stored[0]["action"] == "creds_set"
    assert stored[0]["meta"]["groq_key"] == "***"  # nunca el valor real
    assert stored[0]["meta"]["count"] == 1


def test_recent_devuelve_eventos_con_limite() -> None:
    """`GET /api/events/recent` devuelve los últimos eventos respetando `limit`."""
    with TestClient(app) as client:
        for i in range(5):
            client.post(
                "/api/events",
                json={"action": "nav", "session_id": "sess-1", "meta": {"i": i}},
            )
        response = client.get("/api/events/recent", params={"limit": 3})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert [e["meta"]["i"] for e in body] == [2, 3, 4]  # los 3 más recientes, en orden


def test_recent_filtra_por_session_id() -> None:
    """`GET /api/events/recent?session_id=` aísla la traza de una sola sesión."""
    with TestClient(app) as client:
        client.post("/api/events", json={"action": "nav", "session_id": "A", "meta": {}})
        client.post("/api/events", json={"action": "nav", "session_id": "B", "meta": {}})
        client.post("/api/events", json={"action": "chat", "session_id": "A", "meta": {}})
        response = client.get("/api/events/recent", params={"session_id": "A"})
    body = response.json()
    assert len(body) == 2
    assert {e["session_id"] for e in body} == {"A"}
