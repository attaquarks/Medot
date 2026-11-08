"""MCP tool loading (M7, doc 08 §7): the runtime is an MCP client.

Each connector is a remote streamable-HTTP MCP server. Discovery opens a
session, lists tools and wraps them as LangChain StructuredTools named
`mcp__<server>__<tool>` (the doc's `mcp:<server>:<tool>` namespace, adjusted
to the characters OpenAI function names allow). Every tool CALL opens its
own short-lived session — no long-lived connection state to babysit.
"""
from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("medot.connectors")

TOOL_CACHE_TTL = 300  # seconds; refreshed when a connector changes


def tool_prefix(provider: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in provider.lower())[:40]
    return f"mcp__{cleaned or 'server'}__"


def _py_type(spec: dict) -> Any:
    return {
        "string": str, "number": float, "integer": int, "boolean": bool,
        "array": list, "object": dict,
    }.get(str(spec.get("type", "string")), Any)


def _args_model(tool_name: str, schema: dict):
    """JSON Schema -> a pydantic model LangChain can bind."""
    from pydantic import create_model

    if not isinstance(schema, dict):
        return None
    required = set(schema.get("required", []))
    fields = {}
    for prop, spec in (schema.get("properties") or {}).items():
        if not str(prop).isidentifier():
            continue  # non-identifier arg names cannot become python fields
        if prop in required:
            fields[prop] = (_py_type(spec), ...)
        else:
            fields[prop] = (_py_type(spec), spec.get("default"))
    if not fields:
        return None
    return create_model(f"{tool_name}_args", **fields)


async def _call_tool(connector: dict, headers: dict, tool_name: str, arguments: dict) -> str:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with (
        httpx2.AsyncClient(headers=headers, timeout=30) as http,
        streamable_http_client(connector["url"], http_client=http) as streams,
    ):
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})
            parts = []
            for part in result.content or []:
                text = getattr(part, "text", None)
                if text is not None:
                    parts.append(text)
            # mcp 2.x renamed isError -> is_error; accept both
            if getattr(result, "is_error", None) or getattr(result, "isError", False):
                raise RuntimeError("; ".join(parts) or "the connector reported an error")
            return "\n".join(parts) or "(no output)"


def _wrap_tool(connector: dict, headers: dict, prefix: str, raw: dict) -> Any:
    from langchain_core.tools import StructuredTool

    tool_name = f"{prefix}{raw['name']}"
    args_model = _args_model(tool_name, raw.get("inputSchema"))

    async def _run(**kwargs):
        return await _call_tool(connector, headers, raw["name"], kwargs)

    return StructuredTool(
        name=tool_name,
        description=(raw.get("description") or raw["name"])[:1000],
        args_schema=args_model,
        coroutine=_run,
    )


async def list_server_tools(url: str, headers: dict) -> list[dict]:
    """Live discovery — the console's test button and the cache loader."""
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with (
        httpx2.AsyncClient(headers=headers, timeout=30) as http,
        streamable_http_client(url, http_client=http) as streams,
    ):
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            # mcp 2.x renamed inputSchema -> input_schema; accept both
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None),
                }
                for t in listed.tools
            ]


_cache: dict[str, tuple[float, list]] = {}


def invalidate_cache(connector_id: str | None = None) -> None:
    if connector_id:
        _cache.pop(connector_id, None)
    else:
        _cache.clear()


async def load_tools(client, user_id: str, identity_id: str, keystore) -> list:
    """Enabled connectors granted to this identity -> wrapped LangChain tools."""
    import asyncio

    from ..tools.registry import DEFAULT_TOOLS

    def _granted_rows():
        return (
            client.table("identity_connector_grants")
            .select("connector_account_id")
            .eq("identity_id", identity_id)
            .eq("user_id", user_id)
            .execute()
            .data
            or []
        )

    def _connector_rows():
        return (
            client.table("connector_accounts")
            .select("id,provider,url,auth_header_name,enabled")
            .eq("user_id", user_id)
            .eq("enabled", True)
            .execute()
            .data
            or []
        )

    granted = await asyncio.to_thread(_granted_rows)
    if not granted:
        return []
    allowed = {g["connector_account_id"] for g in granted}
    rows = await asyncio.to_thread(_connector_rows)
    tools: list = []
    own_names = {t.name for t in DEFAULT_TOOLS}
    for row in rows:
        if row["id"] not in allowed or not row["url"]:
            continue
        cached = _cache.get(row["id"])
        now = time.monotonic()
        if cached and now - cached[0] < TOOL_CACHE_TTL:
            tools.extend(cached[1])
            continue
        headers = {}
        if row["auth_header_name"]:
            secret = keystore.get_secret(f"connectors.{user_id}.{row['id']}")
            if secret:
                headers[row["auth_header_name"]] = secret
        try:
            listed = await list_server_tools(row["url"], headers)
        except Exception as exc:  # noqa: BLE001 - a down connector must not break the turn
            log.warning("connector %s unreachable: %s", row["provider"], exc)
            continue
        prefix = tool_prefix(row["provider"])
        wrapped = [
            _wrap_tool(row, headers, prefix, raw)
            for raw in listed
            if f"{prefix}{raw['name']}" not in own_names
        ]
        _cache[row["id"]] = (now, wrapped)
        tools.extend(wrapped)
    return tools
