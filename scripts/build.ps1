# scripts/build.ps1 — Pipeline de build de la UI: Astro -> inline -> backend/static
# (lo que sirve el gateway FastAPI en /). Uso: .\scripts\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
# venv fuera de OneDrive (para uv) — ver docs/ejecucion.md
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\agrovision-venv"

Write-Host "=== Build AgroVisión UI (Astro -> backend/static) ===" -ForegroundColor Cyan

# 1) Compilar Astro
Write-Host "`n[1/3] Compilando Astro (pnpm build)..." -ForegroundColor Yellow
Push-Location "$root\frontend"
pnpm install
pnpm build
$buildOk = ($LASTEXITCODE -eq 0)
Pop-Location
if (-not $buildOk) { Write-Error "pnpm build falló"; exit 1 }

# 2) Post-procesar: inline de JS y rutas relativas (Regla de Oro para ShinyApps)
Write-Host "`n[2/3] Post-procesando index.html (inline_js.py)..." -ForegroundColor Yellow
uv run python scripts/inline_js.py
if ($LASTEXITCODE -ne 0) { Write-Error "inline_js.py falló"; exit 1 }

# 3) Copiar el build a backend/static (preservando .gitkeep)
Write-Host "`n[3/3] Copiando frontend\dist -> backend\static..." -ForegroundColor Yellow
$static = "$root\backend\static"
New-Item -ItemType Directory -Force -Path $static | Out-Null
Get-ChildItem $static -Exclude ".gitkeep" -Force | Remove-Item -Recurse -Force
Copy-Item -Path "$root\frontend\dist\*" -Destination $static -Recurse -Force
if (-not (Test-Path "$static\.gitkeep")) { New-Item -ItemType File "$static\.gitkeep" | Out-Null }

Write-Host "`n=== Build completado. Sirve con:  .\scripts\run_backend.ps1  -> http://127.0.0.1:8000/ ===" -ForegroundColor Green
