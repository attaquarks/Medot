"""Two-tier memory.

  ShortTermMemory  -> Redis. Rolling conversation window per (agent, peer).
                      Cheap, fast, evicted by length/TTL. Feeds the prompt.
  LongTermMemory   -> Postgres + pgvector. Durable facts/preferences/summaries,
                      retrieved by semantic similarity. Survives restarts.

Each agent uses its own namespace, so the Business and Health agents never see
each other's memory (Requirement #1).
"""
from .short_term import ShortTermMemory
from .long_term import LongTermStore

__all__ = ["ShortTermMemory", "LongTermStore"]
