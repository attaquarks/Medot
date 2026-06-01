# 02 · Technology Stack

Chosen for **simplicity, cross-platform local execution, and a clean path to scale**.

## 2.1 Summary

| Concern | Choice | Why this, not the alternatives |
|---|---|---|
| Language | **Python 3.11** | Best ecosystem for LLM agents + Google/MS SDKs. One language across infra & agents. |
| Service framework | **FastAPI + Uvicorn** | Async, tiny, great for webhooks; auto OpenAPI for the gateway. |
| Agent workflow | **LangGraph** | Explicit, inspectable state machines for multi-step tool loops; better than hidden-magic frameworks for maintainability. |
| LLM access | **LiteLLM** | One API over Ollama + OpenAI + Anthropic → the hybrid router is ~80 lines. |
| Local LLM runtime | **Ollama** | One-line cross-platform install, model management, OpenAI-compatible endpoint. |
| Relational store | **PostgreSQL 16** | Battle-tested, schemas give per-agent isolation, JSON columns for flexible fields. |
| Vector store | **pgvector** | Semantic memory **inside** Postgres → no extra service to run or back up. |
| Short-term memory + bus | **Redis 7 (Streams)** | Doubles as conversation cache and durable event bus → fewer moving parts. |
| ORM / migrations | **SQLAlchemy 2 (async) + Alembic** | Async sessions; Alembic available for real migrations (bootstrap script for first run). |
| WhatsApp (default) | **Baileys** (Node sidecar) | QR pairing = non-technical onboarding; free. (Unofficial — see [05](05-integrations.md).) |
| WhatsApp (official) | **Meta Cloud API** adapter | Compliance path for client-facing use. |
| Phone/voice | **Twilio** + Deepgram/OpenAI Realtime | Twilio for PSTN; realtime engine for STT↔LLM↔TTS. |
| Secrets | **cryptography (Fernet)** + **keyring** | Envelope encryption; master key in OS keychain, never on disk. |
| Logging | **structlog** | JSON logs with a redaction processor for secrets. |
| Packaging/deploy | **Docker Compose** + Make + install scripts | One command; identical on Win/macOS/Linux. |

## 2.2 Polyglot boundary

Everything is Python **except** the WhatsApp sidecar, which is **Node/TypeScript** because the
mature unofficial WhatsApp libraries (Baileys, whatsapp-web.js) are Node-only. It is a thin
process exposing a REST bridge (`/send`, `/qr`, `/health`) and forwarding inbound messages to the
Python gateway — so the polyglot surface is tiny and well-contained.

## 2.3 Dependency manifest (Python)

See [`pyproject.toml`](../pyproject.toml). Highlights: `fastapi`, `uvicorn`, `pydantic-settings`,
`sqlalchemy[asyncio]`, `asyncpg`, `pgvector`, `redis`, `litellm`, `langgraph`, `httpx`,
`google-api-python-client`, `msal`, `twilio`, `cryptography`, `keyring`, `structlog`, `tenacity`.

## 2.4 What we deliberately avoided

- **A separate vector DB (Pinecone/Chroma/Weaviate)** — pgvector is enough at laptop scale and one fewer service.
- **Kafka/RabbitMQ** — Redis Streams covers our throughput with far less ops burden.
- **A heavyweight agent framework with opaque control flow** — explicit LangGraph + a small base loop is easier to debug and extend.
- **Kubernetes** — overkill for a laptop; the same images later run on a single VM or ECS task (see [08](08-hardware-cost-scalability.md)).
