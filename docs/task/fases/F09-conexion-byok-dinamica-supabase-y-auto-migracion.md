# Fase 9 — Conexión BYOK Dinámica a Supabase del Usuario y Auto-Migración de Esquema en Backend

## [ ] Fase 9 — Conexión BYOK Dinámica a Supabase del Usuario y Auto-Migración de Esquema en Backend


<!-- indice-fase:inicio -->

> **Índice de la Fase:**
- [ ] SF9.1 — Sesión Multi-DSN por Usuario y Auto-Bootstrap de Migraciones SQL
  - [ ] T9.1.1 — Soportar `X-User-Database-Url` dinámico, auto-migración idempotente y endpoint `POST /api/credentials/connect-db`

<!-- indice-fase:fin -->

- **Objetivo:** Lograr que AgroVisión en `https://alexp97-agrovision.hf.space` no dependa de ninguna base de datos global en el servidor: cada usuario se conecta con su propia base de datos Supabase por sesión (`X-User-Database-Url`), y si su base de datos está totalmente vacía, el backend ejecuta automáticamente las migraciones idempotentes (`0001_initial_schema.sql` + `0002_field_selected_indices.sql`) para construir toda la arquitectura PostGIS; si ya tiene la arquitectura y datos, los detecta y devuelve sus parcelas existentes.
- **Entregable global:** `backend/db/session.py` multi-DSN con `ensure_schema_initialized(dsn)`, `backend/api/deps.py` leyendo `X-User-Database-Url`, `backend/api/credentials.py` con `POST /api/credentials/connect-db` y `GET /api/credentials/status` consciente de headers BYOK, `backend/services/parcels.py` propagando el DSN del usuario al backfill en segundo plano, y suite de pruebas `tests/unit/test_byok_db_session.py`.
- **AC global de la Fase:**
  - [ ] `UserKeys` en `backend/api/deps.py` incluye `database_url: str | None` resuelto desde la cabecera `X-User-Database-Url` (con fallback a `DATABASE_URL` del entorno únicamente si no es el placeholder `<pwd>@<host>`).
  - [ ] `backend/db/session.py` cachea motores `AsyncEngine` y `async_sessionmaker` por DSN (`get_engine(dsn)` y `get_sessionmaker(dsn)`) y provee `ensure_schema_initialized(dsn: str) -> list[str]` que ejecuta `apply_migrations(dsn)` automáticamente una vez por DSN en memoria.
  - [ ] `get_db` en `backend/api/deps.py` usa el DSN del usuario (`keys.database_url`), ejecuta `await ensure_schema_initialized(dsn)` antes de abrir la primera sesión de ese DSN, y si no hay ningún DSN configurado lanza `HTTPException(status_code=503, detail=...)` claro indicando que conecte su base de datos Supabase en Credenciales.
  - [ ] `POST /api/credentials/connect-db` valida la conexión al DSN provisto (en body o cabecera `X-User-Database-Url`), ejecuta `ensure_schema_initialized(dsn)` para crear la arquitectura si la BD está vacía, cuenta cuántas parcelas existen en `public.fields` y retorna `{"connected": True, "schema_ready": True, "migrations_applied": [...], "existing_parcels": N}`.
  - [ ] `GET /api/credentials/status` considera tanto las cabeceras `X-User-*` de la sesión actual como las variables del entorno (ignorando placeholders `<pwd>@<host>`).
  - [ ] `run_indices_backfill` en `backend/services/parcels.py` abre su sesión con `get_sessionmaker(keys.database_url)()` para guardar los índices satelitales en la BD del usuario.
- **Tests de la Fase:**
  - **Test Unitario:** `uv run python -m pytest tests/unit/test_byok_db_session.py -q`.
  - **Test de Simulación de Usuario:** Simulación con `TestClient` de dos usuarios con distintos `X-User-Database-Url`, verificando auto-migración en primera conexión, aislamiento de sesiones y respuesta de `POST /api/credentials/connect-db`.

---

### [ ] SF9.1 — Sesión Multi-DSN por Usuario y Auto-Bootstrap de Migraciones SQL

- **Objetivo:** Implementar el enrutamiento dinámico de base de datos por usuario (`X-User-Database-Url`), la inicialización automática del esquema PostGIS cuando la BD del usuario es nueva y el endpoint de verificación/conexión `POST /api/credentials/connect-db`.
- **Entregable:** `backend/db/session.py`, `backend/api/deps.py`, `backend/api/credentials.py`, `backend/services/parcels.py`, `docs/architect/architecture_agrovision.md` y `tests/unit/test_byok_db_session.py`.
- **AC de la Sub fase:**
  - [ ] `get_engine(dsn)` y `get_sessionmaker(dsn)` soportan múltiples DSN por proceso sin mezclar conexiones entre distintos usuarios.
  - [ ] `ensure_schema_initialized(dsn)` aplica `0001_initial_schema.sql` y `0002_field_selected_indices.sql` automáticamente la primera vez que ve un DSN y lo marca en caché para no repetir DDL en cada request subsecuente.
  - [ ] `POST /api/credentials/connect-db` y `GET /api/credentials/status` funcionan con `X-User-Database-Url`.
  - [ ] Todos los tests existentes (`tests/unit/`) y los nuevos (`tests/unit/test_byok_db_session.py`) pasan al 100%.
- **Tests de la Sub fase:**
  - **Test Unitario:** `uv run python -m pytest tests/unit/test_byok_db_session.py -q`.
  - **Test de Simulación de Usuario:** `uv run python -m pytest tests/unit -q && uv run ruff check .`.

#### [ ] T9.1.1 — Soportar `X-User-Database-Url` dinámico, auto-migración idempotente y endpoint `POST /api/credentials/connect-db`
- **Objetivo de la Tarea:** Actualizar `backend/db/session.py`, `backend/api/deps.py`, `backend/api/credentials.py` y `backend/services/parcels.py` para conexión BYOK dinámica con auto-creación de arquitectura SQL, y crear `tests/unit/test_byok_db_session.py`.
- **Entregable:** `backend/db/session.py`, `backend/api/deps.py`, `backend/api/credentials.py`, `backend/services/parcels.py`, `docs/architect/architecture_agrovision.md` y `tests/unit/test_byok_db_session.py`.

> **🧠 Explicación:** En Hugging Face Spaces (`https://alexp97-agrovision.hf.space`), la aplicación es pública y multiusuario bajo el modelo BYOK. Si el contenedor no tiene `DATABASE_URL` global, cada usuario envía su propia cadena PostgreSQL de Supabase en `X-User-Database-Url`. Al conectar una base de datos recién creada en Supabase, `ensure_schema_initialized(dsn)` corre `apply_migrations(dsn)` automáticamente para crear PostGIS y todas las tablas; y cuando el usuario vuelve a entrar en otra sesión con la misma URI, las migraciones idempotentes (`IF NOT EXISTS`) respetan intactos sus datos y el endpoint reporta cuántas parcelas existentes tiene.

> **💡 Cómo hacerlo (ejemplo):**
> ```python
> # En backend/db/session.py:
> _INITIALIZED_DSNS: set[str] = set()
>
> def _is_valid_dsn(url: str | None) -> bool:
>     return bool(url and url.strip() and "<pwd>" not in url and "<host>" not in url)
>
> async def ensure_schema_initialized(dsn: str | None = None) -> list[str]:
>     resolved = _resolve_raw_url(dsn)
>     if resolved in _INITIALIZED_DSNS:
>         return []
>     applied = await apply_migrations(resolved)
>     _INITIALIZED_DSNS.add(resolved)
>     return applied
> ```

- **AC de la Tarea:**
  - [ ] `backend/db/session.py` soporta DSN dinámico por argumento y `ensure_schema_initialized(dsn)`.
  - [ ] `backend/api/deps.py` extrae `X-User-Database-Url` en `UserKeys.database_url` y lo usa en `get_db`.
  - [ ] `backend/api/credentials.py` expone `POST /api/credentials/connect-db` y actualiza `GET /api/credentials/status` para reconocer las cabeceras `X-User-*`.
  - [ ] `backend/services/parcels.py` pasa `keys.database_url` a `get_sessionmaker(keys.database_url)` en `run_indices_backfill`.
  - [ ] `tests/unit/test_byok_db_session.py` cubre resolución de DSN, rechazo de placeholders `<pwd>@<host>`, caché de `ensure_schema_initialized` y endpoint `POST /api/credentials/connect-db`.
- **Tests de la Tarea:**
  - **Test Unitario:** `uv run python -m pytest tests/unit/test_byok_db_session.py -q`.
  - **Test de Simulación de Usuario:** `uv run python -m pytest tests/unit -q && uv run ruff check .`.
