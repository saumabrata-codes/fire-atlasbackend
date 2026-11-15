$ErrorActionPreference = 'Stop'
docker compose --project-directory (Resolve-Path (Join-Path $PSScriptRoot '../..')) up -d --build --wait
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'FireAtlas is running at http://localhost:5173. API docs are at http://localhost:8000/docs.'
