# Medot — Architecture & Redesign Documents

This folder is the authoritative design record for the transformation of this
repository from **AIA** (a two-agent WhatsApp assistant with hardcoded
`business` and `health` agents) into **Medot** — one personal AI companion
("Me.") that develops persistent, user-visible specialist identities.

These documents do **not** replace the historical `docs/01…09` AIA
specifications; they supersede them. The old docs are retained as a record of
the existing implementation and are explicitly marked as non-authoritative for
the new direction.

## Document map

| Doc | Covers |
|---|---|
| [01-product-specification.md](01-product-specification.md) | Product identity, philosophy, users, MVP scope, explicit non-goals |
| [02-system-architecture.md](02-system-architecture.md) | Me., identities, task workers, runtime, messaging, knowledge, approvals — the core architecture |
| [03-whatsapp-connection-strategy.md](03-whatsapp-connection-strategy.md) | Transport options (Agent Platform / Cloud API / linked devices / Baileys), `fromMe` semantics, recommendation |
| [04-knowledge-graph-architecture.md](04-knowledge-graph-architecture.md) | Unified per-user graph, identity ownership, hybrid memory (episodic/semantic/records/retrieval), stale-memory protection |
| [05-graphiti-evaluation.md](05-graphiti-evaluation.md) | Deep Graphiti evaluation, backend/Windows findings, PoC plan, adoption recommendation |
| [06-supabase-schema.md](06-supabase-schema.md) | Full Supabase schema proposal, RLS design, dynamic JSONB domain records |
| [07-desktop-and-local-platform.md](07-desktop-and-local-platform.md) | Tauri 2 shell, navigation, identity detail pages, Python runtime lifecycle, local filesystem, secret storage |
| [08-providers-connectors-browser.md](08-providers-connectors-browser.md) | Model profiles, provider adapters, connector registry, browser capability |
| [09-migration-roadmap.md](09-migration-roadmap.md) | Existing-code audit, migration strategy, target repo layout, milestones 1–8, first milestone acceptance criteria |
| [12-ac1-verification.md](12-ac1-verification.md) | AC1 end-to-end verification procedure |
| [13-hosted-development.md](13-hosted-development.md) | No-local-builds policy, hosted services map, CI installer flow |
| [10-open-decisions.md](10-open-decisions.md) | Technical risks and decisions that remain open, with owners and trigger points |
| [11-framework-integration.md](11-framework-integration.md) | LangChain/LangGraph/LiteLLM/MCP integration contract, approval flow, checkpointer rules, PoC plan |

## The one governing principle

> **Medot is one personal companion, not a collection of bots.**

Everything in these documents is evaluated against it: one WhatsApp
conversation, one unified knowledge graph per user, one runtime executing any
number of persistent identities, and a desktop console that keeps the
underlying sophistication invisible.
