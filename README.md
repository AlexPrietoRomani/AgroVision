# AgroVisión — Plataforma de Monitoreo Agronómico

Plataforma de [AgroVisión](docs/reference/description_proyecto_agrovision.md) para monitoreo agronómico de precisión: **gestión de parcelas**, **teledetección NDVI** (Sentinel-2, 5 años), **agente conversacional (RAG)** y **conteo de plantas por dron** (este último **en desarrollo**). Backend **FastAPI** (monolito modular), persistencia **Supabase (PostGIS) BYOK**, y UI en **migración de Shiny → Astro + Tailwind** (Agro-Stack).

> **Modelo BYOK, credenciales efímeras.** Las llaves del usuario (Supabase, Copernicus, Groq) viven **solo en memoria de sesión** y se envían por cabeceras `X-User-*`; nunca se persisten. Refrescar borra todo.
>
> **Conteo por dron — EN DESARROLLO.** Arranca deshabilitado (`COUNTING_ENABLED=false`); la cola/worker/tabla existen pero inactivos hasta que el [repo del modelo](docs/reference/description_proyecto_modelo_conteo_plantas.md) publique el artefacto `agrovision-plantcount` en Hugging Face Hub. **Licencia: AGPL-3.0.**

## Módulos (6)

Resumen de Campo · Creación de Parcelas · Teledetección · Conteo por Dron (en desarrollo) · Asistente Agéntico · Credenciales.

## Arquitectura

```
Astro + Tailwind (UI, Fase 8)  ──HTTP /api──►  FastAPI (monolito modular)  ──►  Supabase (PostGIS) [BYOK]
   (Shiny = legacy en /shiny)                    ├─ /api/fields    (parcelas)        ├─ Sentinel Hub / Copernicus (NDVI)
                                                  ├─ /api/ndvi(+raster), /api/weather  ├─ Open-Meteo (clima, sin llave)
                                                  ├─ /api/chat      (agente RAG)        └─ Groq / Llama 3 (LLM)
                                                  └─ /api/count     (conteo, en desarrollo)
```

## Estructura

```
backend/    # FastAPI: api/ (routers por dominio) · services/ (negocio) · core/ (dominio puro) · db/ (PostGIS) · main
frontend/   # UI Shiny (legacy) → migrando a Astro + Tailwind (Fase 8)
supabase/   # migraciones SQL (PostGIS, índices, RLS, PGMQ)
tests/      # unit · integration (Supabase/Copernicus/Groq, skip sin llaves) · e2e
docs/       # reference/architect/db versionados; plan/task/investigation/doc_guia no
```

## Arranque rápido (local, sin Docker)

> **Windows + OneDrive:** la carpeta está sincronizada por la nube, lo que rompe los *hardlinks* y bloquea el `.venv`. Crea el entorno **fuera** de OneDrive:
> ```powershell
> $env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
> ```
> (El `link-mode = "copy"` ya está en `pyproject.toml`.)

```powershell
# 1) Dependencias
uv sync

# 2) (una vez, si usarás parcelas) configurar DATABASE_URL en .env y aplicar migraciones
uv run python -m backend.db.migrate

# 3) Backend (FastAPI) en :8000  — o scripts/run_backend.ps1
uv run python -u -m uvicorn backend.main:app --reload --port 8000 --log-level info

# 4) UI en :8001 (otra terminal) — o scripts/run_ui.ps1
uv run python -u -m uvicorn frontend.app:app --reload --port 8001
# Atajo: ambos en ventanas separadas
.\scripts\dev.ps1
```

Detalle completo (credenciales por módulo, migraciones, troubleshooting): **[`docs/ejecucion.md`](docs/ejecucion.md)**.

## Credenciales BYOK (capa gratuita)

| Servicio | Habilita | Variable(s) en `.env` |
|----------|----------|------------------------|
| **Supabase** (PostGIS) | Parcelas, Teledetección, Resumen | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` |
| **Copernicus CDSE** | NDVI satelital + heatmap | `DEV_COPERNICUS_CLIENT_ID`, `DEV_COPERNICUS_CLIENT_SECRET` |
| **Groq** | Asistente RAG | `DEV_GROQ_API_KEY` |
| Open-Meteo | Clima | — (sin llave) |

La app abre **sin** credenciales; cada módulo se activa al poner su llave (en `.env` local o en la pestaña *Credenciales*).

## Calidad y pruebas

```powershell
uv run ruff check .
uv run python -m pytest                 # unit + integración (skip sin llaves)
uv run python -m pytest tests/unit -q   # solo unitarias (rápidas)
```

## Documentación

- Definición: [`docs/reference/description_proyecto_agrovision.md`](docs/reference/description_proyecto_agrovision.md)
- Arquitectura: [`docs/architect/architecture_agrovision.md`](docs/architect/architecture_agrovision.md)
- Diseño de BD: [`docs/db/diseno_db.md`](docs/db/diseno_db.md)
- Ejecución (runbook): [`docs/ejecucion.md`](docs/ejecucion.md)
