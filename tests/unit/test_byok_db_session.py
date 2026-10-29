"""
Archivo: test_byok_db_session.py
Descripción: Pruebas unitarias de la sesión multi-DSN BYOK dinámica y auto-migración.
Ejecución: uv run python -m pytest tests/unit/test_byok_db_session.py -q
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.db.session import (
    _INITIALIZED_DSNS,
    _is_valid_dsn,
    ensure_schema_initialized,
    get_engine,
    get_sessionmaker,
)


class TestIsValidDSN:
    def test_valid_dsn(self) -> None:
        assert _is_valid_dsn("postgresql+asyncpg://user:pass@host:5432/db") is True

    def test_valid_dsn_no_password(self) -> None:
        assert _is_valid_dsn("postgresql://user@host/db") is True

    def test_placeholder_pwd(self) -> None:
        assert _is_valid_dsn("<pwd>@<host>") is False

    def test_placeholder_host(self) -> None:
        assert _is_valid_dsn("postgresql+asyncpg://<pwd>@<host>") is False

    def test_none(self) -> None:
        assert _is_valid_dsn(None) is False

    def test_empty(self) -> None:
        assert _is_valid_dsn("") is False


class TestGetEngineSessionmakerDSN:
    def test_get_engine_cached_by_dsn(self) -> None:
        engine1 = get_engine(dsn="postgresql+asyncpg://user1:pass1@host1/db1")
        engine2 = get_engine(dsn="postgresql+asyncpg://user1:pass1@host1/db1")
        assert engine1 is engine2

    def test_get_engine_different_dsns(self) -> None:
        engine1 = get_engine(dsn="postgresql+asyncpg://user1:pass1@host1/db1")
        engine2 = get_engine(dsn="postgresql+asyncpg://user2:pass2@host2/db2")
        assert engine1 is not engine2

    def test_get_sessionmaker_cached_by_dsn(self) -> None:
        maker1 = get_sessionmaker(dsn="postgresql+asyncpg://user1:pass1@host1/db1")
        maker2 = get_sessionmaker(dsn="postgresql+asyncpg://user1:pass1@host1/db1")
        assert maker1 is maker2

    def test_get_sessionmaker_different_dsns(self) -> None:
        maker1 = get_sessionmaker(dsn="postgresql+asyncpg://user1:pass1@host1/db1")
        maker2 = get_sessionmaker(dsn="postgresql+asyncpg://user2:pass2@host2/db2")
        assert maker1 is not maker2


class TestEnsureSchemaInitialized:
    @pytest.mark.asyncio
    async def test_first_initialization_with_mock(self) -> None:
        _INITIALIZED_DSNS.clear()
        with patch("backend.db.session.apply_migrations") as mock_apply:
            mock_apply.return_value = ["0001_initial_schema.sql", "0002_field_selected_indices.sql"]
            result = await ensure_schema_initialized(
                "postgresql+asyncpg://user1:pass1@host1/db1"
            )
            assert result == ["0001_initial_schema.sql", "0002_field_selected_indices.sql"]
            assert len(_INITIALIZED_DSNS) == 1
            mock_apply.assert_awaited_once_with("postgresql+asyncpg://user1:pass1@host1/db1")

    @pytest.mark.asyncio
    async def test_idempotent_subsequent_call(self) -> None:
        _INITIALIZED_DSNS.clear()
        with patch("backend.db.session.apply_migrations") as mock_apply:
            # Primera llamada - retorna aplicaciones
            mock_apply.return_value = ["0001_initial_schema.sql"]
            _ = await ensure_schema_initialized(
                "postgresql+asyncpg://user1:pass1@host1/db1"
            )
            assert mock_apply.await_count == 1

            # Segunda llamada con mismo DSN - debería usar caché
            _ = await ensure_schema_initialized(
                "postgresql+asyncpg://user1:pass1@host1/db1"
            )
            assert mock_apply.await_count == 1

    @pytest.mark.asyncio
    async def test_different_dsns_independent(self) -> None:
        _INITIALIZED_DSNS.clear()
        with patch("backend.db.session.apply_migrations") as mock_apply:
            mock_apply.side_effect = lambda dsn: [f"migración_{dsn.split('//')[-1]}"]

            _ = await ensure_schema_initialized(
                "postgresql+asyncpg://user1:pass1@host1/db1"
            )
            _ = await ensure_schema_initialized(
                "postgresql+asyncpg://user2:pass2@host2/db2"
            )

            assert len(_INITIALIZED_DSNS) == 2
            assert mock_apply.await_count == 2

class TestUserKeysAndDeps:
    def test_placeholder_extended(self) -> None:
        from backend.api.deps import _is_placeholder
        assert _is_placeholder("postgresql://postgres.<proyecto>:pass@host:5432/postgres") is True
        assert _is_placeholder("postgresql://user:placeholder_pass@host/db") is True
        assert _is_placeholder("postgresql://user:secret@host/db") is False

    def test_production_no_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from backend.api.deps import get_user_keys
        from backend.config import get_settings

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db.supabase.co:5432/postgres")
        monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
        monkeypatch.setenv("SUPABASE_ANON_KEY", "anon_key")
        get_settings.cache_clear()

        try:
            # Sin headers en producción -> todo None
            keys = get_user_keys()
            assert keys.database_url is None
            assert keys.supabase_url is None
            assert keys.supabase_key is None

            # Con header en producción -> toma el header
            keys_with_header = get_user_keys(
                x_user_database_url="postgresql://user:pass@host/db"
            )
            assert keys_with_header.database_url == "postgresql://user:pass@host/db"
        finally:
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_credentials_status_does_not_expose_dsn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from backend.api.credentials import credentials_status
        from backend.api.deps import UserKeys
        from backend.config import get_settings

        monkeypatch.setenv("APP_ENV", "production")
        get_settings.cache_clear()

        try:
            res = await credentials_status(
                keys=UserKeys(database_url="postgresql://user:pass@host:5432/db")
            )
            assert "dsn" not in res
            assert res["env"] == "production"
            assert res["dsn_valid"] is True
        finally:
            get_settings.cache_clear()
