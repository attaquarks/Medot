# Medot — Graphiti Evaluation

Status: **Stage 1 deliverable** — research verified against official sources
on 2026-10-31 (graphiti-core 0.31.2, current docs).

> Recommendation up front: **Supabase-native knowledge graph (Approach A) for
> the MVP**, Graphiti deferred as an optional backend (Approach B) behind the
> `KnowledgeService` abstraction, with a small proof-of-concept scheduled
> before Milestone 3 ends. The decisive fact: Graphiti has **no Postgres
> backend and will not get one** (officially closed), and every backend it
> *does* support conflicts with the "no Docker/Neo4j/graph-DB installs for
> desktop users" requirement on Windows.

---

## 1. What Graphiti is (verified current state)

`graphiti-core` 0.31.2 (Apache-2.0, Python ≥3.10) — a temporal knowledge
graph: LLM-driven extraction of entity nodes and temporal "fact" edges from
**episodes** (message/text/json), with automatic deduplication, contradiction
handling (`invalid_at` on edges), hybrid retrieval (BM25 + semantic + RRF,
16 search recipes), optional cross-encoder reranking, and community detection.

Key API (verified in 0.31.x):

```python
graphiti.add_episode(
    name=..., episode_body=..., reference_time=now,
    source=EpisodeType.message, group_id=user_namespace,
    entity_types={"Person": Person, ...},   # Pydantic models, per-call
    edge_types={...}, edge_type_map={...},
    custom_extraction_instructions=...,
)
graphiti.search(query, center_node_uuid=domain_root, group_ids=[...])
graphiti.remove_episode(episode_uuid)
graphiti.nodes.entity.delete(...) / delete_by_group_id(group_id)  # nodes only
```

Notes: the OSS library has **no "v4"** (v4 is Zep's platform API generation —
a common confusion; old v2/v3 examples do not match 0.31.x, which moved to a
namespace API `graphiti.nodes.entity.save/delete`); `add_episode` runs a
multi-step LLM pipeline and is documented to be run as a **background
process**; a separate `small_model` handles cheap classification.

## 2. Backends & the Supabase question (verified)

| Backend | Extra | Windows native | Process model | Verdict for Medot |
|---|---|---|---|---|
| **Neo4j 5.26+** | core dep | **Yes** (Desktop/Community installer) | Local server (JVM) | Escape hatch; too heavy to require of end users |
| **FalkorDB** | `[falkordb]` | No (Linux/Docker only) | Docker container | Excluded (no-Docker rule) |
| **FalkorDBLite** | `[falkordblite]` | **No** — Linux/macOS wheels only; docs suggest WSL for Windows | Embedded | Excluded (Windows rule) |
| **Kuzu 0.11.3** | `[kuzu]` | **Yes** — pip win_amd64 wheels, fully embedded | In-process | Only zero-install option — **but upstream archived Oct 2025 and Graphiti's extra is slated for removal** (dead end) |
| **Neptune** | `[neptune]` | n/a | AWS service | Excluded |
| **Postgres/Supabase** | — | — | — | **Not supported.** Feature request issue #779 closed *as not planned* (Sep 2026); no official or established community driver; Zep CE's Postgres usage was metadata/vectors only, never Graphiti-on-Postgres |

**Conclusion**: Graphiti cannot run on Supabase, and on a Windows-first,
no-extra-installs desktop product its only compliant backend is a deprecated
one. That rules out Graphiti as the MVP's primary store.

## 3. group_id — namespacing, not security (verified)

Official docs: *"A namespace filter does not replace application
authorization… Your application must authorize each `group_id` value before
it passes the value to Graphiti."* Nodes/edges carry a **single** group_id;
search takes `group_ids` filters. On FalkorDB a group_id even maps to a
physically separate database.

**Medot model**: one graph per **user** (`group_id = f"user:{user_id}"` — a
single namespace per user keeps cross-domain relationships possible), with
identity ownership represented by Medot's own metadata (domain roots +
owner_identity_id in Supabase, mirrored as domain-root entities), **not** by
per-identity namespaces. Authorization is enforced in the application layer
at every call; Graphiti never sees an untrusted namespace value. Relevance
ranking (node-distance reranking around a domain root) is treated purely as
ranking — never as filtering-for-permission.

## 4. Dynamic identities & schemas (verified feasible)

`entity_types`/`edge_types` are plain `dict[str, type[BaseModel]]` per call —
so a **stable ontology + runtime-constructed Pydantic models** can represent
arbitrary user-created identities without generating Python source:

- Medot ships a fixed core ontology: `Person`, `Goal`, `Event`, `Preference`,
  `Organization`, `Place`, `Topic`, `Record` + generic relation types with
  per-domain relation vocabularies (`domain_schemas`).
- Domain specificity comes from *instructions + relation vocabularies +
  record types*, not from new entity classes ("Health", "Gardening" are
  domain roots, not types).
- `pydantic.create_model()` builds per-domain type variants from user config
  when genuinely needed.
- Schema evolution: adding attributes is non-breaking; pre-typed data keeps
  working; **retyping requires re-ingest** — acceptable because Medot's
  canonical data lives in Supabase and can re-emit episodes.

## 5. Providers & model requirements (verified)

- LLM clients: `OpenAIClient` (default, `/v1/responses`), **`OpenAIGenericClient`**
  for OpenAI-compatible endpoints — the required path for **Ollama** (which
  lacks `/v1/responses`), `AnthropicClient`, Gemini/Groq/Azure clients.
- Embeddings: OpenAI/Azure/Gemini/Voyage/sentence-transformers. **Anthropic
  and Groq provide no embeddings** (and Anthropic no reranker) — a Medot user
  with an Anthropic-only chat profile still needs an embedding profile;
  Graphiti's docs themselves pair Anthropic with OpenAI embeddings.
- Cross-encoder reranker **optional** (RRF/MMR recipes need none); local
  `BGERerankerClient` exists.
- Structured output: strongly recommended; smaller models are explicitly
  warned about ("incorrect output schemas and ingestion failures,
  particularly when using smaller models").
- **Privacy consequence**: extraction is multi-LLM and token-heavy with no
  official per-episode cost figures (the Zep paper reports ~2–2.5 s/turn on
  managed infra). Medot's policy stands: extraction uses the user's
  configured extraction profile only — never silently rerouted — and runs
  asynchronously. If a user's extraction model is weak, extraction quality
  degrades; Medot surfaces extraction status in Desktop rather than failing
  silently.

## 6. Deletion / correction / provenance (verified)

- Temporal: edges carry `valid_at` / `invalid_at` / `expired_at`;
  `add_episode` **automatically invalidates contradicted edges** — matches
  Medot's stale-memory contract natively.
- Correction = ingest a new contradicting episode (or manual edge edit);
  there is no dedicated "correct this fact" API.
- Deletion: `remove_episode`, node/edge deletes, **`delete_by_group_id` for
  nodes** (per-user wipe exists) — but *edges* have no group-wise delete
  (enumerate + delete or episode cascade). Medot's hard-delete job must
  handle edges itself. Provenance: `get_nodes_and_edges_by_episode`.

## 7. Managed alternative: Zep (verified)

Zep (commercial) runs Graphiti internally on their managed service with
SOC 2/HIPAA governance; **Zep Community Edition is deprecated** (moved to
legacy). Zep Cloud is the only "no-ops Graphiti" path — a privacy/latency/
cost trade-off deferred to post-MVP (OD-12).

## 8. Approach A vs Approach B (the actual comparison)

| Concern | A: Supabase-native | B: Supabase + Graphiti backend |
|---|---|---|
| User installs | None (already required for auth/DB) | None for Supabase **+** Neo4j/Kuzu process or Docker |
| Canonical store | One (Postgres) | Two (Postgres + graph DB) — sync problem |
| Sync/consistency | Trivially consistent | Episodic writes duplicated; deletion/correction must propagate both ways; versioning drift risk |
| Cross-domain relationships | Native (edges unrestricted) | Native within one group_id namespace |
| Hybrid retrieval (BM25+vector+graph rerank) | Buildable: pgvector HNSW + Postgres FTS + bounded traversal + app-level rerank | Built-in (16 recipes) |
| Temporal facts | App-managed `valid_from/valid_to` (§06 schema) | Built-in `valid_at/invalid_at` + auto-invalidation |
| Extraction pipeline | Medot-owned LLM calls (simpler, model-flexible, works with weak local models) | Graphiti's pipeline (stronger default quality with strong models; officially shaky with small models) |
| Windows-first MVP | ✅ | ⚠️ only via dead-end Kuzu or a Neo4j install |
| Effort to MVP | Moderate (well-understood) | High (two stores + driver + ops) |

**Decision**: Approach A for MVP. The features Graphiti would add (rich
temporal invalidation, hybrid search recipes) are exactly the parts Medot can
implement incrementally in Postgres *behind the `KnowledgeService`
abstraction* — and the abstraction makes Approach B a plug-in upgrade when
the PoC proves the quality/cost case (e.g. for users with strong cloud
models).

## 9. Graphiti proof-of-concept plan (still required before Milestone 3)

Isolated prototype in `experiments/graphiti-poc/` (own venv, own deps, no
production imports), synthetic Health/Business/Education data:

1. Ingest 30–50 realistic conversation episodes per domain (three users for
   isolation).
2. Create domain-root entities; per-call dynamic entity types from user
   config (validating §4).
3. Update a temporal fact; confirm automatic invalidation of the old edge.
4. Retrieve around the Health root (`center_node_uuid`) with `group_ids`
   isolation; verify cross-domain retrieval (one graph, multiple domains).
5. Delete a user (`delete_by_group_id` + manual edge cleanup); verify zero
   residue.
6. Record: extraction latency/token cost per episode on (a) OpenAI-mini-class
   and (b) a local 8B model via `OpenAIGenericClient`; failure rates.

Success bars: <8 s and <15k tokens per episode on the cloud profile;
isolation leaks = 0; invalidation correctness = 100% on planted
contradictions. **If the PoC passes, Graphiti becomes an optional
`KnowledgeService` backend (Approach B) for strong-model users post-MVP;
otherwise the Supabase-native implementation stands alone.** Either way the
`KnowledgeService` interface (domain-scoped `get_current`/`get_known`,
temporal writes, per-user wipe) is the contract that must not leak Graphiti
types.
