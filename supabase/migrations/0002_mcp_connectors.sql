-- ============================== MCP connectors (M7) =========================
-- connector_accounts gains the MCP endpoint fields: the streamable-HTTP URL,
-- the auth header name (its VALUE lives in the OS keystore via credential_ref,
-- like provider keys), and an enabled switch. Existing rows keep working.
alter table public.connector_accounts
  add column if not exists url text not null default '',
  add column if not exists auth_header_name text,
  add column if not exists enabled boolean not null default true;
