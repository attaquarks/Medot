"""Long-term semantic memory (pgvector).

Stores durable facts, preferences and rolling summaries as embeddings and
retrieves them by cosine similarity. Namespaced by (tenant, agent) so agents are
fully isolated.
"""
from __future__ import annotations

from sqlalchemy import select

from ..db.base import session_scope
from ..db.models import LongTermMemory
from ..llm.router import get_router


class LongTermStore:
    def __init__(self, agent: str):
        self.agent = agent
        self._llm = get_router()

    async def remember(
        self, tenant: str, content: str, *, kind: str = "fact", meta: dict | None = None
    ) -> str:
        embedding = await self._llm.embed(content)
        async with session_scope() as s:
            row = LongTermMemory(
                tenant_id=tenant,
                agent=self.agent,
                kind=kind,
                content=content,
                embedding=embedding,
                meta=meta or {},
            )
            s.add(row)
            await s.flush()
            return row.id

    async def recall(self, tenant: str, query: str, *, k: int = 5) -> list[str]:
        """Return the k most semantically relevant memories for this agent."""
        q_emb = await self._llm.embed(query)
        async with session_scope() as s:
            stmt = (
                select(LongTermMemory.content)
                .where(
                    LongTermMemory.tenant_id == tenant,
                    LongTermMemory.agent == self.agent,
                )
                # pgvector cosine distance operator via SQLAlchemy
                .order_by(LongTermMemory.embedding.cosine_distance(q_emb))
                .limit(k)
            )
            rows = await s.execute(stmt)
            return [r[0] for r in rows.all()]
