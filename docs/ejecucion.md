# Guía de Ejecución y Despliegue: AgroVisión MVP

> **Proyecto:** `agrovision-mvp` (UI Shiny + backend FastAPI)
> **Fecha de Actualización:** 2026-06-03
> **Objetivo:** Runbook para clonar, levantar el entorno local y (a futuro) desplegar el MVP sin fricciones.
>
> **Estado del conteo:** el módulo de **conteo de plantas está EN DESARROLLO** (standby). La app abre y funciona; la pestaña de Conteo muestra el aviso *"Módulo en preparación"*. El conteo real se habilita cuando el [repo del modelo](reference/description_proyecto_modelo_conteo_plantas.md) publique el artefacto. Para **demostrar el flujo** hay un modo *mock* (datos de prueba) — ver §3.5.

---

## 1. Requisitos Previos

### 1.1 Software y Herramientas

| Software | Versión Mínima | Comando de Verificación |
|----------|----------------|-------------------------|
| Python   | 3.11+ (probado 3.13) | `python --version` |
| uv       | 0.4+ (probado 0.9) | `uv --version` |
| Git      | 2.30+ | `git --version` |

> No se requiere Docker para el desarrollo local (se ejecuta con `uv`). Docker es opcional (ver §4).

### 1.2 Cuentas y Accesos

Solo necesarias **a futuro** para desplegar o activar el conteo real (no para correr en local):

- **ShinyApps.io**: cuenta + token (deploy de la UI).
- **Render**: cuenta (deploy del backend).
- **Supabase**: proyecto (plataforma completa: BD/Storage/Colas).
- **Hugging Face Hub**: token (descargar el modelo de conteo cuando se publique).

Las variables para estos servicios ya están declaradas (vacías) en `.env.example`.

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

### 3.1 Opción A: Script Automatizado (Recomendado)

```powershell
# Levanta backend (:8000) y UI (:8001) en ventanas separadas
.\scripts\dev.ps1
```

### 3.2 Opción B: Ejecución Manual (Modo Detallado)

> Se usa `python -m uvicorn` (no los shims `uvicorn.exe`/`shiny.exe`, que OneDrive bloquea).
> La app Shiny es ASGI, por lo que `uvicorn frontend.app:app` equivale a `shiny run frontend/app.py`.

**Terminal 1 — Backend / API:**
```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — UI (Shiny):**
```powershell
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
uv run python -m uvicorn frontend.app:app --host 127.0.0.1 --port 8001 --reload
```

### 3.3 Puertos y Accesos Locales

- **UI (Shiny)**: `http://127.0.0.1:8001`
- **Backend / API**: `http://127.0.0.1:8000`
- **Healthcheck**: `http://127.0.0.1:8000/api/status`
- **Documentación API (Swagger)**: `http://127.0.0.1:8000/docs`

### 3.4 Checklist de Verificación Rápida (Sanity Check)

1. [ ] Abrir `http://127.0.0.1:8001` y ver la UI con sus 2 pestañas (Conteo, Credenciales).
2. [ ] La pestaña **Conteo** muestra el aviso *"Módulo en preparación (standby)"*.
3. [ ] La pestaña **Credenciales** muestra el aviso de efimeralidad; al recargar (F5) los campos quedan vacíos.
4. [ ] `curl http://127.0.0.1:8000/api/status` responde `200` con `"counting_enabled": false`.

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
| Puerto en uso | Otro proceso ocupa 8000/8001 | Cambiar `--port` o cerrar el proceso. |

---

## 7. Ejecución de Tests

```bash
# Suite completa (unitarias + integración)
uv run python -m pytest

# Calidad de código
uv run ruff check .
uv run ruff format --check backend frontend tests scripts

# Solo E2E (Playwright; omitidas por defecto hasta habilitar el conteo)
uv run python -m pytest tests/e2e -v
```

> Nota: se usa `python -m pytest` (no el shim `pytest.exe`) por el tema de OneDrive descrito en §6.
