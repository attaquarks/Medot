# Medot — WhatsApp Connection Strategy

Status: **Decided (product owner, 2026-11-02)** — Medot implements **both**
WhatsApp routes behind one transport contract, and the user chooses per
desktop install: the official **WhatsApp Agent Platform** (Route 1) and/or the
unofficial **Baileys** WhatsApp Web bridge (Route 2). This supersedes the
2026-11-01 "Agent Platform exclusively" decision (historical record in §5)
and its relay prerequisite — the Agent Platform's long-poll `GET /updates`
needs no public URL and no relay.

Requirement recap: **one** WhatsApp conversational identity (Me.) per user;
specialist identities never read more inbound messages than the user's own
conversations; proactive outbound (daily messages) must work.

---

## 1. Decision

1. **Both routes, user's choice, combinable.** The desktop console offers
   both; a user can connect one or both simultaneously. Each gets its own
   RLS-scoped `connector_accounts` row (`whatsapp_agent_platform` /
   `whatsapp_baileys`), so "mode" is just which rows are connected.
2. **One transport contract** (§4): connect, `send(peer, text)`,
   `on_inbound(handler)`, `health()`; normalized envelopes tagged with the
   originating transport so the rest of Medot is transport-blind.
3. **No relay.** Both routes dial out from the desktop (Agent Platform
   long-poll; Baileys socket). The old relay design is parked; it returns only
   if Meta moves to webhook-only or a hosted multi-user deployment is
   authorized (OD-13).
4. **Identity model unchanged**: one agent conversation per user; internal
   specialist identities stay in-app.

## 2. Route 1 — WhatsApp Agent Platform (official)

Official API, no ban risk; requires the rolling-out WhatsApp Agents feature
and an agent created in Agent Manager.

| Aspect | Value |
|---|---|
| Base URL | `https://api.whatsapp.com/agent/v1` |
| Auth | `Authorization: Bearer <api key>` (WhatsApp → Settings → Agents → Create agent → Chat info → API key) |
| Inbound | Long-poll `GET /updates` — no public URL, no relay |
| Outbound | `POST /messages` (text ≤ 4096 UTF-16 units; media via `POST /media` upload → send with media id) |
| Receipts | `POST /statuses` (read receipt + 25 s typing indicator) |
| Limits | 12 msg/min, 12 status/min, 15 polls/min (we pace at 14/min), 12/min per media operation |
| Media caps | 5 MiB photos, 16 MiB video/audio/documents; inbound downloads capped (64 MiB) |
| Replies | Meta limitation: only the creator receives replies; extra senders can be admitted but Meta refuses replies to non-creators |
| Delivery | At-least-once — dedupe by `wamid`; 409 `poll_conflict` if another poller shares the key |

**Implementation.** `runtime/medot/whatsapp/agent_platform.py` — pure httpx
client ported from the reference implementation
([ahtishamdilawar/hermes-whatsapp-agent-platform](https://github.com/ahtishamdilawar/hermes-whatsapp-agent-platform)
`client.py`), keeping the manual's error taxonomy (NotSent / Ambiguous),
rolling per-minute RateWindows, UTF-16 message splitting, media
upload/get/download with sha256 + size verification, and the updates-envelope
parser. Poll loop, backoff, poll-conflict accounting (3 conflicts → transport
stops with a clear status error), read receipts with typing indicator:
`runtime/medot/whatsapp/manager.py` `AgentPlatformTransport`.

The desktop asks for the key; the runtime stores it in the OS keystore
(account `whatsapp.<user_id>`), records the connection (RLS-scoped
`connector_accounts`, provider `whatsapp_agent_platform`), and starts
long-polling. On restart the runtime resumes connected transports
(keystore + connector rows).

## 2.1 Media limits (Route 1)

Photos 5 MiB JPEG/PNG (larger re-encoded by the platform), video/audio/
documents 16 MiB, captions ≤ 1024 UTF-16 units. Inbound media downloads are
capped and sha256-verified; no exception message ever contains a media
URL/id/filename (log-safe taxonomy kept from the reference implementation).
Media uploads have their own 12/min budget; downloads have none.

## 2.2 Creator-only limitation (Route 1)

Meta currently lets an agent send only to its creator. Admitted non-creator
senders' messages still arrive inbound, but Meta refuses replies to them —
`NotCreatorError` is classified and surfaced in transport status (the `error`
field) instead of crashing the poll loop. Sends default to the last inbound
peer (the creator).

## 2.3 Poll conflict (Route 1)

If another device polls the same agent key, Meta replaces the older poll
(409/1752041). The transport counts conflicts; after 3 in a row it stops with
"a newer poll for this agent replaced this one" in status.

## 3. Route 2 — Baileys bridge (unofficial)

Unofficial — emulates a WhatsApp Web session (QR pairing, persistent session),
small ban risk. A dedicated number is recommended for bot mode.

| Aspect | Value |
|---|---|
| Bridge | `bridges/baileys/index.mjs` (Node 18+, plain ESM, no build step) |
| Runtime side | `runtime/medot/whatsapp/baileys.py` (spawns node, npm-installs deps on first start) |
| Pairing | QR (data-URL PNG via `GET /qr`, rendered by the desktop) — poll until `paired` |
| Inbound | Bridge long-poll `GET /updates?cursor=&timeout=` — same envelope shape as Route 1 |
| Outbound | `POST /send {to, text}` (bare numbers normalized to JIDs; self-chat → own JID) |
| Groups | Supported: `group_policy` (pairing / allowlist / open), `require_mention`, group JIDs `120363...@g.us` |
| Allowlist | `allowed_users` (digits) or `allow_all`; bot mode requires one — otherwise all inbound is denied; self-chat ignores the allowlist |
| Session | Multi-file auth state under `<workspace>/state/whatsapp/baileys-session` (full account access — protect it; never commit) |
| Lifecycle | disconnect keeps the paired session; logout unpair + wipes it |
| Prereq | Node.js 18+ (version-checked); bridge deps auto-installed at first start (npm install is not a build) |

**fromMe semantics** (verified in Baileys source during the Stage 1
evaluation): `fromMe=true` covers every send from the account. Self-chat mode
therefore suppresses the bridge's own send-echoes by message id; bot mode
skips `fromMe` entirely.

Ban-risk guidance: dedicated number for bot mode, conversational pacing, no
bulk/unrequested messaging, re-pair if a WhatsApp Web protocol update breaks
the bridge. Do not scan the QR with your primary number for bot mode unless
you accept the risk.

## 4. Shared transport behavior

Both routes: normalized envelopes → in-memory dedupe → persistence into
`conversations` (upsert on `user_id+channel+peer`; `transport` column tags the
route) and `messages` (upsert on unique `wa_message_id` — duplicate delivery
absorbed). The runtime resumes connected routes on restart. Proactive sends
default to the last inbound peer per route.

## 4.1 Desktop flow

The console offers both routes on the connect screen: paste the Agent
Platform key, scan the Baileys QR, or connect both (each card shows status +
disconnect). Connecting either satisfies "connected" for onboarding; the
other can be added later.

## 5. Historical record — superseded decisions

**2026-11-01 (superseded 2026-11-02):** Agent Platform exclusively. Baileys
and Cloud API retired from the roadmap; a relay was believed required (the
platform was assumed webhook-relayed). The long-poll model makes the relay
unnecessary for the desktop product; the relay concept is parked (OD-13).

**Stage 1 (superseded):** Baileys on a dedicated companion number was
provisionally recommended before the Agent Platform decision. Cloud API
number exclusivity, 24-h window/template rules, and per-message pricing
analysis: see the archived doc `docs/archive/aia/05-integrations.md`.
