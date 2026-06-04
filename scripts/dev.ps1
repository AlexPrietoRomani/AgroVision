# Arranca el stack de DESARROLLO en ventanas PowerShell separadas (local, sin Docker):
#   - Gateway FastAPI (:8000) — API en /api (+ UI compilada en / si existe backend/static).
#   - Astro dev server (:4321) — UI con hot-reload; proxea /api -> :8000.
# Uso:  .\scripts\dev.ps1
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-File", "`"$PSScriptRoot\run_backend.ps1`""
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; pnpm dev"

Write-Host "API:                 http://127.0.0.1:8000/api/status"
Write-Host "UI (Astro, dev):     http://localhost:4321/        (hot-reload)"
Write-Host "UI (compilada):      http://127.0.0.1:8000/        (tras .\scripts\build.ps1)"
Write-Host "UI Shiny (legacy):   .\scripts\run_ui.ps1          -> http://127.0.0.1:8001"
