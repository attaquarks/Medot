# ai-assistant-system — Agent Briefing

> A local-first, two-agent personal assistant ("Business Assistant" + "Health & Diet Coach") that talks to the user over WhatsApp, runs as Docker Compose on the user's laptop, and uses a hybrid LLM (local Ollama by default, cloud fallback for hard tasks). Production-grade scaffold with a Node Baileys sidecar; several integration call-sites are marked `# TODO(impl)` (see `docs/09-roadmap.md`).

## 1. Identity
- **Name:** ai-assistant-system (package name `aia`, version 0.1.0 per `pyproject.toml` and `src/aia/__init__.py:11`).
- **Absolute path:** `C:\Users\Atta\Documents\Projects\ai-assistant-system`
- **Category:** agent (multi-agent personal assistant, hybrid local/cloud LLM).
- **Lifecycle stage:** scaffold — runnable end-to-end via `make setup && make up`, with several `# TODO(impl)` markers in integration adapters and the scheduler.
- **Hypothesis confirmed:** yes. The plan's hypothesis ("multi-service AI assistant: src/aia Python service, whatsapp-gateway service, postgres deploy, Makefile, comprehensive docs/") is accurate. The actual structure is: one Python `aia` package with multiple entrypoints (gateway, two agent workers, onboarding), a Node/TypeScript WhatsApp sidecar (`services/whatsapp-gateway`), a Docker Compose stack with Postgres+pgvector+Redis, a Makefile, and `docs/01-..09-*.md` plus a cloud-run guide.
- **Repo health:** 4/5 — real README, `docs/` (9 docs), `pyproject.toml`, `Makefile`, `docker-compose.yml`, `.env.example`, install scripts for Win/macOS/Linux, schema, agent framework, provider abstractions, and a wizard are all present; deductions for sparse test coverage (only `tests/test_crypto.py` + `tests/test_nutrition.py`) and several `# TODO(impl)` integration holes.

## 2. Tech Stack
**Languages + versions (from `pyproject.toml` and `services/whatsapp-gateway/package.json`):**
- Python `>=3.11` (Dockerfiles `docker/python.Dockerfile`, `docker/onboarding.Dockerfile` both `FROM python:3.11`).
- TypeScript / Node 20 (`services/whatsapp-gateway/Dockerfile`: `FROM node:20-slim`).

**Frameworks and key libraries (top 10 by role):**
- `fastapi>=0.110` + `uvicorn[standard]>=0.29` — web framework for gateway + onboarding (`src/aia/gateway/main.py`, `src/aia/onboarding/main.py`).
- `pydantic>=2.6` + `pydantic-settings>=2.2` — typed config (`src/aia/config.py`).
- `sqlalchemy[asyncio]>=2.0` + `asyncpg>=0.29` + `pgvector>=0.2.5` — async ORM + Postgres + vector store (`src/aia/db/base.py`, `src/aia/db/models.py`).
- `redis>=5.0` — short-term memory + Redis Streams event bus (`src/aia/events/bus.py`, `src/aia/memory/short_term.py`).
- `litellm>=1.40` — unified LLM access (Ollama + OpenAI + Anthropic) (`src/aia/llm/router.py`).
- `langgraph>=0.1.5` + `langchain-core>=0.2` — agent workflow state machines (declared in `pyproject.toml`; reasoning loop in `src/aia/agents/base.py`).
- `cryptography>=42.0` + `keyring>=24.3` — Fernet envelope encryption + OS keychain master key (`src/aia/security/crypto.py`).
- `httpx>=0.27` — async HTTP client for all provider adapters.
- `google-api-python-client>=2.120` + `google-auth-oauthlib>=1.2` + `msal>=1.28` + `twilio>=9.0` — provider SDKs.
- `@whiskeysockets/baileys` ^6.7.0 + `express` ^4.19 + `pino` + `qrcode` — Node WhatsApp sidecar (`services/whatsapp-gateway/src/index.ts`).

**Infra / services (from `docker-compose.yml`):**
- **DB:** `pgvector/pgvector:pg16` on port 5432, three logical schemas (`core`, `business`, `health`).
- **Cache / event bus:** `redis:7-alpine` on port 6378, `appendonly yes`, used for short-term memory and Redis Streams event bus.
- **Vector store:** `pgvector` inside the same Postgres.
- **LLM:** Ollama is expected to run natively on the host (`OLLAMA_BASE_URL=http://host.docker.internal:11434` default; `scripts/pull-models.sh` does `ollama pull`). Cloud LLM fallback is OpenAI or Anthropic via LiteLLM.
- **Object storage:** none — local volumes only (`pgdata`, `redisdata`, `wa_auth`).
- **External APIs:** Twilio (voice + TwiML), Deepgram (STT, env `DEEPGRAM_API_KEY`), Gmail/Outlook (email), Google/MS Calendar, Nutrition providers (`usda` / `nutritionix` / `openfoodfacts`), Notion/Todoist/Google Tasks, Meta WhatsApp Business Cloud API (optional).

**Run / build / test tools:**
- Python deps via `uv` (`uv.lock` present); package manager not pinned in `pyproject.toml`.
- Linter/format: `ruff` (declared in `pyproject.toml` `[tool.ruff] line-length = 100`, `target-version = "py311"`, optional `dev` extra).
- Test: `pytest>=8.0` + `pytest-asyncio>=0.23` (declared in `dev` extra); `pyproject.toml` sets `asyncio_mode = "auto"`, `testpaths = ["tests"]`.
- Type-check: `mypy>=1.10` declared in dev extra (not wired into the Makefile).
- Build (Node sidecar): TypeScript compiled with `tsc -p tsconfig.json` (`services/whatsapp-gateway/package.json` scripts).
- Orchestration: Docker Compose v2 (`COMPOSE := docker compose` in `Makefile`).

## 3. Repository Layout
```
ai-assistant-system/
├─ src/aia/                  # the shared `aia` Python package; many entrypoints
│  ├─ __init__.py            # package docstring + __version__
│  ├─ config.py              # pydantic-settings typed env config
│  ├─ logging.py             # structlog with secret-redaction processor
│  ├─ db/                    # SQLAlchemy async engine, models, idempotent init
│  ├─ security/              # Fernet envelope crypto, keychain, audit log
│  ├─ llm/router.py          # hybrid local->cloud LLM router via LiteLLM
│  ├─ memory/                # short_term (Redis list) + long_term (pgvector)
│  ├─ events/bus.py          # Redis Streams event bus with consumer groups
│  ├─ agents/
│  │  ├─ base.py             # BaseAgent reasoning loop (recall -> prompt -> LLM -> tools)
│  │  ├─ tools.py            # Tool / ToolRegistry / ToolContext abstractions
│  │  ├─ business/           # Agent 1: prompts, tools, workflow, service
│  │  └─ health/             # Agent 2: prompts, tools, nutrition math, service
│  ├─ integrations/          # whatsapp, email, calendar, tasks, voice, nutrition, oauth
│  ├─ gateway/               # inbound FastAPI router (WhatsApp/email/calendar/phone)
│  └─ onboarding/            # FastAPI + Jinja setup wizard (templates/index.html)
├─ services/whatsapp-gateway # Node/TypeScript sidecar (Baileys + REST bridge)
│  ├─ package.json, tsconfig.json, Dockerfile
│  └─ src/index.ts           # /health, /qr, /send, /typing -> forwards to Python
├─ deploy/postgres/init.sql  # pgvector + three schemas (mounted into container)
├─ docker/                   # python.Dockerfile, onboarding.Dockerfile
├─ scripts/                  # install.sh (macOS/Linux), install.ps1 (Windows), pull-models.sh
├─ docs/                     # 01-architecture, 02-tech-stack, 03-database-schema,
│                            # 04-agent-prompts-and-tools, 05-integrations,
│                            # 06-deployment-and-onboarding, 07-security,
│                            # 08-hardware-cost-scalability, 09-roadmap,
│                            # LOCAL_RUN_WITH_OLLAMA_CLOUD
├─ tests/                    # conftest.py, test_crypto.py, test_nutrition.py
├─ pyproject.toml, uv.lock   # Python deps + ruff/pytest config
├─ docker-compose.yml        # 7 services: postgres, redis, whatsapp-gateway,
│                            #   gateway, business-agent, health-agent, onboarding
├─ Makefile                  # setup, onboard, up, down, logs, migrate, test, fmt, clean
├─ .env.example              # every supported env var
└─ LICENSE                   # MIT
```
- `src/aia/`: one installable Python package with several entrypoints — the same container image runs each service via `python -m aia.<entrypoint>`.
- `services/whatsapp-gateway/`: only Node/TypeScript piece; thin REST bridge to Baileys.
- `deploy/`: minimal — just `init.sql` for Postgres (mounted on first boot).
- `docker/`: two Dockerfiles (shared Python image + a near-duplicate onboarding image).
- `scripts/`: cross-platform install + Ollama model pull.
- `docs/`: nine numbered design docs + a cloud-run guide.
- `tests/`: only crypto and nutrition-math unit tests; no agent behaviour or integration tests.

## 4. Architecture
Two agents share one Python package and one Postgres database, but each agent has its own schema, prompts, tool registry, and memory namespace (the README calls this "Requirement #1: fully independent agents on shared infra"). The user talks over WhatsApp; the Node Baileys sidecar posts inbound messages to the Python gateway; the gateway routes each event to one agent's Redis Stream; the agent worker consumes, reasons with the LLM router, calls tools, persists, and replies over WhatsApp.

```mermaid
flowchart LR
  WA["📱 WhatsApp"] <--> GW["whatsapp-gateway<br/>Baileys / Cloud API<br/>Node :8085"]
  GW <--> R["Redis :6378<br/>short-term mem + Streams bus"]
  R --> RT["Inbound Gateway<br/>FastAPI :8080"]
  RT --> B["Business Agent worker<br/>python -m aia.agents.business.service"]
  RT --> H["Health Agent worker<br/>python -m aia.agents.health.service"]
  B & H <--> PG[("PostgreSQL :5432<br/>schemas: core, business, health<br/>pgvector")]
  B & H --> OL["Ollama<br/>host :11434 (local LLM)"]
  B & H -. hard tasks / fallback .-> CL["Cloud LLM<br/>OpenAI / Anthropic"]
  B & H <--> INTG["Gmail · Outlook · Google/MS Calendar · Twilio · Nutrition · Notion/Todoist"]
  ONB["Onboarding wizard<br/>FastAPI :8088"] --> PG
  ONB --> GW
```

**Request/data flow end-to-end (one WhatsApp message):** the sidecar (`services/whatsapp-gateway/src/index.ts`) captures the message over the Baileys socket and POSTs `{from, text, number_tag?}` to `gateway/whatsapp-inbound` (`src/aia/gateway/main.py:74`). The router (`src/aia/gateway/router.py:route`) decides business vs. health (number_tag, slash command, keyword heuristic, optional LLM classifier). The gateway publishes an `Event` to `whatsapp.inbound.{agent}` on Redis Streams (`src/aia/events/bus.py:EventBus.publish`). The matching agent worker (`src/aia/agents/{business,health}/service.py`) consumes via consumer group, calls `agent.handle_message` (`src/aia/agents/base.py:BaseAgent`) which: (1) recalls k=5 long-term memories from pgvector, (2) fetches short-term history from Redis, (3) calls `LLMRouter.complete` (local first, cloud fallback) with the agent's tool schemas, (4) loops up to 4 hops on ` ```tool ` blocks, (5) persists the exchange to short-term memory. The reply is sent back via the WhatsApp provider (`src/aia/integrations/whatsapp/base.py:WhatsAppProvider.send_text`).

**External boundaries and trust boundaries:**
- The Node sidecar (`services/whatsapp-gateway`) is the only component that opens a WebSocket to WhatsApp servers; the Python `gateway` service receives only its HTTP POSTs (`services/whatsapp-gateway/src/index.ts: GATEWAY_INBOUND_URL`).
- Twilio voice webhooks land at `POST /webhook/twilio/voice` (`src/aia/gateway/main.py`) returning TwiML.
- Meta Cloud API verification handshake at `GET /webhook/whatsapp/cloud`; inbound at `POST /webhook/whatsapp/cloud` (`src/aia/gateway/main.py`).
- All inter-service traffic (Redis, Postgres, WhatsApp sidecar->gateway) stays inside the Docker Compose network; only the gateway (`:8080`), the WhatsApp sidecar (`:8085`), and the onboarding wizard (`:8088`) are published on host ports.
- Untrusted data enters via WhatsApp messages, webhooks, and OAuth callbacks in the wizard. The `BaseAgent` and tool handlers are the trust boundary for what reaches LLM prompts and the DB.

## 5. Data Layer
- **Database:** PostgreSQL 16 with the `pgvector` extension, three logical schemas per `src/aia/db/base.py:8-10`:
  - `core` — `tenants`, `credentials` (encrypted OAuth tokens), `conversations`, `messages`, `long_term_memory` (pgvector), `audit_logs`.
  - `business` — `clients`, `emails`, `calendar_events`, `tasks`, `call_logs`.
  - `health` — `health_profile`, `meals`, `weight_logs`, `exercises`, `targets`.
  - All tables inherit `_PK` (id UUID, `tenant_id` indexed, `created_at`) — see `src/aia/db/models.py:24-29`; `EMBED_DIM = 768` for `nomic-embed-text`.
- **Migrations:** none as Alembic yet. Bootstrap is `python -m aia.db.init` (`src/aia/db/init.py`), which is idempotent: it `CREATE EXTENSION IF NOT EXISTS vector`, creates the three schemas, then `Base.metadata.create_all` from SQLAlchemy. The Postgres container also runs `deploy/postgres/init.sql` on first boot, which sets up the same extension + schemas. The `Makefile` migrate target is `docker compose run --rm gateway python -m aia.db.init`.
- **Vector store / embeddings / retrieval strategy:** `LongTermMemory` table in `core` schema with a `Vector(EMBED_DIM)` column. `LongTermStore.recall` (`src/aia/memory/long_term.py:36`) does cosine-distance top-k retrieval scoped to `(tenant_id, agent)` so the two agents never read each other's memories. Embeddings come from `LLMRouter.embed` (defaults to `ollama/nomic-embed-text`).
- **Short-term memory:** `ShortTermMemory` (`src/aia/memory/short_term.py`) stores a rolling 20-turn list of JSON messages per `(tenant, agent, peer)` in Redis with a 7-day TTL.
- **Cache / event bus:** `redis:7-alpine` (port 6378, AOF on) used both as memory store and as the `EventBus` (`src/aia/events/bus.py`) running on Redis Streams with consumer groups for at-least-once delivery.
- **File / blob storage:** none. WhatsApp Baileys auth sessions persist to a Docker volume `wa_auth` (`.gitignore` excludes `auth_info*/`).
- **Where secrets live and how they're loaded:**
  - `load_or_create_master_key` (`src/aia/security/crypto.py:23`) reads (in order) `AIA_MASTER_KEY` env, OS keychain entry `service="aia", account="master_key"` via `keyring`, then falls back to `~/.aia_master.key` with `chmod 0o600`.
  - Per-row envelope encryption: `CredentialCipher.encrypt(plaintext)` -> `wrapped_data_key.ciphertext`, both base64 (`src/aia/security/crypto.py:54-66`). Each row uses a fresh data key (verified by `tests/test_crypto.py::test_each_row_uses_a_fresh_data_key`).
  - Credentials live in `core.credentials` with `encrypted_blob` (Text). `OAuthManager.load_token` (`src/aia/integrations/oauth.py:104`) decrypts at request time.
  - The wizard writes env values to `.env` (Docker volume bind `./.env:/app/.env`).
  - `src/aia/logging.py` has a structlog redaction processor for keys matching `token|secret|password|api[_-]?key|authorization|bearer`.

## 6. APIs and Interfaces
**HTTP endpoints (all in `src/aia/gateway/main.py`):**
- `GET /health` — liveness + WhatsApp transport status.
- `GET /models` — list models visible to the configured Ollama server (incl. `:cloud` models).
- `POST /test/message` — drive one agent turn over HTTP, local-env only (gated by `AIA_ENV=local`).
- `POST /webhook/whatsapp` — inbound from the Baileys Node sidecar; body `{from, text, number_tag?}`.
- `GET /webhook/whatsapp/cloud` — Meta Cloud API verification handshake (`hub.verify_token` + `hub.challenge`).
- `POST /webhook/whatsapp/cloud` — inbound from Meta Cloud API.
- `POST /webhook/twilio/voice` — returns TwiML bridging the call to a media-stream websocket (`ws://.../media`).

**Onboarding wizard endpoints (`src/aia/onboarding/main.py`):**
- `GET /` — dashboard (connected accounts + WhatsApp status).
- `POST /configure` — write env values (enabled agents, LLM provider/keys, allowed WhatsApp numbers) back to `.env`.
- `GET /connect/{provider}` — initiate OAuth (`google` or `microsoft`); CSRF `state` is tracked in an in-process dict.
- `GET /oauth/callback` — exchange code, store encrypted token, redirect.
- `GET /whatsapp` — render the current Baileys QR as a data-URL PNG.

**Python entrypoints (declared in `pyproject.toml [project.scripts]` and called via `python -m`):**
- `aia-gateway` -> `aia.gateway.main:main` (the FastAPI inbound router).
- `aia-business` -> `aia.agents.business.service:main` (business agent worker).
- `aia-health` -> `aia.agents.health.service:main` (health agent worker).
- `aia-onboarding` -> `aia.onboarding.main:main` (setup wizard).

**CLI commands (from `Makefile`):** `help`, `setup`, `onboard`, `up`, `down`, `logs`, `migrate`, `test`, `fmt`, `clean`. Cross-platform: `scripts/install.sh` (macOS/Linux) and `scripts/install.ps1` (Windows).

**MCP tools, webhooks, scheduled jobs:** no MCP server. Webhooks listed above. Scheduled jobs (morning brief, daily accountability, weekly checkin) are declared as async functions in `src/aia/agents/business/workflow.py:64` (`daily_summary`) and `src/aia/agents/health/workflow.py` (`daily_accountability`, `weekly_checkin`) but no scheduler is wired yet — `docs/09-roadmap.md` lists "scheduler (APScheduler/Celery)" as a Phase 1 TODO.

**Frontend routes:** the only UI is the wizard at `http://localhost:8088` (Jinja template `src/aia/onboarding/templates/index.html`); no SPA.

## 7. Configuration
**Env vars actually referenced (cross-checked `src/aia/config.py:Settings` + `.env.example`):**
- `AIA_ENV` (`local`|`hosted`), `AIA_TENANT_ID` (default `default`), `AIA_LOG_LEVEL` (default `INFO`), `ENABLED_AGENTS` (default `business,health`).
- `AIA_MASTER_KEY` (optional base64 32-byte; usually generated into keychain on first run).
- `DATABASE_URL` (default `postgresql+asyncpg://aia:aia@localhost:5432/aia`), `REDIS_URL` (default `redis://localhost:6378/0`).
- `OLLAMA_BASE_URL` (default `http://localhost:11434`), `LLM_LOCAL_MODEL` (default `ollama/llama3.1:8b-instruct-q4_K_M`), `LLM_CLOUD_MODEL` (default `openai/gpt-4o-mini`), `LLM_EMBEDDING_MODEL` (default `ollama/nomic-embed-text`), `LLM_FORCE_CLOUD` (`0`/`1`), `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_API_KEY` (only when pointing to Ollama Cloud).
- `WHATSAPP_PROVIDER` (`baileys`|`cloud`), `WHATSAPP_GATEWAY_URL` (default `http://localhost:8085`), `WHATSAPP_CLOUD_TOKEN`, `WHATSAPP_CLOUD_PHONE_ID`, `WHATSAPP_CLOUD_VERIFY_TOKEN`, `WHATSAPP_ALLOWED_NUMBERS`.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT` (default `common`).
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `DEEPGRAM_API_KEY`.
- `NUTRITION_PROVIDER` (`usda`|`nutritionix`|`openfoodfacts`), `USDA_API_KEY`, `NUTRITIONIX_APP_ID`, `NUTRITIONIX_API_KEY`.
- `TASKS_PROVIDER` (`local`|`notion`|`todoist`|`google_tasks`), `NOTION_TOKEN`, `TODOIST_TOKEN`.
- `ONBOARDING_PORT` (default `8088`), `PUBLIC_BASE_URL` (default `http://localhost:8088`).

**Config files and hierarchy:** `pydantic-settings` `BaseSettings` in `src/aia/config.py:Settings` reads `.env` at project root with `extra="ignore"`. `get_settings()` is `lru_cache`-d; all code imports it instead of reading env directly. The wizard mutates `.env` in place via `python-dotenv`'s `set_key` (`src/aia/onboarding/main.py:configure`).

**Feature flags / runtime toggles:**
- `WHATSAPP_PROVIDER` selects Baileys vs. Meta Cloud API (`src/aia/integrations/whatsapp/base.py:get_whatsapp`).
- `LLM_FORCE_CLOUD=1` flips the LLM router to always use the cloud model (`src/aia/llm/router.py:_pick`).
- `Settings.offline` is `True` when no cloud key is configured (exposed for callers that want to gate on connectivity).
- `TASKS_PROVIDER` / `NUTRITION_PROVIDER` / `WHATSAPP_PROVIDER` all act as runtime toggle keys for the relevant factory functions.

## 8. Build, Run, Deploy
**Exact commands (copied from `Makefile`):**
- `make setup` — copy `.env.example` -> `.env` (if missing), `docker compose build`, `docker compose up -d postgres redis`, run `./scripts/pull-models.sh`, then `make migrate`.
- `make onboard` — `docker compose up -d onboarding`; open `http://localhost:8088`.
- `make up` — `docker compose up -d` (whole stack).
- `make down` — `docker compose down` (keeps data volumes).
- `make logs` — `docker compose logs -f --tail=100`.
- `make migrate` — `docker compose run --rm gateway python -m aia.db.init`.
- `make test` — `docker compose run --rm gateway pytest -q`.
- `make fmt` — `ruff check --fix . && ruff format .`.
- `make clean` — `docker compose down -v` (irreversible: deletes data volumes).

**Local dev one-liner (<=5 commands):**
```bash
make setup    # build images, start postgres+redis, pull Ollama models, run migrations
make onboard  # launch wizard at http://localhost:8088
# (in the browser: connect Google/Microsoft, scan WhatsApp QR, pick nutrition provider)
make up       # start gateway + both agent workers
make logs     # tail all containers
```

**Test / lint / build / deploy (separated):**
- Test: `make test` (preferred) or `pytest -q` inside the `gateway` container.
- Lint/format: `make fmt` (ruff) or `ruff check . && ruff format .`.
- Type-check: `mypy` (declared in `[project.optional-dependencies].dev` but not wired into the Makefile).
- Build Python image: `docker compose build` (uses `docker/python.Dockerfile`).
- Build Node sidecar: `cd services/whatsapp-gateway && npm install && npm run build` (uses the local `Dockerfile`).
- Deploy: no cloud deploy script in repo. The `docker-compose.yml` and `Makefile` are local-first by design; `docs/08-hardware-cost-scalability.md` and `docs/LOCAL_RUN_WITH_OLLAMA_CLOUD.md` discuss a scale-out path (ECS/Cloud Run/K8s) and an Ollama Cloud variant. Phase 5 in `docs/09-roadmap.md` lists a "managed" plan but it is not implemented.

**Deployment platform hints:** none. No `vercel.json`, no `fly.toml`, no `render.yaml`, no `.github/workflows/`. Production is "same Docker images, larger VM" per `docs/08-hardware-cost-scalability.md`.

## 9. Testing
- **Test framework:** `pytest` (async, `asyncio_mode = "auto"`, `testpaths = ["tests"]` per `pyproject.toml`).
- **Kinds of tests present:** only **unit tests**, in two files: `tests/test_crypto.py` (envelope encryption round-trip, per-row data-key uniqueness, master-key rotation) and `tests/test_nutrition.py` (BMR Mifflin-St Jeor, TDEE, calorie target + 1200 floor, MET-based calories burned, projected weeks to goal, day-progress on-track). `tests/conftest.py` adds `src/` to `sys.path`.
- **No integration, e2e, or contract tests.** No tests for agents, the gateway, the router, the event bus, OAuth, providers, or the wizard.
- **Coverage status:** partial — the two pure-function modules are well covered; everything that touches Redis, Postgres, the LLM, or WhatsApp is uncovered.
- **How to run:** `make test` (preferred, runs inside the gateway container) or `pytest -q` after `pip install -e .[dev]`. The `dev` extra installs `pytest`, `pytest-asyncio`, `ruff`, and `mypy`.

## 10. Known Issues and TODOs
- **Explicit `# TODO(impl)` markers** (from `docs/09-roadmap.md` "TODO(impl) index" and a grep of the source):
  - `src/aia/integrations/email/gmail.py:33` — OAuth refresh in `_access_token` ("refresh with refresh_token when expires_at has passed").
  - `src/aia/integrations/email/graph.py` — flesh out Graph `send` / `create_draft` / `get_body` (only `list_recent` and `send` are implemented; `get_body` and `create_draft` are absent).
  - `src/aia/integrations/calendar/graph.py` — entire Microsoft Graph calendar adapter raises `NotImplementedError` for every method.
  - `src/aia/integrations/tasks/notion.py` and `src/aia/integrations/tasks/todoist.py` — both are full stubs (every method raises `NotImplementedError`).
  - `src/aia/agents/business/tools.py:_principal_wa_id` — always returns `None`, so `escalate` falls back to notifying the current `ctx.peer` instead of the principal.
  - `src/aia/gateway/main.py` — `/media` WebSocket route referenced in TwiML does not exist; realtime voice engine (Deepgram/OpenAI Realtime) is not wired.
  - Scheduler (APScheduler/Celery) is missing — `daily_summary`, `daily_accountability`, `weekly_checkin` are defined but never triggered.
- **No Alembic migrations** — schema is created idempotently by `Base.metadata.create_all`; production schema evolution would need Alembic migrations wired in (`alembic` is already a dep in `pyproject.toml`).
- **No CI** — there is no `.github/` directory, no GitHub Actions, no other CI config.
- **No automated test for the agents** — only the two unit-test files; the reasoning loop, router, and tool dispatch are untested.
- **OAuth state is in-process** — `src/aia/onboarding/main.py:32 _states: dict[str, str] = {}` is per-process; restart loses the CSRF state mid-OAuth.
- **WhatsApp Baileys transport violates WhatsApp ToS** — README explicitly warns to use a secondary number; no runtime guard prevents a real number being paired.
- **`email` table exists but is not populated by any code path** — `EmailProvider` returns plain `EmailMessage` dataclasses (`src/aia/integrations/email/base.py`); nothing in `gateway/main.py` polls mail and writes into `business.emails`, and `on_email` only logs and escalates from the event payload.
- **Stray file** — `aia-two-agent-local-assistant-architecture-specification.html` (~39KB design doc) at the repo root; `.gitignore` does not exclude it but the modern truth lives in `docs/01-architecture.md` (per the existing AGENT.md commentary).
- **License** — `LICENSE` is MIT; `pyproject.toml` declares `license = { text = "MIT" }`. No other IP gaps spotted.
- **Dockerfile duplication** — `docker/onboarding.Dockerfile` is a near-clone of `docker/python.Dockerfile`; could be one parameterized image.

## 11. Production-Readiness Checklist
| Area | Status | Evidence |
|---|---|---|
| Auth | ⚠️ partial | OAuth2 authorization-code flow with Google + Microsoft in `src/aia/integrations/oauth.py`; encryption at rest, but per-tenant scoping is not enforced at route level and `WHATSAPP_ALLOWED_NUMBERS` exists but is not checked in `src/aia/gateway/main.py` before publishing. |
| Secrets management | ✅ | Envelope encryption (`src/aia/security/crypto.py`), master key in OS keychain, structlog redaction (`src/aia/logging.py:21`). |
| Observability | ⚠️ partial | `structlog` JSON logs with redaction, `make logs`; no Prometheus, OTel, or metrics endpoint. |
| Error handling | ⚠️ partial | `tenacity` retry decorator on `_call` (`src/aia/llm/router.py:64`); event-bus handler logs and leaves unacked for retry (`src/aia/events/bus.py:73`); no global FastAPI error middleware, no SLOs/error budget. |
| Rate limiting | ❌ missing | No middleware in `src/aia/gateway/main.py`; webhook endpoints are unauthenticated. |
| CI/CD | ❌ missing | No `.github/workflows`, no `.gitlab-ci.yml`, no CI of any kind. |
| Backups | ❌ missing | `make clean` deletes volumes; no documented backup or restore for `pgdata` / `redisdata` / `wa_auth`. |
| Rollback | ⚠️ partial | Docker images are pinned via compose; no deployment script or version tagging convention. |
| Logging | ✅ | `structlog` JSON with secret redaction in `src/aia/logging.py`. |
| PII/GDPR | ⚠️ partial | Local-first is privacy-friendly by default; tenant isolation in schema; no retention policy file, no DSR workflow, no DPIA. |
| Cost ceiling | ⚠️ partial | Local Ollama by default (`Settings.offline` when no cloud key); cloud fallback (`LLM_FORCE_CLOUD=1`) has no spend cap. |

## 12. Next Concrete Steps
1. **Tomorrow morning: stand up the stack and run one full Health-agent loop.** `make setup && make onboard && make up`, pair WhatsApp via QR, send a meal description, confirm it lands in `health.meals` and the agent replies with kcal/macros remaining. This validates the gateway -> event bus -> agent -> tool -> reply chain.
2. **Fill the cheap `# TODO(impl)` holes that are required for the happy path:** OAuth refresh in `src/aia/integrations/email/gmail.py:33`; wire the `_principal_wa_id` lookup from `Tenant.preferences` so `escalate` actually notifies the principal (`src/aia/agents/business/tools.py`).
3. **Wire the scheduler** (APScheduler or a simple `asyncio` loop) so `daily_accountability`, `weekly_checkin`, and `daily_summary` actually fire. Without this, the agents only react; they never initiate.
4. **Add a CI workflow** at `.github/workflows/ci.yml`: `ruff check .`, `pytest -q`, and `docker compose config` (validates the compose file). This is the cheapest way to catch the `# TODO(impl)` regressions and lint drift going forward.
5. **Add an Alembic migration baseline** and re-run `python -m aia.db.init` against a clean volume to confirm parity; then switch the `migrate` Makefile target to `alembic upgrade head`.
6. **Write at least one agent behaviour test per agent** using a recorded fixture (mock LLM + mock provider) — a transcript of `send_meal -> log_meal -> daily_status` for the Health agent, and `reschedule_meeting -> check_availability -> create_meeting` for the Business agent.
7. **Document and ship a one-command Postgres backup** (`scripts/backup-pg.sh` using `pg_dump` against the `pgdata` volume) and add a `make backup` target.
8. **Add webhook signature verification** for the two unauthenticated webhook endpoints (`POST /webhook/whatsapp` from Baileys, `POST /webhook/twilio/voice`) before exposing the stack to the public internet.

**Definition of done for v0.1 (single-user laptop production):** WhatsApp message in -> correctly routed to one agent -> at least one tool called successfully -> reply in WhatsApp -> entry persisted in the matching `core`/`{agent}` table -> one CI run per PR is green.

## 13. Pointers for a Fresh Agent
**Files to read first (in order, <= 8):**
1. `README.md` — the project pitch, quick start, and WhatsApp honesty note.
2. `docs/01-architecture.md` — the current architecture (Mermaid included).
3. `docs/02-tech-stack.md` and `docs/03-database-schema.md` — why each choice, full table list.
4. `src/aia/config.py` — every env var, its default, and `Settings.offline`.
5. `src/aia/agents/base.py` — the shared reasoning loop (recall -> prompt -> LLM -> tools -> persist).
6. `src/aia/agents/business/workflow.py` and `src/aia/agents/health/workflow.py` — the two agents' event handlers and proactive entry points.
7. `src/aia/gateway/main.py` + `src/aia/gateway/router.py` — the inbound router and agent selection.
8. `docs/09-roadmap.md` — the phase plan and the full `# TODO(impl)` index.

**Files to NOT touch:**
- `aia-two-agent-local-assistant-architecture-specification.html` — historical design doc; superseded by `docs/01-architecture.md` and the numbered doc set.
- `.venv/`, `pgdata/`, `redisdata/`, `wa_auth/` — runtime/secret volumes; created and managed by Docker.
- `services/whatsapp-gateway/auth_info*/` — Baileys session; do not commit (already in `.gitignore`).
- `uv.lock` — let `uv` manage it; do not hand-edit.
- `LICENSE` — MIT; do not change.

**Anti-patterns observed in this repo (do not introduce):**
- Bypassing the LLM router — always go through `src/aia/llm/router.py`; never call `litellm` directly from agents or tools.
- Storing OAuth tokens in plaintext — always use `CredentialCipher.encrypt` / `OAuthManager.load_token` (`src/aia/integrations/oauth.py:104`).
- Cross-schema foreign keys — the two agents are isolated; do not add FKs from `business.*` or `health.*` to `core.*` user data, only to shared infrastructure.
- Reading env vars directly — always import `get_settings()` from `src/aia/config.py`.
- Returning raw exceptions to WhatsApp — the `BaseAgent` swallows loop errors and returns a best-effort summary; do not change the reply path to leak stack traces.
- Inventing new providers without using the existing factory functions in `src/aia/integrations/{whatsapp,email,calendar,tasks,nutrition,voice}/base.py`.

**If you only have 30 minutes:** run `make setup && make onboard`, get a WhatsApp message into the gateway (`src/aia/gateway/main.py:74 /webhook/whatsapp`), and trace it to the matching agent worker via `src/aia/events/bus.py:EventBus.consume`. That single end-to-end loop is the highest-leverage starting point; everything else is layered on top of it.

<!-- generated by prime-agent subagent, category=agent -->
