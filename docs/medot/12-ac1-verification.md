# AC1 End-to-End Verification — Google Sign-In on Windows

Status: **Active procedure** for closing Milestone 1's AC1 with real Google
credentials. Estimated time: ~10 minutes, one-time.

**Rule: your client secret never enters chat, code, or git.** It lives in
`supabase/.env.local` (gitignored) and in your Supabase provider config only.

## Context

Milestone 1 was verified against the **local Supabase stack** (Docker, on your
machine). There is no hosted Medot project yet — one will be created when we
move to shared/hosted testing (needs your Supabase account; the local stack
does not require it and is sufficient for AC1).

## Step 1 — Your actions in Google Cloud (one-time)

1. Google Cloud Console → **APIs & Services → Credentials** → open your
   OAuth 2.0 Client.
2. The client type must be **Web application** (Supabase Auth redirects
   through a web callback).
3. Under **Authorized redirect URIs**, add exactly:
   ```
   http://127.0.0.1:54321/auth/v1/callback
   ```
   (Google permits `http` only for localhost/127.0.0.1 — this is the local
   stack's auth callback.)
4. Keep the Client ID / Client Secret for the next step. Do not paste them
   anywhere else.

## Step 2 — Your actions on this machine (one-time)

1. Copy the template and fill in your credentials:
   ```
   copy supabase\.env.example supabase\.env.local
   ```
   then edit `supabase/.env.local`:
   ```
   SUPABASE_AUTH_GOOGLE_CLIENT_ID=<your client id>
   SUPABASE_AUTH_GOOGLE_SECRET=<your client secret>
   ```
2. Start the stack with credentials loaded:
   ```
   powershell -File scripts\start-stack.ps1
   ```
   (`supabase/.env.local` is gitignored — verify with `git status` that it
   does not appear.)

## Step 3 — Automated smoke check (agent-runnable)

```bash
curl -sI "http://127.0.0.1:54321/auth/v1/authorize?provider=google&redirect_to=medot://auth/callback"
```
Expected: **HTTP 302** with `location: https://accounts.google.com/o/oauth2/...`
— proves the Google provider is configured and `medot://auth/callback` is
accepted. A 400 here means Step 1/2 was missed.

## Step 4 — The genuine end-to-end run (both)

1. Start the desktop app in dev mode (shell A):
   ```powershell
   cd desktop
   $env:MEDOT_DEV_RUNTIME = "1"
   npm run tauri dev
   ```
   (dev builds register the `medot://` protocol at runtime — added for this
   verification; installed builds get it from the installer.)
2. In the Medot window, click **Sign in with Google**.
3. The system browser opens Google's consent screen → choose your account →
   consent.
4. Google redirects to Supabase → Supabase redirects to
   `medot://auth/callback?code=…` → Windows hands the URL to the running
   Medot app (deep-link, single-instance) → the runtime validates and
   exchanges the code (PKCE) → the session is stored in Windows Credential
   Manager.
5. The window flips to "Signed in. Me. is ready — your account is set up."
   and `/bootstrap` reports the trigger-created profile, settings, Me.
   identity, and global domain for the **real Google account**.

Pass criteria: session restored after restarting the app without re-consent
(keystore persistence), and `/bootstrap.complete == true`.

## What "done" means for AC1

- [ ] Step 3 smoke check returns 302 → accounts.google.com
- [ ] Step 4 completes sign-in through the real browser + real deep link
- [ ] Session persists across app restart (no re-consent)
- [ ] `/bootstrap` returns `complete: true` for the Google-authenticated user

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Step 3 returns 400 | Google provider not configured | Re-run `start-stack.ps1`; check `.env.local` keys |
| `redirect_uri_mismatch` at Google | Redirect URI not added in Google Cloud | Re-do Step 1.3 exactly |
| Browser says "can't open medot://" | Dev protocol not registered | Run via `npm run tauri dev` (Step 4.1), not the browser alone |
| Sign-in completes but window unchanged | Runtime not reachable | Check runtime is up (`/health`), launch token handshake in logs |
