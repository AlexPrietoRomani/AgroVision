# Compila la UI Astro y la copia a backend/static (servida por el gateway FastAPI en /).
# Uso:  .\scripts\build_ui.ps1
Set-Location (Split-Path -Parent $PSScriptRoot)

Push-Location frontend
pnpm install
pnpm build
Pop-Location

$static = "backend/static"
New-Item -ItemType Directory -Force -Path $static | Out-Null
# Limpia el estático anterior conservando .gitkeep
Get-ChildItem $static -Exclude ".gitkeep" -Force | Remove-Item -Recurse -Force
Copy-Item -Recurse -Force "frontend/dist/*" "$static/"
if (-not (Test-Path "$static/.gitkeep")) { New-Item -ItemType File "$static/.gitkeep" | Out-Null }

Write-Host "UI Astro compilada -> backend/static (sirve el gateway en http://127.0.0.1:8000/)"
