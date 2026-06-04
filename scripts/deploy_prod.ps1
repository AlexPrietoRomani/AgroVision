# scripts/deploy_prod.ps1 — Despliegue de AgroVisión a ShinyApps.io (Agro-Stack).
#
# El entrypoint es el gateway FastAPI (backend.main:app), que sirve la UI Astro
# compilada en / y la API en /api. Se publica con `rsconnect deploy fastapi` (NO
# `deploy shiny`: el gateway es FastAPI/ASGI). El bundle es el repo (`.`) MENOS las
# exclusiones de `.rscignore` (rsconnect-python no lee .rscignore solo: se traducen a --exclude).
#
# CREDENCIALES (sin paso manual): el script lee `SHINYAPPS_ACCOUNT/TOKEN/SECRET` del
# `.env` y las exporta al entorno; `rsconnect` las toma automáticamente (--account/--token/
# --secret son settables por esas mismas variables). Así NO necesitas `rsconnect add`.
# Alternativa: registrar el servidor una vez y desplegar por nombre:
#   uv run rsconnect add --account <cuenta> --name <cuenta> --token <TOKEN> --secret <SECRET>
#
# BYOK: el `.env` NO viaja en el bundle (está en .rscignore); en producción las llaves de
# datos las pone el usuario por sesión (cabeceras X-User-*). Nota: shinyapps.io NO soporta
# gestión de variables de entorno de runtime, por eso el modelo es BYOK (sin secretos en el server).
#
#   Primer deploy:   .\scripts\deploy_prod.ps1                    (toma la cuenta del .env)
#                    .\scripts\deploy_prod.ps1 -Name <cuenta>     (o explícita)
#   Redeploy:        .\scripts\deploy_prod.ps1 -AppId <id>        (actualiza esa app)
#   Forzar nueva:    .\scripts\deploy_prod.ps1 -New               (crea otra app aparte)
param(
    [string]$Name = "",   # cuenta de ShinyApps; si se omite, se toma de SHINYAPPS_ACCOUNT (.env)
    [string]$AppId = "",  # id de una app existente para REEMPLAZAR (redeploy)
    [switch]$New          # fuerza una app NUEVA aunque haya metadata de un deploy previo
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"

Write-Host "=== Deploy AgroVisión -> ShinyApps.io ===" -ForegroundColor Cyan

# Cargar SHINYAPPS_* del .env al entorno (sin pisar lo que ya exista en la sesión).
# rsconnect lee --account/--token/--secret desde estas mismas variables.
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*(SHINYAPPS_ACCOUNT|SHINYAPPS_TOKEN|SHINYAPPS_SECRET)\s*=\s*(.+)$') {
            $k = $matches[1]; $v = $matches[2].Trim().Trim('"').Trim("'")
            if ($v -and -not [Environment]::GetEnvironmentVariable($k)) { Set-Item "env:$k" $v }
        }
    }
}
if (-not $Name) { $Name = $env:SHINYAPPS_ACCOUNT }

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

# Validación de cuenta
if (-not $Name) {
    Write-Warning "Falta la cuenta de ShinyApps. Pon SHINYAPPS_ACCOUNT en .env o pasa -Name <cuenta>."
    Write-Warning "Y SHINYAPPS_TOKEN/SHINYAPPS_SECRET en .env (o registra antes con 'rsconnect add')."
    exit 1
}
if ($AppId -and $New) { Write-Error "-AppId y -New son mutuamente excluyentes."; exit 1 }

# Autenticación: si hay token+secret (del .env), rsconnect los toma del entorno y solo
# necesita la cuenta. Si no, se asume un servidor ya registrado con 'rsconnect add'.
if ($env:SHINYAPPS_TOKEN -and $env:SHINYAPPS_SECRET) {
    $authArgs = @("--account", $Name)   # token/secret vienen de $env:SHINYAPPS_TOKEN/SECRET
    Write-Host "Auth: credenciales de ShinyApps leídas del .env (cuenta '$Name')."
} else {
    $authArgs = @("--name", $Name)
    Write-Host "Auth: usando servidor registrado '$Name' (rsconnect add previo)."
}

# Destino: -AppId reemplaza esa app; -New fuerza una nueva; por defecto rsconnect
# reutiliza la metadata del deploy anterior (actualiza si existe, crea si no).
$targetArgs = @()
if ($AppId) { $targetArgs = @("--app-id", $AppId) }
elseif ($New) { $targetArgs = @("--new") }

# 3) Desplegar como app FastAPI (ASGI). El entrypoint es el gateway (UI Astro en / + /api).
Write-Host "`n[3/3] Desplegando (deploy fastapi, entrypoint backend.main:app)..." -ForegroundColor Yellow
& uv run python -c "from rsconnect.main import cli; cli()" deploy fastapi . `
    --entrypoint backend.main:app --title "AgroVisión" @authArgs @targetArgs @excludeArgs

Write-Host "`n=== Despliegue completado ===" -ForegroundColor Green
