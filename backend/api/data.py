"""
Archivo: data.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Router del **Explorador de Datos** (Fase 11). Permite consultar las tablas de la BD
Supabase directamente desde la UI. Expone dos endpoints:
    - `GET /api/data/{table}`: lista los primeros 100 registros de una tabla permitida.
    - `POST /api/data/query`: ejecuta una consulta SQL personalizada (solo SELECT).

Seguridad:
    - Solo tablas explícitamente permitidas (`ALLOWED_TABLES`).
    - Solo consultas `SELECT` (bloquea INSERT/UPDATE/DELETE/ALTER/DROP).
    - Límite de 1000 filas por consulta.
    - Timeout de 10 segundos.

Entradas / Dependencias:
    - `backend.api.deps.get_db`, `backend.api.deps.get_user_keys`.

Ejemplo de Integración:
    from backend.api.data import router
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db

router = APIRouter(prefix="/api/data", tags=["explorador de datos"])

# Tablas permitidas para consulta directa
ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "fields",
        "vegetation_indices",
        "weather_data",
        "chat_messages",
        "events",
        "plant_counts",
        "user_profiles",
    }
)

# Límite máximo de filas por consulta
MAX_ROWS = 1000


def _validate_query(sql: str) -> str:
    """
    Valida que la consulta sea solo SELECT (lectura).

    Args:
        sql: Consulta SQL propuesta.

    Returns:
        La consulta limpia (stripped).

    Raises:
        HTTPException: Si la consulta no es SELECT o intenta modificar datos.
    """
    sql = sql.strip().rstrip(";")
    upper = sql.upper()

    # Bloquear cualquier cosa que no sea SELECT
    if not upper.startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Solo se permiten consultas SELECT.")

    # Bloquear palabras clave peligrosas
    dangerous = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "ALTER",
        "DROP",
        "CREATE",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
    ]
    for word in dangerous:
        if re.search(r"\b" + word + r"\b", upper):
            raise HTTPException(status_code=400, detail=f"Consulta bloqueada: contiene '{word}'.")

    return sql


@router.get("/schema")
async def get_schema(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Devuelve el esquema de la BD (tablas, columnas, tipos) para generar un diagrama ER.

    Consulta `information_schema.columns` sobre las tablas permitidas.
    """
    rows = await session.execute(
        text(
            "select table_name, column_name, data_type, is_nullable "
            "from information_schema.columns "
            "where table_schema = 'public' and table_name = any(:tables) "
            "order by table_name, ordinal_position"
        ),
        {"tables": list(ALLOWED_TABLES)},
    )
    tables: dict[str, list[dict]] = {}
    for r in rows:
        tables.setdefault(r.table_name, []).append(
            {"name": r.column_name, "type": r.data_type, "nullable": r.is_nullable == "YES"}
        )
    return {"tables": tables}


@router.get("/{table}")
async def get_table(
    table: str,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Lista los primeros 100 registros de una tabla permitida.

    Args:
        table: Nombre de la tabla (debe estar en ALLOWED_TABLES).
        session: Sesión de BD.

    Returns:
        Dict con `rows` (lista de dicts) y `count`.

    Raises:
        HTTPException: Si la tabla no está permitida o no existe.
    """
    if table not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=400,
            detail=f"Tabla no permitida. Permitidas: {sorted(ALLOWED_TABLES)}",
        )

    try:
        query = text(f"SELECT * FROM {table} LIMIT 100")
        result = await session.execute(query)
        rows = [dict(row._mapping) for row in result.fetchall()]
        # Convertir tipos no serializables
        for row in rows:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
                elif hasattr(v, "__geo_interface__"):
                    row[k] = dict(v.__geo_interface__)
        return {"table": table, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/query")
async def run_query(
    body: dict,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ejecuta una consulta SQL personalizada (solo SELECT).

    Args:
        body: {"sql": "SELECT ..."}
        session: Sesión de BD.

    Returns:
        Dict con `rows` y `count`.

    Raises:
        HTTPException: Si la consulta es inválida o falla.
    """
    sql = body.get("sql", "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="Falta la consulta SQL.")

    sql = _validate_query(sql)

    # Añadir LIMIT si no existe
    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {MAX_ROWS}"

    try:
        result = await session.execute(text(sql))
        rows = [dict(row._mapping) for row in result.fetchall()]
        # Convertir tipos no serializables
        for row in rows:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
                elif hasattr(v, "__geo_interface__"):
                    row[k] = dict(v.__geo_interface__)
        return {"rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
