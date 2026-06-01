"""Idempotent database bootstrap:  python -m aia.db.init

Ensures pgvector + the three schemas exist, then creates all tables from the
SQLAlchemy metadata. Safe to run repeatedly. For real migrations later, switch to
Alembic (already a dependency) — this keeps first-run friction to zero.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from ..logging import configure_logging, get_logger
from . import models  # noqa: F401  (import populates Base.metadata)
from .base import SCHEMA_BUSINESS, SCHEMA_CORE, SCHEMA_HEALTH, Base, get_engine

log = get_logger("db.init")


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        for schema in (SCHEMA_CORE, SCHEMA_BUSINESS, SCHEMA_HEALTH):
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        await conn.run_sync(Base.metadata.create_all)
    log.info("db_initialised")


def main() -> None:
    configure_logging()
    asyncio.run(init_db())


if __name__ == "__main__":
    main()
