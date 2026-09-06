$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker command was not found."
}
docker compose down
Write-Host "Trading Lab OS stopped. Persistent Docker volumes were kept." -ForegroundColor Green
