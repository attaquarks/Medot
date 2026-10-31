# Medot — Open Decisions & Risk Register

Status: **Living document** — each item names its owner (architecture team),
trigger point, and current lean. Updated as milestones resolve them.

| ID | Decision / Risk | Current lean | Resolve by |
|---|---|---|---|
| OD-1 | **Graphiti adoption**: Supabase-native graph (A) vs Graphiti on a supported backend (B) | A for MVP behind `KnowledgeService`; run the §PoC in `05-graphiti-evaluation.md` before Milestone 3 ends | Milestone 3 |
| OD-2 | **Embedding dimension policy**: fixed 1536 + re-embed job vs per-dimension tables | Fixed 1536 + re-embed job (derived data, simplest) | Milestone 3 |
| OD-3 | **WhatsApp transport**: Baileys on the user's own number vs Cloud API vs Agent Platform | Per `03-whatsapp-connection-strategy.md` recommendation; revisit if Meta's Agent Platform opens to third parties | Milestone 5 |
| OD-4 | **JSON Schema enforcement points**: `pg_jsonschema` **is available on Supabase** (verified) — use it for SQL-side CHECK constraints on builtin record types plus app-layer Pydantic for messages | Both layers; CHECK constraints managed by migration per schema version | MVP |
| OD-5 | **Supabase free tier pausing** (7-day inactivity): runtime must degrade gracefully (offline spool) and surface re-activation in Desktop; paid tier removes pausing | Implement graceful degradation in Milestone 1; revisit tier at beta | Milestone 1 |
| OD-6 | **Local model guidance**: minimum viable local models for chat + extraction on user laptops (8 GB RAM reality) | Publish a curated model list + capability probes; test llama-class 7–8B tool-calling | Milestone 4 |
| OD-7 | **Instruction Markdown sync**: canonical copy in Supabase (`identity_instructions`) with Desktop editing; optional local export only (no two-master sync) | Supabase canonical | Milestone 2 |
| OD-8 | **Identity-deletion semantics**: archive domain vs hard-delete on user request (GDPR-style erasure) | Archive with tombstone + async hard-delete job | Milestone 2 |
| OD-9 | **Background invocation parallelism**: sequential first (simpler, deterministic) vs parallel | Sequential in MVP; parallel behind the same interface | Milestone 4 |
| OD-10 | **Windows code signing** cost/certificate choice before distribution | Decide during Milestone 8 planning | Milestone 7 |
| OD-11 | **Baileys maintenance**: upstream project volatility (breaking changes, ban waves) — keep Cloud API adapter warm as the compliance fallback | Keep both adapters tested in CI smoke | Milestone 5 |
| OD-12 | **Zep managed service**: acceptable alternative if self-hosting Graphiti proves heavy (data locality/privacy trade-off needs user input) | Self-host; revisit on cost/ops pressure | Post-MVP |
| R-1 | Extraction latency with local models may make async fact extraction minutes-long — acceptable because extraction is asynchronous; UX must not block on it | Mitigation: extraction queue + status in Desktop | Milestone 3 |
| R-2 | SQLite spool + single-process runtime is a scaling ceiling; fine for personal use, revisit only for hosted/multi-device future | Documented non-goal for MVP | Post-MVP |
| R-3 | WhatsApp template-message rules constrain proactive messaging on Cloud API; Baileys has no such limit but carries ToS risk | Transport abstraction absorbs this; per-transport UX notes | Milestone 5 |
