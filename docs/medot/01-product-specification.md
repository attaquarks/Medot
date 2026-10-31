# Medot — Product Specification

Status: **Proposed v1 — pending review** (Stage 1 deliverable)
Supersedes: the AIA product concept in `README.md` and `docs/01–09`.

---

## 1. Identity

**Medot** is a personal AI companion that develops specialized knowledge and
capabilities around different areas of a user's life.

- The conversational assistant is **Me.** — the permanent coordinator the user
  talks to.
- Primary interface: **one WhatsApp conversation**.
- Secondary interface: **Medot Desktop** — a management console, not a chat
  surface.
- Target platforms: Windows first, then macOS/Linux.

## 2. Who it is for

Ordinary people who use WhatsApp: students, professionals, business owners,
parents, senior citizens, people managing health/routines/hobbies. The
operating benchmark is: *an elderly person must be able to use Medot without
understanding agents, prompts, models, graphs, or automation.* Every technical
concept (identity, knowledge domain, model profile, connector) must surface as
plain language in the UI.

## 3. Core philosophy — one companion, not a fleet

Three explicit design commitments:

1. **One WhatsApp conversation.** All specialist identities live *inside* the
   single conversation with Me. No per-domain bots, no per-domain WhatsApp
   agent slots, no second numbers for specialists.
2. **Persistent identities, not temporary subagents.** A specialist identity
   (Health, Education, Gardening, …) is a durable, user-visible configuration
   with its own instructions, knowledge scope, model profile, tools, and
   permissions. It survives restarts and is *not* an agent-framework subagent.
3. **A growing knowledge system, not a chat log.** The user's life is
   represented as a structured, temporal knowledge graph with episodic memory
   and structured records — selectively retrieved, never dumped into context.

## 4. Me. — coordinator responsibilities

Me. is permanent. It is never replaced when an identity is active; it *delegates*.

| # | Responsibility |
|---|---|
| 1 | Natural conversation with the user |
| 2 | Understand and classify incoming requests |
| 3 | Maintain user-level context and preferences |
| 4 | Manage the identity registry (create/configure/activate/deactivate/delete) |
| 5 | **Suggest** creating an identity when a domain becomes meaningfully complex — always with user confirmation |
| 6 | Route conversations to the active identity; invoke identities in the background |
| 7 | Synthesize multi-identity results into one understandable reply |
| 8 | Enforce permissions/approvals before consequential actions |
| 9 | Keep system-level control (never lose the conversation) |

## 5. Specialist identities

Identities are **data, not code**. There is no hardcoded list — Health and
Business in the old system become *seed examples* at most, and the runtime must
be able to execute an identity for **any** domain (the proof case in the MVP is
Education or Gardening, not Health).

An identity record contains (see `06-supabase-schema.md` for the tables):

- **Identity information** — id, user_id, name, description, slug (command
  name), icon, status, created_at, knowledge-domain root reference.
- **Instructions** — an editable instruction document (AGENT.md-style) with
  version history.
- **Knowledge** — ownership of one logical domain in the unified user graph,
  retrieval configuration, a short summary kept in Me.'s global context.
- **AI configuration** — a model profile (provider, model, generation
  settings, fallback) referencing a securely stored credential.
- **Capabilities** — tool grants, connector grants, browser permissions, MCP
  servers.
- **Execution** — activity history, pending approvals, persistent state.

Creating an identity creates **rows and a logical knowledge scope** — never a
Python module, container, service, or WhatsApp connection.

## 6. Interaction model

- `/health` → activates the Health identity for subsequent messages; state
  persists until `/medot`, another `/slug`, or an explicit change.
- `/medot` → returns to the coordinator. `/identities` → dynamic list.
  `/help` → dynamic help.
- Commands are **generated from identity slugs at runtime** — no hardcoded
  command table. Ordinary messages are *never* re-interpreted as routing
  commands (activation is a deliberate state change, not per-message
  classification).
- Background invocation: Me. may invoke one or more identities without
  changing the active mode (e.g. "check my meal plan and my latest business
  lead" → parallel Health + Business queries → one synthesized reply with
  visible attribution in the activity history).

## 7. MVP experience (the contract for v0.1)

1. User downloads Medot Desktop and signs in with Google (Supabase Auth).
2. Account initialization creates the user root, Me., and default settings.
3. User connects **one** WhatsApp conversation (Me. is the WhatsApp identity).
4. User configures an AI model (provider + key, stored in the OS keystore).
5. User messages Me.; Me. converses, extracts meaningful facts, and maintains
   the user's knowledge graph.
6. When a domain accumulates real complexity, Me. **asks** to organize it into
   an identity; the user confirms; the identity is created with its own scope,
   instructions, model profile, and tools.
7. The identity appears in Desktop; the user can inspect and edit everything.
8. `/slug` activation persists across messages; `/medot` returns control.
9. Me. performs background invocations and answers from **current**
   identity-owned data (never from stale summaries).
10. Facts have temporal validity and source references; corrections and
    contradictions update the graph.
11. User data is isolated per authenticated user (RLS-tested).

A non-health identity (Education or Gardening) must be creatable **without any
schema or code change** — that is the proof of dynamism.

## 8. Explicit non-goals for MVP

Hosted/multi-device cloud sync, billing, agent marketplaces, multiple
WhatsApp identities, complex agent-to-agent frameworks, advanced voice,
connector marketplaces, unrestricted autonomous browsing. Architecture must
*permit* these later (see `10-open-decisions.md`) but the MVP must not carry
them.

## 9. Quality principles

- Simple, permanent solutions over clever abstractions.
- Every architecture contract gets automated tests.
- Nothing is reported as "done" until tested (unit + integration).
- Windows compatibility is a **requirement**, not a nice-to-have, for every
  dependency (no WSL-only or Linux-only components).
- No privileged credentials ever ship in the desktop app.
