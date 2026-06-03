# Levanta el backend FastAPI del MVP en local (sin Docker), en http://127.0.0.1:8000
Set-Location (Split-Path -Parent $PSScriptRoot)

# Entorno virtual fuera de OneDrive (evita errores de hardlink/lock en carpetas sincronizadas)
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
$env:UV_LINK_MODE = "copy"

uv sync
# Se usa "python -u -m uvicorn" (no el shim uvicorn.exe) para evitar errores de
# ejecución en carpetas sincronizadas por OneDrive; -u/PYTHONUNBUFFERED dan logs en vivo.
# --reload-exclude evita reinicios por cambios fuera del código del backend (incluye frontend/).
$env:PYTHONUNBUFFERED = "1"
uv run python -u -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --log-level info `
  --reload-exclude ".venv" --reload-exclude "frontend" --reload-exclude "docs" `
  --reload-exclude "tests" --reload-exclude "scripts" --reload-exclude "supabase" `
  --reload-exclude "models" --reload-exclude "sample_data" --reload-exclude "scratch"
