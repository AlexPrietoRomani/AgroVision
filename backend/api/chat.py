"""
Archivo: chat.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Router del Asistente Agéntico (RAG). `POST /api/chat` recibe un turno del usuario, lo
procesa con el agente (function calling sobre las parcelas) y devuelve la respuesta más
la traza de herramientas usadas. La memoria vive en `chat_messages`. La llave de Groq es
efímera (cabecera `X-User-Groq-Key` o `DEV_GROQ_API_KEY` en local).

Nota: versión **no-streaming** (request/response). El streaming SSE queda como mejora
futura; la respuesta sincrónica encaja bien con la UI Shiny.

Estructura Interna:
    - `POST /api/chat`.

Entradas / Dependencias:
    - `backend.services.agent`, `backend.db.repositories`, `backend.api.deps`.

Ejemplo de Integración:
    from backend.api.chat import router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import UserKeys, get_db, get_user_keys
from backend.db import repositories as repo
from backend.services import agent

router = APIRouter(prefix="/api/chat", tags=["asistente"])


class ChatRequest(BaseModel):
    """Turno del usuario hacia el agente."""

    field_id: str | None = Field(
        default=None,
        description="ID de la parcela asociada para acotar la consulta",
    )


@router.post("")
async def chat(
    body: ChatRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Procesa un turno con el agente RAG y devuelve respuesta + traza de herramientas.

    Args:
        body (ChatRequest): Cuerpo del turno con mensaje, sesión y parcela opcional.
        keys (UserKeys): Llaves del usuario (BYOK).
        session (AsyncSession): Sesión de base de datos activa.

    Returns:
        dict: {reply, tool_logs, session_id}.
    """
    if not keys.groq:
        raise HTTPException(
            status_code=400, detail="Falta la llave de Groq (pestaña Credenciales)."
        )
    field_names = [row.name for row in await repo.list_fields(session)]
    
    field_name = None
    if body.field_id:
        f = await repo.get_field(session, body.field_id)
        if f:
            field_name = f.name
            
    return await agent.run_agent(
        session,
        body.message,
        body.session_id,
        keys.groq,
        field_names,
        field_id=body.field_id,
        field_name=field_name,
    )


@router.get("/history/{session_id}")
async def chat_history(
    session_id: str,
    field_id: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Obtiene el historial de chat de una sesión y parcela específicas.

    Args:
        session_id (str): Identificador del hilo conversacional.
        field_id (str, opcional): ID de la parcela para filtrar. Por defecto es None.
        session (AsyncSession): Sesión de base de datos activa.

    Returns:
        list[dict]: Mensajes de chat en el formato [{'role', 'content'}].
    """
    history = await repo.get_chat_history(session, session_id, field_id=field_id)
    return [{"role": row.role, "content": row.content} for row in history]
