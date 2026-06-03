# Levanta el backend FastAPI del MVP en local (sin Docker), en http://127.0.0.1:8000
Set-Location (Split-Path -Parent $PSScriptRoot)

# Entorno virtual fuera de OneDrive (evita errores de hardlink/lock en carpetas sincronizadas)
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
$env:UV_LINK_MODE = "copy"

uv sync
# Se usa "python -m uvicorn" (no el shim uvicorn.exe) para evitar errores de
# ejecución en carpetas sincronizadas por OneDrive.
uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
