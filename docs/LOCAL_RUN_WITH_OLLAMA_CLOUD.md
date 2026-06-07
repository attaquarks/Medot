# Running AIA locally with Ollama Cloud models (Windows / cmd.exe)

This guide runs the **whole AIA stack** (`postgres`, `redis`, `ollama`, `gateway`,
`business-agent`, `health-agent`) on your laptop, using **Ollama Cloud** for the
LLM (so no multi-GB local downloads). We use `nemotron-3-super:cloud` as the
chat model and `nomic-embed-text` for embeddings.

> A new `GET /models` endpoint on the gateway (port 8080) lets you list every
> model visible to the in-container Ollama server (local + `:cloud`).

---

## 0. Prerequisites (one-time, on the host)

```cmd
REM Docker Desktop must be running.
docker --version
docker compose version

REM Install Ollama on the host (needed for `ollama signin`).
REM Download: https://ollama.com/download  (Windows installer)
ollama --version
```

The first time you run the stack with cloud models you'll need to be signed in
to Ollama Cloud:

```cmd
ollama signin
```
A browser window opens — sign in, and Ollama writes `id_ed25519` keys into
`%USERPROFILE%\.ollama\`. The docker-compose file bind-mounts that directory
into the Ollama container so the same keys are visible there.

---

## 1. Configure `.env`

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
copy .env.example .env
notepad .env
```

In notepad, confirm / change these lines:

```ini
AIA_ENV=local
AIA_TENANT_ID=default
OLLAMA_BASE_URL=http://ollama:11434
LLM_LOCAL_MODEL=ollama/nemotron-3-super:cloud
LLM_CLOUD_MODEL=openai/gpt-4o-mini
LLM_EMBEDDING_MODEL=ollama/nomic-embed-text
LLM_FORCE_CLOUD=0
```

Save and close. The `LLM_LOCAL_MODEL=ollama/...` prefix tells LiteLLM to route
through Ollama; the `nemotron-3-super:cloud` tag tells Ollama itself to pull
the model manifest from Ollama Cloud and stream responses back to you.

---

## 2. Pull the cloud chat model and the embedding model (on the host)

```cmd
ollama pull nemotron-3-super:cloud
ollama pull nomic-embed-text
ollama list
```
You should see both models in the list.

---

## 3. Build the AIA images (one-time, ~3-5 min on first run)

```cmd
docker compose build
```

---

## 4. Start the infrastructure services (Postgres + Redis + Ollama)

```cmd
docker compose up -d postgres redis ollama
```

Wait for Ollama to be healthy (polls `ollama list` until it responds):

```cmd
docker compose exec ollama ollama list
```
You should see `nemotron-3-super:cloud` and `nomic-embed-text` (the
`~/.ollama` bind-mount makes them visible inside the container too).

---

## 5. Initialise the database (idempotent)

```cmd
docker compose run --rm gateway python -m aia.db.init
```

---

## 6. Start each agent — one terminal per service

> The user asked for one command per agent, so they can see each log stream.

### Terminal 1 — Gateway (inbound router + REST + /models endpoint)

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
docker compose up gateway
```

### Terminal 2 — Business agent

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
docker compose up business-agent
```

### Terminal 3 — Health agent

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
docker compose up health-agent
```

### Terminal 4 (optional) — WhatsApp sidecar

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
docker compose up whatsapp-gateway
```

### Terminal 5 (optional) — Onboarding wizard

```cmd
cd C:\Users\Atta\Documents\Projects\ai-assistant-system
docker compose up onboarding
```
…then open <http://localhost:8088>.

---

## 7. Verify the system is wired up correctly

```cmd
REM 7a. Gateway health
curl http://localhost:8080/health

REM 7b. Auto-detected Ollama models (NEW endpoint)
curl http://localhost:8080/models

REM 7c. Drive a single business-agent turn over HTTP (no WhatsApp needed)
curl -X POST http://localhost:8080/test/message ^
  -H "Content-Type: application/json" ^
  -d "{\"agent\":\"business\",\"text\":\"Reschedule my 3pm meeting to tomorrow at 11am and email everyone.\"}"

REM 7d. Drive a single health-agent turn
curl -X POST http://localhost:8080/test/message ^
  -H "Content-Type: application/json" ^
  -d "{\"agent\":\"health\",\"text\":\"I had oats with milk and a banana for breakfast.\"}"
```

If the responses contain real assistant text (not an error), the entire
pipeline — Postgres, Redis, Ollama Cloud, the LLM router, the agent reasoning
loop, and short-term memory — is working end-to-end.

---

## 8. Stopping / restarting

```cmd
REM Stop everything but keep data
docker compose down

REM Start everything again (agents and infra)
docker compose up -d postgres redis ollama gateway business-agent health-agent
```

---

## 9. Switching models (no rebuild needed)

```cmd
REM See what's available
curl http://localhost:8080/models

REM Edit .env and change LLM_LOCAL_MODEL=ollama/<new-name>:<tag>
notepad .env

REM Restart the gateway + agents so they re-read settings
docker compose restart gateway business-agent health-agent
```

Common cloud tags to try:

| Model                       | `LLM_LOCAL_MODEL=...`                   |
| --------------------------- | --------------------------------------- |
| NVIDIA Nemotron 3 Super     | `ollama/nemotron-3-super:cloud`         |
| DeepSeek V3.1               | `ollama/deepseek-v3.1:cloud`            |
| Qwen3 Coder                 | `ollama/qwen3-coder:cloud`              |
| Mistral Large               | `ollama/mistral-large:cloud`            |
| Llama 3.1 8B (fully local)  | `ollama/llama3.1:8b-instruct-q4_K_M`    |

---

## Troubleshooting

| Symptom                                           | Fix                                                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `ollama list` shows nothing in the container      | Make sure `%USERPROFILE%\.ollama` exists on the host and contains `id_ed25519` + the model blobs. |
| `401 Unauthorized` from Ollama Cloud              | Run `ollama signin` on the host, then `docker compose restart ollama`.                            |
| `Test endpoint is only enabled when AIA_ENV=local`| Make sure `AIA_ENV=local` is set in `.env`.                                                       |
| `httpx.ConnectError` to `ollama:11434`            | `docker compose ps` — is the `ollama` container Up and healthy?                                   |
| `asyncpg` connection refused                     | Wait a few seconds — Postgres healthcheck retries up to 10×.                                      |
