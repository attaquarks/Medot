"""Account initialization verification (AC2).

The database trigger `handle_new_user` (migration 0001) creates profile,
user_settings, the Me. coordinator identity (with v1 instructions) and the
global knowledge domain at signup. This module verifies completeness after
sign-in so the desktop can surface a clear error instead of a broken app.

supabase-py's PostgREST client is synchronous — callers on the async API path
wrap this in `asyncio.to_thread`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Initialization:
    user_id: str
    me_identity_id: str
    global_domain_id: str
    complete: bool
    missing: list[str]


def verify_initialization(client, user_id: str) -> Initialization:
    missing: list[str] = []

    def _rows(builder) -> list[dict]:
        return builder.execute().data or []

    if not _rows(client.table("profiles").select("id").eq("id", user_id).limit(1)):
        missing.append("profiles")
    if not _rows(client.table("user_settings").select("user_id").eq("user_id", user_id).limit(1)):
        missing.append("user_settings")

    me = _rows(client.table("identities").select("id,domain_id")
               .eq("user_id", user_id).eq("slug", "me").eq("kind", "coordinator").limit(1))
    me_identity_id = me[0]["id"] if me else ""
    if not me_identity_id:
        missing.append("identities.me")

    if me_identity_id and not _rows(
        client.table("identity_instructions").select("id")
        .eq("identity_id", me_identity_id).eq("version", 1).limit(1)
    ):
        missing.append("identity_instructions.me.v1")

    domain = _rows(client.table("knowledge_domains").select("id")
                   .eq("user_id", user_id).eq("slug", "global").limit(1))
    global_domain_id = domain[0]["id"] if domain else ""
    if not global_domain_id:
        missing.append("knowledge_domains.global")

    if me_identity_id and global_domain_id:
        linked = _rows(client.table("identities").select("id")
                       .eq("id", me_identity_id).eq("domain_id", global_domain_id).limit(1))
        if not linked:
            missing.append("identities.me.domain_link")

    return Initialization(
        user_id=user_id,
        me_identity_id=me_identity_id,
        global_domain_id=global_domain_id,
        complete=not missing,
        missing=missing,
    )
