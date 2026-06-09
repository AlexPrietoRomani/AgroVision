# AgroVisión 🫐

Plataforma de precisión para gestión de parcelas, NDVI satelital, agente RAG y conteo por dron.

[![demo](https://img.shields.io/badge/demo-Hugging%20Face-blue?style=flat&logo=huggingface&logoColor=yellow)](https://alexp97-agrovision.hf.space)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![frontend](https://img.shields.io/badge/frontend-Astro%205-orange?logo=astro&logoColor=white)](https://astro.build/)
[![styling](https://img.shields.io/badge/styling-Tailwind%204-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![database](https://img.shields.io/badge/database-Supabase%20PostGIS-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com/)

Plataforma de [AgroVisión](docs/reference/description_proyecto_agrovision.md) para monitoreo agronómico de precisión: **gestión de parcelas**, **teledetección NDVI** (Sentinel-2, 5 años), **agente conversacional (RAG)**, **explorador de datos SQL** y **conteo de plantas por dron** (este último **en desarrollo**). UI en **Astro + Tailwind** (estática) servida por el backend **FastAPI** (monolito modular), persistencia **Supabase (PostGIS) BYOK**. Despliegue en **Hugging Face Spaces** (Docker). *(Shiny fue eliminado en la Fase 10.)*

## Estado actual

### ✅ Implementado
- **Gestión de parcelas:** creación, edición y persistencia en Supabase (PostGIS)
- **NDVI satelital:** Sentinel-2, serie histórica 5 años, heatmap zonal
- **Clima básico:** temperatura y precipitación (Open-Meteo)
- **Agente RAG:** chat conversacional con Groq/Llama 3
- **Explorador de Datos:** consultas SQL directas a tablas de Supabase
- **Telemetría:** visor de eventos de sesión (memoria o BD)
- **BYOK:** credenciales efímeras, nunca persistidas

###  En desarrollo
- **Conteo por dron:** modelo `agrovision-plantcount` (AGPL-3.0) — cola/worker listos, pendiente publicación del modelo en Hugging Face Hub
- **Variables climáticas adicionales:** humedad, viento, radiación solar, evapotranspiración
- **Índices satelitales adicionales:** EVI, SAVI, NDWI, LST (temperatura superficial)
- **Alertas automatizadas:** umbrales configurables por parcela
- **Exportación de reportes:** PDF/CSV con datos de NDVI + clima

> **Nota:** Los módulos en desarrollo están visibles en la UI pero con funcionalidad limitada. Las variables climáticas actuales (temperatura y precipitación) son la base; se expandirán en fases posteriores.

## Módulos (8)

| Módulo | Estado | Descripción |
|--------|--------|-------------|
| **Resumen de Campo** | ✅ | KPIs de NDVI, tendencia y área por parcela |
| **Creación de Parcelas** | ✅ | Dibujo de polígonos (EPSG:4326) con Leaflet-draw |
| **Teledetección** | ✅ | NDVI Sentinel-2 (5 años) + clima básico |
| **Conteo por Dron** |  | Modelo YOLO/RF-DETR — pendiente publicación |
| **Asistente Agéntico** | ✅ | Chat RAG con Groq/Llama 3 |
| **Explorador de Datos** | ✅ | Consultas SQL directas a Supabase |
| **Credenciales** | ✅ | BYOK efímero (Supabase, Copernicus, Groq) |
| **Telemetría** | ✅ | Visor de eventos de sesión |

> **Próximas mejoras:** más variables climáticas (humedad, viento, radiación) e índices satelitales (EVI, SAVI, NDWI, LST).

## Capturas

| Módulo | Vista |
|--------|-------|
| **Resumen de Campo** | ![Resumen](docs/assets/resumen-campo.png) |
| **Creación de Parcelas** | ![Parcelas](docs/assets/creacion-parcelas.png) |
| **Teledetección NDVI** | ![NDVI](docs/assets/teledeteccion-ndvi.png) |
| **Explorador de Datos** | ![Datos](docs/assets/explorador-datos.png) |
| **Credenciales BYOK** | ![Credenciales](docs/assets/credenciales.png) |
| **Telemetría de Sesión** | ![Telemetría](docs/assets/telemetria-modal.png) |

## Arquitectura

```
Astro + Tailwind (UI estática)  ──fetch /api──►  FastAPI (monolito modular)  ─►  Supabase (PostGIS) [BYOK]
   servida por el gateway en /                    ├─ /api/fields    (parcelas)        ├─ Sentinel Hub / Copernicus (NDVI)
   (1 contenedor en HF Spaces)                    ├─ /api/ndvi(+raster), /api/weather  ├─ Open-Meteo (clima, sin llave)
                                                  ├─ /api/chat      (agente RAG)        └─ Groq / Llama 3 (LLM)
                                                  ├─ /api/events    (telemetría)
                                                  ├─ /api/data      (explorador SQL)
                                                  └─ /api/count     (conteo, en desarrollo)
```

## Estructura

```
backend/    # FastAPI: api/ (routers por dominio) · services/ (negocio) · core/ (dominio puro) · db/ (PostGIS) · static (UI compilada) · main
frontend/   # UI Astro + Tailwind (se compila a backend/static)
supabase/   # migraciones SQL (PostGIS, índices, RLS, PGMQ)
tests/      # unit · integration (Supabase/Copernicus/Groq, skip sin llaves) · e2e
docs/       # reference/architect/db versionados; plan/task/investigation/doc_guia no
```

## Arranque rápido

### Con Docker (recomendado)

```powershell
docker-compose up --build    # http://localhost:8000/
```

### Local (sin Docker)

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

# 3) Compilar la UI Astro -> backend/static  — o scripts/build.ps1
.\scripts\build.ps1

# 4) Backend (FastAPI) en :8000 (sirve la UI en / y la API en /api) — o scripts/run_backend.ps1
uv run python -u -m uvicorn backend.main:app --reload --port 8000 --log-level info

# Desarrollo de UI con hot-reload (Astro :4321 + backend :8000) en ventanas separadas:
.\scripts\dev.ps1
```

Despliegue a **Hugging Face Spaces**: `.\scripts\deploy_hf.ps1 -Force` (ver [`docs/ejecucion.md`](docs/ejecucion.md) §5).

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
