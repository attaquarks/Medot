# Graph Report - ai-assistant-system  (2026-10-27)

## Corpus Check
- Corpus is ~32,452 words - fits in a single context window. You may not need a graph.

## Summary
- 743 nodes · 1583 edges · 44 communities (35 shown, 9 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 105 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Persistence & Nutrition Math
- Calendar Providers
- Business Agent Tools
- Onboarding Wizard UI
- OAuth Credential Manager
- WhatsApp Sidecar Stack
- Email Providers
- Gateway Webhooks
- Task Providers
- Business Workflow & Prompts
- Baileys Transport
- Agent Core & Logging
- Nutrition Providers
- Architecture Principles (Docs)
- Business Agent Worker
- Proactive Scheduler
- Voice (Twilio) Provider
- Roadmap & Gap Register
- Docker Compose Stack
- Redis Event Bus
- Integration Contracts (Docs)
- Database Schema & Isolation
- Tech Stack Rationale
- Sidecar Build Config
- Health Agent & Nutrition Tests
- Health Agent Worker
- Security & Audit Design
- Agent Reasoning Loop
- Inbound Safety Gate
- Onboarding & OAuth Flow Docs
- Configuration & Logging
- LLM Hybrid Router
- Typed Settings
- Short-Term Memory (Redis)
- WhatsApp Sidecar Server
- Email Poller
- Test Fixtures
- Install Scripts (Shell)
- Model Pull Script
- Package Root
- Integration Interfaces
- Onboarding Package
- Project Root

## God Nodes (most connected - your core abstractions)
1. `get_settings()` - 81 edges
2. `session_scope()` - 36 edges
3. `OAuthManager` - 26 edges
4. `ToolContext` - 25 edges
5. `Base` - 21 edges
6. `get_whatsapp()` - 19 edges
7. `get_logger()` - 19 edges
8. `Event` - 18 edges
9. `_PK` - 17 edges
10. `get_router()` - 16 edges

## Surprising Connections (you probably didn't know these)
- `Smart Execution Policy (Local Default, Cloud for Hard Tasks, 100% Offline Fallback)` --semantically_similar_to--> `Hybrid LLM Decision: Local Ollama Default, Cloud Fallback`  [INFERRED] [semantically similar]
  aia-two-agent-local-assistant-architecture-specification.html → README.md
- `Zero-Trust Cryptographic Layer Principle` --semantically_similar_to--> `Envelope Encryption Design (Master Key Wraps Per-Row Data Key Wraps Token)`  [INFERRED] [semantically similar]
  aia-two-agent-local-assistant-architecture-specification.html → docs/07-security.md
- `test_tool_datetime_attaches_configured_timezone()` --calls--> `_dt()`  [INFERRED]
  tests/test_routing.py → src/aia/agents/business/tools.py
- `test_principal_falls_back_to_env_then_first_allowed()` --calls--> `principal_whatsapp()`  [INFERRED]
  tests/test_routing.py → src/aia/agents/principal.py
- `Cost Model (Local ~$0, Hybrid $0.20-0.50, Frontier $3-8, Fully Cloud $8-25 Per User/Month)` --references--> `Hybrid LLM Decision: Local Ollama Default, Cloud Fallback`  [INFERRED]
  docs/08-hardware-cost-scalability.md → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Inbound WhatsApp Message Pipeline (Sidecar -> Gateway -> Redis -> Agent Workers)** — docker_compose_whatsapp_gateway_service, docker_compose_gateway_service, docker_compose_redis_service, docker_compose_business_agent_service, docker_compose_health_agent_service [EXTRACTED 1.00]
- **Agent Isolation Mechanisms Across Prompts, Schemas and Memory** — readme_agent_isolation_requirement, docs_01_architecture_agent_isolation_matrix, docs_03_database_schema_business, docs_03_database_schema_health, docs_07_security_data_isolation [INFERRED 0.85]
- **Hybrid LLM Cost Control (Local Default, Cloud Burst, <$1/Month)** — readme_hybrid_llm_decision, docs_02_tech_stack_litellm, docs_02_tech_stack_ollama, docs_08_hardware_cost_scalability_cost_model [INFERRED 0.85]

## Communities (44 total, 9 thin omitted)

### Community 0 - "Persistence & Nutrition Math"
Cohesion: 0.06
Nodes (61): async_sessionmaker, AsyncEngine, DeclarativeBase, bmr_mifflin(), calorie_target(), calories_burned(), DayProgress, Pure nutrition / energy-balance math. No I/O, fully unit-tested. References: *… (+53 more)

### Community 1 - "Calendar Providers"
Cohesion: 0.08
Nodes (30): CalendarProvider, CalendarSlot, gaps(), ABC, datetime, Return open windows >= duration between busy intervals, sorted. Naive busy…, GoogleCalendarProvider, datetime (+22 more)

### Community 2 - "Business Agent Tools"
Cohesion: 0.09
Nodes (35): add_task(), cancel_meeting(), check_availability(), create_meeting(), draft_email(), _dt(), escalate(), inbox_summary() (+27 more)

### Community 3 - "Onboarding Wizard UI"
Cohesion: 0.10
Nodes (27): HTMLResponse, RedirectResponse, callback(), configure(), connect(), _connected(), index(), get (+19 more)

### Community 4 - "OAuth Credential Manager"
Cohesion: 0.11
Nodes (23): _expires_at(), OAuthManager, ProviderCfg, _providers(), AsyncClient, datetime, Generic OAuth 2.0 (authorization-code) manager. One small, auditable flow…, Return a valid access token, refreshing via refresh_token when stale. The… (+15 more)

### Community 5 - "WhatsApp Sidecar Stack"
Cohesion: 0.06
Nodes (33): axios, express, @hapi/boom, pino, qrcode, dependencies, axios, express (+25 more)

### Community 6 - "Email Providers"
Cohesion: 0.12
Nodes (14): EmailMessage, EmailProvider, ABC, Read / draft / send. Categorisation & urgency are done by the agent's LLM., _build_raw(), _extract_plain_text(), GmailProvider, Gmail adapter via the REST API using the stored, encrypted OAuth token. Kept… (+6 more)

### Community 7 - "Gateway Webhooks"
Cohesion: 0.11
Nodes (25): BaseModel, Response, Inbound router: turns external webhooks (WhatsApp, Twilio) into bus events and…, cloud_inbound(), cloud_verify(), _gated(), health(), list_models() (+17 more)

### Community 8 - "Task Providers"
Cohesion: 0.13
Nodes (11): ABC, datetime, TaskProvider, NotionTaskProvider, AsyncClient, datetime, Notion task provider — pages in a Notion database (NOTION_TOKEN). Expects a…, AsyncClient (+3 more)

### Community 9 - "Business Workflow & Prompts"
Cohesion: 0.15
Nodes (17): System prompt for the Business Assistant. The tool-call convention is…, daily_summary(), on_email(), on_phone(), on_whatsapp(), Business agent class + event-driven workflow handlers. Event subscriptions (see…, Triage a freshly-arrived email. The poller publishes id+sender+subject+snippet., Proactive morning brief. Triggered by the scheduler (see service.main). (+9 more)

### Community 10 - "Baileys Transport"
Cohesion: 0.11
Nodes (7): BaileysProvider, Baileys adapter — HTTP client for the Node WhatsApp sidecar. The sidecar…, ABC, Minimal transport contract the agents rely on., WhatsAppProvider, CloudApiProvider, Meta WhatsApp Business Cloud API adapter (official, compliant). Notes vs…

### Community 11 - "Agent Core & Logging"
Cohesion: 0.17
Nodes (12): BoundLogger, BaseAgent — the reasoning loop shared by both agents. One turn: 1. recall…, get_router(), LLMRouter, Hybrid LLM router. Policy: * DEFAULT -> local model (Ollama). Private, free,…, Return all models visible to the configured Ollama server. Talks to GET…, get_logger(), Two-tier memory. ShortTermMemory -> Redis. Rolling conversation window per… (+4 more)

### Community 12 - "Nutrition Providers"
Cohesion: 0.22
Nodes (12): get_nutrition_provider(), NutritionInfo, NutritionProvider, ABC, Resolve a free-text food description to macros. The agent handles portion math…, Nutrition lookup abstraction (USDA / Nutritionix / OpenFoodFacts)., NutritionixProvider, Nutritionix natural-language adapter (stub). POST /v2/natural/nutrients with… (+4 more)

### Community 13 - "Architecture Principles (Docs)"
Cohesion: 0.15
Nodes (17): AIA Agent Briefing, Repo Anti-Patterns (No Router Bypass, No Plaintext Tokens, No Cross-Schema FKs), In-Process OAuth CSRF State Lost on Restart, Sparse Test Coverage (Only Crypto + Nutrition Unit Tests), End-to-End WhatsApp Message Flow (Sidecar POST -> Router -> Redis Stream -> Agent Loop -> Reply), Event-Driven Stream Processing Principle (Immutable Events, Consumer Groups), AIA Two-Agent Architecture Specification (RFC-093, Historical HTML), Historical Spec Superseded by Numbered docs/ Set (+9 more)

### Community 14 - "Business Agent Worker"
Cohesion: 0.22
Nodes (11): Agent 1 — Business Assistant (client-facing executive assistant)., main(), _maybe_email_poller(), Business agent worker entrypoint: python -m aia.agents.business.service…, Run the poller only when an email account is actually connected., _run(), _send_daily_brief(), get_bus() (+3 more)

### Community 15 - "Proactive Scheduler"
Cohesion: 0.22
Nodes (14): _now(), datetime, Tiny asyncio scheduler for proactive agent messages. No new dependency: each…, Seconds until the next occurrence of a local time (>= 1s in the future)., Seconds until the next given weekday at a local time (today counts)., seconds_until(), seconds_until_weekday(), Scheduler maths + email poller dedupe (pure parts). (+6 more)

### Community 16 - "Voice (Twilio) Provider"
Cohesion: 0.19
Nodes (8): get_voice_provider(), ABC, Return TwiML connecting the call audio to the realtime voice engine., Start an outbound call; returns a provider call id., VoiceProvider, Phone/voice abstraction. Twilio for telephony; a voice engine (Deepgram Voice…, Twilio voice adapter. Architecture for live calls: Caller <-> Twilio PSTN <->…, TwilioVoiceProvider

### Community 17 - "Roadmap & Gap Register"
Cohesion: 0.15
Nodes (15): Missing Scheduler: Proactive Jobs Defined But Never Triggered, v0.1 Definition of Done (Single-User Laptop Production), Log a Meal Sequence (NL Food -> Nutrition Lookup -> meals Row -> Remaining Calories), Doc 04 - Agent Prompts & Tool Definitions, Business Assistant System Prompt (Read Freely Act Carefully, Escalate, CRM Memory), Business Tool Catalog (list_events, check_availability, send_email, remember_client, escalate, ...), Health & Diet Coach System Prompt (Log Meals, Coach on Trends, Not a Doctor), Health Tool Catalog (log_meal, log_weight, log_exercise, daily_status, set_goal, weekly_report) (+7 more)

### Community 18 - "Docker Compose Stack"
Cohesion: 0.21
Nodes (15): AIA Docker Compose Stack (7 Services), Compose Service: business-agent (python -m aia.agents.business.service), Compose Service: gateway (python -m aia.gateway.main, port 8080), Compose Service: health-agent (python -m aia.agents.health.service), Compose Service: postgres (pgvector/pgvector:pg16), Compose Service: redis (redis:7-alpine, AOF, port 6378), Compose Service: whatsapp-gateway (Node Sidecar, port 8085, wa_auth Volume), Ollama Choice (Cross-Platform Local LLM Runtime) (+7 more)

### Community 19 - "Redis Event Bus"
Cohesion: 0.17
Nodes (9): Handler, EventBus, Replay this consumer's un-acked messages (restart recovery). A message that…, Block forever, dispatching events to `handler`. At-least-once delivery. The…, bus_url(), fixture, Event bus integration: pending messages are reclaimed after a consumer dies.…, _redis_available() (+1 more)

### Community 20 - "Integration Contracts (Docs)"
Cohesion: 0.19
Nodes (14): business.emails Table Exists But Is Never Populated, TODO(impl) Integration Gaps Index, Reschedule Meeting Sequence (free_slots -> Propose -> Confirm -> update_event), Doc 05 - Integration Architecture, Calendar Integration (Google + Microsoft, free_slots Gap-Finding), Email Integration (Gmail REST + Microsoft Graph, LLM Does Triage), Provider Interface ABC + get_*_provider Factory Pattern, Tasks Integration (Local DB Default, Notion/Todoist/Google Tasks Drop-In) (+6 more)

### Community 21 - "Database Schema & Isolation"
Cohesion: 0.20
Nodes (14): Agent Isolation Matrix (Prompts, Tools, Memory, DB Schemas, Workers, Config), Doc 03 - Database Schema, business Schema (clients, emails, calendar_events, tasks, call_logs), health Schema (health_profile, meals, weight_logs, exercises, targets), Two-Tier Memory Model (Redis 20-Turn Window, pgvector Cosine Recall Filtered by tenant+agent), Multi-Tenancy via tenant_id + Postgres Row-Level Security, Per-Agent + Per-Tenant Data Isolation, Doc 08 - Hardware, Cost & Scalability (+6 more)

### Community 22 - "Tech Stack Rationale"
Cohesion: 0.18
Nodes (13): Doc 02 - Technology Stack, Deliberately Avoided (Separate Vector DB, Kafka/RabbitMQ, Opaque Agent Frameworks, Kubernetes), Baileys Node Sidecar Choice (QR Pairing Onboarding), Docker Compose + Make + Install Scripts Choice, FastAPI + Uvicorn Choice, LangGraph Choice (Explicit Inspectable State Machines), Polyglot Boundary Rationale (Node-Only Baileys, Thin REST Bridge), PostgreSQL 16 + pgvector Choice (Per-Agent Schemas, In-DB Vectors) (+5 more)

### Community 23 - "Sidecar Build Config"
Cohesion: 0.15
Nodes (12): src/**/*.ts, compilerOptions, esModuleInterop, module, moduleResolution, outDir, resolveJsonModule, rootDir (+4 more)

### Community 25 - "Health Agent Worker"
Cohesion: 0.24
Nodes (11): main(), Health agent worker entrypoint: python -m aia.agents.health.service Subscribes…, _run(), _send_daily_checkin(), _send_weekly_report(), principal_whatsapp(), Resolve the principal's (owner's) WhatsApp id for proactive/escalation…, Fire `fn` every day at the configured local time, forever. (+3 more)

### Community 26 - "Security & Audit Design"
Cohesion: 0.18
Nodes (12): structlog Choice (JSON Logs + Secret Redaction Processor), Idempotent Bootstrap (aia.db.init) vs Alembic Migrations, core Schema (tenants, credentials, conversations, messages, long_term_memory, audit_logs), Doc 07 - Security, Append-Only Audit Logging (core.audit_logs), Envelope Encryption Design (Master Key Wraps Per-Row Data Key Wraps Token), Production Hardening Checklist (OAuth Rotation, Webhook HMAC, RLS+TLS, Rate Limits, KMS), Master Key in OS Keychain via keyring (Never Postgres or .env) (+4 more)

### Community 27 - "Agent Reasoning Loop"
Cohesion: 0.25
Nodes (4): BaseAgent, Parse tool calls. LiteLLM normalises native function-calls into the message,…, BusinessAgent, HealthAgent

### Community 28 - "Inbound Safety Gate"
Cohesion: 0.24
Nodes (10): is_allowed(), normalize_peer(), Reduce any WhatsApp id shape to bare digits: '15551234567@s.whatsapp.net' ->…, Check an inbound peer against the WHATSAPP_ALLOWED_NUMBERS list. An empty/unset…, Inbound WhatsApp safety: peer allowlist, principal resolution, tz parsing., test_is_allowed_accepts_various_jid_shapes(), test_is_allowed_blocks_unknown_number(), test_is_allowed_open_when_no_allowlist_configured() (+2 more)

### Community 29 - "Onboarding & OAuth Flow Docs"
Cohesion: 0.20
Nodes (10): Smart Execution Policy (Local Default, Cloud for Hard Tasks, 100% Offline Fallback), Compose Service: onboarding (Setup Wizard, port 8088, Writes .env), LiteLLM Choice (One API Over Ollama/OpenAI/Anthropic), OAuth 2.0 Credential Flow (ProviderCfg, Encrypted Token Storage), Onboarding Wizard 5-Step Flow (Master Key -> OAuth -> QR -> Preferences -> Launch), Server-Side OAuth 2.0 (CSRF state, Browser Never Sees Token), Hybrid LLM Decision: Local Ollama Default, Cloud Fallback, Onboarding Wizard UI (templates/index.html, Glassmorphism Light/Dark) (+2 more)

### Community 30 - "Configuration & Logging"
Cohesion: 0.27
Nodes (7): get_settings(), Cached singleton. Import this everywhere instead of reading env directly., main(), configure_logging(), Structured logging with a redaction processor so secrets never hit the logs., _redact(), main()

### Community 31 - "LLM Hybrid Router"
Cohesion: 0.33
Nodes (4): Complexity, retry, Any, Return assistant text, transparently falling back local -> cloud.

### Community 32 - "Typed Settings"
Cohesion: 0.33
Nodes (4): BaseSettings, Typed application settings. Everything is read from environment variables…, True when no cloud LLM key is configured -> run 100% locally., Settings

### Community 34 - "WhatsApp Sidecar Server"
Cohesion: 0.40
Nodes (3): app, log, PORT

### Community 36 - "Test Fixtures"
Cohesion: 0.40
Nodes (4): db_env(), fixture, Make the `src/` layout importable during tests without an editable install., Point the app at a throwaway SQLite DB (schemas attached) + fixed master key.

## Knowledge Gaps
- **49 isolated node(s):** `aia`, `install.sh script`, `pull-models.sh script`, `name`, `version` (+44 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_settings()` connect `Configuration & Logging` to `Persistence & Nutrition Math`, `Business Agent Tools`, `Onboarding Wizard UI`, `OAuth Credential Manager`, `Gateway Webhooks`, `Task Providers`, `Business Workflow & Prompts`, `Baileys Transport`, `Agent Core & Logging`, `Nutrition Providers`, `Business Agent Worker`, `Proactive Scheduler`, `Voice (Twilio) Provider`, `Redis Event Bus`, `Health Agent Worker`, `LLM Hybrid Router`, `Typed Settings`, `Short-Term Memory (Redis)`, `Email Poller`?**
  _High betweenness centrality (0.202) - this node is a cross-community bridge._
- **Why does `session_scope()` connect `Persistence & Nutrition Math` to `Business Agent Tools`, `Onboarding Wizard UI`, `OAuth Credential Manager`, `Agent Core & Logging`, `Health Agent Worker`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Why does `OAuthManager` connect `OAuth Credential Manager` to `Calendar Providers`, `Onboarding Wizard UI`, `Business Agent Worker`, `Email Providers`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `session_scope()` (e.g. with `_credentials()` and `test_principal_prefers_tenant_preference()`) actually correct?**
  _`session_scope()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `OAuthManager` (e.g. with `test_get_access_token_raises_when_not_connected()` and `test_get_access_token_refreshes_when_expired_and_updates_row()`) actually correct?**
  _`OAuthManager` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `aia`, `install.sh script`, `pull-models.sh script` to the rest of the system?**
  _49 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Persistence & Nutrition Math` be split into smaller, more focused modules?**
  _Cohesion score 0.05775803144224197 - nodes in this community are weakly interconnected._