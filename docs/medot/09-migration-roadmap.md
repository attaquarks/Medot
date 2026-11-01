# Medot — Repository Audit, Migration Strategy & Roadmap

Status: **Stage 1 deliverable** (audit performed 2026-10-31 on `main` @
`16b631e`, clean tree, 37 tests passing + 1 environment-dependent skip).

---

## 1. Existing application audit (source-backed)

### 1.1 What the repo actually is today

A working AIA system: FastAPI Python runtime (`src/aia/`), Node/TypeScript
Baileys WhatsApp sidecar (`services/whatsapp-gateway/`), Docker Compose stack
(Postgres+pgvector, Redis), uv-managed Python project, 38 automated tests
(38 passing when Redis is up; the bus-replay integration test skips without
it), ruff clean, extensive docs. Recently hardened: OAuth auto-refresh,
Outlook/Notion/Todoist implementations, allowlist enforcement, scheduler,
email poller, bus replay.

### 1.2 Component-by-component disposition

| Component | Location | Verdict for Medot | Notes |
|---|---|---|---|
| **LLM router (LiteLLM)** | `src/aia/llm/router.py` | **Refactor & keep** | Proven local/cloud routing; becomes the provider layer under model profiles. Ollama + OpenAI + Anthropic already work. |
| **BaseAgent loop** | `src/aia/agents/base.py` | **Refactor into generic runtime** | Tool-hop loop is solid; hardcode-free after removing agent-specific prompt wiring. Tool-call parsing (fenced ```tool blocks + native calls) is a genuine asset for small local models. |
| **ToolRegistry / ToolContext** | `src/aia/agents/tools.py` | **Keep as-is** | Clean abstraction; add per-identity grant filtering + approval hook. |
| **Business/Health agents** | `src/aia/agents/business/*`, `health/*` | **Archive as seed data** | Their prompts become seed *instruction documents* and their tools become the first *tool keys*; the Python packages themselves are deleted from the runtime path. Health's nutrition math (`nutrition.py`, fully tested) migrates into a domain-record helper or a seed tool library. |
| **WhatsApp sidecar (Baileys)** | `services/whatsapp-gateway/` | **Archive** | Superseded: Me. connects via the WhatsApp Agent Platform exclusively (decision 2026-11-01, doc 03). |
| **WhatsApp Cloud API adapter** | `src/aia/integrations/whatsapp/cloud_api.py` | **Archive** | Superseded by the same decision. |
| **Gateway webhooks + router** | `src/aia/gateway/` | **Refactor** | Webhook plumbing is reusable; the keyword router (`route()`) is replaced by active-identity state + slash commands. Allowlist logic is kept. |
| **Event bus (Redis Streams)** | `src/aia/events/bus.py` | **Replace** | Redis as a *required user install* violates the Medot deployment principle. Single-process runtime + SQLite spool for offline. The replay-on-restart lesson (stable consumer, ack discipline) carries over conceptually. |
| **OAuth manager** | `src/aia/integrations/oauth.py` | **Refactor** | Token refresh + encrypted storage logic is good; storage target changes from Postgres rows to OS keystore + Supabase `connector_accounts` metadata. |
| **Email/Calendar/Tasks/Nutrition providers** | `src/aia/integrations/*` | **Keep → connector registry** | Gmail, Outlook (Graph), Google/Outlook calendar, Notion, Todoist, USDA/Nutritionix/OpenFoodFacts all implemented + tested. They become the first connectors with per-identity grants. |
| **Fernet crypto + keyring** | `src/aia/security/` | **Keep** | Envelope encryption design is sound; becomes the local secret service wrapper (Windows Credential Manager via `keyring`). |
| **Scheduler** | `src/aia/agents/scheduler.py` | **Keep** | Dependency-free asyncio scheduling for proactive messages. |
| **Email poller** | `src/aia/integrations/email/poller.py` | **Keep → connector** | Becomes a Gmail-connector capability with per-identity grant. |
| **DB layer (SQLAlchemy + pgvector, 3 schemas)** | `src/aia/db/` | **Replace** | Hardcoded `business`/`health` schemas contradict the generic model; Postgres+Redis local install violates deployment principle. Replaced by Supabase client + new schema (`06-supabase-schema.md`). |
| **Onboarding wizard (FastAPI/Jinja)** | `src/aia/onboarding/` | **Replace** | Desktop app subsumes it. |
| **Docker Compose stack** | `docker-compose.yml`, `docker/` | **Archive** | Dev convenience during migration only; not part of the product. |
| **Tests** | `tests/` | **Keep selectively** | crypto/nutrition/oauth/provider tests migrate with their code; DB-schema tests rewritten against Supabase; gateway tests rewritten. |
| **Docs 01–09, README, graphify KB** | `docs/`, `graphify-out/` | **Retain as historical record** | Marked non-authoritative; the graphify KB is a useful map of the *old* architecture. |

### 1.3 Incomplete areas in the old code (irrelevant post-migration, noted for honesty)

`business.emails` table never populated; long-term summarization beyond the
20-turn window unimplemented; voice/Twilio adapter present but unexercised.
None of these block migration; none are carried forward.

### 1.4 Reusable assets summary

Estimated **~60% of the integration/LLM/security layer is directly reusable**;
the persistence, agent-definition, routing, and deployment layers are
replaced. No big-bang rewrite is required — the runtime keeps working during
transition.

## 2. Target repository layout

```
medot/
├─ desktop/                     # Tauri 2 + React console (Windows-first)
│  ├─ src/                      # React/TS: Overview, Identities, Knowledge, …
│  ├─ src-tauri/                # Rust shell: window, sidecar supervisor, deep-link
├─ runtime/                     # Python backend (the old src/aia, reorganized)
│  ├─ medot/
│  │  ├─ api/                   # localhost service API for the desktop
│  │  ├─ coordinator/           # Me.: routing, activation state, synthesis
│  │  ├─ identities/            # registry, lifecycle, instructions, model profiles
│  │  ├─ engine/                # generic identity runtime + temporary workers
│  │  ├─ knowledge/             # KnowledgeService abstraction, retrieval, extraction
│  │  ├─ records/               # dynamic domain records (schemas, validation)
│  │  ├─ messaging/             # transport interface + cloud_api + baileys bridge
│  │  ├─ connectors/            # registry + gmail/calendar/notion/todoist/…
│  │  ├─ browser/               # Playwright service, profiles, approvals
│  │  ├─ approvals/             # approval engine
│  │  ├─ providers/             # model profiles, LiteLLM adapter, credentials
│  │  ├─ supabase/              # client, auth session, RLS-aware data access
│  │  ├─ localstore/            # workspace files, spool, logs, keystore wrapper
│  │  └─ scheduling/            # proactive scheduler
│  └─ pyproject.toml
├─ relay/                       # Medot relay service (Agent Platform webhooks -> desktop fan-out)
├─ website/                     # minimal marketing + download site
├─ supabase/                    # migrations, seed (domain_schemas), RLS tests
├─ docs/
│  ├─ medot/                    # these architecture documents (authoritative)
│  └─ …                         # AIA historical docs (retained, non-authoritative)
└─ tests/                       # runtime + desktop e2e + RLS tests
```

## 3. Migration strategy (no big bang)

Phase the repo in place; keep `main` working:

1. **Docs & skeleton** (this PR): `docs/medot/` + new folder skeleton; old code untouched.
2. **Milestone 1 — Foundation**: Supabase project + schema migrations + RLS tests; runtime gains `supabase/` + `localstore/`; Google sign-in from Desktop. AIA code still runs.
3. **Milestone 2 — Identity registry**: `identities/` with CRUD + versioned instructions + model profiles; seed Me. as the first coordinator identity.
4. **Milestone 3 — Knowledge system**: `KnowledgeService` over the new tables; ingestion from live conversations; record store + seed schemas.
5. **Milestone 4 — Generic runtime**: refactor BaseAgent → registry-driven engine; Me. coordinator + activation router; background invocation; approvals. *AIA's two agents become seed identities here and the old packages are archived.*
6. **Milestone 5 — WhatsApp**: provider-access spike (Agent Manager/API surface), relay service design + authorization (OD-13), Transport interface with Agent Platform implementation, agent-link onboarding (API key -> keystore), dedupe/ordering/reconnect. Old AIA gateway archived.
7. **Milestone 6 — Desktop console**: full UI over the local API.
8. **Milestone 7 — Connectors**: migrate email/calendar/tasks providers under the registry; browser capability.
9. **Milestone 8 — Packaging**: Windows installer, auto-update, recovery tests; macOS/Linux after.

Between Milestones 4–5 the system is straddled: legacy agents run from old
tables while the new runtime is proven in parallel. Cutover is a flag, not a
freeze.

## 4. First implementation milestone (H): Milestone 1 — Foundation

**Goal**: a signed-in, isolated foundation — the smallest slice that every
later milestone stands on, and the point where the Supabase decision is
proven in practice.

Scope:

1. Supabase project (hosted, free tier) with the `06-supabase-schema.md`
   migrations + RLS policies + seed rows (system `domain_schemas`,
   Me. coordinator identity created per user at signup via trigger).
2. `runtime/medot/supabase/`: supabase-py client holding the user session
   (Google OAuth via system browser + deep-link callback), publishable key
   only.
3. `runtime/medot/localstore/`: Windows Credential Manager wrapper
   (keyring) + workspace directory layout.
4. Desktop shell walking skeleton: Tauri 2 window with a single "Sign in
   with Google" screen and a stub Overview; Python runtime as a sidecar
   process; "Quit Medot" vs window-close behavior fixed.
5. CI: schema migrations applied to a fresh Supabase branch; RLS test suite;
   runtime unit tests.

**Explicitly out**: WhatsApp, identity creation UX, knowledge UI, connectors.

**Acceptance criteria** (each maps to a test):

| # | Criterion | Test |
|---|---|---|
| AC1 | Google sign-in from the desktop yields a Supabase user + JWT stored in the OS session | e2e: sign in, restart app, session restored without re-consent |
| AC2 | A new user's signup creates profile + user_settings + Me. identity + global domain | integration: assert rows exist post-signup |
| AC3 | RLS: user B sees zero rows of user A across ALL user-owned tables (16+ tables) | automated RLS suite run under two JWTs |
| AC4 | No privileged key material in the desktop bundle | build assertion: scan installer for `service_role` string |
| AC5 | Runtime sidecar starts with the app, survives window close, stops on Quit | e2e: process assertions |
| AC6 | Publishable-key operations (insert identity row as signed-in user) succeed; same insert with anon key unauthenticated fails | integration |
| AC7 | `uv run pytest` green; migrations idempotent (run twice) | CI |

**Test cases to write first (TDD anchors)**: RLS cross-user matrix; signup
trigger completeness; keystore round-trip; sidecar lifecycle.

## 5. Risks carried into implementation

- Supabase free-tier project pausing on inactivity (mitigation: docs +
  paid tier later; keep runtime resilient to transient DB unavailability).
- Deep-link OAuth callback on Windows needs real-device validation early
  (Milestone 1 AC1 covers it).
- Embedding model switching → re-embed job must exist before any volume of
  embeddings accumulates (open decision OD-2).
