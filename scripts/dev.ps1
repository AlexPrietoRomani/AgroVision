# Arranca backend + UI en ventanas PowerShell separadas (local, sin Docker).
# Uso:  ./scripts/dev.ps1
Start-Process powershell -ArgumentList "-NoExit", "-File", "`"$PSScriptRoot\run_backend.ps1`""
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-File", "`"$PSScriptRoot\run_ui.ps1`""

Write-Host "Backend:  http://127.0.0.1:8000/api/status"
Write-Host "UI Shiny: http://127.0.0.1:8001"
