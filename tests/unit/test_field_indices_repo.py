"""
Archivo: test_field_indices_repo.py
Fecha de modificación: 28/10/2026
Autor: Alex Prieto Romani <alexprieto1997@gmail.com>

Descripción:
Pruebas unitarias de la Fase 4: validan el DDL idempotente de la migración
`0002_field_selected_indices.sql`, el soporte de `selected_indices` en la capa de
repositorios (`backend/db/repositories.py`) y la consulta de índices ya calculados.
La sesión de base de datos se mockea, por lo que no se requiere PostgreSQL.

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_field_indices_repo.py -q
"""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.migrate import MIGRATIONS_DIR
from backend.db.repositories import (
    create_field,
    get_calculated_indices,
    get_field,
    list_fields,
    update_field_attributes,
)

MIGRATION_0002 = MIGRATIONS_DIR / "0002_field_selected_indices.sql"

GEOJSON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-3.70, 40.40],
            [-3.69, 40.40],
            [-3.69, 40.41],
            [-3.70, 40.41],
            [-3.70, 40.40],
        ]
    ],
}


def _normalized(sql: str) -> str:
    """Colapsa espacios y saltos de línea para comparar fragmentos SQL."""
    return re.sub(r"\s+", " ", sql.lower()).strip()


def _without_comments(sql: str) -> str:
    """Elimina los comentarios `--` para inspeccionar solo sentencias ejecutables."""
    return re.sub(r"--.*$", "", sql, flags=re.MULTILINE)


def _result(rows: list[Any]) -> MagicMock:
    """Construye un resultado mock de SQLAlchemy con `.all()` y `.first()`."""
    result = MagicMock()
    result.all.return_value = rows
    result.first.return_value = rows[0] if rows else None
    return result


def _session() -> AsyncMock:
    """Devuelve una sesión async mock compatible con `AsyncSession`."""
    return AsyncMock(spec=AsyncSession)


def test_migration_0002_is_discovered_in_order() -> None:
    """El migrador descubre `0002` después de `0001` (simulación de usuario)."""
    paths = sorted(
        path.name
        for path in MIGRATIONS_DIR.glob("*.sql")
        if not path.name.endswith(".down.sql")
    )
    assert "0001_initial_schema.sql" in paths
    assert "0002_field_selected_indices.sql" in paths
    assert paths.index("0001_initial_schema.sql") < paths.index(
        "0002_field_selected_indices.sql"
    )


def test_migration_0002_adds_idempotent_column() -> None:
    """La migración añade `selected_indices` con default y sin romper re-ejecuciones."""
    sql = _normalized(MIGRATION_0002.read_text(encoding="utf-8"))
    assert (
        "add column if not exists selected_indices text[] not null "
        "default array['ndvi']::text[]" in sql
    )


def test_migration_0002_recreates_constraint_idempotently() -> None:
    """El constraint se elimina si existe y se vuelve a crear con el CHECK esperado."""
    sql = _normalized(_without_comments(MIGRATION_0002.read_text(encoding="utf-8")))
    assert "drop constraint if exists chk_fields_selected_indices" in sql
    assert "add constraint chk_fields_selected_indices" in sql
    assert "cardinality(selected_indices) >= 1" in sql
    assert "selected_indices <@ array['ndvi', 'evi', 'savi', 'ndwi', 'ndre']::text[]" in sql


def test_migration_0002_is_transactional_with_documented_rollback() -> None:
    """La migración abre/cierra transacción y documenta su reversa comentada."""
    raw = MIGRATION_0002.read_text(encoding="utf-8")
    sql = _normalized(_without_comments(raw))
    assert sql.startswith("begin;")
    assert sql.endswith("commit;")
    assert (
        "-- alter table public.fields drop column if exists selected_indices" in raw.lower()
    )


def test_create_field_persists_selected_indices_and_crop_variety() -> None:
    """El alta inserta índices y variedad, y los devuelve en el RETURNING."""
    session = _session()
    session.execute.return_value = _result(
        [
            SimpleNamespace(
                id="field-1",
                name="Lote Olivar",
                area_ha=2.5,
                crop_variety="Picual",
                selected_indices=["ndvi", "ndre"],
            )
        ]
    )

    field = asyncio.run(
        create_field(
            session,
            "Lote Olivar",
            GEOJSON,
            crop_variety="Picual",
            selected_indices=["ndvi", "ndre"],
        )
    )

    sql, params = session.execute.call_args.args
    statement = _normalized(str(sql))
    assert "insert into fields" in statement
    assert "crop_variety" in statement
    assert "selected_indices" in statement
    assert "returning" in statement
    assert params["crop_variety"] == "Picual"
    assert params["selected_indices"] == ["ndvi", "ndre"]
    assert field.selected_indices == ["ndvi", "ndre"]
    session.commit.assert_awaited_once()


def test_create_field_defaults_to_ndvi_when_indices_omitted_or_empty() -> None:
    """Sin selección explícita se persiste `["ndvi"]` para conservar el flujo histórico."""
    for supplied in (None, []):
        session = _session()
        session.execute.return_value = _result(
            [SimpleNamespace(selected_indices=["ndvi"], crop_variety=None)]
        )
        asyncio.run(create_field(session, "Lote", GEOJSON, selected_indices=supplied))
        _, params = session.execute.call_args.args
        assert params["selected_indices"] == ["ndvi"]


def test_get_field_and_list_fields_select_selected_indices() -> None:
    """Las lecturas incluyen la columna `selected_indices` en el SELECT."""
    session = _session()
    session.execute.return_value = _result(
        [SimpleNamespace(id="field-1", selected_indices=["ndvi", "evi"])]
    )
    asyncio.run(get_field(session, "field-1"))
    assert "selected_indices" in _normalized(str(session.execute.call_args.args[0]))

    session = _session()
    session.execute.return_value = _result(
        [SimpleNamespace(id="field-1", selected_indices=["ndvi"])]
    )
    rows = asyncio.run(list_fields(session))
    assert "selected_indices" in _normalized(str(session.execute.call_args.args[0]))
    assert rows[0].selected_indices == ["ndvi"]


def test_update_field_attributes_allows_selected_indices() -> None:
    """La actualización dinámica acepta `selected_indices` y devuelve la fila nueva."""
    session = _session()
    session.execute.side_effect = [
        _result([SimpleNamespace(id="field-1")]),
        _result([SimpleNamespace(id="field-1", selected_indices=["ndvi", "ndre", "ndwi"])]),
    ]

    row = asyncio.run(
        update_field_attributes(
            session, "field-1", {"selected_indices": ["ndvi", "ndre", "ndwi"]}
        )
    )

    update_sql, update_params = session.execute.call_args_list[0].args
    statement = _normalized(str(update_sql))
    assert "selected_indices = :selected_indices" in statement
    assert update_params["selected_indices"] == ["ndvi", "ndre", "ndwi"]
    assert row.selected_indices == ["ndvi", "ndre", "ndwi"]


def test_get_calculated_indices_returns_ordered_distinct_types() -> None:
    """La consulta devuelve los `index_type` distintos ya calculados, ordenados."""
    session = _session()
    session.execute.return_value = _result(
        [SimpleNamespace(index_type="evi"), SimpleNamespace(index_type="ndvi")]
    )

    calculated = asyncio.run(get_calculated_indices(session, "field-1"))

    sql, params = session.execute.call_args.args
    statement = _normalized(str(sql))
    assert "select distinct index_type from vegetation_indices" in statement
    assert "where field_id = :field_id" in statement
    assert "order by index_type" in statement
    assert params == {"field_id": "field-1"}
    assert calculated == ["evi", "ndvi"]


def test_user_simulation_create_then_expand_and_query_calculated_indices() -> None:
    """Flujo completo: alta con dos índices, ampliación a tres y lectura de calculados."""
    session = _session()
    session.execute.side_effect = [
        _result(
            [
                SimpleNamespace(
                    id="field-1",
                    name="Lote Simulado",
                    area_ha=1.2,
                    crop_variety="Arbequina",
                    selected_indices=["ndvi", "ndre"],
                )
            ]
        ),
        _result([SimpleNamespace(id="field-1")]),
        _result(
            [
                SimpleNamespace(
                    id="field-1",
                    selected_indices=["ndvi", "ndre", "ndwi"],
                )
            ]
        ),
        _result([SimpleNamespace(index_type="ndre"), SimpleNamespace(index_type="ndvi")]),
    ]

    async def _run() -> tuple[Any, Any, list[str]]:
        field = await create_field(
            session,
            "Lote Simulado",
            GEOJSON,
            crop_variety="Arbequina",
            selected_indices=["ndvi", "ndre"],
        )
        expanded = await update_field_attributes(
            session, field.id, {"selected_indices": ["ndvi", "ndre", "ndwi"]}
        )
        calculated = await get_calculated_indices(session, field.id)
        return field, expanded, calculated

    field, expanded, calculated = asyncio.run(_run())

    assert field.selected_indices == ["ndvi", "ndre"]
    assert expanded.selected_indices == ["ndvi", "ndre", "ndwi"]
    assert calculated == ["ndre", "ndvi"]
    pending = set(expanded.selected_indices) - set(calculated)
    assert pending == {"ndwi"}
