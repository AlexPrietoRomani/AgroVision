"""
Archivo: test_parcel_indices_api.py
Fecha de modificación: 28/10/2026
Autor: Equipo AgroVisión

Descripción:
Pruebas unitarias y de simulación de usuario de la Fase 5: selección de variables
satelitales en el alta (`FieldIn`), actualización incremental (`FieldUpdate`), backfill
multivariable en el servicio de parcelas y endpoints `/api/fields` y
`/api/vegetation/reprocess`. Se mockean repositorio, teledetección y sesión de BD para
aislar la lógica de API sin infraestructura externa.

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_parcel_indices_api.py -q
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.core.schemas import VALID_SATELLITE_INDICES, FieldIn, FieldUpdate
from backend.db import repositories as repo
from backend.main import app
from backend.services import parcels

_GEOM = {
    "type": "Polygon",
    "coordinates": [
        [[-58.5, -34.6], [-58.5, -34.58], [-58.47, -34.58], [-58.47, -34.6], [-58.5, -34.6]]
    ],
}
_KEYS = UserKeys(copernicus_id="client-id", copernicus_secret="client-secret")


class _FakeSession:
    """Sesión async mínima para el context manager del backfill."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: object) -> bool:
        return False


def _fake_sessionmaker() -> _FakeSession:
    return _FakeSession()


def _field_row(
    selected: list[str] | None = None, crop_variety: str | None = None
) -> SimpleNamespace:
    """Fila de parcela con todos los atributos que consumen los routers."""
    return SimpleNamespace(
        id="field-1",
        name="Lote Arándanos",
        area_ha=1.25,
        lon=-58.48,
        lat=-34.59,
        geojson=json.dumps(_GEOM),
        crop_variety=crop_variety,
        field_type=None,
        soil_type=None,
        irrigation_system=None,
        pests_diseases=None,
        plantation_date=None,
        num_plants=None,
        historical_yield=None,
        target_market=None,
        document_metadata=None,
        selected_indices=selected,
    )


@pytest.fixture
def client() -> TestClient:
    """Cliente HTTP con sesión y credenciales BYOK sustituidas por dobles de prueba."""

    async def _session_override():
        yield object()

    app.dependency_overrides[get_db] = _session_override
    app.dependency_overrides[get_user_keys] = lambda: _KEYS
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# SF5.1 — Esquemas y servicio
# ---------------------------------------------------------------------------


def test_valid_satellite_indices_catalogo() -> None:
    """El catálogo de índices expone exactamente las cinco variables admitidas."""
    assert VALID_SATELLITE_INDICES == ("ndvi", "evi", "savi", "ndwi", "ndre")


def test_field_in_default_es_ndvi() -> None:
    """Sin selección explícita, `FieldIn` usa NDVI y no exige variedad de cultivo."""
    field = FieldIn(name="Lote", geojson=_GEOM)
    assert field.selected_indices == ["ndvi"]
    assert field.crop_variety is None


def test_field_in_normaliza_y_deduplica_seleccion() -> None:
    """La selección se normaliza a minúsculas, sin espacios ni duplicados."""
    field = FieldIn(
        name="Lote",
        geojson=_GEOM,
        crop_variety="Biloxi",
        selected_indices=[" NDVI ", "ndwi", "ndvi", "NDRE"],
    )
    assert field.crop_variety == "Biloxi"
    assert field.selected_indices == ["ndvi", "ndwi", "ndre"]


@pytest.mark.parametrize("indices", [[], ["ndvi", "lai"], [" "], ["ndvi", 3]])
def test_field_in_rechaza_seleccion_invalida(indices: list) -> None:
    """Listas vacías o índices fuera del catálogo disparan ValidationError."""
    with pytest.raises(ValidationError):
        FieldIn(name="Lote", geojson=_GEOM, selected_indices=indices)


def test_field_update_acepta_none_y_normaliza() -> None:
    """`FieldUpdate` permite no tocar la selección o enviarla normalizada."""
    assert FieldUpdate().selected_indices is None
    update = FieldUpdate(selected_indices=["NDRE", "ndre", "ndwi"])
    assert update.selected_indices == ["ndre", "ndwi"]


def test_field_update_rechaza_seleccion_invalida() -> None:
    """Una selección vacía o con un índice desconocido no es válida en el PATCH."""
    with pytest.raises(ValidationError):
        FieldUpdate(selected_indices=[])
    with pytest.raises(ValidationError):
        FieldUpdate(selected_indices=["ndvi", "lai"])


def test_create_parcel_pasa_seleccion_al_repositorio(monkeypatch: pytest.MonkeyPatch) -> None:
    """`create_parcel` propaga variedad y selección cuando el repo las soporta."""
    captured: dict = {}

    async def fake_create_field(
        session: object,
        *,
        name: str,
        geojson: dict,
        user_id: str | None = None,
        crop_variety: str | None = None,
        selected_indices: list[str] | None = None,
    ) -> SimpleNamespace:
        captured.update(
            name=name,
            geojson=geojson,
            user_id=user_id,
            crop_variety=crop_variety,
            selected_indices=selected_indices,
        )
        return SimpleNamespace(id="field-1")

    monkeypatch.setattr(parcels.repo, "create_field", fake_create_field)
    field = FieldIn(
        name="Lote Arándanos",
        geojson=_GEOM,
        crop_variety="Biloxi",
        selected_indices=["ndvi", "ndwi"],
    )

    row = asyncio.run(parcels.create_parcel(object(), field))

    assert row.id == "field-1"
    assert captured["crop_variety"] == "Biloxi"
    assert captured["selected_indices"] == ["ndvi", "ndwi"]


def test_create_parcel_es_compatible_con_repositorio_antiguo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si `create_field` no acepta los kwargs nuevos, la creación sigue funcionando."""

    async def fake_create_field(
        session: object,
        *,
        name: str,
        geojson: dict,
        user_id: str | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(id="field-old")

    monkeypatch.setattr(parcels.repo, "create_field", fake_create_field)
    field = FieldIn(name="Lote", geojson=_GEOM, selected_indices=["evi"])

    row = asyncio.run(parcels.create_parcel(object(), field))

    assert row.id == "field-old"


def test_run_indices_backfill_persiste_cada_indice(monkeypatch: pytest.MonkeyPatch) -> None:
    """El backfill calcula y persiste exactamente los índices solicitados."""
    requested: list[str] = []
    persisted: list[str] = []
    events: list[str] = []

    async def fake_series(
        geojson: dict,
        start: str | None,
        end: str | None,
        client_id: str,
        client_secret: str,
        index: str = "ndvi",
    ) -> list[dict]:
        requested.append(index)
        return [{"date": "2026-01-01", f"mean_{index}": 0.5}]

    async def fake_upsert(
        session: object, field_id: str, points: list[dict], index: str
    ) -> int:
        persisted.append(index)
        return len(points)

    monkeypatch.setattr(parcels.remote_sensing, "index_series_monthly", fake_series)
    monkeypatch.setattr(parcels.repo, "upsert_index_points", fake_upsert)
    monkeypatch.setattr(parcels, "get_sessionmaker", lambda: _fake_sessionmaker)
    monkeypatch.setattr(
        parcels,
        "emit_event",
        lambda action, meta=None, session_id="_backend": events.append(action),
    )

    counts = asyncio.run(
        parcels.run_indices_backfill("field-1", _GEOM, _KEYS, ["ndvi", "evi", "ndvi"])
    )

    assert requested == ["ndvi", "evi"]
    assert persisted == ["ndvi", "evi"]
    assert counts == {"ndvi": 1, "evi": 1}
    assert events == ["backfill_start", "backfill_done"]


def test_run_indices_backfill_sin_credenciales(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin credenciales Copernicus no se consulta Sentinel Hub y se emite el skip."""
    events: list[str] = []

    async def fail_series(*args: object, **kwargs: object) -> list[dict]:
        raise AssertionError("no debe consultarse Sentinel Hub sin credenciales")

    monkeypatch.setattr(parcels.remote_sensing, "index_series_monthly", fail_series)
    monkeypatch.setattr(
        parcels,
        "emit_event",
        lambda action, meta=None, session_id="_backend": events.append(action),
    )

    counts = asyncio.run(parcels.run_indices_backfill("field-1", _GEOM, UserKeys()))

    assert counts == {}
    assert events == ["backfill_skip"]


def test_run_ndvi_backfill_es_wrapper_retrocompatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El wrapper NDVI conserva la firma y el retorno entero original."""
    captured: dict = {}

    async def fake_backfill(
        field_id: str,
        geojson: dict,
        keys: UserKeys,
        indices: list[str] | None = None,
        name: str = "",
    ) -> dict[str, int]:
        captured.update(field_id=field_id, indices=indices, name=name)
        return {"ndvi": 7}

    monkeypatch.setattr(parcels, "run_indices_backfill", fake_backfill)

    total = asyncio.run(parcels.run_ndvi_backfill("field-1", _GEOM, _KEYS, name="Lote"))

    assert total == 7
    assert captured == {"field_id": "field-1", "indices": ["ndvi"], "name": "Lote"}


# ---------------------------------------------------------------------------
# SF5.2 — Endpoints y simulación de usuario
# ---------------------------------------------------------------------------


def test_post_fields_agenda_solo_los_indices_elegidos(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """`POST /api/fields` persiste y agenda el backfill de la selección inicial."""
    created = _field_row(["ndvi", "ndwi"], crop_variety="Biloxi")
    backfill = AsyncMock(return_value={"ndvi": 3, "ndwi": 3})

    async def fake_create(session: object, field_in: FieldIn, user_id: str | None = None):
        assert field_in.selected_indices == ["ndvi", "ndwi"]
        assert field_in.crop_variety == "Biloxi"
        return created

    monkeypatch.setattr(parcels, "create_parcel", fake_create)
    monkeypatch.setattr(parcels, "run_indices_backfill", backfill)

    response = client.post(
        "/api/fields",
        json={
            "name": "Lote Arándanos",
            "geojson": _GEOM,
            "crop_variety": "Biloxi",
            "selected_indices": ["NDVI", "ndwi", "ndvi"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["crop_variety"] == "Biloxi"
    assert body["selected_indices"] == ["ndvi", "ndwi"]
    backfill.assert_awaited_once()
    assert backfill.await_args.args[3] == ["ndvi", "ndwi"]


def test_get_fields_incluye_selected_indices(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """El listado expone `selected_indices` con fallback NDVI."""
    rows = [_field_row(["ndvi", "ndre"]), _field_row(None)]
    monkeypatch.setattr(parcels, "list_parcels", AsyncMock(return_value=rows))

    response = client.get("/api/fields")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["selected_indices"] == ["ndvi", "ndre"]
    assert body[1]["selected_indices"] == ["ndvi"]


def test_get_field_incluye_calculated_indices(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """El detalle expone la selección y los índices ya calculados."""
    row = _field_row(["ndvi", "ndwi"])
    monkeypatch.setattr(parcels, "get_parcel", AsyncMock(return_value=row))
    monkeypatch.setattr(
        repo,
        "get_calculated_indices",
        AsyncMock(return_value=["ndvi", "ndwi"]),
        raising=False,
    )

    response = client.get("/api/fields/field-1")

    assert response.status_code == 200
    body = response.json()
    assert body["selected_indices"] == ["ndvi", "ndwi"]
    assert body["calculated_indices"] == ["ndvi", "ndwi"]


def test_patch_field_agenda_solo_indices_nuevos(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Agregar NDRE agenda únicamente el backfill de NDRE."""
    previous = _field_row(["ndvi", "ndwi"], crop_variety="Biloxi")
    updated = _field_row(["ndvi", "ndwi", "ndre"], crop_variety="Biloxi")
    backfill = AsyncMock(return_value={"ndre": 4})

    monkeypatch.setattr(parcels, "get_parcel", AsyncMock(return_value=previous))
    monkeypatch.setattr(parcels, "update_parcel", AsyncMock(return_value=updated))
    monkeypatch.setattr(
        repo,
        "get_calculated_indices",
        AsyncMock(return_value=["ndvi", "ndwi"]),
        raising=False,
    )
    monkeypatch.setattr(repo, "get_field_geojson", AsyncMock(return_value=_GEOM))
    monkeypatch.setattr(parcels, "run_indices_backfill", backfill)

    response = client.patch(
        "/api/fields/field-1",
        json={"selected_indices": ["ndvi", "ndwi", "ndre"]},
    )

    assert response.status_code == 200
    assert response.json()["selected_indices"] == ["ndvi", "ndwi", "ndre"]
    backfill.assert_awaited_once()
    assert backfill.await_args.args[3] == ["ndre"]


def test_patch_field_usa_seleccion_previa_si_no_hay_calculados(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Sin `get_calculated_indices`, el diferencial se calcula contra la selección previa."""
    previous = _field_row(["ndvi"], crop_variety="Biloxi")
    updated = _field_row(["ndvi", "evi"], crop_variety="Biloxi")
    backfill = AsyncMock(return_value={"evi": 2})

    monkeypatch.setattr(parcels, "get_parcel", AsyncMock(return_value=previous))
    monkeypatch.setattr(parcels, "update_parcel", AsyncMock(return_value=updated))
    monkeypatch.setattr(repo, "get_calculated_indices", None, raising=False)
    monkeypatch.setattr(repo, "get_field_geojson", AsyncMock(return_value=_GEOM))
    monkeypatch.setattr(parcels, "run_indices_backfill", backfill)

    response = client.patch("/api/fields/field-1", json={"selected_indices": ["ndvi", "evi"]})

    assert response.status_code == 200
    assert response.json()["selected_indices"] == ["ndvi", "evi"]
    assert backfill.await_args.args[3] == ["evi"]


def test_patch_field_inexistente_devuelve_404(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Actualizar una parcela inexistente devuelve 404 sin agendar backfill."""
    monkeypatch.setattr(parcels, "get_parcel", AsyncMock(return_value=None))

    response = client.patch("/api/fields/desconocida", json={"selected_indices": ["ndwi"]})

    assert response.status_code == 404


def test_reprocess_selectivo_solo_calcula_indices_enviados(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """`indices` limita el reproceso y anexa el índice a la selección de la parcela."""
    series = AsyncMock(return_value=[{"date": "2026-01-01", "mean_ndre": 0.4}])
    upsert = AsyncMock(return_value=5)
    update_attributes = AsyncMock(return_value=_field_row(["ndvi", "ndwi", "ndre"]))

    monkeypatch.setattr(repo, "get_field_geojson", AsyncMock(return_value=_GEOM))
    monkeypatch.setattr(
        repo, "get_field", AsyncMock(return_value=_field_row(["ndvi", "ndwi"]))
    )
    monkeypatch.setattr(repo, "upsert_index_points", upsert)
    monkeypatch.setattr(repo, "update_field_attributes", update_attributes)
    monkeypatch.setattr(parcels.remote_sensing, "index_series_monthly", series)

    response = client.post(
        "/api/vegetation/reprocess",
        json={"field_id": "field-1", "mode": "indices", "indices": ["ndre"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["indices"] == [{"index": "ndre", "points": 5}]
    assert body["selected_indices"] == ["ndvi", "ndwi", "ndre"]
    series.assert_awaited_once()
    assert series.await_args.args[-1] == "ndre"
    update_attributes.assert_awaited_once()
    assert update_attributes.await_args.args[2] == {
        "selected_indices": ["ndvi", "ndwi", "ndre"]
    }


def test_reprocess_sin_indices_usa_seleccion_de_parcela(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Sin `indices`, se reprocesan los `selected_indices` de la parcela."""
    requested: list[str] = []

    async def fake_series(
        geojson: dict,
        start: str | None,
        end: str | None,
        client_id: str,
        client_secret: str,
        index: str = "ndvi",
    ) -> list[dict]:
        requested.append(index)
        return []

    monkeypatch.setattr(repo, "get_field_geojson", AsyncMock(return_value=_GEOM))
    monkeypatch.setattr(
        repo, "get_field", AsyncMock(return_value=_field_row(["ndvi", "ndwi"]))
    )
    monkeypatch.setattr(repo, "upsert_index_points", AsyncMock(return_value=0))
    monkeypatch.setattr(repo, "update_field_attributes", AsyncMock(return_value=None))
    monkeypatch.setattr(parcels.remote_sensing, "index_series_monthly", fake_series)

    response = client.post(
        "/api/vegetation/reprocess",
        json={"field_id": "field-1", "mode": "indices"},
    )

    assert response.status_code == 200
    assert response.json()["indices"] == [
        {"index": "ndvi", "points": 0},
        {"index": "ndwi", "points": 0},
    ]
    assert requested == ["ndvi", "ndwi"]


def test_reprocess_rechaza_indice_invalido(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Un índice desconocido en el reproceso devuelve 422 y no llama a Sentinel Hub."""
    series = AsyncMock()
    monkeypatch.setattr(repo, "get_field_geojson", AsyncMock(return_value=_GEOM))
    monkeypatch.setattr(parcels.remote_sensing, "index_series_monthly", series)

    response = client.post(
        "/api/vegetation/reprocess",
        json={"field_id": "field-1", "mode": "indices", "indices": ["lai"]},
    )

    assert response.status_code == 422
    series.assert_not_awaited()


def test_simulacion_usuario_alta_y_expansion_incremental(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Flujo real: alta con NDVI+NDWI y posterior adición de NDRE solo calcula NDRE."""
    state = {"selected": ["ndvi", "ndwi"], "calculated": ["ndvi", "ndwi"]}
    backfill = AsyncMock(return_value={"ndre": 3})

    async def fake_create(session: object, field_in: FieldIn, user_id: str | None = None):
        state["selected"] = list(field_in.selected_indices)
        return _field_row(state["selected"], crop_variety=field_in.crop_variety)

    async def fake_get(session: object, field_id: str):
        return _field_row(state["selected"], crop_variety="Biloxi")

    async def fake_update(session: object, field_id: str, attributes: dict):
        if "selected_indices" in attributes:
            state["selected"] = list(attributes["selected_indices"])
        return _field_row(state["selected"], crop_variety="Biloxi")

    monkeypatch.setattr(parcels, "create_parcel", fake_create)
    monkeypatch.setattr(parcels, "get_parcel", fake_get)
    monkeypatch.setattr(parcels, "update_parcel", fake_update)
    monkeypatch.setattr(
        repo,
        "get_calculated_indices",
        AsyncMock(side_effect=lambda session, field_id: list(state["calculated"])),
        raising=False,
    )
    monkeypatch.setattr(repo, "get_field_geojson", AsyncMock(return_value=_GEOM))
    monkeypatch.setattr(parcels, "run_indices_backfill", backfill)

    created = client.post(
        "/api/fields",
        json={
            "name": "Lote Arándanos",
            "geojson": _GEOM,
            "crop_variety": "Biloxi",
            "selected_indices": ["ndvi", "ndwi"],
        },
    )
    expanded = client.patch(
        "/api/fields/field-1",
        json={"selected_indices": ["ndvi", "ndwi", "ndre"]},
    )

    assert created.status_code == 200
    assert created.json()["selected_indices"] == ["ndvi", "ndwi"]
    assert expanded.status_code == 200
    assert expanded.json()["selected_indices"] == ["ndvi", "ndwi", "ndre"]
    assert backfill.await_count == 2
    first_call, second_call = backfill.await_args_list
    assert first_call.args[3] == ["ndvi", "ndwi"]
    assert second_call.args[3] == ["ndre"]
