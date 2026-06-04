"""
Archivo: credentials.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Endpoint de conveniencia para desarrollo: informa **qué credenciales BYOK están
presentes en el `.env` del servidor** (variables `DEV_*` / `SUPABASE_*` / `DATABASE_URL`),
para que la UI pueda ofrecer "usar las del servidor" sin que el usuario las reescriba.
Devuelve **solo booleanos de presencia** — nunca los valores — para no exponer secretos.

Estructura Interna:
    - `GET /api/credentials/status`: presencia (bool) de Groq, Copernicus y Supabase.

Entradas / Dependencias:
    - Variables de entorno (cargadas por `backend.config`).

Ejemplo de Integración:
    from backend.api.credentials import router
"""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/credentials", tags=["credenciales"])


@router.get("/status")
def credentials_status() -> dict:
    """Presencia (bool) de las credenciales en el `.env` del servidor (sin valores)."""
    return {
        "groq": bool(os.getenv("DEV_GROQ_API_KEY")),
        "copernicus": bool(
            os.getenv("DEV_COPERNICUS_CLIENT_ID") and os.getenv("DEV_COPERNICUS_CLIENT_SECRET")
        ),
        "supabase": bool(os.getenv("DATABASE_URL")),
    }
