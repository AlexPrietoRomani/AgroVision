"""
Archivo: credentials.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Endpoint de conveniencia para desarrollo: informa **qué credenciales BYOK están
presentes en el `.env` del servidor** (variables `DEV_*` / `SUPABASE_*` / `DATABASE_URL`),
para que la UI pueda ofrecer "usar las del servidor" sin que el usuario las reescriba.
Devuelve **solo booleanos de presencia** — nunca los valores — para no exponer secretos.

En **producción** (`APP_ENV=production`), las `DEV_*` keys NO están disponibles
(cada usuario debe poner las suyas). El endpoint reporta `env: "production"` para
que la UI muestre el aviso correspondiente.

Estructura Interna:
    - `GET /api/credentials/status`: presencia (bool) de Groq, Copernicus y Supabase + entorno.

Entradas / Dependencias:
    - Variables de entorno (cargadas por `backend.config`).

Ejemplo de Integración:
    from backend.api.credentials import router
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from backend.config import get_settings

router = APIRouter(prefix="/api/credentials", tags=["credenciales"])


@router.get("/status")
def credentials_status() -> dict:
    """Presencia (bool) de las credenciales en el `.env` del servidor (sin valores) + entorno."""
    settings = get_settings()
    is_dev = settings.app_env == "development"

    # En producción, las DEV_* keys NO deben usarse (cada usuario pone las suyas)
    dev_groq = bool(os.getenv("DEV_GROQ_API_KEY")) if is_dev else False
    dev_cop = (
        bool(os.getenv("DEV_COPERNICUS_CLIENT_ID") and os.getenv("DEV_COPERNICUS_CLIENT_SECRET"))
        if is_dev
        else False
    )

    return {
        "env": settings.app_env,
        "groq": dev_groq,
        "copernicus": dev_cop,
        "supabase": bool(os.getenv("DATABASE_URL")),
        "supabase_url": os.getenv("SUPABASE_URL") if is_dev else None,
    }
