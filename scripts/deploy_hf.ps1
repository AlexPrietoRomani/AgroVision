# scripts/deploy_hf.ps1 — Despliegue de AgroVisión a Hugging Face Spaces (SDK Docker).
#
# El Space es un repo git en huggingface.co. HF construye el `Dockerfile` de la raíz
# (gateway FastAPI: UI Astro en / + API en /api) y lo sirve en el puerto `app_port`
# del README.md (8000). NO se compila ni empaqueta en local: solo se hace `git push`
# y HF construye en su lado.
#
# Requisitos (en .env, NO se versiona):
#   HF_TOKEN=hf_xxx              # token con permiso de escritura (huggingface.co/settings/tokens)
#   HF_SPACE_ID=<usuario>/<space>   # p. ej. alexprieto/agrovision  (crea el Space ANTES, SDK=Docker)
#
# Crear el Space una vez (web): huggingface.co/new-space -> SDK "Docker" -> Blank.
# BYOK: no se ponen secretos de datos en el Space; el usuario pega sus llaves por sesión.
#
# Uso:  .\scripts\deploy_hf.ps1
param(
    [string]$SpaceId = "",   # si se omite, se toma de HF_SPACE_ID (.env)
    [switch]$Force           # fuerza el push (sobrescribe el historial del Space)
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "=== Deploy AgroVisión -> Hugging Face Spaces ===" -ForegroundColor Cyan

# Cargar HF_TOKEN / HF_SPACE_ID del .env (sin pisar lo que ya exista en la sesión).
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*(HF_TOKEN|HF_SPACE_ID)\s*=\s*(.+)$') {
            $k = $matches[1]; $v = $matches[2].Trim().Trim('"').Trim("'")
            if ($v -and -not [Environment]::GetEnvironmentVariable($k)) { Set-Item "env:$k" $v }
        }
    }
}
if (-not $SpaceId) { $SpaceId = $env:HF_SPACE_ID }

if (-not $env:HF_TOKEN) { Write-Error "Falta HF_TOKEN en .env (token de escritura de Hugging Face)."; exit 1 }
if (-not $SpaceId -or $SpaceId -notmatch '^[^/]+/[^/]+$') {
    Write-Error "Falta HF_SPACE_ID válido (formato <usuario>/<space>). Pon HF_SPACE_ID en .env o pasa -SpaceId."
    exit 1
}

# El dueño del Space (parte antes de '/') hace de usuario en la URL autenticada.
$owner = $SpaceId.Split("/")[0]
$remote = "https://${owner}:$($env:HF_TOKEN)@huggingface.co/spaces/$SpaceId"

# Aviso: el Space debe existir (SDK Docker). El primer push suele necesitar -Force
# porque el Space arranca con un commit inicial (README) distinto a nuestro historial.
Write-Host "Space: huggingface.co/spaces/$SpaceId  (rama main)" -ForegroundColor Yellow
Write-Host "Empujando el repo (HEAD -> main); HF construirá el Dockerfile..." -ForegroundColor Yellow

$pushArgs = @("push")
if ($Force) { $pushArgs += "--force" }
$pushArgs += @($remote, "HEAD:main")

# Nota: el token va en la URL solo para este push (no se guarda como remote).
& git @pushArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warning "El push falló. Si es el primer deploy, reintenta con:  .\scripts\deploy_hf.ps1 -Force"
    exit 1
}

Write-Host "`n=== Push completado. Sigue el build en huggingface.co/spaces/$SpaceId ===" -ForegroundColor Green
Write-Host "Cuando termine, abre la URL del Space: la UI carga en / y la API en /api." -ForegroundColor Green
