# Medot — Supabase Schema Proposal

Status: **Proposed v1 — pending review** (Stage 1 deliverable)
Auth: Supabase Auth (Google). Ownership boundary: `user_id = auth.uid()` on
every user-owned table, enforced by RLS.

Design rules:

- **Generic identity model** — no table per identity type. A Gardening
  identity is rows, not DDL.
- **Relational for stable universal entities; JSONB for genuinely variable
  domain payloads** (validated by registered JSON Schemas, not free EAV).
- The desktop app uses the **publishable/anon key + user JWT**; the
  service-role key never ships to clients (RLS is the security boundary).

---

## 1. Identity & configuration tables

```sql
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  avatar_url text,
  timezone text not null default 'UTC',
  created_at timestamptz not null default now()
);

create table public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  settings jsonb not null default '{}'::jsonb,   -- proactive hours, privacy toggles, extraction policy
  updated_at timestamptz not null default now()
);

-- One row for Me. (kind='coordinator') plus one per specialist.
create table public.identities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null default 'specialist'
      check (kind in ('coordinator','specialist')),
  name text not null,
  slug text not null,                            -- command name: 'health', 'gardening'
  description text not null default '',
  icon text,                                     -- icon key from the desktop icon set
  status text not null default 'active'
      check (status in ('active','deactivated','archived')),
  domain_id uuid,                                -- set when a specialist owns a domain (FK added below)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, slug)                         -- slug is unique per user, not globally
);

create table public.identity_instructions (
  id uuid primary key default gen_random_uuid(),
  identity_id uuid not null references public.identities(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  version int not null default 1,
  content_md text not null,                      -- AGENT.md-style instructions
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (identity_id, version)
);

create table public.model_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,                            -- "Ollama local", "Claude Sonnet"
  purpose text not null default 'chat'
      check (purpose in ('chat','extraction','embedding','planning')),
  provider text not null,                        -- ollama | openai | anthropic | openai_compatible
  model text not null,
  api_base text,                                 -- for ollama / compatible endpoints
  params jsonb not null default '{}'::jsonb,     -- temperature, max_tokens, context…
  credential_ref text,                           -- OS-keystore alias; NEVER a key value
  capabilities jsonb not null default '{}'::jsonb,  -- tool_calling, structured_output, embedding_dim…
  created_at timestamptz not null default now()
);
```

Identities link to model profiles through a per-identity assignment (kept
simple: `identities.model_profile_id uuid references model_profiles(id)`,
added after both tables exist; `user_settings` carries the extraction/embedding
profile ids).

## 2. Knowledge graph (Supabase-native layer)

These tables are the **canonical application view** of knowledge. They fully
implement the graph natively (Approach A); if Graphiti is adopted later, the
same tables remain authoritative for app concerns while the Graphiti backend
mirrors them behind the `KnowledgeService` abstraction (Approach B — see
`05-graphiti-evaluation.md`).

```sql
create table public.knowledge_domains (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  slug text not null,                            -- 'health', 'education', 'gardening'
  title text not null,
  owner_identity_id uuid references public.identities(id),  -- null = Me.-managed global
  root_node_id uuid,                             -- FK added after knowledge_nodes
  summary text not null default '',              -- the lightweight summary Me. keeps
  status text not null default 'active',
  created_at timestamptz not null default now(),
  unique (user_id, slug)
);

create table public.knowledge_nodes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),
  node_type text not null,                       -- 'person','goal','medication','plant',… (open vocabulary)
  name text not null,
  attributes jsonb not null default '{}'::jsonb,
  summary text not null default '',
  external_ref jsonb,                            -- graph-backend node id when a mirror exists
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on public.knowledge_nodes (user_id, domain_id);
create index on public.knowledge_nodes using gin (attributes);

create table public.knowledge_edges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),   -- primary domain of the edge
  src_node_id uuid not null references public.knowledge_nodes(id) on delete cascade,
  dst_node_id uuid not null references public.knowledge_nodes(id) on delete cascade,
  relation text not null,                        -- 'has_goal','takes_medication','tends_plant',…
  fact text not null,                            -- natural-language fact statement
  valid_from timestamptz not null default now(),
  valid_to timestamptz,                          -- null = currently valid (temporal)
  invalid_reason text,
  confidence numeric(3,2) not null default 1.00,
  source_episode_id uuid,                        -- provenance (FK added below)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on public.knowledge_edges (user_id, src_node_id);
create index on public.knowledge_edges (user_id, dst_node_id);
alter table public.knowledge_edges
  add constraint edges_no_self foreign key (src_node_id) … ;  -- app-enforced; see note
```

Cross-domain edges simply carry the `domain_id` of their primary side while
their endpoints may belong to different domains — ownership never fragments
the graph.

## 3. Episodic memory & embeddings

```sql
create table public.memory_episodes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),   -- primary domain (may be null → global)
  kind text not null check (kind in ('message','document','observation','decision')),
  content text not null,
  conversation_id uuid,                          -- FK added below
  message_id uuid,                               -- FK added below (source message)
  occurred_at timestamptz not null,
  extraction_status text not null default 'pending'
      check (extraction_status in ('pending','extracted','skipped','failed')),
  created_at timestamptz not null default now()
);

-- Regenerable derived data: safe to re-embed wholesale if the model changes.
-- OD-2 (Stage 2): dimension-partitioned tables — one per allowed embedding
-- dimension, each declared by migration with its own HNSW index. Vectors from
-- different models are NEVER compared: every similarity query filters on
-- embed_model (and rows carry the domain scope for ownership filtering).
create table public.memory_embeddings_1536 (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),   -- null = global scope
  ref_type text not null check (ref_type in ('episode','node','record','edge','summary')),
  ref_id uuid not null,
  embedding vector(1536) not null,
  embed_model text not null,
  content_hash text not null,
  created_at timestamptz not null default now()
);
create index on public.memory_embeddings_1536 using hnsw (embedding vector_cosine_ops);
create index on public.memory_embeddings_1536 (user_id, domain_id, ref_type, ref_id);

-- 768 (local nomic-class) and 1024 variants share the identical shape and are
-- created by the same migration; the repository's KnowledgeService selects the
-- table from the embedding profile's declared dimension.

## 4. Dynamic domain records

```sql
create table public.domain_schemas (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,                                  -- null = system builtin (e.g. health.meal)
  type_key text not null,                        -- 'health.meal', 'education.assignment', 'gardening.plant'
  title text not null,
  json_schema jsonb not null,                    -- JSON Schema (draft 2020-12)
  version int not null default 1,
  created_at timestamptz not null default now(),
  unique (type_key, version)
);

create table public.domain_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid not null references public.knowledge_domains(id),
  type_key text not null,                        -- joins to domain_schemas
  data jsonb not null,                           -- validated against the schema at the app layer
  occurred_at timestamptz not null,
  source_episode_id uuid,                        -- provenance (FK added below)
  created_at timestamptz not null default now()
);
create index on public.domain_records (user_id, domain_id, type_key, occurred_at desc);
create index on public.domain_records using gin (data);
```

Validation is enforced in **both layers**: the Python application (Pydantic ←
JSON Schema, for good error messages) at write time, and Postgres-side
`pg_jsonschema` (verified available on Supabase:
`create extension pg_jsonschema with schema extensions;`) as defense-in-depth:

```sql
create extension if not exists pg_jsonschema with schema extensions;
-- per active type_key, a CHECK constraint using jsonb_matches_schema;
-- maintained by a migration whenever a builtin domain_schema version lands
```

**Proving dynamism — a Gardening identity needs zero DDL:**

```sql
-- 1. record types for the new domain (rows, not tables):
insert into public.domain_schemas (user_id, type_key, title, json_schema)
values (null, 'gardening.plant', 'Plant',
  '{"type":"object","required":["species"],
    "properties":{"species":{"type":"string"},
                   "planted_at":{"type":"string","format":"date"},
                   "location":{"type":"string"},
                   "watering_days":{"type":"array","items":{"type":"string"}}}}');

-- 2. domain root:
insert into public.knowledge_domains (user_id, slug, title)
values ($user, 'gardening', 'Gardening');

-- 3. the identity itself:
insert into public.identities (user_id, kind, name, slug, description, domain_id, model_profile_id)
values ($user, 'specialist', 'Gardening', 'gardening', 'My plants and garden care', $domain, $profile);
```

The runtime, retrieval, Desktop UI, and WhatsApp commands pick all of this up
with **no schema change, no deploy, no restart**.

## 5. Conversations, runs, approvals, connectors

```sql
create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel text not null default 'whatsapp',
  transport text not null,                       -- 'cloud_api' | 'baileys'
  peer text not null,                            -- normalized WhatsApp id
  active_identity_id uuid references public.identities(id),  -- persistent /health-style mode
  last_message_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, channel, peer)
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  direction text not null check (direction in ('inbound','outbound')),
  wa_message_id text unique,                     -- transport dedupe key (null for proactive drafts)
  body text not null,
  media jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid not null references public.identities(id),
  trigger text not null check (trigger in ('inbound','background','proactive','desktop')),
  parent_run_id uuid references public.agent_runs(id),      -- coordinator → identity invocations
  status text not null default 'running'
      check (status in ('running','succeeded','failed','awaiting_approval','cancelled')),
  model_profile_id uuid references public.model_profiles(id),
  tokens_in int not null default 0,
  tokens_out int not null default 0,
  error text,
  started_at timestamptz not null default now(),
  ended_at timestamptz
);

create table public.approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid not null references public.agent_runs(id),
  identity_id uuid not null references public.identities(id),
  action text not null,                          -- 'send_email','create_event','browser_form',…
  summary text not null,                         -- human-readable proposal shown to the user
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
      check (status in ('pending','approved','denied','expired')),
  channel text not null default 'whatsapp',      -- decided via WhatsApp reply or Desktop
  decided_at timestamptz,
  expires_at timestamptz not null default now() + interval '24 hours'
);

create table public.activity_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid references public.identities(id),
  run_id uuid references public.agent_runs(id),
  event text not null,                           -- 'identity_created','tool_invoked','fact_updated',…
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.connector_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,                        -- gmail | google_calendar | notion | todoist | mcp:…
  account_label text not null default '',
  credential_ref text,                           -- OS-keystore alias for tokens
  scopes text not null default '',
  status text not null default 'connected'
      check (status in ('connected','needs_reauth','revoked','error')),
  connected_at timestamptz not null default now()
);

create table public.identity_tool_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid not null references public.identities(id) on delete cascade,
  tool_key text not null,                        -- 'calendar.create_event', 'browser.navigate',…
  params jsonb not null default '{}'::jsonb,
  requires_approval boolean not null default true,
  granted_at timestamptz not null default now(),
  unique (identity_id, tool_key)
);

create table public.identity_connector_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid not null references public.identities(id) on delete cascade,
  connector_account_id uuid not null references public.connector_accounts(id) on delete cascade,
  can_read boolean not null default true,
  can_write boolean not null default false,
  granted_at timestamptz not null default now(),
  unique (identity_id, connector_account_id)
);
```

## 6. Row Level Security

Every user-owned table gets the same pair of policies (example shown once;
applied to all):

```sql
alter table public.identities enable row level security;

create policy "own rows select" on public.identities
  for select using ((select auth.uid()) = user_id);
create policy "own rows write" on public.identities
  for all using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
```

Notes:

- `(select auth.uid())` form (not a bare call) so the filter is an `INITPLAN`
  subquery — this is the recommended Supabase RLS performance pattern.
- Tables with no user-facing write path (e.g. `messages` written by the
  runtime) still get select-only user policies; runtime writes use the
  user's session (the runtime acts *as the user*, never as service role).
- The publishable/anon key is safe to embed; the **service-role key never
  leaves the server side** and is not needed by the MVP at all (the local
  runtime holds the user's session, not privileged keys).
- An RLS test suite (fixture: two users, cross-read attempts must return 0
  rows) is a required acceptance test for Milestone 1.

## 7. Deferred vs included

Included in MVP: everything above. Deferred: `browser_profiles`,
`connector_oauth_flows` state, `identity_execution_state` (LangGraph
checkpoint mirror), multi-device sync tables, subscription/billing tables.
