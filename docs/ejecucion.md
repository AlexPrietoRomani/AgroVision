# Guía de Ejecución y Despliegue: AgroVisión (Plataforma)

> **Proyecto:** AgroVisión — UI **Astro + Tailwind** (6 módulos) servida por el backend **FastAPI** (monolito modular). *(Shiny se eliminó en la Fase 10.)*
> **Fecha de Actualización:** 2026-06-04
> **Objetivo:** Runbook para clonar, levantar el entorno local y desplegar la plataforma sin fricciones (el pipeline de despliegue ya está automatizado — ver §5).
>
> **Módulos de la UI (6):** Resumen de Campo · Creación de Parcelas · Teledetección · **Conteo por Dron (EN DESARROLLO)** · Asistente Agéntico · Credenciales.
>
> **La app abre SIN credenciales** (verás los 6 módulos). Para *usar* cada módulo necesitas las llaves BYOK (todas de capa gratuita), que pones en `.env` (local) o en la pestaña **Credenciales** (sesión):
> - **Parcelas / Teledetección / Resumen** → Supabase (`DATABASE_URL`) y, para NDVI, **Copernicus** (`DEV_COPERNICUS_CLIENT_ID/SECRET`). El clima (Open-Meteo) no necesita llave.
> - **Asistente** → **Groq** (`DEV_GROQ_API_KEY`).
> - **Conteo** → **EN DESARROLLO** (standby): la pestaña muestra *"Módulo en preparación"*. Se habilita cuando el **repo del modelo** (proyecto separado) publique el artefacto. Para demostrar el flujo con datos de prueba (mock) — ver §3.5.

---

## 1. Requisitos Previos

### 1.1 Software y Herramientas

| Software | Versión Mínima | Comando de Verificación |
|----------|----------------|-------------------------|
| Python   | 3.11+ (probado 3.13) | `python --version` |
| uv       | 0.4+ (probado 0.9) | `uv --version` |
| Git      | 2.30+ | `git --version` |

> No se requiere Docker para el desarrollo local (se ejecuta con `uv`). Docker es opcional (ver §4).

### 1.2 Cuentas y Accesos (BYOK, capa gratuita)

Para **abrir** la app no necesitas nada. Para **usar** cada módulo en local, crea estas cuentas gratuitas y pon sus llaves en `.env`:

| Servicio | Habilita | Cómo obtenerlo | Variable(s) en `.env` |
|----------|----------|----------------|------------------------|
| **Supabase** (BD PostGIS) | Parcelas, Teledetección, Resumen | Crea proyecto → Settings (API + Database). Usa el **Session pooler** para `DATABASE_URL` (IPv4). | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` |
| **Copernicus CDSE** | NDVI satelital + heatmap | dataspace.copernicus.eu → OAuth client (id/secret) | `DEV_COPERNICUS_CLIENT_ID`, `DEV_COPERNICUS_CLIENT_SECRET` |
| **Groq** | Asistente Agéntico (RAG) | console.groq.com/keys (`gsk_...`) | `DEV_GROQ_API_KEY` |
| Open-Meteo | Clima | — (sin llave) | — |

**Migraciones de BD** (una vez, tras configurar `DATABASE_URL`): `uv run python -m backend.db.migrate` crea tablas, índices, RLS y la extensión PGMQ.

Para **desplegar** (ver §5): un único servicio (el **gateway FastAPI** que sirve UI + API) en **Hugging Face Spaces** (SDK Docker) vía `scripts/deploy_hf.ps1`; la BD es **Supabase**; y Hugging Face Hub alojará el modelo de conteo cuando se publique. Alternativas: **Render** (Docker) o **Posit Connect** (de pago). Todas las variables están en `.env.example`.

---

## 2. Instalación Local

### 2.1 Preparar Entorno Base

> ⚠️ **Windows + OneDrive:** la carpeta del repo está sincronizada por la nube, lo que rompe los *hardlinks* y bloquea el `.venv`. Crea el entorno **fuera** de OneDrive antes de instalar:
> ```powershell
> $env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
> ```
> (El `link-mode = "copy"` ya está fijado en `pyproject.toml`. Los scripts de §3.1 lo configuran solos.)

```bash
# Instalar dependencias (crea el entorno y el lockfile)
uv sync
```

### 2.2 Dependencias del Frontend (Astro)

La UI es **Astro + Tailwind** (Node/pnpm). Compílala a estático con:
```powershell
.\scripts\build.ps1        # = pnpm build + inline_js.py + copia a backend/static
```
El gateway sirve ese build en `/`. Para hot-reload usa `pnpm dev` (ver §3.2). Detalle de cada script y sus equivalentes manuales en **§8 (Referencia de Scripts)**.

### 2.3 Configuración de Variables de Entorno

```bash
# Copiar la plantilla a .env (local, no se versiona)
cp .env.example .env
```

- Para correr el MVP en local **no necesitas ningún secreto**: los valores por defecto bastan.
- `COUNTING_ENABLED=false` deja el conteo **en desarrollo** (standby).
- Los tokens de despliegue (Hugging Face/Render/Supabase) se completan solo cuando toque desplegar (§5).

---

## 3. Ejecución en Desarrollo

> **UI = Astro.** La UI es **Astro + Tailwind**, compilada a estático y **servida por el gateway FastAPI en `/`**. Para desarrollo de UI con hot-reload se usa el dev server de Astro (`:4321`) que proxea `/api` al gateway. *(Shiny se eliminó en la Fase 10.)*

### 3.1 Opción A: UI compilada servida por el gateway (lo más simple)

```powershell
# 1) Compilar la UI Astro -> backend/static (una vez, o tras cambios de UI)
.\scripts\build.ps1
# 2) Levantar el gateway (sirve la UI en / y la API en /api)
.\scripts\run_backend.ps1
```
Abre **http://127.0.0.1:8000/** → la UI completa (6 módulos).

### 3.2 Opción B: Desarrollo de UI con hot-reload (Astro dev)

> Dos terminales: el gateway (API) y el dev server de Astro (UI con recarga en vivo).

**Terminal 1 — Backend / API (`:8000`):**
```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
$env:PYTHONUNBUFFERED = "1"
uv run python -u -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --log-level info --reload-exclude ".venv" --reload-exclude "frontend" --reload-exclude "docs" --reload-exclude "tests" --reload-exclude "scripts" --reload-exclude "supabase" --reload-exclude "models" --reload-exclude "sample_data" --reload-exclude "scratch"
```

**Terminal 2 — UI Astro dev (`:4321`, proxea `/api` → `:8000`):**
```powershell
cd frontend
pnpm dev
```
Abre **http://localhost:4321/**.

### 3.3 Puertos y Accesos Locales

- **UI (Astro, vía gateway)**: `http://127.0.0.1:8000/`
- **UI (Astro dev, hot-reload)**: `http://localhost:4321/`
- **Backend / API**: `http://127.0.0.1:8000/api/...`
- **Healthcheck**: `http://127.0.0.1:8000/api/status`
- **Documentación API (Swagger)**: `http://127.0.0.1:8000/docs`

### 3.4 Checklist de Verificación Rápida (Sanity Check)

1. [ ] Abrir `http://127.0.0.1:8000/` y ver la UI Astro con sus **6 pestañas** (Resumen, Creación de Parcelas, Teledetección, Conteo, Asistente, Credenciales).
2. [ ] `curl http://127.0.0.1:8000/api/status` responde `200` con `"counting_enabled": false`.
3. [ ] La pestaña **Conteo** muestra *"Módulo en desarrollo (standby)"*.
4. [ ] La pestaña **Credenciales** muestra el aviso de efimeralidad; al recargar (F5) los campos quedan vacíos.
5. [ ] (Con `DATABASE_URL` + Copernicus configurados) **Creación de Parcelas**: dibujar un polígono, nombrarlo y *Guardar* → aparece en la lista; tras unos segundos, en **Teledetección** se ve la serie NDVI de 5 años.
6. [ ] (Con Groq) **Asistente**: preguntar *"¿cómo evolucionó el NDVI de \<parcela\>?"* → responde citando la herramienta usada.

> **Pruebas en vivo del backend** (sin la UI): `http://127.0.0.1:8000/docs` (Swagger) lista `/api/fields`, `/api/ndvi`, `/api/ndvi/raster`, `/api/weather`, `/api/chat` y `/api/events` (telemetría: `POST /api/events`, `GET /api/events/recent?session_id=`). Recuerda aplicar migraciones (`uv run python -m backend.db.migrate`) antes de usar parcelas.
>
> **Telemetría (Fase 9):** cada acción de la UI emite un evento (sin secretos) que se loguea en stdout y se guarda en un buffer en memoria, consultable en `GET /api/events/recent`. Para depurar una sesión: `GET /api/events/recent?session_id=<id>`. La persistencia en la tabla `events` es **opcional** (`EVENTS_PERSIST=true`).

### 3.5 (Opcional) Demostrar el Conteo con Datos Mock

Para ver el flujo completo (carga → conteo → overlay) **sin el modelo real**:

```bash
# 1) Generar un ortomosaico de arándano simulado
uv run python scripts/make_sample_orthomosaic.py     # -> sample_data/blueberry_demo.png

# 2) Activar el modo mock en .env
#    COUNTING_ENABLED=true
#    MODEL_BACKEND=mock
```
Reinicia el backend, ve a la pestaña **Conteo** (verás *"(datos de prueba / mock)"*), sube `sample_data/blueberry_demo.png` y obtendrás el overlay con cajas sobre los arbustos y el conteo. Vuelve a `COUNTING_ENABLED=false` para dejarlo en desarrollo.

---

## 4. Compilación y Build (Opcional)

El MVP no requiere transpilación. Como alternativa al arranque con `uv`, hay imágenes Docker:

```bash
docker compose up --build    # gateway en :8000 (sirve API + UI Astro compilada)
```

> Para activar el conteo real en la imagen, descomenta el bloque `hf_hub_download` en el `Dockerfile` (raíz) y pon `COUNTING_ENABLED=true`, `MODEL_BACKEND=onnx`.

---

## 5. Despliegue en Producción / Cloud

> **Destino elegido: Hugging Face Spaces (SDK Docker).** Es gratis, soporta FastAPI nativo vía Docker, da **16 GB de RAM** en CPU básica y no requiere tarjeta. HF construye el [`Dockerfile`](../Dockerfile) de la raíz (gateway FastAPI: UI Astro en `/` + API en `/api`) y lo sirve en el puerto `app_port` (8000) declarado en el `README.md`. El deploy es un `git push` al repo del Space ([`scripts/deploy_hf.ps1`](../scripts/deploy_hf.ps1)).
>
> ⚠️ **shinyapps.io NO sirve** para esta app: solo hospeda apps **Shiny** (R/Python), no FastAPI/ASGI. `rsconnect deploy fastapi` solo aplica a **Posit Connect** (de pago) — ver alternativas en §5.5.
>
> El conteo permanece **en desarrollo (standby)** hasta publicar el modelo; la app se despliega igual.

### 5.1 Pre-vuelo

> [!IMPORTANT]
> - Verifica `uv run ruff check .` y `uv run python -m pytest` en verde antes de desplegar.
> - No se versionan secretos: el modelo es **BYOK** (cada usuario pone sus llaves de datos por sesión; no hay secretos en la imagen).

### 5.2 Modelo de despliegue (Agro-Stack en HF Spaces)

Un solo servicio: el **gateway FastAPI** (`backend.main:app`) sirve la **UI Astro compilada** en `/` y la **API** en `/api`. El Space es un **repo git** en `huggingface.co/spaces/<usuario>/<space>`; al hacer `git push`, HF:
1. construye el `Dockerfile` de la raíz (multi-stage: Node compila Astro → Python/uv corre el gateway, como usuario `1000`);
2. arranca el contenedor escuchando en el puerto `app_port: 8000` (definido en el frontmatter del `README.md`);
3. expone la app en `https://<usuario>-<space>.hf.space`.

Cada `git push` posterior **reconstruye el mismo Space** (no manejas ids de app: HF detecta que es el mismo repo).

> **¿Qué se sube y qué se construye? (equivalente de `.rscignore`)** HF no tiene un flag `--exclude` como `rsconnect`; el Space *es un repo git*, así que se suben los archivos **versionados** (lo pesado ya lo filtra `.gitignore`: `.env`, `.venv`, `node_modules`, `frontend/dist`, `backend/static`, modelos, imágenes…). Lo que mantiene el **build/imagen** mínimos es **[`.dockerignore`](../.dockerignore)**: excluye del *build context* todo lo que el `Dockerfile` no usa (docs, tests, scripts, supabase, caches, `.git`…), dejando solo `frontend/`, `backend/`, `pyproject.toml` y `uv.lock`. → builds más rápidos e imagen sin basura.
> *(Si además quieres un repo de Space mínimo —sin docs/tests visibles—, se puede empujar un subárbol curado; hoy se sube el repo completo por simplicidad.)*

### 5.3 Preparación (una sola vez)

1. **Crea el Space** en la web: [huggingface.co/new-space](https://huggingface.co/new-space) → **SDK: Docker** → *Blank* → nómbralo (p. ej. `agrovision`).
2. **Token de escritura** en [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (tipo *Write*).
3. **Pon en tu `.env`** (no se versiona):
   ```bash
   HF_TOKEN=hf_xxxxxxxx                 # token write
   HF_SPACE_ID=<tu_usuario>/agrovision  # <usuario>/<space>
   ```

### 5.4 Ejecución del Despliegue (`deploy_hf.ps1`)

```powershell
# Primer deploy (sobrescribe el commit inicial del Space):
.\scripts\deploy_hf.ps1 -Force
# Despliegues siguientes (cada push reconstruye el Space):
.\scripts\deploy_hf.ps1
```

El script lee `HF_TOKEN`/`HF_SPACE_ID` del `.env`, arma la URL autenticada del Space y hace `git push HEAD:main`. **No compila en local** (HF construye el `Dockerfile` en su lado). Detalle en **§8.5**.

> **BYOK / seguridad:** el `.env` está en `.gitignore`, así que **no se sube** al Space; las `HF_TOKEN`/`HF_SPACE_ID` solo se usan **en tu máquina** para autenticar el push. Las llaves de datos (Supabase/Copernicus/Groq) las pone cada usuario por sesión (cabeceras `X-User-*`).
> **Migraciones (BYOK):** el Space no tiene BD propia; para la demo, aplica las migraciones contra **tu** Supabase (`uv run python -m backend.db.migrate`) y pega tus llaves en la pestaña *Credenciales*.

### 5.5 Verificación Post-Despliegue

- [ ] El build del Space termina en verde (pestaña *Logs* del Space).
- [ ] La URL pública (`https://<usuario>-<space>.hf.space/`) carga la UI Astro.
- [ ] `https://<usuario>-<space>.hf.space/api/status` responde `200`.
- [ ] Recargar (F5) no rompe la app (hash-routing + rutas relativas).
- [ ] Las credenciales se ingresan en la pestaña *Credenciales* (BYOK; no hay secretos en la imagen).

### 5.6 Alternativas de despliegue

- **Render** (Docker, free tier): usa el mismo [`Dockerfile`](../Dockerfile) (raíz) + [`render.yaml`](../render.yaml). Conectas el repo de GitHub y cada push redespliega. Duerme a los 15 min (cold start ~30–60 s) y da 512 MB de RAM.
- **Posit Connect** (de pago/enterprise): soporta FastAPI vía `rsconnect deploy fastapi --server <url> --api-key <key>`. El script `deploy_prod.ps1` (flujo rsconnect) **se eliminó en la Fase 10** por ser específico de shinyapps; si algún día hay un Connect disponible, se re-añade apuntándolo a ese servidor.

---

## 6. Troubleshooting (Solución de Problemas Frecuentes)

| Problema / Mensaje de Error | Causa Probable | Solución / Workaround |
|-----------------------------|----------------|-----------------------|
| `failed to hardlink ... os error 396` / lock al instalar | `.venv` dentro de carpeta OneDrive | Crear el venv fuera: `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\agrovision-venv"`; `link-mode=copy` ya está en `pyproject.toml`. |
| `Failed to spawn: uvicorn/pytest` (`os error 5`) | Los shims `.exe` se bloquean en OneDrive | Usar la forma de módulo: `uv run python -m uvicorn ...` / `uv run python -m pytest`. |
| UI muestra "backend no disponible" | El backend (:8000) no está arriba | Levantar primero el backend o usar `.\scripts\dev.ps1`. |
| `POST /api/count` devuelve `503` | Conteo en standby (esperado) | Es el comportamiento en desarrollo. Para probar: `COUNTING_ENABLED=true` + `MODEL_BACKEND=mock` (§3.5). |
| `[WinError 10013]` al arrancar (bind) | El puerto (8000/8001) **ya está ocupado** por otro proceso (típico: un `uvicorn` previo que quedó vivo). En Windows esto se reporta como **10013 (acceso denegado)**, no como 10048 (en uso). | Liberar el puerto (ver **§6.1**) o usar otro `--port`. |

### 6.1 Liberar un puerto ocupado (WinError 10013 en Windows)

`[WinError 10013] Intento de acceso a un socket no permitido por sus permisos de acceso` al arrancar **no es un problema de permisos ni de rangos reservados**: el puerto ya está tomado en exclusiva por otro proceso (casi siempre un `uvicorn` anterior con `--reload` que no se cerró). Para liberarlo:

```powershell
# 1) Ver qué ocupa el puerto (el PID es la última columna)
netstat -ano | findstr :8000        # o :4321 para el dev server de Astro

# 2) Identificar el proceso de ese PID
tasklist /FI "PID eq <PID>"

# 3) Matarlo (incluido su árbol de hijos)
taskkill /F /T /PID <PID>

# Atajo: matar TODOS los uvicorn del proyecto de una vez
Get-CimInstance Win32_Process -Filter "Name='python.exe'" Where-Object { $_.CommandLine -match 'uvicorn' } ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

> **Evita huérfanos:** cierra el servidor con **Ctrl+C** (o cierra su ventana); no lo dejes corriendo entre reinicios. `--reload` deja un proceso supervisor + worker, así que pueden acumularse si solo cierras la terminal a la fuerza. Alternativa rápida: arrancar en otro puerto (`--port 8010`). Verifica que quedó libre repitiendo el paso 1.

---

## 7. Ejecución de Tests

```bash
# Suite completa (unitarias + integración)
uv run python -m pytest

# Solo unitarias (rápidas, sin red ni credenciales)
uv run python -m pytest tests/unit -q

# Calidad de código
uv run ruff check .
uv run ruff format --check backend frontend tests scripts

# Solo E2E (Playwright; omitidas por defecto hasta habilitar el conteo)
uv run python -m pytest tests/e2e -v
```

> **Integración:** los tests de `tests/integration/` golpean servicios reales y **se omiten (skip) si faltan sus credenciales** en `.env`:
> - `test_db.py` → requiere `DATABASE_URL` (Supabase).
> - `test_teledeteccion.py` → requiere `DATABASE_URL` + Copernicus.
> - `test_agent.py` → requiere `DATABASE_URL` + Groq.
>
> Con todas las llaves puestas corren ~58 pruebas en verde. Se usa `python -m pytest` (no el shim `pytest.exe`) por el tema de OneDrive descrito en §6.

---

## 8. Referencia de Scripts (`scripts/`)

Todos los `.ps1` viven en `scripts/`, se ejecutan **desde la raíz del repo** (resuelven la raíz solos con `Split-Path -Parent $PSScriptRoot`, así que da igual desde dónde los llames) y fijan `UV_PROJECT_ENVIRONMENT` al venv fuera de OneDrive. Cada uno tiene su **equivalente manual** por si prefieres la terminal.

| Script | Para qué sirve | Uso típico |
|--------|----------------|------------|
| `run_backend.ps1` | Gateway FastAPI (`:8000`) con `--reload` | `.\scripts\run_backend.ps1` |
| `dev.ps1` | Levanta **backend + Astro dev** en 2 ventanas | `.\scripts\dev.ps1` |
| `build.ps1` | Compila la UI Astro → `backend/static` | `.\scripts\build.ps1` |
| `deploy_hf.ps1` | **Despliega a Hugging Face Spaces** (vía activa) | `.\scripts\deploy_hf.ps1 -Force` (primer deploy) |
| `inline_js.py` | Post-proceso del HTML (lo invoca `build.ps1`) | *(automático; ver abajo)* |
| `make_sample_orthomosaic.py` | Genera ortomosaico mock para el conteo | `uv run python scripts/make_sample_orthomosaic.py` |

> Si ves un error de *execution policy* al lanzar un `.ps1`, ábrelo así en esa sesión:
> `powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1`

### 8.1 `build.ps1` — compilar la UI (Astro → `backend/static`)

Pipeline de 3 pasos que deja la UI lista para que el gateway la sirva en `/`:

1. **`pnpm install` + `pnpm build`** en `frontend/` (aborta si `pnpm build` falla).
2. **`inline_js.py`** → inyecta el JS inline y relativiza rutas de assets (Regla de Oro; salvaguarda para sub-paths). *(En HF Spaces/Render se sirve en la raíz, así que no es imprescindible.)*
3. **Copia** `frontend/dist/*` → `backend/static/` (limpia el destino pero **preserva `.gitkeep`**).

```powershell
.\scripts\build.ps1
```

**Requisitos:** Node + `pnpm` instalados; `uv` (para el paso 2). No necesita credenciales.
**Cuándo:** tras cualquier cambio en `frontend/` que quieras ver servido por el gateway (`:8000`). Para iterar UI con recarga en vivo, usa el modo dev (§3.2) en vez de recompilar.

<details><summary>Equivalente manual</summary>

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
Set-Location frontend; pnpm install; pnpm build; Set-Location ..
uv run python scripts/inline_js.py
# copiar frontend\dist\* a backend\static\ (preservando .gitkeep)
Copy-Item -Path frontend\dist\* -Destination backend\static -Recurse -Force
```
</details>

### 8.2 `run_backend.ps1` — gateway FastAPI (`:8000`)

Hace `uv sync` y arranca `backend.main:app` con `--reload` y `--reload-exclude` por capa (no reinicia por cambios en `frontend/`, `docs/`, `tests/`, etc.). Sirve la **API** en `/api`, la **UI compilada** en `/` (si existe `backend/static/index.html`) y el **Swagger** en `/docs`.

```powershell
.\scripts\run_backend.ps1     # -> http://127.0.0.1:8000/
```

**Requisitos:** `uv`. Para *usar* los módulos, `.env` con las llaves BYOK (§1.2) y migraciones aplicadas (`uv run python -m backend.db.migrate`). Ciérralo con **Ctrl+C** para no dejar huérfanos (§6.1).

<details><summary>Equivalente manual</summary>

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
$env:UV_LINK_MODE = "copy"; $env:PYTHONUNBUFFERED = "1"
uv sync
uv run python -u -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --log-level info `
  --reload-exclude ".venv" --reload-exclude "frontend" --reload-exclude "docs" `
  --reload-exclude "tests" --reload-exclude "scripts" --reload-exclude "supabase" `
  --reload-exclude "models" --reload-exclude "sample_data" --reload-exclude "scratch"
```
</details>

### 8.3 `dev.ps1` — backend + Astro dev (hot-reload de UI)

Abre **dos ventanas PowerShell**: una con `run_backend.ps1` (`:8000`) y otra con `pnpm dev` en `frontend/` (Astro en `:4321`, que proxea `/api` → `:8000`). Es la forma cómoda de desarrollar UI: editas en `frontend/src/` y recarga en vivo, sin recompilar a `backend/static`.

```powershell
.\scripts\dev.ps1
```

**Requisitos:** `uv`, Node + `pnpm`. Trabaja en **http://localhost:4321/**. *(La UI compilada en `:8000` sólo refleja cambios tras `build.ps1`.)*

### 8.4 `inline_js.py` — post-proceso del HTML (auxiliar)

No se llama a mano normalmente (lo invoca `build.ps1`). Reescribe `frontend/dist/index.html` *in place*: inyecta inline cualquier `/_astro/*.js`, y relativiza rutas absolutas (favicon, assets) para que la SPA funcione bajo un sub-path dinámico. Es **idempotente**. Ejecutarlo suelto (depurar): `uv run python scripts/inline_js.py` (requiere haber hecho `pnpm build` antes). *(En HF Spaces y Render la app se sirve en la raíz del dominio, así que la "Regla de Oro" no es estrictamente necesaria; el script queda como salvaguarda.)*

### 8.5 `deploy_hf.ps1` — despliegue a Hugging Face Spaces (**vía activa**)

Publica el gateway en un **Docker Space**. No compila en local: hace `git push` del repo al Space y **HF construye el `Dockerfile`** de la raíz (multi-stage Astro→FastAPI, usuario `1000`, puerto `app_port: 8000` del `README.md`).

**Requisitos en `.env`** (no se versiona): `HF_TOKEN` (token *write*) y `HF_SPACE_ID` (`<usuario>/<space>`). El Space debe existir (créalo en la web con **SDK: Docker**). Ver §5.3.

| Parámetro | Obligatorio | Descripción |
|-----------|:-----------:|-------------|
| `-SpaceId <u/s>` | No | Id del Space. Si se omite, se toma de `HF_SPACE_ID` (`.env`). |
| `-Force` | No | Fuerza el push (necesario en el **primer** deploy: sobrescribe el commit inicial del Space). |

```powershell
.\scripts\deploy_hf.ps1 -Force   # primer deploy
.\scripts\deploy_hf.ps1          # siguientes (cada push reconstruye el Space)
```

> El token va en la URL solo durante el push (no se guarda como remote). El `.env` está en `.gitignore`, así que no se sube al Space. Tras el push, sigue el build en la pestaña *Logs* del Space (§5.5).
