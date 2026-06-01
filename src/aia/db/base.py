"""Async SQLAlchemy engine, session factory, and declarative base."""
from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..config import get_settings

# Logical separation of the two agents (Requirement #1: "separate databases").
# One Postgres instance, three schemas, no cross-agent foreign keys.
SCHEMA_CORE = "core"
SCHEMA_BUSINESS = "business"
SCHEMA_HEALTH = "health"


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope. Commits on success, rolls back on error."""
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
