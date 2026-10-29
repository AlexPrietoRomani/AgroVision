# Fase 10 — UI de Credenciales Guiada y Auto-Conexión de Base de Datos BYOK

## [ ] Fase 10 — UI de Credenciales Guiada y Auto-Conexión de Base de Datos BYOK


<!-- indice-fase:inicio -->

> **Índice de la Fase:**
- [ ] SF10.1 — Modal y Panel de Credenciales con `DATABASE_URL`, Guías Paso a Paso y Auto-Carga de Parcelas
  - [ ] T10.1.1 — Actualizar `CredentialsModal.astro`, `AjustesPerfil.astro`, `app.js` y `test_ui_smoke.py`

<!-- indice-fase:fin -->

- **Objetivo:** Actualizar el modal de credenciales (`CredentialsModal.astro`), la pestaña de ajustes (`AjustesPerfil.astro`) y la lógica cliente (`frontend/src/scripts/app.js`) para que el usuario pueda ingresar la **URI de conexión PostgreSQL de su propio Supabase (`DATABASE_URL` — Direct / Transaction o Session Pooler)** con instrucciones desplegables paso a paso y ejemplos claros para cada credencial (Supabase, Copernicus, Groq), enviando `X-User-Database-Url` en cada petición y disparando al guardar la conexión/auto-migración (`POST /api/credentials/connect-db`) y la recarga inmediata de sus parcelas (`loadParcels()`).
- **Entregable global:** `CredentialsModal.astro`, `AjustesPerfil.astro`, `frontend/src/scripts/app.js` y `tests/e2e/test_ui_smoke.py` actualizados, con compilación limpia en `./scripts/build.sh`.
- **AC global de la Fase:**
  - [ ] `CredentialsModal.astro` y `AjustesPerfil.astro` incluyen el campo **Supabase Database URI (`DATABASE_URL` — Transaction / Session Pooler)** (`#cred-db-url` / `#cfg-db-url`) además de los campos opcionales de Supabase, Copernicus y Groq, con un bloque de ayuda (`<details>`) que explica paso a paso cómo obtener cada valor y muestra un ejemplo del formato.
  - [ ] `authHeaders()` en `frontend/src/scripts/app.js` envía `X-User-Database-Url` cuando el usuario ingresó su URI de base de datos, y `updateStatus()` envía `authHeaders()` a `./api/credentials/status` para reflejar en verde las llaves activas de la sesión.
  - [ ] Al hacer clic en **"Usar en esta sesión"** en el modal de credenciales (o guardar en Ajustes), si el usuario ingresó su `DATABASE_URL`, `app.js` invoca `POST /api/credentials/connect-db`: si la BD estaba vacía informa que se creó la arquitectura automáticamente, y si ya tenía parcelas informa cuántas parcelas se encontraron y recarga inmediatamente `loadParcels()` y el perfil.
  - [ ] `pnpm run check`, `./scripts/build.sh` y `tests/e2e/test_ui_smoke.py` pasan con 0 errores.
- **Tests de la Fase:**
  - **Test Unitario:** `cd frontend && pnpm run check` y `./scripts/build.sh`.
  - **Test de Simulación de Usuario:** `uv run python -m pytest tests/e2e/test_ui_smoke.py -q`.

---

### [ ] SF10.1 — Modal y Panel de Credenciales con `DATABASE_URL`, Guías Paso a Paso y Auto-Carga de Parcelas

- **Objetivo:** Incorporar el campo de conexión directa a la BD de Supabase del usuario (`#cred-db-url` / `#cfg-db-url`), las ayudas paso a paso con ejemplos en la UI, y el flujo de auto-conexión y recarga de datos en `app.js`.
- **Entregable:** `frontend/src/components/ui/CredentialsModal.astro`, `frontend/src/components/modules/AjustesPerfil.astro`, `frontend/src/scripts/app.js` y `tests/e2e/test_ui_smoke.py`.
- **AC de la Sub fase:**
  - [ ] Existen `#cred-db-url` en `CredentialsModal.astro` y `#cfg-db-url` en `AjustesPerfil.astro` con ejemplos de formato (`postgresql://postgres.<ref>:<password>@aws-0-...pooler.supabase.com:5432/postgres`) y guía paso a paso (**Connect -> Connection String -> Transaction/Session Pooler**).
  - [ ] `app.js` envía `X-User-Database-Url` en `authHeaders()`, consulta `./api/credentials/status` incluyendo `authHeaders()`, e invoca `./api/credentials/connect-db` + `loadParcels()` al guardar credenciales.
  - [ ] `tests/e2e/test_ui_smoke.py` verifica la presencia de `#cred-db-url` y las guías de ayuda en el bundle compilado.
- **Tests de la Sub fase:**
  - **Test Unitario:** `cd frontend && pnpm run check && cd .. && ./scripts/build.sh`.
  - **Test de Simulación de Usuario:** `uv run python -m pytest tests/e2e/test_ui_smoke.py -q`.

#### [ ] T10.1.1 — Actualizar `CredentialsModal.astro`, `AjustesPerfil.astro`, `app.js` y `test_ui_smoke.py`
- **Objetivo de la Tarea:** Añadir el campo `DATABASE_URL` y las ayudas paso a paso en `CredentialsModal.astro` y `AjustesPerfil.astro`, conectar `X-User-Database-Url` y `POST /api/credentials/connect-db` en `frontend/src/scripts/app.js`, compilar el bundle y actualizar `tests/e2e/test_ui_smoke.py`.
- **Entregable:** `frontend/src/components/ui/CredentialsModal.astro`, `frontend/src/components/modules/AjustesPerfil.astro`, `frontend/src/scripts/app.js` y `tests/e2e/test_ui_smoke.py`.

> **🧠 Explicación:** Cuando el usuario entra a `https://alexp97-agrovision.hf.space`, la aplicación aún no sabe a qué base de datos conectarse. Al abrir **Credenciales**, pegar su URI de Supabase (**Connect -> Transaction/Session Pooler**) y pulsar **"Usar en esta sesión"**, el frontend envía `X-User-Database-Url` a `POST /api/credentials/connect-db`, el backend prepara las tablas si la BD es nueva o detecta las parcelas existentes, y el frontend llama a `loadParcels()` para dibujar inmediatamente sus lotes en el mapa.

> **💡 Cómo hacerlo (ejemplo):**
> ```javascript
> function authHeaders() {
>   const h = {};
>   if (creds.groq) h["X-User-Groq-Key"] = creds.groq;
>   if (creds.copId) h["X-User-Copernicus-Id"] = creds.copId;
>   if (creds.copSecret) h["X-User-Copernicus-Secret"] = creds.copSecret;
>   if (creds.dbUrl) h["X-User-Database-Url"] = creds.dbUrl;
>   if (creds.sbUrl) h["X-User-Supabase-Url"] = creds.sbUrl;
>   if (creds.sbKey) h["X-User-Supabase-Key"] = creds.sbKey;
>   return h;
> }
> ```

- **AC de la Tarea:**
  - [ ] `CredentialsModal.astro` y `AjustesPerfil.astro` actualizados con `#cred-db-url`, `#cfg-db-url`, ejemplos y guía paso a paso.
  - [ ] `frontend/src/scripts/app.js` conecta `creds.dbUrl`, `X-User-Database-Url`, `POST /api/credentials/connect-db` y recarga `loadParcels()`.
  - [ ] `./scripts/build.sh` y `tests/e2e/test_ui_smoke.py` en verde.
- **Tests de la Tarea:**
  - **Test Unitario:** `cd frontend && pnpm run check && cd .. && ./scripts/build.sh`.
  - **Test de Simulación de Usuario:** `uv run python -m pytest tests/e2e/test_ui_smoke.py -q`.
