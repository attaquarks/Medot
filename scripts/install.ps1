# AIA installer for Windows (PowerShell). Idempotent.
# Run from the repo root:  ./scripts/install.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "Checking prerequisites..." -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker Desktop is required: https://www.docker.com/products/docker-desktop/"
}

if (-not (Test-Path ".env")) {
  Write-Host "Creating .env from template..."
  Copy-Item ".env.example" ".env"
}

Write-Host "Building images (first run downloads layers)..." -ForegroundColor Cyan
docker compose build

Write-Host "Starting datastore + local LLM..." -ForegroundColor Cyan
docker compose up -d postgres redis ollama

Write-Host "Pulling local models..." -ForegroundColor Cyan
docker compose exec ollama ollama pull llama3.1:8b-instruct-q4_K_M
docker compose exec ollama ollama pull nomic-embed-text

Write-Host "Initialising database..." -ForegroundColor Cyan
docker compose run --rm gateway python -m aia.db.init

Write-Host "Launching onboarding wizard..." -ForegroundColor Cyan
docker compose up -d onboarding

Write-Host ""
Write-Host "Done. Open http://localhost:8088 to connect your accounts." -ForegroundColor Green
Write-Host "After connecting, run:  make up   (or: docker compose up -d)"
