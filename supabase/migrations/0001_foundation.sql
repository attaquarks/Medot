-- Medot Milestone 1 — foundation schema (docs/medot/06-supabase-schema.md)
-- Idempotent when applied via `supabase db reset`; designed for `db push`.
-- Ownership boundary: every user-owned table carries user_id = auth.uid() via RLS.

-- ============================== extensions ==================================
create extension if not exists vector with schema extensions;
create extension if not exists pg_jsonschema with schema extensions;

-- ============================== profiles & settings =========================
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  avatar_url text,
  timezone text not null default 'UTC',
  created_at timestamptz not null default now()
);

create table if not exists public.user_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  settings jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- ============================== identities ==================================
create table if not exists public.model_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  purpose text not null default 'chat'
      check (purpose in ('chat','extraction','embedding','planning')),
  provider text not null,
  model text not null,
  api_base text,
  params jsonb not null default '{}'::jsonb,
  credential_ref text,
  capabilities jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.identities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null default 'specialist'
      check (kind in ('coordinator','specialist')),
  name text not null,
  slug text not null,
  description text not null default '',
  icon text,
  status text not null default 'active'
      check (status in ('active','deactivated','archived')),
  domain_id uuid,
  model_profile_id uuid references public.model_profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, slug)
);

create table if not exists public.identity_instructions (
  id uuid primary key default gen_random_uuid(),
  identity_id uuid not null references public.identities(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  version int not null default 1,
  content_md text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (identity_id, version)
);

-- ============================== knowledge ===================================
create table if not exists public.knowledge_domains (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  slug text not null,
  title text not null,
  owner_identity_id uuid references public.identities(id),
  root_node_id uuid,
  summary text not null default '',
  status text not null default 'active',
  created_at timestamptz not null default now(),
  unique (user_id, slug)
);

-- identities.domain_id -> knowledge_domains (added here to break the circular FK)
do $$ begin
  if not exists (
    select 1 from pg_constraint where conname = 'identities_domain_fk'
  ) then
    alter table public.identities
      add constraint identities_domain_fk
      foreign key (domain_id) references public.knowledge_domains(id);
  end if;
end $$;

create table if not exists public.knowledge_nodes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),
  node_type text not null,
  name text not null,
  attributes jsonb not null default '{}'::jsonb,
  summary text not null default '',
  external_ref jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists knowledge_nodes_user_domain
  on public.knowledge_nodes (user_id, domain_id);
create index if not exists knowledge_nodes_attributes
  on public.knowledge_nodes using gin (attributes);

create table if not exists public.knowledge_edges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),
  src_node_id uuid not null references public.knowledge_nodes(id) on delete cascade,
  dst_node_id uuid not null references public.knowledge_nodes(id) on delete cascade,
  relation text not null,
  fact text not null,
  valid_from timestamptz not null default now(),
  valid_to timestamptz,
  invalid_reason text,
  confidence numeric(3,2) not null default 1.00,
  source_episode_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists knowledge_edges_src on public.knowledge_edges (user_id, src_node_id);
create index if not exists knowledge_edges_dst on public.knowledge_edges (user_id, dst_node_id);

-- ============================== episodic memory =============================
create table if not exists public.memory_episodes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid references public.knowledge_domains(id),
  kind text not null check (kind in ('message','document','observation','decision')),
  content text not null,
  conversation_id uuid,
  message_id uuid,
  occurred_at timestamptz not null,
  extraction_status text not null default 'pending'
      check (extraction_status in ('pending','extracted','skipped','failed')),
  created_at timestamptz not null default now()
);
create index if not exists memory_episodes_user on public.memory_episodes (user_id, domain_id, occurred_at);

-- OD-2: dimension-partitioned embedding tables (768 / 1024 / 1536).
-- Identical shape; vectors from different models are never compared — every
-- similarity query filters on embed_model, and each table has its own index.
do $$
declare
  dim int;
begin
  foreach dim in array array[768, 1024, 1536] loop
    execute format($f$
      create table if not exists public.memory_embeddings_%1$s (
        id uuid primary key default gen_random_uuid(),
        user_id uuid not null references auth.users(id) on delete cascade,
        domain_id uuid references public.knowledge_domains(id),
        ref_type text not null check (ref_type in ('episode','node','record','edge','summary')),
        ref_id uuid not null,
        embedding vector(%1$s) not null,
        embed_model text not null,
        content_hash text not null,
        created_at timestamptz not null default now()
      );
      create index if not exists memory_embeddings_%1$s_hnsw
        on public.memory_embeddings_%1$s using hnsw (embedding vector_cosine_ops);
      create index if not exists memory_embeddings_%1$s_scope
        on public.memory_embeddings_%1$s (user_id, domain_id, ref_type, ref_id);
    $f$, dim);
  end loop;
end $$;

-- Similarity search RPCs (invoker rights; RLS applies).
create or replace function public.match_embeddings(
  query_embedding extensions.vector,
  match_count int default 8,
  p_embed_model text default null
) returns table (ref_type text, ref_id uuid, content_hash text, distance float)
language sql stable as $$
  select e.ref_type, e.ref_id, e.content_hash,
         e.embedding <=> query_embedding as distance
  from public.memory_embeddings_1536 e
  where e.user_id = (select auth.uid())
    and (p_embed_model is null or e.embed_model = p_embed_model)
  order by e.embedding <=> query_embedding
  limit match_count;
$$;

-- ============================== dynamic domain records ======================
create table if not exists public.domain_schemas (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,  -- null = system builtin
  type_key text not null,
  title text not null,
  json_schema jsonb not null,
  version int not null default 1,
  created_at timestamptz not null default now(),
  unique (type_key, version)
);

create table if not exists public.domain_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  domain_id uuid not null references public.knowledge_domains(id),
  type_key text not null,
  data jsonb not null check (jsonb_typeof(data) = 'object'),
  occurred_at timestamptz not null,
  source_episode_id uuid,
  created_at timestamptz not null default now()
);
create index if not exists domain_records_scope
  on public.domain_records (user_id, domain_id, type_key, occurred_at desc);
create index if not exists domain_records_data on public.domain_records using gin (data);

-- Defense-in-depth: validate record payloads against the newest active
-- domain_schema for their type_key at write time (pg_jsonschema).
create or replace function public.validate_domain_record()
returns trigger language plpgsql as $$
declare
  v_schema jsonb;
begin
  select json_schema into v_schema
  from public.domain_schemas
  where type_key = new.type_key
  order by version desc
  limit 1;
  if v_schema is not null and not extensions.jsonb_matches_schema(v_schema::json, new.data) then
    raise exception 'domain_record % does not match its registered schema', new.type_key
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger if exists domain_records_validate on public.domain_records;
create trigger domain_records_validate
  before insert or update of data on public.domain_records
  for each row execute function public.validate_domain_record();

-- ============================== conversations ===============================
create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel text not null default 'whatsapp',
  transport text not null,
  peer text not null,
  active_identity_id uuid references public.identities(id),
  last_message_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, channel, peer)
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  direction text not null check (direction in ('inbound','outbound')),
  wa_message_id text unique,
  body text not null,
  media jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null,
  created_at timestamptz not null default now()
);
create index if not exists messages_conversation on public.messages (conversation_id, occurred_at);

-- ============================== runs, approvals, activity ===================
create table if not exists public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid not null references public.identities(id),
  trigger text not null check (trigger in ('inbound','background','proactive','desktop')),
  parent_run_id uuid references public.agent_runs(id),
  status text not null default 'running'
      check (status in ('running','succeeded','failed','awaiting_approval','cancelled')),
  model_profile_id uuid references public.model_profiles(id),
  tokens_in int not null default 0,
  tokens_out int not null default 0,
  error text,
  started_at timestamptz not null default now(),
  ended_at timestamptz
);
create index if not exists agent_runs_user on public.agent_runs (user_id, started_at desc);

create table if not exists public.approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  run_id uuid not null references public.agent_runs(id),
  identity_id uuid not null references public.identities(id),
  action text not null,
  summary text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
      check (status in ('pending','approved','denied','expired')),
  channel text not null default 'whatsapp',
  decided_at timestamptz,
  expires_at timestamptz not null default (now() + interval '24 hours')
);
create index if not exists approvals_user on public.approvals (user_id, status);

create table if not exists public.activity_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid references public.identities(id),
  run_id uuid references public.agent_runs(id),
  event text not null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists activity_events_user on public.activity_events (user_id, created_at desc);

-- ============================== connectors ==================================
create table if not exists public.connector_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,
  account_label text not null default '',
  credential_ref text,
  scopes text not null default '',
  status text not null default 'connected'
      check (status in ('connected','needs_reauth','revoked','error')),
  connected_at timestamptz not null default now()
);

create table if not exists public.identity_tool_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid not null references public.identities(id) on delete cascade,
  tool_key text not null,
  params jsonb not null default '{}'::jsonb,
  requires_approval boolean not null default true,
  granted_at timestamptz not null default now(),
  unique (identity_id, tool_key)
);

create table if not exists public.identity_connector_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_id uuid not null references public.identities(id) on delete cascade,
  connector_account_id uuid not null references public.connector_accounts(id) on delete cascade,
  can_read boolean not null default true,
  can_write boolean not null default false,
  granted_at timestamptz not null default now(),
  unique (identity_id, connector_account_id)
);

-- ============================== updated_at triggers =========================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['identities','knowledge_nodes','knowledge_edges'] loop
    execute format('drop trigger if exists %1$s_touch on public.%1$s', t);
    execute format($f$
      create trigger %1$s_touch before update on public.%1$s
      for each row execute function public.touch_updated_at()
    $f$, t);
  end loop;
end $$;

-- ============================== account initialization (AC2) ================
-- A new auth user gets: profile, user_settings, the Me. coordinator identity
-- (with v1 instructions) and their global knowledge domain. Idempotent.
create or replace function public.handle_new_user()
returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_global_domain uuid;
  v_me_identity uuid;
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (new.id, coalesce(new.raw_user_meta_data->>'name', new.email), new.raw_user_meta_data->>'avatar_url')
  on conflict (id) do nothing;

  insert into public.user_settings (user_id) values (new.id)
  on conflict (user_id) do nothing;

  insert into public.knowledge_domains (user_id, slug, title, summary)
  values (new.id, 'global', 'My Life',
          'Everything Me. knows about the user across all areas.')
  on conflict (user_id, slug) do nothing
  returning id into v_global_domain;

  if v_global_domain is null then
    select id into v_global_domain from public.knowledge_domains
    where user_id = new.id and slug = 'global';
  end if;

  insert into public.identities (user_id, kind, name, slug, description, icon, domain_id)
  values (new.id, 'coordinator', 'Me.', 'me',
          'Your personal assistant. Understands you, remembers what matters, and coordinates your specialist identities.',
          'sparkles', v_global_domain)
  on conflict (user_id, slug) do nothing
  returning id into v_me_identity;

  if v_me_identity is null then
    select id into v_me_identity from public.identities
    where user_id = new.id and slug = 'me';
  end if;

  insert into public.identity_instructions (identity_id, user_id, version, content_md, is_active)
  values (v_me_identity, new.id, 1,
'You are Me., the user''s personal assistant and the coordinator of their Medot companion.

- Converse naturally. Learn about the user''s life, preferences and goals over time.
- Keep track of what matters. Facts are stored with sources and dates; never present stale summaries as current.
- When one area of the user''s life grows complex enough, suggest organizing it into its own space (identity) — always asking first.
- Route domain questions to the owning identity, or invoke it in the background and synthesize the results.
- Be warm, concise and honest about what you do not know.', true)
  on conflict (identity_id, version) do nothing;

  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ============================== seed: builtin domain schemas ================
insert into public.domain_schemas (user_id, type_key, title, json_schema)
values
  (null, 'health.meal', 'Meal', '{"type":"object","required":["description"],"properties":{"description":{"type":"string"},"calories":{"type":"number"},"protein_g":{"type":"number"},"carbs_g":{"type":"number"},"fat_g":{"type":"number"}}}'),
  (null, 'health.weight_measurement', 'Weight measurement', '{"type":"object","required":["weight_kg"],"properties":{"weight_kg":{"type":"number","minimum":20,"maximum":400},"source":{"type":"string"}}}'),
  (null, 'health.medication', 'Medication schedule', '{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"dose":{"type":"string"},"frequency":{"type":"string"},"times":{"type":"array","items":{"type":"string"}}}}'),
  (null, 'education.assignment', 'Assignment', '{"type":"object","required":["title"],"properties":{"title":{"type":"string"},"subject":{"type":"string"},"due_at":{"type":"string"},"status":{"type":"string","enum":["todo","submitted","graded"]}}}'),
  (null, 'education.grade', 'Grade', '{"type":"object","required":["title","grade"],"properties":{"title":{"type":"string"},"subject":{"type":"string"},"grade":{"type":"number"},"max_grade":{"type":"number"}}}'),
  (null, 'gardening.plant', 'Plant', '{"type":"object","required":["species"],"properties":{"species":{"type":"string"},"planted_at":{"type":"string"},"location":{"type":"string"},"watering_days":{"type":"array","items":{"type":"string"}}}}'),
  (null, 'business.lead', 'Lead', '{"type":"object","required":["name"],"properties":{"name":{"type":"string"},"company":{"type":"string"},"contact":{"type":"string"},"stage":{"type":"string","enum":["new","contacted","qualified","proposal","won","lost"]}}}')
on conflict (type_key, version) do nothing;

-- ============================== RLS (AC3) ===================================
-- Applied uniformly to every user-owned table. Authenticated users see and
-- write only rows where their owner column matches auth.uid(); anon sees
-- nothing. profiles keys ownership on id (its PK); every other table on user_id.
do $$
declare
  t text;
  owner_col text;
  tables text[] := array[
    'profiles','user_settings','model_profiles','identities','identity_instructions',
    'knowledge_domains','knowledge_nodes','knowledge_edges','memory_episodes',
    'domain_schemas','domain_records','conversations','messages','agent_runs',
    'approvals','activity_events','connector_accounts','identity_tool_grants',
    'identity_connector_grants',
    'memory_embeddings_768','memory_embeddings_1024','memory_embeddings_1536'
  ];
begin
  foreach t in array tables loop
    owner_col := case when t = 'profiles' then 'id' else 'user_id' end;
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "own_rows_select" on public.%I', t);
    execute format($f$
      create policy "own_rows_select" on public.%I
      for select to authenticated
      using ((select auth.uid()) = %I)
    $f$, t, owner_col);
    execute format('drop policy if exists "own_rows_write" on public.%I', t);
    execute format($f$
      create policy "own_rows_write" on public.%I
      for all to authenticated
      using ((select auth.uid()) = %I)
      with check ((select auth.uid()) = %I)
    $f$, t, owner_col, owner_col);
  end loop;
end $$;

-- domain_schemas: builtin rows (user_id null) must be readable by all
-- authenticated users (they define record types), writable only by their owner.
drop policy if exists "builtin_schemas_readable" on public.domain_schemas;
create policy "builtin_schemas_readable" on public.domain_schemas
  for select to authenticated
  using (user_id is null or (select auth.uid()) = user_id);
