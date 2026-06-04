# scripts/deploy_prod.ps1 — Despliegue de AgroVisión a ShinyApps.io (Agro-Stack).
#
# El entrypoint es el gateway FastAPI (backend.main:app), que sirve la UI Astro
# compilada en / y la API en /api. El bundle es el repo (`.`) MENOS las exclusiones
# de `.rscignore` (rsconnect-python no lee .rscignore solo: aquí se traducen a --exclude).
#
# BYOK: el `.env` (secretos) NO viaja en el bundle (está en .rscignore); en producción
# las credenciales las pone el usuario por sesión (cabeceras X-User-*).
#
# Aún no hay app-id para esta app: pásalo cuando exista para hacer redeploy.
#   Primer deploy:  .\scripts\deploy_prod.ps1 -Name <tu_cuenta>
#   Redeploy:       .\scripts\deploy_prod.ps1 -Name <tu_cuenta> -AppId <id>
# Registrar token (una vez):
#   uv run rsconnect add --account <cuenta> --name <cuenta> --token <TOKEN> --secret <SECRET>
param(
    [string]$Name = "<TU_CUENTA_SHINYAPPS>",
    [string]$AppId = ""   # vacío = primer deploy (crea la app); luego usa el id para redeploy
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"

Write-Host "=== Deploy AgroVisión -> ShinyApps.io ===" -ForegroundColor Cyan

# 0) Compilar la UI (Astro -> backend/static)
Write-Host "`n[0/3] Compilando la UI..." -ForegroundColor Yellow
& "$PSScriptRoot\build.ps1"

# 1) requirements.txt para ShinyApps (no usa uv; instala desde requirements.txt)
Write-Host "`n[1/3] Generando requirements.txt (uv export)..." -ForegroundColor Yellow
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error "uv export falló"; exit 1 }

# 2) Construir los --exclude desde .rscignore (ignora comentarios y vacíos)
$patterns = @()
if (Test-Path ".rscignore") {
    $patterns = Get-Content ".rscignore" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and (-not $_.StartsWith("#")) } |
        Select-Object -Unique
} else {
    Write-Warning ".rscignore no encontrado: el bundle incluiría TODO el repo."
}
$excludeArgs = @()
foreach ($p in $patterns) { $excludeArgs += "--exclude"; $excludeArgs += $p }
Write-Host ("[2/3] {0} patrones de exclusión cargados desde .rscignore" -f $patterns.Count)

if ($Name -eq "<TU_CUENTA_SHINYAPPS>") {
    Write-Warning "Falta tu cuenta de ShinyApps. Uso: .\scripts\deploy_prod.ps1 -Name <cuenta> [-AppId <id>]"
    Write-Warning "Y registra el token primero (ver cabecera de este script)."
    exit 1
}

# 3) Desplegar como app FastAPI (ASGI). OJO: NO es 'deploy shiny' (eso espera una app
#    Shiny); el gateway es FastAPI, así que el subcomando correcto es 'deploy fastapi'
#    (rsconnect lo soporta para shinyapps.io). El entrypoint es el gateway que sirve
#    la UI Astro en / y la API en /api.
Write-Host "`n[3/3] Desplegando (deploy fastapi, entrypoint backend.main:app)..." -ForegroundColor Yellow
$appIdArgs = @()
if ($AppId) { $appIdArgs = @("--app-id", $AppId) }
& uv run python -c "from rsconnect.main import cli; cli()" deploy fastapi . `
    --entrypoint backend.main:app --name $Name @appIdArgs @excludeArgs

Write-Host "`n=== Despliegue completado ===" -ForegroundColor Green
