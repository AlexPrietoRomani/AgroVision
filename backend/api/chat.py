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

    session_id: str = Field(min_length=1, description="Hilo conversacional")
    message: str = Field(min_length=1, description="Mensaje del usuario")


@router.post("")
async def chat(
    body: ChatRequest,
    keys: UserKeys = Depends(get_user_keys),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Procesa un turno con el agente RAG y devuelve respuesta + traza de herramientas."""
    if not keys.groq:
        raise HTTPException(
            status_code=400, detail="Falta la llave de Groq (pestaña Credenciales)."
        )
    field_names = [row.name for row in await repo.list_fields(session)]
    return await agent.run_agent(session, body.message, body.session_id, keys.groq, field_names)
