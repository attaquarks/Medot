"""Supabase client factory — publishable key + user session only (AC6).

The service-role key never appears in this process: RLS is the security
boundary, evaluated against the user's JWT attached to every request.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from ..config import get_settings


@lru_cache
def anonymous_client() -> Client:
    """Client without a user session — only for pre-auth operations."""
    s = get_settings()
    if not s.configured:
        raise RuntimeError("Supabase is not configured (MEDOT_SUPABASE_URL / _PUBLISHABLE_KEY).")
    return create_client(s.supabase_url, s.supabase_publishable_key)


def client_for_session(access_token: str) -> Client:
    """Client whose PostgREST/Storage calls run as the authenticated user."""
    if not access_token:
        raise ValueError("access_token is required — unauthenticated writes are rejected by RLS")
    client = anonymous_client()
    client.postgrest.auth(access_token)
    return client
