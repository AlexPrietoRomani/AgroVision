"""
Archivo: profiles.py
Fecha de modificación: 17/06/2026
Autor: Equipo AgroVisión

Descripción:
Router de la API para la gestión de perfiles de usuario (Fase 15). Permite conectar
(buscar o crear) un perfil mediante el hash SHA-256 de la URL de Supabase, leerlo,
actualizarlo y eliminarlo. Nunca almacena API keys — solo nombre, preferencias y
el fingerprint de la URL.

Acciones Principales:
    - `POST /api/profiles/connect`: busca o crea un perfil por hash.
    - `GET /api/profiles/{profile_id}`: lee un perfil (modo compartido).
    - `PATCH /api/profiles/{profile_id}`: actualiza nombre, preferencias, etc.
    - `DELETE /api/profiles/{profile_id}`: elimina un perfil.

Estructura Interna:
    - `router`: instancia de APIRouter con tag "perfiles".
    - `ConnectRequest`, `UpdateRequest`: modelos Pydantic de entrada.

Entradas / Dependencias:
    - `backend.db.repositories` (funciones de perfil).
    - `backend.api.deps` (sesión de base de datos).

Salidas / Efectos:
    - Lee/escribe en la tabla `user_profiles`.

Integración UI:
    - Este router es invocado por el frontend desde la lógica de modos de sesión.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.db import repositories as repo

logger = logging.getLogger("agrovision.profiles")

router = APIRouter(prefix="/api/profiles", tags=["perfiles"])


class ConnectRequest(BaseModel):
    """Modelo de solicitud para conectar (buscar o crear) un perfil."""

    supabase_url_hash: str = Field(
        ..., min_length=16, max_length=128, description="Hash SHA-256 de la URL de Supabase"
    )
    display_name: str = Field(default="Agrónomo", max_length=100)


class UpdateRequest(BaseModel):
    """Modelo de solicitud para actualizar un perfil."""

    display_name: str | None = Field(default=None, max_length=100)
    active_field_id: str | None = None
    preferences: dict[str, Any] | None = None
    session_mode: str | None = Field(default=None, pattern="^(ephemeral|saved|shared)$")


@router.post("/connect")
async def connect_profile(
    body: ConnectRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Busca un perfil existente por hash de URL de Supabase o crea uno nuevo.

    Args:
        body (ConnectRequest): Hash de la URL y nombre opcional.
        db (AsyncSession): Sesión de base de datos.

    Returns:
        dict: Datos completos del perfil (existente o recién creado).
    """
    try:
        profile = await repo.upsert_profile(
            db, supabase_url_hash=body.supabase_url_hash, display_name=body.display_name
        )
        logger.info("Perfil conectado: %s", profile["id"])
        return profile
    except Exception as exc:
        logger.exception("Error al conectar perfil")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{profile_id}")
async def read_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Lee un perfil de usuario por su ID.

    Args:
        profile_id (str): UUID del perfil.
        db (AsyncSession): Sesión de base de datos.

    Returns:
        dict: Datos completos del perfil.

    Raises:
        HTTPException: 404 si el perfil no existe.
    """
    profile = await repo.get_profile(db, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    return profile


@router.patch("/{profile_id}")
async def update_profile(
    profile_id: str,
    body: UpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Actualiza campos específicos de un perfil de usuario.

    Args:
        profile_id (str): UUID del perfil a actualizar.
        body (UpdateRequest): Campos a actualizar.
        db (AsyncSession): Sesión de base de datos.

    Returns:
        dict: Perfil actualizado.

    Raises:
        HTTPException: 404 si el perfil no existe.
    """
    updates = body.model_dump(exclude_none=True)
    profile = await repo.update_profile(db, profile_id, updates)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    logger.info("Perfil actualizado: %s — campos: %s", profile_id, list(updates.keys()))
    return profile


@router.delete("/{profile_id}")
async def remove_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Elimina un perfil de usuario y vuelve a modo efímero.

    Args:
        profile_id (str): UUID del perfil a eliminar.
        db (AsyncSession): Sesión de base de datos.

    Returns:
        dict: Mensaje de confirmación.

    Raises:
        HTTPException: 404 si el perfil no existía.
    """
    deleted = await repo.delete_profile(db, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
    logger.info("Perfil eliminado: %s", profile_id)
    return {"detail": "Perfil eliminado correctamente"}
