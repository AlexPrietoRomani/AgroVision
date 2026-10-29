# Fase 8 — Plantilla .env.example Documentada con Ejemplos y Guías Paso a Paso

## [X] Fase 8 — Plantilla .env.example Documentada con Ejemplos y Guías Paso a Paso


<!-- indice-fase:inicio -->

> **Índice de la Fase:**
- [X] SF8.1 — Rediseño Pedagógico de `.env.example` y Tests de Plantilla
  - [X] T8.1.1 — Documentar paso a paso con ejemplos de formato `.env.example` y crear `tests/unit/test_env_example.py`

<!-- indice-fase:fin -->

- **Objetivo:** Mejorar `.env.example` y `docs/ejecucion.md` para explicar qué credenciales se necesitan realmente en cada escenario (uso BYOK en `https://alexp97-agrovision.hf.space` vs desarrollo local), incluyendo para cada variable un **ejemplo de formato realista** (dummy seguro) y la **ruta exacta clic por clic** dentro de cada plataforma (Supabase, Copernicus CDSE, Groq, Hugging Face) para obtenerla.
- **Entregable global:** `.env.example` rediseñado con ejemplos y rutas paso a paso, actualización de `docs/ejecucion.md` y suite de validación `tests/unit/test_env_example.py`.
- **AC global de la Fase:**
  - [X] `.env.example` documenta en detalle cómo obtener `DATABASE_URL` en Supabase (botón superior **Connect** -> pestaña **Connection String** -> **Transaction pooler** o **Session pooler** -> copiar URI y anteponer `postgresql+asyncpg://`), junto con `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `SUPABASE_SERVICE_ROLE_KEY` (**Project Settings -> Data API / API Keys**).
  - [X] Cada variable de Supabase, Copernicus CDSE, Groq y Hugging Face incluye un ejemplo de formato explícito en comentarios y los pasos exactos para llegar al valor en la web oficial.
  - [X] `.env.example` explica con claridad qué variables son **obligatorias por sesión del usuario (BYOK)** y cuáles son opcionales o de desarrollo local.
  - [X] `tests/unit/test_env_example.py` valida que todas las claves requeridas, ejemplos de formato y guías paso a paso existan en `.env.example` sin exponer secretos reales.
- **Tests de la Fase:**
  - **Test Unitario:** `uv run python -m pytest tests/unit/test_env_example.py -q`.
  - **Test de Simulación de Usuario:** Verificación de carga de `.env.example` con `dotenv_values` comprobando que ninguna clave tenga secretos reales y que todas las secciones estén documentadas.

---

### [X] SF8.1 — Rediseño Pedagógico de `.env.example` y Tests de Plantilla

- **Objetivo:** Documentar exhaustivamente `.env.example` y `docs/ejecucion.md` con ejemplos de formato y rutas de navegación en cada consola cloud.
- **Entregable:** `.env.example`, `docs/ejecucion.md` y `tests/unit/test_env_example.py`.
- **AC de la Sub fase:**
  - [X] `.env.example` incluye instrucciones paso a paso y ejemplos de formato para Supabase (`DATABASE_URL` vía Connect -> Transaction/Session Pooler, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`), Copernicus (`DEV_COPERNICUS_CLIENT_ID`, `DEV_COPERNICUS_CLIENT_SECRET`), Groq (`DEV_GROQ_API_KEY`) y Hugging Face (`HF_SPACE_ID`, `HF_TOKEN`).
  - [X] `tests/unit/test_env_example.py` pasa al 100%.
- **Tests de la Sub fase:**
  - **Test Unitario:** `uv run python -m pytest tests/unit/test_env_example.py -q`.
  - **Test de Simulación de Usuario:** `uv run ruff check .`.

#### [X] T8.1.1 — Documentar paso a paso con ejemplos de formato `.env.example` y crear `tests/unit/test_env_example.py`
- **Objetivo de la Tarea:** Reescribir los bloques de documentación de `.env.example` con ejemplos y cómo llegar a cada valor en Supabase, Copernicus, Groq y Hugging Face, y añadir `tests/unit/test_env_example.py`.
- **Entregable:** `.env.example`, `docs/ejecucion.md` y `tests/unit/test_env_example.py`.

> **🧠 Explicación:** En el modelo BYOK de AgroVisión, el usuario conecta su propia base de datos de Supabase (y llaves de Copernicus/Groq). Muchos usuarios dudan en Supabase entre la URL REST (`https://xyz.supabase.co`) y la cadena PostgreSQL (`DATABASE_URL`), o no saben que en la interfaz actual de Supabase la URI PostgreSQL está en el botón superior **Connect -> Connection String -> Transaction pooler / Session pooler**. Documentar el paso a paso exacto con ejemplos de formato evita errores de conexión.

> **💡 Cómo hacerlo (ejemplo):**
> ```ini
> # -----------------------------------------------------------------------------------
> # 6) Supabase (Base de Datos PostGIS del Usuario — BYOK o Local)
> #    ¿Qué necesitas realmente?
> #    - Para guardar parcelas, polígonos y series satelitales + auto-crear las tablas:
> #      SOLO necesitas `DATABASE_URL` (cadena de conexión PostgreSQL Pooler).
> #    - Cómo llegar a `DATABASE_URL` en la app de Supabase:
> #      1. Entra a tu proyecto en https://supabase.com/dashboard
> #      2. En la barra superior, haz clic en el botón "Connect" (al lado del nombre del proyecto).
> #      3. En la pestaña "Connection String", selecciona "URI" y Method: "Transaction pooler" (puerto 6543) o "Session pooler" (puerto 5432).
> #      4. Copia la URI, reemplaza [YOUR-PASSWORD] por la contraseña de tu BD y usa el prefijo postgresql+asyncpg://
> #      Ejemplo: DATABASE_URL=postgresql+asyncpg://postgres.abcdefghijklm:MiClaveSegura123@aws-0-us-east-1.pooler.supabase.com:5432/postgres
> # -----------------------------------------------------------------------------------
> ```

- **AC de la Tarea:**
  - [X] `.env.example` actualizado con ejemplos y rutas paso a paso para cada variable.
  - [X] `docs/ejecucion.md` sincronizado con la tabla de cómo llegar a cada credencial.
  - [X] `tests/unit/test_env_example.py` en verde.
- **Tests de la Tarea:**
  - **Test Unitario:** `uv run python -m pytest tests/unit/test_env_example.py -q`.
  - **Test de Simulación de Usuario:** `uv run ruff check .`.
