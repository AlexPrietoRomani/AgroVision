# Levanta la UI Shiny del MVP en local (sin Docker), en http://127.0.0.1:8001
Set-Location (Split-Path -Parent $PSScriptRoot)

$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"
$env:UV_LINK_MODE = "copy"

# La app Shiny es ASGI: se sirve con uvicorn (python -u -m) para evitar el shim
# shiny.exe, que OneDrive bloquea. Equivale a `shiny run frontend/app.py`.
# --reload-exclude evita reinicios por cambios fuera del código de la UI (incluye backend/).
$env:PYTHONUNBUFFERED = "1"
uv run python -u -m uvicorn frontend.app:app --host 127.0.0.1 --port 8001 --reload --log-level info `
  --reload-exclude ".venv" --reload-exclude "backend" --reload-exclude "docs" `
  --reload-exclude "tests" --reload-exclude "scripts" --reload-exclude "supabase" `
  --reload-exclude "models" --reload-exclude "sample_data" --reload-exclude "scratch"
