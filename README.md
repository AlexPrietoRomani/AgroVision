# AgroVisión — MVP (Conteo por Dron)

MVP de [AgroVisión](docs/reference/description_proyecto_agrovision_mvp.md): UI en **Shiny for Python** + backend **FastAPI** para el conteo de plantas a partir de ortomosaicos de dron.

> **Estado actual — STANDBY.** El módulo de conteo arranca **deshabilitado** (`COUNTING_ENABLED=false`) hasta que el [repo del modelo](docs/reference/description_proyecto_modelo_conteo_plantas.md) publique el artefacto `agrovision-plantcount` en Hugging Face Hub. Mientras tanto, la UI muestra el aviso *"Módulo en preparación"* y el endpoint `/api/count` responde `503`.
>
> **Modelo agnóstico.** La app consume el artefacto por **contrato** vía un adaptador de inferencia (onnxruntime o `ultralytics` según la arquitectura: YOLO26/RF-DETR). **Licencia: AGPL-3.0** (app open-source).

## Estructura

```
backend/    # FastAPI: config, schemas, core (detection, metrics, inference), api/count, main
frontend/   # Shiny for Python: app.py (Conteo en standby + Credenciales efímeras)
tests/      # unit · integration · e2e (Playwright, skip por defecto)
models/     # artefacto .onnx (no versionado; se descarga de HF Hub)
sample_data/# ortomosaicos de ejemplo (no versionados)
docs/       # documentación (reference/architect/db versionados; plan/task/investigation no)
```

## Arranque rápido (local)

> **Windows + OneDrive:** la carpeta está sincronizada por la nube, lo que rompe los *hardlinks* y bloquea el `.venv`. Crea el entorno **fuera** de OneDrive:
> ```powershell
> $env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
> ```
> (El `link-mode = "copy"` ya está fijado en `pyproject.toml`.)

```bash
# 1) Dependencias (uv)
uv sync

# 2) Backend (FastAPI) en :8000   — o usa scripts/run_backend.ps1
uv run python -m uvicorn backend.main:app --reload --port 8000

# 3) UI (Shiny, ASGI) en :8001 (otra terminal) — o usa scripts/run_ui.ps1
uv run python -m uvicorn frontend.app:app --reload --port 8001
```

> En Windows/OneDrive se usa `python -m uvicorn` en vez de los shims `uvicorn.exe`/`shiny.exe` (que la sincronización en la nube bloquea). La app Shiny es ASGI, así que `uvicorn frontend.app:app` equivale a `shiny run frontend/app.py`.

```bash
# Atajo: levantar backend + UI en ventanas separadas
./scripts/dev.ps1

# 4) Calidad y pruebas
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Con Docker:

```bash
docker compose up --build   # api en :8000, ui en :8001
```

## Activar el conteo (cuando el modelo esté publicado)

1. Publicar `agrovision-plantcount-vX.Y.Z.onnx` en Hugging Face Hub (repo del modelo).
2. Descomentar el bloque `hf_hub_download` en [`backend/Dockerfile`](backend/Dockerfile).
3. Poner `COUNTING_ENABLED=true` y `MODEL_ARCHITECTURE` (`yolo26n`/`rfdetr_nano`).
4. Implementar el decode correspondiente en [`backend/core/inference.py`](backend/core/inference.py).

## Documentación

- Spec funcional: [`docs/reference/description_proyecto_agrovision_mvp.md`](docs/reference/description_proyecto_agrovision_mvp.md)
- Arquitectura: [`docs/architect/architecture_agrovision_mvp.md`](docs/architect/architecture_agrovision_mvp.md)
