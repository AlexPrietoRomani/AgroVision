# Guía de Ejecución y Despliegue: AgroVisión (Plataforma)

> **Proyecto:** AgroVisión — UI **Astro + Tailwind** (6 módulos) servida por el backend **FastAPI** (monolito modular). *(Shiny queda como legacy en `:8001`.)*
> **Fecha de Actualización:** 2026-06-03
> **Objetivo:** Runbook para clonar, levantar el entorno local y (a futuro) desplegar la plataforma sin fricciones.
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

A futuro, para **desplegar**: ShinyApps.io (UI) + Render (backend) + Supabase (BD); y Hugging Face Hub para el modelo de conteo cuando se publique. Todas las variables están declaradas en `.env.example`.

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
- Los tokens de despliegue (ShinyApps/Render/Supabase/HF) se completan solo cuando toque desplegar.

---

## 3. Ejecución en Desarrollo

> **UI = Astro (Fase 8).** La UI principal es **Astro + Tailwind**, compilada a estático y **servida por el gateway FastAPI en `/`**. El Shiny (`backend/dashboard:app`) queda como *legacy* (`:8001`). Para desarrollo de UI con hot-reload se usa el dev server de Astro (`:4321`) que proxea `/api` al gateway.

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
Abre **http://localhost:4321/**. *(UI Shiny legacy, opcional: `.\scripts\run_ui.ps1` en `:8001`.)*

### 3.3 Puertos y Accesos Locales

- **UI (Astro, vía gateway)**: `http://127.0.0.1:8000/`
- **UI (Astro dev, hot-reload)**: `http://localhost:4321/`
- **Backend / API**: `http://127.0.0.1:8000/api/...`
- **Healthcheck**: `http://127.0.0.1:8000/api/status`
- **Documentación API (Swagger)**: `http://127.0.0.1:8000/docs`
- **UI Shiny legacy**: `http://127.0.0.1:8001`

### 3.4 Checklist de Verificación Rápida (Sanity Check)

1. [ ] Abrir `http://127.0.0.1:8000/` y ver la UI Astro con sus **6 pestañas** (Resumen, Creación de Parcelas, Teledetección, Conteo, Asistente, Credenciales).
2. [ ] `curl http://127.0.0.1:8000/api/status` responde `200` con `"counting_enabled": false`.
3. [ ] La pestaña **Conteo** muestra *"Módulo en desarrollo (standby)"*.
4. [ ] La pestaña **Credenciales** muestra el aviso de efimeralidad; al recargar (F5) los campos quedan vacíos.
5. [ ] (Con `DATABASE_URL` + Copernicus configurados) **Creación de Parcelas**: dibujar un polígono, nombrarlo y *Guardar* → aparece en la lista; tras unos segundos, en **Teledetección** se ve la serie NDVI de 5 años.
6. [ ] (Con Groq) **Asistente**: preguntar *"¿cómo evolucionó el NDVI de \<parcela\>?"* → responde citando la herramienta usada.

> **Pruebas en vivo del backend** (sin la UI): `http://127.0.0.1:8000/docs` (Swagger) lista `/api/fields`, `/api/ndvi`, `/api/ndvi/raster`, `/api/weather`, `/api/chat`. Recuerda aplicar migraciones (`uv run python -m backend.db.migrate`) antes de usar parcelas.

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

> Para activar el conteo real en la imagen del backend, descomenta el bloque `hf_hub_download` en `backend/Dockerfile` y pon `COUNTING_ENABLED=true`, `MODEL_BACKEND=onnx`.

---

## 5. Despliegue en Producción / Cloud (a futuro)

> El conteo permanece **en desarrollo (standby)** hasta publicar el modelo; la app se despliega igual.

### 5.1 Pre-vuelo

> [!IMPORTANT]
> - Verifica `uv run ruff check .` y `uv run python -m pytest` en verde antes de desplegar.
> - No se versionan secretos: configúralos en el panel de cada plataforma.

### 5.2 Modelo de despliegue (Agro-Stack)

Un solo servicio: el **gateway FastAPI** (`backend.main:app`) sirve la **UI Astro compilada** en `/`, la **API** en `/api` y (opcional) el Shiny legacy en `/shiny`. Se despliega a **ShinyApps.io** con `rsconnect` (como app ASGI), aplicando la **Regla de Oro** (JS inline + rutas relativas vía `scripts/inline_js.py`).

Registrar el token (una vez):
```powershell
uv run rsconnect add --account <cuenta> --name <cuenta> --token <TOKEN> --secret <SECRET>
```

### 5.3 Ejecución del Despliegue (script)

```powershell
# Primer deploy (crea la app en ShinyApps.io):
.\scripts\deploy_prod.ps1 -Name <cuenta>
# Redeploy (cuando ya exista el app-id):
.\scripts\deploy_prod.ps1 -Name <cuenta> -AppId <id>
```
`deploy_prod.ps1` hace: (0) compila la UI (`build.ps1`), (1) genera `requirements.txt` (`uv export`), (2) traduce `.rscignore` a flags `--exclude`, (3) `rsconnect deploy shiny . --entrypoint backend.main:app`. Parámetros (`-Name`, `-AppId`) y pasos al detalle en **§8.5**.

> **BYOK / seguridad:** el `.env` **NO** viaja en el bundle (está en `.rscignore`); en producción las llaves las pone el usuario por sesión (cabeceras `X-User-*`).
> **Aún no hay app-id** para AgroVisión: el primer deploy con `-Name` lo crea; luego reutiliza el id con `-AppId` para redeploy.
> **Alternativa:** backend en **Render** con `backend/Dockerfile` (etapa Node compila Astro y el gateway sirve `/`).

### 5.4 Verificación Post-Despliegue

- [ ] URL pública accesible vía HTTPS; `/` carga la UI Astro.
- [ ] `https://<app>/api/status` responde `200`.
- [ ] Recargar (F5) no rompe la app: la SPA usa **hash-routing** + **rutas relativas** (Regla de Oro), así que el slug dinámico de ShinyApps no produce 404.
- [ ] Las credenciales se ingresan en la pestaña *Credenciales* (BYOK; no hay secretos en el bundle).

---

## 6. Troubleshooting (Solución de Problemas Frecuentes)

| Problema / Mensaje de Error | Causa Probable | Solución / Workaround |
|-----------------------------|----------------|-----------------------|
| `failed to hardlink ... os error 396` / lock al instalar | `.venv` dentro de carpeta OneDrive | Crear el venv fuera: `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\agrovision-venv"`; `link-mode=copy` ya está en `pyproject.toml`. |
| `Failed to spawn: uvicorn/shiny/pytest` (`os error 5`) | Los shims `.exe` se bloquean en OneDrive | Usar la forma de módulo: `uv run python -m uvicorn ...` / `uv run python -m pytest`. |
| UI muestra "backend no disponible" | El backend (:8000) no está arriba | Levantar primero el backend o usar `.\scripts\dev.ps1`. |
| `POST /api/count` devuelve `503` | Conteo en standby (esperado) | Es el comportamiento en desarrollo. Para probar: `COUNTING_ENABLED=true` + `MODEL_BACKEND=mock` (§3.5). |
| `[WinError 10013]` al arrancar (bind) | El puerto (8000/8001) **ya está ocupado** por otro proceso (típico: un `uvicorn` previo que quedó vivo). En Windows esto se reporta como **10013 (acceso denegado)**, no como 10048 (en uso). | Liberar el puerto (ver **§6.1**) o usar otro `--port`. |

### 6.1 Liberar un puerto ocupado (WinError 10013 en Windows)

`[WinError 10013] Intento de acceso a un socket no permitido por sus permisos de acceso` al arrancar **no es un problema de permisos ni de rangos reservados**: el puerto ya está tomado en exclusiva por otro proceso (casi siempre un `uvicorn` anterior con `--reload` que no se cerró). Para liberarlo:

```powershell
# 1) Ver qué ocupa el puerto (el PID es la última columna)
netstat -ano | findstr :8000        # usa :8001 para la UI

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
| `run_ui.ps1` | UI **Shiny legacy** (`:8001`) | `.\scripts\run_ui.ps1` |
| `dev.ps1` | Levanta **backend + Astro dev** en 2 ventanas | `.\scripts\dev.ps1` |
| `build.ps1` | Compila la UI Astro → `backend/static` | `.\scripts\build.ps1` |
| `deploy_prod.ps1` | Despliega a ShinyApps.io (Agro-Stack) | `.\scripts\deploy_prod.ps1 -Name <cuenta> [-AppId <id>]` |
| `inline_js.py` | Post-proceso del HTML (lo invoca `build.ps1`) | *(automático; ver abajo)* |
| `make_sample_orthomosaic.py` | Genera ortomosaico mock para el conteo | `uv run python scripts/make_sample_orthomosaic.py` |

> Si ves un error de *execution policy* al lanzar un `.ps1`, ábrelo así en esa sesión:
> `powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1`

### 8.1 `build.ps1` — compilar la UI (Astro → `backend/static`)

Pipeline de 3 pasos que deja la UI lista para que el gateway la sirva en `/`:

1. **`pnpm install` + `pnpm build`** en `frontend/` (aborta si `pnpm build` falla).
2. **`inline_js.py`** → inyecta el JS inline y relativiza rutas de assets (Regla de Oro, para que funcione bajo el sub-path de ShinyApps).
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

### 8.4 `run_ui.ps1` — Shiny legacy (`:8001`)

Levanta la UI **Shiny** antigua (`backend.dashboard:app`) en `:8001`. Desde la Fase 8 la UI principal es Astro; esto queda sólo como referencia/legacy.

```powershell
.\scripts\run_ui.ps1          # -> http://127.0.0.1:8001
```

### 8.5 `deploy_prod.ps1` — despliegue a ShinyApps.io (Agro-Stack)

Despliega el repo como una app ASGI cuyo entrypoint es el **gateway** (`backend.main:app`). Pasos:

0. **`build.ps1`** (compila la UI a `backend/static`).
1. **`uv export --no-dev --no-hashes --no-emit-project -o requirements.txt`** (ShinyApps instala desde `requirements.txt`, no usa `uv`).
2. Traduce cada línea de **`.rscignore`** a flags `--exclude` (rsconnect-python no lee `.rscignore` solo).
3. **`rsconnect deploy shiny . --entrypoint backend.main:app --name <cuenta> [--app-id <id>] @exclude`**.

**Parámetros:**

| Parámetro | Obligatorio | Descripción |
|-----------|:-----------:|-------------|
| `-Name <cuenta>` | **Sí** | Tu cuenta/destino de ShinyApps.io. Sin él (queda el placeholder), el script **avisa y sale** sin desplegar. |
| `-AppId <id>` | No | Vacío = **primer deploy** (crea la app). Una vez creada, reutiliza el id para **redeploy**. |

```powershell
# 0) (Una sola vez) registrar el token de ShinyApps:
uv run rsconnect add --account <cuenta> --name <cuenta> --token <TOKEN> --secret <SECRET>

# 1) Primer deploy (crea la app y devuelve su app-id):
.\scripts\deploy_prod.ps1 -Name <cuenta>

# 2) Redeploy (cuando ya tengas el app-id):
.\scripts\deploy_prod.ps1 -Name <cuenta> -AppId <id>
```

> **BYOK / seguridad:** `.env` está en `.rscignore`, así que **no viaja** en el bundle; en producción las llaves las pone el usuario por sesión (cabeceras `X-User-*`). Lo que **sí** va: `backend/` (incl. `backend/static`), `pyproject.toml`, `uv.lock`, `requirements.txt` y `.env.example`.
> **Aún no hay app-id** para AgroVisión: el primer deploy con `-Name` lo crea; guárdalo para los redeploys con `-AppId`.

### 8.6 `inline_js.py` — post-proceso del HTML (auxiliar)

No se llama a mano normalmente (lo invoca `build.ps1`). Reescribe `frontend/dist/index.html` *in place*: inyecta inline cualquier `/_astro/*.js`, y relativiza rutas absolutas (favicon, assets) para que la SPA funcione bajo el sub-path dinámico de ShinyApps. Es **idempotente**. Ejecutarlo suelto (depurar): `uv run python scripts/inline_js.py` (requiere haber hecho `pnpm build` antes).
