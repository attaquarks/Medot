# Hosted Development — No Local Builds, No Docker

Status: **Policy (product owner, 2026-11-01)** — nothing builds on the
owner's machine from this point forward.

## The policy

| Need | Runs where |
|---|---|
| Tests (unit) | Agent workspace (lightweight `pytest` only) + GitHub CI |
| Tests (Supabase/RLS integration) | GitHub CI against the **hosted** project (service key as a repo secret) |
| Supabase migrations | **Supabase dashboard SQL editor** (paste `supabase/migrations/*.sql`) — no local CLI required |
| Desktop installers | **GitHub Actions** (`release` job — dispatch or `v*` tag) → downloadable artifact |
| Website | Vercel (when the website is built) |
| Backend/relay (OD-13) | Free cloud hosting — owner to select; options presented when the relay design is costed |

Banned on the owner's machine: Docker, Supabase CLI stack, `cargo build`,
PyInstaller, NSIS, any packaging. Lightweight `pytest`/`uv run` in the
workspace remains allowed (no build artifacts, seconds).

## Secrets & where they live

| Secret | Lives in | Never in |
|---|---|---|
| Google OAuth client id/secret | Google Cloud + `supabase/.env.local` (local-stack only, gitignored) | chat, git |
| Hosted Supabase URL + publishable key | safe to share in chat; also repo secrets `MEDOT_SUPABASE_URL` / `MEDOT_SUPABASE_PUBLISHABLE_KEY` | n/a |
| Supabase **service key** (hosted) | GitHub repo secret `MEDOT_TEST_SUPABASE_SERVICE_KEY` (user adds via GitHub UI) | chat, git, desktop |

## Hosted Supabase project setup (one-time, owner)

1. Create a project at [supabase.com](https://supabase.com) (free tier).
2. Dashboard → **SQL Editor** → paste the full contents of
   `supabase/migrations/0001_foundation.sql` → Run.
3. **Authentication → Providers → Google**: enable, paste client ID/secret
   (from your Google Cloud OAuth client).
4. **Authentication → URL Configuration**: add `medot://auth/callback` to
   the redirect allow-list.
5. Google Cloud OAuth client → Authorized redirect URIs → add
   `https://<project-ref>.supabase.co/auth/v1/callback`.
6. Share the **Project URL** and **anon/publishable key** with the agent
   (both are publishable values, safe in chat) — the agent sets the repo
   secrets via `gh` and CI takes over from there.

## CI release flow

`release` job (workflow_dispatch or `v*` tag) on `windows-latest`:
PyInstaller sidecar (bundled `config.toml` from repo secrets) → `tauri build`
→ NSIS artifact `Medot-setup-windows`. Installing it registers `medot://`,
bakes the hosted Supabase values, and signs in against the hosted project —
the AC1 flow, no local tooling.
