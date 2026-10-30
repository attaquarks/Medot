#!/usr/bin/env bash
# AIA installer for macOS / Linux. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "Docker is required: https://docs.docker.com/get-docker/"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required."; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo "Native Ollama is required: https://ollama.com/download"; exit 1; }
ollama list >/dev/null 2>&1 || { echo "Ollama is installed but not responding. Start Ollama, then rerun this script."; exit 1; }

if [ ! -f .env ]; then
  echo "Creating .env from template..."
  cp .env.example .env
fi

echo "Building images (first run downloads layers, be patient)..."
docker compose build

echo "Starting datastore..."
docker compose up -d postgres redis

echo "Ensuring local models exist in native Ollama..."
./scripts/pull-models.sh

echo "Initialising database..."
docker compose run --rm gateway python -m aia.db.init

echo "Launching onboarding wizard..."
docker compose up -d onboarding
echo ""
echo "Done. Open http://localhost:8088 to connect your accounts."
echo "After connecting, run: docker compose up -d"
