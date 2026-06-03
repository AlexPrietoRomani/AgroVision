"""
Archivo: agent.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Orquestador del agente conversacional (RAG con function calling) sobre Groq/Llama 3.
Construye la conversación (sistema + memoria + turno), deja que el modelo decida qué
herramienta tipada invocar, ejecuta las herramientas reales (NDVI/clima/densidad) y
devuelve la respuesta final con la traza de herramientas usadas. Persiste los turnos
(user/assistant) en `chat_messages`. Usa la API OpenAI-compatible de Groq vía httpx
(async) — sin SDK extra.

Acciones Principales:
    - `run_agent`: ciclo de tool-calling + memoria + respuesta final.

Estructura Interna:
    - `_system_prompt`: instrucciones + parcelas disponibles.
    - `_groq_chat`: llamada HTTP a Groq (con/sin herramientas).
    - `run_agent`: bucle de orquestación.

Entradas / Dependencias:
    - `httpx`; `backend.services.tools`, `backend.db.repositories`.

Salidas / Efectos:
    - Lecturas/escrituras en `chat_messages`; llamadas a Groq y a las herramientas.

Ejemplo de Integración:
    from backend.services.agent import run_agent
    out = await run_agent(session, "¿cómo va el NDVI de Lote A?", "sess-1", keys, ["Lote A"])
"""

from __future__ import annotations

import json

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import repositories as repo
from backend.services.tools import TOOL_DISPATCH, TOOLS_SCHEMA

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"
_MAX_TOOL_ROUNDS = 4


def _system_prompt(field_names: list[str]) -> str:
    """Construye el prompt de sistema con las parcelas disponibles."""
    parcelas = ", ".join(field_names) if field_names else "(ninguna registrada todavía)"
    return (
        "Eres el asistente agronómico de AgroVisión. Respondes en español, de forma "
        "concisa y técnica. Dispones de herramientas para consultar el NDVI, el clima y "
        "la densidad de las parcelas del usuario; úsalas en vez de inventar datos. Si una "
        "herramienta indica que algo está 'en desarrollo', acláralo. "
        f"Parcelas disponibles: {parcelas}."
    )


async def _groq_chat(api_key: str, messages: list[dict], use_tools: bool) -> dict:
    """Llama al endpoint de chat de Groq (con herramientas si `use_tools`)."""
    payload: dict = {"model": _MODEL, "messages": messages, "temperature": 0.2}
    if use_tools:
        payload["tools"] = TOOLS_SCHEMA
        payload["tool_choice"] = "auto"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _GROQ_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=60
        )
    response.raise_for_status()
    return response.json()


async def run_agent(
    session: AsyncSession,
    message: str,
    session_id: str,
    api_key: str,
    field_names: list[str],
) -> dict:
    """
    Ejecuta el agente: memoria + tool-calling + respuesta, y persiste los turnos.

    Args:
        session (AsyncSession): Sesión de BD.
        message (str): Mensaje del usuario.
        session_id (str): Hilo conversacional.
        api_key (str): Llave de Groq (efímera).
        field_names (list[str]): Parcelas disponibles (para el prompt de sistema).

    Returns:
        dict: {reply, tool_logs, session_id}.
    """
    await repo.save_chat_message(session, session_id=session_id, role="user", content=message)
    history = await repo.get_chat_history(session, session_id)
    messages: list[dict] = [{"role": "system", "content": _system_prompt(field_names)}]
    messages += [{"role": row.role, "content": row.content} for row in history]

    tool_logs: list[dict] = []
    for _ in range(_MAX_TOOL_ROUNDS):
        data = await _groq_chat(api_key, messages, use_tools=True)
        choice = data["choices"][0]["message"]
        tool_calls = choice.get("tool_calls")
        if not tool_calls:
            reply = choice.get("content") or ""
            await repo.save_chat_message(
                session, session_id=session_id, role="assistant", content=reply
            )
            return {"reply": reply, "tool_logs": tool_logs, "session_id": session_id}

        messages.append(choice)  # mensaje del asistente con las tool_calls
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            tool = TOOL_DISPATCH.get(name)
            result = (
                await tool(session, **args)
                if tool
                else f"Herramienta desconocida: {name}."
            )
            tool_logs.append({"tool": name, "args": args})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    # Si se agotaron las rondas de herramientas, pide una respuesta final sin tools.
    data = await _groq_chat(api_key, messages, use_tools=False)
    reply = data["choices"][0]["message"].get("content") or "(sin respuesta)"
    await repo.save_chat_message(session, session_id=session_id, role="assistant", content=reply)
    return {"reply": reply, "tool_logs": tool_logs, "session_id": session_id}
