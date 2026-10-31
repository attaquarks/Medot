# Medot — Framework Integration Contract (LangChain · LangGraph · LiteLLM · MCP)

Status: **Authorized Stage 2 deliverable** — binding contract for Milestones 2–4.
Verified against current LangChain/LangGraph docs (Oct 2026: LangGraph 1.x API-stable,
`create_agent()` is the current harness; `create_react_agent` deprecated).

---

## 0. Division of responsibility (the one-paragraph rule)

**LangChain executes a turn**: one identity, one model, its authorized tools, one
tool-calling loop. **LangGraph orchestrates workflows that outlive a turn**:
approval gates, resume-after-restart, multi-step background jobs. **Medot owns
everything persistent**: identities, instructions, grants, knowledge, memory,
conversations (Supabase) and execution checkpoints (local SQLite). A persistent
identity is never a subgraph and never framework state.

## 1. Components using LangChain

| Component | Usage |
|---|---|
| Identity runtime (engine) | `create_agent()` harness per execution — model + instructions + tools + middleware |
| Tool layer | LangChain `@tool`/structured-tool adapters over Medot `ToolRegistry` entries |
| Model layer | `ChatLiteLLMRouter`-based model factory (see §5) |
| Structured outputs | Pydantic schemas via `create_agent` response format / `with_structured_output` |
| Guardrails | `HumanInTheLoopMiddleware` (§8), tool-call retry middleware |

`create_agent()` is **instantiated per run (and cached per identity+model-profile
revision)** — a disposable execution object. It never stores identity config; the
Supabase registry stays the single source of truth. Cache key:
`(identity_id, instructions_version, model_profile_id, grants_hash)`; cache is
invalidated when any input changes.

## 2. Components using LangGraph

| Component | Usage |
|---|---|
| Coordinator orchestration | One `StateGraph` for a *turn*: route → (active identity | background invocations) → synthesize → post-turn memory enqueue |
| Approval workflow | `interrupt()` on the approval gate node; resume via `Command(resume=decision)` when the user answers over WhatsApp (Supabase `approvals` row links thread) |
| Durable multi-step workflows | email-draft → approve → send; scheduled briefs; connector flows spanning restarts |
| Checkpointing | `SqliteSaver` (`langgraph-checkpoint-sqlite`) — local file per user, verified suitable for single-user desktop use |

**Not** one LangGraph graph per identity. Identities are invoked as *agents
inside* the coordinator/workflow graphs via a node that calls the LangChain
harness. StateGraph vs Functional API: **use `StateGraph` for the coordinator and
approval flows** (need explicit state shape + interrupts); the Functional API may
be adopted later for simple sequential background jobs if it proves simpler —
choose the simpler per case, documented at adoption.

## 3. Replacing the AIA `BaseAgent` loop

The AIA loop (`src/aia/agents/base.py`) is **retired at Milestone 4 cutover**; its
proven ideas are carried into the harness configuration:

- Fenced ```tool```-block parsing for small local models → a **fallback tool-call
  parser** (LangChain output parser/middleware) used when a profile declares
  `tool_calling: "native" | "fenced" | "auto"`.
- `_looks_hard` complexity hint → coordinator routing metadata, not a harness feature.
- Recall/persist hooks → replaced by KnowledgeService retrieval injection (§7) and
  post-turn memory enqueue in the coordinator graph.

## 4. ToolRegistry ↔ LangChain tools

Medot remains the **authority**; LangChain is the **interface**:

```
ToolRegistry (tool definitions + grants + approval policy)   ← Medot, Supabase-backed
      │  build_authorized_tools(identity, ctx)  — server-side filter by grants
      ▼
List[langchain_tool]  (adapter: Medot Tool → @tool with pydantic args schema)
      │  passed to create_agent(model=…, tools=…, middleware=[hitl_middleware])
      ▼
Model discovers & invokes → adapter re-validates: authenticated user, identity,
grants, approval requirement → only then dispatches to the AIA-proven handler
```

Every adapter invocation **re-checks grants and approvals server-side** — the model
can choose tools, never grant them. Existing AIA integration handlers
(email/calendar/tasks/nutrition) are wrapped as `Tool` entries unchanged. Approval-
requiring tools raise the LangGraph interrupt (§8) instead of executing.

## 5. LiteLLM ↔ LangChain model factory

**Verified limitation**: `ChatLiteLLM` (langchain-litellm) resolves credentials via
**process-global environment variables** (docs show `os.environ["OPENAI_API_KEY"]=…`)
— unacceptable for per-identity, per-user credential isolation.
**Adopted path**: `ChatLiteLLMRouter`, which passes `api_key`/`api_base` **per
deployment** in `model_list[*].litellm_params` — Medot builds one router per model
profile with credentials resolved from the OS keystore:

```
Identity.model_profile_id → model_profiles row (provider, model, api_base, params)
  → credential_ref → OS keystore → litellm.Router([{model_list entry}])
  → ChatLiteLLMRouter(router=…, model_name=…)   ← instance-scoped, no env vars
```

Fallback (if the PoC exposes gaps, e.g. streaming/structured-output parity): a thin
`BaseChatModel` adapter calling `litellm.acompletion(**kwargs)` with per-call
`api_key`/`api_base` — LiteLLM remains the provider layer either way. Per-profile
coverage: Ollama (`ollama_chat/…`, explicit `num_ctx`), OpenAI, Anthropic,
OpenAI-compatible (`openai/…` + `api_base`). **Pre-M4 PoC must verify** native +
fenced tool calling and structured output per provider class.

## 6. Identity-specific model profile resolution

`resolve_model(profile_id) -> ChatLiteLLMRouter` — pure factory: registry row +
keystore credential → model instance. Profiles carry `purpose` (chat/extraction/
embedding/planning) and `capabilities` (tool_calling mode, structured_output,
embedding_dim, task_prefix). Memory extraction binds to the user's `extraction`
profile **only**; no cross-profile fallback for private content (OD carried).

## 7. Knowledge context injection

The coordinator graph's retrieve node calls `KnowledgeService.retrieve(scope,
query)` (bounded, freshness-aware per doc 04 §5) and writes a compressed context
block into graph state; the harness receives it as a system-segment (instructions
→ domain context → conversation). No framework component reads the graph directly.

## 8. Approvals: interrupt → Supabase → WhatsApp → resume

```
tool requires approval → HumanInTheLoopMiddleware / interrupt(payload)
  → run paused; checkpoints persisted (SqliteSaver, thread_id = run)
  → approvals row (pending, payload, expires 24h) in Supabase
  → Me. sends WhatsApp proposal; user replies YES/NO (allowlist-checked)
  → gateway matches reply → Command(resume=decision) with same thread_id
  → tool executes exactly once (idempotency key in approval payload)
  → outcome logged to activity_events; approvals row updated
```
Expired approvals resume as `denied` automatically. Checkpoint data is execution
state only; Supabase remains canonical for identity/conversation/approval records.

## 9. Checkpointer thread IDs

`thread_id = f"u:{user_id}:c:{conversation_id}:r:{run_id}"` (≤255 chars).
Isolation: one **SQLite file per user** under the workspace
(`state/checkpoints/{user_id}.sqlite`) + `user_id` in the thread prefix as
defense-in-depth. Pruning: checkpoints older than 30 days or superseded runs are
deleted by a startup sweep (LangGraph checkpoint growth is unbounded by default).

## 10. What stays ordinary Python (deliberately unwrapped)

- Supabase data access, keystore, local paths, spool.
- Knowledge/record stores and retrieval (no LangChain retriever abstraction — our
  freshness/ownership rules don't map onto it).
- Transport adapters, scheduler, connector token refresh.
- Nutrition/measurement calculators (pure functions with tests).
- Anything that would only wrap a function call in framework ceremony.

## 11. Proof of concept (due before Milestone 4 ends)

`experiments/framework-poc/` (isolated deps, synthetic data, no production imports):
1. Dynamic identity (rows → harness) executed via create_agent + ChatLiteLLMRouter
   with keystore-injected credentials (Ollama **and** OpenAI-compatible).
2. Tool grant filtering (one granted, one denied tool) with server-side enforcement.
3. LangGraph approval flow: interrupt → SQLite checkpoint → simulated WhatsApp
   resume → exactly-once tool execution.
4. Structured-output extraction against the extraction profile.
Recorded results feed back into this document before the runtime adopts it.
