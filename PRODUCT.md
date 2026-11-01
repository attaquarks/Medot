# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

(Tauri 2 + React + TypeScript desktop app — WebView2 on Windows first; the
frontend is web tech and is designed/built as web. Native mobile is out of
scope for the MVP.)

## Stack

Existing codebase: React 18 + TypeScript + Vite inside `desktop/`, styled
today with inline style objects; talks to a local Python runtime over
loopback HTTP (`127.0.0.1:8756`, per-launch token header) and to Tauri APIs
(deep-link events, runtime-ready handshake). Rust shell supervises the
runtime sidecar. This stack is fixed; the rebuild stays in it.

## Users

Ordinary people who use WhatsApp — students, professionals, business owners,
parents, senior citizens — managing health, education, work, hobbies. The
operating benchmark: *an elderly person must be able to use Medot without
understanding agents, prompts, models, graphs, or automation.* Every
technical concept surfaces in plain language. The user is non-technical by
design assumption; the desktop app is a management console, never a chat
surface (chat happens on WhatsApp, with Me.).

## Product Purpose

Medot is one personal AI companion — **Me.** — that converses with the user
on a single WhatsApp conversation, remembers their life as a private
knowledge system (graph + episodic memory + structured records), and grows
**specialist identities** (Health, Education, Gardening, …) for areas that
become complex. Identities are data, not code: durable, user-visible
configurations with their own instructions, knowledge scope, model profile,
tools, and permissions. Success: the MVP contract in
`docs/medot/01 §7` — sign in, connect WhatsApp, talk, watch knowledge and
identities grow, inspect and edit everything in Desktop.

## Positioning

One companion, not a fleet: one WhatsApp conversation, permanent Me.
coordinator that delegates to persistent specialist identities; a growing
temporal knowledge system instead of a chat log; local-first (runtime on the
user's machine, data in the user's own Supabase project, secrets in the OS
keystore, RLS-isolated per user). No competitor copies this exact combination
of single-conversation WhatsApp + persistent identities + local-first
knowledge.

## Operating Context

- WhatsApp is the primary interface; Desktop is management/oversight.
- The runtime runs on the user's PC; window close ≠ quit (runtime keeps
  running; tray quit ends it).
- Two WhatsApp routes behind the user's choice (official Agent Platform API
  key, or unofficial Baileys QR bridge — either or both).
- Hosted-dev policy: nothing builds on the user's machine; installers come
  from GitHub Actions.
- Data lives in the user's own Supabase project; per-user RLS isolation is a
  tested guarantee.

## Capabilities and Constraints

Shipped today (runtime API): Google sign-in (PKCE + deep link), session
restore, account bootstrap status, WhatsApp dual-route connect/status/QR/
disconnect per route, test send, local paths. Coming per roadmap (UI must
render honest "not yet" states, no fake data): identity registry + detail
tabs (Overview/Instructions/Knowledge/Memory/Tools/Connectors/Model/
Permissions/Activity), knowledge domain explorer, model profiles + provider
keys (OS keystore), connectors, browser profiles, activity timeline,
approvals, settings.

Hard constraints: Windows compatibility required for every dependency; no
privileged/service credentials ever in the desktop bundle; secrets only in
the OS keystore; plain-language labels (spaces/areas/knowledge — never
nodes/edges/embeddings); commands are runtime-generated from identity slugs.

Explicit MVP non-goals (do not design for them): multi-device sync, billing,
marketplaces, multiple WhatsApp identities, per-domain bots or numbers,
complex agent frameworks, advanced voice.

## Brand Commitments

- Name: **Medot**; the conversational assistant is **Me.** (with the period).
- Wordmark: "Medot." with an amber dot (`#d97706` on warm-neutral ground) —
  established in the shipped console; keep it recognizable.
- Voice: warm, concise, honest about limitations; "Explain this" affordance
  on every technical concept.
- Tone/quality bar from docs/medot/07 §7: large-type-friendly defaults,
  high-contrast palette, keyboard navigable, no decorative animation.

## Evidence on Hand

- Authoritative specs: `docs/medot/01…13` (product, architecture, schema,
  desktop, hosted-dev policy).
- Working runtime + shell: `runtime/medot/` (FastAPI loopback API),
  `desktop/src-tauri/` (sidecar, deep links), `desktop/src/App.tsx`
  (current single-screen onboarding console — the incumbent look: warm
  stone ground `#fafaf9`, white card, near-black ink, amber dot).
- Live hosted Supabase project (Google auth enabled; foundation schema
  applied).
- No marketing site, no testimonials, no press — none may be fabricated.

## Product Principles

1. Plain language always — the elderly-person benchmark governs every label,
   state, and error.
2. One companion — Me. is permanent; specialists are its delegations.
3. Local-first and private — user's machine, user's Supabase, OS keystore;
   nothing privileged ships.
4. Honest states — every not-yet-built capability says so plainly; never
   fake progress or data.
5. Simple and permanent over clever; tested, not "done".

## Accessibility & Inclusion

Large-type-friendly defaults, high-contrast palette, keyboard navigable, no
decorative animation (per docs/medot/07 §7). WCAG AA contrast is the floor.
Plain-language labels throughout; an "Explain this" affordance on technical
concepts (model, connector, approval).
