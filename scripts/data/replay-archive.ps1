param(
    [Parameter(Mandatory = $true)][string]$Sensor,
    [Parameter(Mandatory = $true)][string]$Product,
    [Parameter(Mandatory = $true)][string]$Year,
    [Parameter(Mandatory = $true)][string]$Month,
    [Parameter(Mandatory = $true)][string]$FileName,
    [string]$ApiBase = 'http://localhost:8000'
)
$ErrorActionPreference = 'Stop'
$uri = "$ApiBase/api/v1/ingestion/archive/$Sensor/$Product/$Year/$Month/$FileName/replay"
Invoke-RestMethod -Method Post -Uri $uri
