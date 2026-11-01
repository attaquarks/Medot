# Running AIA Locally With Native Ollama

This guide runs the AIA Docker stack (`postgres`, `redis`, `gateway`,
`business-agent`, `health-agent`, `whatsapp-gateway`) while using Ollama already
installed on the host machine. The project does not run or download an
`ollama/ollama` Docker image.

## 0. Prerequisites

```cmd
docker --version
docker compose version
ollama --version
ollama list
```

If you use Ollama Cloud models such as `nemotron-3-super:cloud`, sign in on the
host:

```cmd
ollama signin
```

## 1. Configure `.env`

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
copy .env.example .env
notepad .env
```

Use the host Ollama URL from inside Docker:

```ini
AIA_ENV=local
AIA_TENANT_ID=default
OLLAMA_BASE_URL=http://host.docker.internal:11434
LLM_LOCAL_MODEL=ollama/nemotron-3-super:cloud
LLM_EMBEDDING_MODEL=ollama/nomic-embed-text
LLM_FORCE_CLOUD=0
```

## 2. Pull Models Into Native Ollama

```cmd
ollama pull nemotron-3-super:cloud
ollama pull nomic-embed-text
ollama list
```

For a fully local model, use a non-cloud tag instead, for example:

```cmd
ollama pull llama3.1:8b-instruct-q4_K_M
```

Then set:

```ini
LLM_LOCAL_MODEL=ollama/llama3.1:8b-instruct-q4_K_M
```

## 3. Build And Start

```cmd
docker compose build
docker compose up -d postgres redis
docker compose run --rm gateway python -m aia.db.init
docker compose up -d whatsapp-gateway gateway business-agent health-agent onboarding
```

Open the onboarding wizard at <http://localhost:8088>.

## 4. Verify

```cmd
curl http://localhost:8080/health
curl http://localhost:8080/models

curl -X POST http://localhost:8080/test/message ^
  -H "Content-Type: application/json" ^
  -d "{\"agent\":\"business\",\"text\":\"Add a follow-up task to call Ali tomorrow.\"}"

curl -X POST http://localhost:8080/test/message ^
  -H "Content-Type: application/json" ^
  -d "{\"agent\":\"health\",\"text\":\"I had oats with milk and a banana for breakfast.\"}"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `httpx.ConnectError` to Ollama | Make sure native Ollama is running and `.env` has `OLLAMA_BASE_URL=http://host.docker.internal:11434`. |
| `401 Unauthorized` from Ollama Cloud | Run `ollama signin` on the host, then restart `gateway`, `business-agent`, and `health-agent`. |
| Models do not appear at `/models` | Run `ollama list` on the host and confirm the same `OLLAMA_BASE_URL` is set in `.env`. |
| `asyncpg` connection refused | Wait for Postgres healthcheck, then rerun the DB init command. |
