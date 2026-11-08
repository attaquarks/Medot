"""KnowledgeService (M3): reads the knowledge tables the way the console
shows them — Areas (domains) → Topics (entity nodes) → Facts (edges with
dates) — plus a read-only record browser over the structured record store.

Writes are not here on purpose: facts arrive via memory extraction (M3a),
records via the record-capture flow that comes later.
"""
from __future__ import annotations


def overview(client, user_id: str) -> dict:
    """Every area with plain counts; the summary the Knowledge screen opens on."""
    domains = (
        client.table("knowledge_domains")
        .select("id,slug,title,summary,owner_identity_id")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    nodes = (
        client.table("knowledge_nodes")
        .select("id,domain_id")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    facts = (
        client.table("knowledge_edges")
        .select("id,domain_id,valid_from")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    episodes = (
        client.table("memory_episodes")
        .select("id")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    out = []
    for domain in domains:
        domain_id = domain["id"]
        domain_facts = [f for f in facts if f["domain_id"] == domain_id]
        out.append(
            {
                **domain,
                "topics": sum(1 for n in nodes if n["domain_id"] == domain_id),
                "facts": len(domain_facts),
                "latest_fact_at": max((f["valid_from"] for f in domain_facts), default=None),
            }
        )
    return {"domains": out, "episodes_total": len(episodes)}


def domain_detail(client, user_id: str, domain_id: str) -> dict | None:
    """One area: its topics and its facts with dates (newest first)."""
    domains = (
        client.table("knowledge_domains")
        .select("id,slug,title,summary,owner_identity_id")
        .eq("id", domain_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not domains:
        return None
    topics = (
        client.table("knowledge_nodes")
        .select("id,name,summary,node_type")
        .eq("user_id", user_id)
        .eq("domain_id", domain_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    facts = (
        client.table("knowledge_edges")
        .select("id,fact,relation,valid_from,valid_to")
        .eq("user_id", user_id)
        .eq("domain_id", domain_id)
        .order("valid_from", desc=True)
        .limit(100)
        .execute()
        .data
        or []
    )
    return {"domain": domains[0], "topics": topics, "facts": facts}


def records(client, user_id: str, domain_id: str) -> dict:
    """Structured records in an area (read-only browser; capture comes later)."""
    rows = (
        client.table("domain_records")
        .select("id,type_key,data,occurred_at")
        .eq("user_id", user_id)
        .eq("domain_id", domain_id)
        .order("occurred_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    titles: dict[str, str] = {}
    if rows:
        schemas = (
            client.table("domain_schemas")
            .select("type_key,title")
            .in_("type_key", sorted({r["type_key"] for r in rows}))
            .execute()
            .data
            or []
        )
        titles = {s["type_key"]: s["title"] for s in schemas}
    return {
        "records": [
            {"id": r["id"], "type_key": r["type_key"], "type_title": titles.get(r["type_key"], r["type_key"]),
             "data": r["data"], "occurred_at": r["occurred_at"]}
            for r in rows
        ]
    }
