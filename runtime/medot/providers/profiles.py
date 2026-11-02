"""Model profiles: CRUD over `model_profiles` (RLS-scoped) + OS keystore keys.

The keystore account is `providers.<user_id>.<profile_id>` (stable across
renames); the row stores only `credential_ref`, never a key.
"""
from __future__ import annotations

import re

from ..localstore import keystore as keystore_mod

PURPOSES = ("chat", "extraction", "embedding", "planning")
_SLUG = re.compile(r"[^a-z0-9-]+")


def _credential_account(user_id: str, profile_id: str) -> str:
    return keystore_mod.provider_account(user_id, profile_id)


def save_profile(
    client,
    user_id: str,
    keystore: keystore_mod.Keystore,
    *,
    profile_id: str | None,
    name: str,
    purpose: str,
    provider: str,
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict:
    """Create or update a profile. The key (when given) goes to the keystore."""
    from .discovery import PROVIDERS

    name = (name or "").strip()
    if not name:
        raise ValueError("give this model profile a name")
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of: {', '.join(PURPOSES)}")
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    model = (model or "").strip()
    if not model:
        raise ValueError("pick a model (fetch the list or type an id)")

    row = {
        "user_id": user_id,
        "name": name,
        "purpose": purpose,
        "provider": provider,
        "model": model,
        "api_base": (api_base or "").strip() or None,
    }

    if profile_id:
        existing = (
            client.table("model_profiles").select("id,credential_ref").eq("id", profile_id).eq("user_id", user_id).limit(1).execute().data
            or []
        )
        if not existing:
            raise ValueError("profile not found")
        if api_key:
            keystore.set_secret(_credential_account(user_id, profile_id), api_key.strip())
        client.table("model_profiles").update(row).eq("id", profile_id).execute()
        return {**row, "id": profile_id}

    inserted = client.table("model_profiles").insert(row).execute().data or []
    saved = inserted[0]
    if api_key:
        keystore.set_secret(_credential_account(user_id, saved["id"]), api_key.strip())
    return saved


def list_profiles(client, user_id: str) -> list[dict]:
    return (
        client.table("model_profiles")
        .select("id,name,purpose,provider,model,api_base,credential_ref,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )


def delete_profile(client, user_id: str, keystore: keystore_mod.Keystore, profile_id: str) -> None:
    rows = (
        client.table("model_profiles").select("id").eq("id", profile_id).eq("user_id", user_id).limit(1).execute().data
        or []
    )
    if not rows:
        raise ValueError("profile not found")
    client.table("model_profiles").delete().eq("id", profile_id).execute()
    keystore.delete_secret(_credential_account(user_id, profile_id))


def load_key(keystore: keystore_mod.Keystore, user_id: str, profile_id: str) -> str | None:
    return keystore.get_secret(_credential_account(user_id, profile_id))


async def verify_profile(client, user_id: str, keystore: keystore_mod.Keystore, profile_id: str) -> dict:
    """Actually call the model with the stored key — the real end-to-end check."""
    rows = (
        client.table("model_profiles")
        .select("id,provider,model,api_base")
        .eq("id", profile_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError("profile not found")
    key = load_key(keystore, user_id, profile_id)
    if not key:
        raise ValueError("no key stored for this profile — edit it and paste the key again")
    from .discovery import litellm_target

    row = rows[0]
    model_string, api_base = litellm_target(row["provider"], row["model"], row["api_base"])
    import time

    import litellm

    start = time.monotonic()
    response = await litellm.acompletion(
        model=model_string,
        api_key=key,
        api_base=api_base,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=8,
        num_retries=0,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    text = (response.choices[0].message.content or "").strip()
    return {"ok": True, "latency_ms": latency_ms, "sample": text[:120], "model_string": model_string}
