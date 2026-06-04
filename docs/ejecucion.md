# Guía de Ejecución y Despliegue: AgroVisión (Plataforma)

> **Proyecto:** AgroVisión — UI Shiny (6 módulos) + backend FastAPI (monolito modular).
> **Fecha de Actualización:** 2026-06-03
> **Objetivo:** Runbook para clonar, levantar el entorno local y (a futuro) desplegar la plataforma sin fricciones.
>
> **Módulos de la UI (6):** Resumen de Campo · Creación de Parcelas · Teledetección · **Conteo por Dron (EN DESARROLLO)** · Asistente Agéntico · Credenciales.
>
> **La app abre SIN credenciales** (verás los 6 módulos). Para *usar* cada módulo necesitas las llaves BYOK (todas de capa gratuita), que pones en `.env` (local) o en la pestaña **Credenciales** (sesión):
> - **Parcelas / Teledetección / Resumen** → Supabase (`DATABASE_URL`) y, para NDVI, **Copernicus** (`DEV_COPERNICUS_CLIENT_ID/SECRET`). El clima (Open-Meteo) no necesita llave.
> - **Asistente** → **Groq** (`DEV_GROQ_API_KEY`).
> - **Conteo** → **EN DESARROLLO** (standby): la pestaña muestra *"Módulo en preparación"*. Se habilita cuando el [repo del modelo](reference/description_proyecto_modelo_conteo_plantas.md) publique el artefacto. Para demostrar el flujo con datos de prueba (mock) — ver §3.5.

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

### 2.2 Dependencias del Frontend

No aplica: la UI es **Shiny for Python** (mismo entorno de `uv`, sin Node/pnpm).

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
.\scripts\build_ui.ps1
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

1. [ ] Abrir `http://127.0.0.1:8001` y ver la UI con sus **6 pestañas** (Resumen, Creación de Parcelas, Teledetección, Conteo, Asistente, Credenciales).
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
docker compose up --build    # api en :8000, ui en :8001
```

> Para activar el conteo real en la imagen del backend, descomenta el bloque `hf_hub_download` en `backend/Dockerfile` y pon `COUNTING_ENABLED=true`, `MODEL_BACKEND=onnx`.

---

## 5. Despliegue en Producción / Cloud (a futuro)

> El conteo permanece **en desarrollo (standby)** hasta publicar el modelo; la app se despliega igual.

### 5.1 Pre-vuelo

> [!IMPORTANT]
> - Verifica `uv run ruff check .` y `uv run python -m pytest` en verde antes de desplegar.
> - No se versionan secretos: configúralos en el panel de cada plataforma.

### 5.2 Configuración del Entorno de Despliegue

```bash
# UI -> ShinyApps.io (token desde https://www.shinyapps.io/admin/#/tokens)
uv run rsconnect add --account <cuenta> --name <cuenta> --token <TOKEN> --secret <SECRET>
```

### 5.3 Ejecución del Despliegue

```bash
# UI (Shiny) -> ShinyApps.io
uv run rsconnect deploy shiny ./frontend --name <cuenta> --title AgroVision-MVP

# Backend -> Render (detecta backend/Dockerfile vía render.yaml)
#   Conecta el repo en el panel de Render o usa la API con RENDER_API_KEY.
```

### 5.4 Verificación Post-Despliegue

- [ ] URL pública de la UI accesible vía HTTPS.
- [ ] `https://<backend-en-render>/api/status` responde `200`.
- [ ] CORS entre la UI (ShinyApps.io) y el backend (Render) configurado (`ALLOWED_ORIGINS`).
- [ ] Recargar la UI (F5) no rompe la sesión (Shiny es ASGI nativo en ShinyApps.io).

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
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'uvicorn' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
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
