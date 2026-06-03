# Levanta la UI Shiny del MVP en local (sin Docker), en http://127.0.0.1:8001
Set-Location (Split-Path -Parent $PSScriptRoot)

$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
$env:UV_LINK_MODE = "copy"

# La app Shiny es ASGI: se sirve con uvicorn (python -m) para evitar el shim
# shiny.exe, que OneDrive bloquea. Equivale a `shiny run frontend/app.py`.
uv run python -m uvicorn frontend.app:app --host 127.0.0.1 --port 8001 --reload
