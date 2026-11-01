# 09 · Implementation Roadmap

This repo is a **coherent, runnable scaffold**: infrastructure, agent framework, schema, provider
abstractions, Docker stack and onboarding are real and wired together. The path below takes it to
production. Items tagged `TODO(impl)` in the code mark the exact insertion points.

## Phase 0 — Scaffold (DONE — in this repo)
- Monorepo, Docker Compose, install scripts (Win/macOS/Linux).
- Shared infra: config, LLM hybrid router, Fernet+keychain crypto, async DB, Redis event bus, two-tier memory.
- Schema + idempotent bootstrap (3 schemas, pgvector).
- Both agents: prompts, tool registries, reasoning loop, workflows, services.
- Provider abstractions: WhatsApp (Baileys + Cloud API), email (Gmail+Graph), calendar (Google+Graph), tasks, nutrition, voice.
- Onboarding wizard + WhatsApp QR pairing.
- Unit tests for nutrition math + crypto.

## Phase 1 — Make one happy path fully real (~1 week)
**Goal:** end-to-end Health agent on Baileys, fully working.
- [ ] Bring up the stack; pair WhatsApp; confirm inbound→event→agent→reply round-trip.
- [ ] Implement OAuth refresh in Gmail/Graph adapters (`_access_token`).
- [ ] Wire `log_meal` → USDA/Nutritionix; verify remaining-calorie math live.
- [ ] Implement the scheduler for `daily_accountability` / `weekly_checkin`.
- [ ] Persist conversations/messages to `core` (currently short-term only).

## Phase 2 — Business agent breadth (~1–2 weeks)
- [ ] Email poller service → `email.received`; triage + draft; urgent escalation.
- [ ] Calendar reschedule flow end-to-end (freeBusy → propose → confirm → update).
- [ ] Local tasks UX + one cloud task adapter (Notion or Todoist).
- [ ] CRM enrichment: link emails/calls/meetings to `clients`.

## Phase 3 — Voice (~1–2 weeks)
- [ ] Media-streams websocket service; integrate Deepgram Voice Agent or OpenAI Realtime.
- [ ] Inbound IVR + outbound calls; transcript → `call_logs` → summary → escalation.

## Phase 4 — Hardening (~1 week)
- [ ] Webhook signature verification (Twilio, WhatsApp Cloud).
- [ ] Alembic migrations; Postgres RLS + TLS; volume encryption.
- [ ] Dead-letter stream, retries, alerting; rate limiting.
- [ ] Native function-calling path for cloud models in the service layer.

## Phase 5 — Multi-tenant / managed (optional, ~2–3 weeks)
- [ ] Hosted OAuth proxy so end users skip app registration.
- [ ] Per-tenant KMS master keys; managed Postgres/Redis.
- [ ] Horizontal scaling (ECS/Cloud Run/K8s); observability (OTel + Grafana).
- [ ] WhatsApp Cloud API onboarding per number/line.

## `TODO(impl)` index
| Location | Work |
|---|---|
| `integrations/email/gmail.py` `_access_token` | OAuth refresh |
| `integrations/email/graph.py` | flesh out Graph calls |
| `integrations/calendar/graph.py` | implement MS calendar |
| `integrations/tasks/notion.py`, `todoist.py` | implement adapters |
| `agents/business/tools.py` `_principal_wa_id` | read principal WA id from tenant prefs |
| `gateway/main.py` `/media` | voice media-stream websocket |
| scheduler | proactive jobs (APScheduler/Celery) |

## Effort estimate
A focused engineer reaches a **dependable single-user product (Phases 1–2 + parts of 4)** in
**~3–5 weeks**; full voice + multi-tenant adds **~3–5 weeks**.
