"""Identity registry (M2b): specialist identities as data, not code.

Me. the coordinator is seeded by the DB trigger on signup; everything here
manages the rest of the registry: specialists the user creates, their
versioned instructions, and which model profile each one thinks with.
Rows live in Supabase (RLS-scoped); the engine reads them at turn time.
"""
from __future__ import annotations

import re

STATUSES = ("active", "deactivated", "archived")


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "identity"


def list_identities(client, user_id: str) -> list[dict]:
    """All identities with their active instructions merged in."""
    rows = (
        client.table("identities")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    instructions = (
        client.table("identity_instructions")
        .select("identity_id,content_md,version")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    active = {i["identity_id"]: i for i in instructions}
    for row in rows:
        instruction = active.get(row["id"])
        row["instructions_md"] = instruction["content_md"] if instruction else ""
        row["instructions_version"] = instruction["version"] if instruction else None
    return rows


def create_identity(
    client,
    user_id: str,
    *,
    name: str,
    instructions_md: str,
    description: str = "",
    icon: str | None = None,
    model_profile_id: str | None = None,
) -> dict:
    """A new specialist identity with its v1 instructions."""
    name = (name or "").strip()
    if not name:
        raise ValueError("give the identity a name")
    instructions_md = (instructions_md or "").strip()
    if not instructions_md:
        raise ValueError("write the identity's instructions (what it is, how it helps)")

    base = _slug(name)
    slug, n = base, 1
    while (
        client.table("identities")
        .select("id")
        .eq("user_id", user_id)
        .eq("slug", slug)
        .limit(1)
        .execute()
        .data
    ):
        n += 1
        slug = f"{base}-{n}"

    inserted = (
        client.table("identities")
        .insert(
            {
                "user_id": user_id,
                "kind": "specialist",
                "name": name,
                "slug": slug,
                "description": description,
                "icon": icon,
                "model_profile_id": model_profile_id,
            }
        )
        .execute()
        .data
        or []
    )
    if not inserted:
        raise ValueError("could not create the identity")
    identity = inserted[0]
    (
        client.table("identity_instructions")
        .insert(
            {
                "user_id": user_id,
                "identity_id": identity["id"],
                "version": 1,
                "content_md": instructions_md,
                "is_active": True,
            }
        )
        .execute()
    )
    identity["instructions_md"] = instructions_md
    identity["instructions_version"] = 1
    return identity


def update_identity(
    client,
    user_id: str,
    identity_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    icon: str | None = None,
    status: str | None = None,
    model_profile_id: str | None = None,
) -> dict | None:
    """Patch the provided fields; None leaves a field alone. Returns the row."""
    patch: dict = {}
    if name is not None:
        if not name.strip():
            raise ValueError("give the identity a name")
        patch["name"] = name.strip()
    if description is not None:
        patch["description"] = description
    if icon is not None:
        patch["icon"] = icon
    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
        patch["status"] = status
    if model_profile_id is not None:
        patch["model_profile_id"] = model_profile_id
    if not patch:
        raise ValueError("nothing to update")
    rows = (
        client.table("identities")
        .update(patch)
        .eq("id", identity_id)
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def save_instructions(client, user_id: str, identity_id: str, content_md: str) -> dict:
    """A new active version; the previous active version is kept, deactivated."""
    content_md = (content_md or "").strip()
    if not content_md:
        raise ValueError("instructions cannot be empty")
    identity = (
        client.table("identities")
        .select("id")
        .eq("id", identity_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not identity:
        raise ValueError("no such identity")
    existing = (
        client.table("identity_instructions")
        .select("version,is_active")
        .eq("identity_id", identity_id)
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    for row in existing:
        if row["is_active"]:
            client.table("identity_instructions").update({"is_active": False}).eq(
                "identity_id", identity_id
            ).eq("version", row["version"]).execute()
    version = max((r["version"] for r in existing), default=0) + 1
    inserted = (
        client.table("identity_instructions")
        .insert(
            {
                "user_id": user_id,
                "identity_id": identity_id,
                "version": version,
                "content_md": content_md,
                "is_active": True,
            }
        )
        .execute()
        .data
        or []
    )
    return inserted[0] if inserted else {"version": version, "content_md": content_md, "is_active": True}
