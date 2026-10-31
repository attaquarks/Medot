# Medot — WhatsApp Connection Strategy

Status: **Stage 1 deliverable** — research verified Oct 2026 against official
Meta docs, the WhatsApp FAQ, WhatsApp ToS, and Baileys source.

Requirement recap: **one** WhatsApp conversational identity (Me.) per user;
specialist identities never appear on WhatsApp; proactive outbound (daily
messages) must work; transport must be replaceable; unofficial transports and
their risks must be named honestly.

---

## 1. The four options (verified)

| | (a) WhatsApp "Agents" (Meta Agent Platform) | (b) Cloud API (Business Platform) | (c) Baileys, dedicated companion number | (d) Baileys, user's primary number |
|---|---|---|---|---|
| Status Oct 2026 | **Closed beta** — consumer feature, up to 5 third-party agents per account; **no public developer onboarding** (no portal/waitlist; unanswered dev-community threads). Non-E2EE; Meta-relayed API key model | Official, GA | Unofficial linked-device client | Unofficial linked-device client |
| Onboarding (non-technical) | Easy once GA | Heavy: Meta portfolio, WABA, dedicated number, tokens; number **excluded from the consumer app** while registered | Scan QR once; user supplies a cheap SIM/eSIM for the companion number | Scan QR in Linked Devices — trivial |
| Proactive outbound | Presumably yes (undocumented) | Only via **pre-approved templates** outside the 24-h customer-service window; per-message pricing (service messages re-charged Oct 2026; 1,000 free/month per number) | Unrestricted | Unrestricted — but sends **as the user** |
| Policy risk | None (official) | None | ToS violation; ban loses a disposable number | ToS violation; ban loses the user's real number — **catastrophic** |
| Fit | Conceptual end-state | Poor UX for a personal companion ("chatting with a business") | **Good** | **Disqualified** |

## 2. Why (d) — Baileys on the user's own number — is disqualified

Verified from Baileys source (`decode-wa-message.ts`): `fromMe = true` means
*the message was sent by the account the session belongs to* — the primary
phone, **any** linked device, or the Baileys client itself. Consequences on a
primary-number session:

- A companion would see all of the user's chats (privacy/trust failure).
- Outbound messages send **as the user** to real contacts — unacceptable for
  an assistant product.
- The standard `if (m.key.fromMe) continue` bot pattern **breaks entirely**:
  every message the user types is `fromMe`, so the bot never sees its own
  user. This is the key semantic difference from a dedicated-number session,
  where `fromMe` messages are genuinely only the bot's own sends and the skip
  pattern is correct.

## 3. Recommendation (MVP)

**Transport: Baileys on a dedicated companion number (secondary SIM/eSIM),
behind a `Transport` interface; Cloud API implemented as the compliant
alternative; Agent Platform tracked as the future sanctioned path.**

1. Onboarding renders the QR in Desktop; the user links the companion number
   like WhatsApp Web. Session persists (`useMultiFileAuthState` equivalent);
   reconnect on app restart; `loggedOut` → re-pair flow in Desktop.
2. **fromMe policy** (transport contract): on the companion number, skip
   `fromMe` inbound echoes for command processing but log own sends to
   message history; keep the existing AIA group/broadcast filters.
3. Ban-risk management is operational, not technical: strictly 1:1,
   low-volume, human-paced traffic to the single opted-in user; no bulk
   sends ever; document the risk and the "use a secondary number" guidance
   prominently (carried over from AIA's honesty note).
4. Reliability: dedupe by WhatsApp message id, ordered per-chat processing,
   offline spool (SQLite) for outbound while the runtime restarts, and
   idempotent sends. The AIA sidecar's reconnect logic is retained and
   hardened.
5. Cloud API adapter (already exists in AIA) stays tested so the switch is a
   configuration change: it suits users who want the fully official path and
   accept template-based proactive messages.

## 4. What must be true for the transport to stay replaceable

- Companion logic, identity state, and history live **only** in Medot
  (Supabase + local spool); nothing WhatsApp-side is load-bearing.
- `Transport` interface: `pair()`, `connect()`, `send(peer, text)`,
  `on_inbound(handler)`, `health()`, normalized message envelope
  (id, peer, text, timestamp, direction, transport-specific extras).
- Both adapters pass the same contract tests (fixture-driven: pair, inbound
  dedupe, outbound retry, reconnect-after-kill).

## 5. Trigger points to revisit

- **Agent Platform opens developer onboarding** → migrate as the sanctioned
  path (architecture already fits: one agent chat, internal identities).
- **A user's companion number is banned** → cheap recovery (new number +
  re-pair); if bans become common at low volume, Cloud API becomes default.
- **Cloud API template rules relax** for 1:1 utility messaging → re-evaluate
  cost/UX balance.

## 6. OD-3 (Stage 2): the centralized Cloud API option — analysis, no decision yet

Requirement: onboarding simple enough for a non-technical user, without forcing
a second SIM purchase. The third architecture worth evaluating is **one official
WhatsApp Business number operated by Medot, shared by all users**:

| Concern | Centralized Cloud API (one Medot number) |
|---|---|
| Onboarding | Best possible: user just messages the published Medot number — no QR, no SIM purchase. Account linking = verify ownership of that WhatsApp account (e.g. confirm a code Medot sends) |
| Multi-user identification | Inbound webhook carries the sender `wa_id` (per-user); Medot maps `wa_id → user_id` after verification. One conversation per user — fits the "one WhatsApp identity" model exactly |
| Outbound / proactive | 24-h customer-service window per user; **outside it only pre-approved templates** — daily briefs must ship as utility templates (Meta approval per template + per-category pricing). Service messages re-charged Oct 2026 with 1,000 free/month **per number — shared across ALL users**, a hard scaling ceiling |
| Message routing to the user's runtime | Requires a **Medot-operated relay**: cloud webhook receiver → per-user fan-out → the user's desktop runtime over a persistent outbound connection (desktop dials out; no inbound ports). Offline desktops need server-side queueing with replay + TTL, and the relay must never store message bodies beyond delivery (privacy) |
| Infrastructure | Always-on cloud service (webhook + queue + relay auth) — the product's first server component, with 24×7 availability expectations; a real cost and ops commitment the desktop-only MVP avoids |
| Privacy / isolation | Multi-tenant number: Meta sees one traffic pattern; tenant isolation enforced in the relay; risk of cross-user routing bugs is a new failure class that local-only transports don't have |
| Costs & limits | Per delivered message (1,000 free service msgs/month per number), 250-recipient tier initially; template approvals add review latency for every new proactive message type |
| Policy | Fully official — no ToS risk, no ban exposure |

**Trade-off summary**: the centralized number wins decisively on onboarding
friction and policy safety, and loses on: a mandatory always-on relay service
(first server component, contradicts the desktop-local MVP), template
constraints on proactive messages, shared free-tier limits, and new
multi-tenant routing/privacy failure modes. The companion-number Baileys
transport keeps the product fully local but requires a SIM.

**Status**: OPEN. No transport is implemented in Milestone 1; the decision
deadline is **Milestone 5 planning**, and the transport abstraction (§4) keeps
all three options implementable. The relay design (persistent outbound
connection + queueing) is a prerequisite if this option is chosen and must be
prototyped before commitment.
