"""
Archivo: migrate.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Aplicador de migraciones SQL versionadas (`supabase/migrations/*.sql`) contra el
Supabase del usuario. Ejecuta cada archivo en orden con una conexión asyncpg directa
(las migraciones son idempotentes: `if not exists` / `drop policy if exists`). Permite
preparar el esquema desde código sin depender de la CLI de Supabase.

Acciones Principales:
    - `apply_migrations`: aplica todos los `.sql` en orden y devuelve los nombres.

Entradas / Dependencias:
    - `asyncpg`; `DATABASE_URL` (o DSN explícito).

Salidas / Efectos:
    - Crea/actualiza el esquema en la BD del usuario.

Ejecución:
    uv run python -m backend.db.migrate
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

MIGRATIONS_DIR: Path = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


async def apply_migrations(dsn: str | None = None) -> list[str]:
    """
    Aplica en orden todas las migraciones `.sql` y devuelve sus nombres.

    Args:
        dsn (str | None): Cadena de conexión; por defecto toma `DATABASE_URL` del entorno.

    Returns:
        list[str]: Nombres de los archivos de migración aplicados.
    """
    load_dotenv()
    dsn = dsn or os.environ["DATABASE_URL"]
    applied: list[str] = []
    conn = await asyncpg.connect(dsn=dsn, timeout=30)
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    finally:
        await conn.close()
    return applied


def main() -> None:
    """Punto de entrada CLI: aplica las migraciones y reporta el resultado."""
    applied = asyncio.run(apply_migrations())
    print("Migraciones aplicadas:", ", ".join(applied) or "(ninguna)")


if __name__ == "__main__":
    main()
