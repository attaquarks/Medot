# Medot — AI Providers, Connectors & Browser

Status: **Proposed v1 — pending review** (Stage 1 deliverable; provider
findings verified against current LiteLLM/LangChain docs, Oct 2026)

---

## 1. Model profiles

Every agentic surface (Me., each identity, temporary workers) resolves its
behavior through a **model profile** row (see `06-supabase-schema.md`):

```
model_profiles:  provider · model · api_base · params · credential_ref · purpose · capabilities
```

- `purpose` distinguishes `chat` / `extraction` / `embedding` / `planning`.
  Different operations may use different models — e.g. a small local model for
  chat, a stronger one for memory extraction, and a dedicated embedding model.
- `credential_ref` is an **OS-keystore alias**, never a key value (Part 9
  requirement: keys separate from model configuration).
- `capabilities` records what the model is *declared* to support
  (`tool_calling`, `structured_output`, `embedding_dim`), so the runtime can
  degrade gracefully instead of crashing on an unsupported model.

## 2. Provider layer (LiteLLM)

LiteLLM stays as the single model surface (it is already proven in this repo's
AIA code and verified current at v1.106.x, Oct 2026):

| Provider | Usage |
|---|---|
| Ollama | `ollama_chat/<model>` prefix (not `ollama/`); set `num_ctx` explicitly — Ollama defaults to **4096 tokens context**, which silently truncates memory-augmented prompts |
| OpenAI / Anthropic | direct provider prefixes |
| OpenAI-compatible | `openai/<model>` + `api_base` (works for LM Studio, vLLM, Ollama's `/v1`, …) |

Known reliability notes (verified):

- Ollama tool-calling varies by model; LiteLLM falls back to JSON-mode tool
  calls when native calling is unsupported. Profiles must declare
  `supports_function_calling` honestly; the runtime prefers known-good local
  models.
- Structured output: use `response_format={"type":"json_schema", …}` where
  the provider supports it; enable client-side schema validation since not
  all providers enforce schemas natively.
- LiteLLM ships near-weekly — **pin the version** in `pyproject.toml` and the
  lockfile.
- The existing fenced ```tool```-block convention (from AIA's `BaseAgent`) is
  retained as the fallback tool-calling path for small local models without
  native function calling — this remains a differentiator for offline use.

## 3. Privacy policy for memory extraction

Extraction and embedding run exclusively on the user's *configured* extraction
and embedding profiles. There is **no silent rerouting** of private
conversation content to another provider when the configured model is
unavailable — extraction is deferred and retried. Cloud-fallback applies only
to the user's *chat* profile, and only if the user configured a cloud key.

## 4. Embeddings

- MVP default profile: 1536-dim (`text-embedding-3-small` or any
  OpenAI-compatible 1536-dim endpoint, including Ollama-served models via the
  OpenAI-compatible route — LiteLLM's dedicated Ollama embedding route is
  undocumented, so the OpenAI-compatible path is the supported one).
- Every embedding row records `embed_model` + `content_hash`; a model switch
  triggers a background **re-embed job** (embeddings are derived data).
  Cross-model similarity is meaningless — vectors are never mixed.
- Note for local embedding models: `nomic-embed-text-v1.5` (768-dim) requires
  task prefixes (`search_document:` / `search_query:`) for good retrieval —
  the embedding profile carries a `task_prefix` capability flag so the
  retrieval layer applies prefixes correctly.

## 5. Connector registry

Connectors are provider integrations with per-identity grants. The registry
(managed in Desktop, stored in Supabase):

| Concept | Storage |
|---|---|
| Provider definitions (gmail, google_calendar, microsoft_graph, notion, todoist, mcp:*) | code registry (capability descriptors) |
| Connected accounts (status, label, scopes, credential_ref) | `connector_accounts` |
| Per-identity grants (read/write flags) | `identity_connector_grants` |

Rules:

- **Google sign-in ≠ Google connector authorization.** Supabase Auth (Google)
  establishes the Medot account; Gmail/Calendar/Drive require a separate
  OAuth consent with their own scopes, stored as `connector_accounts` rows.
- The same connected account can serve multiple identities with *different*
  grants (Business may send email; Health may only read calendar).
- Token storage: refresh tokens live in the **OS keystore**; Supabase holds
  only status/scopes metadata.
- Migration assets: the AIA `integrations/` providers (Gmail, Graph email,
  Google/Graph calendar, Notion, Todoist, nutrition) plus the OAuth manager
  with auto-refresh move behind this registry largely intact.

## 6. Browser capability

- **Engine**: Playwright (Python) driven by the local runtime; Chromium
  launched with a per-profile persistent user-data directory under the
  Medot workspace folder — logins and sessions survive restarts.
- **Profiles**: created/named/deleted in Desktop → `browser_profiles` (local
  manifest; not in Supabase). One active profile per identity grant.
- **MVP capabilities**: navigate, search, read page content (markdown
  extraction), fill/extract forms **read-only**, download files. Any action
  with external side effects (form submission, posting, purchasing) is an
  **approval-gated** tool (`requires_approval = true`).
- Playwright browsers are installed into the Medot workspace on demand at
  first browser use (not bundled) to keep the installer small.

## 7. Temporary workers & MCP

> **Shipped (2026-11-09, M7 v1):** the runtime is a working MCP client —
> streamable-HTTP only (no stdio servers yet). Connectors are one-click for
> the built-in directory (GitHub, Notion, Linear, Slack, Gmail, Google
> Calendar, Drive) and paste-a-URL for custom servers, Claude-style. Tools
> are namespace-muxed as `mcp__<server>__<tool>` — the doc's colon syntax is
> not valid in OpenAI function names, so double underscores stand in (doc
> deviation, deliberate). Connector URL + auth-header name live in
> `connector_accounts` (migration 0002); the header VALUE lives in the OS
> keystore. Tools are cached 5 min per connector and invalidated on edit.
> **V1 limitations, honest:** no per-action approval on MCP tool calls yet
> (our own destructive tools still gate through the interrupt); OAuth-broker
> connectors accept a pasted token instead of a brokered OAuth flow; stdio
> subprocess servers are not supported.


- Temporary task workers inherit the owning identity's model profile and a
  **scope-limited toolset** (own domain reads + explicit task tools); they
  never mutate the registry or another identity's domain.
- MCP: the runtime is an **MCP client** (official Python SDK, production/stable
  as of Oct 2026). Each identity's MCP servers spawn per-identity stdio
  subprocesses or streamable-HTTP connections; their tools are namespace-muxed
  (`mcp:<server>:<tool>`) into the identity's tool list, subject to grants and
  the approval engine. MCP OAuth (required only for remote HTTP servers) is
  deferred; stdio servers take credentials from the local keystore.
- Deep Agents (`deepagents` package): **beta** and pulls provider SDKs
  (Anthropic/Google) that an Ollama-first install shouldn't require. Deferred
  beyond MVP; its ideas (todo planning tool, isolated subagent contexts,
  filesystem offload) are adopted piecemeal in the worker design.
