$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function New-HexSecret([int]$ByteCount = 32) {
    $bytes = New-Object byte[] $ByteCount
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

Write-Host "Trading Lab OS v1.0.1 - PAPER ONLY" -ForegroundColor Cyan
Write-Host "No real exchange keys are required or allowed in this baseline." -ForegroundColor Yellow

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker command was not found. Install/start Docker Desktop with the WSL 2 backend first."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is installed but the Docker engine is not running. Start Docker Desktop and retry."
}

if (-not (Test-Path ".env")) {
    $apiPassword = New-HexSecret 24
    $jwtSecret = New-HexSecret 32
    $wsToken = New-HexSecret 24
    $grafanaPassword = New-HexSecret 16

    @"
FREQTRADE_IMAGE=freqtradeorg/freqtrade:2026.7
FREQTRADE_API_USER=freqtrader
FREQTRADE_API_PASSWORD=$apiPassword
FREQTRADE_JWT_SECRET=$jwtSecret
FREQTRADE_WS_TOKEN=$wsToken
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
"@ | Set-Content -Encoding ASCII ".env"

    Write-Host "Created .env with random local-only credentials." -ForegroundColor Green
    Write-Host "Grafana user: admin" -ForegroundColor Green
    Write-Host "Grafana password: $grafanaPassword" -ForegroundColor Green
    Write-Host "Save that Grafana password now. It is also stored locally in .env." -ForegroundColor Yellow
}

if (-not (Test-Path "freqtrade/user_data/config.json")) {
    Copy-Item "freqtrade/user_data/config.paper.json.example" "freqtrade/user_data/config.json"
}

Write-Host "Running paper-safety guard..." -ForegroundColor Cyan
$mount = "$((Get-Location).Path):/app"
docker run --rm -v $mount -w /app python:3.13-slim python scripts/paper_guard.py
if ($LASTEXITCODE -ne 0) { throw "Paper Guard failed. Nothing will be started." }

Write-Host "Pulling pinned images..." -ForegroundColor Cyan
docker compose pull
if ($LASTEXITCODE -ne 0) { throw "docker compose pull failed." }

Write-Host "Building the read-only metrics exporter..." -ForegroundColor Cyan
docker compose build freqtrade-exporter
if ($LASTEXITCODE -ne 0) { throw "Exporter build failed." }

Write-Host "Starting Trading Lab OS..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

Start-Sleep -Seconds 8
docker compose ps

Write-Host "" 
Write-Host "Open these local pages:" -ForegroundColor Green
Write-Host "Freqtrade / FreqUI : http://127.0.0.1:8080"
Write-Host "MLflow              : http://127.0.0.1:5000"
Write-Host "Prometheus          : http://127.0.0.1:9090"
Write-Host "Grafana             : http://127.0.0.1:3000"
Write-Host "" 
Write-Host "This baseline remains dry_run=true with a simulated 100 USDT wallet." -ForegroundColor Yellow
Write-Host "To stop later, run: .\STOP_WINDOWS.ps1" -ForegroundColor Yellow
