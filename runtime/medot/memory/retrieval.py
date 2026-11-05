"""Knowledge retrieval (M3b): before each turn, recall.

Pulls facts from the user's knowledge graph that are relevant to the
incoming message and returns a prompt block — so Me. knows things without
needing a recall tool call (docs/medot/04 §memory layers, 11 §7 context
segment). Keyword matching only; embeddings come later if the graph
outgrows it.
"""
from __future__ import annotations

import re

# words too common to match on; everything <= 3 chars is dropped too
_STOPWORDS = frozenset({
    "what", "when", "where", "which", "with", "that", "this", "have",
    "does", "did", "was", "were", "are", "can", "could", "would",
    "should", "about", "remember", "know", "tell", "think", "there",
    "their", "them", "then", "from", "your", "please", "okay", "just",
    "like", "want", "need", "good", "well", "yeah",
})

MAX_KEYWORDS = 8
MAX_LINES = 8


def keywords(text: str) -> list[str]:
    """Content words of the message, first-seen order, capped."""
    words = re.findall(r"[a-z0-9']{4,}", text.lower())
    seen: list[str] = []
    for word in words:
        if word in _STOPWORDS or word in seen:
            continue
        seen.append(word)
        if len(seen) == MAX_KEYWORDS:
            break
    return seen


def retrieve_knowledge(client, user_id: str, text: str) -> str:
    """A prompt block of relevant remembered facts, or "" when nothing matches."""
    words = keywords(text)
    if not words:
        return ""
    nodes = (
        client.table("knowledge_nodes")
        .select("name,summary")
        .eq("user_id", user_id)
        .or_(",".join(f"name.ilike.%{w}%,summary.ilike.%{w}%" for w in words))
        .limit(MAX_LINES)
        .execute()
        .data
        or []
    )
    facts = (
        client.table("knowledge_edges")
        .select("fact")
        .eq("user_id", user_id)
        .or_(",".join(f"fact.ilike.%{w}%" for w in words))
        .limit(MAX_LINES)
        .execute()
        .data
        or []
    )
    lines = [n["name"] + (f" — {n['summary']}" if n.get("summary") else "") for n in nodes]
    lines += [e["fact"] for e in facts]
    if not lines:
        return ""
    return "What you remember that may be relevant here:\n" + "\n".join(f"- {line}" for line in lines)
