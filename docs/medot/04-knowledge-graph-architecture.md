# Medot — Unified Knowledge Graph & Memory Architecture

Status: **Proposed v1 — pending review** (Stage 1 deliverable)
Implementation evaluation: see `05-graphiti-evaluation.md`.

---

## 1. One graph per user

Each authenticated user owns **one** unified personal knowledge graph: a
network of entities and temporal relationships — not a chat log, not a
Markdown file tree, and not a fixed-depth tree.

Illustrative shape (domains are dynamic, never hardcoded):

```
User (root)
├── Health          ← domain root (may be owned by the Health identity)
│   ├── Diet / Meal plans / Medication / Measurements / Goals
├── Business        ← domain root (may be owned by the Business identity)
│   ├── Leads / Clients / Meetings / Invoices
├── Education       ← domain root (may be owned by the Education identity)
│   ├── Subjects / Courses / Assignments / Exams / Grades
├── Daily Life / Hobbies / Family / Travel / … (created on demand)
└── Global (Me.-owned): preferences, routines, people, user profile facts
```

A person ("Dr. Saleem", "my sister Ayesha") is a **global** entity that edges
may connect into any domain — cross-domain relationships are a first-class
requirement (a doctor's appointment belongs to Health *and* the calendar).

## 2. Identity ownership = metadata, not partitioning-by-copy

When an identity is created for an existing domain:

1. The existing domain root is **kept where it is**.
2. The identity is recorded as the **owner** of that domain's detailed scope
   (`knowledge_domains.owner_identity_id`).
3. Me. keeps the root node, a **summary**, and a **pointer** in its global
   context — never the detailed sub-tree.
4. Future detailed updates for that domain are written through the owning
   identity's scope.

Consequences (all mandatory):

- No duplication of detailed knowledge when ownership moves.
- No deletion of the original domain root.
- Cross-domain edges are never broken by ownership changes.
- Me. retains *read across the graph* via explicit application-layer
  permission checks; an identity reads its domain plus entities explicitly
  shared into it (e.g. the global People list if granted).
- Ownership metadata (`domain_id`, `owner_identity_id`, scope root ids) lives
  on the domain record and on nodes/edges — **retrieval relevance is not
  authorization**; filtering by ownership happens in application code, not by
  trusting a similarity rank.

## 3. Hybrid memory — four layers

| Layer | Content | Store |
|---|---|---|
| **A. Episodic** | Source messages, user observations, documents + references, decisions | `memory_episodes` (Postgres) + content refs; embeddings in `memory_embeddings` |
| **B. Semantic graph** | Entities, temporal relationships/facts, domain membership, provenance | Knowledge graph (Supabase-native or Graphiti — see 05) |
| **C. Structured records** | Measurements, meals, medication schedules, tasks, assignments, leads, meetings | `domain_records` (JSONB + typed schemas, see `06-supabase-schema.md`) |
| **D. Retrieval** | Query classification → domain selection → graph/record/episodic retrieval → compression → freshness verification | Application service |

Layer C is the canonical store for *record-shaped* facts ("weight 74.2 kg on
2026-11-02", "metformin 500mg twice daily"). The graph holds the *semantic*
version ("User has been tracking weight; trend decreasing since October") and
links to records via provenance. Never store the same fact twice without a
link.

## 4. Selective writing (memory discipline)

Not every message becomes memory. The ingestion pipeline:

1. **Canonical-first**: for structured events (a meal logged, a measurement, a
   task created), persist the `domain_records` row immediately and
   synchronously — this is the durability guarantee.
2. **Asynchronous extraction**: the episode is queued for LLM-driven fact
   extraction (entity/relation proposals) on a background worker.
3. **Extraction rules**: propose facts only when they are durable (not
   phatic/small talk), resolve entities against existing nodes (dedupe by
   identity + name/type), detect **contradictions with current facts** →
   supersede with `valid_to`/`invalid_at` (never delete history), attach
   **provenance** (episode id, message id, timestamp, extraction confidence).
4. **User corrections** ("no, I stopped that medication") are treated as the
   highest-priority update: they invalidate the affected facts immediately.
5. **Privacy policy**: extraction runs on the user's configured extraction
   model — never a different provider "as fallback" for memory content. If the
   extraction model is unavailable, extraction is deferred, not rerouted
   (see `05-graphiti-evaluation.md` §7).

## 5. Selective retrieval (context discipline)

Never load the whole graph. Per turn:

1. **Classify** the query: global / one domain / multiple domains.
2. **Route**: direct answer for global; invoke owning identity for domain
   queries (active mode or background invocation).
3. **Retrieve** inside the owning scope: domain-root-centered graph neighborhood
   (bounded hops, ranked), relevant `domain_records` (typed queries), recent
   episodes (semantic + keyword, small top-k).
4. **Compress** to a context block: facts with timestamps + validity, record
   summaries, source references. Budgeted (a few KB), never "everything".
5. **Verify freshness**: any fact presented as *current* must be either (a)
   retrieved from the owning domain now, or (b) clearly labeled with its
   as-of date. Historical vs current is a first-class rendering distinction.

## 6. Stale-memory protection (the contract)

Scenario: Health owns meal-plan knowledge; Me.'s global summary says only
"has a meal plan". User asks Me. directly: "What is my latest meal plan?"

**Required behaviour** (testable contract):

1. Me. recognizes the query targets a delegated domain (summary pointer says
   authoritative data lives in Health).
2. Me. invokes Health in the background (active mode unchanged) and answers
   from the retrieved, timestamped current record.
3. If retrieval fails, Me. says so explicitly ("I can't reach your Health
   space right now — the last thing I know is from **2 Nov**") — never presents
   the stale summary as current.
4. Every answer sourced from memory carries source references and as-of
   timestamps in the activity history, and critical values (medication,
   money) are restated with their date in the reply.

This is enforced by a knowledge-service API shape that forces the choice:
`get_current(domain, topic)` (live fetch, may fail) vs
`get_known(domain, topic)` (may return stale, flagged). Me.'s system
instructions prohibit answering "what is my X" from `get_known` alone.

## 7. What we deliberately do NOT do

- No fixed depth limits (10/15 nodes) — domain complexity is measured by
  accumulated entities, records, recurring workflows, and retrieval needs.
- No Markdown-file memory as the system of record (Markdown is an *export/
  editing* affordance for instructions, not memory).
- No per-identity separate graphs/namespace-per-identity as the primary model
  (breaks cross-domain relationships and the unified-life goal).
- No EAV free-for-all: structured records are schema-validated JSONB with
  registered types, not unbounded attributes.
