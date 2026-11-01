# Medot.

> One personal AI companion — **Me.** — that lives on your desktop, remembers
> your life in a private knowledge graph, and grows **specialist identities**
> (Health, Education, Business, …) for the areas that matter to you. It talks
> with you on **WhatsApp**.

Medot is local-first: the desktop app (Tauri 2) runs a Python runtime sidecar
on your machine, your data lives in your own Supabase project (row-level
security scoped to your account), and secrets stay in your OS keystore.

---

## How it fits together

```
┌────────────────────────── Your PC ──────────────────────────┐
│  Medot Desktop (Tauri 2 + React)                            │
│    └─ Python runtime sidecar (FastAPI on 127.0.0.1)         │
│         ├─ Me. coordinator + specialist identities          │
│         ├─ WhatsApp transports:                             │
│         │    • Official WhatsApp Agent Platform (long-poll) │
│         │    • Baileys bridge (WhatsApp Web session)        │
│         └─ Secrets in OS keystore · local spool/logs        │
└──────────────────────────┬──────────────────────────────────┘
                           │ publishable key only (RLS-scoped)
                    ┌──────▼───────┐
                    │   Supabase   │  auth (Google) · Postgres + pgvector
                    └──────────────┘
```

- **One WhatsApp identity per user** — the agent conversation is Me.; specialist
  identities stay in-app.
- **No inbound ports, no relay** — the official Agent Platform path long-polls
  `GET /updates`; the Baileys bridge dials out from your machine.
- **Publishable keys only** in the desktop bundle; the service-role key never
  ships (AC4, `scripts/scan_bundle.py`).

## WhatsApp connection — choose your route

| | Route 1 — Agent Platform (official) | Route 2 — Baileys bridge (unofficial) |
|---|---|---|
| What it is | Meta's official Agent API | WhatsApp Web session emulation (Node bridge) |
| Setup | Create agent in WhatsApp → paste API key | Scan QR (Settings → Linked Devices) |
| Requirements | WhatsApp agent (rolling out) | Node.js 18+ |
| Groups | Not supported by Meta | Supported (`group_policy`, `require_mention`) |
| Risk | None — official | Unofficial: small ban risk, use a dedicated number |
| Can run | ✅ alone | ✅ alone — or **both routes at once** |

You pick the route in the desktop app; both can be connected simultaneously
and switched any time. Details: [docs/medot/03-whatsapp-connection-strategy.md](docs/medot/03-whatsapp-connection-strategy.md).

## Repository layout

```
medot/
├─ desktop/          # Tauri 2 + React console (Windows-first)
│  ├─ src/           #   onboarding console: sign-in → connect WhatsApp → ready
│  └─ src-tauri/     #   Rust shell: window, sidecar supervisor, medot:// deep link
├─ runtime/          # Python sidecar (the medot package)
│  └─ medot/
│     ├─ api/        #   loopback service API for the desktop console
│     ├─ whatsapp/   #   transports: agent_platform + baileys bridge manager
│     ├─ supabase/   #   Google sign-in (PKCE + deep link), session, RLS client
│     └─ localstore/ #   OS keystore wrapper + workspace layout
├─ bridges/baileys/  # Node 18+ WhatsApp Web bridge (Baileys), spawned by the runtime
├─ supabase/         # migrations (SQL editor apply), config
├─ docs/medot/       # authoritative design documents (start at 00-README)
├─ docs/archive/     # historical AIA specs (non-authoritative, retained for reference)
└─ scripts/          # sidecar build, AC4 bundle scanner
```

## Development

Prerequisites: Python 3.11+ (`uv`), Node 22 (desktop), Rust (desktop shell).

```bash
# runtime tests (fast, no services needed — integration tests skip
# unless MEDOT_TEST_SUPABASE_URL points at a reachable project)
cd runtime && uv run --extra dev pytest tests/ -q

# desktop dev
cd desktop && npm install && npm run dev
```

### Supabase setup (one-time)

1. Create a project → Dashboard → **SQL Editor** → paste
   [`supabase/migrations/0001_foundation.sql`](supabase/migrations/0001_foundation.sql) → Run.
2. **Authentication → Providers → Google**: enable with your OAuth client id/secret.
3. **Authentication → URL Configuration**: allow `medot://auth/callback`.
4. Google Cloud OAuth client → Authorized redirect URIs → add
   `https://<project-ref>.supabase.co/auth/v1/callback`.
5. Put the project URL + publishable key in `runtime/config.toml`:

```toml
[supabase]
supabase_url = "https://<project-ref>.supabase.co"
publishable_key = "sb_publishable_..."
```

## Releases

Nothing builds on user machines — CI builds the Windows installer
(`workflow_dispatch` or `v*` tag → `Medot-setup-windows` artifact), bundling
the publishable Supabase config from repository secrets:

| Secret | Purpose |
|---|---|
| `MEDOT_SUPABASE_URL` | baked into the installer's `config.toml` |
| `MEDOT_SUPABASE_PUBLISHABLE_KEY` | baked into the installer's `config.toml` |
| `MEDOT_TEST_SUPABASE_URL` | hosted integration/RLS test target |
| `MEDOT_TEST_SUPABASE_SERVICE_KEY` | service key for the hosted test job (never bundled) |

## Documentation

Authoritative design record: **[docs/medot/00-README.md](docs/medot/00-README.md)**
(product spec, architecture, WhatsApp strategy, Supabase schema, desktop
platform, migration roadmap, open decisions). Pre-Medot history lives in
[docs/archive/](docs/archive/).

## License

MIT — see [LICENSE](LICENSE).
