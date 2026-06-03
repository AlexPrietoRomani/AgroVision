"""
Archivo: test_deps.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias del proxy efímero de credenciales: la cabecera tiene prioridad y, si
falta, se hace fallback al entorno DEV (desarrollo local).

Ejecución:
    uv run python -m pytest tests/unit/test_deps.py
"""

from __future__ import annotations

import pytest

from backend.api.deps import get_user_keys


def test_get_user_keys_fallback_a_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin cabecera, las llaves se toman de las variables DEV_* del entorno."""
    monkeypatch.setenv("DEV_COPERNICUS_CLIENT_ID", "env-id")
    monkeypatch.setenv("DEV_COPERNICUS_CLIENT_SECRET", "env-secret")
    monkeypatch.setenv("DEV_GROQ_API_KEY", "env-groq")
    keys = get_user_keys(
        x_user_groq_key=None,
        x_user_copernicus_id=None,
        x_user_copernicus_secret=None,
        x_user_supabase_url=None,
        x_user_supabase_key=None,
    )
    assert keys.copernicus_id == "env-id"
    assert keys.copernicus_secret == "env-secret"
    assert keys.groq == "env-groq"


def test_get_user_keys_cabecera_tiene_prioridad(monkeypatch: pytest.MonkeyPatch) -> None:
    """La cabecera X-User-* gana sobre el entorno DEV."""
    monkeypatch.setenv("DEV_COPERNICUS_CLIENT_ID", "env-id")
    keys = get_user_keys(
        x_user_groq_key=None,
        x_user_copernicus_id="hdr-id",
        x_user_copernicus_secret=None,
        x_user_supabase_url=None,
        x_user_supabase_key=None,
    )
    assert keys.copernicus_id == "hdr-id"
