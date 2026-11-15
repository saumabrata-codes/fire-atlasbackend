param([string]$Output = "fireatlas-$(Get-Date -Format yyyyMMdd-HHmmss).dump")
$ErrorActionPreference = 'Stop'
docker compose exec -T db pg_dump -U fireatlas -Fc -f /tmp/fireatlas.dump fireatlas
docker compose cp db:/tmp/fireatlas.dump $Output
docker compose exec -T db rm -f /tmp/fireatlas.dump
Write-Host "Database backup written to $Output"
