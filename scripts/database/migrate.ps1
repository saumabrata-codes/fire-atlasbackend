$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..\..\backend')
try { python -m alembic upgrade head } finally { Pop-Location }
