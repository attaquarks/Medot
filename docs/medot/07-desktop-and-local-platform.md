# Medot — Desktop Application & Local Platform

Status: **Stage 1 deliverable** — Tauri/Supabase specifics verified against
official docs, Oct 2026 (Tauri 2.12.x stable line).

---

## 1. Shell

**Tauri 2 + React + TypeScript**, keeping the Python runtime as a supervised
**sidecar** process. Windows first (WebView2), macOS/Linux supported.
(Verified: Tauri 2.12.x stable & production-ready; the sidecar mechanism via
`bundle.externalBin` + shell permissions is the official pattern for a
PyInstaller-onedir Python runtime.)

- The desktop is a **management console** — never a chat surface.
- The Python runtime (`medot-runtime`) runs as a child process supervised by
  the Tauri shell. (No WhatsApp sidecar: Me. connects through the WhatsApp
  Agent Platform via the Medot relay — see `03-whatsapp-connection-strategy.md`.
- Communication: runtime serves a **loopback-only HTTP API** (`127.0.0.1`,
  authenticated with a per-launch token shared over stdout/pipe) consumed by
  the React UI via Tauri commands or direct fetch. No ports exposed beyond
  loopback except the WhatsApp transport's own needs.
- **Window close ≠ exit.** Verified mechanism: intercept
  `onCloseRequested` → `preventDefault()` → `window.hide()` (requires the
  `core:window:allow-hide` capability, not in the default set) to tray, keep
  the runtime alive. "Quit Medot" (tray menu) stops runtime + sidecars
  cleanly. This lifecycle rule is tested in Milestone 1.
- Google sign-in plumbing: `signInWithOAuth` (PKCE flow) with
  `redirect_to = medot://auth/callback`; requires **tauri-plugin-deep-link +
  tauri-plugin-single-instance** (deep links arrive as argv to a second
  process on Windows), a Supabase redirect allow-list entry, and validation
  of the callback payload (deep-link URLs are spoofable — validate the
  Supabase `state`). supabase-py's PKCE handling is under-documented —
  prototype this first (Milestone 1 AC1).
- Auto-updates: `tauri-plugin-updater` with mandatory minisign signatures
  (verification cannot be disabled); Windows install modes passive/basicUi;
  note every update re-ships the ~100 MB Python sidecar.

## 2. Navigation

```
Overview        status of Me., WhatsApp connection, model, recent activity
Identities      identity list (Me. first, then specialists) + create flow
  └─ Identity   per-identity detail (below)
Knowledge       graph/domain explorer (read-oriented, plain language)
Connectors      connected accounts + per-identity grants
Browser         profiles and permissions
AI Providers    model profiles, credentials, default profiles
Activity        runs, approvals, fact changes timeline
Settings        profile, timezone, privacy, backups, diagnostics
```

## 3. Identity detail pages (per identity, including Me.)

| Tab | Content |
|---|---|
| Overview | Name, icon, slug/command, description, status toggle, owned domain summary |
| Instructions | Markdown editor for the instruction document (versioned; save = new version) |
| Knowledge | This identity's domain: hierarchy/graph explorer in plain language ("Areas → Topics → Facts with dates"), domain summary, record browser |
| Memory | Recent episodes contributing to the domain; extraction status; correct/delete-a-fact affordances |
| Tools | Assigned tools with read/write flags and approval requirements |
| Connectors | Which connected accounts this identity may use and at what scope |
| Model | Model profile (provider, model, parameters, fallback), per-purpose overrides |
| Permissions | Who can invoke it (Me. background invocation on/off), approval policy |
| Activity | Run history, pending approvals, messages it contributed to |

Language rule: the UI says **spaces/areas/knowledge**, never "nodes/edges/
embeddings/group_id". Facts render with their dates ("Weight 74.2 kg — recorded
2 Nov 2026"); historical vs current is visually distinct.

## 4. Onboarding flow (MVP)

1. Sign in with Google (system browser; deep-link callback).
2. Initialize account (automatic: profile, Me., global domain).
3. Connect WhatsApp: the user links the Medot agent in WhatsApp's Agent
   Manager and pastes the API key (goes to the OS keystore); the relay links
   the account to this desktop.
4. Pick AI provider + model; enter key (goes to OS keystore).
5. Done → Overview.

## 5. Local filesystem layout

```
%APPDATA%/Medot/                     (win)  ~/Library/Application Support/Medot (mac) ~/.local/share/medot (linux)
├─ workspace/
│  ├─ documents/<user>/              user-provided documents & attachments (staged, then ref'd by episodes)
│  ├─ identities/<id>/exports/       optional Markdown exports of instructions
│  ├─ browser/profiles/<name>/       Playwright persistent profiles
│  ├─ downloads/                     files fetched by the runtime
├─ state/
│  ├─ spool.db                       SQLite offline spool (outbound queue, pending extraction)
│  ├─ checkpoints/                   LangGraph SQLite checkpoints (per conversation thread)
│  └─ logs/                          rotating structured logs (redaction processor retained from AIA)
└─ config/app.toml                   non-secret app config (ports, locale) — never secrets
```

Canonical instruction text lives in **Supabase** (`identity_instructions`);
local Markdown is export/edit affordance with one-way sync (OD-7). Secrets
(API keys, WhatsApp session secrets, OAuth refresh tokens, browser state
passphrases) live in the **OS keystore** via the `keyring` wrapper retained
from AIA (Windows Credential Manager / macOS Keychain / Linux Secret Service).
No secrets in `.env`, JSON, Markdown, or database rows.

## 6. Packaging

- Python runtime bundled via **PyInstaller (onedir)** as a Tauri sidecar
  resource; Playwright browsers installed on first use into the workspace.
- Windows: NSIS/MSI installer; code signing decision tracked as OD-10.
- Auto-updates via Tauri updater plugin (decision validated in research pass).
- Crash recovery: runtime logs + spool ensure inbound WhatsApp messages and
  pending extraction survive restarts.

## 7. Accessibility & tone

Large-type-friendly defaults, high-contrast palette, keyboard navigable,
no decorative animation, plain-language labels throughout, and a
"Explain this" affordance on every technical concept (model, connector,
approval) in the UI.
