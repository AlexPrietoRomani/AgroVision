"""
Archivo: events.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Router de **Telemetría y Observabilidad de UI** (Fase 9). Recibe los eventos que el
frontend emite en cada acción del usuario (`POST /api/events`), los **redacta**
(nunca registra secretos), los escribe en *stdout* (logging estructurado) y los guarda
en un **ring buffer** en memoria (acotado a `MAX_EVENTS`) consultable en
`GET /api/events/recent` — útil para depurar una sesión en vivo sin infraestructura.

Opcionalmente (SF9.3, `EVENTS_PERSIST=true` + `DATABASE_URL`) persiste cada evento en
la tabla `events` de Supabase de forma *best-effort* (un fallo de BD nunca rompe la UI).

Estructura Interna:
    - `Event`: esquema Pydantic del evento entrante.
    - `_redact`: elimina valores de claves que parezcan secretos.
    - `POST /api/events`: ingest (log + buffer + persistencia opcional).
    - `GET /api/events/recent`: últimos eventos (filtrables por `session_id`).

Entradas / Dependencias:
    - `fastapi`, `pydantic`, `backend.config`; (opcional) `backend.db` para persistir.

Ejemplo de Integración:
    from backend.api.events import router
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.config import get_settings

router = APIRouter(prefix="/api/events", tags=["telemetría"])
_logger = logging.getLogger("agrovision.events")

# Tope del buffer en memoria: suficiente para depurar una sesión sin crecer sin límite.
MAX_EVENTS = 500
_BUFFER: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)

# Subcadenas que delatan un secreto en una clave de `meta`. El backend NUNCA confía en
# que el front no mande secretos: si una clave las contiene, su valor se redacta.
_SECRET_KEYS = frozenset(
    {"groq", "key", "secret", "token", "password", "anon", "apikey", "auth", "credential"}
)


class Event(BaseModel):
    """Evento de telemetría emitido por la UI (sin secretos)."""

    action: str
    session_id: str
    meta: dict[str, Any] = Field(default_factory=dict)
    ts: str | None = None


def _redact(meta: dict[str, Any]) -> dict[str, Any]:
    """Reemplaza por '***' el valor de toda clave que parezca un secreto."""
    return {k: ("***" if any(s in k.lower() for s in _SECRET_KEYS) else v) for k, v in meta.items()}


async def _persist_event(safe: dict[str, Any]) -> None:
    """Escribe el evento (ya redactado) en la tabla `events`; best-effort (SF9.3)."""
    try:
        from backend.db import repositories as repo
        from backend.db.session import get_sessionmaker

        async with get_sessionmaker()() as session:
            await repo.insert_event(
                session,
                action=safe["action"],
                session_id=safe["session_id"],
                meta=safe["meta"],
            )
    except Exception as error:  # noqa: BLE001 — la telemetría jamás debe romper la UI
        _logger.warning("No se pudo persistir el evento (best-effort): %s", error)


@router.post("")
async def ingest(ev: Event, background: BackgroundTasks) -> dict:
    """Valida, redacta y registra un evento (stdout + buffer; persistencia opcional)."""
    safe = ev.model_dump()
    safe["meta"] = _redact(ev.meta)
    _BUFFER.append(safe)
    _logger.info("[event] %s %s %s", ev.session_id, ev.action, safe["meta"])

    if get_settings().events_persist:
        background.add_task(_persist_event, safe)
    return {"ok": True}


@router.get("/recent")
def recent(limit: int = 100, session_id: str | None = None) -> list[dict]:
    """Devuelve los eventos más recientes (filtrables por `session_id`)."""
    items = list(_BUFFER)
    if session_id is not None:
        items = [e for e in items if e.get("session_id") == session_id]
    limit = max(1, min(limit, MAX_EVENTS))
    return items[-limit:]


@router.get("/all")
async def all_events(
    limit: int = 200,
    session_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Devuelve eventos persistidos en la tabla `events` (requiere EVENTS_PERSIST=true).
    Útil para el visor de telemetría en la UI.
    """
    from sqlalchemy import text

    query = "SELECT id, action, session_id, meta, created_at FROM events"
    params: dict = {}
    conditions = []
    if session_id:
        conditions.append("session_id = :session_id")
        params["session_id"] = session_id
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = min(limit, 1000)

    result = await session.execute(text(query), params)
    rows = [dict(row._mapping) for row in result.fetchall()]
    # Serializar timestamps
    for row in rows:
        if hasattr(row.get("created_at"), "isoformat"):
            row["created_at"] = row["created_at"].isoformat()
    return rows
