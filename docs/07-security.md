# 07 · Security

## 7.1 Threat model

A laptop install. Primary risks: (a) a stolen disk / leaked DB dump exposing account tokens,
(b) one connected account leaking into another agent's context, (c) the agent taking an
irreversible third-party action by mistake. The controls below target each.

## 7.2 Credentials — no plaintext, ever

**Envelope encryption** ([`security/crypto.py`](../src/aia/security/crypto.py)):

```
master key (OS keychain)  ──wraps──>  per-row data key  ──encrypts──>  token
stored blob = base64(wrapped_data_key) "." base64(ciphertext)
```

- **Master key** lives in the **OS keychain** (macOS Keychain / Windows Credential Manager / Linux Secret Service) via `keyring`, auto-generated on first run. It never touches Postgres or `.env`. Headless installs may set `AIA_MASTER_KEY`.
- **Per-row data keys** limit blast radius and make **master-key rotation** cheap (`rotate_master` re-wraps the small data key; secrets aren't re-encrypted).
- Only `core.credentials.encrypted_blob` holds tokens — encrypted. A DB dump alone is useless without the keychain.

## 7.3 OAuth 2.0

- Authorization-code flow with `state` (CSRF) and server-side code exchange ([`integrations/oauth.py`](../src/aia/integrations/oauth.py)). The browser never receives a token.
- Least-privilege scopes per provider; refresh tokens stored encrypted (refresh on expiry is a `TODO(impl)` with the contract in place).

## 7.4 Data isolation

- **Per-agent**: separate Postgres schemas + memory namespaces; long-term recall is filtered by `agent`, so the Health coach cannot read Business CRM data and vice-versa.
- **Per-tenant**: every row carries `tenant_id`; hosted deployments enable Postgres **row-level security** keyed on a session `tenant_id` (see [03](03-database-schema.md) §3.6).

## 7.5 Action safety

- Agents **read freely** but gate **visible third-party actions** (send email, move/cancel meeting, place call) behind explicit user intent; ambiguous requests trigger a clarifying question.
- High-stakes items **escalate** to the principal on WhatsApp rather than the agent acting unilaterally.

## 7.6 Audit logging

Append-only `core.audit_logs` records every sensitive action (credential use, email sent, meeting
mutated, call placed, escalation) with agent, action, resource, timestamp
([`security/audit.py`](../src/aia/security/audit.py)). Answers "what did my agent do, and when?".

## 7.7 Secret hygiene & network

- `structlog` redaction processor scrubs anything matching token/secret/password/api-key/authorization before logs are written ([`logging.py`](../src/aia/logging.py)).
- `.gitignore` excludes `.env`, `*.key`, `auth_info*/`, data volumes.
- Local-first: with no cloud LLM key set, **no data leaves the device**. When cloud fallback is enabled, only the specific hard-task prompt is sent to the chosen provider — document this to users.

## 7.8 Hardening checklist for production

- [ ] Implement OAuth refresh-token rotation + revocation on disconnect.
- [ ] Add HMAC signature verification on Twilio and WhatsApp Cloud webhooks.
- [ ] Enable Postgres RLS + TLS; encrypt volumes at rest (FileVault/BitLocker/LUKS).
- [ ] Rate-limit the gateway; verify Baileys sidecar is bound to localhost only.
- [ ] Per-tenant KMS-backed master keys when hosted (AWS KMS / GCP KMS envelope).
