# Medot — Open Decisions & Risk Register

Status: **Living document** — each item names its owner (architecture team),
trigger point, and current lean. Updated as milestones resolve them.

| ID | Decision / Risk | Current lean | Resolve by |
|---|---|---|---|
| OD-1 | **Graphiti adoption**: Supabase-native graph (A) vs Graphiti on a supported backend (B) | **APPROVED**: A for MVP behind `KnowledgeService`; run the §PoC in `05-graphiti-evaluation.md` before Milestone 3 ends | Milestone 3 |
| OD-2 | **Embedding dimensions**: fixed-dim column vs variable vs per-dimension structures | **RESOLVED (Stage 2)**: dimension-partitioned embedding tables (`memory_embeddings_768`, `_1024`, `_1536` — pre-declared by migration, not per-user), each with its own HNSW index; `embed_model` is a mandatory filter in every similarity query so vectors from different models are never compared; re-embed job moves rows across tables on model switch (embeddings are derived data) | Milestone 3 |
| OD-3 | **WhatsApp transport** | **DECIDED (product owner, 2026-11-01): the official WhatsApp Agent Platform exclusively.** Me. connects through the agent the user links via WhatsApp's Agent Manager; the API key is stored in the OS keystore. Baileys, Cloud API, and a Medot-owned shared number are not Me. transports (doc 03 §1). Implementation gated on: (a) provider-side registration/access spike — no public developer onboarding documented as of 2026-11-01; (b) **OD-13 relay service authorization** | WhatsApp milestone |
| OD-13 | **Medot relay service** (implied by the Agent Platform decision): always-on cloud endpoint receiving platform webhooks, queueing per-user, delivering to desktop runtimes over persistent outbound connections — the product's first server component | Needs design + cost proposal before the WhatsApp milestone; message bodies not retained beyond delivery | Before WhatsApp milestone |
| OD-4 | **Dynamic domain schemas**: no SQL migrations for user identities/records | **CONFIRMED (Stage 2)**: schema in `06-supabase-schema.md` already satisfies it — generic tables + versioned `domain_schemas` + JSONB + Pydantic + `pg_jsonschema` CHECK constraints; no per-user DDL. Guarded by a migration-lint test | MVP |
| OD-5 | **Supabase free tier pausing** (7-day inactivity): runtime must degrade gracefully (offline spool) and surface re-activation in Desktop; paid tier removes pausing | **APPROVED**: implement graceful degradation in Milestone 1; revisit tier at beta | Milestone 1 |
| OD-6 | **Local model guidance**: minimum viable local models for chat + extraction on user laptops (8 GB RAM reality) | **APPROVED**: publish curated model list + capability probes; test 7–8B tool-calling before runtime rollout (feeds the framework PoC) | Milestone 4 |
| OD-7 | **Instruction Markdown sync**: canonical copy in Supabase (`identity_instructions`) with Desktop editing; optional local export only | **APPROVED**: Supabase canonical | Milestone 2 |
| OD-8 | **Identity-deletion semantics**: archive domain vs hard-delete on user request | **APPROVED**: archive with tombstone + separate permanent-erasure process | Milestone 2 |
| OD-9 | **Background invocation parallelism** | **APPROVED**: sequential in MVP behind a replaceable orchestration interface | Milestone 4 |
| OD-10 | **Windows code signing** cost/certificate choice | **APPROVED**: decide during Milestone 8 planning; unsigned builds stay internal until then | Milestone 7 |
| OD-11 | **Baileys maintenance / dual-transport testing** | **APPROVED**: keep Baileys and Cloud API adapters separately tested in CI smoke | Milestone 5 |
| OD-12 | **Zep managed service** | **APPROVED**: reconsider only if the Graphiti PoC justifies it | Post-MVP |
| R-1 | Extraction latency with local models may make async fact extraction minutes-long — acceptable because extraction is asynchronous; UX must not block on it | Mitigation: extraction queue + status in Desktop | Milestone 3 |
| R-2 | SQLite spool + single-process runtime is a scaling ceiling; fine for personal use, revisit only for hosted/multi-device future | Documented non-goal for MVP | Post-MVP |
| R-3 | WhatsApp template-message rules constrain proactive messaging on Cloud API; Baileys has no such limit but carries ToS risk | Transport abstraction absorbs this; per-transport UX notes | Milestone 5 |
