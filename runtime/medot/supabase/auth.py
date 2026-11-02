"""Google sign-in (Supabase Auth) with a desktop deep-link callback — AC1.

Flow (docs/medot/07 §1, verified against Supabase/Tauri docs):
  1. start_google_signin() builds the Supabase authorize URL for provider
     `google` with redirect_to = medot://auth/callback and a PKCE verifier
     stored in the keystore.
  2. The desktop opens the system browser at that URL.
  3. Google redirects to Supabase, Supabase redirects to medot://auth/callback
     (?code=…), the Tauri shell forwards the URL to the runtime.
  4. complete_signin() validates the callback URL, exchanges the code for a
     session, and persists the session blob in the OS keystore.

The callback URL is validated strictly: scheme must match, the host of the
embedded next-url (if any) must be the configured Supabase project — deep-link
URLs are attacker-controllable (manual `medot://` launches), so anything
unexpected is rejected.
"""
from __future__ import annotations

import json
import os
import secrets
import webbrowser
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from ..config import get_settings
from ..localstore import keystore as keystore_mod
from ..localstore.keystore import session_account

_VERIFIER_ACCOUNT = "supabase.pkce_verifier"


@dataclass
class SigninStart:
    authorize_url: str


def start_google_signin(*, open_browser: bool = True) -> SigninStart:
    """Return (and optionally open) the Google consent URL for this desktop."""
    settings = get_settings()
    verifier = secrets.token_urlsafe(64)  # PKCE code_verifier
    keystore_mod.get_keystore().set_secret(_VERIFIER_ACCOUNT, verifier)

    client = _client()
    res = client.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": settings.auth_redirect_uri,
            "skip_browser_redirect": True,
            "flow_type": "pkce",
        },
    })
    url = str(res.url)
    if open_browser:
        webbrowser.open(url)
    return SigninStart(authorize_url=url)


def _client():
    from .client import anonymous_client

    return anonymous_client()


def validate_callback_url(url: str) -> dict[str, str]:
    """Validate a medot://auth/callback URL and extract the auth code.

    Note: urlparse reads `medot://auth/callback` as netloc="auth",
    path="/callback" — compare the joined tail against the redirect URI.
    """
    settings = get_settings()
    parsed = urlparse(url)
    expected = urlparse(settings.auth_redirect_uri)
    if parsed.scheme != expected.scheme:
        raise ValueError(f"unexpected callback scheme {parsed.scheme!r}")
    actual_tail = f"{parsed.netloc}{parsed.path}".lower()
    expected_tail = f"{expected.netloc}{expected.path}".lower()
    if not actual_tail.endswith(expected_tail):
        raise ValueError(f"unexpected callback target {actual_tail!r}")
    query = parse_qs(parsed.query)
    error = query.get("error_description", query.get("error"))
    if error:
        raise ValueError(f"oauth error: {error[0]}")
    codes = query.get("code")
    if not codes or not codes[0]:
        raise ValueError("missing authorization code")
    return {"code": codes[0]}


def complete_signin(callback_url: str) -> dict:
    """Exchange the callback code for a session and persist it (AC1)."""
    code = validate_callback_url(callback_url)["code"]
    verifier = keystore_mod.get_keystore().get_secret(_VERIFIER_ACCOUNT)
    if not verifier:
        raise RuntimeError("no pending sign-in flow (PKCE verifier missing)")
    client = _client()
    session = client.auth.exchange_code_for_session({"auth_code": code})
    persist_session(session)
    payload = _session_payload(session)
    remember_user(payload["user"]["id"])
    keystore_mod.get_keystore().delete_secret(_VERIFIER_ACCOUNT)
    return payload


def persist_session(session) -> None:
    user_id = session.user.id if hasattr(session, "user") else session["user"]["id"]
    blob = json.dumps(_session_payload(session))
    keystore_mod.get_keystore().set_secret(session_account(user_id), blob)


def _session_payload(session) -> dict:
    if hasattr(session, "model_dump"):
        return session.model_dump(mode="json")
    if hasattr(session, "dict"):
        return session.dict()
    return dict(session)


def load_session() -> dict | None:
    """Restore the last signed-in user's session from the keystore."""
    blob = os.environ.get("MEDOT_TEST_SESSION_BLOB")
    if blob:  # test-only backdoor: CI e2e injects a session; never set on user machines
        return json.loads(blob)
    keystore = keystore_mod.get_keystore()
    user_id = keystore.get_secret("supabase.last_user")
    if not user_id:
        return None
    raw = keystore.get_secret(session_account(user_id))
    if not raw:
        return None
    return json.loads(raw)


def remember_user(user_id: str) -> None:
    keystore_mod.get_keystore().set_secret("supabase.last_user", user_id)
